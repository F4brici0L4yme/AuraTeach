"""
main.py
================================================================================
STARK MARK v3 - NÚCLEO 3D INDEPENDIENTE Y ORQUESTADOR MAESTRO MULTIMODAL
================================================================================
Módulo principal y orquestador maestro para el visor 3D interactivo independiente.
Proporciona:
- Sistema de entrada híbrido (Ratón vs. MediaPipe HandLandmarker de 21 landmarks)
  con conmutación en caliente en tiempo real mediante la tecla '|' (ASCII 124).
- Adaptador unificado que normaliza el hardware activo a la estructura estándar
  esperada por HologramController: `manos_simuladas = [{"pos": (x, y), "pinch": bool}]`.
- Control de consumo de CPU: desactivación de inferencia biométrica en modo RATÓN.
- Filtro OneEuroFilter2D (min_cutoff=0.40, beta=0.005, deadband=2.0) para erradicar
  cualquier temblor (jitter) en reposo durante el seguimiento de manos.
- Posición de interacción como punto medio entre pulgar (LM 4) e índice (LM 8).
- Detección de pinza bi-estable por Schmitt Trigger (distancia < 0.23 activa, > 0.31 libera).
- FSM agnóstica (REPOSO, HOVER, SELECCIONADO, DRAG) con congelación estricta de escala.
- Liberación rigurosa de recursos GPU (GlRenderer VRAM) y hardware al salir con ESC.
- Tipado estricto, casting explícito a int en OpenCV y cero excepciones silenciosas.
================================================================================
"""

import logging
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import mediapipe as mp
import numpy as np

from filters import OneEuroFilter2D
from hologram import HologramController
from menu_selector import MenuSelector
from renderer import BaseRenderer, GlRenderer
from scene_model import Objeto3D, SceneModel

# -----------------------------------------------------------------------------
# Configuración del Sistema de Registro (Logging)
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("STARK_Mark_v3_Orchestrator")

# Variable global accesible para estado del orquestador
input_mode: str = "mouse"


