"""
hologram.py
-------------------------------------------------------------------
Módulo de renderizado de hologramas 3D, modo telaraña interactiva y panel táctil.
Implementa:
- Algoritmo del Pintor (Painter's Algorithm) acelerado mediante renderizado
  acotado por Bounding Box 2D (ROI) para evitar copias de fotograma completo.
- Proyección perspectiva vectorizada con NumPy para alto rendimiento (>= 60 FPS).
- Geometría 3D de poliedros (cubo, pirámide, dona, esfera) y mallas externas (.stl/.obj).
- Decimación automática para modelos 3D excediendo max_caras_render para mantener 30+ FPS.
- Detección de fusión bimanual en modo "Telaraña" (doble gesto en L).
- Casting estricto a int en todas las llamadas de renderizado OpenCV.
-------------------------------------------------------------------
"""

import io
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from gestures import is_L_gesture, l_points
from filters import OneEuroFilter, OneEuroFilter2D
from renderer import BaseRenderer, crear_renderer

# Configuración de logging para el módulo
logger = logging.getLogger("HologramSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)

# Color representativo de la telaraña (amarillo neón holográfico)
WEB_COLOR = (255, 255, 120)


# Directorio de modelos y mallas 3D industriales externas
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Blindaje e inicialización de trimesh y simplificación cuadrática por decimanación
_safe_simplify_quadric = None
_ESCENA_DESPIECE_ACTIVA: Optional[Any] = None

def obtener_escena_despiece_activa() -> Optional[Any]:
    """Retorna la instancia SceneModel activa para sincronización de HUD y despiece."""
    return _ESCENA_DESPIECE_ACTIVA
try:
    import trimesh
    HAS_TRIMESH = True
    if not getattr(trimesh.Trimesh, "_stark_patched", False):
        _orig_simplify = getattr(trimesh.Trimesh, "simplify_quadric_decimation", None)
        def _safe_simplify_quadric(self, face_count: int) -> "trimesh.Trimesh":
            try:
                if _orig_simplify is not None:
                    return _orig_simplify(self, int(face_count))
            except Exception as e:
                logger.debug(f"Aviso decimation nativa trimesh: {e}")
            try:
                import fast_simplification
                target_red = max(0.0, min(1.0, 1.0 - (float(face_count) / max(len(self.faces), 1))))
                v_out, f_out = fast_simplification.simplify(self.vertices, self.faces, target_reduction=target_red)
                return trimesh.Trimesh(vertices=v_out, faces=f_out, process=False)
            except Exception as e:
                logger.debug(f"Aviso decimation fallback: {e}")
                return trimesh.Trimesh(vertices=self.vertices, faces=self.faces[:int(face_count)], process=False)
        trimesh.Trimesh.simplify_quadric_decimation = _safe_simplify_quadric
        trimesh.Trimesh._stark_patched = True
except ImportError:
    trimesh = None
    HAS_TRIMESH = False


# ====================================================================
# GENERADORES PROCEDURALES Y PRIMITIVAS 3D NATIVAS (NUMPY)
# ====================================================================

def generar_geometria_cubo(lado: float = 0.85) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría canónica de un cubo centrada en el origen con proporciones elegantes."""
    s = float(lado)
    verts = np.array([
        [-s, -s, -s], [ s, -s, -s], [ s,  s, -s], [-s,  s, -s],
        [-s, -s,  s], [ s, -s,  s], [ s,  s,  s], [-s,  s,  s],
    ], dtype=np.float32)
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    faces = [
        [0, 3, 2, 1],  # Cara trasera (-z)
        [4, 5, 6, 7],  # Cara delantera (+z)
        [0, 1, 5, 4],  # Cara inferior (-y)
        [2, 3, 7, 6],  # Cara superior (+y)
        [0, 4, 7, 3],  # Cara izquierda (-x)
        [1, 2, 6, 5],  # Cara derecha (+x)
    ]
    return verts, edges, faces


def generar_geometria_piramide(base_w: float = 0.90, altura: float = 1.35) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría canónica de una pirámide con proporción áurea y normales exteriores nítidas."""
    s = float(base_w)
    h = float(altura)
    verts = np.array([
        [-s, -s, -s * 0.65], [ s, -s, -s * 0.65], [ s,  s, -s * 0.65], [-s,  s, -s * 0.65],
        [0.0, 0.0,  h * 0.65],
    ], dtype=np.float32)
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (0, 4), (1, 4), (2, 4), (3, 4),
    ]
    faces = [
        [0, 3, 2, 1],  # Base inferior (-z)
        [0, 1, 4],     # Cara sur (-y)
        [1, 2, 4],     # Cara este (+x)
        [2, 3, 4],     # Cara norte (+y)
        [3, 0, 4],     # Cara oeste (-x)
    ]
    return verts, edges, faces


