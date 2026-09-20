"""Run inside Blender: render the blend detector beneath the fruitsim apple mesh."""

import argparse
import csv
import math
from pathlib import Path

import bpy
from mathutils import Vector


def read_ascii_ply(path):
    lines = Path(path).read_text(encoding="ascii").splitlines()
    vertex_count = face_count = 0
    header_end = None
    for index, line in enumerate(lines):
        fields = line.split()
        if fields[:2] == ["element", "vertex"]:
            vertex_count = int(fields[2])
        elif fields[:2] == ["element", "face"]:
            face_count = int(fields[2])
        elif line == "end_header":
            header_end = index + 1
            break
    if header_end is None:
        raise RuntimeError("PLY header is missing end_header")
    vertices = [tuple(float(value) for value in line.split()[:3])
                for line in lines[header_end:header_end + vertex_count]]
    faces = [tuple(int(value) for value in line.split()[1:4])
             for line in lines[header_end + vertex_count:
                               header_end + vertex_count + face_count]]
    return vertices, faces


def look_at(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(name, location, energy, size, target):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def make_apple(ply_path, opacity=1.0):
    vertices, faces = read_ascii_ply(ply_path)
    mesh = bpy.data.meshes.new("fruitsim_real_apple_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    apple = bpy.data.objects.new("fruitsim_real_apple", mesh)
    bpy.context.collection.objects.link(apple)

    material = bpy.data.materials.new("Apple translucent demo")
    material.diffuse_color = (0.58, 0.025, 0.012, opacity)
    material.use_nodes = True
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.58, 0.025, 0.012, opacity)
    bsdf.inputs["Roughness"].default_value = 0.34
    bsdf.inputs["Alpha"].default_value = opacity
    if opacity < 1.0:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
    apple.data.materials.append(material)
    return apple


def read_detector_rays(path):
    traces = {}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            key = (row["wavelength_nm"], row["photon_id"])
            traces.setdefault(key, []).append(
                ((float(row["x_mm"]), float(row["y_mm"]), float(row["z_mm"])),
                 float(row["weight"]))
            )
    return list(traces.values())


def make_ray_material(name, color, strength=3.0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.22
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    return material


def add_ray_curve(name, coordinates, material, bevel_depth):
    if len(coordinates) < 2:
        return
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(coordinates) - 1)
    for point, coordinate in zip(spline.points, coordinates):
        point.co = (*coordinate, 1.0)
    ray = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(ray)
    curve.materials.append(material)


def make_ray_visualization(rays_path, weighted=False, max_traces=0, max_points=600):
    if not rays_path:
        return
    traces = read_detector_rays(rays_path)
    if not traces:
        return
    if max_traces > 0:
        traces = traces[:max_traces]
    colors = [(0.267, 0.004, 0.329), (0.283, 0.141, 0.458),
              (0.254, 0.265, 0.530), (0.164, 0.471, 0.558),
              (0.135, 0.659, 0.518), (0.478, 0.821, 0.318),
              (0.993, 0.906, 0.144)]
    materials = [make_ray_material(f"Photon weight bin {index}", color,
                                    1.5 + 3.0 * index / (len(colors) - 1))
                 for index, color in enumerate(colors)] if weighted else [
                     make_ray_material("Photon paths", (1.0, 0.04, 0.005), 3.0)]

    # Use curves for multi-event paths. In weighted mode, split a path into
    # contiguous weight bins so attenuation is visible inside Blender too.
    for index, trace in enumerate(traces):
        if max_points > 1 and len(trace) > max_points:
            indices = [round(value) for value in
                       [i * (len(trace) - 1) / (max_points - 1)
                        for i in range(max_points)]]
            trace = [trace[i] for i in sorted(set(indices))]
        coordinates = [item[0] for item in trace]
        if not weighted:
            add_ray_curve(f"photon_path_{index}", coordinates, materials[0], 0.13)
            continue
        start = 0
        current_bin = min(len(colors) - 1, int(trace[0][1] * len(colors)))
        for segment in range(1, len(trace)):
            next_bin = min(len(colors) - 1, int(trace[segment][1] * len(colors)))
            if next_bin != current_bin:
                add_ray_curve(f"photon_path_{index}_{start}",
                              coordinates[start:segment + 1], materials[current_bin], 0.16)
                start = segment
                current_bin = next_bin
        add_ray_curve(f"photon_path_{index}_{start}",
                      coordinates[start:], materials[current_bin], 0.16)

    # Single-event specular detector rays are rendered as small octahedra.
    point_vertices = []
    point_faces = []
    radius = 0.75
    point_material = materials[-1] if weighted else materials[0]
    for trace in traces:
        if len(trace) != 1:
            continue
        x, y, z = trace[0][0]
        base = len(point_vertices)
        point_vertices.extend([(x + radius, y, z), (x - radius, y, z),
                                (x, y + radius, z), (x, y - radius, z),
                                (x, y, z + radius), (x, y, z - radius)])
        point_faces.extend([(base + 0, base + 2, base + 4),
                            (base + 2, base + 1, base + 4),
                            (base + 1, base + 3, base + 4),
                            (base + 3, base + 0, base + 4),
                            (base + 2, base + 0, base + 5),
                            (base + 1, base + 2, base + 5),
                            (base + 3, base + 1, base + 5),
                            (base + 0, base + 3, base + 5)])
    if point_vertices:
        mesh = bpy.data.meshes.new("detector_acceptance_points_mesh")
        mesh.from_pydata(point_vertices, [], point_faces)
        mesh.update()
        points = bpy.data.objects.new("detector_acceptance_points", mesh)
        bpy.context.collection.objects.link(points)
        mesh.materials.append(point_material)


def make_ring_light(z=-40.0, major_radius=14.0, tube_radius=1.15):
    """Create a visible annular source around the detector axis."""
    major_steps = 96
    tube_steps = 16
    vertices = []
    faces = []
    for major in range(major_steps):
        u = 2.0 * math.pi * major / major_steps
        for tube in range(tube_steps):
            v = 2.0 * math.pi * tube / tube_steps
            radial = major_radius + tube_radius * math.cos(v)
            vertices.append((radial * math.cos(u), radial * math.sin(u),
                             z + tube_radius * math.sin(v)))
    for major in range(major_steps):
        next_major = (major + 1) % major_steps
        for tube in range(tube_steps):
            next_tube = (tube + 1) % tube_steps
            a = major * tube_steps + tube
            b = next_major * tube_steps + tube
            c = next_major * tube_steps + next_tube
            d = major * tube_steps + next_tube
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new("annular_source_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    ring = bpy.data.objects.new("annular_source_light", mesh)
    bpy.context.collection.objects.link(ring)

    material = bpy.data.materials.new("NIR annular source")
    material.diffuse_color = (1.0, 0.08, 0.005, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (1.0, 0.025, 0.002, 1.0)
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.01, 0.001, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 8.0
    bsdf.inputs["Roughness"].default_value = 0.24
    mesh.materials.append(material)
    return ring


def import_light_model(path, scale=40.0, z=-35.5):
    """Append the authored lightmodel.blend meshes without idealizing them."""
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = [name for name in source.objects]
    imported = []
    for obj in target.objects:
        if obj is None or obj.type != "MESH":
            continue
        obj.name = f"lightmodel_{obj.name}"
        bpy.context.collection.objects.link(obj)
        obj.location = (0.0, 0.0, z)
        # Preserve the authored object scale and apply the scene-unit scale
        # on top of it; replacing it would distort the imported model.
        obj.scale = tuple(value * scale for value in obj.scale)
        imported.append(obj)
    return imported


def render(blend_path, ply_path, output, detector_scale, detector_z, camera_z, target_z,
           rays_path, apple_opacity, light_model, light_scale, light_z,
           ring_z, ring_radius, ring_tube, weighted_rays, max_ray_traces,
           max_ray_points):
    # The blend file is opened as the startup scene, preserving its detector
    # objects and their original Blender materials.
    apple = make_apple(ply_path, apple_opacity)
    make_ray_visualization(rays_path, weighted_rays, max_ray_traces, max_ray_points)
    if light_model:
        import_light_model(light_model, light_scale, light_z)
    else:
        make_ring_light(ring_z, ring_radius, ring_tube)

    detector_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"
                        and obj.name in {"柱体", "立方体"}]
    for obj in detector_objects:
        obj.scale = (detector_scale, detector_scale, detector_scale)
        obj.location = (0.0, 0.0, detector_z)

    # Add a neutral floor only for grounding the placement.
    floor_mesh = bpy.data.meshes.new("demo_ground_mesh")
    floor_mesh.from_pydata([(-90, -90, detector_z - 1.5),
                            (90, -90, detector_z - 1.5),
                            (90, 90, detector_z - 1.5),
                            (-90, 90, detector_z - 1.5)], [], [(0, 1, 2, 3)])
    floor_mesh.update()
    floor = bpy.data.objects.new("demo_ground", floor_mesh)
    bpy.context.collection.objects.link(floor)
    floor.name = "demo_ground"
    floor_material = bpy.data.materials.new("Ground")
    floor_material.diffuse_color = (0.025, 0.03, 0.04, 1.0)
    floor_material.use_nodes = True
    floor_bsdf = next(node for node in floor_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    floor_bsdf.inputs["Base Color"].default_value = (0.025, 0.03, 0.04, 1.0)
    floor_bsdf.inputs["Roughness"].default_value = 0.7
    floor.data.materials.append(floor_material)

    camera_data = bpy.data.cameras.new("demo_camera")
    camera = bpy.data.objects.new("demo_camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (88.0, -112.0, camera_z)
    camera.data.lens = 56.0
    look_at(camera, (0.0, 0.0, target_z))
    bpy.context.scene.camera = camera

    add_area_light("demo_key", (35.0, -45.0, 85.0), 900.0, 55.0, (0.0, 0.0, -8.0))
    add_area_light("demo_fill", (-55.0, 20.0, 35.0), 500.0, 45.0, (0.0, 0.0, -10.0))

    scene = bpy.context.scene
    # Blender 5.2 in this environment exposes the Eevee engine as
    # BLENDER_EEVEE; newer builds may call it BLENDER_EEVEE_NEXT.
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in {
        item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    } else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.render.film_transparent = False
    scene.world.color = (0.008, 0.012, 0.02)
    scene.render.image_settings.color_mode = "RGBA"
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(output).with_suffix(".blend")))
    bpy.ops.render.render(write_still=True)
    print("Rendered", output)
    print("Saved scene", Path(output).with_suffix(".blend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--ply", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detector-scale", type=float, default=20.0)
    parser.add_argument("--detector-z", type=float, default=-42.0)
    parser.add_argument("--camera-z", type=float, default=72.0)
    parser.add_argument("--target-z", type=float, default=-8.0)
    parser.add_argument("--rays", type=Path, default=None,
                        help="detector_rays.csv to overlay in the Blender scene")
    parser.add_argument("--apple-opacity", type=float, default=1.0)
    parser.add_argument("--light-model", type=Path, default=None,
                        help="authored Blender light model to append")
    parser.add_argument("--light-scale", type=float, default=40.0)
    parser.add_argument("--light-z", type=float, default=-35.5)
    parser.add_argument("--weighted-rays", action="store_true",
                        help="color Blender path segments by photon weight")
    parser.add_argument("--max-ray-traces", type=int, default=0)
    parser.add_argument("--max-ray-points", type=int, default=600)
    parser.add_argument("--ring-z", type=float, default=-40.0)
    parser.add_argument("--ring-radius", type=float, default=14.0)
    parser.add_argument("--ring-tube", type=float, default=1.15)
    # Blender keeps script arguments after its own ``--`` separator in
    # sys.argv.  Parse only that tail so Blender's startup arguments do not
    # confuse argparse across Blender versions.
    argv = __import__("sys").argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    args = parser.parse_args(argv)
    render(args.blend, args.ply, args.output, args.detector_scale, args.detector_z,
           args.camera_z, args.target_z, args.rays, args.apple_opacity,
           args.light_model, args.light_scale, args.light_z,
           args.ring_z, args.ring_radius, args.ring_tube,
           args.weighted_rays, args.max_ray_traces, args.max_ray_points)


if __name__ == "__main__":
    main()