class OrquestadorVisor3D:
    """
    Orquestador maestro de la escena 3D y despachador de entrada híbrida (Mouse/Hands).
    """

    def __init__(self, ancho: int = 1280, alto: int = 720) -> None:
        self.w: int = int(ancho)
        self.h: int = int(alto)
        self.titulo_ventana: str = "STARK Mark v3 - Nucleo 3D Independiente"

        # 1. Variables de Modo de Entrada
        global input_mode
        self.input_mode: str = input_mode  # 'mouse' o 'hands'

        # 2. Variables de Entrada de Ratón
        self.mouse_x: int = self.w // 2
        self.mouse_y: int = self.h // 2
        self.mouse_pinch: bool = False

        # 3. Componentes de MediaPipe y Visión
        self.cap: Optional[cv2.VideoCapture] = None
        self.cam_disponible: bool = False
        self.detector_manos: Optional[mp.tasks.vision.HandLandmarker] = None
        self.ruta_modelo_manos: str = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task"
        )

        # Filtro OneEuroFilter2D para la mano:
        # min_cutoff=0.40, beta=0.005, deadband=2.0 según especificación HCI
        self.hand_filter: OneEuroFilter2D = OneEuroFilter2D(
            min_cutoff=0.40,
            beta=0.005,
            d_cutoff=1.0,
            deadband=2.0,
        )

        # Estado del Schmitt Trigger para pinza de mano (dist < 0.23 activa, > 0.31 libera)
        self.hand_pinch: bool = False
        self.hand_pos_actual: Optional[Tuple[int, int]] = None
        self.hand_landmarks_21: Optional[np.ndarray] = None

        # 4. Motor Gráfico y Controladores de Escena 3D
        logger.info(f"Inicializando GlRenderer ({self.w}x{self.h})...")
        self.renderer: GlRenderer = GlRenderer(self.w, self.h)
        self.holo_ctrl: HologramController = HologramController(
            self.w, self.h, renderer=self.renderer
        )
        self.menu: MenuSelector = MenuSelector(self.w, self.h)
        self.menu.modo_actual = "3D"

        # Cargar ensamble mecánico inicial (Despiece LEGO / Motor)
        logger.info("Cargando modelo de despiece mecanico por defecto...")
        self.holo_ctrl.cargar_modelo_despiece()
        self.menu.vincular_escena(self.holo_ctrl.objeto_activo)

        # 5. Métricas de Rendimiento
        self.tiempo_prev: float = time.perf_counter()
        self.fps: float = 60.0

    # -------------------------------------------------------------------------
    # Callbacks y Gestión de Hardware (Ratón)
    # -------------------------------------------------------------------------
    def _mouse_callback(self, event: int, x: int, y: int, flags: int, param: Any) -> None:
        """Callback de OpenCV para capturar eventos del ratón con casting explícito."""
        self.mouse_x = int(np.clip(x, 0, self.w - 1))
        self.mouse_y = int(np.clip(y, 0, self.h - 1))

        if event == cv2.EVENT_LBUTTONDOWN:
            self.mouse_pinch = True
        elif event == cv2.EVENT_LBUTTONUP:
            self.mouse_pinch = False

    def alternar_modo_entrada(self) -> None:
        """Alterna en caliente entre modo 'mouse' y modo 'hands'."""
        global input_mode
        if self.input_mode == "mouse":
            self.input_mode = "hands"
            input_mode = "hands"
            logger.info(">>> CONMUTACION EN CALIENTE: MODO MANOS (MediaPipe 21 Landmarks) ACTIVADO <<<")
            self._asegurar_detector_manos()
            self._asegurar_camara()
        else:
            self.input_mode = "mouse"
            input_mode = "mouse"
            logger.info(">>> CONMUTACION EN CALIENTE: MODO RATON ACTIVADO (MediaPipe en reposo) <<<")
            # Restablecer filtros de mano para evitar discontinuidades
            self.hand_filter.reset()
            self.hand_pinch = False
            self.hand_landmarks_21 = None
            self.hand_pos_actual = None

    # -------------------------------------------------------------------------
    # Inicialización y Evaluación de MediaPipe HandLandmarker
    # -------------------------------------------------------------------------
    def _asegurar_camara(self) -> None:
        """Inicializa la captura de video si aún no está activa."""
        if self.cap is not None and self.cap.isOpened():
            return

        try:
            # Probar índices de cámara estándar con DirectShow en Windows
            for cam_idx in (0, 1):
                cap_test = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
                if cap_test.isOpened():
                    cap_test.set(cv2.CAP_PROP_FRAME_WIDTH, self.w)
                    cap_test.set(cv2.CAP_PROP_FRAME_HEIGHT, self.h)
                    self.cap = cap_test
                    self.cam_disponible = True
                    logger.info(f"Camara de video inicializada en indice {cam_idx} ({self.w}x{self.h}).")
                    return
                cap_test.release()

            # Fallback a backend predeterminado
            cap_default = cv2.VideoCapture(0)
            if cap_default.isOpened():
                self.cap = cap_default
                self.cam_disponible = True
                logger.info(f"Camara de video inicializada con backend predeterminado.")
                return
            cap_default.release()

            logger.warning("No se detecto dispositivo de camara fisica activa. Operando con fallback sintético.")
            self.cam_disponible = False
        except Exception as e:
            logger.warning(f"Aviso al inicializar camara de video: {e}")
            self.cam_disponible = False

    def _asegurar_detector_manos(self) -> bool:
        """Instancia el detector MediaPipe HandLandmarker si no está inicializado."""
        if self.detector_manos is not None:
            return True

        if not os.path.exists(self.ruta_modelo_manos):
            logger.error(
                f"Archivo de modelo MediaPipe no encontrado: '{self.ruta_modelo_manos}'. "
                f"Modo manos no podra procesar landmarks."
            )
            return False

        try:
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            opciones = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=self.ruta_modelo_manos),
                running_mode=VisionRunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.50,
                min_hand_presence_confidence=0.50,
                min_tracking_confidence=0.50,
            )
            self.detector_manos = HandLandmarker.create_from_options(opciones)
            logger.info("MediaPipe HandLandmarker instanciado exitosamente en modo VIDEO.")
            return True
        except Exception as e:
            logger.error(f"Fallo critico al instanciar MediaPipe HandLandmarker: {e}", exc_info=True)
            self.detector_manos = None
            return False

    def _procesar_entrada_manos(
        self, frame_camara: np.ndarray, timestamp_ms: int
    ) -> List[Dict[str, Any]]:
        """
        Evalúa MediaPipe HandLandmarker, extrae 21 puntos, aplica OneEuroFilter2D
        y calcula el estado de pinza mediante Schmitt Trigger.
        Retorna: lista normalizada `[{"pos": (x, y), "pinch": bool, "pts": ndarray}]`.
        """
        if self.detector_manos is None:
            if not self._asegurar_detector_manos():
                return []

        try:
            # Conversión de BGR a RGB para MediaPipe Image
            rgb_frame = cv2.cvtColor(frame_camara, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            # Inferencia no bloqueante para video
            resultado = self.detector_manos.detect_for_video(mp_image, int(timestamp_ms))

            if not resultado or not getattr(resultado, "hand_landmarks", None):
                # Reposo: sin manos detectadas
                self.hand_filter.reset()
                self.hand_pinch = False
                self.hand_landmarks_21 = None
                self.hand_pos_actual = None
                return []

            lista_manos = resultado.hand_landmarks
            if len(lista_manos) == 0:
                self.hand_filter.reset()
                self.hand_pinch = False
                self.hand_landmarks_21 = None
                self.hand_pos_actual = None
                return []

            # Seleccionar mano dominante (primera detectada)
            lms = lista_manos[0]
            items = lms.landmark if hasattr(lms, "landmark") else lms
            if len(items) < 21:
                return []

            # 1. Extraer los 21 puntos biométricos en coordenadas de píxeles HD
            pts_21 = np.zeros((21, 3), dtype=np.float32)
            for i in range(21):
                pt = items[i]
                # Invertir X para efecto espejo si proviene de cámara frontal
                px = float(1.0 - pt.x) * float(self.w)
                py = float(pt.y) * float(self.h)
                pz = float(pt.z) * float(self.w)
                pts_21[i] = [px, py, pz]

            self.hand_landmarks_21 = pts_21

            # 2. Calcular posición de interacción: punto medio entre Landmark 4 (Pulgar) y Landmark 8 (Índice)
            p4 = pts_21[4]
            p8 = pts_21[8]
            raw_inter_x = (float(p4[0]) + float(p8[0])) * 0.5
            raw_inter_y = (float(p4[1]) + float(p8[1])) * 0.5

            # 3. Aplicar OneEuroFilter2D (min_cutoff=0.40, beta=0.005, deadband=2.0)
            now_t = float(timestamp_ms) / 1000.0
            filtro_x, filtro_y = self.hand_filter.filter(
                (raw_inter_x, raw_inter_y), timestamp=now_t
            )
            inter_x_int = int(np.clip(round(filtro_x), 0, self.w - 1))
            inter_y_int = int(np.clip(round(filtro_y), 0, self.h - 1))
            self.hand_pos_actual = (inter_x_int, inter_y_int)

            # 4. Schmitt Trigger para Pinza (distancia < 0.23 activa, > 0.31 libera)
            # Normalizado por la escala de la palma (Landmark 0 a Landmark 9)
            dist_pinza_px = math.hypot(float(p8[0] - p4[0]), float(p8[1] - p4[1]))
            tam_palma_px = max(math.hypot(float(pts_21[9][0] - pts_21[0][0]), float(pts_21[9][1] - pts_21[0][1])), 1.0)
            ratio_distancia = dist_pinza_px / tam_palma_px

            # Bi-estable Schmitt Trigger
            if self.hand_pinch:
                if ratio_distancia > 0.31:
                    self.hand_pinch = False
            else:
                if ratio_distancia < 0.23:
                    self.hand_pinch = True

            return [{
                "pos": (inter_x_int, inter_y_int),
                "pinch": self.hand_pinch,
                "pts": pts_21,
            }]

        except Exception as e:
            logger.error(f"Error procesando frame en MediaPipe: {e}", exc_info=True)
            return []

    # -------------------------------------------------------------------------
    # Renderizado del HUD y Telemetría Multimodal
    # -------------------------------------------------------------------------
    def _dibujar_hud_modo(self, frame: np.ndarray) -> np.ndarray:
        """
        Dibuja un indicador persistente no intrusivo en el HUD superior
        con confirmación visual clara del modo de entrada activo.
        """
        # Dimensiones y posicionamiento de la insignia HUD superior
        badge_w = 340
        badge_h = 44
        badge_x = int((self.w - badge_w) // 2)
        badge_y = 12

        # Colores temáticos STARK
        es_raton = (self.input_mode == "mouse")
        color_acento = (255, 205, 30) if es_raton else (30, 255, 120)  # Cian/Dorado vs Verde Neón
        color_fondo = (20, 22, 28)

        # Panel translúcido (Badge superior centrado)
        sub_roi = frame[badge_y : badge_y + badge_h, badge_x : badge_x + badge_w]
        if sub_roi.shape[0] == badge_h and sub_roi.shape[1] == badge_w:
            rect_fondo = np.full_like(sub_roi, color_fondo, dtype=np.uint8)
            cv2.addWeighted(rect_fondo, 0.75, sub_roi, 0.25, 0.0, dst=sub_roi)

        # Borde biselado
        cv2.rectangle(
            frame,
            (badge_x, badge_y),
            (badge_x + badge_w, badge_y + badge_h),
            color_acento,
            1,
            cv2.LINE_AA,
        )

        # Texto del Modo Activo
        texto_modo = "[|] ENTRADA: RATON" if es_raton else "[|] ENTRADA: MANOS"
        cv2.putText(
            frame,
            texto_modo,
            (badge_x + 16, badge_y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        # Led de estado animado / punto indicador
        led_color = (0, 255, 0) if (es_raton or self.hand_landmarks_21 is not None) else (0, 165, 255)
        cv2.circle(
            frame,
            (badge_x + badge_w - 20, badge_y + 20),
            5,
            led_color,
            -1,
            cv2.LINE_AA,
        )

        # Sub-etiqueta de ayuda rápida
        sub_info = "Clic: Pinza / Arrastre" if es_raton else "Pinza: Pulgar-Indice (21 LMs)"
        cv2.putText(
            frame,
            sub_info,
            (badge_x + 16, badge_y + 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            color_acento,
            1,
            cv2.LINE_AA,
        )

        # Guía de controles inferior permanente
        cv2.putText(
            frame,
            "[|] Cambiar Entrada | [X] Despiece Radial | [R] Reset | [ESC] Salir Limpio",
            (int(15), int(self.h - 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )

        # Telemetría de FPS
        cv2.putText(
            frame,
            f"FPS: {self.fps:.1f}",
            (int(self.w - 110), 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 255, 120),
            1,
            cv2.LINE_AA,
        )

        return frame

    def _dibujar_esqueleto_mano(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja el esqueleto de 21 landmarks de la mano si está en modo 'hands'."""
        if self.input_mode != "hands" or self.hand_landmarks_21 is None:
            return frame

        pts = self.hand_landmarks_21
        color_hueso = (0, 255, 200)
        color_articulacion = (255, 255, 255)
        color_pinza = (0, 0, 255) if self.hand_pinch else (0, 255, 0)

        # Conexiones anatómicas estándar de MediaPipe
        conexiones = [
            # Pulgar
            (0, 1), (1, 2), (2, 3), (3, 4),
            # Índice
            (0, 5), (5, 6), (6, 7), (7, 8),
            # Medio
            (9, 10), (10, 11), (11, 12),
            # Anular
            (13, 14), (14, 15), (15, 16),
            # Meñique
            (0, 17), (17, 18), (18, 19), (19, 20),
            # Palma
            (5, 9), (9, 13), (13, 17),
        ]

        # Dibujar líneas óseas
        for p_ini, p_fin in conexiones:
            pt1 = (int(pts[p_ini][0]), int(pts[p_ini][1]))
            pt2 = (int(pts[p_fin][0]), int(pts[p_fin][1]))
            cv2.line(frame, pt1, pt2, color_hueso, 1, cv2.LINE_AA)

        # Dibujar articulaciones
        for idx in range(21):
            pt = (int(pts[idx][0]), int(pts[idx][1]))
            cv2.circle(frame, pt, 2, color_articulacion, -1, cv2.LINE_AA)

        # Dibujar retícula visual de interacción (Punto medio 4 y 8)
        if self.hand_pos_actual is not None:
            hx, hy = self.hand_pos_actual
            cv2.circle(frame, (hx, hy), 6, color_pinza, 2, cv2.LINE_AA)
            if self.hand_pinch:
                cv2.circle(frame, (hx, hy), 3, (0, 0, 255), -1, cv2.LINE_AA)

        return frame

    # -------------------------------------------------------------------------
    # Bucle Principal de Ejecución
    # -------------------------------------------------------------------------
    def ejecutar(self) -> None:
        """Bucle principal de renderizado, orquestación y captura de entrada."""
        cv2.namedWindow(self.titulo_ventana, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.titulo_ventana, self._mouse_callback)

        logger.info("Visor 3D Interactivo iniciado. Presiona '|' para alternar entrada, ESC para salir.")

        try:
            while True:
                ahora = time.perf_counter()
                dt = ahora - self.tiempo_prev
                self.tiempo_prev = ahora
                if dt > 0.0:
                    self.fps = 0.90 * self.fps + 0.10 * (1.0 / dt)

                timestamp_ms = int(time.time() * 1000)

                # =============================================================
                # FASE 2: ADAPTADOR UNIFICADO DE ENTRADA HÍBRIDA
                # =============================================================
                manos_simuladas: List[Dict[str, Any]] = []
                cursor_pos: Optional[Tuple[float, float]] = None

                if self.input_mode == "mouse":
                    # Desactiva temporalmente el proceso de MediaPipe para ahorrar CPU
                    manos_simuladas = [{
                        "pos": (int(self.mouse_x), int(self.mouse_y)),
                        "pinch": bool(self.mouse_pinch),
                    }]
                    cursor_pos = (float(self.mouse_x), float(self.mouse_y))

                elif self.input_mode == "hands":
                    # Instancia y evalúa MediaPipe HandLandmarker
                    frame_camara = None
                    if self.cap is not None and self.cap.isOpened():
                        ret, img = self.cap.read()
                        if ret and img is not None:
                            frame_camara = img

                    if frame_camara is None:
                        # Fallback a buffer negro si no hay cámara física disponible
                        frame_camara = np.zeros((self.h, self.w, 3), dtype=np.uint8)

                    manos_simuladas = self._procesar_entrada_manos(frame_camara, timestamp_ms)

                    if self.hand_pos_actual is not None:
                        cursor_pos = (float(self.hand_pos_actual[0]), float(self.hand_pos_actual[1]))
                    else:
                        cursor_pos = None

                # =============================================================
                # FASE 3: ACTUALIZACIÓN FSM Y RENDERIZADO 3D
                # =============================================================
                frame_buffer = np.zeros((self.h, self.w, 3), dtype=np.uint8)

                # Actualizar lógica 3D de forma agnóstica (HologramController)
                self.holo_ctrl.actualizar(frame_buffer, manos=manos_simuladas, cursor_pos=cursor_pos)

                # Renderizar escena 3D a través de BaseRenderer / GlRenderer
                frame_renderizado = self.renderer.renderizar_escena(
                    frame_buffer,
                    self.holo_ctrl.objeto_activo,
                    config=self.holo_ctrl.config,
                )

                # Renderizar menú lateral / radial
                frame_menu = self.menu.dibujar_menu(frame_renderizado, cursor_pos=cursor_pos)

                # Renderizar esqueleto en modo manos
                frame_esqueleto = self._dibujar_esqueleto_mano(frame_menu)

                # Renderizar HUD y badge superior de conmutación
                frame_final = self._dibujar_hud_modo(frame_esqueleto)

                # Procesar interacciones del menú selector si hubo clic
                if cursor_pos is not None:
                    pinch_activo = False
                    if len(manos_simuladas) > 0:
                        pinch_activo = bool(manos_simuladas[0].get("pinch", False))

                    gesto_menu = {
                        "es_clic_izquierdo": pinch_activo,
                        "pinch_agarrar": 0.15 if pinch_activo else 1.0,
                    }
                    accion_menu = self.menu.procesar_clic_virtual(cursor_pos, gesto_menu)
                    if accion_menu:
                        self._procesar_accion_menu(accion_menu)

                # Presentación de fotograma
                cv2.imshow(self.titulo_ventana, frame_final)

                # =============================================================
                # CONTROL DE TECLADO RÁPIDO
                # =============================================================
                key = cv2.waitKey(1) & 0xFF

                if key == 27:  # ESC: Salir
                    logger.info("Tecla ESC detectada. Iniciando cierre limpio...")
                    break
                elif key == 124 or key == ord("|"):  # Tecla '|' (ASCII 124): Conmutación en caliente
                    self.alternar_modo_entrada()
                elif key == ord("x") or key == ord("X"):  # 'x': Expandir/Contraer despiece radial
                    nuevo_factor = 1.0 if self.holo_ctrl.factor_explosion < 0.5 else 0.0
                    self.holo_ctrl.set_factor_explosion(nuevo_factor)
                    logger.info(f"Factor de explosion despiece alternado a: {nuevo_factor:.1f}")
                elif key == ord("r") or key == ord("R"):  # 'r': Reiniciar vista
                    self.holo_ctrl.reset()
                    logger.info("Transformaciones y orientacion de escena restablecidas.")

        except Exception as e:
            logger.error(f"Excepcion imprevista en el lazo principal: {e}", exc_info=True)
        finally:
            self.limpiar_recursos()

    def _procesar_accion_menu(self, accion: str) -> None:
        """Enruta los eventos disparados desde el menú interactivo a la escena 3D."""
        try:
            if accion == "DESPIECE":
                self.holo_ctrl.cargar_modelo_despiece()
            elif accion in ("ANATOMIA", "CORAZON"):
                self.holo_ctrl.cargar_modelo_anatomico(preset="corazon")
            elif accion == "CEREBRO":
                self.holo_ctrl.cargar_modelo_anatomico(preset="cerebro")
            elif accion == "ATOMO":
                self.holo_ctrl.cargar_modelo_atomico()
            elif accion == "MOLECULA":
                self.holo_ctrl.cargar_modelo_molecular()
            elif accion in ("MATH", "GRAFICADORA"):
                self.holo_ctrl.cargar_modelo_superficie()
            elif accion in ("CUBO", "ESFERA", "PIRAMIDE", "DONA"):
                self.holo_ctrl.cargar_modelo_primitiva(accion.lower())

            self.menu.vincular_escena(self.holo_ctrl.objeto_activo)
            logger.info(f"Modelo de escena actualizado mediante menu: '{accion}'")
        except Exception as e:
            logger.error(f"Error procesando accion del menu '{accion}': {e}", exc_info=True)

    def limpiar_recursos(self) -> None:
        """
        Libera estrictamente todos los recursos gráficos (VRAM en GlRenderer),
        captura de cámara y descriptores de ventana para evitar pérdidas de memoria.
        """
        logger.info("Liberando recursos de hardware y VRAM de OpenGL...")

        # 1. Liberar motor de renderizado y buffers VRAM
        try:
            if hasattr(self.renderer, "liberar"):
                self.renderer.liberar()
            elif hasattr(self.renderer, "liberar_recursos"):
                self.renderer.liberar_recursos()
        except Exception as e:
            logger.warning(f"Aviso al liberar GlRenderer: {e}")

        # 2. Cerrar detector MediaPipe HandLandmarker
        if self.detector_manos is not None:
            try:
                self.detector_manos.close()
                self.detector_manos = None
                logger.info("Detector MediaPipe cerrado.")
            except Exception as e:
                logger.warning(f"Aviso al cerrar HandLandmarker: {e}")

        # 3. Liberar captura de cámara
        if self.cap is not None:
            try:
                self.cap.release()
                self.cap = None
                logger.info("Dispositivo de camara liberado.")
            except Exception as e:
                logger.warning(f"Aviso al liberar VideoCapture: {e}")

        # 4. Destruir ventanas de OpenCV
        try:
            cv2.destroyAllWindows()
        except Exception as e:
            logger.warning(f"Aviso al destruir ventanas OpenCV: {e}")

        logger.info("Recursos liberados completamente. Proceso finalizado.")


def main() -> None:
    """Punto de entrada principal para la ejecución aislada del núcleo 3D."""
    orquestador = OrquestadorVisor3D(ancho=1280, alto=720)
    orquestador.ejecutar()


if __name__ == "__main__":
    main()
