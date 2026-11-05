"""
gestures.py
-------------------------------------------------------------------
Módulo de visión por computador y análisis de gestos con MediaPipe Tasks API.
Refactorizado para máxima precisión ("filo filo"):
- Invarianza por escala y corrección de anisotropía 4:3 (soporte para pts en px y lm).
- Schmitt Trigger (bi-estable) con histéresis estricta para clics y pinzas.
- Disambiguación rigurosa entre PAZ (estático) y SCROLL (desplazamiento vertical |Δy| > deadzone).
- Seguimiento de velocidad de scroll dependiente de Δt y escala normalizada de palma d_ref.
- Lógica estricta de exclusión mutua para Clic Izquierdo, Clic Derecho y Agarre.
- Histéresis temporal (> 0.35s) para Puño (Minimizar) y Mano Abierta (Maximizar).
- Temporizador de debounce / cooldown (0.3s) entre clics para suprimir rebotes.
- Paridad de tipos int en OpenCV y cero excepciones silenciosas.
-------------------------------------------------------------------
"""

import logging
import math
import os
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import mediapipe as mp
import numpy as np

from config import (
    DEFAULT_CONFIG,
    HAND_MODEL_PATH,
    HAND_MODEL_URL,
    POSE_MODEL_PATH,
    POSE_MODEL_URL,
)
from filters import BancoLandmarksFilter, LandmarkPoint

# Configuración de logging para el módulo
logger = logging.getLogger("GesturesSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)

# Estructuras base de MediaPipe Tasks
BaseOptions = mp.tasks.BaseOptions
VisionRunningMode = mp.tasks.vision.RunningMode
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions

# Conexiones esqueléticas estándar de la mano en MediaPipe (21 landmarks)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

# Estilo visual de anotación para cada mano (formato BGR nativo de OpenCV)
STYLE = {
    "Left": {"color": (255, 220, 60), "name": "IZQUIERDA"},   # BGR: Cian brillante
    "Right": {"color": (60, 160, 255), "name": "DERECHA"},    # BGR: Naranja cálido
}

# Índices de articulaciones de brazos en MediaPipe Pose: (hombro, codo, muñeca)
POSE_BRAZOS = [(11, 13, 15), (12, 14, 16)]


def asegurar_modelo(ruta: str, url: str, nombre: str) -> None:
    """Descarga el modelo de MediaPipe correspondiente si no existe en el disco."""
    if not os.path.exists(ruta):
        logger.info(f"Descargando modelo de {nombre} (descarga única inicial)...")
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        try:
            urllib.request.urlretrieve(url, ruta)
            logger.info(f"Modelo {nombre} descargado con éxito en: {ruta}")
        except Exception as e:
            logger.error(f"Error al descargar modelo {nombre} desde {url}: {e}")
            raise


def crear_detector_manos(config: Optional[Union[Dict[str, Any], Any]] = None) -> HandLandmarker:
    """Crea e inicializa la instancia de HandLandmarker en modo VIDEO."""
    asegurar_modelo(HAND_MODEL_PATH, HAND_MODEL_URL, "manos")
    cfg = config or {}
    min_det = float(cfg.get("min_deteccion_confianza", 0.50))
    min_track = float(cfg.get("min_seguimiento_confianza", 0.50))
    min_pres = float(cfg.get("min_presencia_confianza", 0.50))

    opciones = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=HAND_MODEL_PATH),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=min_det,
        min_hand_presence_confidence=min_pres,
        min_tracking_confidence=min_track,
    )
    return HandLandmarker.create_from_options(opciones)


def crear_detector_pose(config: Optional[Union[Dict[str, Any], Any]] = None) -> Optional[PoseLandmarker]:
    """Crea e inicializa PoseLandmarker de forma tolerante a fallos."""
    try:
        asegurar_modelo(POSE_MODEL_PATH, POSE_MODEL_URL, "pose")
        cfg = config or {}
        min_det = float(cfg.get("min_deteccion_pose", 0.5))
        min_track = float(cfg.get("min_seguimiento_pose", 0.5))

        opciones = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=POSE_MODEL_PATH),
            running_mode=VisionRunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_det,
            min_pose_presence_confidence=min_det,
            min_tracking_confidence=min_track,
        )
        return PoseLandmarker.create_from_options(opciones)
    except Exception as e:
        logger.warning(f"No se pudo iniciar Pose ({e}). El sistema continuará sin telemetría de antebrazo.")
        return None


_bancos_landmarks_manos: Dict[str, Dict[str, BancoLandmarksFilter]] = {
    "Left": {
        "pts": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
        "norm": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
    },
    "Right": {
        "pts": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
        "norm": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
    },
}


def extraer_manos(resultado: Any, w: int, h: int) -> Dict[str, Dict[str, Any]]:
    """
    Extrae y clasifica los landmarks detectados para ambas manos de forma blindada contra excepciones.
    Soporta Tasks API (hand_landmarks) y estructuras compatibles.
    Devuelve: {"Left" / "Right": {"lm": landmarks_normalizados, "pts": np.ndarray(21, 2) en px HD}}.
    """
    global _bancos_landmarks_manos
    if not resultado:
        for b in _bancos_landmarks_manos.values():
            if isinstance(b, dict):
                b["pts"].reset()
                b["norm"].reset()
            else:
                b.reset()
        return {}

    try:
        hand_lms_list = getattr(resultado, "hand_landmarks", None) or getattr(resultado, "multi_hand_landmarks", None)
        if not hand_lms_list:
            return {}

        handedness_list = getattr(resultado, "handedness", None) or getattr(resultado, "multi_handedness", None)

        detectadas = []
        for i, lms in enumerate(hand_lms_list):
            try:
                items = lms.landmark if hasattr(lms, "landmark") else lms
                if items is None or len(items) < 21:
                    continue
                etiqueta = "Right"
                if handedness_list and i < len(handedness_list):
                    h_item = handedness_list[i]
                    if hasattr(h_item, "classification") and len(h_item.classification) > 0:
                        etiqueta = h_item.classification[0].label
                    elif isinstance(h_item, (list, tuple)) and len(h_item) > 0:
                        etiqueta = getattr(h_item[0], "category_name", getattr(h_item[0], "label", "Right"))

                pts = np.array([[float(l.x) * w, float(l.y) * h] for l in items], dtype=np.float32)
                if etiqueta not in _bancos_landmarks_manos:
                    _bancos_landmarks_manos[etiqueta] = {
                        "pts": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
                        "norm": BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True),
                    }
                if bool(DEFAULT_CONFIG.get("suavizar_landmarks_crudos", True)):
                    pts = _bancos_landmarks_manos[etiqueta]["pts"].filter_pts(pts)
                    items = _bancos_landmarks_manos[etiqueta]["norm"].filter_landmarks(items)

                detectadas.append([etiqueta, items, pts])
            except Exception as e_item:
                logger.debug(f"Error procesando mano individual: {e_item}")

        # Si ambas manos llegan etiquetadas igual (caso raro), resolver por posición horizontal X
        if len(detectadas) == 2 and detectadas[0][0] == detectadas[1][0]:
            detectadas.sort(key=lambda d: d[2][:, 0].mean())
            detectadas[0][0], detectadas[1][0] = "Left", "Right"

        return {e: {"lm": lm_norm, "pts": pts} for e, lm_norm, pts in detectadas}
    except Exception as e:
        logger.warning(f"Error en extraer_manos: {e}")
        return {}


