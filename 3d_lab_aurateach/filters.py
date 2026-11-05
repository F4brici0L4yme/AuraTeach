"""
filters.py
-------------------------------------------------------------------
Módulo centralizado de filtrado y suavizado anti-temblor (Anti-Jitter)
para interacción táctil y control gestual en tiempo real.
Consolida:
- LowPassFilter: Filtro de paso bajo exponencial de primer orden.
- LowPassFilterEMA: Filtro de promedio móvil exponencial configurable.
- OneEuroFilter (1€ Filter): Algoritmo de Casiez et al. (CHI 2012)
  con corte adaptativo según velocidad para 1 dimensión.
- OneEuroFilter2D: Adaptación cartesiana 2D para coordenadas (X, Y).
-------------------------------------------------------------------
"""

import math
import time
from typing import Any, List, Optional, Tuple

import numpy as np


class LowPassFilter:
    """Filtro de paso bajo exponencial de primer orden."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha: float = alpha
        self.last_val: Optional[float] = None

    def filter(self, value: float, alpha: Optional[float] = None) -> float:
        if not math.isfinite(value):
            return self.last_val if self.last_val is not None else 0.0
        if alpha is not None:
            self.alpha = alpha
        if self.last_val is None:
            self.last_val = value
            return value
        filtered = self.alpha * value + (1.0 - self.alpha) * self.last_val
        self.last_val = filtered
        return filtered

    def get_last(self) -> Optional[float]:
        return self.last_val

    def reset(self) -> None:
        self.last_val = None


class LowPassFilterEMA:
    """Filtro de Promedio Móvil Exponencial (EMA) para suavizado anti-temblor."""

    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha: float = alpha
        self.last_val: Optional[float] = None

    def filter(self, val: float) -> float:
        if self.last_val is None:
            self.last_val = val
            return val
        filtered = self.alpha * val + (1.0 - self.alpha) * self.last_val
        self.last_val = filtered
        return filtered

    def reset(self) -> None:
        self.last_val = None


class OneEuroFilter:
    """
    Implementación del algoritmo '1€ Filter' (Casiez, Roussel, Vogel - CHI 2012).
    Ajusta dinámicamente la frecuencia de corte según la velocidad del movimiento:
    - Bajas velocidades: corte bajo -> elimina temblores involuntarios y ruido.
    - Altas velocidades: corte alto -> latencia mínima sin retraso percibido.
    """

    def __init__(
        self,
        min_cutoff: float = 0.02,
        beta: float = 0.08,
        d_cutoff: float = 1.0,
        deadband: float = 0.0,
    ) -> None:
        self.min_cutoff: float = float(min_cutoff)
        self.beta: float = float(beta)
        self.d_cutoff: float = float(d_cutoff)
        self.deadband: float = float(deadband)
        self.x_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        self.last_time: Optional[float] = None
        self.prev_x: Optional[float] = None
        self.last_out: Optional[float] = None
        self.dx: float = 0.0

    @staticmethod
    def _calcular_alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-4))
        return 1.0 / (1.0 + tau / max(dt, 1e-5))

    def filter(
        self,
        x: float,
        timestamp: Optional[float] = None,
        t: Optional[float] = None,
        deadband: Optional[float] = None,
    ) -> float:
        # LOW-03: Guardia estricta contra NaN/Inf para evitar degradación permanente del filtro
        if not math.isfinite(x):
            last_x = self.x_filter.get_last()
            return last_x if last_x is not None else 0.0

        time_val = timestamp if timestamp is not None else t
        now_t = float(time_val) if time_val is not None else time.perf_counter()
        if self.last_time is None:
            self.last_time = now_t
            self.prev_x = x
            self.dx = 0.0
            out0 = self.x_filter.filter(x, 1.0)
            self.last_out = out0
            return out0

        dt = now_t - self.last_time
        # LOW-04: Si transcurrió una pausa prolongada (> 0.5s), reiniciar derivada para suprimir picos
        if dt > 0.5:
            self.last_time = now_t
            self.prev_x = x
            self.dx = 0.0
            self.dx_filter.reset()
            out_reset = self.x_filter.filter(x, 1.0)
            self.last_out = out_reset
            return out_reset

        dt = max(dt, 1e-5)
        self.last_time = now_t

        # Derivada (velocidad instantánea)
        prev = self.x_filter.get_last()
        self.prev_x = prev
        dx = 0.0 if prev is None else (x - prev) / dt
        self.dx = dx

        # Suavizado de la derivada
        alpha_d = self._calcular_alpha(self.d_cutoff, dt)
        edx = self.dx_filter.filter(dx, alpha_d)

        # Frecuencia de corte adaptativa dependiente de la velocidad
        cutoff = self.min_cutoff + self.beta * abs(edx)
        alpha = self._calcular_alpha(cutoff, dt)
        filtered = self.x_filter.filter(x, alpha)

        db = float(deadband) if deadband is not None else self.deadband
        if db > 0.0 and self.last_out is not None:
            if abs(filtered - self.last_out) < db:
                return self.last_out

        self.last_out = filtered
        return filtered

    def reset(self) -> None:
        self.x_filter.reset()
        self.dx_filter.reset()
        self.last_time = None
        self.prev_x = None
        self.last_out = None
        self.dx = 0.0


# Alias para compatibilidad
OneEuroFilter1D = OneEuroFilter


class OneEuroFilter2D:
    """Filtro One Euro para coordenadas cartesianas (X, Y) en 2D con zona muerta opcional."""

    def __init__(
        self,
        min_cutoff: float = 0.02,
        beta: float = 0.08,
        d_cutoff: float = 1.0,
        deadband: float = 1.5,
    ) -> None:
        self.filter_x = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.filter_y = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.deadband: float = float(deadband)
        self.last_point: Optional[Tuple[float, float]] = None

    @property
    def prev_x(self) -> Optional[float]:
        return self.filter_x.prev_x

    @property
    def prev_y(self) -> Optional[float]:
        return self.filter_y.prev_x

    @property
    def dx(self) -> float:
        return self.filter_x.dx

    @property
    def dy(self) -> float:
        return self.filter_y.dx

    @property
    def speed(self) -> float:
        """Velocidad euclidiana instantánea (magnitud de la derivada)."""
        return math.hypot(self.dx, self.dy)

    def filter(
        self,
        point: Tuple[float, float],
        timestamp: Optional[float] = None,
        t: Optional[float] = None,
        deadband: Optional[float] = None,
    ) -> Tuple[float, float]:
        # LOW-03: Guardia defensiva contra NaN/Inf en puntos 2D
        px_val, py_val = float(point[0]), float(point[1])
        if not math.isfinite(px_val) or not math.isfinite(py_val):
            return self.last_point if self.last_point is not None else (0.0, 0.0)

        time_val = timestamp if timestamp is not None else t
        px = self.filter_x.filter(px_val, timestamp=time_val)
        py = self.filter_y.filter(py_val, timestamp=time_val)

        # Zona muerta dinámica o configurada
        db = float(deadband) if deadband is not None else self.deadband
        if db > 0.0 and self.last_point is not None:
            dist = math.hypot(px - self.last_point[0], py - self.last_point[1])
            if dist < db:
                return self.last_point

        self.last_point = (px, py)
        return (px, py)

    def reset(self) -> None:
        self.filter_x.reset()
        self.filter_y.reset()
        self.last_point = None


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


class OneEuroFilter3D:
    """Filtro One Euro adaptativo para coordenadas (X, Y, Z) en 3D."""

    def __init__(
        self,
        min_cutoff: float = 0.05,
        beta: float = 0.05,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff: float = float(min_cutoff)
        self.beta: float = float(beta)
        self.d_cutoff: float = float(d_cutoff)
        self.filter_x = OneEuroFilter(self.min_cutoff, self.beta, self.d_cutoff)
        self.filter_y = OneEuroFilter(self.min_cutoff, self.beta, self.d_cutoff)
        self.filter_z = OneEuroFilter(self.min_cutoff, self.beta, self.d_cutoff)
        self.last_point: Optional[Tuple[float, float, float]] = None

    def filter(
        self,
        x: float,
        y: float,
        z: float = 0.0,
        timestamp: Optional[float] = None,
        t: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        t_val = timestamp if timestamp is not None else t
        fx = self.filter_x.filter(x, timestamp=t_val)
        fy = self.filter_y.filter(y, timestamp=t_val)
        fz = self.filter_z.filter(z, timestamp=t_val)
        self.last_point = (fx, fy, fz)
        return (fx, fy, fz)

    def reset(self) -> None:
        self.filter_x.reset()
        self.filter_y.reset()
        self.filter_z.reset()
        self.last_point = None


class BancoLandmarksFilter:
    """
    Banco de 21 filtros OneEuroFilter3D para estabilizar las coordenadas (X, Y, Z)
    de todas las articulaciones esqueléticas de la mano antes del cálculo gestual.
    """

    def __init__(
        self,
        min_cutoff: float = 0.8,
        beta: float = 0.02,
        d_cutoff: float = 1.0,
        diferenciado: bool = True,
    ) -> None:
        self.min_cutoff: float = float(min_cutoff)
        self.beta: float = float(beta)
        self.d_cutoff: float = float(d_cutoff)
        self.diferenciado: bool = diferenciado
        self.filtros = []
        for i in range(21):
            if diferenciado and i in (2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16, 18, 19, 20):
                # Dedos finos: alta fidelidad y reactividad sin jitter
                self.filtros.append(OneEuroFilter3D(min_cutoff=1.2, beta=0.04, d_cutoff=self.d_cutoff))
            else:
                # Muñeca y base de palma (0, 1, 5, 9, 13, 17): anclaje ultra-estable
                self.filtros.append(OneEuroFilter3D(min_cutoff=0.8, beta=0.02, d_cutoff=self.d_cutoff))

    def filter_pts(
        self,
        pts: np.ndarray,
        timestamp: Optional[float] = None,
    ) -> np.ndarray:
        """Filtra un array numpy de puntos en píxeles (N, 2) o (N, 3)."""
        if pts is None or len(pts) < 21:
            return pts
        res = pts.copy()
        n = min(len(pts), 21)
        tiene_z = (pts.shape[1] >= 3)
        for i in range(n):
            z_val = float(pts[i, 2]) if tiene_z else 0.0
            fx, fy, fz = self.filtros[i].filter(
                float(pts[i, 0]), float(pts[i, 1]), z_val, timestamp=timestamp
            )
            res[i, 0] = fx
            res[i, 1] = fy
            if tiene_z:
                res[i, 2] = fz
        return res

    def filter_landmarks(
        self,
        lm: List[Any],
        timestamp: Optional[float] = None,
    ) -> List[Any]:
        """Filtra una lista de landmarks normalizados (objetos con .x, .y, .z)."""
        if lm is None or len(lm) < 21:
            return lm
        n = min(len(lm), 21)
        res = []
        for i in range(n):
            item = lm[i]
            x_val = float(getattr(item, "x", item[0] if isinstance(item, (list, tuple)) else 0.0))
            y_val = float(getattr(item, "y", item[1] if isinstance(item, (list, tuple)) else 0.0))
            z_val = float(getattr(item, "z", item[2] if isinstance(item, (list, tuple)) and len(item) > 2 else 0.0))
            fx, fy, fz = self.filtros[i].filter(x_val, y_val, z_val, timestamp=timestamp)
            res.append(LandmarkPoint(fx, fy, fz))
        if len(lm) > 21:
            res.extend(lm[21:])
        return res

    def reset(self) -> None:
        for f in self.filtros:
            f.reset()