def generar_geometria_caja(
    dx: float = 0.5, dy: float = 0.5, dz: float = 0.5
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría canónica de una caja sólida 3D centrada en el origen."""
    hx, hy, hz = float(dx) * 0.5, float(dy) * 0.5, float(dz) * 0.5
    verts = np.array([
        [-hx, -hy, -hz], [ hx, -hy, -hz], [ hx,  hy, -hz], [-hx,  hy, -hz],
        [-hx, -hy,  hz], [ hx, -hy,  hz], [ hx,  hy,  hz], [-hx,  hy,  hz],
    ], dtype=np.float32)
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    faces = [
        [0, 3, 2, 1],  # -z
        [4, 5, 6, 7],  # +z
        [0, 1, 5, 4],  # -y
        [2, 3, 7, 6],  # +y
        [0, 4, 7, 3],  # -x
        [1, 2, 6, 5],  # +x
    ]
    return verts, edges, faces


def generar_geometria_cilindro_x(
    radio: float = 0.3, longitud: float = 1.0, segmentos: int = 16
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría sólida de un cilindro horizontal alineado con el eje X."""
    hx = float(longitud) * 0.5
    r = float(radio)
    n = max(8, int(segmentos))
    verts_list: List[List[float]] = []

    # Vértices de la base izquierda (-hx)
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        verts_list.append([-hx, r * math.cos(ang), r * math.sin(ang)])
    # Vértices de la base derecha (+hx)
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        verts_list.append([hx, r * math.cos(ang), r * math.sin(ang)])
    # Centro tapa izquierda
    verts_list.append([-hx, 0.0, 0.0])
    # Centro tapa derecha
    verts_list.append([hx, 0.0, 0.0])

    verts = np.array(verts_list, dtype=np.float32)
    edges: List[Tuple[int, int]] = []
    for i in range(n):
        nxt = (i + 1) % n
        edges.append((i, nxt))
        edges.append((n + i, n + nxt))
        edges.append((i, n + i))

    faces: List[List[int]] = []
    idx_c_izq = 2 * n
    idx_c_der = 2 * n + 1
    for i in range(n):
        nxt = (i + 1) % n
        # Cara lateral cuadrada/rectangular
        faces.append([i, nxt, n + nxt, n + i])
        # Triángulo tapa izquierda
        faces.append([idx_c_izq, nxt, i])
        # Triángulo tapa derecha
        faces.append([idx_c_der, n + i, n + nxt])

    return verts, edges, faces


def generar_geometria_cilindro_z(
    radio: float = 0.3, longitud: float = 1.0, segmentos: int = 32
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría sólida de un cilindro vertical alineado con el eje Z (Fase 4)."""
    hz = float(longitud) * 0.5
    r = float(radio)
    n = max(8, int(segmentos))
    verts_list: List[List[float]] = []
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        verts_list.append([r * math.cos(ang), r * math.sin(ang), -hz])
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        verts_list.append([r * math.cos(ang), r * math.sin(ang), hz])
    verts_list.append([0.0, 0.0, -hz])
    verts_list.append([0.0, 0.0, hz])

    verts = np.array(verts_list, dtype=np.float32)
    edges: List[Tuple[int, int]] = []
    for i in range(n):
        nxt = (i + 1) % n
        edges.append((i, nxt))
        edges.append((n + i, n + nxt))
        edges.append((i, n + i))

    faces: List[List[int]] = []
    idx_bot = 2 * n
    idx_top = 2 * n + 1
    for i in range(n):
        nxt = (i + 1) % n
        faces.append([i, nxt, n + nxt, n + i])
        faces.append([idx_bot, nxt, i])
        faces.append([idx_top, n + i, n + nxt])

    return verts, edges, faces


def generar_geometria_dona(major_r: float = 0.90, minor_r: float = 0.30, n_u: int = 24, n_v: int = 12) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría paramétrica de alta fidelidad de un toroide cuántico en NumPy."""
    verts_list = []
    for i in range(n_u):
        u = (2.0 * np.pi * i) / n_u
        cos_u, sin_u = np.cos(u), np.sin(u)
        for j in range(n_v):
            v = (2.0 * np.pi * j) / n_v
            cos_v, sin_v = np.cos(v), np.sin(v)
            x = (major_r + minor_r * cos_v) * cos_u
            y = (major_r + minor_r * cos_v) * sin_u
            z = minor_r * sin_v
            verts_list.append([x, y, z])

    verts = np.array(verts_list, dtype=np.float32)
    edges_set = set()
    faces_list = []

    for i in range(n_u):
        next_i = (i + 1) % n_u
        for j in range(n_v):
            next_j = (j + 1) % n_v
            v0 = i * n_v + j
            v1 = next_i * n_v + j
            v2 = next_i * n_v + next_j
            v3 = i * n_v + next_j

            edges_set.add(tuple(sorted((v0, v1))))
            edges_set.add(tuple(sorted((v1, v2))))
            edges_set.add(tuple(sorted((v2, v3))))
            edges_set.add(tuple(sorted((v3, v0))))
            faces_list.append([v0, v1, v2, v3])

    edges = [tuple(int(x) for x in e) for e in edges_set]
    return verts, edges, faces_list


def generar_geometria_esfera(n_lat: int = 16, n_lon: int = 24, radio: float = 0.95) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera una esfera UV paramétrica de alta fidelidad sin pinching polar en NumPy."""
    verts_list = []
    verts_list.append([0.0, 0.0, -radio])
    for i in range(1, n_lat):
        theta = -np.pi / 2.0 + (np.pi * i) / n_lat
        z = radio * np.sin(theta)
        r_xy = radio * np.cos(theta)
        for j in range(n_lon):
            phi = (2.0 * np.pi * j) / n_lon
            x = r_xy * np.cos(phi)
            y = r_xy * np.sin(phi)
            verts_list.append([x, y, z])
    verts_list.append([0.0, 0.0, radio])
    verts = np.array(verts_list, dtype=np.float32)

    edges_set = set()
    faces_list = []
    for j in range(n_lon):
        p_sur = 0
        v1 = 1 + j
        v2 = 1 + ((j + 1) % n_lon)
        edges_set.add(tuple(sorted((p_sur, v1))))
        edges_set.add(tuple(sorted((v1, v2))))
        faces_list.append([p_sur, v2, v1])

    for i in range(1, n_lat - 1):
        idx_base = 1 + (i - 1) * n_lon
        idx_sig = 1 + i * n_lon
        for j in range(n_lon):
            next_j = (j + 1) % n_lon
            v0 = idx_base + j
            v1 = idx_base + next_j
            v2 = idx_sig + next_j
            v3 = idx_sig + j
            edges_set.add(tuple(sorted((v0, v1))))
            edges_set.add(tuple(sorted((v1, v2))))
            edges_set.add(tuple(sorted((v2, v3))))
            edges_set.add(tuple(sorted((v3, v0))))
            faces_list.append([v0, v1, v2, v3])

    idx_norte = len(verts) - 1
    idx_ultimo_anillo = 1 + (n_lat - 2) * n_lon
    for j in range(n_lon):
        v1 = idx_ultimo_anillo + j
        v2 = idx_ultimo_anillo + ((j + 1) % n_lon)
        edges_set.add(tuple(sorted((v1, idx_norte))))
        edges_set.add(tuple(sorted((v1, v2))))
        faces_list.append([v1, v2, idx_norte])

    edges = [tuple(int(x) for x in e) for e in edges_set]
    return verts, edges, faces_list


def generar_geometria_octaedro(s: float = 1.1) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Genera geometría canónica de un octaedro regular centrada en el origen."""
    scale = float(s)
    verts = np.array([
        [ scale, 0.0, 0.0], [-scale, 0.0, 0.0],
        [0.0,  scale, 0.0], [0.0, -scale, 0.0],
        [0.0, 0.0,  scale], [0.0, 0.0, -scale],
    ], dtype=np.float32)
    edges = [
        (0, 2), (2, 1), (1, 3), (3, 0),
        (0, 4), (1, 4), (2, 4), (3, 4),
        (0, 5), (1, 5), (2, 5), (3, 5),
    ]
    faces = [
        [4, 0, 2], [4, 2, 1], [4, 1, 3], [4, 3, 0],
        [5, 2, 0], [5, 1, 2], [5, 3, 1], [5, 0, 3],
    ]
    return verts, edges, faces


_v_cubo, _e_cubo, _f_cubo = generar_geometria_cubo()
_v_piramide, _e_piramide, _f_piramide = generar_geometria_piramide()
_v_dona, _e_dona, _f_dona = generar_geometria_dona()
_v_esfera, _e_esfera, _f_esfera = generar_geometria_esfera()

# Vértices 3D canónicos centrados en el origen
SHAPES_VERTICES: Dict[str, np.ndarray] = {
    "cubo": _v_cubo,
    "piramide": _v_piramide,
    "dona": _v_dona,
    "toroide": _v_dona,
    "esfera": _v_esfera,
}

# Aristas conectivas canónicas por defecto (cubo unitario como referencia estándar)
CUBE_EDGES: List[Tuple[int, int]] = _e_cubo
EDGES: List[Tuple[int, int]] = CUBE_EDGES

# Definición de caras poligonales para sombreado volumétrico
FACES: Dict[str, List[List[int]]] = {
    "cubo": _f_cubo,
    "piramide": _f_piramide,
    "dona": _f_dona,
    "toroide": _f_dona,
    "esfera": _f_esfera,
}

# Diccionario de aristas por figura geométrica
SHAPE_EDGES: Dict[str, List[Tuple[int, int]]] = {
    "cubo": _e_cubo,
    "piramide": _e_piramide,
    "dona": _e_dona,
    "toroide": _e_dona,
    "esfera": _e_esfera,
}


def _extraer_aristas_caracteristicas(mesh: Any) -> List[Tuple[int, int]]:
    """Extrae aristas características (> 25°) o aristas únicas de una malla Trimesh."""
    edges: List[Tuple[int, int]] = []
    if hasattr(mesh, "face_adjacency_angles") and len(mesh.face_adjacency_angles) > 0:
        try:
            sharp_mask = mesh.face_adjacency_angles > np.radians(25.0)
            if hasattr(mesh, "face_adjacency_edges") and len(mesh.face_adjacency_edges) == len(sharp_mask):
                feature_edges = mesh.face_adjacency_edges[sharp_mask]
                if hasattr(mesh, "edges_boundary") and len(mesh.edges_boundary) > 0:
                    all_edges = np.vstack([feature_edges, mesh.edges_boundary])
                else:
                    all_edges = feature_edges
                edges = [tuple(sorted((int(e[0]), int(e[1])))) for e in all_edges]
                edges = list(dict.fromkeys(edges))
        except Exception as e:
            logger.debug(f"Filtro de aristas por ángulo omitido: {e}")

    if not edges and hasattr(mesh, "edges_unique"):
        edges = [tuple(int(x) for x in e) for e in mesh.edges_unique]
    return edges


def cargar_malla_archivo(
    ruta_archivo: str,
    max_caras: int = 3000,
) -> Optional[Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]]:
    """
    Carga un archivo 3D industrial (.stl, .obj, .glb o .gltf) desde una ruta absoluta o desde 'assets/'.
    Aplica:
    1. Decimación cuadrática dinámica (simplify_quadric_decimation) si excede max_caras (<= 3000 caras).
    2. Normalización geométrica automática: traslación al centroide (-mesh.centroid) y reescalado isotrópico.
    3. Filtrado de aristas características (> 25°) para renderizado alámbrico nítido de alta tecnología.
    """
    ruta_resolv = ruta_archivo
    if not os.path.exists(ruta_resolv):
        # Intentar resolución en el directorio assets/
        cand = os.path.join(ASSETS_DIR, ruta_archivo)
        if os.path.exists(cand):
            ruta_resolv = cand
        else:
            # Probar añadiendo extensiones estándar
            encontrado = False
            for ext in (".obj", ".stl", ".glb", ".gltf", ".OBJ", ".STL", ".GLB", ".GLTF"):
                cand_ext = os.path.join(ASSETS_DIR, ruta_archivo + ext)
                if os.path.exists(cand_ext):
                    ruta_resolv = cand_ext
                    encontrado = True
                    break
            if not encontrado:
                logger.debug(f"No se encontró archivo 3D en assets para: {ruta_archivo}")
                return None

    if not os.path.exists(ruta_resolv):
        return None

    if not HAS_TRIMESH or trimesh is None:
        logger.warning("'trimesh' no está instalado. Modelos externos requieren 'pip install trimesh'.")
        return None

    try:
        cargado = trimesh.load(ruta_resolv)
        if isinstance(cargado, trimesh.Scene):
            geoms = [g for g in cargado.geometry.values() if isinstance(g, trimesh.Trimesh)]
            mesh = trimesh.util.concatenate(geoms) if geoms else None
        elif isinstance(cargado, trimesh.Trimesh):
            mesh = cargado
        else:
            mesh = None

        if mesh is None or len(mesh.vertices) == 0:
            return None

        # 1. Decimación cuadrática dinámica (<= max_caras)
        if len(mesh.faces) > max_caras:
            try:
                mesh = mesh.simplify_quadric_decimation(max_caras)
            except Exception as e:
                logger.debug(f"Decimación cuadrática omitida: {e}")

        # 2. Normalización geométrica automática
        # Traslación al centroide (-mesh.centroid)
        mesh.apply_translation(-mesh.centroid)

        # Reescalado isotrópico al volumen estándar de pantalla
        max_extent = float(max(mesh.extents)) if len(mesh.extents) > 0 else 1.0
        if max_extent > 1e-4:
            mesh.apply_scale(1.8 / max_extent)

        verts = np.array(mesh.vertices, dtype=np.float32)
        faces = [list(int(x) for x in f) for f in mesh.faces]

        # 3. Filtrado de aristas características (> 25°)
        edges = _extraer_aristas_caracteristicas(mesh)

        return verts, edges, faces
    except Exception as e:
        logger.warning(f"Aviso al cargar modelo 3D {ruta_resolv}: {e}")
        return None


def cargar_ensamble_gltf_glb(
    ruta_o_datos: Union[str, bytes, bytearray, io.BytesIO, Any],
    max_caras: int = 3000,
    reorientar_z_up_a_y_up: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Subfase 2.2: Parser de ensambles jerárquicos GLTF/GLB (.glb / .gltf) mediante Trimesh.
    Preserva la jerarquía de nodos padre-hijo:
      - ID o nombre único de nodo ('node_name' / 'part_id').
      - Matriz de transformación local 4x4 (traslación, rotación, escala respecto al padre).
      - Vértices, normales, caras y aristas individuales por sub-malla (sin texturas pesadas ni skinning).
    Aplica normalización automática:
      - Consistencia de ejes Y-up / Z-forward (estándar GLTF 2.0, con opción de reorientar Z-up).
      - Cálculo del centroide global del ensamble y centrado exacto en el origen local (0, 0, 0).
      - Reescalado isotrópico uniforme para encajar en el volumen unitario de visualización [-0.9, 0.9].
    """
    if not HAS_TRIMESH or trimesh is None:
        logger.warning("'trimesh' no disponible para parsear ensamble GLTF/GLB.")
        return None

    try:
        cargado: Any = None
        if isinstance(ruta_o_datos, (bytes, bytearray)):
            if len(ruta_o_datos) < 12:
                logger.warning("Datos binarios GLB demasiado cortos o corruptos.")
                return None
            bio = io.BytesIO(bytes(ruta_o_datos))
            cargado = trimesh.load(bio, file_type="glb")
        elif isinstance(ruta_o_datos, io.BytesIO):
            cargado = trimesh.load(ruta_o_datos, file_type="glb")
        elif hasattr(trimesh, "Scene") and isinstance(ruta_o_datos, (trimesh.Scene, trimesh.Trimesh)):
            cargado = ruta_o_datos
        elif isinstance(ruta_o_datos, str):
            ruta_resolv = ruta_o_datos
            if not os.path.exists(ruta_resolv):
                cand = os.path.join(ASSETS_DIR, ruta_o_datos)
                if os.path.exists(cand):
                    ruta_resolv = cand
                else:
                    encontrado = False
                    for ext in (".glb", ".gltf", ".GLB", ".GLTF", ".obj", ".stl"):
                        cand_ext = os.path.join(ASSETS_DIR, ruta_o_datos + ext)
                        if os.path.exists(cand_ext):
                            ruta_resolv = cand_ext
                            encontrado = True
                            break
                    if not encontrado:
                        logger.warning(f"Archivo GLTF/GLB no encontrado: {ruta_o_datos}")
                        return None
            if not os.path.isfile(ruta_resolv) or os.path.getsize(ruta_resolv) == 0:
                logger.warning(f"Archivo GLTF/GLB vacío o inválido: {ruta_resolv}")
                return None
            cargado = trimesh.load(ruta_resolv)
        else:
            return None

        if cargado is None:
            return None

        nodos_crudos: List[Dict[str, Any]] = []
        base_frame = "world"

        if isinstance(cargado, trimesh.Scene):
            base_frame = str(getattr(cargado.graph, "base_frame", "world"))
            parent_map: Dict[str, str] = {}
            local_mat_map: Dict[str, np.ndarray] = {}

            orden_edgelist: List[str] = []
            try:
                for u_parent, v_child, edge_data in cargado.graph.to_edgelist():
                    v_str = str(v_child)
                    parent_map[v_str] = str(u_parent)
                    if v_str not in orden_edgelist:
                        orden_edgelist.append(v_str)
                    mat = edge_data.get("matrix", None) if isinstance(edge_data, dict) else None
                    if mat is not None:
                        local_mat_map[v_str] = np.asarray(mat, dtype=np.float32).reshape((4, 4))
            except Exception as e:
                logger.debug(f"Aviso al leer edgelist de SceneGraph: {e}")

            set_nodes_geom = set(str(n) for n in getattr(cargado.graph, "nodes_geometry", []))
            nodes_geom = [n for n in orden_edgelist if n in set_nodes_geom]
            for n_extra in getattr(cargado.graph, "nodes_geometry", []):
                if str(n_extra) not in nodes_geom:
                    nodes_geom.append(str(n_extra))
            usados_nombres: set = set()

            for idx, node_name in enumerate(nodes_geom):
                n_str = str(node_name)
                try:
                    world_mat, geom_key = cargado.graph.get(node_name)
                    geom = cargado.geometry.get(geom_key)
                except Exception:
                    continue

                if not isinstance(geom, trimesh.Trimesh) or len(geom.vertices) == 0 or len(geom.faces) == 0:
                    continue

                w_mat = np.asarray(world_mat, dtype=np.float32).reshape((4, 4))
                l_mat = local_mat_map.get(n_str, w_mat.copy()).astype(np.float32)
                p_name = parent_map.get(n_str, base_frame)

                uid = n_str if n_str not in usados_nombres else f"{n_str}_{idx}"
                usados_nombres.add(uid)

                nodos_crudos.append({
                    "node_name": uid,
                    "parent_name": p_name,
                    "geom_name": str(geom_key),
                    "mesh": geom.copy(),
                    "transform_local": l_mat,
                    "transform_world": w_mat,
                })

            # Fallback si la escena tenía geometrías no vinculadas en nodes_geometry
            if not nodos_crudos and cargado.geometry:
                for idx, (g_key, geom) in enumerate(cargado.geometry.items()):
                    if isinstance(geom, trimesh.Trimesh) and len(geom.vertices) > 0 and len(geom.faces) > 0:
                        uid = str(g_key)
                        eye4 = np.eye(4, dtype=np.float32)
                        eye4[:3, 3] = np.asarray(geom.centroid, dtype=np.float32)
                        nodos_crudos.append({
                            "node_name": uid,
                            "parent_name": base_frame,
                            "geom_name": uid,
                            "mesh": geom.copy(),
                            "transform_local": eye4,
                            "transform_world": np.eye(4, dtype=np.float32),
                        })

        elif isinstance(cargado, trimesh.Trimesh):
            if len(cargado.vertices) == 0 or len(cargado.faces) == 0:
                return None
            sub_meshes = cargado.split(only_watertight=False)
            if not sub_meshes:
                sub_meshes = [cargado]
            for idx, sm in enumerate(sub_meshes[:24]):
                if len(sm.vertices) == 0 or len(sm.faces) == 0:
                    continue
                uid = f"nodo_{idx}"
                l_mat = np.eye(4, dtype=np.float32)
                l_mat[:3, 3] = np.asarray(sm.centroid, dtype=np.float32)
                nodos_crudos.append({
                    "node_name": uid,
                    "parent_name": base_frame,
                    "geom_name": uid,
                    "mesh": sm.copy(),
                    "transform_local": l_mat,
                    "transform_world": np.eye(4, dtype=np.float32),
                })

        if not nodos_crudos:
            logger.warning("El archivo GLTF/GLB no contiene nodos geométricos válidos.")
            return None

        # Matriz opcional de reorientación de ejes a Y-up / Z-forward
        # (GLTF 2.0 define por especificación +Y arriba, +Z hacia el frente y +X a la derecha)
        R_axis = np.eye(4, dtype=np.float32)
        if reorientar_z_up_a_y_up:
            # Rotación -90° en X: convierte Z-up a Y-up / Z-forward
            R_axis = np.array([
                [1.0,  0.0, 0.0, 0.0],
                [0.0,  0.0, 1.0, 0.0],
                [0.0, -1.0, 0.0, 0.0],
                [0.0,  0.0, 0.0, 1.0],
            ], dtype=np.float32)

        # Decimación proporcional por nodo y proyección de vértices al espacio global del ensamble
        max_caras_por_nodo = max(150, int(max_caras) // max(len(nodos_crudos), 1))
        todos_vertices_mundo: List[np.ndarray] = []

        for nodo in nodos_crudos:
            mesh_n = nodo["mesh"]
            if len(mesh_n.faces) > max_caras_por_nodo:
                try:
                    mesh_n = mesh_n.simplify_quadric_decimation(max_caras_por_nodo)
                except Exception as e:
                    logger.debug(f"Decimación en nodo {nodo['node_name']} omitida: {e}")

            w_mat = R_axis @ nodo["transform_world"]
            nodo["transform_world"] = w_mat
            if nodo["parent_name"] == base_frame:
                nodo["transform_local"] = R_axis @ nodo["transform_local"]

            v_local_raw = np.asarray(mesh_n.vertices, dtype=np.float32)
            ones = np.ones((len(v_local_raw), 1), dtype=np.float32)
            v_hom = np.hstack([v_local_raw, ones])
            v_world = (v_hom @ w_mat.T)[:, :3].astype(np.float32)

            nodo["mesh"] = mesh_n
            nodo["v_world"] = v_world
            todos_vertices_mundo.append(v_world)

        # 1. Cálculo del centroide global del ensamble y centrado en (0, 0, 0)
        verts_ensamble = np.vstack(todos_vertices_mundo)
        if not np.all(np.isfinite(verts_ensamble)):
            logger.warning("Vértices con valores NaN/Inf detectados en GLTF/GLB.")
            return None

        centroide_global_orig = verts_ensamble.mean(axis=0).astype(np.float32)
        verts_centrados = verts_ensamble - centroide_global_orig

        # 2. Reescalado isotrópico al volumen unitario de visualización (extensión máx = 1.8)
        min_b = verts_centrados.min(axis=0)
        max_b = verts_centrados.max(axis=0)
        extents_orig = (max_b - min_b).astype(np.float32)
        max_extent = float(np.max(extents_orig))
        escala_iso = float(1.8 / max_extent) if max_extent > 1e-5 else 1.0

        nodos_procesados: List[Dict[str, Any]] = []
        for nodo in nodos_crudos:
            mesh_n = nodo["mesh"]
            v_norm = ((nodo["v_world"] - centroide_global_orig) * escala_iso).astype(np.float32)
            c_pieza = v_norm.mean(axis=0).astype(np.float32)

            faces_n = [list(int(x) for x in f) for f in mesh_n.faces]
            edges_n = _extraer_aristas_caracteristicas(mesh_n)

            # Calcular normales de vértices/caras en espacio normalizado
            try:
                mesh_norm = trimesh.Trimesh(vertices=v_norm, faces=mesh_n.faces, process=False)
                v_normals = np.asarray(mesh_norm.vertex_normals, dtype=np.float32)
            except Exception:
                v_normals = np.zeros_like(v_norm, dtype=np.float32)

            nodos_procesados.append({
                "node_name": nodo["node_name"],
                "part_id": nodo["node_name"],
                "parent_name": nodo["parent_name"],
                "geom_name": nodo["geom_name"],
                "transform_local": nodo["transform_local"].astype(np.float32),
                "transform_world": nodo["transform_world"].astype(np.float32),
                "vertices_locales": v_norm,
                "normales_locales": v_normals,
                "aristas": edges_n,
                "caras": faces_n,
                "centroide_local": c_pieza,
            })

        verts_finales = np.vstack([n["vertices_locales"] for n in nodos_procesados])
        centroide_final = verts_finales.mean(axis=0).astype(np.float32)
        extents_final = (verts_finales.max(axis=0) - verts_finales.min(axis=0)).astype(np.float32)

        return {
            "nodos": nodos_procesados,
            "base_frame": base_frame,
            "centroide_original": centroide_global_orig,
            "centroide_global": centroide_final,
            "escala_normalizacion": escala_iso,
            "extents_normalizados": extents_final,
            "orientacion_ejes": "Y-up / Z-forward",
        }
    except Exception as e:
        logger.warning(f"Error al parsear ensamble GLTF/GLB ({e}). Se activará fallback procedural.")
        return None


def registrar_figura_3d(
    nombre: str,
    vertices: np.ndarray,
    aristas: List[Tuple[int, int]],
    caras: Optional[List[List[int]]] = None,
) -> None:
    """Registra dinámicamente una figura 3D para proyección y renderizado con Algoritmo del Pintor."""
    clave = str(nombre).lower().strip()
    SHAPES_VERTICES[clave] = np.asarray(vertices, dtype=np.float32)
    SHAPE_EDGES[clave] = aristas
    if caras is not None:
        FACES[clave] = caras


def obtener_geometria_figura(
    nombre: str,
    max_caras: int = 3000,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
    """Obtiene vértices, aristas y caras para cualquier figura registrada, predeterminada o malla externa."""
    clave = str(nombre).lower().strip()
    if clave in ("toroide", "donut"):
        clave = "dona"
    elif clave in ("cube",):
        clave = "cubo"
    elif clave in ("pyramid",):
        clave = "piramide"
    elif clave in ("sphere",):
        clave = "esfera"

    if clave in SHAPES_VERTICES:
        verts = SHAPES_VERTICES[clave]
        edges = SHAPE_EDGES.get(clave, EDGES)
        faces = FACES.get(clave, [])
        return verts, edges, faces

    # Intentar cargar como archivo 3D externo (.obj / .stl)
    res = cargar_malla_archivo(nombre, max_caras=max_caras)
    if res is not None:
        v, e, f = res
        registrar_figura_3d(clave, v, e, f)
        return v, e, f

    return SHAPES_VERTICES["cubo"], SHAPE_EDGES["cubo"], FACES["cubo"]


def rotation_matrix(yaw: float, pitch: float, roll: float = 0.0) -> np.ndarray:
    """Genera la matriz de rotación compuesta 3D (Rz * Ry * Rx)."""
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cr, sr = np.cos(roll), np.sin(roll)

    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float32)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]], dtype=np.float32)
    rz = np.array([[cr, -sr, 0.0], [sr, cr, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)

    return rz @ ry @ rx


def project(
    points_3d: np.ndarray,
    center: Tuple[float, float],
    base: float,
    scale: float,
) -> Tuple[List[Tuple[int, int]], np.ndarray]:
    """
    Proyecta vértices 3D al plano 2D de la imagen con cámara de perspectiva de forma vectorizada.
    Devuelve lista de coordenadas en píxeles enteros y array NumPy de profundidades Z en cámara.
    """
    d = 4.0
    f = base * scale
    pts = np.asarray(points_3d, dtype=np.float32)

    zc = np.maximum(pts[:, 2] + d, 0.1)
    px = np.round(f * pts[:, 0] / zc + center[0]).astype(np.int32)
    py = np.round(f * (-pts[:, 1]) / zc + center[1]).astype(np.int32)

    out_pts = list(zip(px.tolist(), py.tolist()))
    return out_pts, zc


def draw_object(
    frame: np.ndarray,
    shape_name: str,
    yaw: float,
    pitch: float,
    scale: float,
    center: Tuple[float, float],
    color: Tuple[int, int, int],
    base: float = 200.0,
    roll: float = 0.0,
    config: Optional[Union[Dict[str, Any], Any]] = None,
) -> None:
    """
    Renderiza un objeto 3D holográfico aplicando el Algoritmo del Pintor (Painter's Algorithm).
    Optimizado mediante recorte BBox 2D (ROI) para evitar copias del fotograma completo.
    """
    if hasattr(config, "data"):
        cfg = config.data
    elif isinstance(config, dict):
        cfg = config
    else:
        cfg = {}
    use_painter = bool(cfg.get("enable_painter_algorithm", True))
    use_faces = bool(cfg.get("enable_3d_faces", True))
    face_opacity = float(cfg.get("faces_opacity", 0.92))

    # 1. Transformación angular de vértices
    clave = shape_name.lower()
    if clave not in SHAPES_VERTICES:
        clave = "cubo"

    rot = rotation_matrix(yaw, pitch, roll)
    rotated = SHAPES_VERTICES[clave] @ rot.T
    pts, z_depths = project(rotated, center, base, scale)

    if not pts:
        return

    # 2. Calcular Bounding Box 2D para renderizado acotado (Cero lag por copias innecesarias)
    h_f, w_f = frame.shape[:2]
    all_x = [p[0] for p in pts]
    all_y = [p[1] for p in pts]

    pad = 25
    x1 = max(0, min(all_x) - pad)
    y1 = max(0, min(all_y) - pad)
    x2 = min(w_f, max(all_x) + pad)
    y2 = min(h_f, max(all_y) + pad)

    if x2 <= x1 or y2 <= y1:
        return

    # Submatriz ROI para evitar copiar toda la resolución (e.g. 1280x720)
    roi = frame[y1:y2, x1:x2]
    pts_roi = [(int(p[0] - x1), int(p[1] - y1)) for p in pts]

    # 3. Caras 3D semitransparentes (Algoritmo del Pintor en polígonos con Back-Face Culling)
    caras_shape = FACES.get(clave, [])
    if use_faces and caras_shape:
        overlay = roi.copy()
        caras_info = []
        for face_indices in caras_shape:
            if all(idx < len(z_depths) for idx in face_indices):
                # Back-Face Culling 2D por producto cruz en espacio de pantalla
                p0 = pts_roi[face_indices[0]]
                p1 = pts_roi[face_indices[1]]
                p2 = pts_roi[face_indices[2]]
                cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
                if cross <= 0:
                    continue  # Descartar cara posterior oculta

                z_face = sum(float(z_depths[idx]) for idx in face_indices) / len(face_indices)
                poly_pts = np.array([pts_roi[idx] for idx in face_indices], dtype=np.int32)

                # Sombreado 3D sólido por normal de cara con vector de luz [0.4, 0.7, 0.6]
                v0_3d = rotated[face_indices[0]]
                v1_3d = rotated[face_indices[1]]
                v2_3d = rotated[face_indices[2]]
                n_3d = np.cross(v1_3d - v0_3d, v2_3d - v0_3d)
                norm_val = float(np.linalg.norm(n_3d))
                if norm_val > 1e-6:
                    n_unit = n_3d / norm_val
                    L_dir = np.array([0.40, 0.70, 0.60], dtype=np.float32)
                    L_dir /= np.linalg.norm(L_dir)
                    ndotl = abs(float(np.dot(n_unit, L_dir)))
                    shading = float(np.clip(0.40 + 0.60 * ndotl, 0.25, 1.0))
                else:
                    shading = 0.70
                f_col = (
                    int(np.clip(color[0] * shading, 0, 255)),
                    int(np.clip(color[1] * shading, 0, 255)),
                    int(np.clip(color[2] * shading, 0, 255)),
                )
                caras_info.append((z_face, poly_pts, f_col))

        if use_painter and len(caras_info) > 1:
            caras_info.sort(key=lambda item: item[0], reverse=True)

        for _, poly_pts, f_col in caras_info:
            cv2.fillPoly(overlay, [poly_pts], f_col, cv2.LINE_AA)

        cv2.addWeighted(overlay, face_opacity, roi, 1.0 - face_opacity, 0, roi)

    # 4. Aristas 3D (Renderizado directo en ROI sin asignaciones de memoria redundantes)
    aristas_shape = SHAPE_EDGES.get(clave, EDGES)
    aristas_info = []
    for a, b in aristas_shape:
        if a < len(z_depths) and b < len(z_depths):
            z_arista = (float(z_depths[a]) + float(z_depths[b])) * 0.5
            aristas_info.append((z_arista, a, b))

    if use_painter and len(aristas_info) > 1:
        aristas_info.sort(key=lambda item: item[0], reverse=True)

    if aristas_info:
        z_vals = [item[0] for item in aristas_info]
        min_z, max_z = min(z_vals), max(z_vals)
        span_z = max(max_z - min_z, 1e-4)

        for z_arista, a, b in aristas_info:
            norm_depth = (max_z - z_arista) / span_z
            # Arista tubular: trazo base con mayor grosor y brillo metálico
            base_thickness = 3 if norm_depth > 0.35 else 2

            factor_brillo = 0.70 + 0.30 * norm_depth
            edge_color = (
                int(color[0] * factor_brillo),
                int(color[1] * factor_brillo),
                int(color[2] * factor_brillo),
            )
            # Componente especular central (tubo metálico reflectante)
            specular_edge_color = (
                min(255, int(edge_color[0] * 1.35 + 75)),
                min(255, int(edge_color[1] * 1.35 + 75)),
                min(255, int(edge_color[2] * 1.35 + 75)),
            )
            pt_a = pts_roi[a]
            pt_b = pts_roi[b]
            # 1. Trazo base tubular
            cv2.line(roi, pt_a, pt_b, edge_color, int(base_thickness), cv2.LINE_AA)
            # 2. Resaltado especular tubular interno
            cv2.line(roi, pt_a, pt_b, specular_edge_color, 1, cv2.LINE_AA)

    # 5. Nodos en vértices iluminados con destello especular
    z_min_glob = float(np.min(z_depths))
    z_max_glob = float(np.max(z_depths))
    span_glob = max(z_max_glob - z_min_glob, 1e-4)

    for i, p in enumerate(pts_roi):
        norm_v = (z_max_glob - float(z_depths[i])) / span_glob
        radius = int(5 if norm_v > 0.55 else 3)
        glow_col = (
            min(255, int(color[0] * 1.2 + 50)),
            min(255, int(color[1] * 1.2 + 50)),
            min(255, int(color[2] * 1.2 + 50)),
        )
        # Halo exterior difuso
        cv2.circle(roi, p, int(radius + 2), glow_col, 1, cv2.LINE_AA)
        # Núcleo iluminado
        cv2.circle(roi, p, int(radius), color, -1, cv2.LINE_AA)
        # Brillo especular metálico Blinn-Phong en el centro
        spec_r = max(1, radius // 2)
        cv2.circle(roi, (p[0] - max(1, radius // 3), p[1] - max(1, radius // 3)), int(spec_r), (255, 255, 255), -1, cv2.LINE_AA)


def draw_web(
    frame: np.ndarray,
    pts6: np.ndarray,
    color: Tuple[int, int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Renderiza la telaraña cibernética con anillos concéntricos, radios y nodos.
    Devuelve el contorno convexo y el centroide de la estructura con casting int estricto.
    """
    pts = np.array(pts6, dtype=np.float32)
    hull = cv2.convexHull(pts).reshape(-1, 2)
    centroid = hull.mean(axis=0)

    # Bounding Box de la telaraña para renderizado acotado
    h_f, w_f = frame.shape[:2]
    all_x = pts[:, 0]
    all_y = pts[:, 1]
    pad = 20
    x1 = max(0, int(np.min(all_x)) - pad)
    y1 = max(0, int(np.min(all_y)) - pad)
    x2 = min(w_f, int(np.max(all_x)) + pad)
    y2 = min(h_f, int(np.max(all_y)) + pad)

    if x2 > x1 and y2 > y1:
        roi = frame[y1:y2, x1:x2]
        overlay = roi.copy()
        offset = np.array([x1, y1], dtype=np.float32)
        c_roi = centroid - offset
        hull_roi = hull - offset
        pts_roi = pts - offset

        # Anillos concéntricos proporcionales
        for s in (1.0, 0.75, 0.5, 0.25):
            poly = (c_roi + s * (hull_roi - c_roi)).astype(np.int32)
            cv2.polylines(overlay, [poly], True, color, 2 if s == 1.0 else 1, cv2.LINE_AA)

        # Radios desde el centroide hacia los vértices exteriores
        c_pt = (int(round(c_roi[0])), int(round(c_roi[1])))
        for v in hull_roi:
            v_pt = (int(round(v[0])), int(round(v[1])))
            cv2.line(overlay, c_pt, v_pt, color, 1, cv2.LINE_AA)

        # Hilos transversales diagonales entre segmentos contiguos
        n = len(hull_roi)
        for i in range(n):
            m1 = (hull_roi[i] + hull_roi[(i + 1) % n]) / 2.0
            m2 = (hull_roi[(i + 1) % n] + hull_roi[(i + 2) % n]) / 2.0
            m1_pt = (int(round(m1[0])), int(round(m1[1])))
            m2_pt = (int(round(m2[0])), int(round(m2[1])))
            cv2.line(overlay, m1_pt, m2_pt, color, 1, cv2.LINE_AA)

        # Nodos iluminados en los puntos anatómicos de las manos
        for p in pts_roi:
            p_int = (int(round(p[0])), int(round(p[1])))
            cv2.circle(overlay, p_int, 6, color, -1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.8, roi, 0.2, 0, roi)

    return hull, centroid


class Objeto3D:
    """
    Clase 'Objeto3D' polimórfica para entidades tridimensionales desacopladas espacialmente.
    Posee coordenadas de mundo propias sobre la pantalla y ciclo de vida independiente,
    con soporte integral para modelos predeterminados (cubo, pirámide, dona, esfera),
    mallas externas (.obj/.stl) y nodos jerárquicos GLTF/GLB (.glb/.gltf).
    """

    def __init__(
        self,
        tipo_modelo: str = "cubo",
        pos_mundo: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        escala: float = 1.0,
        color: Tuple[int, int, int] = (255, 235, 30),
        base: float = 200.0,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        node_name: Optional[str] = None,
        part_id: Optional[str] = None,
        parent_name: Optional[str] = None,
        transform_local: Optional[np.ndarray] = None,
    ) -> None:
        self.config: Any = config if config is not None else {}
        self.tipo_modelo: str = str(tipo_modelo).lower()

        # Metadatos jerárquicos de nodo (Subfase 2.2)
        self.node_name: str = str(node_name) if node_name is not None else self.tipo_modelo
        self.part_id: str = str(part_id) if part_id is not None else self.node_name
        self.parent_name: Optional[str] = str(parent_name) if parent_name is not None else None
        if transform_local is not None:
            self.transform_local: np.ndarray = np.asarray(transform_local, dtype=np.float32).reshape((4, 4))
        else:
            self.transform_local = np.eye(4, dtype=np.float32)
        self.transform_explosion: np.ndarray = self.transform_local.copy()
        self.centroide_local: np.ndarray = np.zeros(3, dtype=np.float32)

        # Referencias a buffers individuales en VRAM (ModernGL VAO/VBO)
        self.gpu_buffers: Optional[Dict[str, Any]] = None
        self.vao: Optional[Any] = None
        self.vbo: Optional[Any] = None

        # pos_mundo: np.ndarray([x, y, z], dtype=np.float32) -> Inicializado al centro de la pantalla
        if pos_mundo is not None:
            arr = np.asarray(pos_mundo, dtype=np.float32)
            if arr.shape == (2,):
                self.pos_mundo: np.ndarray = np.array([arr[0], arr[1], 0.0], dtype=np.float32)
            else:
                self.pos_mundo = arr.astype(np.float32)
        else:
            self.pos_mundo = np.array([640.0, 360.0, 0.0], dtype=np.float32)

        # rotacion: np.ndarray([yaw, pitch, roll], dtype=np.float32)
        if rotacion is not None:
            self.rotacion: np.ndarray = np.asarray(rotacion, dtype=np.float32)
        else:
            # Orientación isométrica volumétrica 3D por defecto para visualización con profundidad
            self.rotacion = np.array([0.45, 0.35, 0.10], dtype=np.float32)

        # escala: float
        self.escala: float = float(escala)

        # color BGR y base focal de proyección
        self.color: Tuple[int, int, int] = color
        self.base: float = float(base)
        self.visible: bool = True
        self.xray: bool = False

        # vertices_locales: np.ndarray con los vértices base de la primitiva seleccionada
        # caras: lista de tuplas/aristas para el renderizado
        self.vertices_locales: np.ndarray = np.empty((0, 3), dtype=np.float32)
        self.normales_locales: np.ndarray = np.empty((0, 3), dtype=np.float32)
        self.aristas: List[Tuple[int, int]] = []
        self.caras: List[List[int]] = []
        self.set_tipo(self.tipo_modelo)

        # Caché de proyección y estado
        self.ultimos_puntos_2d: List[Tuple[int, int]] = []
        self.ultimas_profundidades: Optional[np.ndarray] = None

        # Cinemática y física angular de rotación tipo Mapamundi
        self.vel_yaw: float = 0.0
        self.vel_pitch: float = 0.0
        self.friccion_rotacion: float = 0.94

    def set_tipo(self, tipo_modelo: str) -> None:
        """Carga y actualiza la geometría base del modelo 3D polimórfico (primitivas o mallas externas)."""
        self.tipo_modelo = str(tipo_modelo)
        max_caras = int(self.config.get("max_caras_render", 3000)) if hasattr(self.config, "get") else 3000
        verts, edges, faces = obtener_geometria_figura(self.tipo_modelo, max_caras=max_caras)
        self.vertices_locales = np.asarray(verts, dtype=np.float32).copy()
        self.aristas = list(edges)
        self.caras = [list(f) for f in faces]

    @property
    def vertices(self) -> np.ndarray:
        return self.vertices_locales

    @vertices.setter
    def vertices(self, valor: np.ndarray) -> None:
        self.vertices_locales = np.asarray(valor, dtype=np.float32)

    @property
    def normales(self) -> np.ndarray:
        return self.normales_locales

    @normales.setter
    def normales(self, valor: np.ndarray) -> None:
        self.normales_locales = np.asarray(valor, dtype=np.float32)

    def actualizar(
        self,
        nueva_pos: Optional[Union[np.ndarray, Tuple[float, float], Tuple[float, float, float]]] = None,
        delta_rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        nueva_rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        escala: Optional[float] = None,
        landmarks: Optional[Any] = None,
        pts: Optional[np.ndarray] = None,
        ahora: Optional[float] = None,
        gesto: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Actualiza el estado cinemático del contenedor geométrico (Scene Node puro).
        Solo acepta transformaciones espaciales explícitas pasadas por argumento.
        Inercia absoluta (Fase 1.1): Si no se envían transformaciones explícitas o
        landmarks es None, retiene inmutable su posición, rotación y escala,
        conservando el momento angular inercial (efecto Mapamundi).
        """
        if nueva_pos is not None:
            n_pos = np.asarray(nueva_pos, dtype=np.float32)
            if n_pos.shape == (2,):
                self.pos_mundo[0] = n_pos[0]
                self.pos_mundo[1] = n_pos[1]
            elif n_pos.shape == (3,):
                self.pos_mundo[:] = n_pos[:]

        if nueva_rotacion is not None:
            n_rot = np.asarray(nueva_rotacion, dtype=np.float32)
            self.rotacion[:len(n_rot)] = n_rot[:]
            self.vel_yaw = 0.0
            self.vel_pitch = 0.0

        if delta_rotacion is not None:
            d_rot = np.asarray(delta_rotacion, dtype=np.float32)
            self.rotacion[:len(d_rot)] += d_rot[:]

        # Inercia angular "Mapamundi": Si hay velocidad angular residual y no se forzó nueva_rotacion
        if nueva_rotacion is None and delta_rotacion is None:
            if abs(self.vel_yaw) > 0.0005 or abs(self.vel_pitch) > 0.0005:
                self.rotacion[0] += self.vel_yaw
                self.rotacion[1] += self.vel_pitch
                self.vel_yaw *= self.friccion_rotacion
                self.vel_pitch *= self.friccion_rotacion
                if abs(self.vel_yaw) < 0.0005:
                    self.vel_yaw = 0.0
                if abs(self.vel_pitch) < 0.0005:
                    self.vel_pitch = 0.0

        if escala is not None and escala > 0:
            self.escala = float(escala)

    def proyectar(
        self,
        center: Optional[Tuple[float, float]] = None,
        base: Optional[float] = None,
        scale: Optional[float] = None,
        rot_matrix: Optional[np.ndarray] = None,
    ) -> Tuple[List[Tuple[int, int]], np.ndarray]:
        """
        Proyecta vectorialmente los vértices locales transformados hacia el plano 2D.
        Devuelve lista de puntos enteros y profundidades zc.
        """
        c = center if center is not None else (float(self.pos_mundo[0]), float(self.pos_mundo[1]))
        b = float(base if base is not None else self.base)
        s = float(scale if scale is not None else self.escala)

        if rot_matrix is not None:
            rot = rot_matrix
        else:
            yaw, pitch, roll = float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2])
            rot = rotation_matrix(yaw, pitch, roll)

        rotated = self.vertices_locales @ rot.T
        pts, z_depths = project(rotated, c, b, s)
        self.ultimos_puntos_2d = pts
        self.ultimas_profundidades = z_depths
        return pts, z_depths

    def proyectar_vertices(self) -> List[Tuple[int, int]]:
        """Retorna las coordenadas proyectadas 2D de los vértices en píxeles enteros."""
        pts, _ = self.proyectar()
        return pts

    def calcular_aabb_2d(
        self,
        center: Optional[Tuple[float, float]] = None,
        pad: int = 15,
    ) -> Tuple[int, int, int, int]:
        """
        Calcula dinámicamente el Bounding Box 2D (AABB) a partir de los vértices proyectados.
        Retorna (x_min, y_min, x_max, y_max) en coordenadas de pantalla.
        """
        pts, _ = self.proyectar(center=center)
        if not pts:
            c = center if center is not None else (float(self.pos_mundo[0]), float(self.pos_mundo[1]))
            return (int(c[0] - 50), int(c[1] - 50), int(c[0] + 50), int(c[1] + 50))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x_min = int(min(xs) - pad)
        y_min = int(min(ys) - pad)
        x_max = int(max(xs) + pad)
        y_max = int(max(ys) + pad)
        return (x_min, y_min, x_max, y_max)

    def contiene_punto(
        self,
        punto: Tuple[float, float],
        center: Optional[Tuple[float, float]] = None,
        pad: int = 15,
    ) -> bool:
        """Verifica si un punto 2D (px, py) se encuentra dentro de la BBox proyectada."""
        x_min, y_min, x_max, y_max = self.calcular_aabb_2d(center=center, pad=pad)
        px, py = float(punto[0]), float(punto[1])
        return x_min <= px <= x_max and y_min <= py <= y_max

    def renderizar(
        self,
        frame: np.ndarray,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Renderiza el objeto 3D sobre el fotograma en su posición de mundo 'pos_mundo'
        (o en 'center' si se especifica explícitamente) usando el Algoritmo del Pintor y ROI acotado (< 2.5 ms).
        """
        cfg = config or self.config
        c = center if center is not None else (float(self.pos_mundo[0]), float(self.pos_mundo[1]))

        clave = str(self.tipo_modelo).lower().strip()
        if clave not in SHAPES_VERTICES and len(self.vertices_locales) > 0:
            registrar_figura_3d(clave, self.vertices_locales, self.aristas, self.caras)

        draw_object(
            frame=frame,
            shape_name=self.tipo_modelo,
            yaw=float(self.rotacion[0]),
            pitch=float(self.rotacion[1]),
            scale=float(self.escala),
            center=c,
            color=self.color,
            base=self.base,
            roll=float(self.rotacion[2]),
            config=cfg,
        )
        return frame


class SceneModel(Objeto3D):
    """
    Modelo de Escena Jerárquico y Compuesto Multi-Pieza (Fase 1.4 & Subfase 2.2).
    Gestiona modelos estructurados en sub-piezas/sub-mallas (piezas: Dict[str, Objeto3D]),
    incluyendo ensambles industriales complejos en formato GLTF/GLB (.glb/.gltf).
    Preserva la jerarquía de nodos padre-hijo, matrices de transformación local 4x4,
    normalización isotrópica en el origen (0, 0, 0) y referencias individuales a VAO/VBO en GPU.
    Implementa la cinemática de Vista Explosionada (Exploded View):
      P_pieza(t) = P_centro + t * k * R * (C_pieza - C_centro) + Delta_manual
    """

    def __init__(
        self,
        tipo_modelo: str = "cubo_modular",
        pos_mundo: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        escala: float = 1.0,
        color: Tuple[int, int, int] = (255, 235, 30),
        base: float = 200.0,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        k_explosion: float = 180.0,
        piezas: Optional[Dict[str, Objeto3D]] = None,
    ) -> None:
        self.factor_explosion: float = 0.0
        self.k_explosion: float = float(k_explosion)
        self.piezas: Dict[str, Objeto3D] = {}
        self.centroides_locales: Dict[str, np.ndarray] = {}
        self.offsets_manuales: Dict[str, np.ndarray] = {}
        self.jerarquia: Dict[str, Optional[str]] = {}
        self.matrices_locales: Dict[str, np.ndarray] = {}
        self.centroide_global: np.ndarray = np.zeros(3, dtype=np.float32)
        self.centroide_original: np.ndarray = np.zeros(3, dtype=np.float32)
        self.escala_normalizacion: float = 1.0
        self.orientacion_ejes: str = "Y-up / Z-forward"
        self.fallback_activado: bool = False
        self.pieza_seleccionada_id: Optional[str] = None
        self.piezas_desacopladas: set[str] = set()
        self.modo_manipulacion: str = "ENSAMBLE"  # "ENSAMBLE" (global) vs "PIEZA" (local aislado)
        self.piezas_ocultas: set[str] = set()
        self.pieza_aislada_id: Optional[str] = None
        self.pieza_resaltada_id: Optional[str] = None
        self.piezas_xray: set[str] = set()
        self.rects_panel_piezas: Dict[str, Tuple[int, int, int, int]] = {}
        self.rect_panel_despiece: Optional[Tuple[int, int, int, int]] = None
        self.rect_slider_explosion: Optional[Tuple[int, int, int, int]] = None
        self.track_slider_coords: Optional[Tuple[int, int, int]] = None
        self.panel_despiece_visible: bool = True
        self._cached_aabbs: Dict[str, Tuple[int, int, int, int]] = {}
        self._cache_key: Any = None
        self._posiciones_cache_key: Any = None

        super().__init__(
            tipo_modelo=tipo_modelo,
            pos_mundo=pos_mundo,
            rotacion=rotacion,
            escala=escala,
            color=color,
            base=base,
            config=config,
        )

        global _ESCENA_DESPIECE_ACTIVA
        if any(term in str(self.tipo_modelo).lower() for term in ("despiece", "mecanico", "cubo_modular")):
            _ESCENA_DESPIECE_ACTIVA = self

        if piezas is not None:
            self.piezas = dict(piezas)
            for pid, p in self.piezas.items():
                p.part_id = str(pid)
                if not getattr(p, "node_name", None):
                    p.node_name = str(pid)
                c_local = getattr(p, "centroide_local", None)
                if c_local is not None:
                    self.centroides_locales[pid] = np.asarray(c_local, dtype=np.float32)
                elif len(p.vertices_locales) > 0:
                    self.centroides_locales[pid] = p.vertices_locales.mean(axis=0)
                else:
                    self.centroides_locales[pid] = np.zeros(3, dtype=np.float32)
                self.jerarquia[pid] = getattr(p, "parent_name", "world")
                self.matrices_locales[pid] = getattr(p, "transform_local", np.eye(4, dtype=np.float32))
        elif not self.piezas:
            self._construir_piezas(self.tipo_modelo)

        self._actualizar_posiciones_piezas()

    @property
    def nodos(self) -> List[str]:
        """Retorna la lista de nombres de nodos jerárquicos cargados en la escena."""
        return list(self.piezas.keys())

    @property
    def lista_nodos(self) -> List[Objeto3D]:
        """Retorna la lista de instancias Objeto3D correspondientes a los nodos de la escena."""
        return list(self.piezas.values())

    def calcular_centroide_ensamble(self) -> np.ndarray:
        """Calcula el centroide geométrico global actual de todos los vértices locales del ensamble."""
        if not self.piezas:
            if len(self.vertices_locales) > 0:
                return self.vertices_locales.mean(axis=0).astype(np.float32)
            return np.zeros(3, dtype=np.float32)
        listas_v = [p.vertices_locales for p in self.piezas.values() if len(p.vertices_locales) > 0]
        if not listas_v:
            return np.zeros(3, dtype=np.float32)
        todos_v = np.vstack(listas_v)
        return todos_v.mean(axis=0).astype(np.float32)

    def obtener_extents_ensamble(self) -> np.ndarray:
        """Calcula las dimensiones del bounding box 3D envolvente (dx, dy, dz) en espacio local normalizado."""
        if not self.piezas:
            if len(self.vertices_locales) > 0:
                return (self.vertices_locales.max(axis=0) - self.vertices_locales.min(axis=0)).astype(np.float32)
            return np.zeros(3, dtype=np.float32)
        listas_v = [p.vertices_locales for p in self.piezas.values() if len(p.vertices_locales) > 0]
        if not listas_v:
            return np.zeros(3, dtype=np.float32)
        todos_v = np.vstack(listas_v)
        return (todos_v.max(axis=0) - todos_v.min(axis=0)).astype(np.float32)

    def _construir_cubo_modular_fallback(self) -> None:
        """Construye el cubo modular procedural de 8 octantes canónicos (usado por defecto o como fallback seguro)."""
        self.piezas.clear()
        self.centroides_locales.clear()
        self.jerarquia.clear()
        self.matrices_locales.clear()

        octantes_coords = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        s_dim = 0.38
        base_verts, base_edges, base_faces = generar_geometria_cubo(lado=s_dim)

        colores_octantes = [
            (0, 255, 255), (0, 200, 255), (0, 255, 200), (100, 255, 255),
            (255, 200, 0), (255, 255, 100), (0, 230, 255), (200, 255, 150),
        ]

        for i, (sx, sy, sz) in enumerate(octantes_coords):
            part_id = f"pieza_{i}"
            c_vec = np.array([sx * 0.55, sy * 0.55, sz * 0.55], dtype=np.float32)
            mat_local = np.eye(4, dtype=np.float32)
            mat_local[:3, 3] = c_vec
            p = Objeto3D(
                tipo_modelo=f"octante_{i}",
                pos_mundo=self.pos_mundo.copy(),
                rotacion=self.rotacion.copy(),
                escala=self.escala,
                color=colores_octantes[i % len(colores_octantes)],
                base=self.base,
                config=self.config,
                node_name=part_id,
                part_id=part_id,
                parent_name="world",
                transform_local=mat_local,
            )
            p.vertices_locales = base_verts.copy()
            p.aristas = list(base_edges)
            p.caras = [list(f) for f in base_faces]
            p.centroide_local = c_vec
            self.piezas[part_id] = p
            self.centroides_locales[part_id] = c_vec
            self.jerarquia[part_id] = "world"
            self.matrices_locales[part_id] = mat_local

        self.centroide_global = np.zeros(3, dtype=np.float32)
        self.escala_normalizacion = 1.0

    def _construir_ensamble_mecanico_multicapa(self) -> None:
        """
        Construye el Ensamble Mecánico Industrial Multicapa procedural (Fase 4):
        Compuesto por 6 piezas sólidas técnicas con geometría de alta resolución (>= 32 segmentos):
        1. Carcasa Exterior (Bloque / Carcasa exterior)
        2. Cubierta Superior (Cubierta superior mecanizada)
        3. Eje Rotor Central (Eje motriz central)
        4. Engranaje Planetario (Corona dentada toroidal)
        5. Pistones Radiales (Cilindros radiales)
        6. Brida de Acoplamiento (Brida de transmisión)
        """
        self.piezas.clear()
        self.centroides_locales.clear()
        self.jerarquia.clear()
        self.matrices_locales.clear()

        # Geometrías procedurales industriales de alta resolución (>= 32 segmentos)
        v_base, e_base, f_base = generar_geometria_caja(dx=2.60, dy=0.22, dz=0.90)
        v_carcasa, e_carcasa, f_carcasa = generar_geometria_cilindro_z(radio=0.95, longitud=0.75, segmentos=32)
        v_cubierta, e_cubierta, f_cubierta = generar_geometria_cilindro_z(radio=0.90, longitud=0.25, segmentos=32)
        v_eje, e_eje, f_eje = generar_geometria_cilindro_z(radio=0.20, longitud=2.30, segmentos=32)
        v_engranaje, e_engranaje, f_engranaje = generar_geometria_dona(major_r=0.70, minor_r=0.18, n_u=32, n_v=16)
        v_pistones, e_pistones, f_pistones = generar_geometria_cilindro_x(radio=0.24, longitud=1.40, segmentos=32)
        v_brida, e_brida, f_brida = generar_geometria_cilindro_z(radio=0.85, longitud=0.20, segmentos=32)

        piezas_def = [
            ("placa_base",          v_base,      e_base,      f_base,      np.array([ 0.00, -0.85,  0.00], dtype=np.float32), (60, 65, 75)),
            ("carcasa_exterior",    v_carcasa,   e_carcasa,   f_carcasa,   np.array([ 0.00,  0.00,  0.00], dtype=np.float32), (65, 70, 80)),
            ("cubierta_superior",   v_cubierta,  e_cubierta,  f_cubierta,  np.array([ 0.00,  0.00,  0.75], dtype=np.float32), (185, 195, 210)),
            ("eje_rotor_central",   v_eje,       e_eje,       f_eje,       np.array([ 0.00,  0.00,  0.00], dtype=np.float32), (230, 235, 245)),
            ("engranaje_planetario",v_engranaje, e_engranaje, f_engranaje, np.array([ 0.00,  0.00,  0.30], dtype=np.float32), (35, 160, 215)),
            ("pistones_radiales",   v_pistones,  e_pistones,  f_pistones,  np.array([ 0.00,  0.00, -0.30], dtype=np.float32), (160, 115, 60)),
            ("brida_acoplamiento",  v_brida,     e_brida,     f_brida,     np.array([ 0.00,  0.00, -0.75], dtype=np.float32), (170, 180, 190)),
        ]

        for part_id, verts, edges, faces, c_vec, col in piezas_def:
            mat_local = np.eye(4, dtype=np.float32)
            mat_local[:3, 3] = c_vec
            p = Objeto3D(
                tipo_modelo=part_id,
                pos_mundo=self.pos_mundo.copy(),
                rotacion=self.rotacion.copy(),
                escala=self.escala,
                color=col,
                base=self.base,
                config=self.config,
                node_name=part_id,
                part_id=part_id,
                parent_name="world",
                transform_local=mat_local,
            )
            p.vertices_locales = verts.copy()
            p.aristas = list(edges)
            p.caras = [list(f) for f in faces]
            p.centroide_local = c_vec
            self.piezas[part_id] = p
            self.centroides_locales[part_id] = c_vec
            self.jerarquia[part_id] = "world"
            self.matrices_locales[part_id] = mat_local

        self.centroide_global = np.zeros(3, dtype=np.float32)
        self.escala_normalizacion = 1.0

    def _construir_ensamblaje_axial_industrial(self) -> None:
        """Alias para _construir_ensamble_mecanico_multicapa para compatibilidad retrospectiva."""
        self._construir_ensamble_mecanico_multicapa()

    def cargar_gltf_glb(
        self,
        ruta_o_datos: Union[str, bytes, bytearray, io.BytesIO, Any],
        max_caras: Optional[int] = None,
        reorientar_z_up_a_y_up: bool = False,
    ) -> bool:
        """
        Subfase 2.2: Carga e interpreta un ensamble 3D jerárquico GLTF/GLB (.glb/.gltf).
        Si el archivo está corrupto, incompleto o vacío, activa tolerancia a fallos
        construyendo la malla cúbica modular procedural como fallback seguro.
        Retorna True si la carga GLTF/GLB fue exitosa, o False si se recurrió al fallback.
        """
        limite_caras = int(max_caras) if max_caras is not None else int(self.config.get("max_caras_render", 3000))
        resultado = cargar_ensamble_gltf_glb(
            ruta_o_datos=ruta_o_datos,
            max_caras=limite_caras,
            reorientar_z_up_a_y_up=reorientar_z_up_a_y_up,
        )

        if resultado is None or not resultado.get("nodos"):
            logger.warning(f"SceneModel: Falló la ingesta GLTF/GLB para '{ruta_o_datos}'. Activando fallback procedural.")
            self.fallback_activado = True
            if any(term in str(self.tipo_modelo).lower() for term in ("mecanic", "motor", "industrial")):
                self._construir_ensamble_mecanico_multicapa()
            else:
                self._construir_cubo_modular_fallback()
            self._posiciones_cache_key = None
            self._cache_key = None
            self._actualizar_posiciones_piezas()
            return False

        self.fallback_activado = False
        self.piezas.clear()
        self.centroides_locales.clear()
        self.offsets_manuales.clear()
        self.jerarquia.clear()
        self.matrices_locales.clear()
        self.pieza_seleccionada_id = None

        paleta_nodos = [
            (0, 255, 255), (0, 210, 255), (50, 255, 200), (120, 240, 255),
            (255, 210, 40), (255, 255, 110), (40, 230, 255), (180, 255, 140),
        ]

        todos_verts: List[np.ndarray] = []
        for idx, info_nodo in enumerate(resultado["nodos"]):
            part_id = str(info_nodo["part_id"])
            node_name = str(info_nodo["node_name"])
            parent_name = info_nodo.get("parent_name", "world")
            mat_local = np.asarray(info_nodo["transform_local"], dtype=np.float32).reshape((4, 4))
            c_pieza = np.asarray(info_nodo["centroide_local"], dtype=np.float32)
            v_locales = np.asarray(info_nodo["vertices_locales"], dtype=np.float32)
            n_locales = np.asarray(info_nodo.get("normales_locales", np.empty((0, 3), dtype=np.float32)), dtype=np.float32)

            col_pieza = paleta_nodos[idx % len(paleta_nodos)]
            pieza = Objeto3D(
                tipo_modelo=node_name,
                pos_mundo=self.pos_mundo.copy(),
                rotacion=self.rotacion.copy(),
                escala=self.escala,
                color=col_pieza,
                base=self.base,
                config=self.config,
                node_name=node_name,
                part_id=part_id,
                parent_name=parent_name,
                transform_local=mat_local,
            )
            pieza.vertices_locales = v_locales
            pieza.normales_locales = n_locales
            pieza.aristas = list(info_nodo["aristas"])
            pieza.caras = [list(f) for f in info_nodo["caras"]]
            pieza.centroide_local = c_pieza

            self.piezas[part_id] = pieza
            self.centroides_locales[part_id] = c_pieza
            self.jerarquia[part_id] = parent_name
            self.matrices_locales[part_id] = mat_local
            todos_verts.append(v_locales)

        if todos_verts:
            self.vertices_locales = np.vstack(todos_verts).astype(np.float32)

        self.centroide_original = np.asarray(resultado["centroide_original"], dtype=np.float32)
        self.centroide_global = np.asarray(resultado["centroide_global"], dtype=np.float32)
        self.escala_normalizacion = float(resultado["escala_normalizacion"])
        self.orientacion_ejes = str(resultado.get("orientacion_ejes", "Y-up / Z-forward"))

        self._posiciones_cache_key = None
        self._cache_key = None
        self._actualizar_posiciones_piezas()
        return True

    # Alias directo para invocaciones concisas
    cargar_glb = cargar_gltf_glb

    def _construir_piezas(self, tipo_modelo: str) -> None:
        """Construye las sub-piezas procedurales o a partir de ensambles GLTF/GLB y mallas Trimesh."""
        clave_raw = str(tipo_modelo).strip()
        clave = clave_raw.lower()

        # 0. Detección prioritaria de formatos jerárquicos GLTF/GLB (.glb / .gltf)
        es_formato_glb = clave.endswith((".glb", ".gltf"))
        if not es_formato_glb:
            for ext_g in (".glb", ".gltf", ".GLB", ".GLTF"):
                if os.path.exists(os.path.join(ASSETS_DIR, clave_raw + ext_g)):
                    es_formato_glb = True
                    break

        if es_formato_glb:
            self.cargar_gltf_glb(clave_raw)
            return

        # 1. Malla externa (.obj o .stl) si existe el archivo
        ruta_archivo = None
        if os.path.isabs(clave_raw) and os.path.exists(clave_raw):
            ruta_archivo = clave_raw
        else:
            candidato = os.path.join(ASSETS_DIR, os.path.basename(clave_raw))
            if os.path.exists(candidato):
                ruta_archivo = candidato

        if ruta_archivo and HAS_TRIMESH and trimesh is not None:
            try:
                mesh = trimesh.load(ruta_archivo)
                if isinstance(mesh, trimesh.Scene):
                    geoms = [g for g in mesh.dump() if isinstance(g, trimesh.Trimesh)]
                else:
                    geoms = mesh.split(only_watertight=False)

                if len(geoms) > 1:
                    max_caras_sub = max(200, 3000 // len(geoms))
                    for i, g in enumerate(geoms[:12]):
                        g_simp = g.simplify_quadric_decimation(max_caras_sub) if len(g.faces) > max_caras_sub else g
                        c_i = np.array(g_simp.centroid, dtype=np.float32)
                        verts_norm = np.array(g_simp.vertices - c_i, dtype=np.float32)
                        edges_i = [tuple(int(x) for x in e) for e in g_simp.edges_unique]
                        faces_i = [list(int(x) for x in f) for f in g_simp.faces]

                        col_sub = (
                            int(np.clip(self.color[0] + (i * 35) % 80 - 40, 0, 255)),
                            int(np.clip(self.color[1] + (i * 45) % 80 - 40, 0, 255)),
                            int(np.clip(self.color[2] + (i * 25) % 80 - 40, 0, 255)),
                        )
                        part_id = f"pieza_{i}"
                        mat_local = np.eye(4, dtype=np.float32)
                        mat_local[:3, 3] = c_i
                        p = Objeto3D(
                            tipo_modelo=f"{clave}_{i}",
                            pos_mundo=self.pos_mundo.copy(),
                            rotacion=self.rotacion.copy(),
                            escala=self.escala,
                            color=col_sub,
                            base=self.base,
                            config=self.config,
                            node_name=part_id,
                            part_id=part_id,
                            parent_name="world",
                            transform_local=mat_local,
                        )
                        p.vertices_locales = verts_norm
                        p.aristas = edges_i
                        p.caras = faces_i
                        p.centroide_local = c_i
                        self.piezas[part_id] = p
                        self.centroides_locales[part_id] = c_i
                        self.jerarquia[part_id] = "world"
                        self.matrices_locales[part_id] = mat_local
                    return
            except Exception as e:
                logger.debug(f"Aviso al despiezar malla {clave}: {e}")

        # 2. Despiece modular procedural de Pirámide (base + 4 caras triangulares)
        if "piramide" in clave:
            partes_piramide = [
                ("base", np.array([0.0, 0.0, -0.6], dtype=np.float32), 0.70),
                ("cara_norte", np.array([0.0, 0.5, 0.1], dtype=np.float32), 0.50),
                ("cara_sur", np.array([0.0, -0.5, 0.1], dtype=np.float32), 0.50),
                ("cara_este", np.array([0.5, 0.0, 0.1], dtype=np.float32), 0.50),
                ("cara_oeste", np.array([-0.5, 0.0, 0.1], dtype=np.float32), 0.50),
            ]
            v_base, e_base, f_base = generar_geometria_piramide(base_w=0.6, altura=0.7)
            for i, (nombre, c_vec, _) in enumerate(partes_piramide):
                part_id = f"pieza_{i}"
                mat_local = np.eye(4, dtype=np.float32)
                mat_local[:3, 3] = c_vec
                p = Objeto3D(
                    tipo_modelo=nombre,
                    pos_mundo=self.pos_mundo.copy(),
                    rotacion=self.rotacion.copy(),
                    escala=self.escala,
                    color=self.color,
                    base=self.base,
                    config=self.config,
                    node_name=nombre,
                    part_id=part_id,
                    parent_name="world",
                    transform_local=mat_local,
                )
                p.vertices_locales = np.array(v_base, dtype=np.float32)
                p.aristas = list(e_base)
                p.caras = [list(f) for f in f_base]
                p.centroide_local = c_vec
                self.piezas[part_id] = p
                self.centroides_locales[part_id] = c_vec
                self.jerarquia[part_id] = "world"
                self.matrices_locales[part_id] = mat_local
            return

        # 3. Despiece modular procedural
        if clave == "cubo_modular":
            self._construir_cubo_modular_fallback()
        elif any(term in clave for term in ("despiece", "mecanico", "industrial")):
            self._construir_ensamble_mecanico_multicapa()
        elif any(term in clave for term in ("cubo", "ensamblaje", "modular", "default")):
            self._construir_cubo_modular_fallback()

    def _actualizar_posiciones_piezas(self) -> None:
        """
        Calcula la posición cinemática de mundo para cada sub-pieza según el factor de explosión t:
        P_pieza(t) = P_centro + t * k * R * (C_pieza - C_centro) + Delta_manual
        Asimismo, actualiza la matriz de transformación local de explosión multiplicando su
        traslación local por (1.0 + t) sin deformar la geometría base.

        HIGH-02 — Idempotencia garantizada por caché de estado cinemático:
        - Si los parámetros cinemáticos no han cambiado (factor, rotación, pos, escala, offsets),
          retorna inmediatamente en O(1).
        """
        key = (
            round(float(self.factor_explosion), 4),
            round(float(self.pos_mundo[0]), 2),
            round(float(self.pos_mundo[1]), 2),
            round(float(self.pos_mundo[2]), 2),
            round(float(self.rotacion[0]), 4),
            round(float(self.rotacion[1]), 4),
            round(float(self.rotacion[2]), 4),
            round(float(self.escala), 4),
            tuple((k, round(float(v[0]), 2), round(float(v[1]), 2), round(float(v[2]), 2))
                  for k, v in sorted(self.offsets_manuales.items())),
            tuple(sorted(self.piezas_desacopladas)),
        )
        if getattr(self, "_posiciones_cache_key", None) == key:
            return  # Estado idéntico: salida O(1) inmediata

        rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
        t = float(self.factor_explosion)
        k = float(self.k_explosion * self.escala)

        for part_id, pieza in self.piezas.items():
            desacoplada = part_id in self.piezas_desacopladas
            manual = self.offsets_manuales.get(part_id, np.zeros(3, dtype=np.float32))

            if desacoplada:
                # Subfase 2.3: Nodo desacoplado con manipulación local aislada (independiente de la explosión global)
                pieza.pos_mundo[0] = float(self.pos_mundo[0] + manual[0])
                pieza.pos_mundo[1] = float(self.pos_mundo[1] + manual[1])
                pieza.pos_mundo[2] = float(self.pos_mundo[2] + manual[2])
                pieza.transform_explosion = pieza.transform_local.copy()
            else:
                c_local = self.centroides_locales.get(part_id, np.zeros(3, dtype=np.float32))
                disp_3d = rot @ (c_local * (t * k))
                pieza.pos_mundo[0] = float(self.pos_mundo[0] + disp_3d[0] + manual[0])
                pieza.pos_mundo[1] = float(self.pos_mundo[1] + disp_3d[1] + manual[1])
                pieza.pos_mundo[2] = float(self.pos_mundo[2] + disp_3d[2] + manual[2])
                pieza.transform_explosion = pieza.transform_local.copy()
                pieza.transform_explosion[:3, 3] = pieza.transform_local[:3, 3] * (1.0 + t)

            pieza.rotacion[:] = self.rotacion[:]
            pieza.escala = float(self.escala)

        self._posiciones_cache_key = key
        self._cache_key = None

    def agregar_pieza(
        self,
        part_id: str,
        pieza: Objeto3D,
        centroide_local: Optional[np.ndarray] = None,
        parent_name: str = "world",
    ) -> None:
        """Agrega o registra una sub-pieza al ensamble jerárquico."""
        self.piezas[part_id] = pieza
        c_loc = centroide_local if centroide_local is not None else getattr(pieza, "centroide_local", np.zeros(3, dtype=np.float32))
        self.centroides_locales[part_id] = np.asarray(c_loc, dtype=np.float32)
        self.jerarquia[part_id] = parent_name
        if hasattr(pieza, "transform_local") and pieza.transform_local is not None:
            self.matrices_locales[part_id] = pieza.transform_local
        else:
            mat = np.eye(4, dtype=np.float32)
            mat[:3, 3] = self.centroides_locales[part_id]
            self.matrices_locales[part_id] = mat
        self._posiciones_cache_key = None
        self._cache_key = None

    def desacoplar_pieza(self, part_id: str) -> bool:
        """
        Subfase 2.3: Desacopla temporalmente una sub-pieza de la jerarquía de explosión global.
        Su matriz de transformación local responde al arrastre de forma independiente.
        """
        if part_id not in self.piezas:
            return False
        if part_id not in self.piezas_desacopladas:
            rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
            t = float(self.factor_explosion)
            k = float(self.k_explosion * self.escala)
            c_local = self.centroides_locales.get(part_id, np.zeros(3, dtype=np.float32))
            disp_3d = rot @ (c_local * (t * k))
            actual_manual = self.offsets_manuales.get(part_id, np.zeros(3, dtype=np.float32))
            self.offsets_manuales[part_id] = (disp_3d + actual_manual).astype(np.float32)

            self.piezas_desacopladas.add(part_id)
            self.modo_manipulacion = "PIEZA"
            self._posiciones_cache_key = None
            self._cache_key = None
            self._actualizar_posiciones_piezas()
        return True

    def reacoplar_pieza(self, part_id: str) -> bool:
        """
        Subfase 2.3: Reacopla la sub-pieza a la jerarquía de explosión global (inercia elástica).
        """
        if part_id in self.piezas_desacopladas:
            self.piezas_desacopladas.remove(part_id)
            if part_id in self.offsets_manuales:
                del self.offsets_manuales[part_id]
            if not self.piezas_desacopladas:
                self.modo_manipulacion = "ENSAMBLE"
            self._posiciones_cache_key = None
            self._cache_key = None
            self._actualizar_posiciones_piezas()
            return True
        return False

    def reacoplar_todas(self) -> None:
        """Reacopla todas las sub-piezas a la jerarquía global."""
        self.piezas_desacopladas.clear()
        self.offsets_manuales.clear()
        self.modo_manipulacion = "ENSAMBLE"
        self._posiciones_cache_key = None
        self._cache_key = None
        self._actualizar_posiciones_piezas()

    def esta_desacoplada(self, part_id: str) -> bool:
        """Retorna True si la pieza está desacoplada de la jerarquía de explosión global."""
        return part_id in self.piezas_desacopladas

    def set_factor_explosion(self, t: float) -> None:
        """
        Regula el factor de explosión escalar t en el rango [0.0, 1.0].
        0.0 = Ensamblado original compacto.
        1.0 = Despiece radial máximo.
        """
        self.factor_explosion = float(np.clip(t, 0.0, 1.0))
        self._cache_key = None
        self._actualizar_posiciones_piezas()

    def reensamblar(self) -> None:
        """Colapsa el despiece al estado original ensamblado (t = 0.0) y resetea offsets manuales y estados de pieza."""
        self.factor_explosion = 0.0
        self.offsets_manuales.clear()
        self.piezas_desacopladas.clear()
        self.modo_manipulacion = "ENSAMBLE"
        self.pieza_seleccionada_id = None
        self.pieza_aislada_id = None
        self.pieza_resaltada_id = None
        self.piezas_ocultas.clear()
        self.piezas_xray.clear()
        for p in self.piezas.values():
            p.visible = True
            p.xray = False
        self._cache_key = None
        self._actualizar_posiciones_piezas()

    def toggle_visibilidad_pieza(self, part_id: str) -> bool:
        """Alterna visibilidad de una pieza individual (mostrar/ocultar)."""
        if part_id not in self.piezas:
            return False
        p = self.piezas[part_id]
        nuevo = not getattr(p, "visible", True)
        p.visible = nuevo
        if nuevo:
            self.piezas_ocultas.discard(part_id)
        else:
            self.piezas_ocultas.add(part_id)
        self._cache_key = None
        return nuevo

    def aislar_pieza(self, part_id: Optional[str]) -> None:
        """Aisla una pieza ocultando todas las demás. Si ya estaba aislada, restaura todas."""
        if part_id is None or self.pieza_aislada_id == str(part_id):
            self.pieza_aislada_id = None
            self.restaurar_visibilidad_todas()
        else:
            self.pieza_aislada_id = str(part_id)
            self.piezas_ocultas.clear()
            for pid, p in self.piezas.items():
                if pid == str(part_id):
                    p.visible = True
                else:
                    p.visible = False
                    self.piezas_ocultas.add(pid)
        self._cache_key = None

    def resaltar_pieza(self, part_id: Optional[str]) -> None:
        """Resalta una pieza individual con feedback visual brillante."""
        if part_id is None or self.pieza_resaltada_id == str(part_id):
            self.pieza_resaltada_id = None
            self.pieza_seleccionada_id = None
        else:
            self.pieza_resaltada_id = str(part_id)
            self.pieza_seleccionada_id = str(part_id)
        self._cache_key = None

    def toggle_xray_pieza(self, part_id: str) -> bool:
        """Alterna modo Rayos-X (transparencia translúcida) sobre una pieza."""
        if part_id not in self.piezas:
            return False
        p = self.piezas[part_id]
        nuevo = not getattr(p, "xray", False)
        p.xray = nuevo
        if nuevo:
            self.piezas_xray.add(part_id)
        else:
            self.piezas_xray.discard(part_id)
        self._cache_key = None
        return nuevo

    def restaurar_visibilidad_todas(self) -> None:
        """Restaura la visibilidad de todas las piezas del modelo."""
        self.pieza_aislada_id = None
        self.piezas_ocultas.clear()
        for p in self.piezas.values():
            p.visible = True
        self._cache_key = None

    def calcular_ancla_pieza(self, part_id: str) -> np.ndarray:
        """
        Retorna las coordenadas 2D (px) del ancla de ensamble de la pieza:
        - Si está desacoplada: su posición original esperada en la formación de explosión actual.
        - Si el ensamble está explosionado: la posición base compacta ensamblada (t = 0.0).
        """
        rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
        c_local = self.centroides_locales.get(part_id, np.zeros(3, dtype=np.float32))
        t = float(self.factor_explosion)
        k = float(self.k_explosion * self.escala)

        if part_id in self.piezas_desacopladas:
            disp_3d = rot @ (c_local * (t * k))
            ancla_3d = self.pos_mundo + disp_3d
        else:
            ancla_3d = self.pos_mundo.copy()

        return np.array([float(ancla_3d[0]), float(ancla_3d[1])], dtype=np.float32)

    def dibujar_lineas_guia(self, frame: np.ndarray) -> np.ndarray:
        """
        Dibuja líneas guía finas (anti-aliased) entre la posición original (ancla)
        y la posición despiezada de cada sub-pieza del SceneModel.
        Incluye marcadores de ancla, resalte dinámico y feedback de proximidad magnética (< 65 px).
        """
        if not self.piezas:
            return frame

        tipo_mod = getattr(self, "tipo_modelo", "")
        es_desp = (tipo_mod in ("despiece", "despiece_mecanico", "motor", "anatomia", "anatomico") or getattr(self, "es_modelo_anatomico", False))
        es_no_desp = (getattr(self, "es_modelo_atomico", False) or getattr(self, "es_modelo_molecular", False) or tipo_mod in ("cubo", "esfera", "piramide", "dona", "modelo_atomico", "modelo_molecular", "superficie_3d"))
        if not es_desp or es_no_desp:
            return frame

        h_f, w_f = frame.shape[:2]
        t = float(self.factor_explosion)
        hay_desacoples = len(self.piezas_desacopladas) > 0

        if t <= 0.01 and not hay_desacoples:
            return frame

        for part_id, pieza in self.piezas.items():
            if not getattr(pieza, "visible", True):
                continue

            pos_ancla_2d = self.calcular_ancla_pieza(part_id)
            pos_pieza_2d = np.array([float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1])], dtype=np.float32)

            dist = float(np.linalg.norm(pos_pieza_2d - pos_ancla_2d))
            if dist < 4.0:
                continue

            ax, ay = int(round(pos_ancla_2d[0])), int(round(pos_ancla_2d[1]))
            px, py = int(round(pos_pieza_2d[0])), int(round(pos_pieza_2d[1]))

            if not (-150 <= ax <= w_f + 150 and -150 <= ay <= h_f + 150):
                continue
            if not (-150 <= px <= w_f + 150 and -150 <= py <= h_f + 150):
                continue

            esta_desacoplada = part_id in self.piezas_desacopladas
            esta_cerca_snap = (esta_desacoplada and dist < 65.0)
            es_seleccionada = (part_id == getattr(self, "pieza_seleccionada_id", None) or 
                               part_id == getattr(self, "pieza_resaltada_id", None))

            if esta_cerca_snap:
                col_linea = (255, 240, 50)  # Resalte cian táctil brillante (Fase 3)
                grosor = 2
            elif es_seleccionada:
                col_linea = (0, 240, 255)   # Amarillo / cian brillante
                grosor = 2
            else:
                col_linea = (220, 200, 80)  # Cian sutil holográfico
                grosor = 1

            # Línea guía continua fina con anti-aliasing
            cv2.line(frame, (ax, ay), (px, py), col_linea, grosor, cv2.LINE_AA)

            # Marcador en punto de ancla: círculo doble concéntrico
            cv2.circle(frame, (ax, ay), 3, col_linea, -1, cv2.LINE_AA)
            cv2.circle(frame, (ax, ay), 6, col_linea, 1, cv2.LINE_AA)

            # Marcador en centro de pieza
            cv2.circle(frame, (px, py), 2, col_linea, -1, cv2.LINE_AA)

            # Feedback visual de Snap Magnético cuando dist < 65 px
            if esta_cerca_snap:
                cv2.circle(frame, (ax, ay), 65, (255, 240, 50), 1, cv2.LINE_AA)
                cv2.line(frame, (ax - 72, ay), (ax - 58, ay), (255, 240, 50), 2, cv2.LINE_AA)
                cv2.line(frame, (ax + 58, ay), (ax + 72, ay), (255, 240, 50), 2, cv2.LINE_AA)
                cv2.line(frame, (ax, ay - 72), (ax, ay - 58), (255, 240, 50), 2, cv2.LINE_AA)
                cv2.line(frame, (ax, ay + 58), (ax, ay + 72), (255, 240, 50), 2, cv2.LINE_AA)
                cv2.putText(
                    frame,
                    f"SNAP {dist:.0f}px",
                    (ax + 10, ay - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (255, 240, 50),
                    1,
                    cv2.LINE_AA,
                )

        return frame

    def dibujar_panel_piezas(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Dibuja el panel táctil flotante con la lista de sub-piezas:
        mostrar/ocultar, aislar, resaltar y transparencia (Rayos-X).
        Solo visible para modelos de despiece o anatomía.
        """
        if not self.piezas or len(self.piezas) <= 1 or not getattr(self, "panel_despiece_visible", True):
            return frame

        tipo_mod = str(getattr(self, "tipo_modelo", "")).lower()
        es_no_desp = (
            getattr(self, "es_modelo_atomico", False)
            or getattr(self, "es_modelo_molecular", False)
            or getattr(self, "es_modelo_superficie", False)
            or tipo_mod in ("cubo", "esfera", "piramide", "dona", "modelo_atomico", "modelo_molecular", "superficie_3d", "onda_radial", "silla")
        )
        if es_no_desp:
            return frame

        h_f, w_f = frame.shape[:2]
        x1, y1 = 18, 88
        w_panel = 224
        n_piezas = len(self.piezas)
        max_filas = max(4, (h_f - y1 - 90) // 26)
        n_piezas_vis = min(n_piezas, max_filas)
        h_panel = 32 + n_piezas_vis * 26 + (40 if n_piezas > n_piezas_vis else 26)

        x2 = x1 + w_panel
        y2 = y1 + h_panel
        self.rect_panel_despiece = (x1, y1, x2, y2)

        if y2 > h_f - 10 or x2 > w_f - 10:
            return frame

        roi_p = frame[y1:y2, x1:x2]
        dark = np.zeros_like(roi_p)
        cv2.addWeighted(roi_p, 0.40, dark, 0.60, 0, roi_p)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 180, 50), 1, cv2.LINE_AA)

        # Encabezado
        cv2.putText(frame, "PIEZAS DESPIECE", (x1 + 8, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 220, 255), 1, cv2.LINE_AA)

        # Botón [VER TODAS] en cabecera
        btn_all_x1, btn_all_y1 = x1 + 132, y1 + 6
        btn_all_x2, btn_all_y2 = x2 - 8, y1 + 24
        self.rects_panel_piezas["RESTAURAR_TODAS"] = (btn_all_x1, btn_all_y1, btn_all_x2, btn_all_y2)
        cv2.rectangle(frame, (btn_all_x1, btn_all_y1), (btn_all_x2, btn_all_y2), (0, 200, 240), 1, cv2.LINE_AA)
        cv2.putText(frame, "VER TODO", (btn_all_x1 + 6, btn_all_y1 + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 240), 1, cv2.LINE_AA)

        mapa_nombres = {
            "pieza_0": "Soporte Izq",
            "pieza_1": "Buje Izq",
            "pieza_2": "Eje Central",
            "pieza_3": "Rueda",
            "pieza_4": "Buje Der",
            "pieza_5": "Soporte Der",
            "pieza_6": "Placa Base",
            "soporte_izq": "Soporte Izq",
            "buje_izq": "Buje Izq",
            "eje_central": "Eje Central",
            "rueda": "Rueda",
            "buje_der": "Buje Der",
            "soporte_der": "Soporte Der",
            "placa_base": "Placa Base",
        }

        # Filas de piezas con nombres legibles (limitadas por altura visible)
        items_piezas = list(self.piezas.items())[:n_piezas_vis]
        for i, (part_id, pieza) in enumerate(items_piezas):
            row_y1 = y1 + 32 + i * 26
            row_y2 = row_y1 + 22

            es_vis = getattr(pieza, "visible", True)
            es_iso = (self.pieza_aislada_id == part_id)
            es_res = (self.pieza_resaltada_id == part_id or self.pieza_seleccionada_id == part_id)
            es_xray = (part_id in self.piezas_xray or getattr(pieza, "xray", False))

            raw_nom = str(getattr(pieza, "node_name", part_id))
            nom_display = mapa_nombres.get(part_id, mapa_nombres.get(raw_nom, raw_nom.replace("_", " ").title()))[:12]
            col_nom = (50, 255, 120) if es_res else ((240, 240, 240) if es_vis else (120, 120, 120))
            cv2.putText(frame, nom_display, (x1 + 8, row_y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.33, col_nom, 1, cv2.LINE_AA)

            # Botón 1: [V] Visibilidad
            bx1_v, bx2_v = x1 + 110, x1 + 132
            self.rects_panel_piezas[f"TOGGLE_VIS_{part_id}"] = (bx1_v, row_y1, bx2_v, row_y2)
            col_btn_v = (0, 240, 255) if es_vis else (90, 90, 90)
            cv2.rectangle(frame, (bx1_v, row_y1), (bx2_v, row_y2), col_btn_v, 1, cv2.LINE_AA)
            cv2.putText(frame, "V" if es_vis else "X", (bx1_v + 6, row_y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.32, col_btn_v, 1, cv2.LINE_AA)

            # Botón 2: [A] Aislar
            bx1_a, bx2_a = x1 + 136, x1 + 158
            self.rects_panel_piezas[f"AISLAR_{part_id}"] = (bx1_a, row_y1, bx2_a, row_y2)
            col_btn_a = (0, 215, 255) if es_iso else (130, 130, 130)
            cv2.rectangle(frame, (bx1_a, row_y1), (bx2_a, row_y2), col_btn_a, 1, cv2.LINE_AA)
            cv2.putText(frame, "A", (bx1_a + 6, row_y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.32, col_btn_a, 1, cv2.LINE_AA)

            # Botón 3: [R] Resaltar
            bx1_r, bx2_r = x1 + 162, x1 + 184
            self.rects_panel_piezas[f"RESALTAR_{part_id}"] = (bx1_r, row_y1, bx2_r, row_y2)
            col_btn_r = (50, 255, 120) if es_res else (130, 130, 130)
            cv2.rectangle(frame, (bx1_r, row_y1), (bx2_r, row_y2), col_btn_r, 1, cv2.LINE_AA)
            cv2.putText(frame, "R", (bx1_r + 6, row_y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.32, col_btn_r, 1, cv2.LINE_AA)

            # Botón 4: [X] Rayos-X
            bx1_x, bx2_x = x1 + 188, x1 + 210
            self.rects_panel_piezas[f"XRAY_{part_id}"] = (bx1_x, row_y1, bx2_x, row_y2)
            col_btn_x = (255, 120, 220) if es_xray else (130, 130, 130)
            cv2.rectangle(frame, (bx1_x, row_y1), (bx2_x, row_y2), col_btn_x, 1, cv2.LINE_AA)
            cv2.putText(frame, "X", (bx1_x + 6, row_y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.32, col_btn_x, 1, cv2.LINE_AA)

        # Leyenda explicativa compacta de 1 línea al pie del panel
        y_leg = y1 + 32 + n_piezas_vis * 26 + 18
        if n_piezas > n_piezas_vis:
            cv2.putText(frame, f"(+{n_piezas - n_piezas_vis} piezas mas)", (x1 + 8, y_leg - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (180, 200, 220), 1, cv2.LINE_AA)
            y_leg += 12
        cv2.putText(frame, "[V]er [A]islar [R]esaltar [X]-Ray", (x1 + 8, y_leg), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (0, 200, 240), 1, cv2.LINE_AA)

        return frame

    def dibujar_slider_explosion(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Dibuja el slider interactivo horizontal para regular el factor de explosión (0% a 100%).
        """
        tipo_mod = getattr(self, "tipo_modelo", "")
        es_desp = (tipo_mod in ("despiece", "despiece_mecanico", "motor", "anatomia", "anatomico") or getattr(self, "es_modelo_anatomico", False))
        es_no_desp = (getattr(self, "es_modelo_atomico", False) or getattr(self, "es_modelo_molecular", False) or tipo_mod in ("cubo", "esfera", "piramide", "dona", "modelo_atomico", "modelo_molecular", "superficie_3d"))
        if not es_desp or es_no_desp:
            return frame
        h_f, w_f = frame.shape[:2]
        sw = 320
        sx1 = int(w_f // 2 - sw // 2)
        sx2 = sx1 + sw
        sy1 = int(h_f - 46)
        sy2 = int(h_f - 18)
        self.rect_slider_explosion = (sx1, sy1, sx2, sy2)

        track_x1 = sx1 + 86
        track_x2 = sx2 - 56
        track_y = int((sy1 + sy2) // 2)
        track_w = max(1, track_x2 - track_x1)
        self.track_slider_coords = (track_x1, track_x2, track_y)

        roi_s = frame[sy1:sy2, sx1:sx2]
        dark = np.zeros_like(roi_s)
        cv2.addWeighted(roi_s, 0.35, dark, 0.65, 0, roi_s)
        cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (200, 180, 50), 1, cv2.LINE_AA)

        cv2.putText(frame, "DESPIECE", (sx1 + 8, track_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 220, 255), 1, cv2.LINE_AA)
        cv2.line(frame, (track_x1, track_y), (track_x2, track_y), (70, 75, 80), 4, cv2.LINE_AA)

        t = float(self.factor_explosion)
        hx = int(round(track_x1 + t * track_w))
        if hx > track_x1:
            cv2.line(frame, (track_x1, track_y), (hx, track_y), (0, 220, 255), 4, cv2.LINE_AA)

        cv2.circle(frame, (hx, track_y), 6, (0, 220, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, (hx, track_y), 8, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"{int(round(t * 100))}%", (track_x2 + 8, track_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 220, 255), 1, cv2.LINE_AA)

        return frame

    def esta_sobre_ui_despiece(self, cursor_pos: Optional[Tuple[float, float]]) -> bool:
        """Determina si las coordenadas del cursor colisionan con el panel o el slider de despiece."""
        if cursor_pos is None:
            return False
        cx, cy = float(cursor_pos[0]), float(cursor_pos[1])

        if self.rect_slider_explosion is not None:
            sx1, sy1, sx2, sy2 = self.rect_slider_explosion
            if sx1 - 8 <= cx <= sx2 + 8 and sy1 - 8 <= cy <= sy2 + 8:
                return True

        if self.rect_panel_despiece is not None:
            px1, py1, px2, py2 = self.rect_panel_despiece
            if px1 <= cx <= px2 and py1 <= cy <= py2:
                return True

        return False

    def procesar_interaccion_despiece(
        self,
        cursor_pos: Tuple[float, float],
        clic: bool = False,
        drag: bool = False,
    ) -> Optional[str]:
        """
        Procesa clics y arrastres táctiles sobre el slider de explosión y botones del panel de piezas.
        """
        cx, cy = float(cursor_pos[0]), float(cursor_pos[1])

        # 1. Slider de explosión (clic o arrastre continuo)
        if self.track_slider_coords is not None and self.rect_slider_explosion is not None:
            sx1, sy1, sx2, sy2 = self.rect_slider_explosion
            track_x1, track_x2, track_y = self.track_slider_coords
            track_w = max(1, track_x2 - track_x1)

            if sx1 - 8 <= cx <= sx2 + 8 and sy1 - 8 <= cy <= sy2 + 8:
                if clic or drag:
                    nuevo_t = float(np.clip((cx - track_x1) / float(track_w), 0.0, 1.0))
                    self.set_factor_explosion(nuevo_t)
                    return f"SLIDER_EXPLOSION_{nuevo_t:.2f}"

        # 2. Panel táctil de piezas (botones por flanco de clic)
        if clic and self.rects_panel_piezas:
            for act_key, (bx1, by1, bx2, by2) in self.rects_panel_piezas.items():
                if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                    if act_key.startswith("TOGGLE_VIS_"):
                        pid = act_key.replace("TOGGLE_VIS_", "")
                        self.toggle_visibilidad_pieza(pid)
                        return act_key
                    elif act_key.startswith("AISLAR_"):
                        pid = act_key.replace("AISLAR_", "")
                        self.aislar_pieza(pid)
                        return act_key
                    elif act_key.startswith("RESALTAR_"):
                        pid = act_key.replace("RESALTAR_", "")
                        self.resaltar_pieza(pid)
                        return act_key
                    elif act_key.startswith("XRAY_"):
                        pid = act_key.replace("XRAY_", "")
                        self.toggle_xray_pieza(pid)
                        return act_key
                    elif act_key == "RESTAURAR_TODAS":
                        self.restaurar_visibilidad_todas()
                        return act_key

        return None


    def calcular_aabbs_piezas(self, pad: int = 10) -> Dict[str, Tuple[int, int, int, int]]:
        """Calcula el BBox 2D (AABB) independiente para cada sub-pieza del modelo con caché de cuadro."""
        key = (
            pad,
            round(float(self.factor_explosion), 3),
            round(float(self.pos_mundo[0]), 1),
            round(float(self.pos_mundo[1]), 1),
            round(float(self.rotacion[0]), 3),
            round(float(self.rotacion[1]), 3),
            round(float(self.rotacion[2]), 3),
            round(float(self.escala), 3),
            len(self.offsets_manuales),
        )
        if getattr(self, "_cache_key", None) == key and getattr(self, "_cached_aabbs", None):
            return self._cached_aabbs

        self._actualizar_posiciones_piezas()
        aabbs = {}
        for part_id, pieza in self.piezas.items():
            c_2d = (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))
            aabbs[part_id] = pieza.calcular_aabb_2d(center=c_2d, pad=pad)
        self._cached_aabbs = aabbs
        self._cache_key = key
        return aabbs

    def seleccionar_pieza(self, punto: Tuple[float, float], pad: int = 10) -> Optional[str]:
        """
        Detecta colisión 2D punto-AABB para seleccionar una sub-pieza individual.
        Retorna el part_id de la pieza seleccionada o None.
        """
        px, py = float(punto[0]), float(punto[1])
        aabbs = self.calcular_aabbs_piezas(pad=pad)
        mejor_id: Optional[str] = None
        mejor_z: float = -999999.0

        for part_id, bbox in aabbs.items():
            x1, y1, x2, y2 = bbox
            if x1 <= px <= x2 and y1 <= py <= y2:
                pieza = self.piezas[part_id]
                z_val = -float(pieza.pos_mundo[2])
                if z_val > mejor_z:
                    mejor_z = z_val
                    mejor_id = part_id

        self.pieza_seleccionada_id = mejor_id
        return mejor_id

    def trasladar_pieza(self, part_id: str, delta: Union[np.ndarray, Tuple[float, float], List[float]]) -> None:
        """Traslada aisladamente la sub-pieza seleccionada (aislamiento inercial)."""
        if part_id in self.piezas:
            if part_id not in self.offsets_manuales:
                self.offsets_manuales[part_id] = np.zeros(3, dtype=np.float32)
            d = np.asarray(delta, dtype=np.float32)
            self.offsets_manuales[part_id][0] += float(d[0])
            self.offsets_manuales[part_id][1] += float(d[1])
            self.piezas[part_id].pos_mundo[0] += float(d[0])
            self.piezas[part_id].pos_mundo[1] += float(d[1])
            self._posiciones_cache_key = None
            self._cache_key = None

    def set_tipo(self, tipo_modelo: str) -> None:
        """Carga el modelo y reconstruye sub-piezas si corresponde (LOW-15)."""
        super().set_tipo(tipo_modelo)
        if not hasattr(self, "piezas") or self.piezas is None:
            self.piezas = {}
            self.centroides_locales = {}
            self.offsets_manuales = {}
            self.pieza_seleccionada_id = None
        else:
            self.piezas.clear()
            self.centroides_locales.clear()
            self.offsets_manuales.clear()
            self.pieza_seleccionada_id = None
        self._construir_piezas(self.tipo_modelo)
        self._posiciones_cache_key = None
        self._cache_key = None
        self._actualizar_posiciones_piezas()

    def proyectar(
        self,
        center: Optional[Tuple[float, float]] = None,
        base: Optional[float] = None,
        scale: Optional[float] = None,
        rot_matrix: Optional[np.ndarray] = None,
    ) -> Tuple[List[Tuple[int, int]], np.ndarray]:
        """Proyecta vectorialmente todas las sub-piezas al plano 2D."""
        if not self.piezas:
            return super().proyectar(center=center, base=base, scale=scale, rot_matrix=rot_matrix)

        self._actualizar_posiciones_piezas()
        rot = rot_matrix if rot_matrix is not None else rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))
        todos_pts: List[Tuple[int, int]] = []
        todas_zc: List[float] = []
        for pieza in self.piezas.values():
            c_p = (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))
            pts_p, zc_p = pieza.proyectar(center=c_p, base=base, scale=scale, rot_matrix=rot)
            todos_pts.extend(pts_p)
            todas_zc.extend(zc_p.tolist())

        self.ultimos_puntos_2d = todos_pts
        self.ultimas_profundidades = np.array(todas_zc, dtype=np.float32) if todas_zc else np.empty(0, dtype=np.float32)
        return todos_pts, self.ultimas_profundidades

    def calcular_aabb_2d(
        self,
        center: Optional[Tuple[float, float]] = None,
        pad: int = 15,
    ) -> Tuple[int, int, int, int]:
        """Calcula el BBox 2D que engloba a todas las sub-piezas activas."""
        if not self.piezas:
            return super().calcular_aabb_2d(center=center, pad=pad)

        aabbs = self.calcular_aabbs_piezas(pad=pad)
        all_x1 = [box[0] for box in aabbs.values()]
        all_y1 = [box[1] for box in aabbs.values()]
        all_x2 = [box[2] for box in aabbs.values()]
        all_y2 = [box[3] for box in aabbs.values()]

        return (int(min(all_x1)), int(min(all_y1)), int(max(all_x2)), int(max(all_y2)))

    def contiene_punto(
        self,
        punto: Tuple[float, float],
        center: Optional[Tuple[float, float]] = None,
        pad: int = 15,
    ) -> bool:
        """
        Verifica colisión 2D punto-objeto en modo ensamble o despiece:
        Detecta colisión tanto con las sub-piezas físicas individuales (mecánica LEGO)
        como con el BBox envolvente global del ensamble.
        """
        if not self.piezas:
            return super().contiene_punto(punto, center=center, pad=pad)

        if getattr(self, "factor_explosion", 0.0) > 0.05:
            return self.seleccionar_pieza(punto, pad=pad) is not None
        return (self.seleccionar_pieza(punto, pad=pad) is not None) or super().contiene_punto(punto, center=center, pad=pad)

    def renderizar(
        self,
        frame: np.ndarray,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Renderiza todas las sub-piezas mediante un pipeline unificado de alto rendimiento (< 2.0 ms):
        1. Recorte en un único ROI acotado para todas las sub-piezas.
        2. Back-Face Culling 2D en caras poligonales.
        3. Fusión única cv2.addWeighted para caras transparentes (cero asignaciones redundantes).
        4. Renderizado directo de aristas y nodos sobre ROI.
        """
        if not self.piezas:
            return super().renderizar(frame, config=config, center=center)

        raw_cfg = config or self.config
        if hasattr(raw_cfg, "data"):
            cfg = raw_cfg.data
        elif isinstance(raw_cfg, dict):
            cfg = raw_cfg
        else:
            cfg = {}
        use_painter = bool(cfg.get("enable_painter_algorithm", True))
        use_faces = bool(cfg.get("enable_3d_faces", True))
        face_opacity = float(cfg.get("faces_opacity", 0.92))
        use_culling = bool(cfg.get("backface_culling", True))

        self._actualizar_posiciones_piezas()
        rot = rotation_matrix(float(self.rotacion[0]), float(self.rotacion[1]), float(self.rotacion[2]))

        # 1. Proyectar todas las sub-piezas y recopilar geometría 2D
        piezas_proy = []
        all_x = []
        all_y = []
        dx_c = float(center[0] - self.pos_mundo[0]) if center is not None else 0.0
        dy_c = float(center[1] - self.pos_mundo[1]) if center is not None else 0.0
        for part_id, pieza in self.piezas.items():
            if not getattr(pieza, "visible", True):
                continue
            c_p = (float(pieza.pos_mundo[0] + dx_c), float(pieza.pos_mundo[1] + dy_c))
            pts, zc = pieza.proyectar(center=c_p, rot_matrix=rot)
            if pts:
                for p in pts:
                    all_x.append(p[0])
                    all_y.append(p[1])
                piezas_proy.append((part_id, pieza, pts, zc))

        if not all_x:
            return frame

        # 2. Bounding Box acotado único para toda la escena
        h_f, w_f = frame.shape[:2]
        pad = 20
        x1 = max(0, min(all_x) - pad)
        y1 = max(0, min(all_y) - pad)
        x2 = min(w_f, max(all_x) + pad)
        y2 = min(h_f, max(all_y) + pad)

        if x2 <= x1 or y2 <= y1:
            return frame

        roi = frame[y1:y2, x1:x2]

        # 3. Ordenar piezas según profundidad Z
        if use_painter:
            piezas_proy.sort(key=lambda item: float(item[1].pos_mundo[2]), reverse=True)

        # 4. Renderizado de caras con Back-Face Culling en overlays separados (Sólido vs Rayos-X)
        if use_faces:
            overlay_solid = roi.copy()
            overlay_xray = roi.copy()
            hay_solid = False
            hay_xray = False
            for part_id, pieza, pts, zc in piezas_proy:
                es_res = (part_id == getattr(self, "pieza_resaltada_id", None) or 
                          part_id == self.pieza_seleccionada_id)
                es_xray = (part_id in getattr(self, "piezas_xray", set()) or getattr(pieza, "xray", False))
                col = (50, 255, 120) if es_res else pieza.color
                pts_roi = [(int(p[0] - x1), int(p[1] - y1)) for p in pts]

                caras = getattr(pieza, "caras", [])
                v_loc = getattr(pieza, "vertices_locales", np.empty((0, 3), dtype=np.float32))
                for f in caras:
                    if len(f) >= 3 and all(idx < len(pts_roi) for idx in f):
                        if use_culling:
                            p0 = pts_roi[f[0]]
                            p1 = pts_roi[f[1]]
                            p2 = pts_roi[f[2]]
                            cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
                            if cross <= 0:
                                continue  # Cara posterior oculta

                        # Sombreado 3D sólido por normal de cara con vector de luz [0.4, 0.7, 0.6]
                        if len(v_loc) > max(f):
                            v0_3d = v_loc[f[0]] @ rot.T
                            v1_3d = v_loc[f[1]] @ rot.T
                            v2_3d = v_loc[f[2]] @ rot.T
                            n_3d = np.cross(v1_3d - v0_3d, v2_3d - v0_3d)
                            norm_val = float(np.linalg.norm(n_3d))
                            if norm_val > 1e-6:
                                n_unit = n_3d / norm_val
                                L_dir = np.array([0.40, 0.70, 0.60], dtype=np.float32)
                                L_dir /= np.linalg.norm(L_dir)
                                ndotl = abs(float(np.dot(n_unit, L_dir)))
                                shading = float(np.clip(0.40 + 0.60 * ndotl, 0.25, 1.0))
                            else:
                                shading = 0.70
                        else:
                            shading = 0.70

                        face_col = (
                            int(np.clip(col[0] * shading, 0, 255)),
                            int(np.clip(col[1] * shading, 0, 255)),
                            int(np.clip(col[2] * shading, 0, 255)),
                        )
                        poly = np.array([pts_roi[idx] for idx in f], dtype=np.int32)
                        if es_xray:
                            cv2.fillPoly(overlay_xray, [poly], face_col)
                            hay_xray = True
                        else:
                            cv2.fillPoly(overlay_solid, [poly], face_col)
                            hay_solid = True

            if hay_solid:
                cv2.addWeighted(overlay_solid, face_opacity, roi, 1.0 - face_opacity, 0, roi)
            if hay_xray:
                cv2.addWeighted(overlay_xray, 0.22, roi, 0.78, 0, roi)

        # 5. Renderizado directo de aristas tubulares y nodos sobre roi (cero copias de memoria)
        for part_id, pieza, pts, zc in piezas_proy:
            is_sel = (part_id == getattr(self, "pieza_resaltada_id", None) or 
                      part_id == self.pieza_seleccionada_id)
            is_xray = (part_id in getattr(self, "piezas_xray", set()) or getattr(pieza, "xray", False))
            col = (50, 255, 120) if is_sel else ((255, 230, 80) if is_xray else pieza.color)
            pts_roi = [(int(p[0] - x1), int(p[1] - y1)) for p in pts]

            spec_col = (
                min(255, int(col[0] * 1.35 + 75)),
                min(255, int(col[1] * 1.35 + 75)),
                min(255, int(col[2] * 1.35 + 75)),
            )

            aristas = getattr(pieza, "aristas", [])
            for a, b in aristas:
                if a < len(pts_roi) and b < len(pts_roi):
                    # Arista tubular: trazo base de mayor grosor + resalte especular reflectante
                    grosor_base = 3 if is_sel else (1 if is_xray else 2)
                    cv2.line(roi, pts_roi[a], pts_roi[b], col, grosor_base, cv2.LINE_AA)
                    if not is_xray:
                        cv2.line(roi, pts_roi[a], pts_roi[b], spec_col, 1, cv2.LINE_AA)

            for p in pts_roi:
                # Vértice iluminado con destello especular
                r_vert = 4 if is_sel else (2 if is_xray else 3)
                cv2.circle(roi, p, r_vert, col, -1, cv2.LINE_AA)
                if not is_xray:
                    cv2.circle(roi, (p[0] - 1, p[1] - 1), 1, (255, 255, 255), -1, cv2.LINE_AA)

        # 6. Destacar AABB y etiqueta de la sub-pieza seleccionada aisladamente
        if self.pieza_seleccionada_id and self.pieza_seleccionada_id in self.piezas:
            p_sel = self.piezas[self.pieza_seleccionada_id]
            bx = p_sel.calcular_aabb_2d(center=p_sel.pos_mundo[:2], pad=6)
            col_b = (50, 255, 120)
            cv2.rectangle(frame, (int(bx[0]), int(bx[1])), (int(bx[2]), int(bx[3])), col_b, 1, cv2.LINE_AA)
            cv2.putText(
                frame,
                f"PIEZA: {self.pieza_seleccionada_id}",
                (int(bx[0]), max(int(bx[1] - 4), 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                col_b,
                1,
                cv2.LINE_AA,
            )

        # 7. Renderizado de líneas guía finas, panel de piezas y slider de explosión
        frame = self.dibujar_lineas_guia(frame)
        frame = self.dibujar_panel_piezas(frame)
        frame = self.dibujar_slider_explosion(frame)

        return frame

    def actualizar(
        self,
        nueva_pos: Optional[Union[np.ndarray, Tuple[float, float], Tuple[float, float, float]]] = None,
        delta_rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        nueva_rotacion: Optional[Union[np.ndarray, Tuple[float, float, float], List[float]]] = None,
        escala: Optional[float] = None,
        landmarks: Optional[Any] = None,
        pts: Optional[np.ndarray] = None,
        ahora: Optional[float] = None,
        gesto: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Actualiza transformaciones espaciales explícitas y sincroniza sub-piezas."""
        super().actualizar(
            nueva_pos=nueva_pos,
            delta_rotacion=delta_rotacion,
            nueva_rotacion=nueva_rotacion,
            escala=escala,
            landmarks=landmarks,
            pts=pts,
            ahora=ahora,
            gesto=gesto,
            **kwargs,
        )
        self._actualizar_posiciones_piezas()


# Catálogo canónico de modelos 3D GLTF/GLB disponibles en assets
MAPA_MODELOS_GLB: Dict[str, Tuple[str, str]] = {
    "corazon": ("anatomia/corazon.glb", "CORAZON"),
    "cerebro": ("anatomia/cerebro.glb", "CEREBRO"),
    "carro_buggy": ("mecanica/carro_buggy.glb", "CARRO_BUGGY"),
    "buggy": ("mecanica/carro_buggy.glb", "CARRO_BUGGY"),
    "reductora": ("mecanica/reductora_engranajes.glb", "REDUCTORA"),
    "reductora_engranajes": ("mecanica/reductora_engranajes.glb", "REDUCTORA"),
    "reductora_motor": ("mecanica/motores/reductora_motor.glb", "REDUCTORA"),
    "motor_mecanismo": ("mecanica/motores/motor_mecanismo.glb", "MOTOR_MECANISMO"),
    "motor_dc": ("mecanica/motores/motor_dc.glb", "MOTOR_DC"),
    "motor_brushless": ("mecanica/motores/motor_brushless.glb", "MOTOR_BRUSHLESS"),
    "motor_stepper": ("mecanica/motores/motor_stepper_nema17.glb", "MOTOR_STEPPER"),
    "motor_stepper_nema17": ("mecanica/motores/motor_stepper_nema17.glb", "MOTOR_STEPPER"),
    "arduino_uno": ("electronica/arduino_uno.glb", "ARDUINO_UNO"),
    "arduino": ("electronica/arduino_uno.glb", "ARDUINO_UNO"),
    "esp32_cam": ("electronica/esp32_s3_cam.glb", "ESP32_CAM"),
    "esp32_s3_cam": ("electronica/esp32_s3_cam.glb", "ESP32_CAM"),
    "casco_sensores": ("electronica/casco_sensores.glb", "CASCO_SENSORES"),
    "modulo_tech": ("electronica/modulo_tech.glb", "MODULO_TECH"),
}


class HologramController:
    """
    Controlador de la lógica, estados y renderizado interactivo del modo holograma.
    Gestiona el control bimanual, la telaraña fusionada y el menú de selección.
    """

    def __init__(
        self,
        config_or_w: Optional[Union[Dict[str, Any], Any, int]] = None,
        h: Optional[int] = None,
        renderer: Optional[BaseRenderer] = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(config_or_w, int):
            w_init = config_or_w
            h_init = int(h) if h is not None else 720
            self.config = kwargs.get("config", {})
        elif hasattr(config_or_w, "data"):
            w_init = 1280
            h_init = 720
            self.config = config_or_w.data
        elif isinstance(config_or_w, dict):
            w_init = 1280
            h_init = 720
            self.config = config_or_w
        else:
            w_init = 1280
            h_init = 720
            self.config = {}

        self.smooth = float(self.config.get("smooth_holograma", 0.25))
        self.web_smooth = float(self.config.get("web_smooth", 0.4))

        self.manos_estado = {
            "Left": self._crear_estado_mano(),
            "Right": self._crear_estado_mano(),
        }
        self.web_shape = "cubo_modular"
        self.web_active = False
        self.web_counter = 0
        self.web_pts_smooth: Optional[np.ndarray] = None

        # Color holográfico canónico constante (configurable o cian cuántico por defecto)
        self.color: Tuple[int, int, int] = tuple(self.config.get("color_holograma", (255, 235, 30)))

        # Instancia canónica única persistente centrada exactamente en el centro geométrico de la pantalla (X = 640.0, Y = 360.0)
        # Inicializada como Objeto3D sólido de 1 sola pieza para Cubo
        self.objeto_activo: SceneModel = SceneModel(
            tipo_modelo="cubo_modular",
            pos_mundo=np.array([float(w_init // 2), float(h_init // 2), 0.0], dtype=np.float32),
            color=self.color,
            config=self.config,
        )
        self.objeto_mundo: Objeto3D = self.objeto_activo
        self.objetos: Dict[str, Objeto3D] = {
            "Left": self.objeto_activo,
            "Right": self.objeto_activo,
        }
        self.pos_personalizada: bool = False

        # Subsistema de renderizado acelerado desacoplado (Principio P5)
        if renderer is not None:
            self.renderer = renderer
        else:
            self.renderer = crear_renderer(self.config, w=w_init, h=h_init)

        # Umbrales Schmitt Trigger de pinza
        self.agarrar_cerrar: float = float(self.config.get("agarrar_cerrar", 0.20))
        self.agarrar_liberar: float = float(self.config.get("agarrar_liberar", 0.32))

        # Máquina de Estados Finita (FSM) de Interacción Táctil (Fase 1.2)
        self.estado_fsm: str = "REPOSO"  # "REPOSO", "HOVER", "AGARRADO"
        self.seleccionado: bool = False  # Foco / Selección activa independiente del objeto 3D
        self._pinza_previa: bool = False  # Detección de flanco de subida de pinza
        self._frames_hover: int = 0
        self._frames_grab: int = 0
        self._frames_leave: int = 0
        self._frames_release: int = 0
        self.mano_grab_prev_pos: Optional[np.ndarray] = None
        self.mano_rot_prev_palm: Optional[np.ndarray] = None
        self._escala_grab: float = 1.0  # Escala congelada al momento de activar AGARRADO
        self._pinch_grab_dist: Optional[float] = None  # Distancia de pinza al momento del agarre
        self.bbox_2d: Tuple[int, int, int, int] = (540, 260, 740, 460)

        # Filtrado e inmunidad al ruido (Fase 1.4)
        self.deadband_escala: float = float(self.config.get("deadband_escala", 0.035))
        self.alpha_escala: float = float(self.config.get("alpha_escala", 0.20))
        self.deadband_rot_px: float = float(self.config.get("deadband_rot_px", 1.2))
        self.max_rot_delta_px: float = float(self.config.get("max_rot_delta_px", 120.0))

        # Gestión de Escena y Vista Explosionada Multi-Pieza (Fase 1.4 & Subfase 2.3)
        self.pieza_foco_id: Optional[str] = None
        self.factor_explosion: float = 0.0
        self.modo_manipulacion: str = "ENSAMBLE"  # "ENSAMBLE" (global) vs "PIEZA" (local)

        # Filtros One Euro dedicados anti-temblor para rotación, profundidad Z cenital y escala (Fase 9)
        rot_cutoff = float(self.config.get("rot_3d_min_cutoff", self.config.get("holo_min_cutoff", 0.45)))
        rot_beta = float(self.config.get("rot_3d_beta", self.config.get("holo_beta", 0.005)))
        escala_cutoff = float(self.config.get("escala_3d_min_cutoff", 0.45))
        escala_beta = float(self.config.get("escala_3d_beta", 0.005))

        self.filter_yaw: OneEuroFilter = OneEuroFilter(min_cutoff=rot_cutoff, beta=rot_beta)
        self.filter_pitch: OneEuroFilter = OneEuroFilter(min_cutoff=rot_cutoff, beta=rot_beta)
        self.filter_roll: OneEuroFilter = OneEuroFilter(min_cutoff=rot_cutoff, beta=rot_beta)
        self.filter_z: OneEuroFilter = OneEuroFilter(min_cutoff=rot_cutoff, beta=rot_beta)
        self.deadband_escala_estricta: float = float(self.config.get("escala_3d_deadband", 0.04))
        self.filter_escala: OneEuroFilter = OneEuroFilter(min_cutoff=escala_cutoff, beta=escala_beta)
        self.filter_explosion: OneEuroFilter = OneEuroFilter(min_cutoff=0.40, beta=0.005, deadband=0.03)
        self._d_palmas_prev: Optional[float] = None

        # Física de Trackball / Mapamundi con momento angular e inercia
        self.vel_yaw: float = 0.0
        self.vel_pitch: float = 0.0
        self.friccion_rotacion: float = float(self.config.get("friccion_rotacion", 0.95))
        self._ultimo_tiempo_rot: float = time.time()
        self._rotacion_aplicada_en_frame: bool = False

        # Animación suave de entrada (Ease-Out 300 ms) y centrado de pantalla en píxeles (Fase 4)
        self._anim_entrada_inicio: float = 0.0
        self._anim_entrada_duracion: float = 0.30
        self._anim_entrada_activa: bool = False
        self._escala_base_objetivo: float = 1.0
        self._ultimo_w: int = 1280
        self._ultimo_h: int = 720

    @staticmethod
    def _crear_estado_mano() -> Dict[str, Any]:
        return {
            "yaw": 0.0,
            "pitch": 0.0,
            "scale": 1.0,
            "shape": "cubo",
            "smooth_palm": None,
            "smooth_ratio": None,
            "pinch_prev": False,
            "euro_palm": OneEuroFilter2D(min_cutoff=1.2, beta=0.15, d_cutoff=1.0, deadband=1.0),
        }

    def reset(self) -> None:
        """Reinicia el estado del holograma a valores predeterminados."""
        self.manos_estado = {
            "Left": self._crear_estado_mano(),
            "Right": self._crear_estado_mano(),
        }
        self.web_active = False
        self.web_counter = 0
        self.web_pts_smooth = None
        self.pos_personalizada = False
        self.estado_fsm = "REPOSO"
        self.vel_yaw = 0.0
        self.vel_pitch = 0.0
        self._rotacion_aplicada_en_frame = False
        self.seleccionado = False
        self._pinza_previa = False
        self._frames_hover = 0
        self._frames_grab = 0
        self._frames_leave = 0
        self._frames_release = 0
        self.mano_grab_prev_pos = None
        self.mano_rot_prev_palm = None
        self._escala_grab = 1.0
        self._pinch_grab_dist = None
        self.pieza_foco_id = None
        self.factor_explosion = 0.0
        self.modo_manipulacion = "ENSAMBLE"
        self._ratio_pinza_prev = None
        self.filter_yaw.reset()
        self.filter_pitch.reset()
        self.filter_roll.reset()
        self.filter_z.reset()
        self.filter_escala.reset()
        if hasattr(self, "filter_explosion"):
            self.filter_explosion.reset()
        self._d_palmas_prev = None
        if isinstance(self.objeto_activo, SceneModel):
            self.objeto_activo.reensamblar()

        self.objeto_activo.rotacion = np.array([0.45, 0.35, 0.10], dtype=np.float32)
        self.objeto_activo.escala = 1.0
        cx = float(self._ultimo_w // 2)
        cy = float(self._ultimo_h // 2)
        self.objeto_activo.pos_mundo = np.array([cx, cy, 0.0], dtype=np.float32)
        self.objeto_activo.color = self.color
        self.objeto_mundo = self.objeto_activo
        self.objetos["Left"] = self.objeto_activo
        self.objetos["Right"] = self.objeto_activo

    def centrar_objeto(self, w: Optional[int] = None, h: Optional[int] = None, animar: bool = True) -> None:
        """
        Fija la posición del objeto activo estrictamente en el centro geométrico de la pantalla
        en píxeles: [float(w // 2), float(h // 2), 0.0] (jamás [0, 0, 0]).
        Ajusta la escala para ocupar ~55% de la altura útil de la pantalla con animación
        suave de entrada (ease-out 300 ms).
        """
        curr_w = int(w if w is not None else self._ultimo_w)
        curr_h = int(h if h is not None else self._ultimo_h)
        cx = float(curr_w // 2)
        cy = float(curr_h // 2)

        if hasattr(self, "objeto_activo") and self.objeto_activo is not None:
            self.objeto_activo.pos_mundo = np.array([cx, cy, 0.0], dtype=np.float32)

            # Cálculo de escala para ocupar ~55% de la altura útil del fotograma
            altura_util = 0.55 * float(curr_h)
            ext_aprox = 200.0
            if hasattr(self.objeto_activo, "obtener_extents_ensamble"):
                try:
                    exts = self.objeto_activo.obtener_extents_ensamble()
                    if exts is not None and len(exts) >= 2 and float(exts[1]) > 10.0:
                        ext_aprox = float(exts[1])
                except Exception:
                    pass
            elif hasattr(self.objeto_activo, "base") and getattr(self.objeto_activo, "base", 0) > 10:
                ext_aprox = float(self.objeto_activo.base)

            escala_55 = max(0.2, min(5.0, altura_util / max(ext_aprox, 50.0)))
            self._escala_base_objetivo = escala_55

            # Reset de filtros e inercia para arranque limpio
            self.filter_yaw.reset()
            self.filter_pitch.reset()
            self.filter_roll.reset()
            self.vel_pitch = 0.0
            self.vel_yaw = 0.0

            if animar:
                self._anim_entrada_inicio = time.time()
                self._anim_entrada_activa = True
                self.objeto_activo.escala = self._escala_base_objetivo * 0.65
            else:
                self._anim_entrada_activa = False
                self.objeto_activo.escala = self._escala_base_objetivo

    def liberar_objeto(self) -> None:
        """Libera de forma limpia e inmediata los buffers GPU (VBOs/VAOs) del objeto activo."""
        if hasattr(self, "renderer") and hasattr(self.renderer, "liberar_buffers_objeto"):
            try:
                self.renderer.liberar_buffers_objeto(self.objeto_activo)
            except Exception as e:
                logger.debug(f"HologramController: Aviso al liberar buffers de GPU: {e}")

    def liberar(self) -> None:
        """Libera de forma limpia e idempotente los recursos del controlador holografico."""
        self.reset()
        if hasattr(self.renderer, "liberar"):
            try:
                self.renderer.liberar()
            except Exception as e:
                logger.debug(f"Aviso al liberar renderer: {e}")

    def set_factor_explosion(self, t: float) -> None:
        """Regula el factor de explosión escalar t en [0.0, 1.0] sobre SceneModel."""
        self.factor_explosion = float(np.clip(t, 0.0, 1.0))
        if isinstance(self.objeto_activo, SceneModel):
            self.objeto_activo.set_factor_explosion(self.factor_explosion)

    def reensamblar(self) -> None:
        """Colapsa el despiece multi-pieza al estado ensamblado original (t = 0.0)."""
        self.factor_explosion = 0.0
        self.pieza_foco_id = None
        self.modo_manipulacion = "ENSAMBLE"
        if isinstance(self.objeto_activo, SceneModel):
            self.objeto_activo.reensamblar()

    def cargar_modelo_escena(self, scene: SceneModel) -> None:
        """Carga un SceneModel como entidad activa principal."""
        if hasattr(self, "renderer") and hasattr(self.renderer, "liberar_buffers_objeto"):
            self.renderer.liberar_buffers_objeto(self.objeto_activo)
        self.objeto_activo = scene
        self.objeto_mundo = scene
        self.objetos["Left"] = scene
        self.objetos["Right"] = scene
        self.factor_explosion = scene.factor_explosion
        self.modo_manipulacion = getattr(scene, "modo_manipulacion", "ENSAMBLE")
        self.centrar_objeto(animar=True)

    def cargar_modelo_glb(self, ruta_o_id: str, nombre_modelo: Optional[str] = None) -> SceneModel:
        """
        Carga e inicializa un ensamble 3D jerárquico desde un archivo GLTF/GLB (.glb/.gltf)
        como entidad SceneModel activa, resolviendo la ruta en assets (anatomia, mecanica, electronica, motores).
        Garantiza liberación previa de VBOs en VRAM y centrado suave en pantalla.
        """
        self.liberar_objeto()

        ruta_str = str(ruta_o_id).strip()
        ruta_res: Optional[str] = None

        if os.path.isabs(ruta_str) and os.path.exists(ruta_str):
            ruta_res = ruta_str
        else:
            candidatos = [
                os.path.join(ASSETS_DIR, ruta_str),
                os.path.join(ASSETS_DIR, "anatomia", ruta_str),
                os.path.join(ASSETS_DIR, "mecanica", ruta_str),
                os.path.join(ASSETS_DIR, "mecanica", "motores", ruta_str),
                os.path.join(ASSETS_DIR, "electronica", ruta_str),
            ]
            for cand in candidatos:
                if os.path.exists(cand):
                    ruta_res = os.path.abspath(cand)
                    break
                for ext in (".glb", ".gltf", ".GLB", ".GLTF"):
                    if os.path.exists(cand + ext):
                        ruta_res = os.path.abspath(cand + ext)
                        break
                if ruta_res:
                    break

        if not ruta_res or not os.path.exists(ruta_res):
            logger.warning(f"HologramController: No se localizó archivo GLB para '{ruta_o_id}'. Usando nombre como fallback.")
            ruta_res = ruta_str

        nom = nombre_modelo or os.path.splitext(os.path.basename(ruta_res))[0].upper()
        escena = SceneModel(
            tipo_modelo=nom,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        escena.cargar_gltf_glb(ruta_res)
        self.cargar_modelo_escena(escena)

        tag = nom.lower()
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = tag
        self.web_shape = tag
        self.centrar_objeto(animar=True)
        return escena

    def cargar_modelo_atomico(
        self,
        protones: int = 6,
        neutrones: int = 6,
        electrones: Optional[int] = None,
    ) -> Any:
        """Carga e inicializa el simulador cuántico ModeloAtomico como entidad activa (Etapa 3)."""
        from atomic_model import ModeloAtomico
        atom = ModeloAtomico(
            protones=protones,
            neutrones=neutrones,
            electrones=electrones,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.cargar_modelo_escena(atom)
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = "atomo"
        self.web_shape = "atomo"
        return atom

    def cargar_modelo_molecular(
        self,
        preset: str = "H2O",
    ) -> Any:
        """Carga e inicializa el constructor molecular ModeloMolecular como entidad activa (STARK Molecular Builder)."""
        from molecular_model import ModeloMolecular
        mol = ModeloMolecular(
            preset=preset,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.cargar_modelo_escena(mol)
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = "molecula"
        self.web_shape = "molecula"
        return mol

    def cargar_modelo_superficie(
        self,
        preset: str = "onda_radial",
    ) -> Any:
        """Carga e inicializa la superficie matemática 3D ModeloSuperficie3D como entidad activa (STARK Math Grapher)."""
        from math_grapher import ModeloSuperficie3D
        surf = ModeloSuperficie3D(
            preset=preset,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.cargar_modelo_escena(surf)
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = "superficie"
        self.web_shape = "superficie"
        return surf

    def cargar_modelo_anatomico(
        self,
        preset: str = "corazon",
    ) -> Any:
        """Carga e inicializa el modelo anatómico multicapa ModeloAnatomico (STARK Bio-Anatomy Engine)."""
        from anatomy_model import ModeloAnatomico
        anat = ModeloAnatomico(
            preset=preset,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.cargar_modelo_escena(anat)
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = "anatomia"
        self.web_shape = "anatomia"
        return anat

    def cargar_modelo_despiece(self) -> SceneModel:
        """Carga e inicializa el ensamble mecánico industrial despiezable (Modo LEGO)."""
        escena = SceneModel(
            tipo_modelo="despiece",
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.cargar_modelo_escena(escena)
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = "despiece"
        self.web_shape = "despiece"
        return escena

    def cargar_modelo_primitiva(self, nombre_figura: str) -> Objeto3D:
        """Carga una figura geométrica sólida primitiva (cubo, esfera, piramide, dona)."""
        if hasattr(self, "renderer") and hasattr(self.renderer, "liberar_buffers_objeto"):
            self.renderer.liberar_buffers_objeto(self.objeto_activo)
        figura = str(nombre_figura).lower()
        obj = Objeto3D(
            tipo_modelo=figura,
            pos_mundo=self.objeto_activo.pos_mundo.copy(),
            rotacion=self.objeto_activo.rotacion.copy(),
            escala=self.objeto_activo.escala,
            color=self.color,
            config=self.config,
        )
        self.objeto_activo = obj
        self.objeto_mundo = obj
        self.objetos["Left"] = obj
        self.objetos["Right"] = obj
        for et in ("Left", "Right"):
            if et in self.manos_estado:
                self.manos_estado[et]["shape"] = figura
        self.web_shape = figura
        self.centrar_objeto(animar=True)
        return obj

    def cargar_figura_geometrica(self, nombre_figura: str) -> Objeto3D:
        """Alias para cargar_modelo_primitiva para compatibilidad total."""
        return self.cargar_modelo_primitiva(nombre_figura)

    def _sincronizar_figura_activa(self, fig_activa: Any) -> None:
        """Sincroniza la figura activa del controlador con el modelo 3D activo sin recargas redundantes."""
        fig_act_str = str(fig_activa).lower().strip()
        tipo_act_str = str(getattr(self.objeto_activo, "tipo_modelo", "")).lower().strip()

        es_cubo_nuevo = fig_act_str in ("cubo", "cubo_modular")
        es_cubo_act = tipo_act_str in ("cubo", "cubo_modular")
        if es_cubo_nuevo and es_cubo_act:
            return

        if fig_act_str == tipo_act_str:
            return

        es_atom_act = getattr(self.objeto_activo, "es_modelo_atomico", False)
        es_atom_new = fig_act_str in ("atomo", "modelo_atomico", "atomico")
        es_mol_act = getattr(self.objeto_activo, "es_modelo_molecular", False)
        es_mol_new = fig_act_str in ("molecula", "molecular", "modelo_molecular")
        es_surf_act = getattr(self.objeto_activo, "es_modelo_superficie", False)
        es_surf_new = fig_act_str in ("superficie", "math", "math_3d", "superficie_3d", "onda_radial", "silla")
        es_anat_act = getattr(self.objeto_activo, "es_modelo_anatomico", False)
        es_anat_new = fig_act_str in ("anatomia", "anatomico", "bio")
        es_despiece_nuevo = fig_act_str in ("despiece", "ensamblaje", "mecanico")

        # 1. Catálogo GLTF/GLB especializado (Anatomía, Mecánica, Electrónica, Motores)
        if fig_act_str in MAPA_MODELOS_GLB:
            ruta_glb, nom_glb = MAPA_MODELOS_GLB[fig_act_str]
            if tipo_act_str != nom_glb.lower():
                self.liberar_objeto()
                self.cargar_modelo_glb(ruta_glb, nom_glb)
            return

        # 2. Rutas directas a archivos .glb / .gltf
        if fig_act_str.endswith((".glb", ".gltf")):
            nom_archivo = os.path.splitext(os.path.basename(fig_act_str))[0].lower()
            if tipo_act_str != nom_archivo:
                self.liberar_objeto()
                self.cargar_modelo_glb(fig_act_str)
            return

        # 3. Modelos funcionales STARK (Átomo, Molécula, Superficie Math, Anatomía)
        if es_atom_new:
            if not es_atom_act:
                self.liberar_objeto()
                self.cargar_modelo_atomico()
            return

        if es_mol_new:
            if not es_mol_act:
                self.liberar_objeto()
                self.cargar_modelo_molecular()
            return

        if es_surf_new:
            if not es_surf_act:
                self.liberar_objeto()
                preset_m = fig_act_str if fig_act_str in ("onda_radial", "silla") else "onda_radial"
                self.cargar_modelo_superficie(preset=preset_m)
            return

        if es_anat_new:
            if not es_anat_act:
                self.liberar_objeto()
                self.cargar_modelo_anatomico(preset="corazon")
            return

        if es_despiece_nuevo:
            if tipo_act_str != "despiece":
                self.liberar_objeto()
                self.cargar_modelo_despiece()
            return

        if es_cubo_nuevo and not es_cubo_act:
            self.liberar_objeto()
            nueva_escena = SceneModel(
                tipo_modelo="cubo_modular",
                pos_mundo=self.objeto_activo.pos_mundo.copy(),
                rotacion=self.objeto_activo.rotacion.copy(),
                escala=self.objeto_activo.escala,
                color=self.color,
                config=self.config,
            )
            self.cargar_modelo_escena(nueva_escena)
            return

        # 4. Primitivas geométricas sólidas (cubo, esfera, piramide, dona, mi_modelo)
        if not isinstance(self.objeto_activo, SceneModel) and fig_act_str in ("cubo", "esfera", "piramide", "dona", "mi_modelo"):
            self.objeto_activo.set_tipo(fig_act_str)
            return

        self.liberar_objeto()
        self.cargar_modelo_primitiva(fig_activa)

    def set_renderer(self, renderer: BaseRenderer) -> None:
        """Permite inyectar o alternar el motor de renderizado (GlRenderer / CpuRenderer) en caliente."""
        self.renderer = renderer

    def obtener_bbox_2d(self, pad: int = 20) -> Tuple[int, int, int, int]:
        """Retorna el Bounding Box 2D [x_min, y_min, x_max, y_max] proyectado del objeto activo."""
        self.bbox_2d = self.objeto_activo.calcular_aabb_2d(pad=pad)
        return self.bbox_2d

    def _reproducir_sonido_snap(self) -> None:
        """Emite retroalimentación acústica opcional ante snap magnético."""
        try:
            import winsound
            winsound.Beep(1200, 40)
        except Exception:
            pass

    def _dibujar_etiqueta_contextual_flotante(
        self,
        frame: np.ndarray,
        part_id: str,
        pieza: Objeto3D,
        estado: str,
    ) -> None:
        """
        Subfase 2.3: Etiquetado Contextual Flotante (Anclaje 3D -> 2D estilo HUD).
        Proyecta el centroide 3D de la sub-pieza a coordenadas de pantalla (2D)
        y dibuja una tarjeta de información con retícula y directriz quebrada.
        Muestra nombre de pieza, distancia al ancla y estado de proximidad magnética (< 65 px).
        """
        h_f, w_f = frame.shape[:2]
        c_p = (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))
        pts_p, _ = pieza.proyectar(center=c_p)
        if pts_p:
            cx = int(np.mean([p[0] for p in pts_p]))
            cy = int(np.mean([p[1] for p in pts_p]))
        else:
            cx = int(pieza.pos_mundo[0])
            cy = int(pieza.pos_mundo[1])

        cx = max(15, min(cx, w_f - 15))
        cy = max(15, min(cy, h_f - 15))

        es_desacoplada = False
        dist_ancla = 0.0
        if isinstance(self.objeto_activo, SceneModel):
            es_desacoplada = self.objeto_activo.esta_desacoplada(part_id)
            pos_ancla_2d = self.objeto_activo.calcular_ancla_pieza(part_id)
            dist_ancla = float(np.linalg.norm(np.array([cx, cy], dtype=np.float32) - pos_ancla_2d))

        es_snap = es_desacoplada and (dist_ancla < 65.0)

        if es_snap:
            tag_estado = "[SNAP READY]"
            col_hud = (255, 240, 50)  # Resalte cian táctil brillante (Fase 3)
        elif estado == "AGARRADO" or es_desacoplada:
            tag_estado = "[DESACOPLADA]" if es_desacoplada else "[DRAG]"
            col_hud = (50, 255, 120)  # Verde táctil
        elif estado == "HOVER":
            tag_estado = "[HOVER]"
            col_hud = (255, 255, 100)  # Cian/amarillo neón
        else:
            tag_estado = "[SELECCIONADA]"
            col_hud = (0, 255, 255)  # Amarillo neón

        # 1. Retícula de fijación (crosshair / anchor 3D)
        cv2.circle(frame, (cx, cy), 3, col_hud, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 7, col_hud, 1, cv2.LINE_AA)

        # 2. Geometría de tarjeta HUD flotante
        card_w, card_h = 185, 42
        if cx + 45 + card_w < w_f - 10:
            tx = cx + 45
            elbow_x = cx + 25
        else:
            tx = max(10, cx - 45 - card_w)
            elbow_x = cx - 25

        if cy - 35 - card_h > 10:
            ty = cy - 35
            elbow_y = cy - 20
        else:
            ty = min(h_f - card_h - 10, cy + 35)
            elbow_y = cy + 20

        # Directriz quebrada (leader line)
        cv2.line(frame, (cx, cy), (elbow_x, elbow_y), col_hud, 1, cv2.LINE_AA)
        target_x_conn = tx if tx > cx else tx + card_w
        cv2.line(frame, (elbow_x, elbow_y), (target_x_conn, ty + card_h // 2), col_hud, 1, cv2.LINE_AA)

        # 3. Tarjeta HUD translúcida con telemetría
        x1_c, y1_c = tx, ty
        x2_c, y2_c = tx + card_w, ty + card_h
        roi_c = frame[y1_c:y2_c, x1_c:x2_c]
        if roi_c.shape[0] == card_h and roi_c.shape[1] == card_w:
            dark_bg = np.zeros_like(roi_c)
            cv2.addWeighted(roi_c, 0.35, dark_bg, 0.65, 0, roi_c)
            cv2.rectangle(frame, (x1_c, y1_c), (x2_c, y2_c), col_hud, 1, cv2.LINE_AA)

            nodo_nombre = getattr(pieza, "node_name", part_id)
            texto_linea1 = f"{nodo_nombre} {tag_estado}"
            if es_snap:
                texto_linea2 = f"SNAP: {dist_ancla:.0f}px (<65px LOCK)"
            elif dist_ancla > 0.0:
                texto_linea2 = f"Dist: {dist_ancla:.0f}px | Z:{pieza.pos_mundo[2]:.0f}"
            else:
                texto_linea2 = f"X:{pieza.pos_mundo[0]:.0f} Y:{pieza.pos_mundo[1]:.0f} Z:{pieza.pos_mundo[2]:.0f}"

            cv2.putText(frame, texto_linea1, (x1_c + 6, y1_c + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.33, col_hud, 1, cv2.LINE_AA)
            cv2.putText(frame, texto_linea2, (x1_c + 6, y1_c + 33), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (200, 230, 255), 1, cv2.LINE_AA)

    def _dibujar_feedback_fsm(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """Dibuja retroalimentación visual holográfica según el estado FSM (HOVER / AGARRADO / FOCO)."""
        # Si el modelo tiene una sub-pieza bajo foco (HOVER o seleccionada), encuadrar la pieza individual
        if isinstance(self.objeto_activo, SceneModel) and getattr(self, "pieza_foco_id", None):
            if self.pieza_foco_id in self.objeto_activo.piezas:
                p_foco = self.objeto_activo.piezas[self.pieza_foco_id]
                bbox = p_foco.calcular_aabb_2d(center=p_foco.pos_mundo[:2], pad=10)
                # Subfase 2.3: Etiquetado contextual flotante anclado 3D -> 2D
                self._dibujar_etiqueta_contextual_flotante(frame, self.pieza_foco_id, p_foco, self.estado_fsm)


        x1, y1, x2, y2 = bbox
        h_f, w_f = frame.shape[:2]
        x1 = max(0, min(x1, w_f - 1))
        y1 = max(0, min(y1, h_f - 1))
        x2 = max(0, min(x2, w_f - 1))
        y2 = max(0, min(y2, h_f - 1))

        if self.estado_fsm == "HOVER":
            col = (255, 255, 100)  # Cian/amarillo neón
            d = max(12, int((x2 - x1) * 0.15))
            cv2.line(frame, (x1, y1), (x1 + d, y1), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x1, y1), (x1, y1 + d), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2 - d, y1), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2, y1 + d), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1 + d, y2), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1, y2 - d), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2 - d, y2), col, 2, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2, y2 - d), col, 2, cv2.LINE_AA)  # MEDIUM-09: segmento vertical correcto
            cv2.putText(frame, "HOVER", (x1, max(y1 - 6, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)

        elif self.estado_fsm == "AGARRADO":
            col = (50, 255, 50)  # Verde táctil
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2, cv2.LINE_AA)
            cv2.putText(frame, "DRAG", (x1, max(y1 - 6, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)

        elif getattr(self, "seleccionado", False):
            # Objeto con foco / seleccionado: corchetes discretos cian neón
            col = (255, 200, 0)
            d = max(8, int((x2 - x1) * 0.10))
            cv2.line(frame, (x1, y1), (x1 + d, y1), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x1, y1), (x1, y1 + d), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2 - d, y1), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x2, y1), (x2, y1 + d), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1 + d, y2), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x1, y2), (x1, y2 - d), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2 - d, y2), col, 1, cv2.LINE_AA)
            cv2.line(frame, (x2, y2), (x2, y2 - d), col, 1, cv2.LINE_AA)  # MEDIUM-09: segmento vertical correcto
            cv2.putText(frame, "FOCO", (x1, max(y1 - 6, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)

        # Feedback adicional de Despiece Mecánico (Líneas guía, panel de piezas y slider de explosión)
        if isinstance(self.objeto_activo, SceneModel):
            tipo_act = getattr(self.objeto_activo, "tipo_modelo", "")
            es_desp = (tipo_act in ("despiece", "despiece_mecanico", "motor", "anatomia", "anatomico") or getattr(self.objeto_activo, "es_modelo_anatomico", False))
            es_no_desp = (getattr(self.objeto_activo, "es_modelo_atomico", False) or getattr(self.objeto_activo, "es_modelo_molecular", False) or tipo_act in ("cubo", "esfera", "piramide", "dona", "modelo_atomico", "modelo_molecular", "superficie_3d"))
            if es_desp and not es_no_desp:
                self.objeto_activo.dibujar_lineas_guia(frame)
                self.objeto_activo.dibujar_panel_piezas(frame)
                self.objeto_activo.dibujar_slider_explosion(frame)


    def actualizar(
        self,
        frame: Any,
        manos: Optional[Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]] = None,
        datos_top: Optional[Dict[str, Any]] = None,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> None:
        """
        Ejecuta la actualización del holograma para el frame actual:
        calcula rotación/escala de cada mano o activa el modo telaraña conjunta.
        Permite fusionar la información cenital ortogonal de datos_top.
        Agnóstico al origen de entrada: soporta frame primero o manos primero,
        así como manos simuladas en lista [{"pos": (x, y), "pinch": bool}].
        """
        # Intercambio inteligente si los argumentos se enviaron en orden inverso
        if not isinstance(frame, np.ndarray) and isinstance(manos, np.ndarray):
            frame, manos = manos, frame

        if frame is None or not isinstance(frame, np.ndarray):
            frame = np.zeros((getattr(self, "_ultimo_h", 720), getattr(self, "_ultimo_w", 1280), 3), dtype=np.uint8)

        # Normalización de entrada agnóstica para lista de manos simuladas
        if isinstance(manos, list):
            manos_dict: Dict[str, Dict[str, Any]] = {}
            for i_m, m_item in enumerate(manos):
                if isinstance(m_item, dict) and "pos" in m_item:
                    px = float(m_item["pos"][0])
                    py = float(m_item["pos"][1])
                    pinch_val = bool(m_item.get("pinch", False))

                    if "pts" in m_item and m_item["pts"] is not None and len(m_item["pts"]) >= 21:
                        pts_sim = np.asarray(m_item["pts"], dtype=np.float32)
                    else:
                        # Síntesis precisa de 21 landmarks antropomórficos para mouse
                        pts_sim = np.zeros((21, 3), dtype=np.float32)
                        pts_sim[0] = [px, py + 80.0, 0.0]
                        pts_sim[5] = [px - 25.0, py + 40.0, 0.0]
                        pts_sim[9] = [px, py + 40.0, 0.0]
                        pts_sim[13] = [px + 20.0, py + 40.0, 0.0]
                        pts_sim[17] = [px + 35.0, py + 45.0, 0.0]
                        pts_sim[6] = [px - 5.0, py + 25.0, 0.0]
                        pts_sim[7] = [px - 2.0, py + 12.0, 0.0]
                        pts_sim[8] = [px, py, 0.0]
                        # palm_size = norm(pts[0] - pts[9]) = 40.0
                        # Pinza cerrada (pinch=True): dist = 6.0 -> ratio = 0.15 (< 0.20)
                        # Pinza abierta (pinch=False): dist = 42.0 -> ratio = 1.05 (> 0.32)
                        offset_thumb = 6.0 if pinch_val else 42.0
                        pts_sim[1] = [px - 20.0, py + 65.0, 0.0]
                        pts_sim[2] = [px - 30.0, py + 50.0, 0.0]
                        pts_sim[3] = [px - 25.0, py + 30.0, 0.0]
                        pts_sim[4] = [px - offset_thumb, py, 0.0]
                        for idx_base, col_off in [(10, 5), (14, 20), (18, 35)]:
                            pts_sim[idx_base] = [px + col_off, py + 25.0, 0.0]
                            pts_sim[idx_base + 1] = [px + col_off, py + 12.0, 0.0]
                            pts_sim[idx_base + 2] = [px + col_off, py, 0.0]

                    tag = "Right" if i_m == 0 else "Left"
                    manos_dict[tag] = {"pts": pts_sim, "pinch": pinch_val}
            manos = manos_dict
        elif manos is None:
            manos = {}

        h, w = frame.shape[:2]
        self._ultimo_w = w
        self._ultimo_h = h
        centro_pantalla = (float(w // 2), float(h // 2))
        self._rotacion_aplicada_en_frame = False

        # Animación suave de entrada (Ease-Out 300 ms) y centrado de pantalla (Fase 4)
        if self._anim_entrada_activa:
            ahora_anim = time.time()
            prog = (ahora_anim - self._anim_entrada_inicio) / max(self._anim_entrada_duracion, 1e-4)
            if prog >= 1.0:
                prog = 1.0
                self._anim_entrada_activa = False
                self.objeto_activo.escala = self._escala_base_objetivo
            else:
                ease_out = 1.0 - (1.0 - prog) ** 3
                self.objeto_activo.escala = self._escala_base_objetivo * (0.65 + 0.35 * ease_out)
            self.objeto_activo.pos_mundo[0] = float(w // 2)
            self.objeto_activo.pos_mundo[1] = float(h // 2)
            self.objeto_activo.pos_mundo[2] = 0.0
        elif not getattr(self, "pos_personalizada", False):
            # Si pos_mundo no ha sido modificado por interacción o está en reposo,
            # garantizar que pos_mundo coincida con el centro geométrico de la pantalla
            if np.allclose(self.objeto_activo.pos_mundo[:2], [640.0, 360.0]) and (w != 1280 or h != 720):
                self.objeto_activo.pos_mundo[0] = float(w // 2)
                self.objeto_activo.pos_mundo[1] = float(h // 2)

        # Fusión ortogonal z si la cámara cenital (Top-Down) está activa y detecta mano
        if datos_top is not None and isinstance(datos_top, dict) and datos_top.get("mano_detectada", False):
            z_cenital = datos_top.get("z_depth")
            if z_cenital is not None and hasattr(self, "filter_z"):
                z_filtrado = float(self.filter_z.filter(float(z_cenital) - 120.0))
                self.objeto_activo.pos_mundo[2] = z_filtrado

        if getattr(self.objeto_activo, "es_modelo_anatomico", False):
            self.objeto_activo.actualizar(frame, ahora=time.time())

        # Restablecer suavizado de manos ausentes para evitar tirones
        for etiqueta in ("Left", "Right"):
            if etiqueta not in manos:
                st = self.manos_estado[etiqueta]
                st["smooth_palm"] = None
                st["smooth_ratio"] = None
                st["pinch_prev"] = False
                if st.get("euro_palm") is not None:
                    st["euro_palm"].reset()

        info = {}
        for etiqueta, datos in manos.items():
            st = self.manos_estado[etiqueta]
            pts = np.asarray(datos["pts"], dtype=np.float32)
            palm = pts[[0, 5, 9, 13, 17]].mean(axis=0)
            palm_size = max(float(np.linalg.norm(pts[0] - pts[9])), 1.0)
            ratio = float(np.linalg.norm(pts[4] - pts[8])) / palm_size

            # Filtro OneEuroFilter2D estandarizado para posición de palma (cero jitter, cero retraso)
            if st.get("euro_palm") is None:
                st["euro_palm"] = OneEuroFilter2D(min_cutoff=1.2, beta=0.15, d_cutoff=1.0, deadband=1.0)
            p_filtrado = st["euro_palm"].filter((float(palm[0]), float(palm[1])))
            st["smooth_palm"] = np.array(p_filtrado, dtype=np.float32)

            if st["smooth_ratio"] is None:
                st["smooth_ratio"] = ratio
            else:
                st["smooth_ratio"] = self.smooth * ratio + (1.0 - self.smooth) * st["smooth_ratio"]

            # Anclas espaciales para desviación angular relativa (yaw y pitch)
            anchor = np.array([w * (0.27 if etiqueta == "Left" else 0.73), h * 0.55])
            norm_x = np.clip((st["smooth_palm"][0] - anchor[0]) / (w / 4.0), -1.5, 1.5)
            norm_y = np.clip((st["smooth_palm"][1] - h / 2.0) / (h / 2.0), -1.5, 1.5)

            st["yaw"] = norm_x * 1.4
            st["pitch"] = norm_y * 1.0
            st["scale"] = float(np.clip(st["smooth_ratio"] / 0.8, 0.4, 2.2))

            info[etiqueta] = {
                "pts": pts,
                "anchor": (float(anchor[0]), float(anchor[1])),
                "pinch": st["smooth_ratio"] < 0.35,
                "is_L": is_L_gesture(pts),
            }

        # Activación con histéresis del modo Telaraña (ambas manos en L)
        ambas_L = ("Left" in info and "Right" in info and info["Left"]["is_L"] and info["Right"]["is_L"])
        if ambas_L:
            self.web_counter = min(self.web_counter + 1, 10)
        else:
            self.web_counter = max(self.web_counter - 2, 0)

        if not self.web_active and self.web_counter >= 5:
            self.web_active = True
            self.web_pts_smooth = None
        elif self.web_active and self.web_counter <= 0:
            self.web_active = False

        if self.web_active and "Left" in info and "Right" in info:
            # === MODO TELARAÑA (un objeto fusionado central) ===
            raw = np.array(l_points(info["Left"]["pts"]) + l_points(info["Right"]["pts"]), dtype=np.float32)
            if self.web_pts_smooth is None:
                self.web_pts_smooth = raw
            else:
                self.web_pts_smooth = self.web_smooth * raw + (1.0 - self.web_smooth) * self.web_pts_smooth

            hull, centroid = draw_web(frame, self.web_pts_smooth, WEB_COLOR)

            area = float(cv2.contourArea(hull.astype(np.float32)))
            size = np.sqrt(max(area, 1.0))
            scale = float(np.clip(size / 180.0, 0.3, 3.0))

            pl = self.manos_estado["Left"]["smooth_palm"]
            pr = self.manos_estado["Right"]["smooth_palm"]
            roll = float(np.arctan2(pr[1] - pl[1], pr[0] - pl[0]))

            yaw = float(np.clip((centroid[0] - w / 2.0) / (w / 2.0), -1.5, 1.5)) * 1.4
            pitch = float(np.clip((centroid[1] - h / 2.0) / (h / 2.0), -1.5, 1.5)) * 1.0

            if not (getattr(self.objeto_activo, "es_modelo_atomico", False)
                    or getattr(self.objeto_activo, "es_modelo_anatomico", False)
                    or getattr(self.objeto_activo, "es_modelo_molecular", False)
                    or getattr(self.objeto_activo, "es_modelo_superficie", False)):
                self.objeto_activo.set_tipo(self.web_shape)
            self.objeto_activo.rotacion[0] = yaw
            self.objeto_activo.rotacion[1] = pitch
            self.objeto_activo.rotacion[2] = roll
            self.objeto_activo.escala = scale
            self.objeto_activo.pos_mundo[0] = float(centroid[0])
            self.objeto_activo.pos_mundo[1] = float(centroid[1])
            self.objeto_activo.color = self.color

            self.renderer.renderizar_escena(
                frame,
                self.objeto_activo,
                config=self.config,
                center=(float(centroid[0]), float(centroid[1])),
            )
        else:
            # === PIPELINE UNIFICADO Y MÁQUINA DE ESTADOS FINITA (FSM) DE INTERACCIÓN (Fase 1.2) ===
            bbox_actual = self.obtener_bbox_2d(pad=20)
            x_min, y_min, x_max, y_max = bbox_actual

            # Control Bimanual de Despiece (separación entre palmas normalizada)
            if "Left" in info and "Right" in info and isinstance(self.objeto_activo, SceneModel):
                if self.estado_fsm != "AGARRADO":
                    pl = self.manos_estado["Left"]["smooth_palm"]
                    pr = self.manos_estado["Right"]["smooth_palm"]
                    if pl is not None and pr is not None:
                        d_palmas = float(np.linalg.norm(pr - pl)) / max(float(w), 1.0)
                        # Amortiguación del 100%: si variación < 3%, t permanece congelado (Fase 3)
                        if self._d_palmas_prev is not None:
                            delta_rel = abs(d_palmas - self._d_palmas_prev) / max(self._d_palmas_prev, 1e-4)
                            if delta_rel < 0.03:
                                d_palmas = self._d_palmas_prev
                            else:
                                self._d_palmas_prev = d_palmas
                        else:
                            self._d_palmas_prev = d_palmas

                        t_bimanual = float(np.clip((d_palmas - 0.20) / 0.40, 0.0, 1.0))
                        if not info["Left"]["pinch"] and not info["Right"]["pinch"]:
                            if hasattr(self, "filter_explosion"):
                                t_filtrado = float(self.filter_explosion.filter(t_bimanual))
                            else:
                                t_filtrado = t_bimanual
                            self.set_factor_explosion(t_filtrado)

            if len(info) > 0:
                # Mano dominante activa (Right prioritaria o primera detectada)
                etiqueta_activa = "Right" if "Right" in info else next(iter(info.keys()))
                st = self.manos_estado[etiqueta_activa]
                pts_activa = info[etiqueta_activa]["pts"]

                # Puntos anatómicos clave (Landmark 8: yema índice, Landmark 4: yema pulgar)
                idx_tip = (float(pts_activa[8][0]), float(pts_activa[8][1]))
                palm = pts_activa[[0, 5, 9, 13, 17]].mean(axis=0)
                palm_size = max(float(np.linalg.norm(pts_activa[0] - pts_activa[9])), 1.0)
                dist_pinza = float(np.linalg.norm(pts_activa[4] - pts_activa[8]))
                ratio_pinza = dist_pinza / palm_size

                # Fusión cruzada ortogonal no ocluida con la cámara cenital
                if datos_top is not None and isinstance(datos_top, dict) and datos_top.get("mano_detectada", False):
                    top_pinch = datos_top.get("pinch_dist_top")
                    if top_pinch is not None:
                        ratio_pinza = min(ratio_pinza, float(top_pinch))

                # Orientación angular fluida en 3 ejes (yaw, pitch, roll)
                yaw_act = float(st["yaw"])
                pitch_act = float(st["pitch"])
                v_palm = pts_activa[17] - pts_activa[5]
                roll_act = float(np.arctan2(v_palm[1], v_palm[0]))

                # Subfase 2.3: GPU Ray Picking Preciso con resolución nativa de oclusiones
                pieza_pick = None
                if hasattr(self.renderer, "pick"):
                    pieza_pick = self.renderer.pick(idx_tip[0], idx_tip[1], objeto_o_escena=self.objeto_activo)
                elif hasattr(self.objeto_activo, "seleccionar_pieza"):
                    pieza_pick = self.objeto_activo.seleccionar_pieza(idx_tip)

                if pieza_pick is not None:
                    sobre_objeto = True
                    es_despiece = isinstance(self.objeto_activo, SceneModel) and bool(self.objeto_activo.piezas)
                    if es_despiece:
                        self.pieza_foco_id = pieza_pick
                        if hasattr(self.objeto_activo, "pieza_seleccionada_id"):
                            self.objeto_activo.pieza_seleccionada_id = pieza_pick
                else:
                    sobre_objeto = self.objeto_activo.contiene_punto(idx_tip, pad=20)
                    if not sobre_objeto and self.estado_fsm == "REPOSO":
                        self.pieza_foco_id = None
                        if hasattr(self.objeto_activo, "pieza_seleccionada_id"):
                            self.objeto_activo.pieza_seleccionada_id = None

                # Schmitt Trigger para pinza índice-pulgar
                pinza_cerrada = (ratio_pinza <= self.agarrar_cerrar)
                pinza_abierta = (ratio_pinza >= self.agarrar_liberar)

                # Flanco de bajada/subida de pinza (detección de clic / tap)
                flanco_pinza_down = bool(pinza_cerrada and not self._pinza_previa)
                flanco_pinza_up = bool(pinza_abierta and self._pinza_previa)

                # Interacción táctil directa con UI de Despiece (Slider de explosión y panel de piezas)
                if isinstance(self.objeto_activo, SceneModel) and self.objeto_activo.esta_sobre_ui_despiece(idx_tip):
                    if flanco_pinza_down:
                        act_desp = self.objeto_activo.procesar_interaccion_despiece(idx_tip, clic=True)
                        if act_desp:
                            self.set_factor_explosion(self.objeto_activo.factor_explosion)
                    elif pinza_cerrada:
                        act_desp = self.objeto_activo.procesar_interaccion_despiece(idx_tip, clic=False, drag=True)
                        if act_desp:
                            self.set_factor_explosion(self.objeto_activo.factor_explosion)

                # Rama especializada: FSM Subatómica para ModeloAtomico (Etapa 3)
                if getattr(self.objeto_activo, "es_modelo_atomico", False):
                    # PRIORIDAD TÁCTIL ABSOLUTA: Hit-test de Barra Lateral y Presets
                    cursor_int = (int(round(idx_tip[0])), int(round(idx_tip[1])))
                    toque_barra = self.objeto_activo.procesar_toque_barra_atomica(
                        cursor_int, pinza_activa=pinza_cerrada, ahora=time.time()
                    )
                    if toque_barra:
                        self.estado_fsm = "REPOSO"
                        self.mano_rot_prev_palm = None
                        self.vel_yaw = 0.0
                        self.vel_pitch = 0.0
                        self._pinza_previa = pinza_cerrada
                    else:
                        res_subat = self.objeto_activo.procesar_interaccion_subatomica(
                            cursor_pos=idx_tip,
                            pinza_cerrada=pinza_cerrada,
                            flanco_down=flanco_pinza_down,
                            flanco_up=flanco_pinza_up,
                            pieza_pick=pieza_pick,
                            sensibilidad_rotacion=float(self.config.get("sensibilidad_rotacion_3d", 0.006)),
                        )
                        self._pinza_previa = pinza_cerrada
                        evento = res_subat.get("evento", "REPOSO")
                        if evento in ("DRAG_DISPENSADOR", "ARRASTRANDO_NUEVA", "DRAG_NUCLEON", "ARRASTRANDO_EXISTENTE", "INICIO_DRAG_ATOMO", "ARRASTRANDO_ATOMO"):
                            self.estado_fsm = "AGARRADO"
                            self.pos_personalizada = True
                        elif evento in ("INICIO_ROTACION_GLOBAL", "ROTANDO_GLOBAL"):
                            self.estado_fsm = "HOVER"
                        elif evento in ("ABSORCION_NUCLEO", "ABSORCION_ORBITAL", "PARTICULA_ANIQUILADA", "PARTICULA_CANCELADA", "FIN_ROTACION_GLOBAL", "FIN_DRAG_ATOMO"):
                            self.estado_fsm = "REPOSO"

                        # Rotación 3D volumétrica fluida con una sola mano en el aire (cinemática cuántica libre)
                        particula_volando = getattr(self.objeto_activo, "particula_en_vuelo", None) is not None
                        if not pinza_cerrada and self.estado_fsm == "REPOSO" and not particula_volando:
                            curr_palm = st["smooth_palm"] if st.get("smooth_palm") is not None else palm
                            if self.mano_rot_prev_palm is not None:
                                dx = float(curr_palm[0] - self.mano_rot_prev_palm[0])
                                dy = float(curr_palm[1] - self.mano_rot_prev_palm[1])
                                disp = float(np.hypot(dx, dy))
                                if disp >= self.deadband_rot_px:
                                    vel_inst_yaw = (dx / float(w)) * 18.0
                                    vel_inst_pitch = -(dy / float(h)) * 18.0
                                    self.vel_yaw = 0.35 * self.vel_yaw + 0.65 * vel_inst_yaw
                                    self.vel_pitch = 0.35 * self.vel_pitch + 0.65 * vel_inst_pitch
                                    self.objeto_activo.rotacion[0] += self.vel_yaw
                                    self.objeto_activo.rotacion[1] += self.vel_pitch
                                    if hasattr(self.objeto_activo, "vel_yaw"):
                                        self.objeto_activo.vel_yaw = self.vel_yaw
                                        self.objeto_activo.vel_pitch = self.vel_pitch
                                self._rotacion_aplicada_en_frame = True
                                self.objeto_activo.rotacion[2] = float(self.filter_roll.filter(roll_act))

                            self.mano_rot_prev_palm = curr_palm.copy()
                        else:
                            self.mano_rot_prev_palm = None

                else:
                    # 1. Selección y Foco Táctil:
                    # Un pinch dentro de la BBox activa inmediatamente el foco del objeto.
                    # Un clic en espacio vacío fuera de la BBox en REPOSO desactiva el foco.
                    if flanco_pinza_down:
                        if sobre_objeto:
                            self.seleccionado = True
                            if self.pieza_foco_id and hasattr(self.objeto_activo, "pieza_seleccionada_id"):
                                self.objeto_activo.pieza_seleccionada_id = self.pieza_foco_id
                        elif self.estado_fsm == "REPOSO":
                            self.seleccionado = False
                            self.pieza_foco_id = None
                            if hasattr(self.objeto_activo, "pieza_seleccionada_id"):
                                self.objeto_activo.pieza_seleccionada_id = None

                    # 2. FSM: Transiciones de estado con histéresis temporal
                    if self.estado_fsm == "REPOSO":
                        # REPOSO: Entrar con pinza abierta dentro del BBox activa HOVER tras 3 frames
                        if sobre_objeto and not pinza_cerrada:
                            self._frames_hover += 1
                            if self._frames_hover >= 3:
                                self.estado_fsm = "HOVER"
                                self._frames_hover = 0
                        else:
                            self._frames_hover = max(0, self._frames_hover - 1)

                        # Si el objeto ya tiene foco y se ejecuta pinza dentro del BBox -> transiciona a AGARRADO
                        if self.seleccionado and sobre_objeto and pinza_cerrada:
                            self._frames_grab += 1
                            if self._frames_grab >= 2:
                                self.estado_fsm = "AGARRADO"
                                self._frames_grab = 0
                                self._escala_grab = float(self.objeto_activo.escala)
                                self._pinch_grab_dist = dist_pinza
                                self.mano_grab_prev_pos = np.array([idx_tip[0], idx_tip[1]], dtype=np.float32)
                                self.pos_personalizada = True
                                es_despiece = (
                                    isinstance(self.objeto_activo, SceneModel)
                                    and bool(self.objeto_activo.piezas)
                                    and (
                                        getattr(self.objeto_activo, "tipo_modelo", "") in ("despiece", "ensamble_mecanico")
                                        or getattr(self.objeto_activo, "factor_explosion", 0.0) > 0.05
                                        or getattr(self.objeto_activo, "es_modelo_anatomico", False)
                                        or (self.pieza_foco_id and self.objeto_activo.esta_desacoplada(self.pieza_foco_id))
                                    )
                                )
                                if es_despiece and self.pieza_foco_id:
                                    self.objeto_activo.desacoplar_pieza(self.pieza_foco_id)
                                    self.modo_manipulacion = "PIEZA"
                                else:
                                    self.modo_manipulacion = "ENSAMBLE"
                        else:
                            if not sobre_objeto or not pinza_cerrada:
                                self._frames_grab = 0

                    elif self.estado_fsm == "HOVER":
                        es_despiece = isinstance(self.objeto_activo, SceneModel) and bool(self.objeto_activo.piezas)
                        if es_despiece and pieza_pick is not None:
                            self.pieza_foco_id = pieza_pick
                            if hasattr(self.objeto_activo, "pieza_seleccionada_id"):
                                self.objeto_activo.pieza_seleccionada_id = pieza_pick

                        # HOVER -> AGARRADO (DRAG): Pinza cerrada estrictamente DENTRO del BBox (2 frames de confirmación)
                        if pinza_cerrada and sobre_objeto:
                            self._frames_grab += 1
                            if self._frames_grab >= 2:
                                self.estado_fsm = "AGARRADO"
                                self.seleccionado = True
                                self._frames_grab = 0
                                self._escala_grab = float(self.objeto_activo.escala)  # Bloqueo rígido de escala en DRAG
                                self._pinch_grab_dist = dist_pinza
                                self.mano_grab_prev_pos = np.array([idx_tip[0], idx_tip[1]], dtype=np.float32)
                                self.pos_personalizada = True

                                # Subfase 2.3: FSM Local vs Global (Desacople de pieza individual tipo LEGO vs Ensamble)
                                es_despiece = (
                                    isinstance(self.objeto_activo, SceneModel)
                                    and bool(self.objeto_activo.piezas)
                                    and (
                                        getattr(self.objeto_activo, "tipo_modelo", "") in ("despiece", "ensamble_mecanico")
                                        or getattr(self.objeto_activo, "factor_explosion", 0.0) > 0.05
                                        or getattr(self.objeto_activo, "es_modelo_anatomico", False)
                                        or (self.pieza_foco_id and self.objeto_activo.esta_desacoplada(self.pieza_foco_id))
                                    )
                                )
                                if es_despiece and self.pieza_foco_id:
                                    self.objeto_activo.desacoplar_pieza(self.pieza_foco_id)
                                    self.modo_manipulacion = "PIEZA"
                                else:
                                    self.modo_manipulacion = "ENSAMBLE"

                        else:
                            self._frames_grab = 0
                            if not sobre_objeto:
                                self._frames_leave += 1
                                if self._frames_leave >= 3:
                                    self.estado_fsm = "REPOSO"
                                    self._frames_leave = 0
                            else:
                                self._frames_leave = 0

                    elif self.estado_fsm == "AGARRADO":
                        self.pos_personalizada = True
                        self.seleccionado = True
                        if pinza_abierta:
                            self._frames_release += 1
                            if self._frames_release >= 2:
                                # SOLTAR (DROP): Mecánica LEGO con una sola mano
                                if isinstance(self.objeto_activo, SceneModel) and self.pieza_foco_id:
                                    p_sel = self.objeto_activo.piezas.get(self.pieza_foco_id)
                                    if p_sel is not None:
                                        rot_m = rotation_matrix(float(self.objeto_activo.rotacion[0]), float(self.objeto_activo.rotacion[1]), float(self.objeto_activo.rotacion[2]))
                                        t_exp = float(self.objeto_activo.factor_explosion)
                                        k_exp = float(self.objeto_activo.k_explosion * self.objeto_activo.escala)
                                        c_loc = self.objeto_activo.centroides_locales.get(self.pieza_foco_id, np.zeros(3, dtype=np.float32))
                                        disp_ancla = rot_m @ (c_loc * (t_exp * k_exp))
                                        pos_ancla_2d = np.array([self.objeto_activo.pos_mundo[0] + disp_ancla[0], self.objeto_activo.pos_mundo[1] + disp_ancla[1]], dtype=np.float32)
                                        pos_pieza_2d = np.array([p_sel.pos_mundo[0], p_sel.pos_mundo[1]], dtype=np.float32)
                                        dist_ancla = float(np.linalg.norm(pos_pieza_2d - pos_ancla_2d))

                                        if dist_ancla < 65.0:
                                            # Snap magnético: encaja de vuelta en su lugar original del motor
                                            self.objeto_activo.reacoplar_pieza(self.pieza_foco_id)
                                            self._reproducir_sonido_snap()
                                            logger.info(f"Snap magnético: pieza {self.pieza_foco_id} reacoplada al motor (dist={dist_ancla:.1f}px < 65px)")
                                        else:
                                            # Se queda flotando donde el usuario la dejó (tipo LEGO)
                                            logger.info(f"Pieza {self.pieza_foco_id} liberada flotando libre (dist={dist_ancla:.1f}px >= 65px)")

                                    self.modo_manipulacion = "ENSAMBLE"
                                    self.pieza_foco_id = None
                                self.estado_fsm = "REPOSO"
                                self.mano_grab_prev_pos = None
                                self._pinch_grab_dist = None
                                self._frames_release = 0
                        else:
                            self._frames_release = 0
                            # Frenado físico instantáneo al agarrar el objeto (Brake)
                            self.vel_yaw = 0.0
                            self.vel_pitch = 0.0
                            if hasattr(self.objeto_activo, "vel_yaw"):
                                self.objeto_activo.vel_yaw = 0.0
                                self.objeto_activo.vel_pitch = 0.0

                            # ARRASTRE EXCLUSIVAMENTE POSICIONAL (Delta DX, Delta DY)
                            curr_pos = np.array([idx_tip[0], idx_tip[1]], dtype=np.float32)
                            if self.mano_grab_prev_pos is not None:
                                delta = curr_pos - self.mano_grab_prev_pos
                                # Si estamos manipulando una pieza desacoplada en modo PIEZA:
                                if (
                                    self.modo_manipulacion == "PIEZA"
                                    and isinstance(self.objeto_activo, SceneModel)
                                    and getattr(self, "pieza_foco_id", None)
                                ):
                                    self.objeto_activo.trasladar_pieza(self.pieza_foco_id, delta)
                                else:
                                    self.objeto_activo.pos_mundo[0] += float(delta[0])
                                    self.objeto_activo.pos_mundo[1] += float(delta[1])
                            self.mano_grab_prev_pos = curr_pos

                            # Escala y rotación estrictamente congeladas durante el arrastre
                            self.objeto_activo.escala = self._escala_grab

                    # 3. Cinemática Libre: Rotación volumétrica continua y Zoom Táctil en el aire
                    # Siempre que la mano tenga la pinza abierta (sin exigir clic previo)
                    puede_interactuar_libre = (
                        not pinza_cerrada
                        and self.estado_fsm != "AGARRADO"
                    )
                    if puede_interactuar_libre:
                        curr_palm = st["smooth_palm"] if st.get("smooth_palm") is not None else palm
                        if self.mano_rot_prev_palm is not None:
                            dx = float(curr_palm[0] - self.mano_rot_prev_palm[0])
                            dy = float(curr_palm[1] - self.mano_rot_prev_palm[1])
                            disp = float(np.hypot(dx, dy))

                            # Rotación reactiva 360° con inercia Mapamundi
                            if disp >= self.deadband_rot_px:
                                vel_inst_yaw = (dx / float(w)) * 18.0
                                vel_inst_pitch = -(dy / float(h)) * 18.0
                                self.vel_yaw = 0.35 * self.vel_yaw + 0.65 * vel_inst_yaw
                                self.vel_pitch = 0.35 * self.vel_pitch + 0.65 * vel_inst_pitch
                                self.objeto_activo.rotacion[0] += self.vel_yaw
                                self.objeto_activo.rotacion[1] += self.vel_pitch
                                if hasattr(self.objeto_activo, "vel_yaw"):
                                    self.objeto_activo.vel_yaw = self.vel_yaw
                                    self.objeto_activo.vel_pitch = self.vel_pitch
                                self._rotacion_aplicada_en_frame = True

                                self.objeto_activo.rotacion[2] = float(self.filter_roll.filter(roll_act))

                        self.mano_rot_prev_palm = curr_palm.copy()

                        # Filtrado de escala con zona muerta estricta (solo si el objeto está seleccionado)
                        if self.seleccionado:
                            ratio_suavizado = float(st.get("smooth_ratio", ratio_pinza))
                            candidata_escala = float(np.clip(ratio_suavizado / 0.70, 0.45, 3.0))
                            delta_s = abs(candidata_escala - self.objeto_activo.escala)
                            if delta_s > self.deadband_escala:
                                if hasattr(self, "filter_escala"):
                                    self.objeto_activo.escala = float(self.filter_escala.filter(candidata_escala))
                                else:
                                    self.objeto_activo.escala = float(
                                        self.alpha_escala * candidata_escala + (1.0 - self.alpha_escala) * self.objeto_activo.escala
                                    )

                            if isinstance(self.objeto_activo, SceneModel):
                                self.objeto_activo._actualizar_posiciones_piezas()
                    else:
                        self.mano_rot_prev_palm = None

                    self._pinza_previa = pinza_cerrada

                    if getattr(self.objeto_activo, "es_modelo_molecular", False) and idx_tip is not None:
                        self.objeto_activo.procesar_interaccion(
                            cursor_pos=idx_tip,
                            pinza_cerrada=pinza_cerrada,
                            flanco_down=(pinza_cerrada and not self._pinza_previa),
                            flanco_up=(not pinza_cerrada and self._pinza_previa),
                        )
                    elif getattr(self.objeto_activo, "es_modelo_superficie", False):
                        self.objeto_activo.procesar_interaccion(
                            cursor_pos=idx_tip,
                            pinza_cerrada=pinza_cerrada,
                            flanco_down=flanco_pinza_down,
                            flanco_up=flanco_pinza_up,
                            ahora=time.time(),
                        )
                    elif getattr(self.objeto_activo, "es_modelo_anatomico", False):
                        self.objeto_activo.procesar_interaccion(
                            cursor_pos=idx_tip,
                            pinza_cerrada=pinza_cerrada,
                            flanco_down=flanco_pinza_down,
                            flanco_up=flanco_pinza_up,
                            ahora=time.time(),
                        )

                fig_activa = st.get("shape", self.web_shape)
                self._sincronizar_figura_activa(fig_activa)

                for et, d in info.items():
                    self.manos_estado[et]["pinch_prev"] = d["pinch"]

            else:
                # Sin manos detectadas: Regla de persistencia inercial absoluta (99.99% confiabilidad)
                if self.estado_fsm in ("AGARRADO", "HOVER"):
                    self.estado_fsm = "REPOSO"
                    self.mano_grab_prev_pos = None
                    self._pinch_grab_dist = None
                self.mano_rot_prev_palm = None
                self._ratio_pinza_prev = None
                self._frames_hover = 0
                self._frames_grab = 0
                self._frames_leave = 0
                self._frames_release = 0
                self._pinza_previa = False
                # Conservación inercial Mapamundi: no resetear vel_yaw/pitch cuando las manos salen de cámara

                # Conserva estrictamente pos_mundo, rotacion y escala sin alterar nada
                fig_activa = self.manos_estado["Right"].get("shape", self.web_shape)
                self._sincronizar_figura_activa(fig_activa)

            # Inercia física estilo Mapamundi (cuando no se está aplicando rotación activa con la mano)
            if self.estado_fsm != "AGARRADO" and not getattr(self, "_rotacion_aplicada_en_frame", False):
                if abs(self.vel_yaw) > 0.0005 or abs(self.vel_pitch) > 0.0005:
                    self.objeto_activo.rotacion[0] += self.vel_yaw
                    self.objeto_activo.rotacion[1] += self.vel_pitch
                    self.vel_yaw *= 0.95
                    self.vel_pitch *= 0.95
                    if hasattr(self.objeto_activo, "vel_yaw"):
                        self.objeto_activo.vel_yaw = self.vel_yaw
                        self.objeto_activo.vel_pitch = self.vel_pitch
                    if isinstance(self.objeto_activo, SceneModel):
                        self.objeto_activo._actualizar_posiciones_piezas()
                else:
                    self.vel_yaw = 0.0
                    self.vel_pitch = 0.0
                    if hasattr(self.objeto_activo, "vel_yaw"):
                        self.objeto_activo.vel_yaw = 0.0
                        self.objeto_activo.vel_pitch = 0.0

            # Renderizado desacoplado mediante BaseRenderer (GPU GlRenderer / CPU CpuRenderer)
            center_render = centro_pantalla if not getattr(self, "pos_personalizada", False) else None
            frame = self.renderer.renderizar_escena(frame, self.objeto_activo, config=self.config, center=center_render)

            # Retroalimentación visual interactiva FSM (BBox AABB / Corner brackets / Estado)
            if getattr(self.objeto_activo, "es_modelo_anatomico", False):
                idx_tip_feed = idx_tip if (manos and len(info) > 0) else None
                frame = self.objeto_activo.dibujar_hud_anatomico(frame, cursor_pos=idx_tip_feed)
            elif getattr(self.objeto_activo, "es_modelo_atomico", False) or getattr(self.objeto_activo, "es_modelo_molecular", False):
                idx_tip_feed = idx_tip if len(info) > 0 else (cursor_pos if cursor_pos is not None else None)
                self.objeto_activo.dibujar_feedback_interaccion(frame, cursor_pos=idx_tip_feed)
            else:
                self._dibujar_feedback_fsm(frame, bbox_actual)

    def dibujar_hud(self, frame: np.ndarray, fps: float) -> np.ndarray:
        """Dibuja en pantalla los datos de telemetría del modo holograma sin solapamientos."""
        h, w = frame.shape[:2]
        cv2.putText(frame, f"FPS: {fps:.1f}", (int(w - 110), 75), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        backend_tag = getattr(self.renderer, "tipo_backend", "CPU")
        cv2.putText(frame, f"Motor: {backend_tag}", (int(w - 240), 120), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 200), 1, cv2.LINE_AA)

        if self.web_active:
            cv2.putText(frame, "MODO TELARANA ACTIVO", (190, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, WEB_COLOR, 2, cv2.LINE_AA)

        cv2.putText(
            frame,
            "L bimanual: Telarana | Pinch: Escalar | [M] Modo | [R] Reset | [Q] Salir",
            (15, int(h - 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA
        )
        return frame
