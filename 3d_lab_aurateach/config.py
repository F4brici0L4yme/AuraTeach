"""
config.py
-------------------------------------------------------------------
Módulo de Configuración Centralizada, Persistencia Atómica y Hot-Reload:
- DEFAULT_CONFIG completo y exhaustivo (~55 parámetros).
- HotConfig con hilo de vigilancia en caliente (daemon), recarga sin
  pérdida de referencias en memoria y acceso directo estilo diccionario.
- Validación de consistencia geométrica (Schmitt Triggers: cerrar < liberar).
- Helper atómico centralizado con tempfile y os.replace para blindaje contra fallos de energía.
-------------------------------------------------------------------
"""

import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Dict, Iterator, Optional, Union

import numpy as np

# Configuración de Logging para el módulo
logger = logging.getLogger("ConfigSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Rutas de los modelos de MediaPipe Tasks
HAND_MODEL_PATH = os.path.join(BASE_DIR, "hand_landmarker.task")
POSE_MODEL_PATH = os.path.join(BASE_DIR, "pose_landmarker_lite.task")

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)

# Diccionario maestro de configuración con valores por defecto óptimos
DEFAULT_CONFIG: Dict[str, Any] = {
    # --- Modos de inicio y control ---
    "modo_inicial": "PIZARRA",           # "PIZARRA", "MOUSE" o "HOLOGRAMA"
    "mano_mouse": None,                  # "Right", "Left", o None (automático)

    # --- Cámara y visualización (Arquitectura Tri-Cámara) ---
    "fuente_camara": None,               # None para webcam local o URL HTTP/RTSP
    "cam_index": 0,                      # Índice de webcam local (Cámara 1 Frontal)
    "cam_docente_frontal": 0,            # Cámara 1: Docente Frontal (Plano X, Y)
    "cam_docente_cenital": 1,            # Cámara 2: Docente Cenital / Lateral 90° (Plano X, Z)
    "cam_aula_alumnos": 2,               # Cámara 3: Aula Estudiantes (On-Demand)
    "dual_cam_orthogonal": True,         # Fusión Ortogonal Cruzada activa
    "aula_on_demand": True,              # Monitoreo de aula bajo demanda (0% CPU/GPU por defecto)
    "cam_width": 640,
    "cam_height": 480,
    "escala_ventana": 1.25,              # Escala visual del frame en pantalla
    "pantalla_ancho": 960,               # Resolución horizontal recomendada (960x720 ágil)
    "pantalla_alto": 720,                # Resolución vertical recomendada (960x720 ágil)
    "fullscreen": False,                 # Ventana ágil y ligera sin forzar fullscreen pesado
    "fps_captura": 30,
    "cam_mjpg": True,                    # Formato MJPG en UVC para alta tasa de cuadros sostenida
    "fallback_local": True,              # Conmutar a webcam local si falla stream de red

    # --- Robustez de red (ESP32-S3 / Stream IP) ---
    "url_esp32_defecto": "http://192.168.4.1:81/stream",
    "max_fallos_lectura_seguidos": 60,
    "intentos_abrir_stream_red": 5,
    "espera_entre_intentos_red": 1.0,
    "max_reconexiones_seguidas": 10,
    "timeout_lectura_red_ms": 4000,

    # --- Mapeo de pantalla y cursor ---
    "margen_zona_activa": 0.12,
    "invertir_cursor_x": False,
    "invertir_cursor_y": False,
    "max_salto_pixeles": 250,

    # --- Filtro One Euro para mouse_controller ---
    "one_euro_min_cutoff": 0.35,
    "one_euro_beta": 0.008,
    "one_euro_d_cutoff": 1.0,
    "one_euro_deadband": 2.0,

    # --- Reducción de Temblor y Filtros Anti-Jitter (Fase 9) ---
    "suavizar_landmarks_crudos": True,    # Filtro One Euro previo a cálculo de gestos
    "lm_filter_min_cutoff": 0.08,        # Frecuencia mínima banco landmarks (Hz)
    "lm_filter_beta": 0.04,              # Coeficiente velocidad banco landmarks
    "lm_filter_d_cutoff": 1.0,           # Frecuencia corte derivada landmarks
    "hud_pointer_min_cutoff": 0.15,      # Perfil One Euro para puntero HUD
    "hud_pointer_beta": 0.08,            # Coeficiente velocidad puntero HUD
    "hud_pointer_deadband": 1.5,         # Zona muerta puntero HUD (px)
    "rot_3d_min_cutoff": 0.45,           # Perfil One Euro rotación 3D yaw/pitch/roll
    "rot_3d_beta": 0.005,                # Coeficiente velocidad rotación 3D
    "rot_3d_deadband_px": 1.2,           # Zona muerta rotación 3D (px)
    "escala_3d_min_cutoff": 0.45,        # Perfil One Euro escala 3D
    "escala_3d_beta": 0.005,             # Coeficiente velocidad escala 3D
    "escala_3d_deadband": 0.035,         # Zona muerta escala 3D

    # --- Umbrales de gestos de dedos y pinches (Normalizados con d_ref) ---
    "umbral_dedo_extendido": 1.15,
    "agarrar_cerrar": 0.23,
    "agarrar_liberar": 0.31,
    "frames_para_arrastre": 6,
    "cooldown_clicks": 0.30,

    "click_derecho_cerrar": 0.23,
    "click_derecho_liberar": 0.31,
    "frames_confirmar_click_derecho": 5,

    # --- Confirmaciones por frames de acciones especiales ---
    "frames_confirmar_puno": 8,
    "frames_confirmar_mano_abierta": 8,
    "frames_confirmar_paz": 8,
    "frames_confirmar_salida_pausa": 8,

    # --- Scroll por Gestos ---
    "swipe_ventana_segundos": 0.25,
    "swipe_velocidad_umbral": 1.3,
    "swipe_cooldown": 0.6,
    "scroll_swipe_cantidad": 6,
    "wb_scroll_sensibilidad": 20.0,      # Multiplicador de desplazamiento para pyautogui.scroll
    "wb_scroll_deadzone": 15.0,          # Umbral relativo/px para activar scroll vertical

    # --- HUD y duraciones (Fase 3: HUD Interactivo Multimodal) ---
    "ultima_accion_duracion": 1.2,
    "hud_dwell_duracion": 0.40,          # Duración en segundos para dwell universal
    "hud_dwell_max_velocidad": 60.0,     # Velocidad máxima (px/s) para avance de dwell
    "legacy_panel_activo": False,        # Anula zonas táctiles invisibles del panel lateral viejo

    # --- MediaPipe Confianzas y Calibración ---
    "min_deteccion_confianza": 0.50,
    "min_seguimiento_confianza": 0.50,
    "min_presencia_confianza": 0.50,
    "min_deteccion_pose": 0.5,
    "min_seguimiento_pose": 0.5,
    "umbral_visibilidad_pose": 0.5,
    "pose_cada_n_frames": 3,

    # --- ROI de Pizarra ---
    "roi_enmascarar": True,              # Aislar MediaPipe al área de proyección
    "roi_margen_px": 60,                 # Margen en px de la máscara de inferencia

    # --- Pizarra Inteligente (Smart Whiteboard) ---
    "whiteboard_ema_alpha": 0.35,
    "whiteboard_dwell_time": 0.5,
    "whiteboard_smart_shapes": True,
    "whiteboard_use_one_euro": True,
    "wb_min_cutoff": 0.02,               # Frecuencia mínima One Euro Whiteboard (Hz)
    "wb_beta": 0.08,                    # Coeficiente de velocidad One Euro Whiteboard
    "wb_d_cutoff": 1.0,                  # Frecuencia de corte de derivada Whiteboard
    "wb_punto_pinza": True,              # Interpolación biométrica índice-pulgar
    "wb_roi_margen_px": 0.0,             # Tolerancia en px para dibujar dentro de ROI
    "wb_clic_derecho_mapea_pantalla": True, # Mapeo absoluto del clic derecho a resolución de pantalla
    "wb_grosor_pincel": 5,               # Grosor inicial de pincel en píxeles (rango 1 - 25 px)
    "wb_radio_borrado": 30,              # Radio inicial de borrador de palma en píxeles (rango 10 - 100 px)

    # --- Holograma 3D y Telaraña ---
    "smooth_holograma": 0.25,
    "alpha_escala": 0.20,
    "deadband_escala": 0.035,
    "web_smooth": 0.4,
    "enable_painter_algorithm": True,
    "enable_3d_faces": True,
    "faces_opacity": 0.95,
    "holo_min_cutoff": 1.5,
    "holo_beta": 0.01,
    "max_caras_render": 700,             # Límite para garantizar >= 30 FPS
}


