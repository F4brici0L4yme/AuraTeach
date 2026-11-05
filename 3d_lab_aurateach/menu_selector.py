"""
menu_selector.py
-------------------------------------------------------------------
Módulo del menú lateral HUD flotante, desplegable e interactivo.
Implementa la clase MenuElegible3D con:
- Pestaña de cabecera colapsable / desplegable: [ ☰ MENÚ ] / [ ✕ CERRAR ].
- Blindaje contra ausencia de librerías: Bloque try/except para 'trimesh'
  con generador procedural matemático integrado (Fallback en NumPy) para que
  la aplicación jamás sufra un crash si trimesh no está instalado.
- Activación por flanco de subida (Flank Trigger) para evitar rebotes continuos.
- Panel desplegable con botones táctiles interactivos para alternar modos:
  [ HOLOGRAMA ], [ MOUSE ] y [ PIZARRA ].
- Botones táctiles de selección de figuras 3D procedurales y modelos OBJ/STL.
- Filtrado de aristas características (Feature Edge Filtering > 25°) para aligerar
  renderizado de mallas complejas sin saturar la CPU/GPU.
- Efectos de iluminación al pasar el cursor (hover) y confirmación táctil inmediata.
- Paridad de tipos int en OpenCV y logging estructurado.
-------------------------------------------------------------------
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

# Configuración de logging para el módulo
logger = logging.getLogger("MenuSelectorSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)

from hologram import (
    ASSETS_DIR,
    HAS_TRIMESH,
    trimesh,
    generar_geometria_cubo,
    generar_geometria_piramide,
    generar_geometria_esfera,
    generar_geometria_dona,
    generar_geometria_octaedro,
)


# ====================================================================
# GENERADORES PROCEDURALES Y ALIASES CANÓNICOS (REUTILIZADOS DE HOLOGRAM)
# ====================================================================

# Preservación funcional estricta (Regla R1) con sentido de caras exterior corregido
_crear_cubo_fallback = generar_geometria_cubo
_crear_piramide_fallback = generar_geometria_piramide
_crear_esfera_fallback = generar_geometria_esfera
_crear_dona_fallback = generar_geometria_dona
_crear_octaedro_fallback = generar_geometria_octaedro


# ====================================================================
# CLASE PRINCIPAL DEL MENÚ HUD 3D
# ====================================================================

class MenuElegible3D:
    """
    Panel HUD interactivo desplegable para control táctil de modos y figuras 3D.
    Tolerante a la ausencia de trimesh gracias a generadores matemáticos procedurales.
    """

    _aviso_trimesh_mostrado: bool = False

    MODOS_CONFIG = [
        {"id": "MODO_HOLOGRAMA", "label": "Holograma 3D", "icono": "[H]"},
        {"id": "MODO_MOUSE",     "label": "Control Mouse", "icono": "[M]"},
        {"id": "MODO_PIZARRA",   "label": "Pizarra Smart", "icono": "[P]"},
        {"id": "TOGGLE_AULA",    "label": "Participaciones [P]", "icono": "[A]"},
    ]

    FIGURAS_CONFIG = [
        {"id": "ATOMO",            "label": "Atomo Cuantico",        "icono": "[@]"},
        {"id": "MOLECULA",         "label": "Constructor Molecular", "icono": "[M]"},
        {"id": "MATH",             "label": "Graficadora Math",      "icono": "[f]"},
        {"id": "CORAZON",          "label": "Corazon 3D",            "icono": "<3>"},
        {"id": "CEREBRO",          "label": "Cerebro 3D",            "icono": "[B]"},
        {"id": "CARRO_BUGGY",      "label": "Carro Buggy",           "icono": "[V]"},
        {"id": "REDUCTORA",        "label": "Reductora Engranajes",  "icono": "[G]"},
        {"id": "MOTOR_MECANISMO",  "label": "Motor Mecanismo",       "icono": "[M]"},
        {"id": "MOTOR_DC",         "label": "Motor DC",              "icono": "[D]"},
        {"id": "MOTOR_BRUSHLESS",  "label": "Motor Brushless",       "icono": "[b]"},
        {"id": "MOTOR_STEPPER",    "label": "Motor Stepper NEMA17",  "icono": "[S]"},
        {"id": "ARDUINO_UNO",      "label": "Arduino Uno",           "icono": "[A]"},
        {"id": "ESP32_CAM",        "label": "ESP32-S3 CAM",          "icono": "[E]"},
        {"id": "CASCO_SENSORES",   "label": "Casco Sensores",        "icono": "[H]"},
        {"id": "MODULO_TECH",      "label": "Modulo Tech",           "icono": "[T]"},
        {"id": "ANATOMIA",         "label": "Bio-Anatomia 3D",       "icono": "[B]"},
        {"id": "DESPIECE",         "label": "Motor LEGO",            "icono": "[#]"},
        {"id": "CUBO",             "label": "Cubo",                  "icono": "[C]"},
        {"id": "ESFERA",           "label": "Esfera",                "icono": "[O]"},
        {"id": "PIRAMIDE",         "label": "Piramide",              "icono": "[A]"},
        {"id": "DONA",             "label": "Dona",                  "icono": "[D]"},
        {"id": "MI_MODELO",        "label": "Mi Modelo",             "icono": "[*]"},
    ]

    RADIAL_NODOS = [
        {"id": "MODO_HOLOGRAMA", "label": "HOLOGRAMA",   "shortcut": "1", "icono": "[H]", "color": (0, 240, 255)},
        {"id": "ATOMO",          "label": "ATOMO",       "shortcut": "2", "icono": "[@]", "color": (50, 255, 120)},
        {"id": "MOLECULA",       "label": "MOLECULA",    "shortcut": "3", "icono": "[M]", "color": (100, 240, 255)},
        {"id": "MATH",           "label": "GRAFICADORA", "shortcut": "4", "icono": "[f]", "color": (160, 90, 255)},
        {"id": "ANATOMIA",       "label": "ANATOMIA",    "shortcut": "5", "icono": "[B]", "color": (50, 100, 255)},
        {"id": "DESPIECE",       "label": "DESPIECE",    "shortcut": "6", "icono": "[D]", "color": (0, 215, 255)},
        {"id": "MODO_PIZARRA",   "label": "PIZARRA",     "shortcut": "7", "icono": "[P]", "color": (255, 200, 50)},
        {"id": "MODO_MOUSE",     "label": "MOUSE",       "shortcut": "8", "icono": "[C]", "color": (255, 130, 50)},
    ]

    CATALOGO_MODELOS_3D = [
        {
            "id": "ATOMO",
            "nombre": "Atomo Cuantico",
            "subtitulo": "Simulador Rutherford-Bohr",
            "icono": "[@]",
            "color": (0, 240, 255),
            "shortcut": "1",
        },
        {
            "id": "MOLECULA",
            "nombre": "Molecula 3D",
            "subtitulo": "Constructor Molecular H2O",
            "icono": "<*>",
            "color": (50, 255, 120),
            "shortcut": "2",
        },
        {
            "id": "DESPIECE",
            "nombre": "Motor LEGO",
            "subtitulo": "Despiece Mecanico Axial",
            "icono": "[#]",
            "color": (0, 200, 255),
            "shortcut": "3",
        },
        {
            "id": "ANATOMIA",
            "nombre": "Bio-Anatomia",
            "subtitulo": "Corazon Multicapa 3D",
            "icono": "<3>",
            "color": (80, 90, 255),
            "shortcut": "4",
        },
        {
            "id": "MATH",
            "nombre": "Graficadora",
            "subtitulo": "Math Grapher 2D / 3D",
            "icono": "f(x)",
            "color": (255, 180, 0),
            "shortcut": "5",
        },
        {
            "id": "CUBO",
            "nombre": "Cubo 3D",
            "subtitulo": "Poliedro Regular Basico",
            "icono": "[C]",
            "color": (100, 200, 255),
            "shortcut": "6",
        },
        {
            "id": "ESFERA",
            "nombre": "Esfera 3D",
            "subtitulo": "Malla Esferica Cuadrica",
            "icono": "(O)",
            "color": (120, 240, 160),
            "shortcut": "7",
        },
        {
            "id": "PIRAMIDE",
            "nombre": "Piramide 3D",
            "subtitulo": "Piramide Cuadrangular",
            "icono": "/_\\",
            "color": (255, 200, 80),
            "shortcut": "8",
        },
        {
            "id": "DONA",
            "nombre": "Dona Toroide",
            "subtitulo": "Toroide Parametrico 3D",
            "icono": "(o)",
            "color": (240, 120, 240),
            "shortcut": "9",
        },
        {
            "id": "MI_MODELO",
            "nombre": "Mi Modelo",
            "subtitulo": "Malla OBJ / GLB Externa",
            "icono": "[M]",
            "color": (200, 220, 255),
            "shortcut": "0",
        },
    ]

    CATALOGO_COMPLETO_3D = [
        # --- Ciencia y Simulación Cuántica ---
        {
            "id": "ATOMO",
            "nombre": "Atomo Cuantico",
            "subtitulo": "Simulador Rutherford-Bohr",
            "icono": "[@]",
            "color": (0, 240, 255),
            "shortcut": "1",
            "archivo": "",
        },
        {
            "id": "MOLECULA",
            "nombre": "Molecula 3D",
            "subtitulo": "Constructor Molecular H2O",
            "icono": "<*>",
            "color": (50, 255, 120),
            "shortcut": "2",
            "archivo": "",
        },
        {
            "id": "MATH",
            "nombre": "Graficadora",
            "subtitulo": "Math Grapher 2D / 3D",
            "icono": "f(x)",
            "color": (255, 180, 0),
            "shortcut": "3",
            "archivo": "",
        },
        # --- Anatomía y Biología ---
        {
            "id": "CORAZON",
            "nombre": "Corazon 3D",
            "subtitulo": "Fisiologia Cardiaca Multicapa",
            "icono": "<3>",
            "color": (80, 90, 255),
            "shortcut": "4",
            "archivo": "anatomia/corazon.glb",
        },
        {
            "id": "CEREBRO",
            "nombre": "Cerebro 3D",
            "subtitulo": "59 Nodos Cerebrales y Lobulos",
            "icono": "[B]",
            "color": (180, 100, 255),
            "shortcut": "5",
            "archivo": "anatomia/cerebro.glb",
        },
        {
            "id": "ANATOMIA",
            "nombre": "Bio-Anatomia",
            "subtitulo": "HUD Biometrico ECG / BPM",
            "icono": "[+]",
            "color": (60, 130, 255),
            "shortcut": "6",
            "archivo": "",
        },
        # --- Mecánica y Motores ---
        {
            "id": "CARRO_BUGGY",
            "nombre": "Carro Buggy",
            "subtitulo": "Vehiculo Off-Road Multi-pieza",
            "icono": "[V]",
            "color": (50, 220, 255),
            "shortcut": "7",
            "archivo": "mecanica/carro_buggy.glb",
        },
        {
            "id": "REDUCTORA",
            "nombre": "Reductora Engranajes",
            "subtitulo": "Caja Planetaria Industrial",
            "icono": "[G]",
            "color": (0, 200, 255),
            "shortcut": "8",
            "archivo": "mecanica/reductora_engranajes.glb",
        },
        {
            "id": "MOTOR_MECANISMO",
            "nombre": "Motor Mecanismo",
            "subtitulo": "Biela-Manivela y Piston",
            "icono": "[M]",
            "color": (255, 180, 40),
            "shortcut": "9",
            "archivo": "mecanica/motores/motor_mecanismo.glb",
        },
        {
            "id": "MOTOR_DC",
            "nombre": "Motor DC",
            "subtitulo": "Rotor y Estator DC",
            "icono": "[D]",
            "color": (255, 130, 50),
            "shortcut": "A",
            "archivo": "mecanica/motores/motor_dc.glb",
        },
        {
            "id": "MOTOR_BRUSHLESS",
            "nombre": "Motor Brushless",
            "subtitulo": "Trifasico sin Escobillas",
            "icono": "[b]",
            "color": (50, 255, 120),
            "shortcut": "B",
            "archivo": "mecanica/motores/motor_brushless.glb",
        },
        {
            "id": "MOTOR_STEPPER",
            "nombre": "Motor Stepper NEMA17",
            "subtitulo": "Paso a Paso de Precision",
            "icono": "[S]",
            "color": (200, 200, 255),
            "shortcut": "C",
            "archivo": "mecanica/motores/motor_stepper_nema17.glb",
        },
        {
            "id": "DESPIECE",
            "nombre": "Motor LEGO",
            "subtitulo": "Despiece Mecanico Axial",
            "icono": "[#]",
            "color": (0, 200, 255),
            "shortcut": "D",
            "archivo": "",
        },
        # --- Electrónica y Robótica ---
        {
            "id": "ARDUINO_UNO",
            "nombre": "Arduino Uno",
            "subtitulo": "Microcontrolador ATmega328P",
            "icono": "[A]",
            "color": (0, 180, 220),
            "shortcut": "E",
            "archivo": "electronica/arduino_uno.glb",
        },
        {
            "id": "ESP32_CAM",
            "nombre": "ESP32-S3 CAM",
            "subtitulo": "Modulo WiFi/BT con OV2640",
            "icono": "[E]",
            "color": (120, 220, 100),
            "shortcut": "F",
            "archivo": "electronica/esp32_s3_cam.glb",
        },
        {
            "id": "CASCO_SENSORES",
            "nombre": "Casco Sensores",
            "subtitulo": "Sensor Array Headset",
            "icono": "[H]",
            "color": (220, 120, 255),
            "shortcut": "G",
            "archivo": "electronica/casco_sensores.glb",
        },
        {
            "id": "MODULO_TECH",
            "nombre": "Modulo Tech",
            "subtitulo": "Componente Electronico 3D",
            "icono": "[T]",
            "color": (240, 200, 100),
            "shortcut": "H",
            "archivo": "electronica/modulo_tech.glb",
        },
        # --- Primitivas Geométricas ---
        {
            "id": "CUBO",
            "nombre": "Cubo 3D",
            "subtitulo": "Poliedro Regular Basico",
            "icono": "[C]",
            "color": (100, 200, 255),
            "shortcut": "I",
            "archivo": "",
        },
        {
            "id": "ESFERA",
            "nombre": "Esfera 3D",
            "subtitulo": "Malla Esferica Cuadrica",
            "icono": "(O)",
            "color": (120, 240, 160),
            "shortcut": "J",
            "archivo": "",
        },
        {
            "id": "PIRAMIDE",
            "nombre": "Piramide 3D",
            "subtitulo": "Piramide Cuadrangular",
            "icono": "/_\\",
            "color": (255, 200, 80),
            "shortcut": "K",
            "archivo": "",
        },
        {
            "id": "DONA",
            "nombre": "Dona Toroide",
            "subtitulo": "Toroide Parametrico 3D",
            "icono": "(o)",
            "color": (240, 120, 240),
            "shortcut": "L",
            "archivo": "",
        },
        {
            "id": "MI_MODELO",
            "nombre": "Mi Modelo",
            "subtitulo": "Malla OBJ / GLB Externa",
            "icono": "[*]",
            "color": (200, 220, 255),
            "shortcut": "M",
            "archivo": "",
        },
    ]

    SUB_MODELOS_CONFIG = [
        {"id": "TOGGLE_SELECTOR", "label": "Modelos [F]", "shortcut": "F"},
        {"id": "CUBO",            "label": "Cubo",        "shortcut": "1"},
        {"id": "ESFERA",          "label": "Esfera",      "shortcut": "2"},
        {"id": "PIRAMIDE",        "label": "Piramide",    "shortcut": "3"},
        {"id": "DESPIECE",        "label": "Motor 3D",    "shortcut": "4"},
        {"id": "ATOMO",           "label": "Atomo",       "shortcut": "5"},
        {"id": "MOLECULA",        "label": "Molecula",    "shortcut": "6"},
        {"id": "ANATOMIA",        "label": "Anatomia",    "shortcut": "7"},
        {"id": "CENTRAR_MODELO",  "label": "Centrar [R]", "shortcut": "R"},
    ]

    def __init__(
        self,
        config_or_w: Optional[Union[Dict[str, Any], Any, int]] = None,
        assets_dir_or_h: Optional[Union[str, int]] = None,
        assets_dir: str = ASSETS_DIR,
    ) -> None:
        if isinstance(config_or_w, int):
            self.config = {}
            self.last_w = config_or_w
            self.last_h = int(assets_dir_or_h) if isinstance(assets_dir_or_h, int) else 720
            self.assets_dir = os.path.abspath(assets_dir)
        else:
            if hasattr(config_or_w, "data"):
                self.config = config_or_w.data
            elif isinstance(config_or_w, dict):
                self.config = config_or_w
            else:
                self.config = {}
            if isinstance(assets_dir_or_h, str):
                self.assets_dir = os.path.abspath(assets_dir_or_h)
            else:
                self.assets_dir = os.path.abspath(assets_dir)
            self.last_w = 1280
            self.last_h = 720
        self.seleccion_activa: str = "ATOMO"
        self.modo_actual: str = "PIZARRA"
        self.desplegado: bool = False  # Colapsado al inicio para vista limpia
        self.menu_radial_activo: bool = False  # Menú Radial Central Arc Reactor
        self.ultimo_clic_tiempo: float = -999.0
        self.cooldown_clic: float = 0.25

        # Dwell-time universal y arbitraje anti-falsos disparos (Fase 3)
        self.legacy_panel_activo: bool = bool(self.config.get("legacy_panel_activo", False))
        self.dwell_duracion: float = float(self.config.get("hud_dwell_duracion", 0.40))
        self._dwell_duracion: float = self.dwell_duracion
        self.dwell_max_velocidad: float = float(self.config.get("hud_dwell_max_velocidad", 60.0))
        self._dwell_nodo_id: Optional[str] = None
        self._dwell_inicio: float = 0.0
        self._ultimo_cursor_pos: Optional[Tuple[float, float]] = None
        self._ultimo_cursor_t: float = 0.0
        self._vel_cursor: float = 0.0
        self._cache_nodos_radiales: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        self._cache_pill_sizes: Dict[str, Dict[str, Any]] = {}

        # Barra superior compacta de sub-modelos 3D
        self.rects_submodelos: Dict[str, Tuple[int, int, int, int]] = {}
        self.last_w: int = 1280
        self.last_h: int = 720

        # Selector visual centrado / Carrusel 3D (Fase 4)
        self.selector_modelos_activo: bool = False
        self.carrusel_indice_foco: int = 0
        self.rects_carrusel: Dict[str, Tuple[int, int, int, int]] = {}

        # Estado y vinculación de Despiece Mecánico (Fase 6)
        self.factor_explosion: float = 0.0
        self.modelo_despiece: Optional[Any] = None

        # Advertencia informativa solo una vez si trimesh no está presente
        if not HAS_TRIMESH and not MenuElegible3D._aviso_trimesh_mostrado:
            logger.info("Librería 'trimesh' no detectada. Operando con motor procedural NumPy sin interrupciones.")
            MenuElegible3D._aviso_trimesh_mostrado = True

        # Flank trigger para evitar disparo continuo con pinza mantenida
        self._pinza_prev: bool = False

        # Caché de mallas trimesh o procedurales para acelerar proyección
        self._mallas_cache: Dict[str, Any] = {}
        self._datos_render_cache: Dict[str, Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]] = {}

        # Geometría del HUD
        self.tab_x: int = 15
        self.tab_y: int = 15
        self.tab_w: int = 160
        self.tab_h: int = 34

        self.btn_w: int = 160
        self.btn_h: int = 28
        self.btn_spacing: int = 4
        self.padding: int = 6

        self.rect_tab: Tuple[int, int, int, int] = (self.tab_x, self.tab_y, self.tab_x + self.tab_w, self.tab_y + self.tab_h)
        self.rect_panel: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self.botones_modos: List[Dict[str, Any]] = []
        self.botones_figuras: List[Dict[str, Any]] = []

        # Inicializar geometría 2D estática de botones
        self._recalcular_posiciones_botones()

        # Precargar geometrías
        self._precargar_mallas()

    @property
    def botones(self) -> List[Dict[str, Any]]:
        """Retorna la lista unificada de botones del menú (modos y figuras)."""
        if not self.botones_modos and not self.botones_figuras:
            self._recalcular_posiciones_botones()
        return self.botones_modos + self.botones_figuras

    def _recalcular_posiciones_botones(self) -> None:
        """Calcula las coordenadas estáticas 2D de los botones del panel desplegable."""
        tx1, ty1, tx2, ty2 = self.rect_tab
        panel_y_start = ty2 + 4
        px1 = tx1
        py1 = panel_y_start
        panel_w = self.btn_w + self.padding * 2
        total_items = len(self.MODOS_CONFIG) + len(self.FIGURAS_CONFIG)
        panel_h = (self.btn_h + self.btn_spacing) * total_items + 38 + self.padding * 2
        px2 = px1 + panel_w
        py2 = py1 + panel_h
        self.rect_panel = (int(px1), int(py1), int(px2), int(py2))

        y_cursor = py1 + self.padding + 14 + 6
        self.botones_modos = []
        for modo in self.MODOS_CONFIG:
            bx1 = px1 + self.padding
            by1 = y_cursor
            bx2 = bx1 + self.btn_w
            by2 = by1 + self.btn_h
            y_cursor += self.btn_h + self.btn_spacing
            btn_data = dict(modo)
            btn_data["rect"] = (int(bx1), int(by1), int(bx2), int(by2))
            self.botones_modos.append(btn_data)

        y_cursor += 16
        self.botones_figuras = []
        for fig in self.FIGURAS_CONFIG:
            bx1 = px1 + self.padding
            by1 = y_cursor
            bx2 = bx1 + self.btn_w
            by2 = by1 + self.btn_h
            y_cursor += self.btn_h + self.btn_spacing
            btn_data = dict(fig)
            btn_data["rect"] = (int(bx1), int(by1), int(bx2), int(by2))
            self.botones_figuras.append(btn_data)

    def _precargar_mallas(self) -> None:
        """Inicializa las geometrías en segundo plano."""
        for item in self.FIGURAS_CONFIG:
            btn_id = item["id"]
            try:
                self.obtener_datos_render(btn_id)
            except Exception as e:
                logger.debug(f"Precarga de {btn_id}: {e}")

    def limpiar_cache(self) -> None:
        """Invalida y vacía los cachés de geometría y datos de renderizado (INFO-06)."""
        self._mallas_cache.clear()
        self._datos_render_cache.clear()
        logger.info("Cachés de geometría de MenuElegible3D invalidados.")

    def actualizar_modo(self, nuevo_modo: str) -> None:
        """Actualiza el modo actual sincronizándolo con teclado o clics."""
        self.modo_actual = nuevo_modo.upper()

    def obtener_rect_btn_hud(self, w: Optional[int] = None) -> Tuple[int, int, int, int]:
        """
        Retorna las coordenadas (x1, y1, x2, y2) del Bounding Box 2D del nodo circular táctil
        estilo Arc Reactor en la esquina superior derecha (centro cx = w - 45, cy = 42, radio = 24).
        """
        curr_w = int(w if w is not None else self.last_w)
        cx = int(curr_w - 45)
        cy = 42
        r = 24
        return (int(cx - r), int(cy - r), int(cx + r), int(cy + r))

    def esta_sobre_boton_hud(self, cursor_pos: Optional[Tuple[float, float]], w: Optional[int] = None) -> bool:
        """Determina si el cursor táctil está sobre el nodo circular radial estilo Arc Reactor de HUD (área táctil >= 48px)."""
        if cursor_pos is None:
            return False
        curr_w = float(w if w is not None else self.last_w)
        cx_cur, cy_cur = float(cursor_pos[0]), float(cursor_pos[1])
        cx_btn = curr_w - 45.0
        cy_btn = 42.0
        r_tol = 24.0 + 8.0  # Radio con margen de tolerancia táctil e histéresis (diámetro 64 px >= 48 px)
        return bool((cx_cur - cx_btn) ** 2 + (cy_cur - cy_btn) ** 2 <= (r_tol ** 2))

    def esta_sobre_boton_menu(self, cursor_pos: Optional[Tuple[float, float]]) -> bool:
        """Determina si la punta del dedo se encuentra sobre el botón de cabecera [ = MENU ] / [ X CERRAR ]."""
        if cursor_pos is None:
            return False
        cx, cy = cursor_pos
        tx1, ty1, tx2, ty2 = self.rect_tab
        return (tx1 <= cx <= tx2 and ty1 <= cy <= ty2)

    def esta_sobre_barra_superior_3d(self, cursor_pos: Optional[Tuple[float, float]], w: Optional[int] = None) -> bool:
        """Determina si el cursor está sobre alguno de los botones de la barra superior de sub-modelos 3D (área táctil >= 48px)."""
        if cursor_pos is None:
            return False
        cx, cy = float(cursor_pos[0]), float(cursor_pos[1])
        for rx1, ry1, rx2, ry2 in self.rects_submodelos.values():
            # Margen táctil de al menos 48 px de altura con histéresis espacial
            if (rx1 - 4) <= cx <= (rx2 + 4) and (ry1 - 10) <= cy <= (ry2 + 14):
                return True
        return False

    def esta_sobre_menu(
        self,
        cursor_pos: Optional[Tuple[float, float]],
        w: Optional[int] = None,
        h: Optional[int] = None,
        ui_visible: bool = True,
    ) -> bool:
        """Determina con resolución real si el cursor interactivo se encuentra sobre el área táctil del HUD."""
        if cursor_pos is None:
            return False

        # Selector de Modelos 3D centrado (Fase 4): prioridad absoluta de UI (R6)
        if getattr(self, "selector_modelos_activo", False):
            return True

        curr_w = int(w if w is not None else self.last_w)
        curr_h = int(h if h is not None else self.last_h)

        # 1. Nodo circular superior derecho de HUD (siempre activo e inmune a ui_visible)
        if self.esta_sobre_boton_hud(cursor_pos, curr_w):
            return True
        if not ui_visible:
            return False

        # 2. Barra superior compacta de sub-modelos 3D
        if self.esta_sobre_barra_superior_3d(cursor_pos, curr_w):
            return True

        # 3. Menú Radial Central Arc Reactor (cuando está activo o desplegado)
        if getattr(self, "desplegado", False) or getattr(self, "menu_radial_activo", False):
            nodos = self.obtener_nodos_radiales(w=curr_w, h=curr_h)
            cx, cy = float(cursor_pos[0]), float(cursor_pos[1])
            for n in nodos:
                if (cx - n["cx"]) ** 2 + (cy - n["cy"]) ** 2 <= (n["r"] + 10) ** 2:
                    return True
            cen_x = int(curr_w // 2)
            cen_y = int(curr_h // 2)
            if (cx - cen_x) ** 2 + (cy - cen_y) ** 2 <= (26 + 10) ** 2:
                return True

        # 4. Panel lateral legacy: solo activo si legacy_panel_activo=True explícito
        if getattr(self, "legacy_panel_activo", False):
            tx1, ty1, tx2, ty2 = self.rect_tab
            if tx1 <= cursor_pos[0] <= tx2 and ty1 <= cursor_pos[1] <= ty2:
                return True
            if getattr(self, "desplegado", False):
                px1, py1, px2, py2 = self.rect_panel
                if px1 <= cursor_pos[0] <= px2 and py1 <= cursor_pos[1] <= py2:
                    return True

        # 5. UI de Despiece Mecánico (Panel de piezas y Slider de explosión)
        if getattr(self, "seleccion_activa", "") in ("DESPIECE", "ANATOMIA"):
            sw = 320
            sx1 = int(curr_w // 2 - sw // 2)
            sx2 = sx1 + sw
            sy1 = int(curr_h - 46)
            sy2 = int(curr_h - 18)
            cx, cy = float(cursor_pos[0]), float(cursor_pos[1])
            if sx1 - 8 <= cx <= sx2 + 8 and sy1 - 8 <= cy <= sy2 + 8:
                return True
            if 18 <= cx <= 248 and 88 <= cy <= 410:
                return True

        return False

    def vincular_escena(self, scene: Any) -> None:
        """Vincula una instancia SceneModel a la interfaz de menú selector."""
        self.modelo_despiece = scene

    def dibujar_boton_hud(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
        ui_visible: bool = True,
    ) -> np.ndarray:
        """
        Dibuja el nodo radial táctil estilo Arc Reactor en la esquina superior derecha (cx = w - 45, cy = 42, r = 24)
        para alternar la visibilidad de todas las interfaces (Modo Inmersivo Limpio).
        - Si ui_visible == True: Luce en neón cian/esmeralda vivo con arcos de energía.
        - Si ui_visible == False: Dibuja únicamente este nodo circular en tono tenue para restaurar la interfaz.
        """
        h_f, w_f = frame.shape[:2]
        cx = int(w_f - 45)
        cy = 42
        r = 24

        hover = self.esta_sobre_boton_hud(cursor_pos, w_f)

        x1 = max(0, cx - r - 4)
        y1 = max(0, cy - r - 4)
        x2 = min(w_f, cx + r + 5)
        y2 = min(h_f, cy + r + 5)

        roi = frame[y1:y2, x1:x2]
        if roi.shape[0] > 0 and roi.shape[1] > 0:
            dark_overlay = roi.copy()
            bg_col = (35, 25, 20) if (hover and ui_visible) else ((20, 25, 30) if ui_visible else (15, 18, 22))
            alpha = 0.65 if (hover or ui_visible) else 0.30

            # Disco interior translúcido
            local_cx = cx - x1
            local_cy = cy - y1
            cv2.circle(dark_overlay, (local_cx, local_cy), r, bg_col, -1, cv2.LINE_AA)
            cv2.addWeighted(dark_overlay, alpha, roi, 1.0 - alpha, 0, roi)

            # Paleta de colores Sci-Fi Arc Reactor
            if ui_visible:
                ring_col = (0, 240, 255) if hover else (0, 200, 230)
                arc_col = (50, 255, 120) if hover else (0, 240, 255)
                txt_col = (255, 255, 255) if hover else (210, 230, 240)
            else:
                ring_col = (0, 200, 180) if hover else (65, 85, 95)
                arc_col = (50, 255, 120) if hover else (50, 80, 75)
                txt_col = (255, 255, 255) if hover else (140, 160, 175)

            # Anillo exterior
            cv2.circle(frame, (cx, cy), r, ring_col, 2 if hover else 1, cv2.LINE_AA)
            # Arcos segmentados (Reactor Arc)
            cv2.ellipse(frame, (cx, cy), (r - 4, r - 4), 0, 15, 75, arc_col, 2, cv2.LINE_AA)
            cv2.ellipse(frame, (cx, cy), (r - 4, r - 4), 0, 195, 255, arc_col, 2, cv2.LINE_AA)
            # Texto "HUD [Tab]"
            cv2.putText(
                frame, "HUD", (cx - 14, cy + 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, txt_col, 1, cv2.LINE_AA
            )
            cv2.putText(
                frame, "Tab", (cx - 11, cy + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 240, 255) if hover else (140, 180, 200), 1, cv2.LINE_AA
            )

            # Anillo de progreso Dwell-Time circular sobre botón HUD
            if self._dwell_nodo_id == "TOGGLE_HUD" and self._dwell_inicio > 0.0:
                elapsed = time.time() - self._dwell_inicio
                frac = min(1.0, max(0.0, elapsed / max(self._dwell_duracion, 1e-4)))
                ang_prog = int(round(frac * 360.0))
                if ang_prog > 0:
                    cv2.ellipse(frame, (cx, cy), (r + 4, r + 4), -90, 0, ang_prog, (0, 255, 180), 2, cv2.LINE_AA)
        return frame

    def obtener_nodos_radiales(self, w: Optional[int] = None, h: Optional[int] = None) -> List[Dict[str, Any]]:
        """Calcula las posiciones espaciales 2D de los nodos del Menú Radial Arc Reactor con resolución real."""
        curr_w = int(w if w is not None else self.last_w)
        curr_h = int(h if h is not None else self.last_h)
        cache_key = (curr_w, curr_h)
        if cache_key in self._cache_nodos_radiales:
            return self._cache_nodos_radiales[cache_key]

        cx = int(curr_w // 2)
        cy = int(curr_h // 2)
        R_nodes = 120
        nodos = []
        n_nodos = len(self.RADIAL_NODOS)
        step_theta = (2.0 * np.pi) / max(n_nodos, 1)
        for i, data in enumerate(self.RADIAL_NODOS):
            theta = -np.pi / 2.0 + i * step_theta
            nx = int(round(cx + R_nodes * np.cos(theta)))
            ny = int(round(cy + R_nodes * np.sin(theta)))
            n = dict(data)
            n["cx"] = nx
            n["cy"] = ny
            n["r"] = 24  # Radio 24 px -> Diámetro táctil 48 px mínimo
            n["indice"] = i
            nodos.append(n)
        self._cache_nodos_radiales[cache_key] = nodos
        return nodos

    def dibujar_barra_submodelos_3d(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Dibuja una barra horizontal delgada y elegante en la parte superior (y = 12 a 36 px)
        con pastillas compactas para: [Cubo] [Esfera] [Piramide] [Despiece] [Atomo] [Molecula] [Anatomia].
        Permite cambiar de sub-modelo 3D directamente sin desplegar el HUD central.
        """
        h_f, w_f = frame.shape[:2]
        self.rects_submodelos.clear()

        n_items = len(self.SUB_MODELOS_CONFIG)
        pill_h = 24
        py1 = 12
        py2 = py1 + pill_h

        if not self._cache_pill_sizes:
            for i, item in enumerate(self.SUB_MODELOS_CONFIG):
                sc = str(item.get("shortcut", i + 1))
                display_txt = f"{sc}. {item['label']}"
                (tw, th), _ = cv2.getTextSize(display_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
                (tw_raw, _), _ = cv2.getTextSize(item["label"], cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                self._cache_pill_sizes[item["id"]] = {
                    "display_txt": display_txt,
                    "tw": tw, "th": th,
                    "w": max(64, tw_raw + 20),
                }

        widths = [self._cache_pill_sizes[item["id"]]["w"] for item in self.SUB_MODELOS_CONFIG]
        spacing = 8
        total_w = sum(widths) + spacing * (n_items - 1)
        start_x = max(160, int((w_f - total_w) // 2))

        px = float(cursor_pos[0]) if cursor_pos is not None else -1.0
        py = float(cursor_pos[1]) if cursor_pos is not None else -1.0

        # Fondo translúcido global en una sola pasada para toda la barra (ultra-rápido <= 0.02 ms)
        strip_x2 = min(w_f, start_x + total_w)
        strip = frame[py1:py2, start_x:strip_x2]
        if strip.shape[0] > 0 and strip.shape[1] > 0:
            cv2.convertScaleAbs(strip, dst=strip, alpha=0.45)

        cur_x = start_x
        for i, item in enumerate(self.SUB_MODELOS_CONFIG):
            pdata = self._cache_pill_sizes[item["id"]]
            w_i = pdata["w"]
            bx1 = int(cur_x)
            bx2 = int(cur_x + w_i)
            self.rects_submodelos[item["id"]] = (bx1, py1, bx2, py2)
            cur_x += w_i + spacing

            is_active = (self.seleccion_activa == item["id"])
            is_hover = (bx1 <= px <= bx2 and py1 <= py <= py2)

            if is_hover:
                roi = frame[py1:py2, bx1:bx2]
                cv2.rectangle(roi, (0, 0), (bx2 - bx1, py2 - py1), (45, 38, 20), -1)
            elif is_active:
                roi = frame[py1:py2, bx1:bx2]
                cv2.rectangle(roi, (0, 0), (bx2 - bx1, py2 - py1), (25, 55, 40), -1)

            border_col = (0, 240, 255) if is_hover else ((50, 255, 120) if is_active else (70, 85, 100))
            thick = 2 if (is_hover or is_active) else 1
            cv2.rectangle(frame, (bx1, py1), (bx2, py2), border_col, thick, cv2.LINE_AA)

            txt_col = (255, 255, 255) if (is_hover or is_active) else (180, 200, 220)
            tx = int(bx1 + (w_i - pdata["tw"]) // 2)
            ty = int(py1 + (pill_h + pdata["th"]) // 2 - 1)
            cv2.putText(frame, pdata["display_txt"], (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.36, txt_col, 1, cv2.LINE_AA)

            # Barra de progreso Dwell-Time inferior en pastilla activa
            if is_hover and self._dwell_nodo_id == item["id"] and self._dwell_inicio > 0.0:
                elapsed = time.time() - self._dwell_inicio
                frac = min(1.0, max(0.0, elapsed / max(self._dwell_duracion, 1e-4)))
                pw = int(round((bx2 - bx1) * frac))
                if pw > 0:
                    cv2.line(frame, (bx1 + 2, py2 - 2), (bx1 + pw - 2, py2 - 2), (0, 255, 180), 3, cv2.LINE_AA)

        return frame

    def dibujar_menu_radial_central(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Dibuja el Menú Radial Holográfico Circular en el centro de la pantalla (Arc Reactor Core).
        - Dimensiones compactas: radio_orbita = 115 px, radio_nucleo = 26 px, radio_nodo = 24 px.
        - 6 nodos radiales circulares a 60° con hover responsivo, halo especular y barra de progreso Dwell.
        - Cero frame.copy() global: usa ROI local recortado de 300x300 px para alto rendimiento (>= 60 FPS).
        """
        h_f, w_f = frame.shape[:2]
        cx = int(w_f // 2)
        cy = int(h_f // 2)
        ang_anim = (time.time() * 50.0) % 360.0

        # 1. Overlay translúcido sobre ROI local acotado (radio ~150 px)
        roi_r = 160
        rx1 = max(0, cx - roi_r)
        rx2 = min(w_f, cx + roi_r)
        ry1 = max(0, cy - roi_r)
        ry2 = min(h_f, cy + roi_r)

        roi = frame[ry1:ry2, rx1:rx2]
        if roi.shape[0] > 0 and roi.shape[1] > 0:
            dark_roi = roi.copy()
            cv2.circle(dark_roi, (cx - rx1, cy - ry1), roi_r - 2, (12, 14, 20), -1)
            cv2.addWeighted(dark_roi, 0.45, roi, 0.55, 0, roi)

        # 2. Núcleo Central del Arc Reactor (radio = 26 px)
        cv2.circle(frame, (cx, cy), 26, (0, 200, 240), 2, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 18, (18, 22, 30), -1)
        cv2.circle(frame, (cx, cy), 18, (50, 255, 120), 1, cv2.LINE_AA)

        # Arcos segmentados giratorios en el núcleo
        for seg_idx in range(3):
            arc_start = int((ang_anim + seg_idx * 120.0) % 360)
            arc_end = int((arc_start + 60) % 360)
            cv2.ellipse(frame, (cx, cy), (22, 22), 0, arc_start, arc_end, (0, 240, 255), 1, cv2.LINE_AA)

        # Resplandor central y texto compacto "STARK [Esc]"
        cv2.circle(frame, (cx, cy), 4, (255, 255, 255), -1)
        cv2.putText(
            frame, "STARK", (cx - 15, cy + 7),
            cv2.FONT_HERSHEY_SIMPLEX, 0.26, (0, 240, 255), 1, cv2.LINE_AA
        )
        cv2.putText(
            frame, "[Esc]", (cx - 12, cy + 17),
            cv2.FONT_HERSHEY_SIMPLEX, 0.22, (180, 210, 230), 1, cv2.LINE_AA
        )

        # Arco de progreso Dwell en núcleo central para colapsar HUD
        if self._dwell_nodo_id == "CERRAR_HUD" and self._dwell_inicio > 0.0:
            elapsed = time.time() - self._dwell_inicio
            frac = min(1.0, max(0.0, elapsed / max(self._dwell_duracion, 1e-4)))
            ang_core = int(round(frac * 360.0))
            if ang_core > 0:
                cv2.ellipse(frame, (cx, cy), (30, 30), -90, 0, ang_core, (0, 255, 180), 2, cv2.LINE_AA)

        # 3. 6 Nodos Radiales a 60° (radio_orbita = 115 px, radio_nodo = 24 px)
        nodos = self.obtener_nodos_radiales(w=w_f, h=h_f)
        px, py = (-1.0, -1.0)
        if cursor_pos is not None:
            px, py = float(cursor_pos[0]), float(cursor_pos[1])

        for i, nodo in enumerate(nodos):
            nx = int(nodo["cx"])
            ny = int(nodo["cy"])
            r_base = int(nodo["r"])
            lbl = str(nodo["label"])
            ico = str(nodo["icono"])
            col_node = tuple(int(c) for c in nodo["color"])
            node_id = str(nodo["id"])

            is_hover = bool(cursor_pos is not None and ((px - nx) ** 2 + (py - ny) ** 2 <= (r_base + 6) ** 2))
            is_active = (
                (node_id.replace("MODO_", "") == self.modo_actual)
                or (node_id == self.seleccion_activa)
            )

            r_draw = int(r_base + 3 if is_hover else (r_base + 1 if is_active else r_base))

            # Línea conectora holográfica desde el núcleo hasta el nodo
            vx = float(nx - cx)
            vy = float(ny - cy)
            v_len = max(float(np.hypot(vx, vy)), 1.0)
            nx_dir = vx / v_len
            ny_dir = vy / v_len
            p1_ray = (int(round(cx + 28.0 * nx_dir)), int(round(cy + 28.0 * ny_dir)))
            p2_ray = (int(round(nx - float(r_draw) * nx_dir)), int(round(ny - float(r_draw) * ny_dir)))
            cv2.line(frame, p1_ray, p2_ray, (0, 160, 200) if not is_hover else (0, 240, 255), 1, cv2.LINE_AA)

            # Relleno del nodo
            if is_hover:
                bg_col = (45, 38, 22)
                border_col = (0, 240, 255)
                thick = 2
            elif is_active:
                bg_col = (25, 55, 35)
                border_col = (50, 255, 120)
                thick = 2
            else:
                bg_col = (20, 24, 32)
                border_col = col_node
                thick = 1

            cv2.circle(frame, (nx, ny), r_draw, bg_col, -1)
            cv2.circle(frame, (nx, ny), r_draw, border_col, thick, cv2.LINE_AA)

            # Arcos orbitales exteriores al nodo
            cv2.ellipse(frame, (nx, ny), (r_draw + 3, r_draw + 3), 0, int((ang_anim * 1.5) % 360), int((ang_anim * 1.5 + 80) % 360), border_col, 1, cv2.LINE_AA)

            # Highlight especular Blinn-Phong
            cv2.circle(frame, (nx - r_draw // 3, ny - r_draw // 3), max(2, r_draw // 4), (255, 255, 255), -1)

            # Icono centrado
            (tw1, th1), _ = cv2.getTextSize(ico, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
            cv2.putText(
                frame, ico, (nx - tw1 // 2, ny - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA
            )

            # Atajo numérico visible
            sc = str(nodo.get("shortcut", i + 1))
            cv2.putText(
                frame, f"[{sc}]", (nx - 9, ny - r_draw - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 240, 255) if is_hover else (150, 200, 220), 1, cv2.LINE_AA
            )

            # Texto corto de función
            palabras = lbl.split()
            txt_display = palabras[0] if len(palabras) == 1 else (palabras[1] if palabras[0] in ("MODO", "MOTOR", "CONTROL", "PIZARRA") else palabras[0])
            (tw2, th2), _ = cv2.getTextSize(txt_display, cv2.FONT_HERSHEY_SIMPLEX, 0.30, 1)
            cv2.putText(
                frame, txt_display, (nx - tw2 // 2, ny + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.30, (220, 240, 255) if not is_hover else (255, 255, 255), 1, cv2.LINE_AA
            )

            # Arco de progreso Dwell-Time circular (si está en hover sobre este nodo)
            if is_hover and self._dwell_nodo_id == node_id and self._dwell_inicio > 0.0:
                elapsed = time.time() - self._dwell_inicio
                frac = min(1.0, max(0.0, elapsed / self._dwell_duracion))
                ang_prog = int(frac * 360.0)
                if ang_prog > 0:
                    cv2.ellipse(frame, (nx, ny), (r_draw + 5, r_draw + 5), -90, 0, ang_prog, (0, 255, 180), 2, cv2.LINE_AA)

        return frame

    def _dibujar_vector_preview(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        model_id: str,
        col: Tuple[int, int, int],
    ) -> None:
        """Dibuja una miniatura vectorial 2D estilizada del modelo 3D en tiempo real (cero assets externos)."""
        if model_id == "ATOMO":
            cv2.ellipse(frame, (x, y), (36, 14), 30, 0, 360, col, 1, cv2.LINE_8)
            cv2.ellipse(frame, (x, y), (36, 14), -30, 0, 360, col, 1, cv2.LINE_8)
            cv2.ellipse(frame, (x, y), (36, 14), 90, 0, 360, (0, 240, 255), 1, cv2.LINE_8)
            cv2.circle(frame, (x, y), 6, (0, 255, 180), -1)
        elif model_id == "MOLECULA":
            cv2.circle(frame, (x, y - 10), 10, (50, 100, 255), -1)
            cv2.circle(frame, (x - 20, y + 15), 7, (240, 240, 255), -1)
            cv2.circle(frame, (x + 20, y + 15), 7, (240, 240, 255), -1)
            cv2.line(frame, (x, y - 5), (x - 16, y + 11), (200, 220, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x, y - 5), (x + 16, y + 11), (200, 220, 255), 2, cv2.LINE_8)
        elif model_id == "DESPIECE":
            cv2.rectangle(frame, (x - 22, y - 18), (x + 22, y + 18), col, 2, cv2.LINE_8)
            cv2.circle(frame, (x, y), 8, (0, 240, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x - 30, y), (x + 30, y), (0, 255, 180), 1, cv2.LINE_8)
        elif model_id in ("ANATOMIA", "CORAZON"):
            pts = np.array([[x, y + 24], [x - 22, y - 2], [x - 14, y - 20], [x, y - 10], [x + 14, y - 20], [x + 22, y - 2]], np.int32)
            cv2.polylines(frame, [pts], True, (60, 70, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x, y - 10), (x, y + 8), (255, 120, 150), 1, cv2.LINE_8)
        elif model_id == "CEREBRO":
            cv2.ellipse(frame, (x - 10, y), (14, 20), 0, 0, 360, (180, 100, 255), 2, cv2.LINE_8)
            cv2.ellipse(frame, (x + 10, y), (14, 20), 0, 0, 360, (180, 100, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x, y - 16), (x, y + 16), (220, 180, 255), 1, cv2.LINE_8)
        elif model_id == "CARRO_BUGGY":
            cv2.rectangle(frame, (x - 22, y - 8), (x + 22, y + 10), col, 2, cv2.LINE_8)
            cv2.circle(frame, (x - 16, y + 14), 7, (0, 240, 255), -1, cv2.LINE_8)
            cv2.circle(frame, (x + 16, y + 14), 7, (0, 240, 255), -1, cv2.LINE_8)
            cv2.line(frame, (x - 14, y - 8), (x - 6, y - 18), col, 2, cv2.LINE_8)
            cv2.line(frame, (x + 14, y - 8), (x + 6, y - 18), col, 2, cv2.LINE_8)
            cv2.line(frame, (x - 6, y - 18), (x + 6, y - 18), col, 2, cv2.LINE_8)
        elif model_id in ("REDUCTORA", "REDUCTORA_ENGRANAJES"):
            cv2.circle(frame, (x, y), 16, col, 2, cv2.LINE_8)
            cv2.circle(frame, (x, y), 6, (0, 240, 255), -1, cv2.LINE_8)
            for ang in (0, 45, 90, 135, 180, 225, 270, 315):
                rad = np.radians(ang)
                px1 = int(round(x + 16 * np.cos(rad)))
                py1 = int(round(y + 16 * np.sin(rad)))
                px2 = int(round(x + 22 * np.cos(rad)))
                py2 = int(round(y + 22 * np.sin(rad)))
                cv2.line(frame, (px1, py1), (px2, py2), col, 2, cv2.LINE_8)
        elif model_id in ("MOTOR_MECANISMO", "MOTOR_DC", "MOTOR_BRUSHLESS", "MOTOR_STEPPER"):
            cv2.rectangle(frame, (x - 16, y - 16), (x + 16, y + 16), col, 2, cv2.LINE_8)
            cv2.circle(frame, (x, y), 8, (0, 240, 255), 1, cv2.LINE_8)
            cv2.line(frame, (x, y - 24), (x, y - 16), (255, 255, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x - 10, y), (x + 10, y), (50, 255, 120), 1, cv2.LINE_8)
        elif model_id == "ARDUINO_UNO":
            cv2.rectangle(frame, (x - 22, y - 16), (x + 22, y + 16), (0, 180, 220), 2, cv2.LINE_8)
            cv2.rectangle(frame, (x - 20, y - 14), (x - 10, y - 6), (200, 200, 200), -1, cv2.LINE_8)
            cv2.rectangle(frame, (x - 6, y - 6), (x + 8, y + 8), (60, 60, 60), -1, cv2.LINE_8)
            for i in range(4):
                cv2.circle(frame, (x - 12 + i * 8, y + 12), 1, (255, 255, 255), -1)
        elif model_id == "ESP32_CAM":
            cv2.rectangle(frame, (x - 18, y - 20), (x + 18, y + 20), (120, 220, 100), 2, cv2.LINE_8)
            cv2.circle(frame, (x, y - 4), 9, (40, 40, 40), -1)
            cv2.circle(frame, (x, y - 4), 9, (200, 240, 200), 1, cv2.LINE_8)
            cv2.circle(frame, (x, y - 4), 3, (0, 200, 255), -1)
        elif model_id == "CASCO_SENSORES":
            cv2.ellipse(frame, (x, y + 4), (22, 18), 0, 180, 360, (220, 120, 255), 2, cv2.LINE_8)
            cv2.line(frame, (x - 22, y + 4), (x - 16, y + 14), col, 2, cv2.LINE_8)
            cv2.line(frame, (x + 22, y + 4), (x + 16, y + 14), col, 2, cv2.LINE_8)
            cv2.circle(frame, (x, y - 14), 4, (0, 255, 200), -1)
        elif model_id == "MODULO_TECH":
            pts = np.array([[x, y - 20], [x + 18, y - 10], [x + 18, y + 10], [x, y + 20], [x - 18, y + 10], [x - 18, y - 10]], np.int32)
            cv2.polylines(frame, [pts], True, (240, 200, 100), 2, cv2.LINE_8)
            cv2.circle(frame, (x, y), 5, (0, 255, 255), -1)
        elif model_id == "MATH":
            pts = [int(y + 14 * np.sin((xi - x) * 0.12)) for xi in range(x - 28, x + 29, 4)]
            for i in range(len(pts) - 1):
                cv2.line(frame, (x - 28 + i * 4, pts[i]), (x - 28 + (i + 1) * 4, pts[i + 1]), col, 2, cv2.LINE_8)
            cv2.line(frame, (x - 30, y), (x + 30, y), (120, 140, 160), 1, cv2.LINE_8)
        elif model_id == "CUBO":
            cv2.rectangle(frame, (x - 18, y - 12), (x + 12, y + 18), col, 1, cv2.LINE_8)
            cv2.rectangle(frame, (x - 12, y - 18), (x + 18, y + 12), col, 1, cv2.LINE_8)
            cv2.line(frame, (x - 18, y - 12), (x - 12, y - 18), col, 1, cv2.LINE_8)
            cv2.line(frame, (x + 12, y - 12), (x + 18, y - 18), col, 1, cv2.LINE_8)
            cv2.line(frame, (x + 12, y + 18), (x + 18, y + 12), col, 1, cv2.LINE_8)
            cv2.line(frame, (x - 18, y + 18), (x - 12, y + 12), col, 1, cv2.LINE_8)
        elif model_id == "ESFERA":
            cv2.circle(frame, (x, y), 22, col, 1, cv2.LINE_8)
            cv2.ellipse(frame, (x, y), (22, 9), 0, 0, 360, col, 1, cv2.LINE_8)
            cv2.ellipse(frame, (x, y), (9, 22), 0, 0, 360, col, 1, cv2.LINE_8)
        elif model_id == "PIRAMIDE":
            pts = np.array([[x, y - 22], [x - 24, y + 18], [x + 24, y + 18]], np.int32)
            cv2.polylines(frame, [pts], True, col, 1, cv2.LINE_8)
            cv2.line(frame, (x, y - 22), (x + 4, y + 18), col, 1, cv2.LINE_8)
        elif model_id == "DONA":
            cv2.ellipse(frame, (x, y), (28, 16), 0, 0, 360, col, 2, cv2.LINE_8)
            cv2.ellipse(frame, (x, y), (14, 8), 0, 0, 360, (0, 240, 255), 1, cv2.LINE_8)
        else:
            cv2.circle(frame, (x, y), 20, col, 1, cv2.LINE_8)
            cv2.putText(frame, "OBJ", (x - 14, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_8)

    def dibujar_selector_modelos_carrusel(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Dibuja el selector visual centrado / carrusel de modelos 3D (Fase 4):
        - Tarjetas grandes centradas en pantalla con miniatura renderizada, título, subtítulo y atajo.
        - Navegación multimodal: flechas de carrusel, botones táctiles, dwell de 0.40s y atajos 1-0.
        - Botón integrado [ CENTRAR (R) ] y [ CERRAR (Esc) ].
        """
        curr_h, curr_w = frame.shape[:2]
        modal_w = min(880, curr_w - 60)
        modal_h = min(460, curr_h - 80)
        mx1 = int((curr_w - modal_w) // 2)
        my1 = int((curr_h - modal_h) // 2)
        mx2 = int(mx1 + modal_w)
        my2 = int(my1 + modal_h)
        cx = curr_w // 2

        self.rects_carrusel.clear()

        # 1. Fondo translúcido Sci-Fi con borde de energía
        roi = frame[my1:my2, mx1:mx2]
        if roi.shape[0] > 0 and roi.shape[1] > 0:
            cv2.convertScaleAbs(roi, dst=roi, alpha=0.30)

        cv2.rectangle(frame, (mx1, my1), (mx2, my2), (0, 240, 255), 2, cv2.LINE_8)
        # Esquinas decorativas
        c_len = 16
        for ex, ey, sx, sy in [(mx1, my1, 1, 1), (mx2, my1, -1, 1), (mx1, my2, 1, -1), (mx2, my2, -1, -1)]:
            cv2.line(frame, (ex, ey), (ex + sx * c_len, ey), (50, 255, 120), 3, cv2.LINE_8)
            cv2.line(frame, (ex, ey), (ex, ey + sy * c_len), (50, 255, 120), 3, cv2.LINE_8)

        # 2. Encabezado del Selector
        cv2.putText(
            frame, "SELECTOR DE MODELOS 3D  [ STARK MARK v3 ]", (mx1 + 24, my1 + 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.56, (0, 240, 255), 2, cv2.LINE_8
        )
        cv2.putText(
            frame, "Navegacion: Rueda Mouse | Flechas [<][>] | Atajos 1-0 | Dwell 0.40s | Tecla [F] o [Esc] Cerrar",
            (mx1 + 24, my1 + 52), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 200, 225), 1, cv2.LINE_8
        )

        px = float(cursor_pos[0]) if cursor_pos is not None else -1.0
        py = float(cursor_pos[1]) if cursor_pos is not None else -1.0

        # Botón [ CENTRAR (R) ]
        btn_c_x1, btn_c_y1 = mx2 - 245, my1 + 16
        btn_c_x2, btn_c_y2 = mx2 - 125, my1 + 46
        self.rects_carrusel["CENTRAR_MODELO"] = (btn_c_x1, btn_c_y1, btn_c_x2, btn_c_y2)
        h_centrar = (btn_c_x1 <= px <= btn_c_x2 and btn_c_y1 <= py <= btn_c_y2)
        cv2.rectangle(frame, (btn_c_x1, btn_c_y1), (btn_c_x2, btn_c_y2), (40, 60, 35) if h_centrar else (20, 32, 25), -1)
        cv2.rectangle(frame, (btn_c_x1, btn_c_y1), (btn_c_x2, btn_c_y2), (50, 255, 120) if h_centrar else (0, 200, 160), 1, cv2.LINE_8)
        cv2.putText(frame, "[ CENTRAR (R) ]", (btn_c_x1 + 10, btn_c_y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_8)
        if h_centrar and self._dwell_nodo_id == "CENTRAR_MODELO" and self._dwell_inicio > 0.0:
            frac = min(1.0, max(0.0, (time.time() - self._dwell_inicio) / max(self._dwell_duracion, 1e-4)))
            pw = int(round((btn_c_x2 - btn_c_x1) * frac))
            if pw > 0:
                cv2.line(frame, (btn_c_x1 + 2, btn_c_y2 - 2), (btn_c_x1 + pw - 2, btn_c_y2 - 2), (0, 255, 180), 2, cv2.LINE_8)

        # Botón [ CERRAR (Esc) ]
        btn_x_x1, btn_x_y1 = mx2 - 115, my1 + 16
        btn_x_x2, btn_x_y2 = mx2 - 20, my1 + 46
        self.rects_carrusel["CERRAR_SELECTOR"] = (btn_x_x1, btn_x_y1, btn_x_x2, btn_x_y2)
        h_cerrar = (btn_x_x1 <= px <= btn_x_x2 and btn_x_y1 <= py <= btn_x_y2)
        cv2.rectangle(frame, (btn_x_x1, btn_x_y1), (btn_x_x2, btn_x_y2), (60, 30, 30) if h_cerrar else (30, 20, 20), -1)
        cv2.rectangle(frame, (btn_x_x1, btn_x_y1), (btn_x_x2, btn_x_y2), (0, 120, 255) if h_cerrar else (70, 70, 90), 1, cv2.LINE_8)
        cv2.putText(frame, "[ CERRAR (Esc) ]", (btn_x_x1 + 6, btn_x_y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_8)
        if h_cerrar and self._dwell_nodo_id == "CERRAR_SELECTOR" and self._dwell_inicio > 0.0:
            frac = min(1.0, max(0.0, (time.time() - self._dwell_inicio) / max(self._dwell_duracion, 1e-4)))
            pw = int(round((btn_x_x2 - btn_x_x1) * frac))
            if pw > 0:
                cv2.line(frame, (btn_x_x1 + 2, btn_x_y2 - 2), (btn_x_x1 + pw - 2, btn_x_y2 - 2), (0, 255, 180), 2, cv2.LINE_8)

        # 3. Flechas de Navegación Lateral
        nav_prev_rect = (mx1 + 16, my1 + 185, mx1 + 54, my1 + 245)
        nav_next_rect = (mx2 - 54, my1 + 185, mx2 - 16, my1 + 245)
        self.rects_carrusel["NAV_PREV"] = nav_prev_rect
        self.rects_carrusel["NAV_NEXT"] = nav_next_rect

        h_prev = (nav_prev_rect[0] <= px <= nav_prev_rect[2] and nav_prev_rect[1] <= py <= nav_prev_rect[3])
        h_next = (nav_next_rect[0] <= px <= nav_next_rect[2] and nav_next_rect[1] <= py <= nav_next_rect[3])

        for rect_n, is_h, label_arr in [(nav_prev_rect, h_prev, "<"), (nav_next_rect, h_next, ">")]:
            cv2.rectangle(frame, (rect_n[0], rect_n[1]), (rect_n[2], rect_n[3]), (35, 45, 55) if is_h else (20, 26, 32), -1)
            cv2.rectangle(frame, (rect_n[0], rect_n[1]), (rect_n[2], rect_n[3]), (0, 240, 255) if is_h else (60, 80, 95), 1, cv2.LINE_8)
            cv2.putText(frame, label_arr, (rect_n[0] + 13, rect_n[1] + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 240, 255) if is_h else (160, 190, 210), 2, cv2.LINE_8)

        # 4. Tarjetas del Carrusel (5 tarjetas visibles centradas)
        n_total = len(self.CATALOGO_MODELOS_3D)
        foco = self.carrusel_indice_foco % n_total
        offsets = [-2, -1, 0, 1, 2]

        card_configs = {
            0:  {"w": 210, "h": 260, "cx": cx,              "alpha_box": (28, 36, 48), "border_col": (0, 240, 255), "thick": 2},
            -1: {"w": 145, "h": 200, "cx": cx - 185,        "alpha_box": (20, 25, 34), "border_col": (70, 95, 115), "thick": 1},
            1:  {"w": 145, "h": 200, "cx": cx + 185,        "alpha_box": (20, 25, 34), "border_col": (70, 95, 115), "thick": 1},
            -2: {"w": 105, "h": 150, "cx": cx - 315,        "alpha_box": (16, 20, 26), "border_col": (50, 65, 80),  "thick": 1},
            2:  {"w": 105, "h": 150, "cx": cx + 315,        "alpha_box": (16, 20, 26), "border_col": (50, 65, 80),  "thick": 1},
        }

        cy_deck = my1 + 225

        for off in offsets:
            cfg_c = card_configs[off]
            m_idx = (foco + off) % n_total
            m_data = self.CATALOGO_MODELOS_3D[m_idx]
            mid = m_data["id"]

            cw, ch = cfg_c["w"], cfg_c["h"]
            ccx = cfg_c["cx"]
            ccy = cy_deck

            k_x1 = int(ccx - cw // 2)
            k_y1 = int(ccy - ch // 2)
            k_x2 = int(ccx + cw // 2)
            k_y2 = int(ccy + ch // 2)

            self.rects_carrusel[mid] = (k_x1, k_y1, k_x2, k_y2)
            is_hover_card = (k_x1 <= px <= k_x2 and k_y1 <= py <= k_y2)
            is_active_model = (self.seleccion_activa == mid)

            bg_card = (40, 50, 65) if is_hover_card else ((30, 48, 38) if is_active_model else cfg_c["alpha_box"])
            b_col = (0, 255, 180) if is_hover_card else ((50, 255, 120) if is_active_model else cfg_c["border_col"])

            cv2.rectangle(frame, (k_x1, k_y1), (k_x2, k_y2), bg_card, -1)
            cv2.rectangle(frame, (k_x1, k_y1), (k_x2, k_y2), b_col, cfg_c["thick"], cv2.LINE_8)

            if off == 0:
                # Tarjeta Central Principal
                badge_txt = f"[{m_data['shortcut']}] {m_data['nombre']}"
                cv2.putText(frame, badge_txt, (k_x1 + 14, k_y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_8)

                # Miniatura vectorial renderizada
                self._dibujar_vector_preview(frame, ccx, ccy - 8, mid, m_data["color"])

                # Subtítulo descriptivo
                cv2.putText(frame, m_data["subtitulo"], (k_x1 + 12, k_y2 - 42), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (180, 210, 230), 1, cv2.LINE_8)

                # Botón de selección interactivo [ SELECCIONAR ]
                sel_y1 = k_y2 - 32
                sel_y2 = k_y2 - 8
                sel_x1 = k_x1 + 20
                sel_x2 = k_x2 - 20
                self.rects_carrusel[f"SEL_{mid}"] = (sel_x1, sel_y1, sel_x2, sel_y2)

                h_sel = (sel_x1 <= px <= sel_x2 and sel_y1 <= py <= sel_y2) or is_hover_card
                cv2.rectangle(frame, (sel_x1, sel_y1), (sel_x2, sel_y2), (45, 60, 35) if h_sel else (24, 34, 40), -1)
                cv2.rectangle(frame, (sel_x1, sel_y1), (sel_x2, sel_y2), (0, 255, 180) if h_sel else (0, 200, 230), 1, cv2.LINE_8)
                cv2.putText(frame, "SELECCIONAR [Enter]", (sel_x1 + 18, sel_y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1, cv2.LINE_8)

                # Dwell progress en tarjeta central
                if (is_hover_card or h_sel) and self._dwell_nodo_id in (mid, f"SEL_{mid}") and self._dwell_inicio > 0.0:
                    frac = min(1.0, max(0.0, (time.time() - self._dwell_inicio) / max(self._dwell_duracion, 1e-4)))
                    pw = int(round((k_x2 - k_x1) * frac))
                    if pw > 0:
                        cv2.line(frame, (k_x1 + 2, k_y2 - 2), (k_x1 + pw - 2, k_y2 - 2), (0, 255, 180), 3, cv2.LINE_8)
            else:
                # Tarjetas Laterales Secundarias
                badge_txt = f"[{m_data['shortcut']}] {m_data['nombre'][:10]}"
                cv2.putText(frame, badge_txt, (k_x1 + 8, k_y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (200, 220, 240), 1, cv2.LINE_8)
                self._dibujar_vector_preview(frame, ccx, ccy, mid, m_data["color"])

        # 5. Paginador de puntos inferior
        dot_y = my2 - 20
        for d_idx in range(n_total):
            dx = int(cx + (d_idx - (n_total - 1) / 2.0) * 18)
            is_cur = (d_idx == foco)
            cv2.circle(frame, (dx, dot_y), 5 if is_cur else 3, (0, 240, 255) if is_cur else (60, 75, 90), -1)

        return frame

    def dibujar_menu(
        self,
        frame: np.ndarray,
        cursor_pos: Optional[Tuple[float, float]] = None,
        ui_visible: bool = True,
    ) -> np.ndarray:
        """
        Dibuja los elementos del HUD interactivo multimodal (tiempo de renderizado <= 2.0 ms):
        - Botón táctil superior derecho [ HUD ] (siempre accesible e interactivo).
        - Si ui_visible == False: Modo inmersivo limpio, solo dibuja el botón HUD.
        - Si ui_visible == True:
          * Barra superior horizontal compacta para sub-modelos 3D (cuando el modo activo es 3D/HOLOGRAMA).
          * Menú Radial Central Arc Reactor (cuando está desplegado).
          * Panel lateral legacy: solo si legacy_panel_activo == True.
        """
        self.last_h, self.last_w = frame.shape[:2]

        # 1. Botón táctil superior derecho para alternar HUD / Menú Radial
        frame = self.dibujar_boton_hud(frame, cursor_pos=cursor_pos, ui_visible=ui_visible)

        if not ui_visible:
            return frame

        # 2. Barra horizontal superior compacta de sub-modelos 3D (y = 12..38 px)
        if self.modo_actual in ("3D", "MODO_3D", "HOLOGRAMA"):
            frame = self.dibujar_barra_submodelos_3d(frame, cursor_pos=cursor_pos)

        # 3. Menú Radial Central Arc Reactor (si está activo o desplegado)
        if getattr(self, "desplegado", False) or getattr(self, "menu_radial_activo", False):
            frame = self.dibujar_menu_radial_central(frame, cursor_pos=cursor_pos)

        # 4. Selector Visual Centrado / Carrusel de Modelos 3D (Fase 4)
        if getattr(self, "selector_modelos_activo", False):
            frame = self.dibujar_selector_modelos_carrusel(frame, cursor_pos=cursor_pos)

        return frame

    def procesar_clic_boton_hud(
        self,
        cursor_pos: Optional[Tuple[float, float]],
        gesto: Dict[str, Any],
        ahora: Optional[float] = None,
        w: int = 1280,
    ) -> bool:
        """
        Detecta si el usuario realizó un clic táctil (pinza o clic izquierdo)
        sobre el botón de HUD en la esquina superior derecha, con flanco de subida y cooldown de 0.3s.
        """
        if cursor_pos is None:
            return False
        cx, cy = cursor_pos
        hx1, hy1, hx2, hy2 = self.obtener_rect_btn_hud(w)
        if not (hx1 <= cx <= hx2 and hy1 <= cy <= hy2):
            return False

        if ahora is None:
            ahora = time.time()
        if ahora - self.ultimo_clic_tiempo < 0.30:
            return False

        pinza_indice = float(gesto.get("dist_pulgar_indice", gesto.get("pinch_agarrar", 1.0)))
        es_clic_izq = bool(gesto.get("es_clic_izquierdo", False))
        pinza_cerrada = (pinza_indice < 0.22) or es_clic_izq

        disparo = pinza_cerrada and not self._pinza_prev
        if disparo:
            self.ultimo_clic_tiempo = ahora
            logger.info("Alternancia de HUD solicitada vía botón táctil flotante.")
            return True
        return False

    def _activar_nodo(self, act_id: str) -> str:
        """Enruta y activa la acción seleccionada en el menú radial o barra 3D."""
        if act_id.startswith("MODO_"):
            modo_elegido = act_id.replace("MODO_", "")
            self.actualizar_modo(modo_elegido)
            return act_id
        elif act_id in ("ATOMO", "MOLECULA", "MATH", "ANATOMIA", "DESPIECE", "CUBO", "ESFERA", "PIRAMIDE", "DONA", "GRAFICADORA"):
            self.seleccion_activa = act_id
            return act_id
        elif act_id in ("CERRAR_HUD", "TOGGLE_HUD"):
            return "CERRAR_HUD"
        return act_id

    def procesar_clic_virtual(
        self,
        cursor_pos: Optional[Tuple[float, float]],
        gesto: Dict[str, Any],
        ahora: Optional[float] = None,
        w: Optional[int] = None,
        h: Optional[int] = None,
        vel_cursor: Optional[float] = None,
    ) -> Optional[str]:
        """
        Detecta pulsaciones táctiles virtuales (clic izquierdo de mouse, pinza instantánea o
        permanencia Dwell-time universal de 0.40s) usando flanco de subida y arbitraje anti-falsos disparos.
        """
        if cursor_pos is None:
            self._pinza_prev = False
            self._dwell_nodo_id = None
            self._dwell_inicio = 0.0
            return None

        if ahora is None:
            ahora = time.time()

        curr_w = int(w if w is not None else self.last_w)
        curr_h = int(h if h is not None else self.last_h)
        cx, cy = float(cursor_pos[0]), float(cursor_pos[1])

        # Actualizar estimador de velocidad del cursor para arbitraje de Dwell (< 60 px/s)
        if vel_cursor is not None:
            self._vel_cursor = float(vel_cursor)
        else:
            dt = ahora - self._ultimo_cursor_t if self._ultimo_cursor_t > 0 else 0.033
            if self._ultimo_cursor_pos is not None and dt > 1e-4:
                dx = cx - self._ultimo_cursor_pos[0]
                dy = cy - self._ultimo_cursor_pos[1]
                self._vel_cursor = float(np.hypot(dx, dy) / dt)
            else:
                self._vel_cursor = 0.0
        self._ultimo_cursor_pos = (cx, cy)
        self._ultimo_cursor_t = ahora

        # Estados de entrada del gesto
        pinza_indice = float(gesto.get("dist_pulgar_indice", gesto.get("pinch_agarrar", 1.0)))
        es_clic_izq = bool(gesto.get("es_clic_izquierdo", False))
        pinza_cerrada = (pinza_indice < 0.22) or es_clic_izq

        # Detección de flanco de subida (Flank Trigger) para pinza instantánea o clic de mouse
        disparo = pinza_cerrada and not self._pinza_prev
        self._pinza_prev = pinza_cerrada

        hud_abierto = bool(getattr(self, "desplegado", False) or getattr(self, "menu_radial_activo", False))

        # Identificar qué elemento del HUD se encuentra bajo el cursor táctil (Hit-Testing)
        target_id: Optional[str] = None
        target_tipo: Optional[str] = None

        # 0. Selector Modal Centrado de Modelos 3D (Fase 4: prioridad máxima de hit-testing)
        if getattr(self, "selector_modelos_activo", False) and self.rects_carrusel:
            for item_id, (bx1, by1, bx2, by2) in self.rects_carrusel.items():
                if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                    target_id = item_id
                    target_tipo = "SELECTOR_CARRUSEL"
                    break

        # 1. Botón superior derecho [ HUD ] (cx = w - 45, cy = 42, r = 24)
        elif self.esta_sobre_boton_hud(cursor_pos, curr_w):
            target_id = "TOGGLE_HUD"
            target_tipo = "BOTON_HUD"

        # 2. Menú Radial Central Arc Reactor (si está abierto)
        elif hud_abierto:
            nodos_rad = self.obtener_nodos_radiales(w=curr_w, h=curr_h)
            for nodo in nodos_rad:
                ncx, ncy, nr = nodo["cx"], nodo["cy"], nodo["r"]
                # Margen táctil con histéresis espacial
                r_hit = (nr + 12) if (self._dwell_nodo_id == nodo["id"]) else (nr + 8)
                if (cx - ncx) ** 2 + (cy - ncy) ** 2 <= r_hit ** 2:
                    target_id = nodo["id"]
                    target_tipo = "NODO_RADIAL"
                    break

            if target_id is None:
                # Núcleo central STARK Arc Reactor (para cerrar el HUD)
                cen_x = int(curr_w // 2)
                cen_y = int(curr_h // 2)
                r_core_hit = 38 if (self._dwell_nodo_id == "CERRAR_HUD") else 34
                if (cx - cen_x) ** 2 + (cy - cen_y) ** 2 <= r_core_hit ** 2:
                    target_id = "CERRAR_HUD"
                    target_tipo = "NUCLEO_CENTRAL"

        # 3. Pastillas compactas de la barra superior de sub-modelos 3D
        if target_id is None and self.modo_actual in ("3D", "MODO_3D", "HOLOGRAMA") and self.rects_submodelos:
            for sub_id, (bx1, py1, bx2, py2) in self.rects_submodelos.items():
                my1 = max(0, py1 - 10)
                my2 = py2 + 14
                mx1 = bx1 - 4
                mx2 = bx2 + 4
                if mx1 <= cx <= mx2 and my1 <= cy <= my2:
                    target_id = sub_id
                    target_tipo = "SUBMODELO_3D"
                    break

        # 4. Compatibilidad con panel lateral legacy (solo si legacy_panel_activo == True)
        if target_id is None and getattr(self, "legacy_panel_activo", False):
            tx1, ty1, tx2, ty2 = self.rect_tab
            if tx1 <= cx <= tx2 and ty1 <= cy <= ty2:
                target_id = "TOGGLE_MENU"
                target_tipo = "LEGACY_TAB"
            elif getattr(self, "desplegado", False):
                for btn in self.botones_modos:
                    bx1, by1, bx2, by2 = btn["rect"]
                    if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                        target_id = btn["id"]
                        target_tipo = "LEGACY_BTN_MODO"
                        break
                if target_id is None:
                    for btn in self.botones_figuras:
                        bx1, by1, bx2, by2 = btn["rect"]
                        if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                            target_id = btn["id"]
                            target_tipo = "LEGACY_BTN_FIGURA"
                            break

        # 5. UI de Despiece Mecánico (Slider y Panel)
        if target_id is None and getattr(self, "seleccion_activa", "") in ("DESPIECE", "ANATOMIA"):
            sw = 320
            sx1 = int(curr_w // 2 - sw // 2)
            sx2 = sx1 + sw
            sy1 = int(curr_h - 46)
            sy2 = int(curr_h - 18)
            track_x1 = sx1 + 86
            track_x2 = sx2 - 56
            track_w = max(1, track_x2 - track_x1)

            if sx1 - 8 <= cx <= sx2 + 8 and sy1 - 8 <= cy <= sy2 + 8:
                if disparo or pinza_cerrada:
                    nuevo_t = float(np.clip((cx - track_x1) / float(track_w), 0.0, 1.0))
                    self.factor_explosion = nuevo_t
                    try:
                        from hologram import obtener_escena_despiece_activa
                        escena = getattr(self, "modelo_despiece", None) or obtener_escena_despiece_activa()
                        if escena is not None:
                            escena.set_factor_explosion(nuevo_t)
                    except Exception:
                        pass
                    return f"SLIDER_EXPLOSION_{nuevo_t:.2f}"

            if 18 <= cx <= 248 and 88 <= cy <= 410:
                if disparo:
                    try:
                        from hologram import obtener_escena_despiece_activa
                        escena = getattr(self, "modelo_despiece", None) or obtener_escena_despiece_activa()
                        if escena is not None:
                            act = escena.procesar_interaccion_despiece(cursor_pos, clic=True)
                            if act:
                                return act
                    except Exception:
                        pass

        # --- A. DISPARO POR FLANCO (PINCH O CLIC IZQUIERDO DE MOUSE) ---
        if disparo and target_id is not None:
            if ahora - self.ultimo_clic_tiempo >= self.cooldown_clic:
                self.ultimo_clic_tiempo = ahora
                self._dwell_nodo_id = None
                self._dwell_inicio = 0.0

                if target_id in ("TOGGLE_HUD", "TOGGLE_MENU"):
                    self.desplegado = not self.desplegado
                    self.menu_radial_activo = self.desplegado
                    logger.info("HUD alternado vía botón táctil.")
                    return target_id
                elif target_id == "CERRAR_HUD":
                    self.desplegado = False
                    self.menu_radial_activo = False
                    logger.info("HUD radial colapsado desde núcleo central.")
                    return "CERRAR_HUD"
                elif target_tipo == "NODO_RADIAL":
                    self.desplegado = False
                    self.menu_radial_activo = False
                    logger.info(f"Nodo Radial seleccionado por flanco: {target_id}")
                    return self._activar_nodo(target_id)
                elif target_tipo == "SELECTOR_CARRUSEL":
                    if target_id == "CERRAR_SELECTOR":
                        self.selector_modelos_activo = False
                        logger.info("Selector de Modelos cerrado por clic.")
                        return "CERRAR_SELECTOR"
                    elif target_id == "CENTRAR_MODELO":
                        logger.info("Modelo centrado desde selector por clic.")
                        return "CENTRAR_MODELO"
                    elif target_id == "NAV_PREV":
                        self.carrusel_indice_foco = (self.carrusel_indice_foco - 1) % len(self.CATALOGO_MODELOS_3D)
                        return "NAV_PREV"
                    elif target_id == "NAV_NEXT":
                        self.carrusel_indice_foco = (self.carrusel_indice_foco + 1) % len(self.CATALOGO_MODELOS_3D)
                        return "NAV_NEXT"
                    else:
                        clean_id = target_id.replace("SEL_", "")
                        self.selector_modelos_activo = False
                        self.seleccion_activa = clean_id
                        logger.info(f"Modelo 3D seleccionado desde carrusel por clic: {clean_id}")
                        return clean_id
                elif target_tipo == "SUBMODELO_3D":
                    if target_id == "TOGGLE_SELECTOR":
                        self.selector_modelos_activo = not self.selector_modelos_activo
                        return "TOGGLE_SELECTOR"
                    elif target_id == "CENTRAR_MODELO":
                        return "CENTRAR_MODELO"
                    self.seleccion_activa = target_id
                    logger.info(f"Sub-modelo 3D seleccionado desde barra: {target_id}")
                    return target_id
                elif target_tipo == "LEGACY_BTN_MODO":
                    if target_id == "TOGGLE_AULA":
                        return "TOGGLE_AULA"
                    modo_elegido = target_id.replace("MODO_", "")
                    self.actualizar_modo(modo_elegido)
                    return target_id
                elif target_tipo == "LEGACY_BTN_FIGURA":
                    self.seleccion_activa = target_id
                    return target_id
                return self._activar_nodo(target_id)

        # --- B. ARBITRAJE DE DWELL-TIME UNIVERSAL (0.40s) ---
        # Regla de arbitraje anti-falsos disparos:
        # El temporizador de dwell solo avanza si:
        # 1. La mano está abierta / sin pinza activa (pinza_cerrada == False)
        # 2. La velocidad del cursor es baja (< 60 px/s)
        # 3. sobre_menu == True (target_id is not None)
        dwell_arbitraje_ok = (
            (target_id is not None)
            and (not pinza_cerrada)
            and (self._vel_cursor < self.dwell_max_velocidad)
        )

        if dwell_arbitraje_ok and target_id is not None:
            if self._dwell_nodo_id == target_id:
                if (ahora - self._dwell_inicio) >= self._dwell_duracion:
                    self._dwell_nodo_id = None
                    self._dwell_inicio = 0.0
                    self.ultimo_clic_tiempo = ahora

                    if target_id in ("TOGGLE_HUD", "TOGGLE_MENU"):
                        self.desplegado = not self.desplegado
                        self.menu_radial_activo = self.desplegado
                        logger.info("HUD alternado vía Dwell en botón HUD.")
                        return target_id
                    elif target_id == "CERRAR_HUD":
                        self.desplegado = False
                        self.menu_radial_activo = False
                        logger.info("HUD colapsado vía Dwell en núcleo central.")
                        return "CERRAR_HUD"
                    elif target_tipo == "NODO_RADIAL":
                        self.desplegado = False
                        self.menu_radial_activo = False
                        logger.info(f"Nodo Radial seleccionado por Dwell: {target_id}")
                        return self._activar_nodo(target_id)
                    elif target_tipo == "SELECTOR_CARRUSEL":
                        if target_id == "CERRAR_SELECTOR":
                            self.selector_modelos_activo = False
                            logger.info("Selector de Modelos cerrado por Dwell.")
                            return "CERRAR_SELECTOR"
                        elif target_id == "CENTRAR_MODELO":
                            logger.info("Modelo centrado desde selector por Dwell.")
                            return "CENTRAR_MODELO"
                        elif target_id == "NAV_PREV":
                            self.carrusel_indice_foco = (self.carrusel_indice_foco - 1) % len(self.CATALOGO_MODELOS_3D)
                            return "NAV_PREV"
                        elif target_id == "NAV_NEXT":
                            self.carrusel_indice_foco = (self.carrusel_indice_foco + 1) % len(self.CATALOGO_MODELOS_3D)
                            return "NAV_NEXT"
                        else:
                            clean_id = target_id.replace("SEL_", "")
                            self.selector_modelos_activo = False
                            self.seleccion_activa = clean_id
                            logger.info(f"Modelo 3D seleccionado desde carrusel por Dwell: {clean_id}")
                            return clean_id
                    elif target_tipo == "SUBMODELO_3D":
                        if target_id == "TOGGLE_SELECTOR":
                            self.selector_modelos_activo = not self.selector_modelos_activo
                            return "TOGGLE_SELECTOR"
                        elif target_id == "CENTRAR_MODELO":
                            return "CENTRAR_MODELO"
                        self.seleccion_activa = target_id
                        logger.info(f"Sub-modelo 3D seleccionado por Dwell: {target_id}")
                        return target_id
                    elif target_tipo == "LEGACY_BTN_MODO":
                        if target_id == "TOGGLE_AULA":
                            return "TOGGLE_AULA"
                        modo_elegido = target_id.replace("MODO_", "")
                        self.actualizar_modo(modo_elegido)
                        return target_id
                    elif target_tipo == "LEGACY_BTN_FIGURA":
                        self.seleccion_activa = target_id
                        return target_id
                    return self._activar_nodo(target_id)
            else:
                self._dwell_nodo_id = target_id
                self._dwell_inicio = ahora
        else:
            self._dwell_nodo_id = None
            self._dwell_inicio = 0.0

        return None

    def obtener_malla_3d(self, nombre: Optional[str] = None) -> Optional[Any]:
        """Retorna la malla trimesh si está disponible, o None en modo fallback."""
        if not HAS_TRIMESH:
            return None

        id_malla = (nombre or self.seleccion_activa).upper()
        if id_malla in self._mallas_cache:
            return self._mallas_cache[id_malla]

        mesh: Optional[Any] = None

        try:
            if id_malla == "CUBO":
                mesh = trimesh.creation.box(extents=(1.6, 1.6, 1.6))
            elif id_malla == "ESFERA":
                mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
            elif id_malla == "PIRAMIDE":
                mesh = trimesh.creation.cone(radius=1.1, height=1.6, sections=4)
            elif id_malla == "DONA":
                if hasattr(trimesh.creation, "torus"):
                    mesh = trimesh.creation.torus(major_radius=0.9, minor_radius=0.35, major_sections=20, minor_sections=12)
                elif hasattr(trimesh.creation, "annulus"):
                    mesh = trimesh.creation.annulus(r_min=0.55, r_max=1.25, height=0.4)
                else:
                    logger.warning("trimesh.creation.torus no disponible; recurriendo a generador procedural (LOW-09).")
                    mesh = None
            elif id_malla == "DESPIECE":
                mesh = trimesh.creation.box(extents=(1.5, 1.5, 1.5))
            elif id_malla == "ATOMO":
                if hasattr(trimesh.creation, "icosphere"):
                    mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
                else:
                    mesh = trimesh.creation.box(extents=(1.2, 1.2, 1.2))
            elif id_malla == "MI_MODELO":
                for ext in (
                    "mi_modelo.glb", "mi_modelo.gltf", "mi_modelo.obj", "mi_modelo.stl",
                    "model.glb", "model.gltf", "model.obj", "model.stl",
                ):
                    ruta = os.path.join(self.assets_dir, ext)
                    if os.path.exists(ruta):
                        try:
                            cargado = trimesh.load(ruta)
                            if isinstance(cargado, trimesh.Scene):
                                geom = [g for g in cargado.geometry.values() if isinstance(g, trimesh.Trimesh)]
                                mesh = trimesh.util.concatenate(geom) if geom else None
                            elif isinstance(cargado, trimesh.Trimesh):
                                mesh = cargado
                            if mesh is not None:
                                break
                        except Exception as e:
                            logger.debug(f"Error al cargar {ruta}: {e}")

                if mesh is None:
                    if hasattr(trimesh.creation, "octahedron"):
                        mesh = trimesh.creation.octahedron()
                    elif hasattr(trimesh.creation, "box"):
                        mesh = trimesh.creation.box(extents=(1.4, 1.4, 1.4))

            if mesh is not None:
                max_caras = int(self.config.get("max_caras_render", 3000))
                if len(mesh.faces) > max_caras:
                    try:
                        mesh = mesh.simplify_quadric_decimation(max_caras)
                    except Exception as e:
                        logger.debug(f"Decimación omitida: {e}")

                mesh.apply_translation(-mesh.centroid)
                max_extent = max(mesh.extents) if len(mesh.extents) > 0 else 1.0
                if max_extent > 1e-4:
                    mesh.apply_scale(1.8 / max_extent)
                self._mallas_cache[id_malla] = mesh
        except Exception as e:
            logger.warning(f"Error procesando malla {id_malla}: {e}")
            mesh = None

        return mesh

    def obtener_datos_render(
        self,
        nombre: Optional[str] = None,
    ) -> Tuple[np.ndarray, List[Tuple[int, int]], List[List[int]]]:
        """
        Extrae vértices, aristas y caras para renderizado con Algoritmo del Pintor.
        Si trimesh está disponible, aplica filtrado de aristas > 25°.
        Si trimesh no está instalado, utiliza generadores procedurales matemáticos nativos (Fallback).
        """
        id_malla = (nombre or self.seleccion_activa).upper()
        if id_malla in self._datos_render_cache:
            return self._datos_render_cache[id_malla]

        # 1. Si no hay trimesh, usar generadores matemáticos nativos
        if not HAS_TRIMESH:
            if id_malla == "CUBO":
                v, e, f = _crear_cubo_fallback()
            elif id_malla == "ESFERA":
                v, e, f = _crear_esfera_fallback()
            elif id_malla == "PIRAMIDE":
                v, e, f = _crear_piramide_fallback()
            elif id_malla == "DONA":
                v, e, f = _crear_dona_fallback()
            elif id_malla in ("ATOMO", "MOLECULA", "MATH", "ANATOMIA"):
                v, e, f = _crear_dona_fallback(major_r=0.9, minor_r=0.15, n_u=20, n_v=8)
            else:
                v, e, f = _crear_octaedro_fallback()

            self._datos_render_cache[id_malla] = (v, e, f)
            return v, e, f

        # 2. Si trimesh está instalado, extraer de la malla trimesh
        mesh = self.obtener_malla_3d(id_malla)
        if mesh is None:
            if id_malla == "CUBO":
                v, e, f = _crear_cubo_fallback()
            elif id_malla == "ESFERA":
                v, e, f = _crear_esfera_fallback()
            elif id_malla == "PIRAMIDE":
                v, e, f = _crear_piramide_fallback()
            elif id_malla == "DONA":
                v, e, f = _crear_dona_fallback()
            elif id_malla in ("ATOMO", "MOLECULA", "MATH", "ANATOMIA"):
                v, e, f = _crear_dona_fallback(major_r=0.9, minor_r=0.15, n_u=20, n_v=8)
            else:
                v, e, f = _crear_octaedro_fallback()
            self._datos_render_cache[id_malla] = (v, e, f)
            return v, e, f

        vertices = np.array(mesh.vertices, dtype=np.float32)
        faces = [list(int(x) for x in f) for f in mesh.faces]

        if hasattr(mesh, "face_adjacency_angles") and len(mesh.edges_unique) > 120:
            try:
                sharp_mask = mesh.face_adjacency_angles > np.radians(25.0)
                if hasattr(mesh, "face_adjacency_edges") and len(mesh.face_adjacency_edges) == len(sharp_mask):
                    feature_edges = mesh.face_adjacency_edges[sharp_mask]
                    edges = [tuple(int(x) for x in e) for e in feature_edges]
                    if not edges:
                        edges = [tuple(int(x) for x in e) for e in mesh.edges_unique]
                else:
                    edges = [tuple(int(x) for x in e) for e in mesh.edges_unique]
            except Exception:
                edges = [tuple(int(x) for x in e) for e in mesh.edges_unique]
        else:
            edges = [tuple(int(x) for x in e) for e in mesh.edges_unique]

        self._datos_render_cache[id_malla] = (vertices, edges, faces)
        return vertices, edges, faces


# Alias canónico para compatibilidad de orquestadores
MenuSelector = MenuElegible3D

