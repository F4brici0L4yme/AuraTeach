"""
anatomy_model.py
-------------------------------------------------------------------
Módulo de Modelado Biomédico 3D y Despiece por Capas Anatómicas
(STARK Bio-Anatomy Engine) para STARK Mark v3:
- Arquitectura de Ensamble Anatómico Multicapa (compatible con SceneModel).
- Estrategia Híbrida: Prioridad 1 ingesta GLTF/GLB externa (`assets/corazon.glb`),
  Prioridad 2 respaldo procedural SDF/paramétrico suave de alta resolución (>= 40x48)
  con normales suaves analíticas/numéricas por vértice.
- 4 Capas Biológicas Concéntricas / Jerárquicas canónicas:
  * Capa 1: Miocardio / Pared muscular externa (`capa_muscular`).
  * Capa 2: Cavidades y Válvulas internas (`sistema_valvular`).
  * Capa 3: Sistema Vascular / Aorta y Cava (`sistema_circulatorio`).
  * Capa 4: Sistema de Conducción Eléctrico y Coronario (`sistema_nervioso`).
- Presets Clínicos Didácticos: Corazón Humano y Encéfalo / Cráneo Multicapa.
- Latido Fisiológico Asimétrico en tiempo real (Sístole rápida y Diástole prolongada)
  con desfase aurículo-ventricular diferenciado entre aurículas y ventrículos.
- Simulación Hemodinámica de Flujo Sanguíneo por GPU Instancing:
  160 partículas animadas (azul desoxigenada / roja oxigenada) con cero bucles
  Python en el pipeline de renderizado e interruptor [ FLUJO: ON/OFF ].
- Dos Modos de Disección Virtual: Despiece Axial Anatómico y Modo Peeling
  (Retirada secuencial de capas externas), más aislamiento selectivo de piezas.
- Integración con GlRenderer (ModernGL / Z-Buffer / Blinn-Phong) y fallback CPU
  con OpenCV (casting int32 estricto).
- Tarjetas de información clínica flotantes y callouts con directrices quebradas.
-------------------------------------------------------------------
"""

import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from hologram import (
    ASSETS_DIR,
    Objeto3D,
    SceneModel,
    rotation_matrix,
)

