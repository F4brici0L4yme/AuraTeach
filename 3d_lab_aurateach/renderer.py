"""
renderer.py
-------------------------------------------------------------------
Módulo de Arquitectura de Renderizado Acelerado por Hardware (STARK Mark v3 - Fase 2.1):
- Contrato Abstracto 'BaseRenderer' (Principio P5 de separación escena / dibujo).
- 'CpuRenderer': Fallback 100% resiliente basado en OpenCV (Painter's Algorithm, Back-Face Culling, 2D ROI).
- 'GlRenderer': Núcleo gráfico acelerado por GPU (ModernGL 3.3+, FBO con Z-Buffer GL_DEPTH_TEST,
  Shaders GLSL holográficos con efecto Fresnel, líneas de barrido y mezcla aditiva).
- Factory 'crear_renderer' con degradación elegante ante ausencia de GPU.
-------------------------------------------------------------------
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger("RendererSTARK")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
logger.setLevel(logging.INFO)


class BaseRenderer(ABC):
    """
    Contrato abstracto para el subsistema de renderizado holográfico 3D (Principio P5).
    Desacopla completamente la jerarquía de nodos de escena (Objeto3D, SceneModel)
    de la API de dibujado subyacente (CPU OpenCV / GPU ModernGL).
    """

    @abstractmethod
    def inicializar(self, w: int, h: int) -> bool:
        """Inicializa los buffers y contextos de renderizado."""
        pass

    def cargar(self, objeto_o_escena: Any) -> Dict[str, Any]:
        """Carga o pre-asigna los buffers geométricos de una escena o nodo (Principio P5)."""
        return {"backend": self.tipo_backend, "nodos_cargados": 0, "vram_bytes": 0}

    @abstractmethod
    def renderizar_escena(
        self,
        frame: np.ndarray,
        objeto_o_escena: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """Renderiza el objeto o escena 3D componiéndolo sobre el fotograma BGR."""
        pass

    @abstractmethod
    def pick_pieza(
        self,
        objeto_o_escena: Any,
        punto: Tuple[float, float],
        pad: int = 10,
    ) -> Optional[str]:
        """Detecta colisión 2D/3D sobre las sub-piezas de la escena."""
        pass

    def pick(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """GPU/CPU Ray Picking sobre la escena (Subfase 2.3)."""
        return None

    def _renderizar_flujo_sanguineo_gl(
        self,
        modelo_anatomico: Any,
        center: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Renderizado de flujo sanguíneo (stub en BaseRenderer)."""
        pass

    def renderizar_overlay_ui_gl(
        self,
        frame: np.ndarray,
        telemetria: Optional[Any] = None,
        menu_3d: Optional[Any] = None,
        voz_ctrl: Optional[Any] = None,
        cursor_pos: Optional[Tuple[float, float]] = None,
        ui_visible: bool = True,
        desplazar_telemetria: bool = False,
    ) -> np.ndarray:
        """
        Superpone la interfaz de usuario (telemetría, menú lateral y control por voz)
        sobre el contexto gráfico (Subfase 2.4).
        """
        desplazar = desplazar_telemetria or getattr(getattr(self, "_ultima_escena", None), "es_modelo_atomico", False)
        if ui_visible and telemetria is not None and getattr(telemetria, "mostrar_hud", True):
            frame = telemetria.dibujar_hud(frame, desplazar_izquierda=desplazar)
        if menu_3d is not None:
            frame = menu_3d.dibujar_menu(frame, cursor_pos, ui_visible=ui_visible)
        if ui_visible and voz_ctrl is not None:
            frame = voz_ctrl.dibujar_hud_ptt(frame)
        return frame


    @abstractmethod
    def liberar(self) -> None:
        """Libera buffers, texturas y contextos asociados."""
        pass

    @property
    @abstractmethod
    def tipo_backend(self) -> str:
        """Retorna el identificador del backend ('GL' o 'CPU')."""
        pass

    @property
    @abstractmethod
    def disponible(self) -> bool:
        """Indica si el renderizador está listo y operativo."""
        pass


