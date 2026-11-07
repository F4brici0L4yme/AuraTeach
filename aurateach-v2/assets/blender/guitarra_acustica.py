"""Create a single, educational steel-string acoustic guitar asset for AuraTeach.

Run inside Blender 5.1+ (or through Blender Lab MCP). The file contains one
assembled guitar made from named mesh parts plus a review-only camera.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUT_DIR = os.path.join(ROOT, "assets", "blender", "guitarra_acustica")
BLEND_PATH = os.path.join(OUTPUT_DIR, "guitarra_acustica.blend")
GLB_PATH = os.path.join(OUTPUT_DIR, "guitarra_acustica.glb")


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.context.scene.collection.children):
        bpy.context.scene.collection.children.unlink(collection)
        bpy.data.collections.remove(collection)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def make_material(name: str, color: tuple[float, float, float], roughness: float = 0.52, metallic: float = 0.0):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return material


WOOD_TOP = make_material("Madera · abeto claro", (0.76, 0.49, 0.23), 0.67)
WOOD_SIDE = make_material("Madera · aros y fondo", (0.36, 0.16, 0.08), 0.53)
WOOD_NECK = make_material("Madera · nogal del mástil", (0.28, 0.12, 0.055), 0.48)
WOOD_BRACE = make_material("Madera · varetas interiores", (0.88, 0.67, 0.37), 0.62)
FRETBOARD = make_material("Ébano · diapasón", (0.075, 0.055, 0.045), 0.42)
INK = make_material("Negro · boca y detalles", (0.035, 0.026, 0.02), 0.65)
IVORY = make_material("Hueso · cejuela y selleta", (0.94, 0.84, 0.64), 0.42)
STEEL = make_material("Acero · cuerdas y clavijas", (0.63, 0.70, 0.75), 0.28, 0.78)
PEARL = make_material("Nácar · marcadores", (0.87, 0.86, 0.77), 0.32, 0.12)


def link_to_model(obj: bpy.types.Object, parent: bpy.types.Object | None = None) -> bpy.types.Object:
    collection = bpy.data.collections.get("Guitarra_acustica")
    if collection is None:
        collection = bpy.data.collections.new("Guitarra_acustica")
        bpy.context.scene.collection.children.link(collection)
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj["aura_part"] = True
    return obj


def finish_mesh(obj: bpy.types.Object, name: str, material, parent: bpy.types.Object | None = None):
    obj.name = name
    obj.data.name = name + "_mesh"
    obj.data.materials.append(material)
    return link_to_model(obj, parent)


def smooth_outline(points: list[tuple[float, float]], steps: int = 5) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    count = len(points)
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
        for step in range(steps):
            t = step / steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0]) * t2 + (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1]) * t2 + (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1]) * t3)
            result.append((x, y))
    return result


BODY = smooth_outline([
    (-0.46, 1.50), (-0.84, 1.33), (-1.06, 1.02), (-1.02, 0.66),
    (-0.76, 0.35), (-0.51, 0.13), (-0.69, -0.24), (-1.16, -0.62),
    (-1.34, -1.08), (-1.24, -1.53), (-0.81, -1.87), (0.0, -1.98),
    (0.81, -1.87), (1.24, -1.53), (1.34, -1.08), (1.16, -0.62),
    (0.69, -0.24), (0.51, 0.13), (0.76, 0.35), (1.02, 0.66),
    (1.06, 1.02), (0.84, 1.33), (0.46, 1.50),
])


def plate(name: str, outline: list[tuple[float, float]], z: float, thickness: float, material, parent):
    n = len(outline)
    vertices = [(x, y, z) for x, y in outline]
    vertices.append((0.0, -0.15, z))
    faces = [(n, i, (i + 1) % n) for i in range(n)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    finish_mesh(obj, name, material, parent)
    if thickness:
        solid = obj.modifiers.new("Grosor de la pieza", "SOLIDIFY")
        solid.thickness = thickness
        solid.offset = -1.0
        bevel = obj.modifiers.new("Bordes suaves", "BEVEL")
        bevel.width = 0.035
        bevel.segments = 2
    return obj


def side_shell(name: str, outline: list[tuple[float, float]], top_z: float, bottom_z: float, material, parent):
    n = len(outline)
    vertices = [(x, y, top_z) for x, y in outline] + [(x, y, bottom_z) for x, y in outline]
    faces = [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish_mesh(obj, name, material, parent)


def bevel_box(name: str, location: tuple[float, float, float], dimensions: tuple[float, float, float], material, parent, bevel: float = 0.025):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    finish_mesh(obj, name, material, parent)
    if bevel:
        modifier = obj.modifiers.new("Cantos redondeados", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        obj.modifiers.new("Normales suaves", "WEIGHTED_NORMAL")
    return obj


def beam(name: str, a: tuple[float, float, float], b: tuple[float, float, float], width: float, height: float, material, parent):
    start = Vector(a)
    end = Vector(b)
    direction = end - start
    obj = bevel_box(name, tuple((start + end) * 0.5), (width, direction.length, height), material, parent, min(width, height) * 0.22)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Y", "Z")
    return obj


def cylinder(name: str, a: tuple[float, float, float], b: tuple[float, float, float], radius: float, material, parent, vertices: int = 16):
    start = Vector(a)
    end = Vector(b)
    direction = end - start
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=direction.length, location=tuple((start + end) * 0.5))
    obj = bpy.context.object
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return finish_mesh(obj, name, material, parent)


def sphere(name: str, location: tuple[float, float, float], radius: float, material, parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=radius, location=location)
    obj = bpy.context.object
    bpy.ops.object.shade_smooth()
    return finish_mesh(obj, name, material, parent)


def ring(name: str, location: tuple[float, float, float], major: float, minor: float, material, parent):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=64, minor_segments=8, location=location)
    obj = bpy.context.object
    bpy.ops.object.shade_smooth()
    return finish_mesh(obj, name, material, parent)


def polyline(name: str, points: list[tuple[float, float, float]], radius: float, material, parent):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    curve.materials.append(material)
    return link_to_model(obj, parent)


def add_camera() -> None:
    review = bpy.data.collections.new("Revision_no_exportar")
    bpy.context.scene.collection.children.link(review)
    data = bpy.data.cameras.new("Camara_revision")
    camera = bpy.data.objects.new("Camara_revision", data)
    review.objects.link(camera)
    camera.location = (8.2, -7.5, 11.5)
    target = Vector((0.0, 1.5, 0.0))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.type = "ORTHO"
    data.ortho_scale = 8.7
    bpy.context.scene.camera = camera


def build() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    clear_scene()
    scene = bpy.context.scene
    root = bpy.data.objects.new("Guitarra_Acustica", None)
    root.empty_display_type = "CIRCLE"
    root.empty_display_size = 0.18
    model_collection = bpy.data.collections.new("Guitarra_acustica")
    scene.collection.children.link(model_collection)
    model_collection.objects.link(root)
    root["display_name"] = "Guitarra acústica de cuerdas metálicas"
    root["description"] = "Modelo educativo con tapa desmontable y refuerzos interiores visibles."

    # Hollow body shell: these panels are separate so the soundboard can be removed.
    side_shell("Aros_del_cuerpo", BODY, 0.12, -0.22, WOOD_SIDE, root)
    plate("Fondo_del_cuerpo", BODY, -0.22, -0.065, WOOD_SIDE, root)
    top = plate("Tapa_armonica_desmontable", BODY, 0.12, -0.045, WOOD_TOP, root)
    top["display_name"] = "Tapa armónica desmontable"
    top["removable"] = True

    # Internal wooden structure below the removable top.
    bevel_box("Bloque_del_mastil", (0.0, 1.12, -0.025), (0.76, 0.38, 0.21), WOOD_BRACE, root, 0.025)
    bevel_box("Bloque_inferior", (0.0, -1.56, -0.025), (0.52, 0.30, 0.21), WOOD_BRACE, root, 0.025)
    beam("Vareta_X_izquierda", (-0.96, -0.92, -0.035), (0.33, 0.39, -0.035), 0.10, 0.13, WOOD_BRACE, root)
    beam("Vareta_X_derecha", (0.96, -0.92, -0.035), (-0.33, 0.39, -0.035), 0.10, 0.13, WOOD_BRACE, root)
    beam("Vareta_transversal_inferior", (-0.88, -1.22, -0.035), (0.88, -1.22, -0.035), 0.10, 0.13, WOOD_BRACE, root)
    beam("Vareta_transversal_superior", (-0.72, 0.45, -0.035), (0.72, 0.45, -0.035), 0.09, 0.12, WOOD_BRACE, root)
    beam("Vareta_fan_izquierda", (-0.23, 0.28, -0.04), (-0.82, -0.82, -0.04), 0.06, 0.10, WOOD_BRACE, root)
    beam("Vareta_fan_centro_izquierda", (-0.10, 0.18, -0.04), (-0.40, -1.02, -0.04), 0.06, 0.10, WOOD_BRACE, root)
    beam("Vareta_fan_centro_derecha", (0.10, 0.18, -0.04), (0.40, -1.02, -0.04), 0.06, 0.10, WOOD_BRACE, root)
    beam("Vareta_fan_derecha", (0.23, 0.28, -0.04), (0.82, -0.82, -0.04), 0.06, 0.10, WOOD_BRACE, root)
    bevel_box("Placa_interior_del_puente", (0.0, -0.35, -0.015), (0.58, 0.33, 0.10), WOOD_BRACE, root, 0.02)

    # Neck and headstock.
    bevel_box("Mastil", (0.0, 2.45, 0.19), (0.62, 2.92, 0.27), WOOD_NECK, root, 0.08)
    bevel_box("Talon_del_mastil", (0.0, 1.12, 0.17), (0.70, 0.46, 0.37), WOOD_NECK, root, 0.08)
    bevel_box("Diapason", (0.0, 2.48, 0.345), (0.55, 2.78, 0.075), FRETBOARD, root, 0.035)
    bevel_box("Pala", (0.0, 4.18, 0.22), (1.30, 1.10, 0.22), WOOD_NECK, root, 0.11)
    # Sixteen raised fret bars are combined in one semantic mesh for simple part selection.
    fret_parts = []
    nut_y = 3.72
    scale_length = 3.45
    for fret in range(1, 21):
        y = nut_y - scale_length * (1.0 - 2.0 ** (-fret / 12.0))
        if y < 1.20:
            break
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, y, 0.389))
        fret_obj = bpy.context.object
        fret_obj.dimensions = (0.54, 0.027, 0.026)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        fret_parts.append(fret_obj)
    bpy.ops.object.select_all(action="DESELECT")
    for item in fret_parts:
        item.select_set(True)
    bpy.context.view_layer.objects.active = fret_parts[0]
    bpy.ops.object.join()
    frets = finish_mesh(bpy.context.object, "Trastes", STEEL, root)
    frets["display_name"] = "Trastes"
    for index, y in enumerate((3.42, 2.60, 1.75), start=1):
        sphere(f"Marcador_de_posicion_{index}", (0.0, y, 0.39), 0.065, PEARL, root)

    # Bridge, saddle, pins and sound-hole trim.
    bevel_box("Puente", (0.0, -0.34, 0.19), (0.82, 0.23, 0.14), WOOD_NECK, root, 0.035)
    bevel_box("Selleta", (0.0, -0.245, 0.275), (0.64, 0.035, 0.09), IVORY, root, 0.01)
    pins = []
    for index in range(6):
        x = -0.25 + index * 0.10
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.043, location=(x, -0.42, 0.275))
        pins.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for item in pins:
        item.select_set(True)
    bpy.context.view_layer.objects.active = pins[0]
    bpy.ops.object.join()
    finish_mesh(bpy.context.object, "Pines_del_puente", IVORY, root)
    ring("Roseta_exterior", (0.0, 0.47, 0.151), 0.48, 0.026, WOOD_NECK, root)
    ring("Roseta_interior", (0.0, 0.47, 0.153), 0.40, 0.018, IVORY, root)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.385, depth=0.008, location=(0.0, 0.47, 0.13))
    finish_mesh(bpy.context.object, "Fondo_oscuro_de_la_boca", INK, root)

    # Nut and six strings. The string set is one semantic part in this first asset.
    bevel_box("Cejuela", (0.0, 3.72, 0.405), (0.61, 0.075, 0.09), IVORY, root, 0.018)
    for index in range(6):
        x = -0.205 + index * 0.082
        side = -1 if index < 3 else 1
        tuner_y = 3.98 + (index if side == -1 else 5 - index) * 0.25
        tuner_x = side * 0.43
        polyline(
            f"Cuerda_{index + 1}",
            [(x, -0.245, 0.33), (x, 0.47, 0.43), (x, 3.72, 0.43), (tuner_x, tuner_y, 0.43)],
            0.012 if index < 3 else 0.016,
            STEEL,
            root,
        )

    # Three tuning machines on each side, each retained as separately named pieces.
    for side_name, sign in (("Izquierda", -1.0), ("Derecha", 1.0)):
        for index, y in enumerate((4.00, 4.25, 4.50), start=1):
            x = sign * 0.48
            cylinder(f"Clavija_{side_name}_{index}_eje", (x, y, 0.15), (x + sign * 0.20, y, 0.15), 0.045, STEEL, root)
            sphere(f"Clavija_{side_name}_{index}_mariposa", (x + sign * 0.27, y, 0.15), 0.09, PEARL, root)
            cylinder(f"Clavija_{side_name}_{index}_poste", (x, y, 0.22), (x, y, 0.46), 0.034, STEEL, root, 12)

    add_camera()
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1500
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.92, 0.91, 0.87)
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.curvature_ridge_factor = 1.4
    scene.display.shading.curvature_valley_factor = 1.0
    scene.display.shading.show_object_outline = True
    scene.display.shading.object_outline_color = (0.08, 0.055, 0.035)
    scene.display.shading.background_type = "WORLD"
    scene.display.shading.show_shadows = True
    scene.view_settings.view_transform = "Standard"
    scene.camera.data.lens = 50

    # Save only the model and review camera. Export selection omits the camera.
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for child in root.children_recursive:
        child.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
    )
    print(f"GUITAR_BLEND={BLEND_PATH}")
    print(f"GUITAR_GLB={GLB_PATH}")
    print(f"GUITAR_PARTS={len([obj for obj in bpy.context.scene.objects if obj.get('aura_part')])}")


build()
