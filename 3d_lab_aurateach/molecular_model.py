"""
molecular_model.py
-------------------------------------------------------------------
Módulo del Constructor y Simulador Molecular 3D (STARK Mark v3):
- 'ModeloMolecular': Entidad jerárquica compatible con 'SceneModel' y 'BaseRenderer'
  que representa una molécula interactiva en 3D con átomos instanciados y
  enlaces covalentes volumétricos (tubos cilíndricos sólidos).
- Paleta estándar CPK (Corey-Pauling-Koltun) y radios atómicos relativos:
  * Hidrógeno (H): Blanco / Gris muy claro [0.90, 0.90, 0.92], radio r = 0.12
  * Carbono (C): Gris oscuro / Negro grafito [0.20, 0.20, 0.22], radio r = 0.18
  * Oxígeno (O): Rojo intenso [0.90, 0.12, 0.12], radio r = 0.16
  * Nitrógeno (N): Azul intenso [0.15, 0.30, 0.90], radio r = 0.17
- Geometrías moleculares espaciales canónicas:
  * Agua (H2O): Geometría angular a 104.5° (d = 0.96)
  * Dióxido de Carbono (CO2): Geometría lineal a 180° (d = 1.16) con enlaces dobles
  * Metano (CH4): Geometría tetraédrica simétrica 3D a 109.5° (d = 1.09)
  * Amoníaco (NH3): Geometría piramidal trigonal a 107.0° (d = 1.01)
- Soporte para aceleración por hardware ModernGL (GPU Draw Call único para átomos
  y buffer de enlaces con Z-Buffer y sombreado Blinn-Phong).
-------------------------------------------------------------------
"""

import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from hologram import SceneModel, rotation_matrix

logger = logging.getLogger("MolecularEngineSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)

# ====================================================================
# PALETA QUÍMICA CPK Y RADIOS ATÓMICOS RELATIVOS
# ====================================================================

TABLA_CPK: Dict[str, Dict[str, Any]] = {
    "H": {
        "nombre": "Hidrogeno",
        "radio": 0.12,
        "color_rgb": (0.90, 0.90, 0.92),
        "color_bgr": (235, 230, 230),
        "masa": 1.008,
        "valencia": 1,
    },
    "C": {
        "nombre": "Carbono",
        "radio": 0.18,
        "color_rgb": (0.20, 0.20, 0.22),
        "color_bgr": (56, 51, 51),
        "masa": 12.011,
        "valencia": 4,
    },
    "O": {
        "nombre": "Oxigeno",
        "radio": 0.16,
        "color_rgb": (0.90, 0.12, 0.12),
        "color_bgr": (31, 31, 230),
        "masa": 15.999,
        "valencia": 2,
    },
    "N": {
        "nombre": "Nitrogeno",
        "radio": 0.17,
        "color_rgb": (0.15, 0.30, 0.90),
        "color_bgr": (230, 77, 38),
        "masa": 14.007,
        "valencia": 3,
    },
}

RADIO_ENLACE_SIMPLE: float = 0.038
RADIO_ENLACE_DOBLE: float = 0.026
OFFSET_ENLACE_DOBLE: float = 0.045
COLOR_ENLACE_BGR: Tuple[int, int, int] = (200, 205, 215)
COLOR_ENLACE_RGB: Tuple[float, float, float] = (0.78, 0.80, 0.84)


def sanitizar_texto_cv(texto: str) -> str:
    """Reemplaza caracteres no ASCII (acentos, tildes) por sus equivalentes ASCII para cv2.putText."""
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U', '°': ' deg'
    }
    for orig, rep in reemplazos.items():
        texto = texto.replace(orig, rep)
    return texto


