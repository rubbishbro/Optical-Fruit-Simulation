"""Render the Blender debug scene for Unity IlluminationMode.RingIllumination.

Coordinate convention: Blender Z is the vertical axis, corresponding to Unity Y.
The Spot Lights are visual helpers only; the printed source table documents the
geometry that the Monte Carlo emitter should consume.
"""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from render_blender_detector_apple import add_area_light, look_at, make_apple, read_ascii_ply  # noqa: E402


def material(name, color, emission=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, alpha)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, alpha)
    bsdf.inputs["Roughness"].default_value = 0.28
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0 and hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


def add_line(name, start, end, mat, width=0.16):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = width
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*start, 1.0)
    spline.points[1].co = (*end, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    return obj


def add_circle(name, center, radius, mat, segments=128, width=0.20):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = width
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(segments)
    for i in range(segments + 1):
        phi = 2.0 * math.pi * i / segments
        spline.points[i].co = (center[0] + radius * math.cos(phi),
                                center[1] + radius * math.sin(phi),
                                center[2], 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    return obj


def add_marker(name, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=scale,
                                         location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def add_sensor_from_startup(sensor_z, detector_objects, scale=24.0):
    rig = bpy.data.objects.new("SensorRig", None)
    bpy.context.collection.objects.link(rig)
    sensor_mat = material("Sensor aperture", (0.05, 0.35, 0.9), emission=1.2)
    for obj in detector_objects:
        obj.parent = rig
        obj.location = (0.0, 0.0, sensor_z)
        obj.scale = (scale, scale, scale)
        if not obj.data.materials:
            obj.data.materials.append(sensor_mat)
    # Explicit finite aperture guide.  The radius scales with the detector.blend
    # geometry instead of becoming a mathematical point.
    aperture_radius = 10.47 * scale / 20.0
    aperture = add_circle("SensorAperture", (0.0, 0.0, sensor_z + 1.1), aperture_radius,
                          sensor_mat, width=0.28)
    aperture.parent = rig
    aperture.location = (0.0, 0.0, sensor_z + 1.1)
    return rig


def add_authored_lightmodel_ring(path, rig, positions, tilt, scale=12.0, gap=0.018):
    """Duplicate the authored lightmodel meshes into every ring position."""
    for index, (position, phi) in enumerate(positions):
        unit = bpy.data.objects.new(f"LightModel_{index:02d}", None)
        bpy.context.collection.objects.link(unit)
        unit.parent = rig
        unit.location = position
        # The source model is two authored cubes and its emitting side is the
        # local +Z side. Blender's positive Y rotation sends +Z toward +X;
        # at phi=0 the apple is toward -X, so the tilt sign must be negative.
        # This keeps the two source cubes intact while turning their emitting
        # side from the ring toward the apple.
        unit.rotation_mode = "QUATERNION"
        unit.rotation_quaternion = (Quaternion(Vector((0.0, 0.0, 1.0)), phi)
                                     @ Quaternion(Vector((0.0, 1.0, 0.0)), -tilt))
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = [name for name in source.objects]
        source_meshes = [obj for obj in target.objects
                         if obj is not None and obj.type == "MESH"]
        source_meshes.sort(key=lambda obj: obj.location.z)
        # The authored cubes meet at this plane. Make it the optical origin,
        # instead of rotating around the large cube's origin.
        contact_top = source_meshes[0].location.z + source_meshes[0].dimensions.z * 0.5
        contact_bottom = source_meshes[1].location.z - source_meshes[1].dimensions.z * 0.5
        emission_plane_z = 0.5 * (contact_top + contact_bottom)
        for source_obj in source_meshes:
            source_obj.name = f"LightModel_{index:02d}_{source_obj.name}"
            bpy.context.collection.objects.link(source_obj)
            source_obj.parent = unit
            # Object scale does not scale parent-space location in Blender.
            # Scale the authored relative offset explicitly as well.
            source_obj.location = tuple(value * scale for value in (
                source_obj.location.x,
                source_obj.location.y,
                source_obj.location.z - emission_plane_z))
            # The authored cubes touch at their mating faces. Add a small
            # source-space gap so the two physical parts remain visually
            # separable after the ring tilt; the gap scales with the model.
            if source_obj.name.endswith(".001"):
                source_obj.location.z += gap * scale
            source_obj.rotation_euler = tuple(source_obj.rotation_euler)
            source_obj.scale = tuple(value * scale for value in source_obj.scale)
    return rig


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.startup_blend))
    # Freeze the detector source objects before loading lightmodel.blend. Both
    # source meshes must remain part of SensorRig; otherwise Blender can
    # resolve duplicate Chinese object names and silently rename/drop one.
    source_detector_objects = [o for o in bpy.data.objects
                               if o.type == "MESH" and o.name in {"柱体", "立方体"}]
    source_detector_objects.sort(key=lambda obj: obj.dimensions.x)
    detector_names = ["DetectorGlass", "DetectorHousing"]
    # Make independent data copies before importing the second blend. This
    # preserves both source meshes and their materials despite Blender's name
    # collision handling for Chinese object names.
    detector_objects = []
    for source_obj, name in zip(source_detector_objects, detector_names):
        obj = source_obj.copy()
        obj.data = source_obj.data.copy()
        obj.name = name
        bpy.context.collection.objects.link(obj)
        detector_objects.append(obj)
    for source_obj in source_detector_objects:
        bpy.data.objects.remove(source_obj, do_unlink=True)
    vertices, _ = read_ascii_ply(args.ply)
    xs, ys, zs = zip(*vertices)
    center = Vector(((min(xs) + max(xs)) * 0.5,
                     (min(ys) + max(ys)) * 0.5,
                     (min(zs) + max(zs)) * 0.5))
    height = max(zs) - min(zs)
    apple_radius = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.5
    apple = make_apple(args.ply, opacity=0.48)
    apple.name = "Apple_ModeB_Debug"

    ring_radius = args.ring_radius_ratio * apple_radius if args.use_ratio else args.ring_radius
    ring_z = center.z + (args.ring_height_ratio * height if args.use_ratio else args.ring_height)
    # Keep the sensor completely below the apple.  The previous version used
    # an offset from the ring plane, which put the detector disk inside the
    # apple's lower half for this mesh.
    sensor_z = (min(zs) - args.sensor_below_bottom if args.use_ratio
                else min(zs) - args.sensor_offset)
    target = Vector((center.x, center.y,
                     center.z + (args.target_height_ratio * height if args.use_ratio else args.target_height)))
    tilt = math.radians(args.light_tilt_deg)
    beam = math.radians(args.beam_divergence_deg)
    power_per_light = args.total_optical_power / args.light_count

    rig = bpy.data.objects.new("RingLightRig", None)
    bpy.context.collection.objects.link(rig)
    light_mat = material("Ring source emission", (1.0, 0.08, 0.008), emission=8.0)
    ray_mat = material("Ring direction guides", (1.0, 0.52, 0.02), emission=3.5)
    guide_mat = material("Ring radius guide", (1.0, 0.15, 0.01), emission=1.5)
    add_circle("RingRadiusGuide", (center.x, center.y, ring_z), ring_radius, guide_mat, width=0.22).parent = rig

    source_rows = []
    authored_positions = []
    for i in range(args.light_count):
        phi = 2.0 * math.pi * i / args.light_count
        position = Vector((center.x + ring_radius * math.cos(phi),
                           center.y + ring_radius * math.sin(phi), ring_z))
        radial_in = Vector((center.x - position.x, center.y - position.y, 0.0)).normalized()
        direction = (radial_in * math.cos(tilt) + Vector((0.0, 0.0, 1.0)) * math.sin(tilt)).normalized()
        authored_positions.append((position, phi))
        obj = bpy.data.lights.new(f"Light_{i:02d}", type="SPOT")
        obj.energy = max(1.0, 1200.0 * power_per_light / max(args.total_optical_power, 1e-9))
        obj.spot_size = min(math.pi, max(0.02, 2.0 * beam))
        obj.spot_blend = 0.35
        light = bpy.data.objects.new(f"Light_{i:02d}", obj)
        bpy.context.collection.objects.link(light)
        light.location = position
        look_at(light, position + direction)
        light.parent = rig
        add_line(f"DirectionRay_{i:02d}", position,
                 position + direction * args.debug_ray_length, ray_mat, width=0.18).parent = rig
        source_rows.append((i, position, direction))

    add_authored_lightmodel_ring(args.light_model, rig, authored_positions,
                                 tilt, args.light_model_scale, args.light_model_gap)
    add_sensor_from_startup(sensor_z, detector_objects)

    # Ground and camera make the vertical relationship easy to inspect.
    ground_mat = material("Ground", (0.018, 0.024, 0.038))
    mesh = bpy.data.meshes.new("mode_b_ground_mesh")
    mesh.from_pydata([(-100, -100, sensor_z - 1.8), (100, -100, sensor_z - 1.8),
                      (100, 100, sensor_z - 1.8), (-100, 100, sensor_z - 1.8)], [], [(0, 1, 2, 3)])
    mesh.materials.append(ground_mat)
    ground = bpy.data.objects.new("ModeB_Ground", mesh)
    bpy.context.collection.objects.link(ground)

    camera_data = bpy.data.cameras.new("ModeB_Debug_Camera")
    camera = bpy.data.objects.new("ModeB_Debug_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (92.0, -118.0, center.z + 70.0)
    camera.data.lens = 55.0
    look_at(camera, (center.x, center.y, center.z - 3.0))
    bpy.context.scene.camera = camera
    add_area_light("ModeB_Key", (38, -50, 95), 1000.0, 60.0, center)
    add_area_light("ModeB_Fill", (-60, 25, 38), 500.0, 48.0, center)

    scene = bpy.context.scene
    engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 820
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(args.output)
    scene.world.color = (0.006, 0.009, 0.018)
    scene.render.film_transparent = False
    scene["Mode"] = "RingIllumination"
    scene["UnityVerticalAxis"] = "Y; Blender debug mapping is Z"
    scene["lightCount"] = args.light_count
    scene["ringRadius"] = ring_radius
    scene["ringHeightOffset"] = ring_z - center.z
    scene["lightTiltDeg"] = args.light_tilt_deg
    scene["beamDivergenceDeg"] = args.beam_divergence_deg
    scene["totalOpticalPower"] = args.total_optical_power
    scene["powerPerLight"] = power_per_light
    scene["sensorCenter"] = tuple((0.0, 0.0, sensor_z))
    scene["sensorRadius"] = 10.47 * 24.0 / 20.0
    scene["detectorSourceBlend"] = str(args.startup_blend)
    scene["lightModelSourceBlend"] = str(args.light_model)
    scene["lightModelScale"] = args.light_model_scale
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.with_suffix(".blend")))
    bpy.ops.render.render(write_still=True)
    print("Mode B parameters:", {"lightCount": args.light_count, "ringRadius": round(ring_radius, 3),
                                  "ringHeightOffset": round(ring_z - center.z, 3),
                                  "lightTiltDeg": args.light_tilt_deg,
                                  "beamDivergenceDeg": args.beam_divergence_deg,
                                  "powerPerLight": power_per_light,
                                  "sensorZ": round(sensor_z, 3)})
    print("Rendered", args.output)
    print("Saved", args.output.with_suffix(".blend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--startup-blend", type=Path, required=True)
    parser.add_argument("--ply", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--light-model", type=Path, required=True)
    parser.add_argument("--light-model-scale", type=float, default=12.0)
    parser.add_argument("--light-model-gap", type=float, default=0.06,
                        help="small source-space gap between the two authored cubes")
    parser.add_argument("--light-count", type=int, default=12)
    parser.add_argument("--use-ratio", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ring-radius-ratio", type=float, default=1.08)
    parser.add_argument("--ring-radius", type=float, default=37.0)
    parser.add_argument("--ring-height-ratio", type=float, default=-0.28)
    parser.add_argument("--ring-height", type=float, default=-19.0)
    parser.add_argument("--light-tilt-deg", type=float, default=35.0)
    parser.add_argument("--beam-divergence-deg", type=float, default=12.0)
    parser.add_argument("--target-height-ratio", type=float, default=0.04)
    parser.add_argument("--target-height", type=float, default=2.7)
    parser.add_argument("--total-optical-power", type=float, default=1.0)
    parser.add_argument("--sensor-offset-ratio", type=float, default=0.55,
                        help="legacy ratio retained for compatibility")
    parser.add_argument("--sensor-below-bottom", type=float, default=14.0,
                        help="distance below the apple's lowest mesh point")
    parser.add_argument("--sensor-offset", type=float, default=12.0)
    parser.add_argument("--debug-ray-length", type=float, default=25.0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    render(args)


if __name__ == "__main__":
    main()
