"""Render small light-background PNG previews for AuraTeach's local GLB library.

Run from the repository root:
  blender --background --python prototipo/rodrigo-demos/render-thumbnails.py -- --root .
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    return parser.parse_args(argv)


def clean_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for item in list(datablocks):
            if item.users == 0:
                datablocks.remove(item)


def make_world():
    world = bpy.data.worlds.new("AuraTeach preview world") if not bpy.data.worlds else bpy.data.worlds[0]
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (.83, .86, .91, 1)
    bg.inputs[1].default_value = .8


def add_area_light(name, location, energy, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, 0)) - obj.location).to_track_quat("-Z", "Y").to_euler()


def preview_id(file, root):
    assets = root / "3d_lab_aurateach" / "assets"
    if file.is_relative_to(assets):
        return "lab-" + str(file.relative_to(assets).with_suffix("")).replace("/", "-")
    return {
        "9_13_2025-mejorado.glb": "escuela-scan",
        "flower-pot.glb": "maceta",
        "mushroom_colony_LOD0.glb": "colonia-hongos",
        "lapicero.glb": "lapicero",
    }.get(file.name, file.stem.lower().replace("_", "-"))


def render_one(file, output):
    clean_scene()
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(file))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type in {"MESH", "EMPTY", "CURVE", "FONT", "SURFACE"}]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        print(f"Skip (no mesh): {file}")
        return

    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    minimum = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    maximum = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    center = (minimum + maximum) * .5
    size = maximum - minimum
    maximum_dimension = max(size.x, size.y, size.z, .001)
    scale = 2.0 / maximum_dimension
    transform = Matrix.Scale(scale, 4) @ Matrix.Translation(-center)
    for obj in imported:
        obj.matrix_world = transform @ obj.matrix_world

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 24
    scene.render.resolution_x = 480
    scene.render.resolution_y = 280
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    make_world()
    add_area_light("Key", (3, -4, 5), 850, 4)
    add_area_light("Fill", (-4, -1, 2), 480, 4)
    add_area_light("Rim", (0, 4, 4), 650, 3)

    camera_data = bpy.data.cameras.new("Preview camera")
    camera_obj = bpy.data.objects.new("Preview camera", camera_data)
    bpy.context.collection.objects.link(camera_obj)
    camera_obj.location = (3.3, -4.6, 3.15)
    camera_obj.rotation_euler = (Vector((0, 0, 0)) - camera_obj.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2.85
    scene.camera = camera_obj
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered {output}")


def main():
    args = arguments()
    root = Path(args.root).resolve()
    output_dir = root / "prototipo" / "rodrigo-demos" / "model-thumbnails"
    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted((root / "3d_lab_aurateach" / "assets").rglob("*.glb"))
    files += [root / "9_13_2025-mejorado.glb", root / "flower-pot.glb", root / "mushroom_colony_LOD0.glb", root / "demo-lapicero" / "lapicero.glb"]
    for file in files:
        if file.exists():
            try:
                render_one(file, output_dir / f"{preview_id(file, root)}.png")
            except Exception as error:
                print(f"Render failed for {file}: {error}")


if __name__ == "__main__":
    main()