def generar_malla_cilindro_entre_puntos(
    p_a: Union[List[float], np.ndarray],
    p_b: Union[List[float], np.ndarray],
    radio: float = 0.038,
    segmentos: int = 16,
    orden: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Genera la geometría 3D completa (vértices y normales normales a la superficie)
    para un cilindro o par de cilindros paralelos (enlaces dobles) entre p_a y p_b.
    Retorna (vertices, normales) con shape (N, 3) y dtype float32.
    """
    p_a = np.asarray(p_a, dtype=np.float32)
    p_b = np.asarray(p_b, dtype=np.float32)
    V = p_b - p_a
    L = float(np.linalg.norm(V))
    if L < 1e-6:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.float32)

    v_hat = V / L
    # Base ortonormal estable sin singularidades en los polos
    if abs(v_hat[2]) < 0.90:
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    else:
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    u_hat = np.cross(v_hat, up)
    norm_u = float(np.linalg.norm(u_hat))
    if norm_u < 1e-6:
        u_hat = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        u_hat = u_hat / norm_u
    w_hat = np.cross(v_hat, u_hat)

    def _generar_tubo_simple(orig: np.ndarray, dest: np.ndarray, r: float) -> Tuple[np.ndarray, np.ndarray]:
        thetas = np.linspace(0, 2.0 * np.pi, segmentos, endpoint=False)
        rad_dirs = np.array([np.cos(t) * u_hat + np.sin(t) * w_hat for t in thetas], dtype=np.float32)
        bottom_pts = orig + r * rad_dirs
        top_pts = dest + r * rad_dirs

        verts: List[np.ndarray] = []
        norms: List[np.ndarray] = []
        for i in range(segmentos):
            nxt = (i + 1) % segmentos
            # Pared lateral del cilindro (2 triángulos por segmento)
            verts.extend([bottom_pts[i], top_pts[i], top_pts[nxt]])
            norms.extend([rad_dirs[i], rad_dirs[i], rad_dirs[nxt]])
            verts.extend([bottom_pts[i], top_pts[nxt], bottom_pts[nxt]])
            norms.extend([rad_dirs[i], rad_dirs[nxt], rad_dirs[nxt]])
            # Tapa inferior
            verts.extend([orig, bottom_pts[nxt], bottom_pts[i]])
            norms.extend([-v_hat, -v_hat, -v_hat])
            # Tapa superior
            verts.extend([dest, top_pts[i], top_pts[nxt]])
            norms.extend([v_hat, v_hat, v_hat])

        return np.array(verts, dtype=np.float32), np.array(norms, dtype=np.float32)

    if orden == 2:
        d_off = OFFSET_ENLACE_DOBLE
        r_sub = radio * 0.72
        v1, n1 = _generar_tubo_simple(p_a + d_off * u_hat, p_b + d_off * u_hat, r_sub)
        v2, n2 = _generar_tubo_simple(p_a - d_off * u_hat, p_b - d_off * u_hat, r_sub)
        return np.vstack([v1, v2]), np.vstack([n1, n2])
    else:
        return _generar_tubo_simple(p_a, p_b, radio)


# ====================================================================
# CLASE PRINCIPAL: MODELO MOLECULAR 3D
# ====================================================================

class ModeloMolecular(SceneModel):
    """
    Entidad jerárquica de ensamble molecular 3D (STARK Molecular Builder):
    - Representa moléculas canónicas (H2O, CO2, CH4, NH3).
    - Admite manipulación inercial con física trackball (vel_yaw, vel_pitch, fricción 0.94).
    - Provee buffers GPU optimizados para instanciación de esferas atómicas y tubos de enlaces.
    - Soporta renderizado holográfico por hardware (ModernGL) y fallback CPU por software.
    """

    def __init__(
        self,
        preset: str = "H2O",
        pos_mundo: Optional[np.ndarray] = None,
        rotacion: Optional[np.ndarray] = None,
        escala: float = 1.0,
        color: Tuple[int, int, int] = (255, 255, 255),
        config: Optional[Union[Dict[str, Any], Any]] = None,
    ):
        super().__init__(
            tipo_modelo="modelo_molecular",
            pos_mundo=pos_mundo,
            rotacion=rotacion,
            escala=escala,
            color=color,
            config=config,
        )
        self.es_modelo_molecular: bool = True
        self.preset_actual: str = str(preset).upper()
        self.version_geometria: int = 1
        self.mostrar_hud: bool = True
        self.base: float = 620.0  # Base canónica idéntica a ModeloAtomico para escala uniforme

        self.atomos: List[Dict[str, Any]] = []
        self.enlaces: List[Dict[str, Any]] = []
        self.info_compuesto: Dict[str, Any] = {}

        # Cachés de buffers GPU
        self._buffer_instancias_cache: Optional[np.ndarray] = None
        self._buffers_enlaces_cache: Optional[Tuple[np.ndarray, np.ndarray]] = None

        # Cooldown y tracking táctil de presets
        self.ultimo_cursor_pos: Optional[Tuple[float, float]] = None
        self._pinza_previa: bool = False
        self.ultimo_clic_preset_tiempo: float = 0.0
        self.rects_botones_presets: Dict[str, Tuple[int, int, int, int]] = {}

        self.cargar_preset(preset)

    # ----------------------------------------------------------------
    # GESTIÓN Y CONSTRUCCIÓN DE PRESETS MOLECULARES
    # ----------------------------------------------------------------

    def cargar_preset(self, nombre: str) -> bool:
        """Carga uno de los presets moleculares rigurosos disponibles."""
        nom = str(nombre).upper().strip()
        if nom in ("H2O", "AGUA", "WATER"):
            self._crear_agua()
        elif nom in ("CO2", "DIOXIDO_CARBONO", "DIOXIDO", "CARBON_DIOXIDE"):
            self._crear_dioxido_carbono()
        elif nom in ("CH4", "METANO", "METHANE"):
            self._crear_metano()
        elif nom in ("NH3", "AMONIACO", "AMMONIA"):
            self._crear_amoniaco()
        else:
            logger.warning(f"Preset molecular '{nombre}' no reconocido. Cargando H2O.")
            self._crear_agua()

        self.preset_actual = str(self.info_compuesto["formula"])
        self.version_geometria += 1
        self._buffer_instancias_cache = None
        self._buffers_enlaces_cache = None
        return True

    def _crear_atomo(self, id_atomo: int, simbolo: str, pos: List[float]) -> Dict[str, Any]:
        """Instancia la estructura de datos interna de un átomo."""
        cpk = TABLA_CPK.get(simbolo, TABLA_CPK["H"])
        return {
            "id": int(id_atomo),
            "simbolo": str(simbolo),
            "pos": np.array(pos, dtype=np.float32),
            "radio": float(cpk["radio"]),
            "color_rgb": tuple(cpk["color_rgb"]),
            "color_bgr": tuple(cpk["color_bgr"]),
            "masa": float(cpk["masa"]),
        }

    def _crear_enlace(self, orig_idx: int, dest_idx: int, orden: int = 1) -> Dict[str, Any]:
        """Instancia la estructura de datos interna de un enlace covalente."""
        p_a = self.atomos[orig_idx]["pos"]
        p_b = self.atomos[dest_idx]["pos"]
        v = p_b - p_a
        longitud = float(np.linalg.norm(v))
        orientacion = (v / longitud).astype(np.float32) if longitud > 1e-6 else np.array([0.0, 0.0, 1.0], dtype=np.float32)
        return {
            "origen_idx": int(orig_idx),
            "destino_idx": int(dest_idx),
            "orden": int(orden),
            "longitud": longitud,
            "orientacion": orientacion,
        }

    def _crear_agua(self) -> None:
        """
        Preset Agua (H2O):
        - Átomo central: Oxígeno en [0, 0, 0].
        - 2 Hidrógenos con longitud d = 0.96 y ángulo de enlace exacto de 104.5° en XY.
        - x = +/- d * sin(52.25°), y = -d * cos(52.25°), z = 0.
        """
        d = 0.96
        theta = np.radians(52.25)
        h1_x = float(d * np.sin(theta))
        h1_y = float(-d * np.cos(theta))
        h2_x = float(-d * np.sin(theta))
        h2_y = float(-d * np.cos(theta))

        self.atomos = [
            self._crear_atomo(0, "O", [0.0, 0.0, 0.0]),
            self._crear_atomo(1, "H", [h1_x, h1_y, 0.0]),
            self._crear_atomo(2, "H", [h2_x, h2_y, 0.0]),
        ]
        self.enlaces = [
            self._crear_enlace(0, 1, orden=1),
            self._crear_enlace(0, 2, orden=1),
        ]
        self.info_compuesto = {
            "formula": "H2O",
            "nombre": "Agua",
            "geometria": "Angular (104.5 deg)",
            "masa_molar": "18.015 g/mol",
            "descripcion": "Solvente polar universal (puentes de hidrogeno)",
            "angulo": 104.5,
            "distancia": 0.96,
        }

    def _crear_dioxido_carbono(self) -> None:
        """
        Preset Dióxido de Carbono (CO2):
        - Átomo central: Carbono en [0, 0, 0].
        - 2 Oxígenos colineales a 180° sobre el eje X a distancia d = 1.16.
        - Enlaces dobles (orden = 2) representados por cilindros gemelos paralelos.
        """
        d = 1.16
        self.atomos = [
            self._crear_atomo(0, "C", [0.0, 0.0, 0.0]),
            self._crear_atomo(1, "O", [+d, 0.0, 0.0]),
            self._crear_atomo(2, "O", [-d, 0.0, 0.0]),
        ]
        self.enlaces = [
            self._crear_enlace(0, 1, orden=2),
            self._crear_enlace(0, 2, orden=2),
        ]
        self.info_compuesto = {
            "formula": "CO2",
            "nombre": "Dioxido de Carbono",
            "geometria": "Lineal (180.0 deg)",
            "masa_molar": "44.010 g/mol",
            "descripcion": "Gas apolar con enlaces dobles covalentes C=O",
            "angulo": 180.0,
            "distancia": 1.16,
        }

    def _crear_metano(self) -> None:
        """
        Preset Metano (CH4):
        - Átomo central: Carbono en [0, 0, 0].
        - 4 Hidrógenos en simetría tetraédrica canónica tridimensional:
          H1: [+s, +s, +s], H2: [-s, -s, +s], H3: [-s, +s, -s], H4: [+s, -s, -s]
          con d = 1.09 (s = d / sqrt(3)), ángulo de enlace 109.5° (arccos(-1/3)).
        """
        d = 1.09
        s = float(d / np.sqrt(3.0))
        self.atomos = [
            self._crear_atomo(0, "C", [0.0, 0.0, 0.0]),
            self._crear_atomo(1, "H", [+s, +s, +s]),
            self._crear_atomo(2, "H", [-s, -s, +s]),
            self._crear_atomo(3, "H", [-s, +s, -s]),
            self._crear_atomo(4, "H", [+s, -s, -s]),
        ]
        self.enlaces = [
            self._crear_enlace(0, 1, orden=1),
            self._crear_enlace(0, 2, orden=1),
            self._crear_enlace(0, 3, orden=1),
            self._crear_enlace(0, 4, orden=1),
        ]
        self.info_compuesto = {
            "formula": "CH4",
            "nombre": "Metano",
            "geometria": "Tetraedrica (109.5 deg)",
            "masa_molar": "16.043 g/mol",
            "descripcion": "Hidrocarburo alcano con hibridacion sp3 perfecta",
            "angulo": 109.5,
            "distancia": 1.09,
        }

    def _crear_amoniaco(self) -> None:
        """
        Preset Amoníaco (NH3):
        - Átomo central: Nitrógeno en [0, 0, 0.20].
        - 3 Hidrógenos en geometría piramidal trigonal (ángulo ~107.0°, d = 1.01).
        """
        d_xy = 0.94
        z_h = -0.37
        angles = [0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0]
        self.atomos = [
            self._crear_atomo(0, "N", [0.0, 0.0, 0.20]),
        ]
        for idx, ang in enumerate(angles):
            hx = float(d_xy * np.cos(ang))
            hy = float(d_xy * np.sin(ang))
            self.atomos.append(self._crear_atomo(idx + 1, "H", [hx, hy, z_h]))
        self.enlaces = [
            self._crear_enlace(0, 1, orden=1),
            self._crear_enlace(0, 2, orden=1),
            self._crear_enlace(0, 3, orden=1),
        ]
        self.info_compuesto = {
            "formula": "NH3",
            "nombre": "Amoniaco",
            "geometria": "Piramidal Trigonal (107.0 deg)",
            "masa_molar": "17.031 g/mol",
            "descripcion": "Base debil con par de electrones libre",
            "angulo": 107.0,
            "distancia": 1.01,
        }

    # ----------------------------------------------------------------
    # BUFFERS DE GPU PARA INSTANCIACIÓN Y ENLACES
    # ----------------------------------------------------------------

    def obtener_buffer_instancias_gpu(self) -> np.ndarray:
        """
        Retorna la matriz de datos de instancia para los átomos de la molécula.
        Shape: (num_atomos, 7), dtype: float32.
        Columnas: [pos_x, pos_y, pos_z, color_r, color_g, color_b, radio].
        """
        if self._buffer_instancias_cache is not None:
            return self._buffer_instancias_cache

        filas = []
        for at in self.atomos:
            p = at["pos"]
            c = at["color_rgb"]
            r = at["radio"]
            filas.append([float(p[0]), float(p[1]), float(p[2]), float(c[0]), float(c[1]), float(c[2]), float(r)])

        self._buffer_instancias_cache = np.array(filas, dtype=np.float32)
        return self._buffer_instancias_cache

    def obtener_buffers_enlaces_gpu(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Genera y retorna los buffers consolidados de vértices y normales para todos los
        tubos cilíndricos de los enlaces covalentes.
        Retorna: (vertices, normales) de shape (V_total, 3) y dtype float32.
        """
        if self._buffers_enlaces_cache is not None:
            return self._buffers_enlaces_cache

        all_verts: List[np.ndarray] = []
        all_norms: List[np.ndarray] = []

        for enl in self.enlaces:
            p_a = self.atomos[enl["origen_idx"]]["pos"]
            p_b = self.atomos[enl["destino_idx"]]["pos"]
            orden = enl["orden"]
            r_enlace = RADIO_ENLACE_SIMPLE if orden == 1 else RADIO_ENLACE_DOBLE
            v, n = generar_malla_cilindro_entre_puntos(p_a, p_b, radio=r_enlace, segmentos=16, orden=orden)
            if len(v) > 0:
                all_verts.append(v)
                all_norms.append(n)

        if all_verts:
            res_v = np.vstack(all_verts).astype(np.float32)
            res_n = np.vstack(all_norms).astype(np.float32)
        else:
            res_v = np.empty((0, 3), dtype=np.float32)
            res_n = np.empty((0, 3), dtype=np.float32)

        self._buffers_enlaces_cache = (res_v, res_n)
        return self._buffers_enlaces_cache

    # ----------------------------------------------------------------
    # BBOX 2D Y COLISIÓN ESPACIAL (HCI)
    # ----------------------------------------------------------------

    def calcular_aabb_2d(
        self,
        center: Optional[Tuple[float, float]] = None,
        pad: int = 20,
    ) -> Tuple[int, int, int, int]:
        """Calcula el Bounding Box 2D proyectado de la molécula en la pantalla."""
        cx = float(center[0]) if center is not None else float(self.pos_mundo[0])
        cy = float(center[1]) if center is not None else float(self.pos_mundo[1])

        R = rotation_matrix(*self.rotacion)
        f_scale = float(self.base * self.escala)
        d_cam = 4.0

        pts_x = []
        pts_y = []

        for at in self.atomos:
            p_rot = R @ at["pos"]
            z_eff = max(float(p_rot[2] + d_cam), 0.1)
            f_z = f_scale / z_eff
            px = cx + f_z * p_rot[0]
            py = cy - f_z * p_rot[1]
            pr = f_z * at["radio"]

            pts_x.extend([px - pr, px + pr])
            pts_y.extend([py - pr, py + pr])

        if not pts_x:
            return (int(round(cx - pad)), int(round(cy - pad)), int(round(cx + pad)), int(round(cy + pad)))

        return (
            int(round(min(pts_x) - pad)),
            int(round(min(pts_y) - pad)),
            int(round(max(pts_x) + pad)),
            int(round(max(pts_y) + pad)),
        )

    def contiene_punto(
        self,
        punto: Tuple[float, float],
        center: Optional[Tuple[float, float]] = None,
        pad: int = 20,
    ) -> bool:
        """Determina si un punto en pantalla (ej. cursor de la mano) intersecta la molécula."""
        x1, y1, x2, y2 = self.calcular_aabb_2d(center=center, pad=pad)
        return bool(x1 <= punto[0] <= x2 and y1 <= punto[1] <= y2)

    # ----------------------------------------------------------------
    # RENDERIZADO FALLBACK CPU (ALGORITMO DEL PINTOR)
    # ----------------------------------------------------------------

    def renderizar(
        self,
        frame: np.ndarray,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Renderizado en CPU por software cuando OpenGL no está disponible:
        Proyecta esferas atómicas y cilindros de enlace respetando Z-sorting.
        """
        cx = float(center[0]) if center is not None else float(self.pos_mundo[0])
        cy = float(center[1]) if center is not None else float(self.pos_mundo[1])

        R = rotation_matrix(*self.rotacion)
        f_scale = float(self.base * self.escala)
        d_cam = 4.0

        atom_proy = []
        for idx, at in enumerate(self.atomos):
            p_rot = R @ at["pos"]
            z_eff = max(float(p_rot[2] + d_cam), 0.1)
            f_z = f_scale / z_eff
            px = int(round(cx + f_z * p_rot[0]))
            py = int(round(cy - f_z * p_rot[1]))
            pr = max(int(round(f_z * at["radio"])), 3)
            atom_proy.append({
                "idx": idx,
                "z": float(p_rot[2]),
                "px": px,
                "py": py,
                "pr": pr,
                "at": at,
            })

        items_render = []
        for enl in self.enlaces:
            a0 = atom_proy[enl["origen_idx"]]
            a1 = atom_proy[enl["destino_idx"]]
            z_avg = (a0["z"] + a1["z"]) * 0.5
            items_render.append(("enlace", z_avg, enl, a0, a1))

        for a in atom_proy:
            items_render.append(("atomo", a["z"], a))

        items_render.sort(key=lambda item: item[1])

        for item in items_render:
            if item[0] == "enlace":
                _, _, enl, a0, a1 = item
                p0 = (int(round(a0["px"])), int(round(a0["py"])))
                p1 = (int(round(a1["px"])), int(round(a1["py"])))
                orden = enl["orden"]
                col_bond = COLOR_ENLACE_BGR

                if orden == 2:
                    dx = float(p1[0] - p0[0])
                    dy = float(p1[1] - p0[1])
                    L = max(math.hypot(dx, dy), 1e-4)
                    ux = -dy / L * 5.0
                    uy = dx / L * 5.0
                    pt0_a = (int(round(p0[0] + ux)), int(round(p0[1] + uy)))
                    pt1_a = (int(round(p1[0] + ux)), int(round(p1[1] + uy)))
                    pt0_b = (int(round(p0[0] - ux)), int(round(p0[1] - uy)))
                    pt1_b = (int(round(p1[0] - ux)), int(round(p1[1] - uy)))
                    cv2.line(frame, pt0_a, pt1_a, col_bond, 3, cv2.LINE_AA)
                    cv2.line(frame, pt0_b, pt1_b, col_bond, 3, cv2.LINE_AA)
                else:
                    cv2.line(frame, p0, p1, col_bond, 5, cv2.LINE_AA)
            else:
                _, _, a = item
                pt = (int(round(a["px"])), int(round(a["py"])))
                pr = int(round(a["pr"]))
                col_bgr = a["at"]["color_bgr"]
                cv2.circle(frame, pt, pr, col_bgr, -1, cv2.LINE_AA)
                cv2.circle(frame, pt, pr, (30, 30, 35), 1, cv2.LINE_AA)
                hl_pt = (int(round(pt[0] - pr * 0.32)), int(round(pt[1] - pr * 0.32)))
                hl_r = max(int(round(pr * 0.28)), 1)
                cv2.circle(frame, hl_pt, hl_r, (255, 255, 255), -1, cv2.LINE_AA)

        if self.mostrar_hud:
            self.dibujar_hud_molecular(frame, cursor_pos=self.ultimo_cursor_pos)

        return frame

    # ----------------------------------------------------------------
    # HUD CONTEXTUAL MOLECULAR Y SELECTOR TÁCTIL
    # ----------------------------------------------------------------

    def dibujar_hud_molecular(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """Dibuja la tarjeta holográfica Sci-Fi flotante con datos del compuesto y botones interactivos."""
        if not self.mostrar_hud:
            return frame

        h, w = frame.shape[:2]
        self.ultimo_cursor_pos = cursor_pos

        card_w = 330
        card_h = 220
        card_x = int(w - card_w - 30)
        card_y = 100

        # Fondo translúcido Sci-Fi oscuro sobre ROI local (sin clonar frame completo)
        rx1, ry1 = max(0, card_x), max(0, card_y)
        rx2, ry2 = min(w, card_x + card_w), min(h, card_y + card_h)
        if rx2 > rx1 and ry2 > ry1:
            sub = frame[ry1:ry2, rx1:rx2]
            bg_box = np.full_like(sub, (18, 20, 26))
            cv2.addWeighted(bg_box, 0.78, sub, 0.22, 0, sub)

        # Marco holográfico cian neón
        col_cyan = (0, 240, 255)
        cv2.rectangle(
            frame,
            (card_x, card_y),
            (card_x + card_w, card_y + card_h),
            col_cyan,
            1,
            cv2.LINE_AA,
        )

        # Esquinas Sci-Fi angulares
        corner_len = 14
        for cx_c, cy_c in [
            (card_x, card_y),
            (card_x + card_w, card_y),
            (card_x, card_y + card_h),
            (card_x + card_w, card_y + card_h),
        ]:
            sx = 1 if cx_c == card_x else -1
            sy = 1 if cy_c == card_y else -1
            cv2.line(frame, (cx_c, cy_c), (cx_c + sx * corner_len, cy_c), (50, 255, 120), 2, cv2.LINE_AA)
            cv2.line(frame, (cx_c, cy_c), (cx_c, cy_c + sy * corner_len), (50, 255, 120), 2, cv2.LINE_AA)

        # Encabezado
        cv2.putText(
            frame,
            "STARK MOLECULAR BUILDER",
            (card_x + 16, card_y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            col_cyan,
            1,
            cv2.LINE_AA,
        )
        cv2.line(frame, (card_x + 16, card_y + 32), (card_x + card_w - 16, card_y + 32), (0, 150, 180), 1, cv2.LINE_AA)

        # Datos del compuesto químico
        info = self.info_compuesto
        formula = str(info.get("formula", self.preset_actual))
        nombre = sanitizar_texto_cv(str(info.get("nombre", "Compuesto")))
        geometria = sanitizar_texto_cv(str(info.get("geometria", "")))
        masa = str(info.get("masa_molar", ""))

        cv2.putText(
            frame,
            formula,
            (card_x + 18, card_y + 68),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.05,
            (50, 255, 120),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"- {nombre.upper()}",
            (card_x + 115, card_y + 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"Geometria: {geometria}",
            (card_x + 18, card_y + 98),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (200, 220, 240),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Masa Molar: {masa}",
            (card_x + 18, card_y + 122),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (200, 220, 240),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Atomos: {len(self.atomos)} | Enlaces: {len(self.enlaces)}",
            (card_x + 18, card_y + 146),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (0, 215, 255),
            1,
            cv2.LINE_AA,
        )

        # Botones interactivos de Presets
        presets = [("H2O", "1"), ("CO2", "2"), ("CH4", "3"), ("NH3", "4")]
        btn_w = 66
        btn_h = 28
        btn_spacing = 8
        start_bx = card_x + 18
        start_by = card_y + 168

        self.rects_botones_presets.clear()

        for idx, (p_name, tecla) in enumerate(presets):
            bx = start_bx + idx * (btn_w + btn_spacing)
            by = start_by
            rect = (bx, by, bx + btn_w, by + btn_h)
            self.rects_botones_presets[p_name] = rect

            is_active = (self.preset_actual == p_name)
            is_hover = False
            if cursor_pos is not None:
                cx_cur, cy_cur = cursor_pos
                if bx <= cx_cur <= bx + btn_w and by <= cy_cur <= by + btn_h:
                    is_hover = True

            if is_active:
                cv2.rectangle(frame, (bx, by), (bx + btn_w, by + btn_h), (50, 255, 120), -1, cv2.LINE_AA)
                cv2.putText(
                    frame,
                    f"[{p_name}]",
                    (bx + 8, by + 19),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (15, 20, 25),
                    2,
                    cv2.LINE_AA,
                )
            else:
                col_btn = (0, 240, 255) if is_hover else (0, 140, 180)
                thick = 2 if is_hover else 1
                cv2.rectangle(frame, (bx, by), (bx + btn_w, by + btn_h), col_btn, thick, cv2.LINE_AA)
                cv2.putText(
                    frame,
                    f"[{p_name}]",
                    (bx + 8, by + 19),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    (220, 220, 220) if not is_hover else (0, 240, 255),
                    1,
                    cv2.LINE_AA,
                )

        return frame

    def detectar_clic_preset(self, x: float, y: float) -> Optional[str]:
        """Verifica si las coordenadas (x, y) caen dentro de un botón de preset."""
        for p_name, (bx1, by1, bx2, by2) in self.rects_botones_presets.items():
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                return p_name
        return None

    def actualizar(self, *args: Any, **kwargs: Any) -> None:
        """Actualiza estados dinamicos del modelo molecular."""
        pass

    def liberar(self) -> None:
        """Libera de forma limpia recursos del modelo molecular."""
        pass

    def procesar_interaccion(
        self,
        cursor_pos: Optional[Tuple[float, float]],
        pinza_cerrada: bool = False,
        flanco_down: bool = False,
        flanco_up: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Procesa gestos táctiles para cambio de presets por contacto con el índice."""
        if cursor_pos is None:
            return {"evento": "NINGUNO"}

        cx, cy = cursor_pos
        self.ultimo_cursor_pos = cursor_pos

        if flanco_down or (pinza_cerrada and not self._pinza_previa):
            ahora = time.time()
            if ahora - self.ultimo_clic_preset_tiempo > 0.25:
                p_clicked = self.detectar_clic_preset(cx, cy)
                if p_clicked is not None:
                    self.ultimo_clic_preset_tiempo = ahora
                    self.cargar_preset(p_clicked)
                    self._pinza_previa = pinza_cerrada
                    return {"evento": "CAMBIO_PRESET", "preset": p_clicked}

        self._pinza_previa = pinza_cerrada
        return {"evento": "NINGUNO"}

    def dibujar_feedback_interaccion(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """Retroalimentación de interfaz durante la manipulación táctil."""
        if self.mostrar_hud:
            self.dibujar_hud_molecular(frame, cursor_pos=cursor_pos)
        return frame