def draw_skeleton(frame: np.ndarray, pts: np.ndarray, color: Tuple[int, int, int]) -> None:
    """Dibuja el esqueleto de articulaciones y líneas de una mano sobre el frame con casting int y protección."""
    if pts is None or len(pts) < 21:
        return
    try:
        for a, b in HAND_CONNECTIONS:
            if a < len(pts) and b < len(pts):
                pt_a = (int(round(pts[a][0])), int(round(pts[a][1])))
                pt_b = (int(round(pts[b][0])), int(round(pts[b][1])))
                cv2.line(frame, pt_a, pt_b, color, 1, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, (int(round(p[0])), int(round(p[1]))), 2, color, -1, cv2.LINE_AA)
    except (IndexError, TypeError, ValueError, cv2.error) as e:
        logger.debug(f"Aviso de geometría en draw_skeleton: {e}")
    except Exception as e:
        logger.warning(f"Error inesperado en draw_skeleton: {e}", exc_info=True)


def dibujar_manos(
    frame: np.ndarray,
    manos: Dict[str, Dict[str, Any]],
    etiqueta_mouse: Optional[str] = None,
) -> None:
    """Superpone los esqueletos y etiquetas identificadoras de las manos en pantalla de forma crash-proof."""
    if not manos:
        return
    try:
        for etiqueta, datos in manos.items():
            pts = datos.get("pts")
            if pts is None or len(pts) < 21:
                continue
            color = STYLE.get(etiqueta, {}).get("color", (0, 255, 0))
            draw_skeleton(frame, pts, color)
            p = pts[[0, 5, 9, 13, 17]].mean(axis=0)
            p_x = int(round(p[0]))
            p_y = int(round(p[1]))
            nombre = STYLE.get(etiqueta, {}).get("name", etiqueta)
            if etiqueta == etiqueta_mouse:
                nombre += " [MOUSE]"
            cv2.putText(
                frame, nombre, (p_x - 40, p_y + 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA
            )
    except Exception as e:
        logger.debug(f"Error en dibujar_manos: {e}")


def elegir_mano_mouse(manos: Dict[str, Dict[str, Any]], mano_config: Optional[str] = None) -> Optional[str]:
    """Selecciona la mano que tendrá el control del cursor según la configuración."""
    if mano_config in ("Left", "Right"):
        return mano_config if mano_config in manos else None
    if "Right" in manos:
        return "Right"
    if "Left" in manos:
        return "Left"
    return None


def distancia(p1: Any, p2: Any) -> float:
    """Calcula la distancia euclidiana entre dos puntos normalizados (x, y)."""
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def razon_extension(lm: Any, pip_idx: int, tip_idx: int, wrist_idx: int = 0) -> float:
    """Calcula la proporción entre distancia (muñeca -> punta) y (muñeca -> articulación PIP)."""
    wrist = lm[wrist_idx]
    dist_pip = max(distancia(wrist, lm[pip_idx]), 1e-6)
    dist_tip = distancia(wrist, lm[tip_idx])
    return dist_tip / dist_pip


def dedo_extendido(
    lm: Any,
    mcp_idx: Optional[int],
    pip_idx: int,
    tip_idx: int,
    wrist_idx: int = 0,
    umbral: float = 1.15,
) -> bool:
    """
    Verifica si un dedo específico se encuentra extendido usando landmarks normalizados.
    Combina la proporción de extensión respecto a muñeca con validación anatómica
    respecto a la articulación base MCP si se proporciona (LOW-05).
    """
    if mcp_idx is not None and mcp_idx >= 0:
        d_mcp_tip = distancia(lm[mcp_idx], lm[tip_idx])
        d_mcp_pip = distancia(lm[mcp_idx], lm[pip_idx])
        if d_mcp_tip < d_mcp_pip * 0.90:
            return False
    return razon_extension(lm, pip_idx, tip_idx, wrist_idx) > umbral


def _dedo_extendido_pts(pts: np.ndarray, tip: int, pip: int, wrist_idx: int = 0, umbral: float = 1.05) -> bool:
    """Verifica si un dedo está extendido usando puntos en píxeles (invariante a distorsión de aspecto)."""
    wrist = pts[wrist_idx]
    norm_tip = float(np.linalg.norm(pts[tip] - wrist))
    norm_pip = max(float(np.linalg.norm(pts[pip] - wrist)), 1e-4)
    return norm_tip > umbral * norm_pip


# ====================================================================
# CLASIFICADOR DE GESTOS CON MÁXIMA PRECISIÓN ("FILO FILO") Y SCROLL
# ====================================================================

class LandmarkPoint:
    """Representación normalizada de landmark para puntero con filtrado ponderado."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __getitem__(self, item: int) -> float:
        return (self.x, self.y, self.z)[item]

    def __repr__(self) -> str:
        return f"LandmarkPoint(x={self.x:.4f}, y={self.y:.4f}, z={self.z:.4f})"


class ClasificadorGestosPrecision:
    """
    Clasificador avanzado de gestos manuales con:
    - Normalización geométrica invariante a escala d_ref y corrección de anisotropía 4:3.
    - Schmitt Triggers para pinzas (histéresis de dos umbrales estables).
    - Disambiguación entre PAZ (dos dedos estáticos) y SCROLL (movimiento vertical dinámico).
    - Cálculo de velocidad de scroll dependiente de Delta-t.
    - Exclusión mutua entre clics, agarres y scroll.
    - Temporizadores de debouncing (cooldown) y persistencia temporal.
    """

    COOLDOWN_CLIC: float = 0.30        # Segundos de inmunidad entre clics consecutivos
    TIEMPO_CONFIRMAR_VENTANAS: float = 0.35  # Segundos continuos para maximizar / minimizar

    def __init__(self) -> None:
        self.ultimo_clic_tiempo: float = -999.0
        self.tiempo_inicio_puno: Optional[float] = None
        self.tiempo_inicio_abierta: Optional[float] = None
        self.disparado_puno: bool = False
        self.disparado_abierta: bool = False

        # Schmitt Trigger bi-estable para pinzas
        self.pinza_izq_activa: bool = False
        self.pinza_der_activa: bool = False

        # Estado dinámico del Gesto de Scroll con tracking temporal
        self.scroll_y_prev: Optional[float] = None
        self.scroll_t_prev: Optional[float] = None
        self.en_scroll_activo: bool = False

        # Bancos de filtros separados para suavizado anti-temblor de los 21 landmarks (Fase 9)
        # banco_norm para coordenadas normalizadas (0..1) y banco_pts para píxeles (0..W, 0..H)
        self.banco_norm = BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True)
        self.banco_pts = BancoLandmarksFilter(min_cutoff=0.8, beta=0.02, diferenciado=True)
        self._ancla_preclic: Optional[Tuple[float, float, float]] = None
        self._ancla_preclic_pts: Optional[Tuple[float, float]] = None

    @property
    def banco_landmarks(self) -> BancoLandmarksFilter:
        return self.banco_norm

    @banco_landmarks.setter
    def banco_landmarks(self, val: BancoLandmarksFilter) -> None:
        self.banco_norm = val

    def reset(self) -> None:
        """Reinicia los contadores y temporizadores internos."""
        self.tiempo_inicio_puno = None
        self.tiempo_inicio_abierta = None
        self.disparado_puno = False
        self.disparado_abierta = False
        self.pinza_izq_activa = False
        self.pinza_der_activa = False
        self.scroll_y_prev = None
        self.scroll_t_prev = None
        self.en_scroll_activo = False
        self.banco_norm.reset()
        self.banco_pts.reset()
        self._ancla_preclic = None
        self._ancla_preclic_pts = None

    @staticmethod
    def _gesto_por_defecto() -> Dict[str, Any]:
        return {
            "gesto_bruto": "NEUTRO",
            "es_clic_izquierdo": False,
            "es_clic_derecho": False,
            "es_agarrar": False,
            "es_puno": False,
            "es_mano_abierta": False,
            "es_paz": False,
            "es_scroll": False,
            "scroll_arriba": False,
            "scroll_abajo": False,
            "scroll_velocidad": 0.0,
            "en_scroll": False,
            "scroll_y": None,
            "d_ref": 1.0,
            "dist_pulgar_indice": 1.0,
            "dist_pulgar_medio": 1.0,
            "dist_pulgar_anular": 1.0,
            "dist_pulgar_menique": 1.0,
            "dist_indice_medio": 1.0,
            "pinch_agarrar": 1.0,
            "pinch_click_derecho": 1.0,
            "index_ext": True,
            "middle_ext": False,
            "ring_ext": False,
            "pinky_ext": False,
            "thumb_ext": False,
            "index_tip": None,
            "x_raw": 0.0,
            "y_raw": 0.0,
            "muneca_x": 0.0,
            "rotacion_muneca": 0.0,
        }

    def clasificar(
        self,
        lm: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        ahora: Optional[float] = None,
        pts: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Analiza los 21 landmarks de la mano y determina el gesto con precisión quirúrgica.
        Soporta entrada de puntos de píxeles HD (pts) para evitar anisotropía 4:3.
        """
        if ahora is None:
            ahora = time.time()
        cfg = config or {}

        try:
            if (pts is None or len(pts) < 21) and (lm is None or len(lm) < 21):
                return self._gesto_por_defecto()

            # Suavizado en clasificador opcional (en el pipeline STARK principal se realiza en extraer_manos)
            if bool(cfg.get("suavizar_en_clasificador", False)):
                mc = float(cfg.get("lm_filter_min_cutoff", 0.08))
                beta = float(cfg.get("lm_filter_beta", 0.04))
                d_cut = float(cfg.get("lm_filter_d_cutoff", 1.0))
                self.banco_norm.min_cutoff = mc
                self.banco_norm.beta = beta
                self.banco_norm.d_cutoff = d_cut
                self.banco_pts.min_cutoff = mc
                self.banco_pts.beta = beta
                self.banco_pts.d_cutoff = d_cut
                if pts is not None and len(pts) >= 21:
                    pts = self.banco_pts.filter_pts(pts, timestamp=ahora)
                if lm is not None and len(lm) >= 21:
                    lm = self.banco_norm.filter_landmarks(lm, timestamp=ahora)

            # 1. Distancias euclidianas normalizadas por tamaño de palma (LM 0 a LM 9)
            if pts is not None and len(pts) >= 21:
                d_ref = float(np.linalg.norm(pts[0] - pts[9]))
                d_ref = max(d_ref, 1e-4)

                dist_pulgar_indice = float(np.linalg.norm(pts[4] - pts[8])) / d_ref
                dist_pulgar_medio = float(np.linalg.norm(pts[4] - pts[12])) / d_ref
                dist_pulgar_anular = float(np.linalg.norm(pts[4] - pts[16])) / d_ref
                dist_pulgar_menique = float(np.linalg.norm(pts[4] - pts[20])) / d_ref
                dist_indice_medio = float(np.linalg.norm(pts[8] - pts[12])) / d_ref

                umbral_ext = float(cfg.get("umbral_dedo_extendido", 1.08))
                index_ext = _dedo_extendido_pts(pts, 8, 6, 0, umbral=umbral_ext)
                middle_ext = _dedo_extendido_pts(pts, 12, 10, 0, umbral=umbral_ext)
                ring_ext = _dedo_extendido_pts(pts, 16, 14, 0, umbral=umbral_ext)
                pinky_ext = _dedo_extendido_pts(pts, 20, 18, 0, umbral=umbral_ext)

                dist_pulgar_palma = float(np.linalg.norm(pts[4] - pts[5])) / d_ref
                thumb_ext = dist_pulgar_palma > 0.65
            else:
                d_ref = max(distancia(lm[0], lm[9]), 1e-4)
                dist_pulgar_indice = distancia(lm[4], lm[8]) / d_ref
                dist_pulgar_medio = distancia(lm[4], lm[12]) / d_ref
                dist_pulgar_anular = distancia(lm[4], lm[16]) / d_ref
                dist_pulgar_menique = distancia(lm[4], lm[20]) / d_ref
                dist_indice_medio = distancia(lm[8], lm[12]) / d_ref

                umbral_ext = float(cfg.get("umbral_dedo_extendido", 1.15))
                index_ext = dedo_extendido(lm, 5, 6, 8, umbral=umbral_ext)
                middle_ext = dedo_extendido(lm, 9, 10, 12, umbral=umbral_ext)
                ring_ext = dedo_extendido(lm, 13, 14, 16, umbral=umbral_ext)
                pinky_ext = dedo_extendido(lm, 17, 18, 20, umbral=umbral_ext)

                dist_pulgar_palma = distancia(lm[4], lm[5]) / d_ref
                thumb_ext = dist_pulgar_palma > 0.65

            # 2. Umbrales de Schmitt Trigger para Clics / Pinzas (0.23 / 0.31)
            umbral_clic_izq_cerrar = float(cfg.get("agarrar_cerrar", 0.23))
            umbral_clic_izq_liberar = float(cfg.get("agarrar_liberar", 0.31))
            umbral_clic_der_cerrar = float(cfg.get("click_derecho_cerrar", 0.23))
            umbral_clic_der_liberar = float(cfg.get("click_derecho_liberar", 0.31))

            # AGARRAR / DRAG: Tanto Índice como Medio están pinchados al Pulgar
            cond_agarrar = (dist_pulgar_indice < 0.22) and (dist_pulgar_medio < 0.22)

            # Schmitt Trigger para Pinza Izquierda (Índice - Pulgar)
            if dist_pulgar_indice < umbral_clic_izq_cerrar:
                self.pinza_izq_activa = True
            elif dist_pulgar_indice > umbral_clic_izq_liberar:
                self.pinza_izq_activa = False

            # Schmitt Trigger para Pinza Derecha (Medio - Pulgar)
            if dist_pulgar_medio < umbral_clic_der_cerrar:
                self.pinza_der_activa = True
            elif dist_pulgar_medio > umbral_clic_der_liberar:
                self.pinza_der_activa = False

            # Exclusión mutua estricta de clics
            cond_clic_izq = self.pinza_izq_activa and (dist_pulgar_medio > umbral_clic_izq_liberar) and not cond_agarrar
            cond_clic_der = self.pinza_der_activa and (dist_pulgar_indice > umbral_clic_der_liberar) and not cond_agarrar

            # Debounce / Cooldown e inmunidad a disparos involuntarios repetitivos
            es_clic_izquierdo = False
            es_clic_derecho = False

            cooldown_clicks = float(cfg.get("cooldown_clicks", self.COOLDOWN_CLIC))
            if ahora - self.ultimo_clic_tiempo >= cooldown_clicks:
                if cond_clic_izq:
                    es_clic_izquierdo = True
                    self.ultimo_clic_tiempo = ahora
                elif cond_clic_der:
                    es_clic_derecho = True
                    self.ultimo_clic_tiempo = ahora

            # 3. GESTO DE SCROLL VS PAZ:
            # Condición anatómica de dos dedos extendidos (Índice + Medio, Anular + Meñique doblados):
            postura_dos_dedos = (
                index_ext
                and middle_ext
                and (not ring_ext)
                and (not pinky_ext)
                and (dist_indice_medio < 0.85)
                and (not cond_agarrar)
                and (not self.pinza_izq_activa)
                and (not self.pinza_der_activa)
            )

            scroll_arriba = False
            scroll_abajo = False
            scroll_velocidad = 0.0
            en_scroll = False

            deadzone_px = float(cfg.get("wb_scroll_deadzone", 15.0))
            sensibilidad = float(cfg.get("wb_scroll_sensibilidad", 20.0))

            if postura_dos_dedos:
                # Centroide vertical de las yemas de índice y medio
                if pts is not None and len(pts) >= 21:
                    c_y = float((pts[8][1] + pts[12][1]) / 2.0)
                    # Escalar deadzone con tamaño relativo de la mano d_ref = norm(pts[0] - pts[9])
                    deadzone_efectiva = deadzone_px * (d_ref / 120.0)
                else:
                    c_y = float((lm[8].y + lm[12].y) / 2.0 * 720.0)
                    deadzone_efectiva = deadzone_px * (d_ref / 120.0) if d_ref > 1.0 else deadzone_px

                dt_scroll = (ahora - self.scroll_t_prev) if self.scroll_t_prev is not None else 0.0

                if self.scroll_y_prev is None or dt_scroll > 0.45 or dt_scroll < 1e-4:
                    self.scroll_y_prev = c_y
                    self.scroll_t_prev = ahora
                    delta_y = 0.0
                else:
                    delta_y = c_y - self.scroll_y_prev

                # DISAMBIGUACIÓN:
                # Si el desplazamiento vertical supera la zona muerta |Delta y| > deadzone => SCROLL DINÁMICO
                # Si permanece en reposo relativo => SEÑAL DE PAZ ESTÁTICA
                if abs(delta_y) > deadzone_efectiva:
                    en_scroll = True
                    dt_eff = max(dt_scroll, 0.01)
                    desplazamiento_neto = abs(delta_y) - deadzone_efectiva

                    if delta_y < -deadzone_efectiva:
                        scroll_arriba = True
                        scroll_abajo = False
                        # Velocidad dependiente de Delta-t
                        scroll_velocidad = float((desplazamiento_neto / 10.0) * (sensibilidad / 10.0) * (0.033 / dt_eff) * 120.0)
                    else:
                        scroll_abajo = True
                        scroll_arriba = False
                        scroll_velocidad = -float((desplazamiento_neto / 10.0) * (sensibilidad / 10.0) * (0.033 / dt_eff) * 120.0)

                    self.scroll_y_prev = c_y
                    self.scroll_t_prev = ahora
                    self.en_scroll_activo = True
                else:
                    # Estático: mantener ancla pero no activar scroll
                    en_scroll = False
                    scroll_arriba = False
                    scroll_abajo = False
                    scroll_velocidad = 0.0
                    self.en_scroll_activo = False
            else:
                self.scroll_y_prev = None
                self.scroll_t_prev = None
                self.en_scroll_activo = False

            # 4. Gestos de postura manual (Puño, Mano Abierta, Trípode, Paz, Apuntar)
            es_puno_raw = not (index_ext or middle_ext or ring_ext or pinky_ext)
            es_mano_abierta_raw = thumb_ext and index_ext and middle_ext and ring_ext and pinky_ext

            # Persistencia temporal (> 0.35s) para minimizar / maximizar
            es_puno_confirmado = False
            if es_puno_raw:
                if self.tiempo_inicio_puno is None:
                    self.tiempo_inicio_puno = ahora
                elif (ahora - self.tiempo_inicio_puno >= self.TIEMPO_CONFIRMAR_VENTANAS) and not self.disparado_puno:
                    es_puno_confirmado = True
                    self.disparado_puno = True
            else:
                self.tiempo_inicio_puno = None
                self.disparado_puno = False

            es_mano_abierta_confirmada = False
            if es_mano_abierta_raw:
                if self.tiempo_inicio_abierta is None:
                    self.tiempo_inicio_abierta = ahora
                elif (ahora - self.tiempo_inicio_abierta >= self.TIEMPO_CONFIRMAR_VENTANAS) and not self.disparado_abierta:
                    es_mano_abierta_confirmada = True
                    self.disparado_abierta = True
            else:
                self.tiempo_inicio_abierta = None
                self.disparado_abierta = False

            tripode = index_ext and middle_ext and ring_ext and not pinky_ext
            paz = postura_dos_dedos and not en_scroll
            apuntar = index_ext and not middle_ext and not ring_ext and not pinky_ext

            # Determinación semántica de 'gesto_bruto' con prioridad jerárquica
            if cond_agarrar:
                gesto_bruto = "AGARRAR"
            elif es_clic_izquierdo or self.pinza_izq_activa:
                gesto_bruto = "CLIC_IZQUIERDO"
            elif es_clic_derecho or self.pinza_der_activa:
                gesto_bruto = "CLIC_DERECHO"
            elif en_scroll:
                gesto_bruto = "SCROLL"
            elif es_puno_raw:
                gesto_bruto = "PUNO"
            elif es_mano_abierta_raw:
                gesto_bruto = "MANO_ABIERTA"
            elif paz:
                gesto_bruto = "PAZ"
            elif tripode:
                gesto_bruto = "TRIPODE"
            elif apuntar:
                gesto_bruto = "APUNTAR"
            else:
                gesto_bruto = "NEUTRO"

            # Rotación angular de la muñeca (Roll relativo a la vertical)
            if pts is not None and len(pts) >= 21:
                dx = float(pts[9][0] - pts[0][0])
                dy = float(pts[9][1] - pts[0][1])
                rotacion_muneca = math.degrees(math.atan2(dx, -dy))
                muneca_x = float(pts[0][0])
            else:
                dx = float(lm[9].x - lm[0].x)
                dy = float(lm[9].y - lm[0].y)
                rotacion_muneca = math.degrees(math.atan2(dx, -dy))
                muneca_x = float(lm[0].x)

            # Filtrado de Ruido Óptico en Landmarks (Media Ponderada LM8 70% + LM7 30%) y Ancla Pre-Clic
            if lm is not None and len(lm) > 8:
                lm8 = lm[8]
                lm7 = lm[7] if len(lm) > 7 else lm8
                x_raw = float(lm8.x) * 0.7 + float(lm7.x) * 0.3
                y_raw = float(lm8.y) * 0.7 + float(lm7.y) * 0.3
                z_raw = float(getattr(lm8, "z", 0.0)) * 0.7 + float(getattr(lm7, "z", 0.0)) * 0.3
                
                # Ancla pre-clic: cuando la pinza pulgar-índice baja de 0.28, congelar rígidamente
                # el ancla de interacción para eliminar micro-tirones y lograr clics quirúrgicos
                if dist_pulgar_indice < 0.28 and len(lm) > 4:
                    if self._ancla_preclic is None:
                        lm4 = lm[4]
                        w_t = 0.50
                        ax = x_raw * (1.0 - w_t) + float(lm4.x) * w_t
                        ay = y_raw * (1.0 - w_t) + float(lm4.y) * w_t
                        az = z_raw * (1.0 - w_t) + float(getattr(lm4, "z", 0.0)) * w_t
                        self._ancla_preclic = (ax, ay, az)
                    x_raw, y_raw, z_raw = self._ancla_preclic
                else:
                    self._ancla_preclic = None

                index_tip = LandmarkPoint(x_raw, y_raw, z_raw)
            elif pts is not None and len(pts) > 8:
                x_raw = float(pts[8][0]) * 0.7 + float(pts[7][0]) * 0.3
                y_raw = float(pts[8][1]) * 0.7 + float(pts[7][1]) * 0.3
                if dist_pulgar_indice < 0.28 and len(pts) > 4:
                    if self._ancla_preclic_pts is None:
                        w_t = 0.50
                        ax = x_raw * (1.0 - w_t) + float(pts[4][0]) * w_t
                        ay = y_raw * (1.0 - w_t) + float(pts[4][1]) * w_t
                        self._ancla_preclic_pts = (ax, ay)
                    x_raw, y_raw = self._ancla_preclic_pts
                else:
                    self._ancla_preclic_pts = None
                index_tip = LandmarkPoint(x_raw / 1280.0, y_raw / 720.0, 0.0)
            else:
                index_tip = None
                x_raw, y_raw = 0.0, 0.0

            return {
                # Banderas de control de alta precisión
                "gesto_bruto": gesto_bruto,
                "es_clic_izquierdo": es_clic_izquierdo,
                "es_clic_derecho": es_clic_derecho,
                "es_agarrar": cond_agarrar,
                "es_puno": es_puno_confirmado,
                "es_mano_abierta": es_mano_abierta_confirmada,
                "es_paz": paz,
                "es_scroll": en_scroll,
                # GESTO DE SCROLL
                "scroll_arriba": scroll_arriba,
                "scroll_abajo": scroll_abajo,
                "scroll_velocidad": scroll_velocidad,
                "en_scroll": en_scroll,
                "scroll_y": self.scroll_y_prev,
                # Distancias normalizadas e invariantes por escala
                "d_ref": d_ref,
                "dist_pulgar_indice": dist_pulgar_indice,
                "dist_pulgar_medio": dist_pulgar_medio,
                "dist_pulgar_anular": dist_pulgar_anular,
                "dist_pulgar_menique": dist_pulgar_menique,
                "dist_indice_medio": dist_indice_medio,
                # Compatibilidad exacta con mouse_controller.py y hologram.py
                "pinch_agarrar": dist_pulgar_indice,
                "pinch_click_derecho": dist_pulgar_medio,
                "index_ext": index_ext,
                "middle_ext": middle_ext,
                "ring_ext": ring_ext,
                "pinky_ext": pinky_ext,
                "thumb_ext": thumb_ext,
                "index_tip": index_tip,
                "x_raw": x_raw,
                "y_raw": y_raw,
                "muneca_x": muneca_x,
                "rotacion_muneca": rotacion_muneca,
            }
        except (IndexError, TypeError, ValueError, AttributeError) as e:
            logger.debug(f"Aviso de landmarks en clasificar gesto: {e}")
            return self._gesto_por_defecto()
        except Exception as e:
            logger.warning(f"Excepción inesperada en clasificar gesto: {e}", exc_info=True)
            return self._gesto_por_defecto()


# Instancia singleton global para invocación funcional directa.
# _clasificador_lock garantiza exclusión mutua ante acceso desde hilos concurrentes
# (hilo principal de MediaPipe + hilo de cámara ThreadedCamera).
# Se usa RLock para permitir re-entrada desde el mismo hilo sin dead-lock.
_clasificador_global = ClasificadorGestosPrecision()
_clasificador_lock = threading.RLock()


def clasificar_gesto(
    lm: Any,
    config: Optional[Union[Dict[str, Any], Any]] = None,
    ahora: Optional[float] = None,
    pts: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Función de clasificación compatible con todos los módulos existentes.
    Utiliza internamente el clasificador de alta precisión con cooldown, Schmitt triggers e invariancia.
    Thread-safe: protegida por RLock para acceso concurrente seguro desde cualquier hilo.
    """
    with _clasificador_lock:
        return _clasificador_global.clasificar(lm, config=config, ahora=ahora, pts=pts)


def analizar_antebrazo(
    resultados_pose: Any,
    muneca_mano: Any,
    umbral_visibilidad: float = 0.5,
) -> Optional[Dict[str, Any]]:
    """Enlaza la pose corporal con la mano detectada para medir la inclinación del antebrazo."""
    if resultados_pose is None or not getattr(resultados_pose, "pose_landmarks", None):
        return None

    lm = resultados_pose.pose_landmarks[0]
    mejor = None
    mejor_dist = None

    for hombro_idx, codo_idx, muneca_idx in POSE_BRAZOS:
        hombro, codo, muneca = lm[hombro_idx], lm[codo_idx], lm[muneca_idx]
        if any((getattr(p, "visibility", 0.0) or 0.0) < umbral_visibilidad for p in (hombro, codo, muneca)):
            continue

        dist = math.hypot(muneca.x - muneca_mano.x, muneca.y - muneca_mano.y)
        if mejor_dist is None or dist < mejor_dist:
            mejor_dist = dist
            mejor = (hombro, codo, muneca)

    if mejor is None:
        return None

    hombro, codo, muneca = mejor
    dx = muneca.x - codo.x
    dy = muneca.y - codo.y
    angulo_antebrazo = math.degrees(math.atan2(dx, -dy))

    return {
        "angulo_antebrazo": angulo_antebrazo,
        "hombro": (hombro.x, hombro.y),
        "codo": (codo.x, codo.y),
        "muneca": (muneca.x, muneca.y),
    }


def is_L_gesture(pts: np.ndarray) -> bool:
    """Verifica si la mano forma una letra 'L' para activar el modo telaraña."""
    palm_size = max(float(np.linalg.norm(pts[0] - pts[9])), 1.0)

    index_ext = _dedo_extendido_pts(pts, 8, 6)
    middle_fold = not _dedo_extendido_pts(pts, 12, 10)
    ring_fold = not _dedo_extendido_pts(pts, 16, 14)
    pinky_fold = not _dedo_extendido_pts(pts, 20, 18)
    thumb_ext = float(np.linalg.norm(pts[4] - pts[5])) > 0.7 * palm_size

    if not (index_ext and middle_fold and ring_fold and pinky_fold and thumb_ext):
        return False

    v_thumb = pts[4] - pts[2]
    v_index = pts[8] - pts[5]
    norm_prod = float(np.linalg.norm(v_thumb) * np.linalg.norm(v_index) + 1e-6)
    cosang = float(np.dot(v_thumb, v_index) / norm_prod)
    angle = np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))
    return 45.0 <= angle <= 135.0


def l_points(pts: np.ndarray) -> List[np.ndarray]:
    """Obtiene los 3 vértices clave de la 'L': esquina (base), punta de pulgar y punta de índice."""
    corner = (pts[2] + pts[5]) / 2.0
    return [corner, pts[4], pts[8]]


# ====================================================================
# GESTOR DE ANCLAJE BIOMECÁNICO DE MANOS (HAND LOCK Y ANTI-SWAPPING)
# ====================================================================

class HandLockManager:
    """
    Gestor de Anclaje Biomecánico de Manos (Hand Lock), HUD en Palmas y Anti-Swapping:
    - Escaneo progresivo de 30 fotogramas (~1s) con anillo dinámico y texto [ 0% ] a [ 100% ].
    - Anclaje biométrico de identidad ('Left', 'Right') con halos de confirmación verde/azul.
    - Algoritmo Anti-Cruce: Resolución de asignación por matriz de distancias mínimas entre la
      posición anterior y la actual para evitar que las manos intercambien identidades al cruzarse.
    - Filtrado de Fondo: Rechazo automático de detecciones que excedan el umbral de distancia
      máxima con respecto a las manos ancladas (inmunidad contra personas en el fondo).
    - Blindaje Crash-Proof total con try/except defensivo.
    """

    def __init__(self, max_frames_escaneo: int = 30, umbral_dist_max: float = 280.0) -> None:
        self.max_frames_escaneo: int = max_frames_escaneo
        self.umbral_dist_max: float = float(umbral_dist_max)
        self.escaneando: bool = False
        self.frames_escaneo: int = 0
        self.manos_bloqueadas: bool = False
        self.anclas_pos: Dict[str, np.ndarray] = {}
        self.ultimas_pos: Dict[str, np.ndarray] = {}
        self.notif_mensaje: str = ""
        self.notif_tiempo: float = -999.0
        self.duracion_notif: float = 2.5

    def iniciar_escaneo(self) -> None:
        """Inicia o reinicia el escaneo progresivo para anclar manos."""
        self.escaneando = True
        self.frames_escaneo = 0
        self.manos_bloqueadas = False
        self.anclas_pos.clear()
        self.ultimas_pos.clear()
        self.notif_mensaje = "Iniciando escaneo de palmas..."
        self.notif_tiempo = time.time()
        logger.info("HandLockManager: Iniciando escaneo progresivo de manos (30 fotogramas).")

    def liberar_bloqueo(self) -> None:
        """Libera el anclaje de manos y vuelve al modo libre."""
        self.escaneando = False
        self.frames_escaneo = 0
        self.manos_bloqueadas = False
        self.anclas_pos.clear()
        self.ultimas_pos.clear()
        self.notif_mensaje = "[Bloqueo de Manos Liberado]"
        self.notif_tiempo = time.time()
        logger.info("HandLockManager: Bloqueo de manos liberado.")

    def toggle_lock(self, manos_detectadas: Optional[Dict[str, Any]] = None) -> bool:
        """Alterna entre escaneo/bloqueo y liberación."""
        if self.manos_bloqueadas or self.escaneando:
            self.liberar_bloqueo()
            return False
        else:
            self.iniciar_escaneo()
            return True

    @staticmethod
    def obtener_centro_palma(pts: np.ndarray) -> np.ndarray:
        """Calcula el centro geométrico de la palma con validación defensiva."""
        try:
            if pts is not None and len(pts) >= 21:
                # Centroide de la base de la palma (Landmark 0) y nudillos (5, 9, 13, 17)
                return pts[[0, 5, 9, 13, 17]].mean(axis=0)
            elif pts is not None and len(pts) > 0:
                return pts.mean(axis=0)
        except Exception as e:
            logger.debug(f"obtener_centro_palma: Aviso al calcular centroide: {e}")
        return np.array([0.0, 0.0], dtype=np.float32)

    def filtrar_y_emparejar_manos(
        self,
        manos_detectadas: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aplica el Algoritmo Anti-Cruce y Filtrado de Fondo cuando manos_bloqueadas == True:
        1. Resuelve asignación óptima por mínima distancia euclidiana entre posiciones anteriores y candidatas.
        2. Descarta detecciones a distancia > umbral_dist_max para ignorar personas en el fondo.
        """
        if not self.manos_bloqueadas or not self.ultimas_pos:
            return manos_detectadas

        if not manos_detectadas:
            return {}

        try:
            candidatos = list(manos_detectadas.values())
            centros_cand = [self.obtener_centro_palma(c["pts"]) for c in candidatos]

            manos_asignadas: Dict[str, Dict[str, Any]] = {}

            # Caso 1 mano anclada
            if len(self.ultimas_pos) == 1:
                etiqueta, p_ant = list(self.ultimas_pos.items())[0]
                dists = [float(np.linalg.norm(c - p_ant)) for c in centros_cand]
                mejor_idx = int(np.argmin(dists))
                if dists[mejor_idx] <= self.umbral_dist_max:
                    manos_asignadas[etiqueta] = candidatos[mejor_idx]
                    self.ultimas_pos[etiqueta] = centros_cand[mejor_idx]
                return manos_asignadas

            # Caso 2 o más manos ancladas
            etiquetas_ancla = list(self.ultimas_pos.keys())
            p_ant_0 = self.ultimas_pos[etiquetas_ancla[0]]
            p_ant_1 = self.ultimas_pos[etiquetas_ancla[1]]

            if len(candidatos) == 1:
                c0 = centros_cand[0]
                d0 = float(np.linalg.norm(c0 - p_ant_0))
                d1 = float(np.linalg.norm(c0 - p_ant_1))
                if d0 <= d1 and d0 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[0]] = candidatos[0]
                    self.ultimas_pos[etiquetas_ancla[0]] = c0
                elif d1 < d0 and d1 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[1]] = candidatos[0]
                    self.ultimas_pos[etiquetas_ancla[1]] = c0
                return manos_asignadas

            # Al menos 2 candidatos: comparar permutaciones de asignación
            # Permutación A: cand 0 -> ancla 0, cand 1 -> ancla 1
            d_00 = float(np.linalg.norm(centros_cand[0] - p_ant_0))
            d_11 = float(np.linalg.norm(centros_cand[1] - p_ant_1))
            coste_A = d_00 + d_11

            # Permutación B: cand 1 -> ancla 0, cand 0 -> ancla 1
            d_10 = float(np.linalg.norm(centros_cand[1] - p_ant_0))
            d_01 = float(np.linalg.norm(centros_cand[0] - p_ant_1))
            coste_B = d_10 + d_01

            if coste_A <= coste_B:
                if d_00 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[0]] = candidatos[0]
                    self.ultimas_pos[etiquetas_ancla[0]] = centros_cand[0]
                if d_11 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[1]] = candidatos[1]
                    self.ultimas_pos[etiquetas_ancla[1]] = centros_cand[1]
            else:
                if d_10 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[0]] = candidatos[1]
                    self.ultimas_pos[etiquetas_ancla[0]] = centros_cand[1]
                if d_01 <= self.umbral_dist_max:
                    manos_asignadas[etiquetas_ancla[1]] = candidatos[0]
                    self.ultimas_pos[etiquetas_ancla[1]] = centros_cand[0]

            return manos_asignadas

        except Exception as e:
            logger.warning(f"Error en algoritmo anti-cruce de manos: {e}")
            return manos_detectadas

    def actualizar(
        self,
        manos_detectadas: Dict[str, Dict[str, Any]],
        ahora: float,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Actualiza el ciclo de escaneo progresivo o filtra por anclaje biomecánico.
        Devuelve el diccionario de manos correspondientes.
        """
        try:
            if self.escaneando:
                if manos_detectadas:
                    self.frames_escaneo += 1
                    if self.frames_escaneo >= self.max_frames_escaneo:
                        # 100% completado -> Anclaje de Identidad
                        self.escaneando = False
                        self.manos_bloqueadas = True
                        self.anclas_pos.clear()
                        self.ultimas_pos.clear()
                        for etq, d in list(manos_detectadas.items())[:2]:
                            c = self.obtener_centro_palma(d["pts"])
                            self.anclas_pos[etq] = c.copy()
                            self.ultimas_pos[etq] = c.copy()
                        self.notif_mensaje = "[Manos Registradas y Bloqueadas]"
                        self.notif_tiempo = ahora
                        logger.info("HandLockManager: [Manos Registradas y Bloqueadas] (100% completado).")
                return manos_detectadas

            if self.manos_bloqueadas:
                return self.filtrar_y_emparejar_manos(manos_detectadas)

            return manos_detectadas
        except Exception as e:
            logger.warning(f"Error en actualización de HandLockManager: {e}")
            return manos_detectadas

    def dibujar_hud_palmas(
        self,
        frame: np.ndarray,
        manos_render: Dict[str, Dict[str, Any]],
        ahora: float,
    ) -> np.ndarray:
        """
        Dibuja los anillos de escaneo progresivo [ 0% ] .. [ 100% ] y
        los halos de confirmación de Hand Lock centrado sobre las palmas.
        """
        try:
            # 1. Modo Escaneo Progresivo (0 - 100%)
            if self.escaneando and manos_render:
                progreso = min(1.0, max(0.0, self.frames_escaneo / float(self.max_frames_escaneo)))
                pct = int(progreso * 100)
                texto_pct = f"[ {pct}% ]"

                for etq, d in list(manos_render.items())[:2]:
                    pts = d.get("pts")
                    if pts is None or len(pts) < 21:
                        continue
                    c = self.obtener_centro_palma(pts)
                    cx, cy = int(round(c[0])), int(round(c[1]))

                    # Anillo exterior de escaneo
                    cv2.circle(frame, (cx, cy), 34, (0, 220, 255), 2, cv2.LINE_AA)
                    # Arco / Círculo interior dinámico
                    r_din = max(4, int(34 * progreso))
                    cv2.circle(frame, (cx, cy), r_din, (0, 255, 255), 1, cv2.LINE_AA)
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 255), -1, cv2.LINE_AA)

                    # Texto dinámico progresivo centrado sobre la palma
                    (tw, th), _ = cv2.getTextSize(texto_pct, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                    cv2.putText(
                        frame, texto_pct, (cx - tw // 2, cy + 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2, cv2.LINE_AA
                    )

            # 2. Modo Manos Bloqueadas (Halo de confirmación Verde/Azul)
            elif self.manos_bloqueadas and manos_render:
                for etq, d in manos_render.items():
                    pts = d.get("pts")
                    if pts is None or len(pts) < 21:
                        continue
                    c = self.obtener_centro_palma(pts)
                    cx, cy = int(round(c[0])), int(round(c[1]))

                    color_lock = (50, 255, 120) if etq == "Right" else (255, 220, 60)
                    cv2.circle(frame, (cx, cy), 28, color_lock, 2, cv2.LINE_AA)
                    cv2.circle(frame, (cx, cy), 4, color_lock, -1, cv2.LINE_AA)

                    txt_l = f"[LOCKED: {etq}]"
                    (tw, th), _ = cv2.getTextSize(txt_l, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                    cv2.putText(
                        frame, txt_l, (cx - tw // 2, cy + 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, color_lock, 1, cv2.LINE_AA
                    )

            # 3. Notificación temporal de bloqueo / desbloqueo
            if (ahora - self.notif_tiempo < self.duracion_notif) and self.notif_mensaje:
                h, w = frame.shape[:2]
                (tw, th), _ = cv2.getTextSize(self.notif_mensaje, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                mx = int((w - tw) // 2)
                my = int(h // 2 - 120)
                sub_roi = frame[max(0, my - th - 10):min(h, my + 10), max(0, mx - 14):min(w, mx + tw + 14)]
                if sub_roi.size > 0:
                    overlay = sub_roi.copy()
                    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], overlay.shape[0]), (20, 24, 30), -1)
                    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], overlay.shape[0]), (50, 255, 120), 1, cv2.LINE_AA)
                    cv2.addWeighted(overlay, 0.85, sub_roi, 0.15, 0, sub_roi)
                cv2.putText(frame, self.notif_mensaje, (mx, my), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 255, 120), 2, cv2.LINE_AA)

        except Exception as e:
            logger.warning(f"Error renderizando HUD de palmas: {e}")

        return frame