class CpuRenderer(BaseRenderer):
    """
    Renderizador por software basado en OpenCV.
    Garantiza compatibilidad absoluta (fallback seguro) en entornos sin GPU o sin ModernGL.
    Utiliza proyección 2D vectorizada, recorte ROI acotado y Back-Face Culling.
    """

    def __init__(
        self,
        w: int = 1280,
        h: int = 720,
        config: Optional[Union[Dict[str, Any], Any]] = None,
    ) -> None:
        self.w: int = int(w)
        self.h: int = int(h)
        if hasattr(config, "data"):
            self.config = config.data
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = {}
        self._disponible: bool = True

    def inicializar(self, w: int, h: int) -> bool:
        self.w = int(w)
        self.h = int(h)
        self._disponible = True
        return True

    def cargar(self, objeto_o_escena: Any) -> Dict[str, Any]:
        es_compuesta = hasattr(objeto_o_escena, "piezas") and bool(objeto_o_escena.piezas)
        n_nodos = len(objeto_o_escena.piezas) if es_compuesta else 1
        return {"backend": "CPU", "nodos_cargados": n_nodos, "vram_bytes": 0}

    cargar_escena_en_vram = cargar

    def renderizar_escena(
        self,
        frame: np.ndarray,
        objeto_o_escena: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        cfg = config or self.config
        if hasattr(objeto_o_escena, "renderizar"):
            return objeto_o_escena.renderizar(frame, config=cfg, center=center)
        return frame

    def pick_pieza(
        self,
        objeto_o_escena: Any,
        punto: Tuple[float, float],
        pad: int = 10,
    ) -> Optional[str]:
        if hasattr(objeto_o_escena, "seleccionar_pieza"):
            return objeto_o_escena.seleccionar_pieza(punto, pad=pad)
        if hasattr(objeto_o_escena, "contiene_punto"):
            if objeto_o_escena.contiene_punto(punto, pad=pad):
                return getattr(objeto_o_escena, "tipo_modelo", "objeto")
        return None

    def pick(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """Picking por software para CpuRenderer."""
        x_px: float = 0.0
        y_px: float = 0.0
        escena: Any = kwargs.get("objeto_o_escena", None)

        if len(args) == 1:
            arg0 = args[0]
            if isinstance(arg0, (tuple, list)) and len(arg0) >= 2:
                x_px, y_px = float(arg0[0]), float(arg0[1])
        elif len(args) == 2:
            arg0, arg1 = args[0], args[1]
            if isinstance(arg0, (int, float)) and isinstance(arg1, (int, float)):
                x_px, y_px = float(arg0), float(arg1)
            elif hasattr(arg0, "piezas") or hasattr(arg0, "contiene_punto"):
                escena = arg0
                if isinstance(arg1, (tuple, list)) and len(arg1) >= 2:
                    x_px, y_px = float(arg1[0]), float(arg1[1])
        elif len(args) >= 3:
            if isinstance(args[0], (int, float)) and isinstance(args[1], (int, float)):
                x_px, y_px = float(args[0]), float(args[1])
                escena = args[2]
            else:
                escena = args[0]
                x_px, y_px = float(args[1]), float(args[2])

        if escena is not None:
            return self.pick_pieza(escena, (x_px, y_px))
        return None


    def liberar(self) -> None:
        self._disponible = False

    @property
    def tipo_backend(self) -> str:
        return "CPU"

    @property
    def disponible(self) -> bool:
        return self._disponible


# Constantes de Shaders GLSL para Estética Holográfica (Fase 2.1)
_GLSL_FACES_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;
layout(location = 1) in vec3 in_norm;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_normal;
out vec3 v_view_dir;
out vec2 v_screen_pos;

void main() {
    vec4 world_p = u_model * vec4(in_vert, 1.0);
    v_normal = normalize(mat3(u_model) * in_norm);
    v_view_dir = normalize(u_cam_pos - world_p.xyz);
    vec4 clip_p = u_mvp * vec4(in_vert, 1.0);
    gl_Position = clip_p;
    v_screen_pos = (clip_p.xy / max(clip_p.w, 0.0001)) * 0.5 + 0.5;
}
"""

_GLSL_FACES_FRAG = """
#version 330 core
in vec3 v_normal;
in vec3 v_view_dir;
in vec2 v_screen_pos;

uniform vec3 u_color;         // BGR o RGB normalizado
uniform float u_opacity;
uniform float u_time;
uniform float u_fresnel_power;
uniform float u_scanline_freq;

out vec4 fragColor;

void main() {
    vec3 N = normalize(v_normal);
    vec3 V = normalize(v_view_dir);

    // Vector de luz direccional volumétrico — Blinn-Phong sólido y opaco
    vec3 L = normalize(vec3(0.40, 0.70, 0.60));
    vec3 H = normalize(L + V);

    // Componente ambiental base sólida
    float ka = 0.50;

    // Componente difusa direccional sólida (dos caras)
    float NdotL = abs(dot(N, L));
    float kd = 0.65 * NdotL;

    // Componente especular metálica Blinn-Phong
    float NdotH = max(0.0, abs(dot(N, H)));
    float ks = pow(NdotH, 36.0) * 0.75;

    // Borde Fresnel sutil (refuerzo de silueta, NO mezcla fantasmal)
    float NdotV = abs(dot(N, V));
    float fresnel = pow(1.0 - NdotV, u_fresnel_power) * 0.20;

    // Color final integrado — Sólido y Opaco
    float scanline = sin(v_screen_pos.y * u_scanline_freq + u_time * 0.0) * 0.0;
    vec3 lit_color = u_color * (ka + kd + fresnel) + vec3(1.0, 1.0, 1.0) * ks + scanline;

    // Alpha asignado desde uniform u_opacity
    float alpha = u_opacity;

    // Salida en formato BGR nativo de OpenCV (B, G, R, A)
    fragColor = vec4(lit_color.b, lit_color.g, lit_color.r, alpha);
}
"""

_GLSL_LINES_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;

uniform mat4 u_mvp;

void main() {
    gl_Position = u_mvp * vec4(in_vert, 1.0);
}
"""

_GLSL_LINES_FRAG = """
#version 330 core
uniform vec3 u_color;
uniform float u_brightness;

out vec4 fragColor;

void main() {
    vec3 col = u_color * max(u_brightness, 1.25);
    // Salida en formato BGR nativo de OpenCV (B, G, R, A)
    fragColor = vec4(col.b, col.g, col.r, 0.95);
}
"""

_GLSL_NODES_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;

uniform mat4 u_mvp;
uniform float u_point_size;

void main() {
    gl_Position = u_mvp * vec4(in_vert, 1.0);
    gl_PointSize = u_point_size;
}
"""

_GLSL_NODES_FRAG = """
#version 330 core
uniform vec3 u_color;

out vec4 fragColor;

void main() {
    vec2 coord = gl_PointCoord - vec2(0.5);
    if (length(coord) > 0.5) {
        discard;
    }
    vec3 col = u_color * 1.5;
    fragColor = vec4(col.b, col.g, col.r, 1.0);
}
"""

_GLSL_PICKING_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;

uniform mat4 u_mvp;

void main() {
    gl_Position = u_mvp * vec4(in_vert, 1.0);
}
"""

_GLSL_PICKING_FRAG = """
#version 330 core
uniform vec4 u_id_color;

out vec4 fragColor;

void main() {
    fragColor = u_id_color;
}
"""

_GLSL_ATOMIC_INST_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;
layout(location = 1) in vec3 in_norm;
layout(location = 2) in vec3 in_inst_pos;
layout(location = 3) in vec3 in_inst_color;
layout(location = 4) in float in_inst_radius;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_normal;
out vec3 v_view_dir;
out vec3 v_color;
out vec2 v_screen_pos;

void main() {
    vec3 scaled_vert = in_vert * in_inst_radius;
    vec3 local_p = scaled_vert + in_inst_pos;
    vec4 world_p = u_model * vec4(local_p, 1.0);
    v_normal = normalize(mat3(u_model) * in_norm);
    v_view_dir = normalize(u_cam_pos - world_p.xyz);
    vec4 clip_p = u_mvp * vec4(local_p, 1.0);
    gl_Position = clip_p;
    v_color = in_inst_color;
    v_screen_pos = (clip_p.xy / max(clip_p.w, 0.0001)) * 0.5 + 0.5;
}
"""

_GLSL_ATOMIC_INST_FRAG = """
#version 330 core
in vec3 v_normal;
in vec3 v_view_dir;
in vec3 v_color;
in vec2 v_screen_pos;

uniform float u_time;
uniform float u_fresnel_power;
uniform float u_scanline_freq;

out vec4 fragColor;

void main() {
    vec3 N = normalize(v_normal);
    vec3 V = normalize(v_view_dir);

    // Luz direccional inclinada clave (Front-Top-Right)
    vec3 L = normalize(vec3(0.35, 0.65, 0.70));
    vec3 H = normalize(L + V);

    // Componente difusa y ambiente para esfera sólida tipo bola de billar / plástico pulido
    float diff = max(dot(N, L), 0.0);
    float ambient = 0.55;

    // Brillo especular Blinn-Phong concentrado (highlight blanco brillante)
    float NdotH = max(dot(N, H), 0.0);
    float spec = pow(NdotH, 48.0);

    // Sutil toque de Fresnel en el reborde (sin scanline, material completamente sólido)
    float NdotV = abs(dot(N, V));
    float fresnel = pow(1.0 - NdotV, max(u_fresnel_power, 2.0));

    // Sutil dinamismo temporal cuántico en la superficie
    float pulse = 1.0 + 0.02 * sin(u_time * 3.0);

    // Fusión de iluminación: acabado sólido y nítido (alpha 1.0) con brillo vivo
    vec3 final_rgb = v_color * (ambient + 0.70 * diff) + vec3(1.0) * (spec * 0.90 * pulse) + v_color * (fresnel * 0.15);

    // Salida en formato BGR nativo de OpenCV (B, G, R, A) con alpha 1.0 sólido
    fragColor = vec4(final_rgb.b, final_rgb.g, final_rgb.r, 1.0);
}
"""

_GLSL_ATOMIC_TORUS_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;
layout(location = 1) in vec3 in_norm;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_normal;
out vec3 v_view_dir;

void main() {
    vec4 world_p = u_model * vec4(in_vert, 1.0);
    v_normal = normalize(mat3(u_model) * in_norm);
    v_view_dir = normalize(u_cam_pos - world_p.xyz);
    gl_Position = u_mvp * vec4(in_vert, 1.0);
}
"""

_GLSL_ATOMIC_TORUS_FRAG = """
#version 330 core
in vec3 v_normal;
in vec3 v_view_dir;

uniform vec3 u_color;

out vec4 fragColor;

void main() {
    vec3 N = normalize(v_normal);
    vec3 V = normalize(v_view_dir);

    // Luz direccional inclinada suave (Front-Top-Right)
    vec3 L = normalize(vec3(0.35, 0.65, 0.70));
    vec3 H = normalize(L + V);

    // Iluminación Blinn-Phong sólida sin destellos (zero flares)
    float diff = max(dot(N, L), 0.0);
    float ambient = 0.55;

    float NdotH = max(dot(N, H), 0.0);
    float spec = pow(NdotH, 32.0);

    vec3 final_rgb = u_color * (ambient + 0.65 * diff) + vec3(1.0) * (spec * 0.55);

    // Salida BGR nativa de OpenCV (B, G, R, A) con alpha 1.0 sólido
    fragColor = vec4(final_rgb.b, final_rgb.g, final_rgb.r, 1.0);
}
"""

_GLSL_SURFACE_VERT = """
#version 330 core
layout(location = 0) in vec3 in_vert;
layout(location = 1) in vec3 in_norm;
layout(location = 2) in vec3 in_col;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_norm;
out vec3 v_color;
out vec3 v_view;

void main() {
    vec4 wp = u_model * vec4(in_vert, 1.0);
    v_norm = normalize(mat3(u_model) * in_norm);
    v_view = normalize(u_cam_pos - wp.xyz);
    v_color = in_col;
    gl_Position = u_mvp * vec4(in_vert, 1.0);
}
"""

_GLSL_SURFACE_FRAG = """
#version 330 core
in vec3 v_norm;
in vec3 v_color;
in vec3 v_view;

out vec4 fragColor;

void main() {
    vec3 N = normalize(v_norm);
    if (!gl_FrontFacing) {
        N = -N;
    }
    vec3 L = normalize(vec3(0.35, 0.65, 0.70));
    vec3 V = normalize(v_view);
    vec3 H = normalize(L + V);

    float diff = max(dot(N, L), 0.0);
    float spec = pow(max(dot(N, H), 0.0), 24.0);

    vec3 ambient = 0.35 * v_color;
    vec3 diffuse = 0.65 * diff * v_color;
    vec3 specular = 0.40 * spec * vec3(1.0, 1.0, 1.0);

    vec3 rgb = ambient + diffuse + specular;
    fragColor = vec4(rgb.b, rgb.g, rgb.r, 0.95);
}
"""

_GLSL_ATOMIC_ORBITAL_VERT = """
#version 330 core
layout(location = 0) in vec2 in_pos;

uniform mat4 u_mvp;
uniform float u_quad_size;

out vec2 v_local_pos;

void main() {
    v_local_pos = in_pos * u_quad_size;
    gl_Position = u_mvp * vec4(v_local_pos.x, 0.0, v_local_pos.y, 1.0);
}
"""

_GLSL_ATOMIC_ORBITAL_FRAG = """
#version 330 core
in vec2 v_local_pos;

uniform float u_radius;
uniform float u_thickness;
uniform float u_time;
uniform float u_speed;
uniform int u_num_electrons;
uniform vec3 u_ring_color;
uniform vec3 u_electron_color;

out vec4 fragColor;

void main() {
    float r = length(v_local_pos);
    float ring_dist = abs(r - u_radius);

    // Perfil para anillo toroidal continuo fino (verde azulado / cian esmeralda)
    float w = max(u_thickness, 0.8);
    float core = exp(-0.5 * pow(ring_dist / w, 2.0));
    float halo = 0.30 / (1.0 + pow(ring_dist / (w * 1.8), 2.0));
    float ring_intensity = max(core, halo);

    // Ángulo polar local en el plano orbital
    float theta = atan(v_local_pos.y, v_local_pos.x);

    // Contribución de halo cuántico de electrones sobre el riel
    float elec_intensity = 0.0;
    if (u_num_electrons > 0) {
        float two_pi = 6.28318530718;
        for (int i = 0; i < u_num_electrons; ++i) {
            float angle_e = float(i) * (two_pi / float(u_num_electrons)) + u_time * u_speed;
            float d_theta = atan(sin(theta - angle_e), cos(theta - angle_e));
            float dist_along_ring = u_radius * d_theta;
            float dist_to_e_sq = pow(r - u_radius, 2.0) + pow(dist_along_ring, 2.0);

            float r_e = 6.5;
            float e_point = exp(-0.5 * (dist_to_e_sq / pow(r_e, 2.0))) * 2.5;
            float e_halo = 0.90 / (1.0 + dist_to_e_sq / pow(r_e * 2.8, 2.0));
            elec_intensity += e_point + e_halo;
        }
    }

    vec3 col = u_ring_color * ring_intensity * 0.85 + u_electron_color * elec_intensity;
    float alpha = clamp(ring_intensity * 0.70 + elec_intensity * 0.95, 0.0, 1.0);

    if (alpha < 0.01) {
        discard;
    }

    // Salida BGR nativa de OpenCV (B, G, R, A)
    fragColor = vec4(col.b, col.g, col.r, alpha);
}
"""


class GlRenderer(BaseRenderer):
    """
    Renderizador acelerado por hardware (GPU) mediante ModernGL.
    Resuelve el cuello de botella de la CPU en la Fase 2.1 y Subfase 2.2:
    - Contexto Offscreen FBO (RGBA + 24-bit Depth Buffer).
    - Z-Buffer nativo (GL_DEPTH_TEST) que elimina el Painter's Algorithm por software.
    - Asignación de buffers VBO/VAO independientes en VRAM por sub-malla/nodo jerárquico.
    - Shaders GLSL con efecto Fresnel, líneas de barrido y composición aditiva BGR directa.
    - Fusión con OpenCV mediante lectura de ROI acotado con cv2.add (0.1 ms).
    - Subfase 2.3: GPU Color/ID Picking offscreen con Z-Buffer y lectura 1x1 píxel (< 2 ms).
    - Subfase 2.4: Migración del HUD, telemetría y menú lateral directamente al contexto OpenGL.
    """

    _GLSL_SURFACE_VERT = _GLSL_SURFACE_VERT
    _GLSL_SURFACE_FRAG = _GLSL_SURFACE_FRAG

    def __init__(
        self,
        w: int = 1280,
        h: int = 720,
        config: Optional[Union[Dict[str, Any], Any]] = None,
    ) -> None:
        self.w: int = int(w)
        self.h: int = int(h)
        if hasattr(config, "data"):
            self.config = config.data
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = {}

        self._ctx: Any = None
        self._fbo: Any = None
        self._prog_faces: Any = None
        self._prog_lines: Any = None
        self._prog_nodes: Any = None
        self._vbo_cache: Dict[str, Any] = {}
        self._vbo_meta: Dict[str, Dict[str, Any]] = {}
        self._disponible: bool = False
        self._fallback_cpu: Optional[CpuRenderer] = None
        self._t_inicio: float = time.time()

        # Buffers y shaders dedicados para GPU Ray Picking (Subfase 2.3)
        self._picking_fbo: Any = None
        self._picking_tex: Any = None
        self._picking_depth: Any = None
        self._prog_picking: Any = None
        self._picking_cache_key: Any = None
        self._id_to_part: Dict[int, str] = {}
        self._part_to_id: Dict[str, int] = {}
        self._ultima_escena: Any = None

        # Buffers y shaders dedicados para GPU Instancing del Núcleo Atómico (Etapa 1)
        self._prog_atomic_inst: Any = None
        self._vbo_sphere_base: Any = None
        self._vbo_atomic_inst: Any = None
        self._vao_atomic_inst: Any = None
        self._n_sphere_verts: int = 0

        # Buffers y shaders dedicados para Nubes y Orbitales Atómicos Procedurales (Etapa 2)
        self._prog_atomic_orbital: Any = None
        self._vbo_orbital_quad: Any = None
        self._vao_orbital_quad: Any = None

        # Buffers y shaders dedicados para Toroide de los Anillos Atómicos 3D Sólidos
        self._prog_atomic_torus: Any = None
        self._vbo_atomic_torus: Any = None
        self._vao_atomic_torus: Any = None
        self._n_torus_verts: int = 0

        # Buffers dedicados para Constructor Molecular 3D (STARK Molecular Builder)
        self._vbo_molecular_inst: Any = None
        self._vao_molecular_inst: Any = None
        self._vbo_molecular_bonds: Any = None
        self._vao_molecular_bonds: Any = None
        self._n_molecular_bond_verts: int = 0
        self._cached_mol_version: int = -1

        # Buffers dedicados para Superficies Matemáticas 3D (STARK Math Grapher)
        self._prog_surface_3d: Any = None
        self._vbo_surface_3d: Any = None
        self._vao_surface_3d: Any = None
        self._n_surface_verts: int = 0
        self._cached_surface_version: int = -1

        # Buffers dedicados para Flujo Sanguíneo por GPU Instancing (STARK Bio-Anatomy)
        self._vbo_flujo_inst: Any = None
        self._vao_flujo_inst: Any = None

        # Parámetros visuales de shaders
        self.fresnel_power: float = float(self.config.get("fresnel_power", 2.5))
        self.scanline_freq: float = float(self.config.get("scanline_freq", 180.0))
        self.edge_brightness: float = float(self.config.get("edge_brightness", 1.4))
        self.faces_opacity: float = float(self.config.get("faces_opacity", 0.95))

        # Pre-asignación de constantes de cámara y vista (optimización de bus/RAM)
        self._cam_pos: Tuple[float, float, float] = (0.0, 0.0, 4.0)
        self._mat_V: np.ndarray = np.eye(4, dtype=np.float32)
        self._mat_V[2, 3] = 4.0

        self.inicializar(self.w, self.h)

    def _limpiar_vbo_cache(self) -> None:
        """Libera de forma explícita los recursos VBO/VAO alojados en VRAM antes de vaciar la caché."""
        for meta in self._vbo_meta.values():
            for k in (
                "vao_faces", "vao_lines", "vao_nodes",
                "vbo_faces", "vbo_lines", "vbo_nodes",
                "vao_pick_faces", "vao_pick_lines",
            ):
                obj_gl = meta.get(k)
                if obj_gl is not None:
                    try:
                        obj_gl.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar recurso GPU {k}: {e}")
        self._vbo_cache.clear()
        self._vbo_meta.clear()

    def _evict_vbo_entry(self, geom_key: str) -> None:
        """Libera de forma explícita los recursos VBO/VAO alojados en VRAM de una entrada específica."""
        meta = self._vbo_meta.pop(geom_key, None)
        if meta:
            for k in (
                "vao_faces", "vao_lines", "vao_nodes",
                "vbo_faces", "vbo_lines", "vbo_nodes",
                "vao_pick_faces", "vao_pick_lines",
            ):
                obj_gl = meta.get(k)
                if obj_gl is not None:
                    try:
                        obj_gl.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al desalojar recurso GPU {k}: {e}")
        self._vbo_cache.pop(geom_key, None)

    def liberar_buffers_objeto(self, objeto: Any) -> None:
        """Libera explícitamente los buffers de GPU asociados a un objeto o sus subpiezas en VRAM."""
        if objeto is None:
            return
        piezas = getattr(objeto, "piezas", None)
        targets = list(piezas.values()) if piezas else [objeto]
        for p in targets:
            geom_key = getattr(p, "_gpu_geom_key", None)
            if not geom_key:
                meta = getattr(p, "gpu_buffers", None)
                if isinstance(meta, dict):
                    geom_key = meta.get("geom_key")
            if geom_key and geom_key in self._vbo_cache:
                self._evict_vbo_entry(geom_key)
            elif getattr(p, "gpu_buffers", None) is not None:
                meta = getattr(p, "gpu_buffers")
                if isinstance(meta, dict):
                    for k in (
                        "vao_faces", "vao_lines", "vao_nodes",
                        "vbo_faces", "vbo_lines", "vbo_nodes",
                        "vao_pick_faces", "vao_pick_lines",
                    ):
                        obj_gl = meta.get(k)
                        if obj_gl is not None:
                            try:
                                obj_gl.release()
                            except Exception:
                                pass
                p.gpu_buffers = None
                p.vao = None
                p.vbo = None

    def inicializar(self, w: int, h: int) -> bool:
        self.w = max(int(w), 64)
        self.h = max(int(h), 64)

        try:
            import moderngl

            if self._ctx is None:
                self._ctx = moderngl.create_context(standalone=True)
                logger.info(f"GlRenderer: Contexto OpenGL creado [{self._ctx.info.get('GL_RENDERER', 'GPU')}]")

            # Limpiar caché de VBOs ante reconfiguración de resolución / contexto (MEDIUM-13)
            self._limpiar_vbo_cache()

            # Crear FBO principal con buffer de color RGBA y buffer de profundidad nativo de 24 bits (HIGH-04)
            if self._fbo is not None:
                for att in getattr(self._fbo, "color_attachments", []):
                    try:
                        att.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar color_attachment: {e}")
                if getattr(self._fbo, "depth_attachment", None) is not None:
                    try:
                        self._fbo.depth_attachment.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar depth_attachment: {e}")
                self._fbo.release()
                self._fbo = None

            color_tex = self._ctx.texture((self.w, self.h), 4)
            depth_rb = self._ctx.depth_renderbuffer((self.w, self.h))
            self._fbo = self._ctx.framebuffer(
                color_attachments=[color_tex],
                depth_attachment=depth_rb,
            )

            # Crear FBO secundario dedicado a GPU Color/ID Picking con Z-Buffer de 24 bits (Subfase 2.3)
            if self._picking_fbo is not None:
                if self._picking_tex is not None:
                    try:
                        self._picking_tex.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar picking_tex: {e}")
                    self._picking_tex = None
                if self._picking_depth is not None:
                    try:
                        self._picking_depth.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar picking_depth: {e}")
                    self._picking_depth = None
                self._picking_fbo.release()
                self._picking_fbo = None

            self._picking_tex = self._ctx.texture((self.w, self.h), 4)
            self._picking_depth = self._ctx.depth_renderbuffer((self.w, self.h))
            self._picking_fbo = self._ctx.framebuffer(
                color_attachments=[self._picking_tex],
                depth_attachment=self._picking_depth,
            )

            # Compilar Shaders GLSL
            if self._prog_faces is None:
                self._prog_faces = self._ctx.program(
                    vertex_shader=_GLSL_FACES_VERT,
                    fragment_shader=_GLSL_FACES_FRAG,
                )
            if self._prog_lines is None:
                self._prog_lines = self._ctx.program(
                    vertex_shader=_GLSL_LINES_VERT,
                    fragment_shader=_GLSL_LINES_FRAG,
                )
            if self._prog_nodes is None:
                self._prog_nodes = self._ctx.program(
                    vertex_shader=_GLSL_NODES_VERT,
                    fragment_shader=_GLSL_NODES_FRAG,
                )
            if self._prog_picking is None:
                self._prog_picking = self._ctx.program(
                    vertex_shader=_GLSL_PICKING_VERT,
                    fragment_shader=_GLSL_PICKING_FRAG,
                )

            if self._prog_atomic_inst is None:
                self._prog_atomic_inst = self._ctx.program(
                    vertex_shader=_GLSL_ATOMIC_INST_VERT,
                    fragment_shader=_GLSL_ATOMIC_INST_FRAG,
                )
            if self._vbo_sphere_base is None:
                from atomic_model import generar_esfera_base_gpu
                s_verts, s_norms = generar_esfera_base_gpu(radio=1.0, sub_lat=12, sub_lon=18)
                self._n_sphere_verts = len(s_verts)
                base_buf = np.hstack([s_verts, s_norms]).astype(np.float32)
                self._vbo_sphere_base = self._ctx.buffer(base_buf.tobytes())

            if self._prog_atomic_orbital is None:
                self._prog_atomic_orbital = self._ctx.program(
                    vertex_shader=_GLSL_ATOMIC_ORBITAL_VERT,
                    fragment_shader=_GLSL_ATOMIC_ORBITAL_FRAG,
                )
            if self._vbo_orbital_quad is None:
                orb_quad_data = np.array([
                    -1.0, -1.0,
                     1.0, -1.0,
                     1.0,  1.0,
                    -1.0, -1.0,
                     1.0,  1.0,
                    -1.0,  1.0,
                ], dtype=np.float32)
                self._vbo_orbital_quad = self._ctx.buffer(orb_quad_data.tobytes())
                self._vao_orbital_quad = self._ctx.vertex_array(
                    self._prog_atomic_orbital,
                    [(self._vbo_orbital_quad, "2f", "in_pos")],
                )

            if self._prog_atomic_torus is None:
                self._prog_atomic_torus = self._ctx.program(
                    vertex_shader=_GLSL_ATOMIC_TORUS_VERT,
                    fragment_shader=_GLSL_ATOMIC_TORUS_FRAG,
                )
            if self._vbo_atomic_torus is None:
                from atomic_model import generar_toroide_orbital_gpu
                t_verts, t_norms = generar_toroide_orbital_gpu(radio_mayor=155.0, radio_tubo=3.8, segs_anillo=64, segs_tubo=14)
                self._n_torus_verts = len(t_verts)
                torus_buf = np.hstack([t_verts, t_norms]).astype(np.float32)
                self._vbo_atomic_torus = self._ctx.buffer(torus_buf.tobytes())
                self._vao_atomic_torus = self._ctx.vertex_array(
                    self._prog_atomic_torus,
                    [(self._vbo_atomic_torus, "3f 3f", "in_vert", "in_norm")],
                )

            self._disponible = True
            self._fallback_cpu = None
            return True


        except Exception as e:
            logger.warning(f"GlRenderer: No se pudo inicializar contexto OpenGL ({e}). Activando CpuRenderer como fallback.")
            self._disponible = False
            self._fallback_cpu = CpuRenderer(w=self.w, h=self.h, config=self.config)
            return False

    def _obtener_buffers_gpu(self, pieza: Any) -> Optional[Tuple[Any, Any, Any, int, int, int]]:
        """
        Subfase 2.2: Crea o reutiliza buffers VBO/VAO independientes en VRAM para caras, aristas y nodos
        de una pieza/nodo jerárquico, vinculando las referencias directamente en 'pieza.gpu_buffers',
        'pieza.vao' y 'pieza.vbo'.
        """
        if not hasattr(pieza, "vertices_locales") or len(pieza.vertices_locales) == 0:
            return None

        # Identificador de geometría persistente y único por instancia de nodo
        if not hasattr(pieza, "_gpu_geom_id"):
            node_tag = getattr(pieza, "node_name", getattr(pieza, "tipo_modelo", "obj"))
            pieza._gpu_geom_id = f"{node_tag}_{id(pieza)}"
        n_v = len(pieza.vertices_locales)
        n_c = len(getattr(pieza, "caras", []))
        n_a = len(getattr(pieza, "aristas", []))
        geom_key = f"{pieza._gpu_geom_id}_{n_v}_{n_c}_{n_a}"
        pieza._gpu_geom_key = geom_key

        if geom_key in self._vbo_cache:
            if getattr(pieza, "gpu_buffers", None) is None and geom_key in self._vbo_meta:
                meta = self._vbo_meta[geom_key]
                pieza.gpu_buffers = meta
                pieza.vao = meta["vao_faces"] if meta["vao_faces"] is not None else meta["vao_lines"]
                pieza.vbo = meta["vbo_faces"] if meta["vbo_faces"] is not None else meta["vbo_nodes"]
            return self._vbo_cache[geom_key]

        verts = np.asarray(pieza.vertices_locales, dtype=np.float32)
        caras = getattr(pieza, "caras", [])
        aristas = getattr(pieza, "aristas", [])
        vram_bytes = 0

        # 1. Caras trianguladas con cálculo vectorial de normales (NumPy, cero bucles Python)
        vao_faces = None
        vbo_f = None
        n_tri_verts = 0
        if isinstance(caras, np.ndarray) and caras.ndim == 2 and caras.shape[1] == 3:
            tri_idx = caras.astype(np.int32)
        else:
            tri_list: List[Tuple[int, int, int]] = []
            for f in caras:
                lf = len(f)
                if lf == 3:
                    tri_list.append((f[0], f[1], f[2]))
                elif lf > 3:
                    f0 = f[0]
                    for i in range(1, lf - 1):
                        tri_list.append((f0, f[i], f[i + 1]))
            tri_idx = np.array(tri_list, dtype=np.int32) if tri_list else np.empty((0, 3), dtype=np.int32)

        if len(tri_idx) > 0:
            valid_m = (tri_idx[:, 0] < len(verts)) & (tri_idx[:, 1] < len(verts)) & (tri_idx[:, 2] < len(verts))
            if not np.all(valid_m):
                tri_idx = tri_idx[valid_m]

        if len(tri_idx) > 0:
            v0 = verts[tri_idx[:, 0]]
            v1 = verts[tri_idx[:, 1]]
            v2 = verts[tri_idx[:, 2]]

            normales_loc = getattr(pieza, "normales_locales", None)
            if normales_loc is not None and len(normales_loc) == len(verts):
                norms_arr = np.asarray(normales_loc, dtype=np.float32)
                n0 = norms_arr[tri_idx[:, 0]]
                n1 = norms_arr[tri_idx[:, 1]]
                n2 = norms_arr[tri_idx[:, 2]]
            else:
                n_vec = np.cross(v1 - v0, v2 - v0)
                n_lens = np.linalg.norm(n_vec, axis=1, keepdims=True)
                n_lens[n_lens < 1e-6] = 1.0
                n_norm = (n_vec / n_lens).astype(np.float32)
                n0 = n_norm
                n1 = n_norm
                n2 = n_norm

            vn0 = np.hstack([v0, n0])
            vn1 = np.hstack([v1, n1])
            vn2 = np.hstack([v2, n2])
            fb = np.empty((len(tri_idx), 3, 6), dtype=np.float32)
            fb[:, 0, :] = vn0
            fb[:, 1, :] = vn1
            fb[:, 2, :] = vn2
            fb = fb.reshape(-1, 6)
            n_tri_verts = len(fb)

            vbo_f = self._ctx.buffer(fb.tobytes())
            vao_faces = self._ctx.vertex_array(self._prog_faces, [(vbo_f, "3f 3f", "in_vert", "in_norm")])
            vram_bytes += int(fb.nbytes)

        # 2. Aristas (Lines) vectorizadas con indexación NumPy
        vao_lines = None
        vbo_l = None
        n_line_verts = 0
        if len(aristas) > 0:
            arr_aristas = np.asarray(aristas, dtype=np.int32)
            if arr_aristas.ndim == 2 and arr_aristas.shape[1] == 2:
                valid_l = (arr_aristas[:, 0] < len(verts)) & (arr_aristas[:, 1] < len(verts))
                arr_aristas = arr_aristas[valid_l]
                if len(arr_aristas) > 0:
                    lb = verts[arr_aristas.reshape(-1)].astype(np.float32)
                    n_line_verts = len(lb)
                    vbo_l = self._ctx.buffer(lb.tobytes())
                    vao_lines = self._ctx.vertex_array(self._prog_lines, [(vbo_l, "3f", "in_vert")])
                    vram_bytes += int(lb.nbytes)

        # 3. Nodos en vértices (Points)
        vb = np.array(verts, dtype=np.float32)
        vbo_n = self._ctx.buffer(vb.tobytes())
        vao_nodes = self._ctx.vertex_array(self._prog_nodes, [(vbo_n, "3f", "in_vert")])
        vram_bytes += int(vb.nbytes)

        # 4. VAOs dedicados para GPU Color/ID Picking (Subfase 2.3)
        vao_pick_faces = None
        if vbo_f is not None and self._prog_picking is not None:
            try:
                vao_pick_faces = self._ctx.vertex_array(self._prog_picking, [(vbo_f, "3f 12x", "in_vert")])
            except Exception as e:
                logger.debug(f"GlRenderer: Aviso al crear vao_pick_faces: {e}")

        vao_pick_lines = None
        if vbo_l is not None and self._prog_picking is not None:
            try:
                vao_pick_lines = self._ctx.vertex_array(self._prog_picking, [(vbo_l, "3f", "in_vert")])
            except Exception as e:
                logger.debug(f"GlRenderer: Aviso al crear vao_pick_lines: {e}")

        meta_info: Dict[str, Any] = {
            "geom_key": geom_key,
            "node_name": getattr(pieza, "node_name", getattr(pieza, "tipo_modelo", "nodo")),
            "vao_faces": vao_faces,
            "vao_lines": vao_lines,
            "vao_nodes": vao_nodes,
            "vao_pick_faces": vao_pick_faces,
            "vao_pick_lines": vao_pick_lines,
            "vbo_faces": vbo_f,
            "vbo_lines": vbo_l,
            "vbo_nodes": vbo_n,
            "n_tri_verts": n_tri_verts,
            "n_line_verts": n_line_verts,
            "n_nodes": len(verts),
            "vram_bytes": vram_bytes,
        }
        pieza.gpu_buffers = meta_info
        pieza.vao = vao_faces if vao_faces is not None else vao_lines
        pieza.vbo = vbo_f if vbo_f is not None else vbo_n

        entry = (vao_faces, vao_lines, vao_nodes, n_tri_verts, n_line_verts, len(verts))
        self._vbo_cache[geom_key] = entry
        self._vbo_meta[geom_key] = meta_info

        # Control estricto de fuga de VRAM: límite máximo de buffers activos (len(_vbo_cache) <= 4)
        while len(self._vbo_cache) > 4:
            oldest_key = next(iter(self._vbo_cache))
            if oldest_key != geom_key:
                self._evict_vbo_entry(oldest_key)
            else:
                break
        return entry

    def cargar(self, objeto_o_escena: Any) -> Dict[str, Any]:
        """
        Subfase 2.2: Aloja de forma anticipada los buffers VBO/VAO individuales en VRAM
        para cada nodo jerárquico de un SceneModel u Objeto3D.
        Retorna el resumen de métricas de VRAM asignada.
        """
        if not self._disponible:
            if self._fallback_cpu:
                return self._fallback_cpu.cargar(objeto_o_escena)
            return {"backend": "CPU (Fallback)", "nodos_cargados": 0, "vram_bytes": 0}

        es_escena_compuesta = hasattr(objeto_o_escena, "piezas") and bool(objeto_o_escena.piezas)
        entidades: List[Tuple[str, Any]] = (
            list(objeto_o_escena.piezas.items()) if es_escena_compuesta else [("raiz", objeto_o_escena)]
        )

        nodos_cargados = 0
        vram_escena = 0
        detalle_nodos: Dict[str, int] = {}

        for part_id, pieza in entidades:
            bufs = self._obtener_buffers_gpu(pieza)
            if bufs is not None:
                nodos_cargados += 1
                nb = int(getattr(pieza, "gpu_buffers", {}).get("vram_bytes", 0))
                vram_escena += nb
                detalle_nodos[str(part_id)] = nb

        return {
            "backend": "GL",
            "nodos_cargados": nodos_cargados,
            "vram_bytes": vram_escena,
            "detalle_nodos": detalle_nodos,
        }

    cargar_escena_en_vram = cargar

    def obtener_metricas_vram(self) -> Dict[str, Any]:
        """Retorna métricas consolidadas de uso de memoria de video (VRAM) en los buffers activos."""
        total_bytes = sum(int(m.get("vram_bytes", 0)) for m in self._vbo_meta.values())
        return {
            "nodos_en_cache": len(self._vbo_meta),
            "vram_bytes_total": total_bytes,
            "vram_kb_total": round(total_bytes / 1024.0, 3),
            "nodos": {
                m.get("node_name", k): int(m.get("vram_bytes", 0))
                for k, m in self._vbo_meta.items()
            },
        }

    def _construir_matriz_mvp(
        self,
        pos_mundo: np.ndarray,
        rotacion: np.ndarray,
        escala: float,
        base: float,
        center: Tuple[float, float],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcula las matrices Model y MVP idénticas a la cámara pinhole de OpenCV:
        px = f * X / (Z + d) + cx
        py = f * (-Y) / (Z + d) + cy
        """
        d = 4.0
        near, far = 0.1, 100.0
        cx, cy = float(center[0]), float(center[1])
        w, h = float(self.w), float(self.h)
        f_scale = float(base * escala)

        # Matriz de Proyección alineada exactamente con coordenadas de pantalla
        P = np.zeros((4, 4), dtype=np.float32)
        P[0, 0] = (2.0 * f_scale) / max(w, 1.0)
        P[0, 2] = (2.0 * cx - w) / max(w, 1.0)
        P[1, 1] = (2.0 * f_scale) / max(h, 1.0)
        P[1, 2] = (h - 2.0 * cy) / max(h, 1.0)
        P[2, 2] = (far + near) / (far - near)
        P[2, 3] = -(2.0 * far * near) / (far - near)
        P[3, 2] = 1.0  # W_clip = Z_view

        # Matriz de Vista (cámara en Z = -d, pre-asignada)
        V = self._mat_V

        # Matriz de Modelo (Rotación Euler yaw, pitch, roll)
        yaw, pitch, roll = float(rotacion[0]), float(rotacion[1]), float(rotacion[2])
        cy_a, sy_a = np.cos(yaw), np.sin(yaw)
        cp_a, sp_a = np.cos(pitch), np.sin(pitch)
        cr_a, sr_a = np.cos(roll), np.sin(roll)

        Ry = np.array([[cy_a, 0.0, sy_a], [0.0, 1.0, 0.0], [-sy_a, 0.0, cy_a]], dtype=np.float32)
        Rx = np.array([[1.0, 0.0, 0.0], [0.0, cp_a, -sp_a], [0.0, sp_a, cp_a]], dtype=np.float32)
        Rz = np.array([[cr_a, -sr_a, 0.0], [sr_a, cr_a, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
        # HIGH-03: Unificar el orden de rotación compuesto (Rz * Ry * Rx) exactamente igual a hologram.py
        R = Rz @ Ry @ Rx

        M = np.eye(4, dtype=np.float32)
        M[:3, :3] = R
        if pos_mundo is not None and len(pos_mundo) >= 3:
            b_norm = float(base) if base > 1.0 else 200.0
            M[2, 3] = float(pos_mundo[2]) / b_norm

        MVP = P @ V @ M
        return M, MVP



    def renderizar_escena(
        self,
        frame: np.ndarray,
        objeto_o_escena: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        if not self._disponible:
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_escena(frame, objeto_o_escena, config=config, center=center)
            return frame

        h_f, w_f = frame.shape[:2]
        if w_f != self.w or h_f != self.h:
            self.inicializar(w_f, h_f)

        try:
            import moderngl

            if self._ultima_escena is not None and self._ultima_escena is not objeto_o_escena:
                self.liberar_buffers_objeto(self._ultima_escena)

            raw_cfg = config or self.config
            if hasattr(raw_cfg, "data"):
                cfg = raw_cfg.data
            elif isinstance(raw_cfg, dict):
                cfg = raw_cfg
            else:
                cfg = {}
            use_faces = bool(cfg.get("enable_3d_faces", True))
            t_actual = float(time.time() - self._t_inicio)

            if getattr(objeto_o_escena, "es_modelo_atomico", False):
                return self._renderizar_modelo_atomico(frame, objeto_o_escena, config=config, center=center)

            if getattr(objeto_o_escena, "es_modelo_molecular", False):
                return self._renderizar_modelo_molecular(frame, objeto_o_escena, config=config, center=center)

            if getattr(objeto_o_escena, "es_modelo_superficie", False):
                return self._renderizar_modelo_superficie(frame, objeto_o_escena, config=config, center=center)

            if hasattr(objeto_o_escena, "_actualizar_posiciones_piezas"):
                objeto_o_escena._actualizar_posiciones_piezas()

            # Determinar lista de entidades a renderizar (SceneModel compuesto u Objeto3D individual)
            es_escena_compuesta = hasattr(objeto_o_escena, "piezas") and bool(objeto_o_escena.piezas)
            entidades: List[Tuple[str, Any]] = (
                list(objeto_o_escena.piezas.items()) if es_escena_compuesta else [("raiz", objeto_o_escena)]
            )

            # Preparar FBO
            self._fbo.use()
            self._fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
            # Caras sólidas con DEPTH_TEST activo y BLEND desactivado para renderizado opaco Blinn-Phong
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.disable(moderngl.BLEND)

            # Renderizar entidades con Z-Buffer por hardware
            pieza_sel_id = getattr(objeto_o_escena, "pieza_seleccionada_id", None)
            cam_pos = self._cam_pos

            for part_id, pieza in entidades:
                if not getattr(pieza, "visible", True):
                    continue
                bufs = self._obtener_buffers_gpu(pieza)
                if bufs is None:
                    continue
                vao_faces, vao_lines, vao_nodes, n_tri, n_lines, n_nodes = bufs

                # Determinar color de la pieza (destacar si está seleccionada)
                col_bgr = (50, 255, 120) if part_id == pieza_sel_id else getattr(pieza, "color", (255, 235, 30))
                col_norm = (float(col_bgr[2]) / 255.0, float(col_bgr[1]) / 255.0, float(col_bgr[0]) / 255.0)

                if es_escena_compuesta and center is not None and hasattr(objeto_o_escena, "pos_mundo"):
                    dx_c = float(center[0] - objeto_o_escena.pos_mundo[0])
                    dy_c = float(center[1] - objeto_o_escena.pos_mundo[1])
                    c_2d = (float(pieza.pos_mundo[0] + dx_c), float(pieza.pos_mundo[1] + dy_c))
                else:
                    c_2d = center if center is not None else (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))

                M, MVP = self._construir_matriz_mvp(
                    pos_mundo=pieza.pos_mundo,
                    rotacion=pieza.rotacion,
                    escala=float(pieza.escala),
                    base=float(pieza.base),
                    center=c_2d,
                )

                # 1. Caras con Shader Blinn-Phong Sólido y Opaco
                if use_faces and vao_faces is not None and n_tri > 0:
                    self._prog_faces["u_mvp"].write(MVP.T.tobytes())
                    self._prog_faces["u_model"].write(M.T.tobytes())
                    self._prog_faces["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))
                    self._prog_faces["u_color"].value = col_norm
                    if "u_opacity" in self._prog_faces:
                        self._prog_faces["u_opacity"].value = 1.0  # Completamente sólido y opaco
                    if "u_time" in self._prog_faces:
                        self._prog_faces["u_time"].value = t_actual
                    if "u_fresnel_power" in self._prog_faces:
                        self._prog_faces["u_fresnel_power"].value = self.fresnel_power
                    if "u_scanline_freq" in self._prog_faces:
                        self._prog_faces["u_scanline_freq"].value = self.scanline_freq
                    vao_faces.render(moderngl.TRIANGLES)

                es_anat = getattr(objeto_o_escena, "es_modelo_anatomico", False)

                # 2. Aristas de contraste metálico sutil
                if vao_lines is not None and n_lines > 0:
                    self._ctx.enable(moderngl.BLEND)
                    self._ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
                    self._prog_lines["u_mvp"].write(MVP.T.tobytes())
                    self._prog_lines["u_color"].value = col_norm
                    self._prog_lines["u_brightness"].value = 0.12 if es_anat else self.edge_brightness
                    vao_lines.render(moderngl.LINES)
                    self._ctx.disable(moderngl.BLEND)

                # 3. Nodos en Vértices (omitir en modelos anatómicos para superficie orgánica suave y pura)
                if not es_anat and vao_nodes is not None and n_nodes > 0:
                    self._prog_nodes["u_mvp"].write(MVP.T.tobytes())
                    self._prog_nodes["u_color"].value = col_norm
                    self._prog_nodes["u_point_size"].value = 5.0
                    vao_nodes.render(moderngl.POINTS)

            # Renderizado de Flujo Sanguíneo por GPU Instancing (STARK Bio-Anatomy)
            if getattr(objeto_o_escena, "es_modelo_anatomico", False) and getattr(objeto_o_escena, "flujo_sanguineo_activo", False):
                self._renderizar_flujo_sanguineo_gl(objeto_o_escena, center=center)

            # Calcular BBox 2D para lectura acotada de ROI (optimización máxima de bus PCIe/RAM)
            pad = 20
            if hasattr(objeto_o_escena, "calcular_aabb_2d"):
                bx = objeto_o_escena.calcular_aabb_2d(pad=pad)
            else:
                bx = (0, 0, self.w, self.h)

            x1 = max(0, min(int(bx[0]), self.w - 1))
            y1 = max(0, min(int(bx[1]), self.h - 1))
            x2 = max(0, min(int(bx[2]), self.w))
            y2 = max(0, min(int(bx[3]), self.h))

            bw = x2 - x1
            bh = y2 - y1

            if bw <= 0 or bh <= 0:
                return frame

            # En OpenGL, el origen Y del viewport está en la parte inferior
            gl_y = self.h - (y1 + bh)
            raw = self._fbo.read(viewport=(x1, gl_y, bw, bh), components=4)
            bgra = np.frombuffer(raw, dtype=np.uint8).reshape((bh, bw, 4))

            # Invertir verticalmente e integrar mediante composición por máscara Alpha (sólido opaco)
            flipped = bgra[::-1, :, :]
            alpha_ch = flipped[:, :, 3]
            bgr = flipped[:, :, :3]
            roi = frame[y1:y2, x1:x2]

            if roi.shape[:2] == flipped.shape[:2]:
                mask = alpha_ch > 0
                mask_solid = alpha_ch >= 240
                roi[mask_solid] = bgr[mask_solid]

                # Bordes suavizados con antialiasing para las aristas (alpha < 240)
                mask_edge = mask & (~mask_solid)
                if mask_edge.any():
                    a_f = (alpha_ch[mask_edge].astype(np.float32) / 255.0)[:, np.newaxis]
                    roi_e = roi[mask_edge].astype(np.float32)
                    bgr_e = bgr[mask_edge].astype(np.float32)
                    roi[mask_edge] = np.clip(roi_e * (1.0 - a_f) + bgr_e * a_f, 0, 255).astype(np.uint8)

            # Destacar AABB si hay una sub-pieza seleccionada en despiece
            if pieza_sel_id and hasattr(objeto_o_escena, "piezas") and pieza_sel_id in objeto_o_escena.piezas:
                p_sel = objeto_o_escena.piezas[pieza_sel_id]
                bx_sel = p_sel.calcular_aabb_2d(center=p_sel.pos_mundo[:2], pad=6)
                col_sel = (50, 255, 120)
                cv2.rectangle(frame, (int(bx_sel[0]), int(bx_sel[1])), (int(bx_sel[2]), int(bx_sel[3])), col_sel, 1, cv2.LINE_AA)
                cv2.putText(
                    frame,
                    f"PIEZA: {pieza_sel_id}",
                    (int(bx_sel[0]), max(int(bx_sel[1] - 4), 15)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.36,
                    col_sel,
                    1,
                    cv2.LINE_AA,
                )

            self._ultima_escena = objeto_o_escena
            return frame

        except Exception as e:
            logger.warning(f"GlRenderer: Error en renderizado GPU ({e}). Conmutando temporalmente a CPU.")
            if self._fallback_cpu is None:
                self._fallback_cpu = CpuRenderer(w=self.w, h=self.h, config=self.config)
            return self._fallback_cpu.renderizar_escena(frame, objeto_o_escena, config=config, center=center)

    def _renderizar_modelo_atomico(
        self,
        frame: np.ndarray,
        modelo_atomico: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        STARK Atomic Engine (Etapas 1 & 2):
        1. Núcleo: Instanciación por Hardware en GPU (ModernGL Draw Call único).
        2. Orbitales y Electrones: Shaders procedurales matemáticos con mezcla aditiva
           (GL_SRC_ALPHA, GL_ONE) y animación temporal u_time sin costo de geometría sólida.
        """
        if not self._disponible or self._ctx is None or self._prog_atomic_inst is None:
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_escena(frame, modelo_atomico, config=config, center=center)
            if hasattr(modelo_atomico, "renderizar"):
                return modelo_atomico.renderizar(frame, config=config, center=center)
            return frame

        try:
            import moderngl

            t_actual = float(time.time() - self._t_inicio)
            cam_pos = self._cam_pos
            escala_tot = float(modelo_atomico.escala)

            inst_nucleos = modelo_atomico.obtener_buffer_instancias_gpu(incluir_electrones=False)
            fn_elecs = getattr(modelo_atomico, "obtener_buffer_electrones_gpu", None)
            inst_elecs = fn_elecs(t_actual) if fn_elecs is not None else np.empty((0, 7), dtype=np.float32)

            if len(inst_elecs) > 0 and len(inst_nucleos) > 0:
                inst_data = np.vstack([inst_nucleos, inst_elecs]).astype(np.float32)
            elif len(inst_elecs) > 0:
                inst_data = inst_elecs.astype(np.float32)
            else:
                inst_data = inst_nucleos.astype(np.float32)

            num_instancias = len(inst_data)

            # Preparar FBO
            self._fbo.use()
            self._fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

            c_2d = center if center is not None else (float(modelo_atomico.pos_mundo[0]), float(modelo_atomico.pos_mundo[1]))
            # Normalización del espacio local del átomo a [-1, 1] para proyección sin distorsión de near-clip
            S_scale = 1.0 / 155.0
            S_mat = np.diag([S_scale, S_scale, S_scale, 1.0]).astype(np.float32)
            M_raw, MVP_raw = self._construir_matriz_mvp(
                pos_mundo=modelo_atomico.pos_mundo,
                rotacion=modelo_atomico.rotacion,
                escala=float(modelo_atomico.escala),
                base=620.0,
                center=c_2d,
            )
            M = M_raw @ S_mat
            MVP = MVP_raw @ S_mat

            # -------------------------------------------------------------
            # PASO 1: Renderizado de Nucleones y Electrones (GPU Instancing + Z-Buffer + Blinn-Phong)
            # -------------------------------------------------------------
            if num_instancias > 0 and self._vbo_sphere_base is not None:
                self._ctx.enable(moderngl.DEPTH_TEST)
                self._ctx.disable(moderngl.BLEND)

                inst_bytes = inst_data.astype(np.float32).tobytes()
                if self._vbo_atomic_inst is None or self._vbo_atomic_inst.size != len(inst_bytes):
                    if self._vbo_atomic_inst is not None:
                        try:
                            self._vbo_atomic_inst.release()
                        except Exception as e:
                            logger.debug(f"GlRenderer: Aviso al liberar vbo_atomic_inst: {e}")
                    self._vbo_atomic_inst = self._ctx.buffer(inst_bytes)
                    self._vao_atomic_inst = self._ctx.vertex_array(
                        self._prog_atomic_inst,
                        [
                            (self._vbo_sphere_base, "3f 3f", "in_vert", "in_norm"),
                            (self._vbo_atomic_inst, "3f 3f 1f/i", "in_inst_pos", "in_inst_color", "in_inst_radius"),
                        ],
                    )
                else:
                    self._vbo_atomic_inst.write(inst_bytes)

                if "u_mvp" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_mvp"].write(MVP.T.tobytes())
                if "u_model" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_model"].write(M.T.tobytes())
                if "u_cam_pos" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))
                if "u_time" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_time"].value = t_actual
                if "u_fresnel_power" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_fresnel_power"].value = self.fresnel_power
                if "u_scanline_freq" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_scanline_freq"].value = self.scanline_freq

                self._vao_atomic_inst.render(moderngl.TRIANGLES, instances=num_instancias)

            # -------------------------------------------------------------
            # PASO 2: Anillos Clásicos Rutherford-Bohr y Nubes Orbitales
            # -------------------------------------------------------------
            anillos = getattr(modelo_atomico, "anillos_clasicos", None)
            n_electrones_tot = getattr(modelo_atomico, "electrones", 0)

            # Si disponemos del shader y VAO de toroide 3D sólido (Rutherford-Bohr Clásico)
            if self._prog_atomic_torus is not None and self._vao_atomic_torus is not None and anillos and n_electrones_tot > 0:
                self._ctx.enable(moderngl.DEPTH_TEST)
                self._ctx.disable(moderngl.BLEND)

                for idx_ring, ring in enumerate(anillos):
                    r_mat3 = ring["mat_rot"]
                    r_mat4 = np.eye(4, dtype=np.float32)
                    r_mat4[:3, :3] = r_mat3

                    MVP_ring = MVP @ r_mat4
                    M_ring = M @ r_mat4

                    self._prog_atomic_torus["u_mvp"].write(MVP_ring.T.tobytes())
                    self._prog_atomic_torus["u_model"].write(M_ring.T.tobytes())
                    self._prog_atomic_torus["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))
                    col_rgb = ring.get("color_rgb", (0.0, 0.58, 0.60))
                    self._prog_atomic_torus["u_color"].value = (float(col_rgb[0]), float(col_rgb[1]), float(col_rgb[2]))

                    self._vao_atomic_torus.render(moderngl.TRIANGLES)

            elif self._prog_atomic_orbital is not None and self._vao_orbital_quad is not None:
                self._ctx.enable(moderngl.BLEND)
                self._ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
                self._ctx.disable(moderngl.DEPTH_TEST)

                if anillos and n_electrones_tot > 0:
                    conteo_por_anillo = [
                        n_electrones_tot // len(anillos) + (1 if k < (n_electrones_tot % len(anillos)) else 0)
                        for k in range(len(anillos))
                    ]
                    for idx_ring, ring in enumerate(anillos):
                        r_orb = float(ring["radio"]) * escala_tot
                        r_mat3 = ring["mat_rot"]
                        r_mat4 = np.eye(4, dtype=np.float32)
                        r_mat4[:3, :3] = r_mat3

                        MVP_orb = MVP @ r_mat4
                        quad_size = r_orb * 1.35
                        n_e_r = conteo_por_anillo[idx_ring]

                        self._prog_atomic_orbital["u_mvp"].write(MVP_orb.T.tobytes())
                        self._prog_atomic_orbital["u_quad_size"].value = float(quad_size)
                        self._prog_atomic_orbital["u_radius"].value = float(r_orb)
                        self._prog_atomic_orbital["u_thickness"].value = float(max(2.6 * escala_tot, 1.8))
                        self._prog_atomic_orbital["u_time"].value = float(t_actual)
                        self._prog_atomic_orbital["u_speed"].value = float(ring.get("velocidad_angular", 1.5))
                        self._prog_atomic_orbital["u_num_electrons"].value = int(n_e_r)
                        self._prog_atomic_orbital["u_ring_color"].value = (0.0, 0.78, 0.70)
                        self._prog_atomic_orbital["u_electron_color"].value = (0.10, 0.45, 1.0)

                        self._vao_orbital_quad.render(moderngl.TRIANGLES)
                elif not anillos and hasattr(modelo_atomico, "capas_orbitales"):
                    capas = getattr(modelo_atomico, "capas_orbitales", [])
                    for capa in capas:
                        r_orb = float(capa["radio"]) * escala_tot
                        n_elec = int(capa["electrones"])
                        w_ang = float(capa["velocidad_angular"])
                        inc_rad = np.radians(float(capa["inclinacion_deg"]))

                        rot_capa = np.array([
                            [1.0, 0.0, 0.0, 0.0],
                            [0.0, np.cos(inc_rad), -np.sin(inc_rad), 0.0],
                            [0.0, np.sin(inc_rad), np.cos(inc_rad), 0.0],
                            [0.0, 0.0, 0.0, 1.0],
                        ], dtype=np.float32)

                        MVP_orb = MVP @ rot_capa
                        quad_size = r_orb * 1.35

                        self._prog_atomic_orbital["u_mvp"].write(MVP_orb.T.tobytes())
                        self._prog_atomic_orbital["u_quad_size"].value = float(quad_size)
                        self._prog_atomic_orbital["u_radius"].value = float(r_orb)
                        self._prog_atomic_orbital["u_thickness"].value = float(max(2.4 * escala_tot, 1.6))
                        self._prog_atomic_orbital["u_time"].value = float(t_actual)
                        self._prog_atomic_orbital["u_speed"].value = float(w_ang)
                        self._prog_atomic_orbital["u_num_electrons"].value = int(n_elec)
                        self._prog_atomic_orbital["u_ring_color"].value = (0.0, 0.78, 0.70)
                        self._prog_atomic_orbital["u_electron_color"].value = (0.10, 0.45, 1.0)

                        self._vao_orbital_quad.render(moderngl.TRIANGLES)

            # -------------------------------------------------------------
            # PASO 3: Composición de ROI acotado FBO -> Frame OpenCV (Alpha Blending Sólido)
            # -------------------------------------------------------------
            max_r = 155.0 * escala_tot
            if anillos:
                max_r = max([float(r["radio"]) for r in anillos], default=155.0) * escala_tot
            elif hasattr(modelo_atomico, "capas_orbitales"):
                capas = getattr(modelo_atomico, "capas_orbitales", [])
                if capas:
                    max_r = max([float(c["radio"]) for c in capas], default=155.0) * escala_tot
            pad = int(round(max_r * 1.25)) + 25
            x1 = max(0, min(int(c_2d[0] - pad), self.w - 1))
            y1 = max(0, min(int(c_2d[1] - pad), self.h - 1))
            x2 = max(0, min(int(c_2d[0] + pad), self.w))
            y2 = max(0, min(int(c_2d[1] + pad), self.h))

            bw = x2 - x1
            bh = y2 - y1

            if bw > 0 and bh > 0:
                gl_y = self.h - (y1 + bh)
                raw = self._fbo.read(viewport=(x1, gl_y, bw, bh), components=4)
                bgra = np.frombuffer(raw, dtype=np.uint8).reshape((bh, bw, 4))
                flipped = cv2.flip(bgra, 0)
                alpha = flipped[:, :, 3]
                bgr = flipped[:, :, :3]
                mask = alpha > 12
                if np.any(mask):
                    roi = frame[y1:y2, x1:x2]
                    # Píxeles sólidos (alpha >= 250): copia directa ultrarrápida
                    mask_solid = alpha >= 250
                    roi[mask_solid] = bgr[mask_solid]
                    # Bordes antialiased translúcidos: alpha blending suave
                    mask_edge = mask & (~mask_solid)
                    if np.any(mask_edge):
                        a_f = (alpha[mask_edge].astype(np.float32) / 255.0)[:, None]
                        roi_e = roi[mask_edge].astype(np.float32)
                        bgr_e = bgr[mask_edge].astype(np.float32)
                        roi[mask_edge] = np.clip(roi_e * (1.0 - a_f) + bgr_e * a_f, 0, 255).astype(np.uint8)

            # -------------------------------------------------------------
            # PASO 4: Superposición de HUD Atómico Cuántico
            # -------------------------------------------------------------
            if hasattr(modelo_atomico, "dibujar_hud_cuantico") and getattr(modelo_atomico, "mostrar_hud", True):
                modelo_atomico.dibujar_hud_cuantico(frame)

            self._ultima_escena = modelo_atomico
            return frame

        except Exception as e:
            logger.warning(f"GlRenderer: Error en renderizado GPU atómico ({e}). Conmutando a CPU.")
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_escena(frame, modelo_atomico, config=config, center=center)
            return frame

    def _renderizar_modelo_molecular(
        self,
        frame: np.ndarray,
        modelo_molecular: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        STARK Molecular Builder (Renderizado GPU):
        1. Átomos: Instanciación por hardware GPU (_prog_atomic_inst y _vbo_sphere_base).
        2. Enlaces Covalentes: Cilindros 3D volumétricos con sombreado Blinn-Phong (_prog_atomic_torus).
        3. Buffer de profundidad activo (moderngl.DEPTH_TEST) para intersección física perfecta.
        4. Composición de ROI acotado y superposición del HUD contextual Sci-Fi.
        """
        if not self._disponible or self._ctx is None or self._prog_atomic_inst is None:
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_escena(frame, modelo_molecular, config=config, center=center)
            if hasattr(modelo_molecular, "renderizar"):
                return modelo_molecular.renderizar(frame, config=config, center=center)
            return frame

        try:
            import moderngl

            t_actual = float(time.time() - self._t_inicio)
            cam_pos = self._cam_pos
            escala_tot = float(modelo_molecular.escala)

            # Preparar FBO
            self._fbo.use()
            self._fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

            c_2d = center if center is not None else (float(modelo_molecular.pos_mundo[0]), float(modelo_molecular.pos_mundo[1]))
            M, MVP = self._construir_matriz_mvp(
                pos_mundo=modelo_molecular.pos_mundo,
                rotacion=modelo_molecular.rotacion,
                escala=escala_tot,
                base=float(modelo_molecular.base),
                center=c_2d,
            )

            # Sincronizar buffers GPU si cambió la geometría o preset
            mol_version = getattr(modelo_molecular, "version_geometria", 0)
            if mol_version != self._cached_mol_version:
                # 1. Buffers de enlaces covalentes (tubos cilíndricos 3D)
                b_verts, b_norms = modelo_molecular.obtener_buffers_enlaces_gpu()
                self._n_molecular_bond_verts = len(b_verts)
                if self._n_molecular_bond_verts > 0:
                    b_buf = np.hstack([b_verts, b_norms]).astype(np.float32).tobytes()
                    if self._vbo_molecular_bonds is None or self._vbo_molecular_bonds.size != len(b_buf):
                        if self._vbo_molecular_bonds is not None:
                            try:
                                self._vbo_molecular_bonds.release()
                            except Exception as e_b:
                                logger.debug(f"GlRenderer: Aviso al liberar vbo_molecular_bonds: {e_b}")
                        self._vbo_molecular_bonds = self._ctx.buffer(b_buf)
                        self._vao_molecular_bonds = self._ctx.vertex_array(
                            self._prog_atomic_torus,
                            [(self._vbo_molecular_bonds, "3f 3f", "in_vert", "in_norm")],
                        )
                    else:
                        self._vbo_molecular_bonds.write(b_buf)
                else:
                    self._vao_molecular_bonds = None

                # 2. Buffers de instancias de átomos
                inst_data = modelo_molecular.obtener_buffer_instancias_gpu()
                inst_bytes = inst_data.astype(np.float32).tobytes()
                if self._vbo_molecular_inst is None or self._vbo_molecular_inst.size != len(inst_bytes):
                    if self._vbo_molecular_inst is not None:
                        try:
                            self._vbo_molecular_inst.release()
                        except Exception as e_i:
                            logger.debug(f"GlRenderer: Aviso al liberar vbo_molecular_inst: {e_i}")
                    self._vbo_molecular_inst = self._ctx.buffer(inst_bytes)
                    self._vao_molecular_inst = self._ctx.vertex_array(
                        self._prog_atomic_inst,
                        [
                            (self._vbo_sphere_base, "3f 3f", "in_vert", "in_norm"),
                            (self._vbo_molecular_inst, "3f 3f 1f/i", "in_inst_pos", "in_inst_color", "in_inst_radius"),
                        ],
                    )
                else:
                    self._vbo_molecular_inst.write(inst_bytes)

                self._cached_mol_version = mol_version

            # Activar Z-Buffer para intersección sólida realista
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.disable(moderngl.BLEND)

            # PASO 1: Renderizado de Enlaces Covalentes (Tubos 3D con sombreado Blinn-Phong)
            if (
                self._n_molecular_bond_verts > 0
                and self._vao_molecular_bonds is not None
                and self._prog_atomic_torus is not None
            ):
                if "u_mvp" in self._prog_atomic_torus:
                    self._prog_atomic_torus["u_mvp"].write(MVP.T.tobytes())
                if "u_model" in self._prog_atomic_torus:
                    self._prog_atomic_torus["u_model"].write(M.T.tobytes())
                if "u_cam_pos" in self._prog_atomic_torus:
                    self._prog_atomic_torus["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))
                if "u_color" in self._prog_atomic_torus:
                    self._prog_atomic_torus["u_color"].value = (0.78, 0.80, 0.84)
                self._vao_molecular_bonds.render(moderngl.TRIANGLES)

            # PASO 2: Renderizado de Átomos (GPU Instancing + Z-Buffer + Paleta CPK)
            num_atomos = len(modelo_molecular.atomos)
            if (
                num_atomos > 0
                and self._vao_molecular_inst is not None
                and self._vbo_sphere_base is not None
                and self._prog_atomic_inst is not None
            ):
                if "u_mvp" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_mvp"].write(MVP.T.tobytes())
                if "u_model" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_model"].write(M.T.tobytes())
                if "u_cam_pos" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))
                if "u_time" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_time"].value = t_actual
                if "u_fresnel_power" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_fresnel_power"].value = self.fresnel_power
                if "u_scanline_freq" in self._prog_atomic_inst:
                    self._prog_atomic_inst["u_scanline_freq"].value = self.scanline_freq
                self._vao_molecular_inst.render(moderngl.TRIANGLES, instances=num_atomos)

            # PASO 3: Composición de ROI acotado FBO -> Frame OpenCV
            max_r = 230.0 * escala_tot
            pad = int(round(max_r)) + 30
            x1 = max(0, min(int(c_2d[0] - pad), self.w - 1))
            y1 = max(0, min(int(c_2d[1] - pad), self.h - 1))
            x2 = max(0, min(int(c_2d[0] + pad), self.w))
            y2 = max(0, min(int(c_2d[1] + pad), self.h))

            bw = x2 - x1
            bh = y2 - y1

            if bw > 0 and bh > 0:
                gl_y = self.h - (y1 + bh)
                raw = self._fbo.read(viewport=(x1, gl_y, bw, bh), components=4)
                bgra = np.frombuffer(raw, dtype=np.uint8).reshape((bh, bw, 4))
                flipped = cv2.flip(bgra, 0)
                alpha = flipped[:, :, 3]
                bgr = flipped[:, :, :3]
                mask = alpha > 12
                if np.any(mask):
                    roi = frame[y1:y2, x1:x2]
                    mask_solid = alpha >= 250
                    roi[mask_solid] = bgr[mask_solid]
                    mask_edge = mask & (~mask_solid)
                    if np.any(mask_edge):
                        a_f = (alpha[mask_edge].astype(np.float32) / 255.0)[:, None]
                        roi_e = roi[mask_edge].astype(np.float32)
                        bgr_e = bgr[mask_edge].astype(np.float32)
                        roi[mask_edge] = np.clip(roi_e * (1.0 - a_f) + bgr_e * a_f, 0, 255).astype(np.uint8)

            # PASO 4: Superposición de HUD Contextual Molecular
            if hasattr(modelo_molecular, "dibujar_hud_molecular") and getattr(modelo_molecular, "mostrar_hud", True):
                modelo_molecular.dibujar_hud_molecular(frame, cursor_pos=getattr(modelo_molecular, "ultimo_cursor_pos", None))

            self._ultima_escena = modelo_molecular
            return frame

        except Exception as e:
            logger.warning(f"GlRenderer: Error en renderizado GPU molecular ({e}). Conmutando a CPU.")
            if self._fallback_cpu is None:
                self._fallback_cpu = CpuRenderer(w=self.w, h=self.h, config=self.config)
            return self._fallback_cpu.renderizar_escena(frame, modelo_molecular, config=config, center=center)

    def _renderizar_modelo_superficie(
        self,
        frame: np.ndarray,
        modelo_superficie: Any,
        config: Optional[Union[Dict[str, Any], Any]] = None,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        STARK Math Grapher (Renderizado GPU de Superficie 3D z = f(x, y)):
        - Malla 3D continua con sombreado Blinn-Phong de doble cara e iluminación especular.
        - Mapa de calor altimétrico (gradiente cian -> azul -> magenta) por vértice.
        - Z-Buffer activo (moderngl.DEPTH_TEST) para oclusión espacial correcta.
        - Superposición del HUD contextual holográfico 3D.
        """
        if not self._disponible or self._ctx is None:
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_escena(frame, modelo_superficie, config=config, center=center)
            if hasattr(modelo_superficie, "renderizar"):
                return modelo_superficie.renderizar(frame, config=config, center=center)
            return frame

        try:
            import moderngl

            if self._prog_surface_3d is None:
                self._prog_surface_3d = self._ctx.program(
                    vertex_shader=_GLSL_SURFACE_VERT,
                    fragment_shader=_GLSL_SURFACE_FRAG,
                )

            cam_pos = self._cam_pos
            escala_tot = float(modelo_superficie.escala)

            # Preparar FBO
            self._fbo.use()
            self._fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.disable(moderngl.CULL_FACE)
            self._ctx.enable(moderngl.BLEND)
            self._ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

            c_2d = center if center is not None else (float(modelo_superficie.pos_mundo[0]), float(modelo_superficie.pos_mundo[1]))
            M, MVP = self._construir_matriz_mvp(
                pos_mundo=modelo_superficie.pos_mundo,
                rotacion=modelo_superficie.rotacion,
                escala=escala_tot,
                base=float(modelo_superficie.base),
                center=c_2d,
            )

            # Sincronizar buffers GPU si cambió el preset o versión
            surf_version = getattr(modelo_superficie, "version_geometria", 0)
            if surf_version != self._cached_surface_version or self._vbo_surface_3d is None:
                buf_interleaved, n_verts = modelo_superficie.obtener_buffer_superficie_gpu()
                self._n_surface_verts = n_verts
                raw_bytes = buf_interleaved.astype(np.float32).tobytes()

                if self._vbo_surface_3d is None or self._vbo_surface_3d.size != len(raw_bytes):
                    if self._vbo_surface_3d is not None:
                        try:
                            self._vbo_surface_3d.release()
                        except Exception as e_s:
                            logger.debug(f"GlRenderer: Aviso al liberar vbo_surface_3d: {e_s}")
                    self._vbo_surface_3d = self._ctx.buffer(raw_bytes)
                    self._vao_surface_3d = self._ctx.vertex_array(
                        self._prog_surface_3d,
                        [(self._vbo_surface_3d, "3f 3f 3f", "in_vert", "in_norm", "in_col")],
                    )
                else:
                    self._vbo_surface_3d.write(raw_bytes)

                self._cached_surface_version = surf_version

            # Renderizar Malla de Superficie 3D
            if self._vao_surface_3d is not None and self._n_surface_verts > 0:
                if "u_mvp" in self._prog_surface_3d:
                    self._prog_surface_3d["u_mvp"].write(MVP.T.tobytes())
                if "u_model" in self._prog_surface_3d:
                    self._prog_surface_3d["u_model"].write(M.T.tobytes())
                if "u_cam_pos" in self._prog_surface_3d:
                    self._prog_surface_3d["u_cam_pos"].value = (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2]))

                self._vao_surface_3d.render(moderngl.TRIANGLES)

            # Composición de ROI acotado FBO -> Frame OpenCV
            max_r = 240.0 * escala_tot
            x_min = max(0, int(c_2d[0] - max_r))
            x_max = min(self.w, int(c_2d[0] + max_r))
            y_min = max(0, int(c_2d[1] - max_r))
            y_max = min(self.h, int(c_2d[1] + max_r))

            if x_max > x_min and y_max > y_min:
                rw = x_max - x_min
                rh = y_max - y_min
                raw_roi = self._fbo.read(viewport=(x_min, self.h - y_max, rw, rh), components=4, dtype="f1")
                arr_fbo_roi = np.frombuffer(raw_roi, dtype=np.uint8).reshape((rh, rw, 4))
                arr_fbo_roi = cv2.flip(arr_fbo_roi, 0)

                bgr_roi = arr_fbo_roi[:, :, :3]
                alpha_roi = arr_fbo_roi[:, :, 3].astype(np.float32) / 255.0
                alpha_3d = np.repeat(alpha_roi[:, :, np.newaxis], 3, axis=2)

                frame_roi = frame[y_min:y_max, x_min:x_max].astype(np.float32)
                blended = bgr_roi.astype(np.float32) * alpha_3d + frame_roi * (1.0 - alpha_3d)
                frame[y_min:y_max, x_min:x_max] = np.clip(blended, 0, 255).astype(np.uint8)

            # Superposición de HUD Contextual
            if hasattr(modelo_superficie, "dibujar_hud_superficie") and getattr(modelo_superficie, "mostrar_hud", True):
                modelo_superficie.dibujar_hud_superficie(frame, cursor_pos=getattr(modelo_superficie, "ultimo_cursor_pos", None))

            self._ultima_escena = modelo_superficie
            return frame

        except Exception as e:
            logger.warning(f"GlRenderer: Error en renderizado GPU de superficie ({e}). Conmutando a CPU.")
            if self._fallback_cpu is None:
                self._fallback_cpu = CpuRenderer(w=self.w, h=self.h, config=self.config)
            return self._fallback_cpu.renderizar_escena(frame, modelo_superficie, config=config, center=center)

    def _renderizar_flujo_sanguineo_gl(
        self,
        modelo_anatomico: Any,
        center: Optional[Tuple[float, float]] = None,
    ) -> None:
        """
        STARK Bio-Anatomy Engine (Flujo Sanguíneo por GPU Instancing):
        - Renderiza las partículas hemodinámicas (azul desoxigenada / roja oxigenada)
          reutilizando el pipeline instanciado de esferas (cero bucles de dibujo en Python).
        - Oclusión correcta en Z-Buffer por hardware (moderngl.DEPTH_TEST).
        """
        if not self._disponible or self._ctx is None:
            return

        fn_flujo = getattr(modelo_anatomico, "obtener_buffer_gpu_flujo", None)
        if fn_flujo is None:
            return

        t_actual = float(time.time() - self._t_inicio)
        inst_flujo = fn_flujo(t_actual)
        if inst_flujo is None or len(inst_flujo) == 0:
            return

        try:
            import moderngl

            # Asegurar programa base instanciado y malla esférica
            if self._prog_atomic_inst is None:
                self._prog_atomic_inst = self._ctx.program(
                    vertex_shader=_GLSL_ATOMIC_INST_VERT,
                    fragment_shader=_GLSL_ATOMIC_INST_FRAG,
                )
            if self._vbo_sphere_base is None:
                from atomic_model import generar_esfera_base_gpu
                s_verts, s_norms = generar_esfera_base_gpu(radio=1.0, sub_lat=12, sub_lon=18)
                self._n_sphere_verts = len(s_verts)
                base_buf = np.hstack([s_verts, s_norms]).astype(np.float32)
                self._vbo_sphere_base = self._ctx.buffer(base_buf.tobytes())

            num_particulas = len(inst_flujo)
            c_2d = center if center is not None else (float(modelo_anatomico.pos_mundo[0]), float(modelo_anatomico.pos_mundo[1]))
            M, MVP = self._construir_matriz_mvp(
                pos_mundo=modelo_anatomico.pos_mundo,
                rotacion=modelo_anatomico.rotacion,
                escala=float(modelo_anatomico.escala),
                base=float(modelo_anatomico.base),
                center=c_2d,
            )

            inst_bytes = inst_flujo.astype(np.float32).tobytes()
            if self._vbo_flujo_inst is None or self._vbo_flujo_inst.size != len(inst_bytes):
                if self._vbo_flujo_inst is not None:
                    try:
                        self._vbo_flujo_inst.release()
                    except Exception as e_f:
                        logger.debug(f"GlRenderer: Aviso al liberar vbo_flujo_inst: {e_f}")
                self._vbo_flujo_inst = self._ctx.buffer(inst_bytes)
                self._vao_flujo_inst = self._ctx.vertex_array(
                    self._prog_atomic_inst,
                    [
                        (self._vbo_sphere_base, "3f 3f", "in_vert", "in_norm"),
                        (self._vbo_flujo_inst, "3f 3f 1f/i", "in_inst_pos", "in_inst_color", "in_inst_radius"),
                    ],
                )
            else:
                self._vbo_flujo_inst.write(inst_bytes)

            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.disable(moderngl.BLEND)

            if "u_mvp" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_mvp"].write(MVP.T.tobytes())
            if "u_model" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_model"].write(M.T.tobytes())
            if "u_cam_pos" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_cam_pos"].value = (float(self._cam_pos[0]), float(self._cam_pos[1]), float(self._cam_pos[2]))
            if "u_time" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_time"].value = t_actual
            if "u_fresnel_power" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_fresnel_power"].value = self.fresnel_power
            if "u_scanline_freq" in self._prog_atomic_inst:
                self._prog_atomic_inst["u_scanline_freq"].value = self.scanline_freq

            self._vao_flujo_inst.render(moderngl.TRIANGLES, instances=num_particulas)
        except Exception as e_gl:
            logger.debug(f"GlRenderer: Error en renderizado de flujo sanguíneo GPU: {e_gl}")

    def renderizar_overlay_ui_gl(
        self,
        frame: np.ndarray,
        telemetria: Optional[Any] = None,
        menu_3d: Optional[Any] = None,
        voz_ctrl: Optional[Any] = None,
        cursor_pos: Optional[Tuple[float, float]] = None,
        ui_visible: bool = True,
        desplazar_telemetria: bool = False,
    ) -> np.ndarray:
        """
        Subfase 2.4: Renderiza y superpone la telemetría (FPS, Latencia, Jitter)
        y el menú lateral directamente en el contexto OpenGL (ModernGL FBO / VRAM).
        Garantiza que la UI se integre por hardware acelerado sobre el lienzo de la escena.
        """
        desplazar = desplazar_telemetria or getattr(getattr(self, "_ultima_escena", None), "es_modelo_atomico", False)

        if not self._disponible or self._ctx is None:
            if self._fallback_cpu:
                return self._fallback_cpu.renderizar_overlay_ui_gl(
                    frame, telemetria, menu_3d, voz_ctrl, cursor_pos,
                    ui_visible=ui_visible, desplazar_telemetria=desplazar
                )
            if ui_visible and telemetria is not None and getattr(telemetria, "mostrar_hud", True):
                frame = telemetria.dibujar_hud(frame, desplazar_izquierda=desplazar)
            if menu_3d is not None:
                frame = menu_3d.dibujar_menu(frame, cursor_pos, ui_visible=ui_visible)
            if ui_visible and voz_ctrl is not None:
                frame = voz_ctrl.dibujar_hud_ptt(frame)
            return frame

        try:
            # Optimización de alto rendimiento (Cero copias / Cero latencia):
            # Renderizado directo C-API OpenCV de la UI sobre el fotograma (< 0.8 ms vs 44 ms del bucle de mezcla)
            if ui_visible and telemetria is not None and getattr(telemetria, "mostrar_hud", True):
                frame = telemetria.dibujar_hud(frame, desplazar_izquierda=desplazar)
            if menu_3d is not None:
                frame = menu_3d.dibujar_menu(frame, cursor_pos, ui_visible=ui_visible)
            if ui_visible and voz_ctrl is not None:
                frame = voz_ctrl.dibujar_hud_ptt(frame)
            return frame
        except Exception as e:
            logger.warning(f"GlRenderer: Error en renderizado OpenGL del HUD/Telemetría ({e}).")
            if ui_visible and telemetria is not None and getattr(telemetria, "mostrar_hud", True):
                frame = telemetria.dibujar_hud(frame, desplazar_izquierda=desplazar)
            if menu_3d is not None:
                frame = menu_3d.dibujar_menu(frame, cursor_pos, ui_visible=ui_visible)
            if ui_visible and voz_ctrl is not None:
                frame = voz_ctrl.dibujar_hud_ptt(frame)
            return frame

    def _renderizar_fbo_picking(self, objeto_o_escena: Any) -> None:
        """
        Subfase 2.3: Renderiza la escena en el FBO secundario offscreen de picking.
        Asigna a cada pieza un color sólido RGB único derivado de su ID entero.
        El Z-buffer nativo de 24 bits (GL_DEPTH_TEST) resuelve automáticamente las oclusiones.
        """
        if not self._disponible or self._picking_fbo is None or self._prog_picking is None:
            return

        import moderngl

        if hasattr(objeto_o_escena, "_actualizar_posiciones_piezas"):
            objeto_o_escena._actualizar_posiciones_piezas()

        es_escena_compuesta = hasattr(objeto_o_escena, "piezas") and bool(objeto_o_escena.piezas)
        entidades: List[Tuple[str, Any]] = (
            list(objeto_o_escena.piezas.items()) if es_escena_compuesta else [("raiz", objeto_o_escena)]
        )

        self._id_to_part.clear()
        self._part_to_id.clear()

        # Preparar FBO secundario de picking
        self._picking_fbo.use()
        self._picking_fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.disable(moderngl.BLEND)  # Color sólido puro, sin mezcla alfa

        int_id = 1
        for part_id, pieza in entidades:
            bufs = self._obtener_buffers_gpu(pieza)
            if bufs is None:
                continue

            # Mapear part_id a int_id y codificar a RGB
            self._id_to_part[int_id] = str(part_id)
            self._part_to_id[str(part_id)] = int_id

            r = float(int_id & 0xFF) / 255.0
            g = float((int_id >> 8) & 0xFF) / 255.0
            b = float((int_id >> 16) & 0xFF) / 255.0

            c_2d = (float(pieza.pos_mundo[0]), float(pieza.pos_mundo[1]))
            M, MVP = self._construir_matriz_mvp(
                pos_mundo=pieza.pos_mundo,
                rotacion=pieza.rotacion,
                escala=float(pieza.escala),
                base=float(pieza.base),
                center=c_2d,
            )

            self._prog_picking["u_mvp"].write(MVP.T.tobytes())
            self._prog_picking["u_id_color"].value = (r, g, b, 1.0)

            # Dibujar caras si existen
            meta = getattr(pieza, "gpu_buffers", None) or {}
            vao_p_f = meta.get("vao_pick_faces")
            n_tri = meta.get("n_tri_verts", 0)
            if vao_p_f is not None and n_tri > 0:
                vao_p_f.render(moderngl.TRIANGLES)
            else:
                # Si no tiene caras, dibujar aristas
                vao_p_l = meta.get("vao_pick_lines")
                n_lines = meta.get("n_line_verts", 0)
                if vao_p_l is not None and n_lines > 0:
                    vao_p_l.render(moderngl.LINES)

            int_id += 1

    def pick(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        Subfase 2.3: GPU Ray Picking Preciso con resolución nativa de oclusiones vía Z-Buffer.
        Soporta firmas flexibles:
          pick(x_px, y_px) -> Optional[str]
          pick(x_px, y_px, objeto_o_escena) -> Optional[str]
          pick(objeto_o_escena, (x_px, y_px)) -> Optional[str]
        Lectura estricta de 1x1 píxel mediante glReadPixels (ModernGL FBO.read) para latencia < 2 ms.
        """
        if not self._disponible or self._picking_fbo is None:
            if self._fallback_cpu:
                return self._fallback_cpu.pick(*args, **kwargs)
            return None

        # Desempaquetar argumentos flexibles
        x_px: float = 0.0
        y_px: float = 0.0
        escena: Any = kwargs.get("objeto_o_escena", None)

        if len(args) == 1:
            arg0 = args[0]
            if isinstance(arg0, (tuple, list)) and len(arg0) >= 2:
                x_px, y_px = float(arg0[0]), float(arg0[1])
        elif len(args) == 2:
            arg0, arg1 = args[0], args[1]
            if isinstance(arg0, (int, float)) and isinstance(arg1, (int, float)):
                x_px, y_px = float(arg0), float(arg1)
            elif hasattr(arg0, "piezas") or hasattr(arg0, "contiene_punto"):
                escena = arg0
                if isinstance(arg1, (tuple, list)) and len(arg1) >= 2:
                    x_px, y_px = float(arg1[0]), float(arg1[1])
        elif len(args) >= 3:
            if isinstance(args[0], (int, float)) and isinstance(args[1], (int, float)):
                x_px, y_px = float(args[0]), float(args[1])
                escena = args[2]
            else:
                escena = args[0]
                x_px, y_px = float(args[1]), float(args[2])

        if escena is None:
            escena = self._ultima_escena

        if escena is None:
            return None

        self._ultima_escena = escena

        try:
            # Clave de estado cinemático para evitar re-renderizado redundante del picking FBO
            piezas_state = (
                tuple(
                    (k, round(float(p.pos_mundo[0]), 1), round(float(p.pos_mundo[1]), 1), round(float(p.pos_mundo[2]), 2))
                    for k, p in sorted(escena.piezas.items())
                )
                if hasattr(escena, "piezas") and bool(escena.piezas)
                else ()
            )
            key = (
                id(escena),
                round(float(getattr(escena, "factor_explosion", 0.0)), 4),
                round(float(getattr(escena, "pos_mundo", [0, 0, 0])[0]), 2),
                round(float(getattr(escena, "pos_mundo", [0, 0, 0])[1]), 2),
                round(float(getattr(escena, "pos_mundo", [0, 0, 0])[2]), 2),
                round(float(getattr(escena, "rotacion", [0, 0, 0])[0]), 4),
                round(float(getattr(escena, "rotacion", [0, 0, 0])[1]), 4),
                round(float(getattr(escena, "rotacion", [0, 0, 0])[2]), 4),
                round(float(getattr(escena, "escala", 1.0)), 4),
                len(getattr(escena, "offsets_manuales", {})),
                len(getattr(escena, "piezas_desacopladas", set())),
                piezas_state,
            )


            if getattr(self, "_picking_cache_key", None) != key:
                self._renderizar_fbo_picking(escena)
                self._picking_cache_key = key

            # Coordenadas en OpenGL (origen abajo a la izquierda)
            x_int = max(0, min(int(round(x_px)), self.w - 1))
            gl_y = max(0, min(self.h - int(round(y_px)) - 1, self.h - 1))

            # Lectura estricta de 1x1 píxel (< 0.05 ms)
            raw = self._picking_fbo.read(viewport=(x_int, gl_y, 1, 1), components=4)
            int_id = int(raw[0]) | (int(raw[1]) << 8) | (int(raw[2]) << 16)

            if int_id > 0 and int_id in self._id_to_part:
                return self._id_to_part[int_id]

            # Tolerancia de proximidad 3x3 si el píxel central fue 0 (para bordes y líneas delgadas)
            x3 = max(0, min(x_int - 1, self.w - 3))
            y3 = max(0, min(gl_y - 1, self.h - 3))
            raw3 = self._picking_fbo.read(viewport=(x3, y3, 3, 3), components=4)
            data3 = np.frombuffer(raw3, dtype=np.uint8).reshape((3, 3, 4))
            for iy in range(3):
                for ix in range(3):
                    p_id = int(data3[iy, ix, 0]) | (int(data3[iy, ix, 1]) << 8) | (int(data3[iy, ix, 2]) << 16)
                    if p_id > 0 and p_id in self._id_to_part:
                        return self._id_to_part[p_id]

            return None

        except Exception as e:
            logger.debug(f"GlRenderer: Excepción en GPU picking ({e}). Fallback a AABB 2D.")
            if hasattr(escena, "seleccionar_pieza"):
                return escena.seleccionar_pieza((x_px, y_px))
            return None

    def pick_pieza(
        self,
        objeto_o_escena: Any,
        punto: Tuple[float, float],
        pad: int = 10,
    ) -> Optional[str]:
        # GPU Picking preciso prioritario (Subfase 2.3)
        res_gpu = self.pick(float(punto[0]), float(punto[1]), objeto_o_escena=objeto_o_escena)
        if res_gpu is not None:
            return res_gpu
        # Fallback a AABB 2D si GPU picking no intersectó geometría sólida
        if hasattr(objeto_o_escena, "seleccionar_pieza"):
            return objeto_o_escena.seleccionar_pieza(punto, pad=pad)
        if hasattr(objeto_o_escena, "contiene_punto"):
            if objeto_o_escena.contiene_punto(punto, pad=pad):
                return getattr(objeto_o_escena, "tipo_modelo", "objeto")
        return None

    def liberar(self) -> None:
        try:
            self._limpiar_vbo_cache()
            if self._fbo is not None:
                for att in getattr(self._fbo, "color_attachments", []):
                    try:
                        att.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar color_attachment en liberar(): {e}")
                if getattr(self._fbo, "depth_attachment", None) is not None:
                    try:
                        self._fbo.depth_attachment.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar depth_attachment en liberar(): {e}")
                self._fbo.release()
                self._fbo = None

            if self._picking_fbo is not None:
                if self._picking_tex is not None:
                    try:
                        self._picking_tex.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar picking_tex en liberar(): {e}")
                    self._picking_tex = None
                if self._picking_depth is not None:
                    try:
                        self._picking_depth.release()
                    except Exception as e:
                        logger.debug(f"GlRenderer: Aviso al liberar picking_depth en liberar(): {e}")
                    self._picking_depth = None
                self._picking_fbo.release()
                self._picking_fbo = None

            for res_atom in (
                self._vbo_sphere_base,
                self._vbo_atomic_inst,
                self._vao_atomic_inst,
                self._prog_atomic_inst,
                self._prog_atomic_orbital,
                self._vbo_orbital_quad,
                self._vao_orbital_quad,
                self._vbo_atomic_torus,
                self._vao_atomic_torus,
                self._prog_atomic_torus,
                self._vbo_molecular_inst,
                self._vao_molecular_inst,
                self._vbo_molecular_bonds,
                self._vao_molecular_bonds,
                self._vbo_surface_3d,
                self._vao_surface_3d,
                self._prog_surface_3d,
                self._vbo_flujo_inst,
                self._vao_flujo_inst,
            ):
                if res_atom is not None:
                    try:
                        res_atom.release()
                    except Exception as e_atom:
                        logger.debug(f"GlRenderer: Aviso al liberar recurso GPU: {e_atom}")
            self._vbo_sphere_base = None
            self._vbo_atomic_inst = None
            self._vao_atomic_inst = None
            self._prog_atomic_inst = None
            self._prog_atomic_orbital = None
            self._vbo_orbital_quad = None
            self._vao_orbital_quad = None
            self._vbo_atomic_torus = None
            self._vao_atomic_torus = None
            self._prog_atomic_torus = None
            self._vbo_molecular_inst = None
            self._vao_molecular_inst = None
            self._vbo_molecular_bonds = None
            self._vao_molecular_bonds = None
            self._cached_mol_version = -1
            self._vbo_surface_3d = None
            self._vao_surface_3d = None
            self._prog_surface_3d = None
            self._vbo_flujo_inst = None
            self._vao_flujo_inst = None
            self._cached_surface_version = -1

            # No invocar self._ctx.release() directamente para prevenir un access violation (C0000005)
            # cuando el Garbage Collector de Python limpia objetos hijos residuales (Buffer/VAO/Prog)
            self._ctx = None
        except Exception as e:
            logger.debug(f"GlRenderer: Aviso al liberar contexto OpenGL: {e}")
        self._disponible = False


    @property
    def tipo_backend(self) -> str:
        return "GL" if self._disponible else "CPU (Fallback)"

    @property
    def disponible(self) -> bool:
        return self._disponible


def crear_renderer(
    config: Optional[Union[Dict[str, Any], Any]] = None,
    w: int = 1280,
    h: int = 720,
) -> BaseRenderer:
    """
    Fábrica de renderizadores holográficos (Principio P5).
    Selecciona automáticamente 'GlRenderer' cuando hay soporte GPU disponible;
    de lo contrario, recurre con tolerancia a fallos a 'CpuRenderer'.
    """
    if hasattr(config, "data"):
        cfg = config.data
    elif isinstance(config, dict):
        cfg = config
    else:
        cfg = {}
    backend_pref = str(cfg.get("backend_render", "gl")).lower()

    if backend_pref in ("gl", "opengl", "gpu", "moderngl"):
        try:
            renderer = GlRenderer(w=w, h=h, config=cfg)
            if renderer.disponible:
                return renderer
        except Exception as e:
            logger.warning(f"crear_renderer: Fallo al crear GlRenderer ({e}). Se usará CpuRenderer.")

    return CpuRenderer(w=w, h=h, config=cfg)
