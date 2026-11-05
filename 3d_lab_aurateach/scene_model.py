"""
scene_model.py
-------------------------------------------------------------------
Módulo desacoplado de jerarquía de modelos y nodos de escena 3D.
Re-exporta SceneModel y Objeto3D para cumplir con el desacoplamiento
arquitectónico de STARK Mark v3.
-------------------------------------------------------------------
"""

from hologram import Objeto3D, SceneModel

__all__ = ["Objeto3D", "SceneModel"]