logger = logging.getLogger("AnatomySTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)


# ====================================================================
# GENERADORES PROCEDURALES DE ALTA FIDELIDAD BIOMÉDICA (>= 40x48)
# ====================================================================

def _generar_malla_grid_parametrico(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    z_grid: np.ndarray,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """
    Construye vértices, aristas, caras triangulares y normales unitarias suaves
    a partir de cuadrículas 2D (Nu, Nv). Calcula normales suaves por vértice.
    """
    Nu, Nv = x_grid.shape
    verts = np.stack([x_grid.flatten(), y_grid.flatten(), z_grid.flatten()], axis=1).astype(np.float32)

    faces_list: List[List[int]] = []
    edges_set = set()

    for i in range(Nu - 1):
        for j in range(Nv):
            j_next = (j + 1) % Nv
            i00 = i * Nv + j
            i01 = i * Nv + j_next
            i10 = (i + 1) * Nv + j
            i11 = (i + 1) * Nv + j_next

            faces_list.append([i00, i10, i01])
            faces_list.append([i01, i10, i11])

            edges_set.add(tuple(sorted((i00, i01))))
            edges_set.add(tuple(sorted((i00, i10))))
            edges_set.add(tuple(sorted((i10, i11))))
            edges_set.add(tuple(sorted((i01, i11))))
            edges_set.add(tuple(sorted((i10, i01))))

    faces_arr = np.array(faces_list, dtype=np.int32)
    normals = np.zeros_like(verts)

    if len(faces_arr) > 0:
        v0 = verts[faces_arr[:, 0]]
        v1 = verts[faces_arr[:, 1]]
        v2 = verts[faces_arr[:, 2]]
        fn = np.cross(v1 - v0, v2 - v0)
        np.add.at(normals, faces_arr[:, 0], fn)
        np.add.at(normals, faces_arr[:, 1], fn)
        np.add.at(normals, faces_arr[:, 2], fn)

    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    lens[lens < 1e-6] = 1.0
    normals = (normals / lens).astype(np.float32)

    edges_list = [tuple(int(x) for x in e) for e in edges_set]
    return verts, edges_list, faces_list, normals


def generar_malla_corazon_miocardio(
    Nu: int = 40,
    Nv: int = 48,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """
    Capa 1 (Externa): Miocardio / Pared muscular externa del corazón.
    Genera un esferoide cardioide anatómico suave de alta densidad (Nu>=40, Nv>=48),
    con el ápex ventricular inferior apuntando hacia abajo-izquierda, masa ventricular asimétrica
    y surcos interventriculares anterior y posterior.
    """
    u = np.linspace(0.015, np.pi - 0.015, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")

    # Ecuación paramétrica de miocardio con curvatura anatómica
    y = np.cos(U) * 1.18 - 0.08 * np.sin(U) * np.cos(V)
    r_base = np.sin(U) * (0.98 - 0.24 * np.cos(U))
    # Surco interventricular anterior y posterior
    surco = 1.0 - 0.06 * (np.sin(V) ** 2)
    # Asimetría cardíaca izquierda-derecha (ventrículo izquierdo más potente y convexo)
    asimetria = 1.0 + 0.16 * np.cos(V) - 0.05 * np.sin(2 * V)

    r_xy = r_base * surco * asimetria
    x = r_xy * np.cos(V) * (1.0 + 0.12 * np.cos(V)) - 0.12 * (1.0 - np.cos(U))
    z = r_xy * np.sin(V) * 0.88 + 0.04 * np.cos(U)

    return _generar_malla_grid_parametrico(x, y, z)


def generar_malla_corazon_valvulas(
    Nu: int = 40,
    Nv: int = 48,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """
    Capa 2 (Media): Cavidades internas (4 cámaras: aurículas y ventrículos)
    y anillos valvulares (mitral, tricúspide, aórtica y pulmonar).
    """
    u = np.linspace(0.03, np.pi - 0.03, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")

    # Cavidad interna ligeramente más compacta
    y = np.cos(U) * 0.90 + 0.04
    # Modulación de 4 lóbulos que representan las 4 cámaras cardíacas
    r_camaras = 0.74 + 0.15 * np.sin(2 * V) * np.cos(U)
    tabique = 1.0 - 0.07 * (np.cos(2 * V) ** 2)
    r_xy = np.sin(U) * r_camaras * tabique
    x = r_xy * np.cos(V) * 0.95 - 0.08 * (1.0 - np.cos(U))
    z = r_xy * np.sin(V) * 0.80

    return _generar_malla_grid_parametrico(x, y, z)


def generar_malla_corazon_circulatorio(
    N_slices: int = 48,
    N_circ: int = 24,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """
    Capa 3 (Vascular): Arteria Aorta tubular con cayado aórtico,
    tronco pulmonar bifurcado y vena cava superior e inferior.
    """
    t_vals = np.linspace(0.0, 1.0, N_slices)
    path = []
    radios = []

    # Trayectoria del cayado aórtico en 3D
    for t in t_vals:
        if t < 0.40:
            # Sección ascendente desde ventrículo izquierdo
            s = t / 0.40
            px = 0.05 + 0.06 * s
            py = 0.35 + 0.65 * s
            pz = 0.05 - 0.06 * s
            r = 0.18 + 0.02 * np.sin(s * np.pi)
        elif t < 0.75:
            # Cayado aórtico curvado hacia dorsal-izquierda
            s = (t - 0.40) / 0.35
            ang = s * np.pi * 0.85
            px = 0.11 - 0.50 * (1.0 - np.cos(ang * 0.7))
            py = 1.00 - 0.20 * np.sin(ang * 0.7)
            pz = -0.01 - 0.46 * np.sin(ang)
            r = 0.18 - 0.02 * s
        else:
            # Aorta torácica descendente
            s = (t - 0.75) / 0.25
            px = -0.38 - 0.05 * s
            py = 0.80 - 0.95 * s
            pz = -0.42 + 0.08 * s
            r = 0.16
        path.append([px, py, pz])
        radios.append(r)

    path_arr = np.array(path, dtype=np.float32)
    angles = np.linspace(0, 2 * np.pi, N_circ, endpoint=False)

    x_grid = np.zeros((N_slices, N_circ), dtype=np.float32)
    y_grid = np.zeros((N_slices, N_circ), dtype=np.float32)
    z_grid = np.zeros((N_slices, N_circ), dtype=np.float32)

    for i in range(N_slices):
        c_pt = path_arr[i]
        r_i = radios[i]
        if i < N_slices - 1:
            T = path_arr[i + 1] - c_pt
        else:
            T = c_pt - path_arr[i - 1]
        T_len = np.linalg.norm(T)
        T = T / max(T_len, 1e-5)

        ref = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        if abs(np.dot(T, ref)) > 0.90:
            ref = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        N = np.cross(T, ref)
        N = N / max(np.linalg.norm(N), 1e-5)
        B = np.cross(T, N)

        for j in range(N_circ):
            th = angles[j]
            offset = r_i * (np.cos(th) * N + np.sin(th) * B)
            pt = c_pt + offset
            x_grid[i, j] = pt[0]
            y_grid[i, j] = pt[1]
            z_grid[i, j] = pt[2]

    return _generar_malla_grid_parametrico(x_grid, y_grid, z_grid)


def generar_malla_corazon_nervioso(
    N_nodes: int = 40,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """
    Capa 4 (Núcleo Eléctrico y Coronario):
    - Sistema de conducción bioeléctrico: Nodo Sinusal, Nodo AV, Haz de His,
      ramas izquierda y derecha, y Red de Purkinje.
    - Árbol coronario: Arterias coronarias anterior descendente y circunfleja.
    """
    nodos_coords = [
        # Nodo Sinusal (marcapasos)
        [ 0.45,  0.80, -0.15],
        # Vías internodales
        [ 0.35,  0.65, -0.12],
        [ 0.28,  0.50, -0.08],
        [ 0.20,  0.35, -0.05],
        # Nodo AV
        [ 0.08,  0.22,  0.00],
        # Haz de His (tabique interventricular)
        [ 0.04,  0.10,  0.02],
        [ 0.00, -0.05,  0.03],
        [-0.04, -0.20,  0.04],
        [-0.08, -0.38,  0.05],
        # Rama Izquierda
        [-0.15, -0.52,  0.07],
        [-0.24, -0.68,  0.10],
        [-0.30, -0.82,  0.12],
        [-0.22, -0.96,  0.08],
        # Rama Derecha
        [ 0.03, -0.52,  0.03],
        [ 0.12, -0.68,  0.04],
        [ 0.18, -0.82,  0.05],
        [ 0.10, -0.96,  0.02],
        # Fibras de Purkinje apicales
        [-0.14, -1.04,  0.05],
        [-0.06, -1.08,  0.02],
        [ 0.02, -1.04, -0.02],
        # Arterias coronarias
        [ 0.05,  0.18,  0.22],
        [ 0.02,  0.00,  0.24],
        [-0.02, -0.18,  0.22],
        [-0.08, -0.36,  0.20],
        [-0.14, -0.55,  0.16],
        [-0.18, -0.74,  0.12],
        [ 0.20,  0.15,  0.18],
        [ 0.28,  0.00,  0.14],
        [ 0.32, -0.18,  0.08],
        [ 0.28, -0.36,  0.04],
    ]

    conexiones = [
        (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8),
        # Rama izquierda
        (8, 9), (9, 10), (10, 11), (11, 12), (12, 17), (17, 18),
        # Rama derecha
        (8, 13), (13, 14), (14, 15), (15, 16), (16, 18), (18, 19),
        # Arterias coronarias
        (20, 21), (21, 22), (22, 23), (23, 24), (24, 25),
        (20, 26), (26, 27), (27, 28), (28, 29),
    ]

    todos_verts: List[np.ndarray] = []
    todas_caras: List[List[int]] = []
    todas_aristas: List[Tuple[int, int]] = []

    def _generar_nodo_bioelectrico(r: float = 0.042) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
        v = np.array([
            [ r,  0,  0],
            [-r,  0,  0],
            [ 0,  r,  0],
            [ 0, -r,  0],
            [ 0,  0,  r],
            [ 0,  0, -r],
        ], dtype=np.float32)
        f = [
            [0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
            [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5],
        ]
        e = [(0, 2), (2, 1), (1, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4), (0, 5), (1, 5), (2, 5), (3, 5)]
        return v, e, f

    r_nodo = 0.042
    v_base, e_base, f_base = _generar_nodo_bioelectrico(r=r_nodo)

    for i, c_pt in enumerate(nodos_coords):
        offset_idx = len(todos_verts) * len(v_base)
        v_despl = v_base + np.array(c_pt, dtype=np.float32)
        todos_verts.append(v_despl)
        for f in f_base:
            todas_caras.append([int(idx + offset_idx) for idx in f])
        for a, b in e_base:
            todas_aristas.append((int(a + offset_idx), int(b + offset_idx)))

    for u_idx, v_idx in conexiones:
        if u_idx < len(nodos_coords) and v_idx < len(nodos_coords):
            c1 = u_idx * len(v_base)
            c2 = v_idx * len(v_base)
            todas_aristas.append((int(c1), int(c2)))

    verts_arr = np.vstack(todos_verts).astype(np.float32)
    normals_arr = np.zeros_like(verts_arr)
    for f in todas_caras:
        if len(f) >= 3:
            v0 = verts_arr[f[0]]
            v1 = verts_arr[f[1]]
            v2 = verts_arr[f[2]]
            fn = np.cross(v1 - v0, v2 - v0)
            for idx in f:
                normals_arr[idx] += fn
    lens = np.linalg.norm(normals_arr, axis=1, keepdims=True)
    lens[lens < 1e-6] = 1.0
    normals_arr = (normals_arr / lens).astype(np.float32)

    return verts_arr, todas_aristas, todas_caras, normals_arr


# --- GENERADORES PARA PRESET CRÁNEO / ENCÉFALO ---

def generar_malla_cerebro_craneo(
    Nu: int = 16,
    Nv: int = 24,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """Capa 1 (Cráneo): Bóveda y calvaria ósea marfil."""
    u = np.linspace(0.02, np.pi * 0.72, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    y = np.cos(U) * 0.95 + 0.10
    rx = np.sin(U) * 0.88 * (1.0 + 0.05 * np.cos(2 * V))
    rz = np.sin(U) * 1.10
    x = rx * np.cos(V)
    z = rz * np.sin(V) + 0.08
    return _generar_malla_grid_parametrico(x, y, z)


def generar_malla_cerebro_meninges(
    Nu: int = 14,
    Nv: int = 20,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """Capa 2 (Meninges): Duramadre y membranas protectoras."""
    u = np.linspace(0.04, np.pi * 0.75, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    y = np.cos(U) * 0.86 + 0.08
    rx = np.sin(U) * 0.80
    rz = np.sin(U) * 1.00
    x = rx * np.cos(V)
    z = rz * np.sin(V) + 0.06
    return _generar_malla_grid_parametrico(x, y, z)


def generar_malla_cerebro_corteza(
    Nu: int = 18,
    Nv: int = 28,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """Capa 3 (Corteza Cerebral): Hemisferios con circunvoluciones y surcos procedurales."""
    u = np.linspace(0.05, np.pi * 0.82, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    fisura = 1.0 - 0.18 * np.abs(np.cos(V)) ** 8
    giros = 1.0 + 0.05 * np.sin(6 * U) * np.cos(10 * V)
    y = (np.cos(U) * 0.78 + 0.06) * giros
    rx = np.sin(U) * 0.74 * fisura * giros
    rz = np.sin(U) * 0.92 * giros
    x = rx * np.cos(V)
    z = rz * np.sin(V) + 0.05
    return _generar_malla_grid_parametrico(x, y, z)


def generar_malla_cerebro_limbico(
    Nu: int = 12,
    Nv: int = 16,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]], np.ndarray]:
    """Capa 4 (Sistema Límbico y Tallo Encefálico): Núcleo límbico y puente troncoencefálico."""
    u = np.linspace(0.10, np.pi * 0.90, Nu)
    v = np.linspace(0, 2 * np.pi, Nv, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    y = np.cos(U) * 0.55 - 0.25
    rx = np.sin(U) * 0.38
    rz = np.sin(U) * 0.48
    x = rx * np.cos(V)
    z = rz * np.sin(V)
    return _generar_malla_grid_parametrico(x, y, z)


# ====================================================================
# CATÁLOGO DE METADATOS CLÍNICOS DIDÁCTICOS
# ====================================================================

PRESETS_ANATOMIA: Dict[str, Dict[str, Any]] = {
    "corazon": {
        "id": "corazon",
        "nombre_organo": "Corazon Humano (Cardiologia)",
        "organo": "Corazon",
        "bpm_default": 72.0,
        "capas": [
            {
                "part_id": "capa_muscular",
                "capa_idx": 1,
                "capa_nombre": "Pared Muscular Externa (Miocardio)",
                "nombre_clinico": "Miocardio Ventricular",
                # Carmín orgánico [0.78, 0.15, 0.18] -> BGR: (46, 38, 199)
                "color_rgb": [0.78, 0.15, 0.18],
                "color_bgr": (46, 38, 199),
                "vector_axial": np.array([0.0, 0.0, 1.25], dtype=np.float32),
                "funcion_fisiologica": "Bomba muscular: Contraccion ventricular coordinada y generacion de presion sistolica.",
            },
            {
                "part_id": "sistema_valvular",
                "capa_idx": 2,
                "capa_nombre": "Cavidades y Valvulas Internas",
                "nombre_clinico": "Ventriculos y Valvulas Cardiacas",
                # Rosa coral / tejido interno [0.90, 0.45, 0.45] -> BGR: (115, 115, 230)
                "color_rgb": [0.90, 0.45, 0.45],
                "color_bgr": (115, 115, 230),
                "vector_axial": np.array([-1.25, 0.0, 0.0], dtype=np.float32),
                "funcion_fisiologica": "Flujo unidireccional auriculoventricular (mitral, tricuspide, aortica).",
            },
            {
                "part_id": "sistema_circulatorio",
                "capa_idx": 3,
                "capa_nombre": "Sistema Vascular (Aorta y Cava)",
                "nombre_clinico": "Cayado Aortico y Vasos Mayores",
                # Rojo arterial brillante [0.95, 0.10, 0.10] -> BGR: (25, 25, 242)
                "color_rgb": [0.95, 0.10, 0.10],
                "color_bgr": (25, 25, 242),
                "vector_axial": np.array([0.0, 1.25, -0.45], dtype=np.float32),
                "funcion_fisiologica": "Distribucion oxigenada sistemica a alta presion y retorno venoso central.",
            },
            {
                "part_id": "sistema_nervioso",
                "capa_idx": 4,
                "capa_nombre": "Sistema de Conduccion Bioelectrica",
                "nombre_clinico": "Nodo Sinusal y Red de Purkinje",
                # Amarillo bioeléctrico neón [0.95, 0.85, 0.10] -> BGR: (25, 217, 242)
                "color_rgb": [0.95, 0.85, 0.10],
                "color_bgr": (25, 217, 242),
                "vector_axial": np.array([1.10, -0.65, 0.0], dtype=np.float32),
                "funcion_fisiologica": "Marcapasos natural autonomo y despolarizacion rapida del sincitio cardiaco.",
            },
        ],
    },
    "cerebro": {
        "id": "cerebro",
        "nombre_organo": "Encefalo / Craneo (Neurologia)",
        "organo": "Encefalo",
        "bpm_default": 0.0,
        "capas": [
            {
                "part_id": "capa_osea",
                "capa_idx": 1,
                "capa_nombre": "Boveda Craneal (Hueso)",
                "nombre_clinico": "Calvaria Craneal Osea",
                "color_rgb": [0.92, 0.90, 0.80],
                "color_bgr": (204, 230, 235),
                "vector_axial": np.array([0.0, 1.30, 0.0], dtype=np.float32),
                "funcion_fisiologica": "Proteccion mecanica y blindaje rigido de la masa encefalica.",
            },
            {
                "part_id": "meninges",
                "capa_idx": 2,
                "capa_nombre": "Meninges y Duramadre",
                "nombre_clinico": "Membrana Meningea y LCR",
                "color_rgb": [0.80, 0.40, 0.50],
                "color_bgr": (128, 102, 204),
                "vector_axial": np.array([0.0, 0.0, 1.25], dtype=np.float32),
                "funcion_fisiologica": "Barrera biologica y amortiguacion hidrostatica de liquido cefalorraquideo.",
            },
            {
                "part_id": "corteza_cerebral",
                "capa_idx": 3,
                "capa_nombre": "Hemisferios y Corteza Cerebral",
                "nombre_clinico": "Sustancia Gris y Circunvoluciones",
                "color_rgb": [0.75, 0.55, 0.65],
                "color_bgr": (166, 140, 191),
                "vector_axial": np.array([-1.25, 0.0, 0.0], dtype=np.float32),
                "funcion_fisiologica": "Funciones cognitivas superiores, memoria, lenguaje y motricidad fina.",
            },
            {
                "part_id": "sistema_limbico",
                "capa_idx": 4,
                "capa_nombre": "Sistema Limbico y Tallo Cerebral",
                "nombre_clinico": "Talamo, Hipocampo y Tronco Encefalico",
                "color_rgb": [0.95, 0.85, 0.10],
                "color_bgr": (25, 217, 242),
                "vector_axial": np.array([0.0, -1.25, 0.0], dtype=np.float32),
                "funcion_fisiologica": "Regulacion homeostatica autonoma, alerta cardiorrespiratoria y emociones.",
            },
        ],
    },
}


# ====================================================================
# CLASE PRINCIPAL: MODELO ANATÓMICO 3D (STARK BIO-ANATOMY)
# ====================================================================

class AnatomicalPiezasDict(dict):
    """Diccionario de piezas con longitud canónica de 4 capas y soporte para alias anatómicos."""
    ALIASES = {
        "ventriculo_izq": "capa_muscular",
        "ventriculo_der": "capa_muscular",
        "miocardio": "capa_muscular",
        "auricula_izq": "sistema_valvular",
        "auricula_der": "sistema_valvular",
        "valvulas": "sistema_valvular",
        "cayado_aortico": "sistema_circulatorio",
        "aorta": "sistema_circulatorio",
        "vena_cava_sup": "sistema_circulatorio",
        "tronco_pulmonar": "sistema_circulatorio",
        "arterias_coronarias": "sistema_nervioso",
        "coronarias": "sistema_nervioso",
        "purkinje": "sistema_nervioso",
    }

    def __getitem__(self, key: Any) -> Any:
        if key in self:
            return super().__getitem__(key)
        alias = self.ALIASES.get(str(key).lower())
        if alias and alias in self:
            return super().__getitem__(alias)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            return super().get(key, default)
        alias = self.ALIASES.get(str(key).lower())
        if alias and alias in self:
            return super().get(alias, default)
        return default


class ModeloAnatomico(SceneModel):
    """
    Modelo Anatómico Multicapa con Soporte para Despiece Axial, Peeling y Hemodinámica
    (STARK Bio-Anatomy Engine):
    - Estrategia Híbrida: Prioridad 1 ingesta GLB externa / Prioridad 2 respaldo procedural.
    - 4 Capas concéntricas/jerárquicas perfectamente aislables.
    - Animación fisiológica asimétrica de sístole/diástole con desfase aurículo-ventricular.
    - Simulación hemodinámica de flujo sanguíneo por GPU Instancing (160 partículas azul/roja).
    - Modos de disección 'AXIAL', 'PEELING' y aislamiento selectivo con callouts interactivos.
    """

    # Waypoints anatómicos del flujo hemodinámico en coordenadas locales
    _WAYPOINTS_FLUX_AZUL = np.array([
        [ 0.35,  0.85, -0.05],  # Vena Cava Superior
        [ 0.38,  0.45, -0.05],  # Aurícula Derecha
        [ 0.25,  0.10,  0.05],  # Válvula Tricúspide
        [ 0.18, -0.40,  0.12],  # Ventrículo Derecho
        [ 0.05, -0.20,  0.15],  # Cono Arterioso
        [-0.15,  0.45,  0.10],  # Tronco Pulmonar
        [-0.30,  0.65,  0.05],  # Arteria Pulmonar Izquierda
    ], dtype=np.float32)

    _WAYPOINTS_FLUX_ROJO = np.array([
        [-0.35,  0.50, -0.20],  # Venas Pulmonares
        [-0.30,  0.35, -0.10],  # Aurícula Izquierda
        [-0.15,  0.05,  0.00],  # Válvula Mitral
        [-0.20, -0.55,  0.08],  # Ventrículo Izquierdo / Ápex
        [-0.05, -0.10,  0.05],  # Vestíbulo Aórtico
        [ 0.05,  0.40,  0.00],  # Aorta Ascendente
        [-0.05,  0.95, -0.10],  # Cayado Aórtico
        [-0.35,  0.80, -0.25],  # Aorta Descendente
    ], dtype=np.float32)

    def set_tipo(self, tipo_modelo: str) -> None:
        """Protección estricta: ModeloAnatomico preserva sus capas y no se sobrescribe con cubo."""
        tipo_lower = str(tipo_modelo).lower()
        if any(org in tipo_lower for org in ("cerebro", "craneo", "encefalo")):
            if self.preset_actual != "cerebro":
                self.cargar_organo("cerebro")
        elif any(org in tipo_lower for org in ("corazon", "cardio")):
            if self.preset_actual != "corazon":
                self.cargar_organo("corazon")

    def __init__(
        self,
        preset: str = "corazon",
        pos_mundo: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        escala: float = 1.0,
        color: Tuple[int, int, int] = (46, 38, 199),
        base: float = 200.0,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        k_explosion: float = 140.0,
    ) -> None:
        self.es_modelo_anatomico: bool = True
        self.preset_actual: str = preset.lower() if preset.lower() in PRESETS_ANATOMIA else "corazon"

        # Modos de Disección: 'AXIAL' vs 'PEELING'
        self.modo_diseccion: str = "AXIAL"
        self.capas_retiradas: int = 0

        # Animación Fisiológica en Tiempo Real (Latido Cardíaco)
        self.latido_activo: bool = (self.preset_actual == "corazon")
        self.bpm: float = 72.0
        self.escala_pulso_actual: float = 1.0
        self.t_onda_actual: float = 0.0
        self.ultimo_t_frame: float = time.time()

        # Simulación Hemodinámica de Flujo Sanguíneo (GPU Instancing)
        self.flujo_sanguineo_activo: bool = True
        self.n_particulas_flujo: int = 160
        self._fases_base_azul: np.ndarray = np.linspace(0.0, 1.0, 80, endpoint=False, dtype=np.float32)
        self._fases_base_rojo: np.ndarray = np.linspace(0.0, 1.0, 80, endpoint=False, dtype=np.float32)

        # Foco e Inspección Táctil
        self.capa_foco_id: Optional[str] = None
        self.mostrar_hud: bool = True
        self.rects_botones_hud: Dict[str, Tuple[int, int, int, int]] = {}
        self.ultimo_toque_tiempo: float = 0.0
        self.ultimo_cursor_pos: Optional[Tuple[float, float]] = None

        super().__init__(
            tipo_modelo=f"anatomia_{self.preset_actual}",
            pos_mundo=pos_mundo,
            rotacion=rotacion,
            escala=escala,
            color=color,
            base=base,
            config=config,
            k_explosion=k_explosion,
        )

        # Construir y registrar las 4 capas anatómicas
        self.cargar_preset(self.preset_actual)

    def cargar_preset(self, preset_id: str) -> bool:
        """
        Carga e inicializa las 4 capas anatómicas para el órgano seleccionado.
        Aplica Estrategia Híbrida:
        - Prioridad 1: Busca modelo externo 'assets/corazon.glb' o '.gltf'.
        - Prioridad 2: Si no existe, genera malla procedural suave (>= 40x48) con normales suaves.
        """
        p_id = preset_id.lower().strip()
        if p_id in ("craneo", "encefalo", "brain"):
            p_id = "cerebro"
        elif p_id in ("heart", "cardiologia", "cardiaco"):
            p_id = "corazon"

        if p_id not in PRESETS_ANATOMIA:
            p_id = "corazon"

        info = PRESETS_ANATOMIA[p_id]
        self.preset_actual = p_id
        self.tipo_modelo = f"anatomia_{p_id}"
        self.piezas = AnatomicalPiezasDict()
        self.centroides_locales.clear()
        self.jerarquia.clear()
        self.matrices_locales.clear()
        self.capas_retiradas = 0

        mallas = []

        if p_id == "corazon":
            self.latido_activo = True
            self.bpm = 72.0

            # Prioridad 1: Carga GLB/GLTF si existe en assets
            candidatos_corazon = [
                os.path.join(ASSETS_DIR, "anatomia", "corazon.glb"),
                os.path.join(ASSETS_DIR, "corazon.glb"),
                os.path.join(ASSETS_DIR, "anatomia", "corazon.gltf"),
                os.path.join(ASSETS_DIR, "corazon.gltf"),
            ]
            ruta_externa = next((c for c in candidatos_corazon if os.path.exists(c)), None)
            gltf_exitoso = False

            if ruta_externa:
                try:
                    from hologram import cargar_ensamble_gltf_glb
                    res_g = cargar_ensamble_gltf_glb(ruta_externa)
                    if res_g and res_g.get("nodos"):
                        nodos = res_g["nodos"]
                        if len(nodos) >= 4:
                            for idx, meta in enumerate(info["capas"]):
                                nodo = nodos[idx % len(nodos)]
                                v_loc = np.asarray(nodo["vertices_locales"], dtype=np.float32)
                                e_loc = [tuple(int(x) for x in e) for e in nodo.get("aristas", [])]
                                f_loc = [list(f) for f in nodo.get("caras", [])]
                                n_loc = np.asarray(nodo.get("normales_locales", np.zeros_like(v_loc)), dtype=np.float32)
                                mallas.append((v_loc, e_loc, f_loc, n_loc))
                        else:
                            # 1 nodo: asignar al miocardio y complementar con válvulas, vascularización y conducción
                            nodo0 = nodos[0]
                            v_loc = np.asarray(nodo0["vertices_locales"], dtype=np.float32)
                            e_loc = [tuple(int(x) for x in e) for e in nodo0.get("aristas", [])]
                            f_loc = [list(f) for f in nodo0.get("caras", [])]
                            n_loc = np.asarray(nodo0.get("normales_locales", np.zeros_like(v_loc)), dtype=np.float32)
                            mallas.append((v_loc, e_loc, f_loc, n_loc))
                            v_c2, e_c2, f_c2, n_c2 = generar_malla_corazon_valvulas(Nu=40, Nv=48)
                            v_c3, e_c3, f_c3, n_c3 = generar_malla_corazon_circulatorio(N_slices=48, N_circ=24)
                            v_c4, e_c4, f_c4, n_c4 = generar_malla_corazon_nervioso(N_nodes=40)
                            mallas.extend([
                                (v_c2, e_c2, f_c2, n_c2),
                                (v_c3, e_c3, f_c3, n_c3),
                                (v_c4, e_c4, f_c4, n_c4),
                            ])
                        gltf_exitoso = True
                        logger.info(f"ModeloAnatomico: Corazón 3D cargado desde archivo externo GLTF/GLB '{ruta_externa}'")
                except Exception as e_glb:
                    logger.warning(f"ModeloAnatomico: Falló carga GLB corazón ({e_glb}). Activando respaldo procedural SDF.")

            # Prioridad 2: Respaldo Procedural SDF/Paramétrico de Alta Fidelidad (>= 40x48)
            if not gltf_exitoso:
                v_c1, e_c1, f_c1, n_c1 = generar_malla_corazon_miocardio(Nu=40, Nv=48)
                v_c2, e_c2, f_c2, n_c2 = generar_malla_corazon_valvulas(Nu=40, Nv=48)
                v_c3, e_c3, f_c3, n_c3 = generar_malla_corazon_circulatorio(N_slices=48, N_circ=24)
                v_c4, e_c4, f_c4, n_c4 = generar_malla_corazon_nervioso(N_nodes=40)
                mallas = [
                    (v_c1, e_c1, f_c1, n_c1),
                    (v_c2, e_c2, f_c2, n_c2),
                    (v_c3, e_c3, f_c3, n_c3),
                    (v_c4, e_c4, f_c4, n_c4),
                ]
        else:
            self.latido_activo = False
            self.bpm = 0.0

            # Prioridad 1: Carga GLB/GLTF de cerebro si existe en assets
            candidatos_cerebro = [
                os.path.join(ASSETS_DIR, "anatomia", "cerebro.glb"),
                os.path.join(ASSETS_DIR, "cerebro.glb"),
                os.path.join(ASSETS_DIR, "anatomia", "cerebro.gltf"),
                os.path.join(ASSETS_DIR, "cerebro.gltf"),
            ]
            ruta_externa_c = next((c for c in candidatos_cerebro if os.path.exists(c)), None)
            gltf_cerebro_exitoso = False

            if ruta_externa_c:
                try:
                    from hologram import cargar_ensamble_gltf_glb
                    res_g_c = cargar_ensamble_gltf_glb(ruta_externa_c)
                    if res_g_c and res_g_c.get("nodos"):
                        nodos_c = res_g_c["nodos"]
                        if len(nodos_c) >= 4:
                            for idx, meta in enumerate(info["capas"]):
                                nodo = nodos_c[idx % len(nodos_c)]
                                v_loc = np.asarray(nodo["vertices_locales"], dtype=np.float32)
                                e_loc = [tuple(int(x) for x in e) for e in nodo.get("aristas", [])]
                                f_loc = [list(f) for f in nodo.get("caras", [])]
                                n_loc = np.asarray(nodo.get("normales_locales", np.zeros_like(v_loc)), dtype=np.float32)
                                mallas.append((v_loc, e_loc, f_loc, n_loc))
                        else:
                            nodo0 = nodos_c[0]
                            v_loc = np.asarray(nodo0["vertices_locales"], dtype=np.float32)
                            e_loc = [tuple(int(x) for x in e) for e in nodo0.get("aristas", [])]
                            f_loc = [list(f) for f in nodo0.get("caras", [])]
                            n_loc = np.asarray(nodo0.get("normales_locales", np.zeros_like(v_loc)), dtype=np.float32)
                            mallas.append((v_loc, e_loc, f_loc, n_loc))
                            v_c2, e_c2, f_c2, n_c2 = generar_malla_cerebro_meninges()
                            v_c3, e_c3, f_c3, n_c3 = generar_malla_cerebro_corteza()
                            v_c4, e_c4, f_c4, n_c4 = generar_malla_cerebro_limbico()
                            mallas.extend([
                                (v_c2, e_c2, f_c2, n_c2),
                                (v_c3, e_c3, f_c3, n_c3),
                                (v_c4, e_c4, f_c4, n_c4),
                            ])
                        gltf_cerebro_exitoso = True
                        logger.info(f"ModeloAnatomico: Cerebro 3D cargado desde archivo externo GLTF/GLB '{ruta_externa_c}'")
                except Exception as e_c:
                    logger.warning(f"ModeloAnatomico: Falló carga GLB cerebro ({e_c}). Activando respaldo procedural.")

            if not gltf_cerebro_exitoso:
                v_c1, e_c1, f_c1, n_c1 = generar_malla_cerebro_craneo()
                v_c2, e_c2, f_c2, n_c2 = generar_malla_cerebro_meninges()
                v_c3, e_c3, f_c3, n_c3 = generar_malla_cerebro_corteza()
                v_c4, e_c4, f_c4, n_c4 = generar_malla_cerebro_limbico()
                mallas = [
                    (v_c1, e_c1, f_c1, n_c1),
                    (v_c2, e_c2, f_c2, n_c2),
                    (v_c3, e_c3, f_c3, n_c3),
                    (v_c4, e_c4, f_c4, n_c4),
                ]

        # Instanciar cada una de las 4 capas biológicas como Objeto3D
        for meta, (verts, edges, faces, normals) in zip(info["capas"], mallas):
            pid = meta["part_id"]
            c_loc = np.array(verts.mean(axis=0), dtype=np.float32)

            mat_local = np.eye(4, dtype=np.float32)
            mat_local[:3, 3] = c_loc

            p = Objeto3D(
                tipo_modelo=pid,
                pos_mundo=self.pos_mundo.copy(),
                rotacion=self.rotacion.copy(),
                escala=self.escala,
                color=meta["color_bgr"],
                base=self.base,
                config=self.config,
                node_name=meta["nombre_clinico"],
                part_id=pid,
                parent_name="world",
                transform_local=mat_local,
            )
            p.vertices_locales = np.asarray(verts, dtype=np.float32)
            p.vertices = p.vertices_locales
            p.normales_locales = np.asarray(normals, dtype=np.float32)
            p.normales = p.normales_locales
            p.aristas = list(edges)
            p.caras = [list(f) for f in faces]
            p.centroide_local = c_loc
            p.visible = True

            # Metadatos biológicos especializados
            p.capa_idx = int(meta["capa_idx"])
            p.capa_nombre = str(meta["capa_nombre"])
            p.nombre_clinico = str(meta["nombre_clinico"])
            p.nombre = str(meta["nombre_clinico"])
            p.tipo_capa = str(pid)
            p.funcion_fisiologica = str(meta["funcion_fisiologica"])
            p.info_clinica = {
                "nombre_clinico": meta["nombre_clinico"],
                "funcion": meta["funcion_fisiologica"],
                "capa": meta["capa_nombre"],
            }
            p.color_base = np.asarray(
                meta.get(
                    "color_rgb",
                    [meta["color_bgr"][2] / 255.0, meta["color_bgr"][1] / 255.0, meta["color_bgr"][0] / 255.0],
                ),
                dtype=np.float32,
            )
            p.vector_axial = np.asarray(meta["vector_axial"], dtype=np.float32)
            p.vector_despiece = p.vector_axial
            p.posicion = p.pos_mundo

            self.piezas[pid] = p
            self.centroides_locales[pid] = c_loc
            self.jerarquia[pid] = "world"
            self.matrices_locales[pid] = mat_local

        self._posiciones_cache_key = None
        self._cache_key = None
        self._actualizar_posiciones_piezas()
        logger.info(f"ModeloAnatomico: Preset '{self.preset_actual}' inicializado con 4 capas biológicas.")
        return True

    # ----------------------------------------------------------------
    # CINEMÁTICA FISIOLÓGICA (LATIDO ASIMÉTRICO Y FLUJO HEMODINÁMICO)
    # ----------------------------------------------------------------

    def set_bpm(self, nuevo_bpm: float) -> None:
        """Ajusta la frecuencia cardíaca en latidos por minuto (BPM)."""
        self.bpm = float(np.clip(nuevo_bpm, 30.0, 220.0))
        logger.info(f"ModeloAnatomico: Frecuencia cardíaca ajustada a {self.bpm:.0f} BPM")

    def toggle_latido(self) -> bool:
        """Pausa o reanuda la animación fisiológica del latido cardíaco."""
        self.latido_activo = not self.latido_activo
        if not self.latido_activo:
            self.escala_pulso_actual = 1.0
        logger.info(f"ModeloAnatomico: Latido cardíaco {'ACTIVO' if self.latido_activo else 'PAUSADO'}")
        return self.latido_activo

    def toggle_flujo(self) -> bool:
        """Activa o desactiva la simulación hemodinámica de flujo sanguíneo."""
        self.flujo_sanguineo_activo = not self.flujo_sanguineo_activo
        logger.info(f"ModeloAnatomico: Flujo sanguíneo {'ACTIVADO' if self.flujo_sanguineo_activo else 'DESACTIVADO'}")
        return self.flujo_sanguineo_activo

    def set_modo_diseccion(self, modo: str) -> None:
        """Alterna entre despiece 'AXIAL' y modo 'PEELING'."""
        m_upper = str(modo).upper().strip()
        if m_upper in ("AXIAL", "PEELING"):
            self.modo_diseccion = m_upper
            self._posiciones_cache_key = None
            self._actualizar_posiciones_piezas()
            logger.info(f"ModeloAnatomico: Modo de disección cambiado a '{self.modo_diseccion}'")

    def cambiar_modo_diseccion(self, modo: Optional[str] = None) -> str:
        """Alterna o asigna el modo de disección ('AXIAL' o 'PEELING')."""
        if modo is not None:
            self.set_modo_diseccion(modo)
        else:
            nuevo = "PEELING" if self.modo_diseccion == "AXIAL" else "AXIAL"
            self.set_modo_diseccion(nuevo)
        return self.modo_diseccion

    def retirar_siguiente_capa(self) -> int:
        """Modo Peeling: retira progresivamente la siguiente capa anatómica externa."""
        if self.capas_retiradas < 3:
            self.capas_retiradas += 1
            self.modo_diseccion = "PEELING"
            self._posiciones_cache_key = None
            self._actualizar_posiciones_piezas()
            logger.info(f"ModeloAnatomico: Capa {self.capas_retiradas} retirada (Peeling activo)")
        return self.capas_retiradas

    def restaurar_todas_capas(self) -> None:
        """Restaura la visibilidad de todas las capas anatómicas a su estado completo."""
        self.capas_retiradas = 0
        self.factor_explosion = 0.0
        self.capa_foco_id = None
        for p in self.piezas.values():
            p.visible = True
        self._posiciones_cache_key = None
        self._actualizar_posiciones_piezas()
        logger.info("ModeloAnatomico: Todas las capas anatómicas restauradas (100% visible)")

    def restaurar_capas(self) -> None:
        """Alias para restaurar_todas_capas()."""
        self.restaurar_todas_capas()

    def aislar_capa(self, part_id: str) -> None:
        """Aísla una capa anatómica específica mostrando su tarjeta clínica y callouts."""
        if part_id in self.piezas:
            self.capa_foco_id = part_id
            for pid, pieza in self.piezas.items():
                pieza.visible = (pid == part_id)
            self._posiciones_cache_key = None
            self._actualizar_posiciones_piezas()
            logger.info(f"ModeloAnatomico: Capa '{part_id}' aislada para inspección clínica.")

    @staticmethod
    def calcular_escala_pulso(t: float, bpm: float = 72.0, parte: str = "ventriculo") -> float:
        """
        Calcula la escala de deformación elástica fisiológica durante el ciclo cardíaco.
        Modela sístole rápida asimétrica y diástole prolongada con desfase aurículo-ventricular.
        """
        if bpm <= 0:
            return 1.0

        periodo = 60.0 / bpm
        fase = (t / periodo) % 1.0

        if parte == "auricula":
            # Sístole auricular temprana (fase 0.00 a 0.18)
            if fase < 0.18:
                t_norm = fase / 0.18
                return 1.0 - 0.08 * (math.sin(t_norm * math.pi) ** 2)
            else:
                t_relaj = (fase - 0.18) / 0.82
                return 1.0 + 0.03 * math.sin(t_relaj * math.pi)
        elif parte == "vasos":
            # Onda de pulso aórtico retardada (fase 0.25 a 0.55)
            if 0.25 <= fase <= 0.55:
                t_norm = (fase - 0.25) / 0.30
                return 1.0 + 0.07 * (math.sin(t_norm * math.pi) ** 2)
            else:
                return 1.0 - 0.01 * math.cos(fase * 2.0 * math.pi)
        elif parte == "nervioso":
            return 1.0 + 0.015 * math.sin(fase * 16.0 * math.pi)
        else:
            # Ventrículos (miocardio principal): sístole asimétrica con contracción fuerte
            if 0.15 <= fase <= 0.45:
                t_sis = (fase - 0.15) / 0.30
                return 1.0 + 0.09 * (math.sin(t_sis * math.pi) ** 3)
            else:
                t_dia = (fase - 0.45) if fase > 0.45 else (fase + 0.55)
                t_dia_norm = t_dia / 0.70
                return 1.0 - 0.04 * math.sin(t_dia_norm * math.pi)

    def obtener_buffer_gpu_flujo(self, ahora: Optional[float] = None) -> np.ndarray:
        """
        Genera el buffer GPU instanciado (160, 7) de partículas hemodinámicas:
        80 partículas azules (sangre desoxigenada) y 80 rojas (sangre oxigenada).
        Formato por partícula: [pos_x, pos_y, pos_z, color_r, color_g, color_b, radio].
        Vectorizado en NumPy con aceleración hemodinámica en sístole (cero bucles en Python).
        """
        if not self.flujo_sanguineo_activo or self.preset_actual != "corazon":
            return np.empty((0, 7), dtype=np.float32)

        t = ahora if ahora is not None else time.time()
        velocidad_base = (self.bpm / 60.0) * 0.40 if self.bpm > 0 else 0.40
        factor_velocidad = velocidad_base * (1.2 if self.escala_pulso_actual > 1.02 else 0.9)

        fases_azul = (self._fases_base_azul + t * factor_velocidad) % 1.0
        fases_rojo = (self._fases_base_rojo + t * factor_velocidad) % 1.0

        def _interp_trayectoria(pts: np.ndarray, fases: np.ndarray) -> np.ndarray:
            n_pts = len(pts)
            idx_f = fases * (n_pts - 1)
            idx0 = np.clip(np.floor(idx_f).astype(np.int32), 0, n_pts - 2)
            idx1 = idx0 + 1
            peso = (idx_f - idx0)[:, np.newaxis]
            return (1.0 - peso) * pts[idx0] + peso * pts[idx1]

        pos_azul = _interp_trayectoria(self._WAYPOINTS_FLUX_AZUL, fases_azul)
        pos_rojo = _interp_trayectoria(self._WAYPOINTS_FLUX_ROJO, fases_rojo)

        n_a = len(pos_azul)
        n_r = len(pos_rojo)

        col_azul = np.tile(np.array([0.08, 0.35, 0.95], dtype=np.float32), (n_a, 1))
        col_rojo = np.tile(np.array([0.98, 0.12, 0.18], dtype=np.float32), (n_r, 1))

        rad_azul = np.full((n_a, 1), 0.048, dtype=np.float32)
        rad_rojo = np.full((n_r, 1), 0.048, dtype=np.float32)

        buf_azul = np.hstack([pos_azul, col_azul, rad_azul])
        buf_rojo = np.hstack([pos_rojo, col_rojo, rad_rojo])

        return np.vstack([buf_azul, buf_rojo]).astype(np.float32)

    def actualizar(
        self,
        frame: Optional[np.ndarray] = None,
        ahora: Optional[float] = None,
        manos: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Actualiza la cinemática fisiológica periódica en tiempo real."""
        t_ahora = ahora if ahora is not None else time.time()
        self.ultimo_t_frame = t_ahora

        if self.latido_activo and self.bpm > 0:
            self.t_onda_actual = t_ahora * (self.bpm / 60.0) * 2.0 * math.pi
            self.escala_pulso_actual = self.calcular_escala_pulso(t_ahora, self.bpm, parte="ventriculo")
        else:
            self.escala_pulso_actual = 1.0

        self._posiciones_cache_key = None
        self._actualizar_posiciones_piezas()

    def _actualizar_posiciones_piezas(self) -> None:
        """Calcula la traslación y deformación elástica diferencial de cada capa."""
        rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
        t = float(self.factor_explosion)
        k = float(self.k_explosion * self.escala)

        if self.modo_diseccion == "PEELING":
            if self.capas_retiradas > 0:
                capas_peeled_efectivas = self.capas_retiradas
            else:
                capas_peeled_efectivas = int(t * 3.99)
        else:
            capas_peeled_efectivas = 0

        for part_id, pieza in self.piezas.items():
            desacoplada = part_id in self.piezas_desacopladas
            manual = self.offsets_manuales.get(part_id, np.zeros(3, dtype=np.float32))
            c_idx = getattr(pieza, "capa_idx", 1)
            v_axial = getattr(pieza, "vector_axial", np.zeros(3, dtype=np.float32))

            # Contracción/expansión diferencial según la capa biológica
            if self.latido_activo:
                if c_idx == 1:
                    pulse_mod = self.calcular_escala_pulso(self.ultimo_t_frame, self.bpm, parte="ventriculo")
                elif c_idx == 2:
                    pulse_mod = self.calcular_escala_pulso(self.ultimo_t_frame, self.bpm, parte="auricula")
                elif c_idx == 3:
                    pulse_mod = self.calcular_escala_pulso(self.ultimo_t_frame, self.bpm, parte="vasos")
                else:
                    pulse_mod = self.calcular_escala_pulso(self.ultimo_t_frame, self.bpm, parte="nervioso")
            else:
                pulse_mod = 1.0

            pieza.escala = float(self.escala * pulse_mod)

            # Visibilidad y Desplazamiento según Modo de Disección
            if self.modo_diseccion == "PEELING":
                if c_idx <= capas_peeled_efectivas:
                    pieza.visible = False
                else:
                    pieza.visible = True
                disp_3d = rot @ (v_axial * (t * k * 0.25))
            else:
                # Si hay una capa aislada específicamente, respetar su aislamiento
                if self.capa_foco_id is not None and not any(self.piezas[pid].visible for pid in self.piezas if pid != self.capa_foco_id):
                    pieza.visible = (part_id == self.capa_foco_id)
                else:
                    pieza.visible = True
                disp_3d = rot @ (v_axial * (t * k))

            if desacoplada:
                pieza.pos_mundo[0] = float(self.pos_mundo[0] + manual[0])
                pieza.pos_mundo[1] = float(self.pos_mundo[1] + manual[1])
                pieza.pos_mundo[2] = float(self.pos_mundo[2] + manual[2])
            else:
                pieza.pos_mundo[0] = float(self.pos_mundo[0] + disp_3d[0] + manual[0])
                pieza.pos_mundo[1] = float(self.pos_mundo[1] + disp_3d[1] + manual[1])
                pieza.pos_mundo[2] = float(self.pos_mundo[2] + disp_3d[2] + manual[2])

            pieza.rotacion[:] = self.rotacion[:]
            pieza.posicion = pieza.pos_mundo

    # ----------------------------------------------------------------
    # INTERACCIÓN TÁCTIL E INSPECCIÓN CLÍNICA (LANDMARK 8)
    # ----------------------------------------------------------------

    def liberar(self) -> None:
        """Libera de forma limpia recursos del modelo anatómico."""
        self.piezas = AnatomicalPiezasDict()
        self.centroides_locales.clear()

    def procesar_interaccion(
        self,
        cursor_pos: Optional[Tuple[float, float]],
        pinza_cerrada: bool = False,
        flanco_down: bool = False,
        flanco_up: bool = False,
        ahora: Optional[float] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Procesa el contacto del dedo índice o mouse sobre los controles clínicos del HUD."""
        self.ultimo_cursor_pos = cursor_pos
        resultado: Dict[str, Any] = {"accion": None}
        if cursor_pos is None:
            return resultado

        cx, cy = float(cursor_pos[0]), float(cursor_pos[1])
        t_ahora = ahora if ahora is not None else time.time()

        if (flanco_down or pinza_cerrada) and (t_ahora - self.ultimo_toque_tiempo > 0.25):
            for bid, rect in self.rects_botones_hud.items():
                if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
                    self.ultimo_toque_tiempo = t_ahora
                    if bid == "TOGGLE_MODO_DISECCION":
                        nuevo_m = "PEELING" if self.modo_diseccion == "AXIAL" else "AXIAL"
                        self.set_modo_diseccion(nuevo_m)
                        resultado["accion"] = "MODO_DISECCION"
                        resultado["modo"] = nuevo_m
                    elif bid == "RETIRAR_CAPA":
                        self.retirar_siguiente_capa()
                        resultado["accion"] = "RETIRAR_CAPA"
                    elif bid == "RESTAURAR_CAPAS":
                        self.restaurar_todas_capas()
                        resultado["accion"] = "RESTAURAR_CAPAS"
                    elif bid == "TOGGLE_FLUJO":
                        act = self.toggle_flujo()
                        resultado["accion"] = "TOGGLE_FLUJO"
                        resultado["flujo_activo"] = act
                    elif bid == "BPM_60":
                        self.set_bpm(60.0)
                        resultado["accion"] = "SET_BPM"
                        resultado["bpm"] = 60.0
                    elif bid == "BPM_72":
                        self.set_bpm(72.0)
                        resultado["accion"] = "SET_BPM"
                        resultado["bpm"] = 72.0
                    elif bid == "BPM_130":
                        self.set_bpm(130.0)
                        resultado["accion"] = "SET_BPM"
                        resultado["bpm"] = 130.0
                    elif bid == "TOGGLE_LATIDO":
                        act = self.toggle_latido()
                        resultado["accion"] = "TOGGLE_LATIDO"
                        resultado["latido_activo"] = act
                    elif bid == "TOGGLE_ORGANO":
                        nuevo_org = "cerebro" if self.preset_actual == "corazon" else "corazon"
                        self.cargar_preset(nuevo_org)
                        resultado["accion"] = "CAMBIO_ORGANO"
                        resultado["organo"] = nuevo_org
                    return resultado

        # Selección / Foco por proximidad al dedo índice
        sel = self.seleccionar_pieza((cx, cy), pad=25)
        if sel is not None:
            self.capa_foco_id = sel
        return resultado

    def procesar_clic_hud(self, x: float, y: float) -> Dict[str, Any]:
        """Procesa un clic puntual (x, y) sobre la botonera táctil del HUD."""
        res = self.procesar_interaccion((x, y), pinza_cerrada=True, flanco_down=True, ahora=self.ultimo_toque_tiempo + 1.0)
        res["click_capturado"] = res.get("accion") is not None
        return res

    def seleccionar_pieza(
        self,
        punto: Tuple[float, float],
        pad: int = 10,
    ) -> Optional[str]:
        """Detecta colisión para seleccionar una capa o sub-parte anatómica."""
        px, py = float(punto[0]), float(punto[1])
        if self.preset_actual == "corazon":
            rot_m = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
            escala_total = float(self.base * self.escala * self.escala_pulso_actual)
            for callout in self.CALLOUTS_CORAZON:
                part = self.piezas.get(callout["part_id"])
                if part is not None and getattr(part, "visible", True):
                    offset_desacople = (part.pos_mundo - self.pos_mundo).astype(np.float32) if self.esta_desacoplada(callout["part_id"]) else np.zeros(3, dtype=np.float32)
                    p3d = rot_m @ (callout["anchor"] * escala_total)
                    sx = self.pos_mundo[0] + p3d[0] + offset_desacople[0]
                    sy = self.pos_mundo[1] + p3d[1] + offset_desacople[1]
                    if (px - sx) ** 2 + (py - sy) ** 2 <= (pad + 18) ** 2:
                        return callout["part_id"]
        return super().seleccionar_pieza(punto, pad=pad)

    # ----------------------------------------------------------------
    # RENDERIZADO CPU FALLBACK Y DIBUJADO DE HUD CLÍNICO
    # ----------------------------------------------------------------

    def renderizar(
        self,
        frame: np.ndarray,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
        cursor_pos: Optional[Tuple[float, float]] = None,
        ui_visible: bool = True,
    ) -> np.ndarray:
        """
        Fallback CPU basado en OpenCV para entornos sin GPU o pruebas headless.
        Renderiza las capas anatómicas, callouts y partículas de flujo sanguíneo.
        """
        if cursor_pos is not None:
            self.ultimo_cursor_pos = cursor_pos

        frame = super().renderizar(frame, config=config, center=center)

        # Renderizar flujo sanguíneo en CPU si está activo
        if self.flujo_sanguineo_activo and self.preset_actual == "corazon":
            cx = float(center[0]) if center is not None else float(self.pos_mundo[0])
            cy = float(center[1]) if center is not None else float(self.pos_mundo[1])

            buf_flujo = self.obtener_buffer_gpu_flujo(time.time())
            if len(buf_flujo) > 0:
                rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
                escala_tot = float(self.escala * self.base)

                pos_3d = buf_flujo[:, :3]
                cols = buf_flujo[:, 3:6]
                pos_rot = (rot @ pos_3d.T).T

                u_arr = cx + pos_rot[:, 0] * escala_tot
                v_arr = cy - pos_rot[:, 1] * escala_tot
                h_f, w_f = frame.shape[:2]

                for i in range(len(buf_flujo)):
                    ui = int(round(u_arr[i]))
                    vi = int(round(v_arr[i]))
                    if 0 <= ui < w_f and 0 <= vi < h_f:
                        c_rgb = cols[i]
                        c_bgr = (int(round(c_rgb[2] * 255)), int(round(c_rgb[1] * 255)), int(round(c_rgb[0] * 255)))
                        cv2.circle(frame, (ui, vi), 3, c_bgr, -1, cv2.LINE_AA)

        if self.mostrar_hud and ui_visible:
            frame = self.dibujar_hud_anatomico(frame, cursor_pos=cursor_pos if cursor_pos is not None else self.ultimo_cursor_pos)

        return frame

    CALLOUTS_CORAZON = [
        {"id": "cava",       "label": "Superior vena cava",   "anchor": np.array([0.35, 0.85, -0.05], dtype=np.float32), "lado": "left",  "part_id": "sistema_circulatorio"},
        {"id": "atrio_der",  "label": "Right atrium",        "anchor": np.array([0.42, 0.35, -0.05], dtype=np.float32), "lado": "left",  "part_id": "sistema_valvular"},
        {"id": "vent_der",   "label": "Right ventricle",     "anchor": np.array([0.22, -0.35, 0.15], dtype=np.float32), "lado": "left",  "part_id": "capa_muscular"},
        {"id": "coronarias", "label": "Coronary arteries",    "anchor": np.array([0.05, -0.20, 0.22], dtype=np.float32), "lado": "left",  "part_id": "sistema_nervioso"},

        {"id": "aorta",      "label": "Aortic arch",          "anchor": np.array([-0.10, 1.05, -0.15], dtype=np.float32), "lado": "right", "part_id": "sistema_circulatorio"},
        {"id": "pulmonar",   "label": "Pulmonary trunk",      "anchor": np.array([-0.18, 0.55, 0.10], dtype=np.float32), "lado": "right", "part_id": "sistema_circulatorio"},
        {"id": "atrio_izq",  "label": "Left atrium",         "anchor": np.array([-0.38, 0.40, -0.10], dtype=np.float32), "lado": "right", "part_id": "sistema_valvular"},
        {"id": "vent_izq",   "label": "Left ventricle",      "anchor": np.array([-0.25, -0.55, 0.10], dtype=np.float32), "lado": "right", "part_id": "capa_muscular"},
    ]

    def _dibujar_callouts_anatomicos(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]],
    ) -> None:
        """Dibuja líneas indicadoras finas hacia los costados izquierdo y derecho."""
        h_f, w_f = frame.shape[:2]
        cx_c = float(cursor_pos[0]) if cursor_pos else -1.0
        cy_c = float(cursor_pos[1]) if cursor_pos else -1.0

        rot_m = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
        escala_total = float(self.base * self.escala * self.escala_pulso_actual)

        left_callouts = [c for c in self.CALLOUTS_CORAZON if c["lado"] == "left"]
        right_callouts = [c for c in self.CALLOUTS_CORAZON if c["lado"] == "right"]

        for grupo, lado in [(left_callouts, "left"), (right_callouts, "right")]:
            n_items = len(grupo)
            y_start = int(h_f * 0.16)
            y_step = int((h_f * 0.65) / max(n_items, 1))

            for i, callout in enumerate(grupo):
                part = self.piezas.get(callout["part_id"])
                if part is not None and not getattr(part, "visible", True):
                    continue

                c_anchor = callout["anchor"]
                offset_desacople = np.zeros(3, dtype=np.float32)
                if part is not None and self.esta_desacoplada(callout["part_id"]):
                    offset_desacople = (part.pos_mundo - self.pos_mundo).astype(np.float32)

                p3d = rot_m @ (c_anchor * escala_total)
                proj_x = int(round(self.pos_mundo[0] + p3d[0] + offset_desacople[0]))
                proj_y = int(round(self.pos_mundo[1] + p3d[1] + offset_desacople[1]))

                y_box = y_start + i * y_step
                label_txt = callout["label"]
                (tw, th), _ = cv2.getTextSize(label_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)

                if lado == "left":
                    x_box = 24
                    elbow_x = min(proj_x - 30, 185)
                    line_end_x = x_box + tw + 10
                    esta_hover = (x_box <= cx_c <= line_end_x and y_box - th - 4 <= cy_c <= y_box + 6) or (abs(proj_x - cx_c) < 22 and abs(proj_y - cy_c) < 22)
                else:
                    x_box = w_f - tw - 24
                    elbow_x = max(proj_x + 30, w_f - 185)
                    line_end_x = x_box - 10
                    esta_hover = (line_end_x <= cx_c <= w_f - 14 and y_box - th - 4 <= cy_c <= y_box + 6) or (abs(proj_x - cx_c) < 22 and abs(proj_y - cy_c) < 22)

                if esta_hover:
                    self.capa_foco_id = callout["part_id"]

                col_line = (50, 255, 120) if esta_hover else (140, 190, 220)
                col_txt = (0, 255, 255) if esta_hover else (220, 240, 255)

                cv2.circle(frame, (proj_x, proj_y), 3, col_line, -1, cv2.LINE_AA)
                cv2.circle(frame, (proj_x, proj_y), 6, col_line, 1, cv2.LINE_AA)
                cv2.line(frame, (proj_x, proj_y), (elbow_x, y_box), col_line, 1, cv2.LINE_AA)
                cv2.line(frame, (elbow_x, y_box), (line_end_x, y_box), col_line, 1, cv2.LINE_AA)
                cv2.putText(frame, label_txt, (x_box, y_box + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.36, col_txt, 1, cv2.LINE_AA)

    def dibujar_hud_anatomico(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
        pieza_enfocada: Optional[Any] = None,
        pulso_escala: Optional[float] = None,
    ) -> np.ndarray:
        """Renderiza la insignia clínica, la tarjeta flotante y los controles del HUD."""
        if not self.mostrar_hud:
            return frame

        if pieza_enfocada is not None:
            if hasattr(pieza_enfocada, "part_id"):
                self.capa_foco_id = pieza_enfocada.part_id
            elif isinstance(pieza_enfocada, str):
                self.capa_foco_id = pieza_enfocada

        if pulso_escala is not None:
            self.escala_pulso_actual = float(pulso_escala)

        # 1. Cabecera Clínica Superior
        cv2.rectangle(frame, (180, 16), (460, 48), (18, 22, 28), -1)
        cv2.rectangle(frame, (180, 16), (460, 48), (46, 38, 199), 1, cv2.LINE_AA)
        org_title = PRESETS_ANATOMIA.get(self.preset_actual, {}).get("nombre_organo", "Anatomia 3D")
        cv2.putText(frame, org_title, (192, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (220, 240, 255), 1, cv2.LINE_AA)

        # 1.5 Callouts Anatómicos 3D -> 2D
        if self.preset_actual == "corazon":
            self._dibujar_callouts_anatomicos(frame, cursor_pos)

        # 2. Tarjeta Holográfica Flotante si hay una capa seleccionada
        if self.capa_foco_id and self.capa_foco_id in self.piezas:
            pieza_foco = self.piezas[self.capa_foco_id]
            if getattr(pieza_foco, "visible", True):
                self._dibujar_tarjeta_clinica_capa(frame, pieza_foco)

        # 3. Barra de Botones Táctiles Inferiores
        self._dibujar_barra_controles_clinicos(frame, cursor_pos)

        return frame

    def _dibujar_tarjeta_clinica_capa(
        self,
        frame: np.ndarray,
        pieza: Objeto3D,
    ) -> None:
        """Dibuja una tarjeta flotante de telemetría y función clínica anclada a la capa."""
        h_f, w_f = frame.shape[:2]
        c_2d = (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))
        pts_p, _ = pieza.proyectar(center=c_2d)
        if pts_p:
            cx = int(np.mean([p[0] for p in pts_p]))
            cy = int(np.mean([p[1] for p in pts_p]))
        else:
            cx, cy = int(pieza.pos_mundo[0]), int(pieza.pos_mundo[1])

        cx = max(20, min(cx, w_f - 20))
        cy = max(20, min(cy, h_f - 20))

        card_w, card_h = 320, 85
        tx = cx + 45 if cx < w_f - 350 else cx - card_w - 45
        ty = max(55, min(cy - card_h // 2, h_f - card_h - 60))

        col_hud = getattr(pieza, "color", (50, 255, 120))
        elbow_x = cx + 25 if tx > cx else cx - 25
        elbow_y = ty + card_h // 2
        cv2.line(frame, (cx, cy), (elbow_x, elbow_y), col_hud, 1, cv2.LINE_AA)
        target_x_conn = tx if tx > cx else tx + card_w
        cv2.line(frame, (elbow_x, elbow_y), (target_x_conn, elbow_y), col_hud, 1, cv2.LINE_AA)

        x1_c, y1_c = tx, ty
        x2_c, y2_c = tx + card_w, ty + card_h
        sub_roi = frame[y1_c:y2_c, x1_c:x2_c]
        if sub_roi.shape[0] == card_h and sub_roi.shape[1] == card_w:
            dark_bg = np.zeros_like(sub_roi)
            cv2.addWeighted(sub_roi, 0.35, dark_bg, 0.65, 0, sub_roi)
            cv2.rectangle(frame, (x1_c, y1_c), (x2_c, y2_c), col_hud, 1, cv2.LINE_AA)

            cv2.putText(frame, f"{pieza.nombre_clinico}", (x1_c + 8, y1_c + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col_hud, 1, cv2.LINE_AA)
            cv2.putText(frame, f"Capa Biologica: {pieza.capa_idx}/4 ({pieza.capa_nombre})", (x1_c + 8, y1_c + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (200, 230, 255), 1, cv2.LINE_AA)

            fase_txt = "SISTOLE" if self.escala_pulso_actual > 1.02 else "DIASTOLE"
            bpm_txt = f"{self.bpm:.0f} BPM ({fase_txt})" if self.latido_activo else "ESTATICO"
            cv2.putText(frame, f"Ritmo: {bpm_txt} | Despiece: {int(self.factor_explosion * 100)}%", (x1_c + 8, y1_c + 52), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (0, 230, 255), 1, cv2.LINE_AA)

            fn_txt = pieza.funcion_fisiologica[:48] + ("..." if len(pieza.funcion_fisiologica) > 48 else "")
            cv2.putText(frame, fn_txt, (x1_c + 8, y1_c + 72), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (170, 190, 210), 1, cv2.LINE_AA)

    def _dibujar_barra_controles_clinicos(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]],
    ) -> None:
        """Dibuja la botonera táctil inferior para disección y control fisiológico."""
        h_f, w_f = frame.shape[:2]
        btn_y1 = h_f - 48
        btn_y2 = h_f - 16

        botones = [
            ("TOGGLE_MODO_DISECCION", f"Modo: {self.modo_diseccion}"),
            ("RETIRAR_CAPA", "[+] Retirar Capa"),
            ("RESTAURAR_CAPAS", "[R] Restaurar Todo"),
            ("TOGGLE_FLUJO", f"Flujo: {'ON' if self.flujo_sanguineo_activo else 'OFF'}"),
            ("BPM_60", "60 BPM"),
            ("BPM_72", "72 BPM"),
            ("BPM_130", "130 BPM"),
            ("TOGGLE_LATIDO", "Pausar" if self.latido_activo else "Reanudar"),
            ("TOGGLE_ORGANO", "Cerebro" if self.preset_actual == "corazon" else "Corazon"),
        ]

        total_w = min(w_f - 180, 1060)
        btn_w = total_w // len(botones)
        curr_x = (w_f - total_w) // 2

        cx = float(cursor_pos[0]) if cursor_pos else -1.0
        cy = float(cursor_pos[1]) if cursor_pos else -1.0

        self.rects_botones_hud.clear()

        for bid, label in botones:
            bx1 = curr_x
            bx2 = curr_x + btn_w - 6
            self.rects_botones_hud[bid] = (bx1, btn_y1, bx2, btn_y2)

            esta_hover = (bx1 <= cx <= bx2 and btn_y1 <= cy <= btn_y2)
            bg_col = (40, 50, 65) if esta_hover else (18, 22, 28)
            border_col = (0, 230, 255) if esta_hover else (60, 75, 95)
            txt_col = (0, 230, 255) if esta_hover else (180, 200, 220)

            if bid == "TOGGLE_FLUJO" and self.flujo_sanguineo_activo:
                border_col = (255, 60, 60)
                txt_col = (255, 120, 120)
            elif bid == "TOGGLE_LATIDO" and self.latido_activo:
                border_col = (50, 255, 120)
            elif bid == "TOGGLE_MODO_DISECCION" and self.modo_diseccion == "PEELING":
                border_col = (255, 150, 50)

            cv2.rectangle(frame, (bx1, btn_y1), (bx2, btn_y2), bg_col, -1)
            cv2.rectangle(frame, (bx1, btn_y1), (bx2, btn_y2), border_col, 1, cv2.LINE_AA)
            cv2.putText(frame, label, (bx1 + 5, btn_y2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.30, txt_col, 1, cv2.LINE_AA)

            curr_x += btn_w