def guardar_json_atomico(datos: Dict[str, Any], ruta: str) -> bool:
    """
    Helper centralizado para escritura atómica en disco usando tempfile y os.replace.
    Garantiza que ningún archivo quede truncado a 0 bytes por cierres abruptos.
    """
    directorio = os.path.dirname(os.path.abspath(ruta)) or "."
    os.makedirs(directorio, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=directorio, prefix="atom_tmp_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, ruta)
        return True
    except Exception as e:
        logger.error(f"Error en escritura atómica para '{ruta}': {e}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as e:
                logger.debug(f"Aviso al eliminar tmp_path: {e}")
        return False


def validar_limites_configuracion(cfg: Dict[str, Any]) -> None:
    """
    Valida y ajusta límites críticos de configuración para evitar inconsistencias lógicas.
    """
    # 1. Forzar agarrar_cerrar < agarrar_liberar (Schmitt Trigger Clic Izquierdo)
    if "agarrar_cerrar" in cfg and "agarrar_liberar" in cfg:
        c = float(cfg["agarrar_cerrar"])
        l = float(cfg["agarrar_liberar"])
        if c >= l:
            cfg["agarrar_cerrar"] = round(l * 0.70, 3)
            logger.warning(f"Inconsistencia en agarrar: forzado cerrar={cfg['agarrar_cerrar']} < liberar={l}")

    # 2. Forzar click_derecho_cerrar < click_derecho_liberar (Schmitt Trigger Clic Derecho)
    if "click_derecho_cerrar" in cfg and "click_derecho_liberar" in cfg:
        c = float(cfg["click_derecho_cerrar"])
        l = float(cfg["click_derecho_liberar"])
        if c >= l:
            cfg["click_derecho_cerrar"] = round(l * 0.70, 3)
            logger.warning(f"Inconsistencia en clic derecho: forzado cerrar={cfg['click_derecho_cerrar']} < liberar={l}")

    # 3. Limitar escala visual de la ventana a rango seguro [0.5, 3.0]
    if "escala_ventana" in cfg:
        cfg["escala_ventana"] = float(np.clip(float(cfg["escala_ventana"]), 0.5, 3.0))
    if "pantalla_ancho" in cfg:
        cfg["pantalla_ancho"] = max(640, int(cfg["pantalla_ancho"]))
    if "pantalla_alto" in cfg:
        cfg["pantalla_alto"] = max(480, int(cfg["pantalla_alto"]))
    if "fullscreen" in cfg:
        cfg["fullscreen"] = bool(cfg["fullscreen"])

    # 4. Scroll deadzone y sensibilidad mayores que cero
    if "wb_scroll_deadzone" in cfg:
        cfg["wb_scroll_deadzone"] = max(1.0, float(cfg["wb_scroll_deadzone"]))
    if "wb_scroll_sensibilidad" in cfg:
        cfg["wb_scroll_sensibilidad"] = max(1.0, float(cfg["wb_scroll_sensibilidad"]))

    # 5. Parámetros cinemáticos y de filtrado de holograma 3D (INFO-01)
    if "smooth_holograma" in cfg:
        cfg["smooth_holograma"] = float(np.clip(float(cfg["smooth_holograma"]), 0.01, 1.0))
    if "alpha_escala" in cfg:
        cfg["alpha_escala"] = float(np.clip(float(cfg["alpha_escala"]), 0.01, 1.0))
    if "deadband_escala" in cfg:
        cfg["deadband_escala"] = max(0.0, float(cfg["deadband_escala"]))
    if "max_caras_render" in cfg:
        cfg["max_caras_render"] = max(10, int(cfg["max_caras_render"]))
    if "hud_dwell_duracion" in cfg:
        cfg["hud_dwell_duracion"] = float(np.clip(float(cfg["hud_dwell_duracion"]), 0.10, 2.0))
    if "hud_dwell_max_velocidad" in cfg:
        cfg["hud_dwell_max_velocidad"] = max(10.0, float(cfg["hud_dwell_max_velocidad"]))


def cargar_configuracion(ruta: str = CONFIG_FILE_PATH) -> Dict[str, Any]:
    """
    Carga la configuración fusionando valores por defecto con config.json.
    Si el archivo no existe o está corrupto, lo regenera atómicamente.
    """
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                cargado = json.load(f)
                if isinstance(cargado, dict):
                    config.update(cargado)
        except Exception as e:
            logger.warning(f"Error al leer '{ruta}' ({e}). Restaurando defaults y persistiendo.")
            guardar_json_atomico(config, ruta)
    else:
        guardar_json_atomico(config, ruta)
        logger.info(f"Archivo de configuración generado con valores completos en: {ruta}")

    validar_limites_configuracion(config)
    return config


def guardar_configuracion(config_data: Dict[str, Any], ruta: str = CONFIG_FILE_PATH) -> bool:
    """Guarda atómicamente los parámetros de configuración en disco."""
    validar_limites_configuracion(config_data)
    ok = guardar_json_atomico(config_data, ruta)
    if ok:
        logger.info(f"Configuración guardada con éxito en '{ruta}'")
    return ok


class HotConfig:
    """
    Gestiona la configuración con recarga dinámica (Hot-Reload) en caliente.
    Mantiene la misma referencia en memoria (.data) e implementa acceso dict
    directo (__getitem__, __setitem__, get, etc.) para que todos los subsistemas
    reciban los cambios en vivo sin desincronizarse.
    """

    IGNORAR_RECARGA = {"fuente_camara", "cam_index", "fallback_local"}

    def __init__(self, ruta: str = CONFIG_FILE_PATH, base_dict: Optional[Dict[str, Any]] = None) -> None:
        self.ruta = os.path.abspath(ruta)
        self._lock = threading.Lock()
        self._running = True
        self._ultimo_mtime: float = 0.0

        # Carga inicial completa garantizada desde frame 1
        if base_dict is not None:
            self.data: Dict[str, Any] = dict(DEFAULT_CONFIG)
            self.data.update(base_dict)
            validar_limites_configuracion(self.data)
        else:
            self.data = cargar_configuracion(self.ruta)

        if os.path.exists(self.ruta):
            try:
                self._ultimo_mtime = os.path.getmtime(self.ruta)
            except OSError as e:
                logger.debug(f"Aviso al obtener getmtime inicial: {e}")
        else:
            self.persistir()

        # Hilo vigía en segundo plano (daemon)
        self._hilo_watcher = threading.Thread(target=self._vigilar_archivo, name="HotConfigWatcher", daemon=True)
        self._hilo_watcher.start()

    def _vigilar_archivo(self) -> None:
        """Comprueba periódicamente el mtime del archivo de configuración."""
        while self._running:
            time.sleep(1.0)
            if not os.path.exists(self.ruta):
                continue
            try:
                mtime = os.path.getmtime(self.ruta)
                recargar = False
                with self._lock:
                    if mtime > self._ultimo_mtime:
                        self._ultimo_mtime = mtime
                        recargar = True
                if recargar:
                    self._recargar()
            except Exception as e:
                logger.debug(f"Aviso al vigilar '{self.ruta}': {e}")

    def recargar_si_cambio(self) -> bool:
        """Comprueba si el archivo cambió en disco y lo recarga inmediatamente."""
        if not os.path.exists(self.ruta):
            return False
        try:
            mtime = os.path.getmtime(self.ruta)
            recargar = False
            with self._lock:
                if mtime > self._ultimo_mtime:
                    self._ultimo_mtime = mtime
                    recargar = True
            if recargar:
                self._recargar()
                return True
        except Exception as e:
            logger.debug(f"Aviso al comprobar cambios en '{self.ruta}': {e}")
        return False

    def _recargar(self) -> None:
        """Lee el archivo JSON y actualiza el diccionario en memoria preservando referencias."""
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                nuevo = json.load(f)

            if not isinstance(nuevo, dict):
                raise ValueError("El archivo JSON no contiene un diccionario válido.")

            with self._lock:
                for k, v in nuevo.items():
                    if k not in self.IGNORAR_RECARGA:
                        self.data[k] = v
                validar_limites_configuracion(self.data)

            logger.info(f"Archivo '{os.path.basename(self.ruta)}' recargado dinámicamente en caliente.")
        except Exception as e:
            logger.error(f"Error al recargar '{self.ruta}': {e}. Restaurando valores por defecto.")
            with self._lock:
                for k, v in DEFAULT_CONFIG.items():
                    if k not in self.data:
                        self.data[k] = v
                validar_limites_configuracion(self.data)

    def ajustar(self, clave: str, factor: float) -> Optional[Union[int, float]]:
        """
        Ajusta multiplicativamente un parámetro numérico y preserva estrictamente su tipo de dato.
        Enteros como frames_confirmar_paz permanecen como enteros.
        """
        with self._lock:
            if clave in self.data and isinstance(self.data[clave], (int, float)):
                val_ant = self.data[clave]
                if isinstance(val_ant, bool):
                    return None
                if isinstance(val_ant, int):
                    nuevo_val = max(1, int(round(val_ant * factor)))
                else:
                    nuevo_val = round(float(val_ant) * factor, 4)

                self.data[clave] = nuevo_val
                validar_limites_configuracion(self.data)
                logger.info(f"Parámetro '{clave}' ajustado: {val_ant} -> {nuevo_val}")
                return nuevo_val
            else:
                logger.warning(f"Clave '{clave}' no encontrada o no es numérica.")
                return None

    def obtener(self, clave: str, default: Any = None) -> Any:
        """Obtiene un valor de configuración de forma segura con lock."""
        with self._lock:
            return self.data.get(clave, default)

    def obtener_todo(self) -> Dict[str, Any]:
        """Retorna una copia completa del diccionario de configuración."""
        with self._lock:
            return dict(self.data)

    def get(self, clave: str, default: Any = None) -> Any:
        """Alias compatible con interfaz dict."""
        return self.obtener(clave, default)

    def get_all(self) -> Dict[str, Any]:
        """Alias compatible para obtener todo."""
        return self.obtener_todo()

    def persistir(self) -> bool:
        """Escribe atómicamente el contenido de self.data en el archivo de configuración."""
        with self._lock:
            validar_limites_configuracion(self.data)
            data_copia = dict(self.data)

        ok = guardar_json_atomico(data_copia, self.ruta)
        if ok and os.path.exists(self.ruta):
            try:
                self._ultimo_mtime = os.path.getmtime(self.ruta)
            except OSError as e:
                logger.debug(f"Aviso al obtener getmtime post-guardado: {e}")
            logger.info(f"Configuración persistida atómicamente en: '{self.ruta}'")
        return ok

    def stop(self) -> None:
        """Detiene el hilo de vigilancia en caliente."""
        self._running = False

    # Métodos mágicos para comportamiento idéntico a un diccionario en vivo
    def __getitem__(self, clave: str) -> Any:
        with self._lock:
            return self.data[clave]

    def __setitem__(self, clave: str, valor: Any) -> None:
        with self._lock:
            self.data[clave] = valor
            validar_limites_configuracion(self.data)

    def __contains__(self, clave: str) -> bool:
        with self._lock:
            return clave in self.data

    def __len__(self) -> int:
        with self._lock:
            return len(self.data)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            return iter(dict(self.data))

    def keys(self) -> Any:
        """Retorna las claves para compatibilidad total con dict() y el protocolo Mapping."""
        with self._lock:
            return dict(self.data).keys()

    def values(self) -> Any:
        """Retorna los valores para compatibilidad total con dict() y el protocolo Mapping."""
        with self._lock:
            return dict(self.data).values()

    def items(self) -> Any:
        """Retorna pares clave-valor para compatibilidad total con dict() y el protocolo Mapping."""
        with self._lock:
            return dict(self.data).items()

    def items_snapshot(self) -> Dict[str, Any]:
        """Retorna una copia atómica e inmutable de toda la configuración (LOW-01)."""
        with self._lock:
            return dict(self.data)

    def copy(self) -> Dict[str, Any]:
        """Retorna una copia atómica e inmutable de toda la configuración."""
        with self._lock:
            return dict(self.data)
