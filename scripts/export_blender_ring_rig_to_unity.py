"""Export the authored Blender ring/fruit rig as a Unity-ready FBX asset.

Run with Blender, not regular Python:

    blender -b assets/blender/alternatives/01_ring_illumination_debug.blend \
      --python scripts/export_blender_ring_rig_to_unity.py -- \
      apps/fruitsim_unity/Assets/Resources/FruitsimBlenderRig.fbx

The source scene is authored in millimetre-like units with Blender Z up.  The
export root applies a 0.03 presentation scale and the FBX exporter converts Z
up to Unity Y up.  Runtime optical geometry remains parameter-driven; this FBX
supplies the authored apple, detector, and lamp housings.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bpy


PRESENTATION_SCALE = 0.03


def _output_path() -> Path:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit("expected exactly one FBX output path after --")
    return Path(args[0]).resolve()


def _lamp_part_name(name: str) -> str | None:
    match = re.match(r"LightModel_(\d{2})_(.+)", name)
    if not match:
        return None
    index, suffix = match.groups()
    return f"RingLampEmitter_{index}" if suffix.endswith(".001") else f"RingLampHousing_{index}"


def _set_material_color(obj: bpy.types.Object, rgba: tuple[float, float, float, float]) -> None:
    if obj.type != "MESH":
        return
    if not obj.data.materials:
        material = bpy.data.materials.new(obj.name + "_Material")
        obj.data.materials.append(material)
    for material in obj.data.materials:
        material.diffuse_color = rgba


def main() -> None:
    output = _output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    selected: list[bpy.types.Object] = []
    for obj in list(bpy.context.scene.objects):
        if obj.name == "Apple_ModeB_Debug":
            obj.name = "BlenderApple"
            _set_material_color(obj, (0.45, 0.035, 0.025, 1.0))
            selected.append(obj)
        elif obj.name == "DetectorGlass":
            _set_material_color(obj, (0.02, 0.32, 0.85, 1.0))
            selected.append(obj)
        elif obj.name == "DetectorHousing":
            _set_material_color(obj, (0.035, 0.055, 0.085, 1.0))
            selected.append(obj)
        elif (new_name := _lamp_part_name(obj.name)) is not None:
            obj.name = new_name
            color = (1.0, 0.24, 0.02, 1.0) if "Emitter" in new_name else (0.22, 0.24, 0.28, 1.0)
            _set_material_color(obj, color)
            selected.append(obj)

    if not any(obj.name == "BlenderApple" for obj in selected):
        raise RuntimeError("source scene does not contain Apple_ModeB_Debug")
    if len([obj for obj in selected if obj.name.startswith("RingLamp")]) != 24:
        raise RuntimeError("source scene must contain 12 two-part authored ring lamps")

    root = bpy.data.objects.new("FruitsimBlenderRig", None)
    bpy.context.collection.objects.link(root)
    selected_names = {obj.name for obj in selected}
    for obj in selected:
        if obj.parent is None or obj.parent.name not in selected_names:
            world_transform = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world_transform
    root.scale = (PRESENTATION_SCALE,) * 3

    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for obj in selected:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.fbx(
        filepath=str(output),
        use_selection=True,
        object_types={"EMPTY", "MESH"},
        axis_forward="-Z",
        axis_up="Y",
        apply_unit_scale=False,
        apply_scale_options="FBX_SCALE_ALL",
        bake_space_transform=False,
        add_leaf_bones=False,
        path_mode="AUTO",
        embed_textures=False,
    )
    print(f"Exported Unity rig: {output}")
    print(f"Objects: {len(selected)} meshes + root; presentation scale={PRESENTATION_SCALE}")


if __name__ == "__main__":
    main()
