# Gear for the 第十三關 (地下實驗室) zombies of 死城突圍 (see CONTEXT.md).
#
#   blender -b -P tools/blender/lab_zombies.py -- assets/models/labzombie.glb [preview.png]
#
# Each piece is modelled in the frame of the joint it hangs from (game coordinates, +Y up, +Z the way it faces):
#   head frame - skull centre y 0.13, top y ~0.27, face toward +z
#   body frame - feet on the origin; chest ~1.35, front of the torso z ~0.15 (the 屍王 body used by 零號病人: ~0.2), back z ~-0.15
#   arm frame  - the shoulder pivot; the upper arm hangs to y -0.31 (elbow), drawn on the right arm (+x outward)
#   leg frame  - the hip pivot; the thigh hangs to y -0.45 (knee);  knee frame - the shin hangs to the ground at y ~-0.5
#   hand frame - the wrist, fingers toward -y
#   dog body   - the 軍犬 body: back at y ~0.8 from z -0.35 to 0.35, neck at z ~0.4;  dog head - eyes at (±0.045, 0.035, 0.085)
# Untextured: exported without UVs.
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "labzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(31)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "hazmat": ((0.8, 0.6, 0.06), 0.6, 0.0, 0), "visor": ((0.03, 0.05, 0.05), 0.05, 0.6, 0), "rubber": ((0.03, 0.03, 0.03), 0.8, 0.0, 0),
    "tank_metal": ((0.5, 0.52, 0.55), 0.35, 0.9, 0), "stripe_green": ((0.1, 0.5, 0.15), 0.5, 0.0, 0),
    "exo_steel": ((0.22, 0.24, 0.26), 0.35, 0.9, 0), "exo_dark": ((0.07, 0.07, 0.08), 0.45, 0.7, 0), "exo_orange": ((0.75, 0.3, 0.04), 0.5, 0.2, 0),
    "core_glow": ((0.2, 0.7, 1.0), 0.2, 0.0, 4.0), "lens_green": ((0.2, 1.0, 0.3), 0.2, 0.0, 3.0), "led_red": ((1.0, 0.1, 0.05), 0.3, 0.0, 4.0),
    "leather": ((0.13, 0.08, 0.05), 0.75, 0.0, 0), "buckle": ((0.6, 0.6, 0.62), 0.3, 1.0, 0), "iv_tube": ((0.75, 0.85, 0.8), 0.15, 0.0, 0),
    "bone": ((0.78, 0.72, 0.6), 0.6, 0.0, 0), "pz_flesh": ((0.35, 0.06, 0.08), 0.45, 0.0, 0), "pz_vein": ((0.6, 0.15, 0.7), 0.4, 0.0, 1.2),
}
MAT = {}
for n, (c, r, mt, em) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if em:
        b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = em
    MAT[n] = m


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def settle(ob, mat):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=12, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=14):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def tube(pts, r, mat, radii=None, res=4):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def ring(cy, rx, rz, r, mat, n=20):
    pts = [(math.sin(k / n * math.tau) * rx, cy, math.cos(k / n * math.tau) * rz) for k in range(n + 1)]
    return tube(pts, r, mat, res=2)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== 防護衣研究員: hood (head frame) and air tank (body frame)
join([ball((0, 0.15, -0.005), (0.155, 0.2, 0.165), "hazmat", 20), ball((0, 0.16, 0.115), (0.115, 0.085, 0.06), "visor", 18),
      *[cyl((s * 0.065, 0.05, 0.13), (s * 0.085, 0.03, 0.2), 0.035, "rubber", 12) for s in (-1, 1)],
      ring(-0.04, 0.16, 0.15, 0.025, "rubber")], "hazmat_hood")
join([cyl((0, 1.05, -0.24), (0, 1.55, -0.24), 0.085, "tank_metal", 16), ball((0, 1.55, -0.24), (0.085, 0.05, 0.085), "tank_metal", 12),
      cyl((0, 1.3, -0.24), (0, 1.36, -0.24), 0.088, "stripe_green", 16), cyl((0, 1.6, -0.24), (0, 1.66, -0.24), 0.02, "rubber", 8),
      tube([(0, 1.64, -0.24), (0.12, 1.72, -0.12), (0.14, 1.66, 0.08), (0.08, 1.74, 0.17)], 0.014, "rubber"),
      *[tube([(s * 0.13, 1.5, -0.16), (s * 0.16, 1.58, 0.0), (s * 0.14, 1.45, 0.16), (s * 0.12, 1.15, 0.16)], 0.016, "rubber") for s in (-1, 1)]], "hazmat_tank")

# ===================================================================== 外骨骼殭屍: frame (body), power core (body, back), arm and leg struts
parts = [box((0, 1.33, -0.21), (0.07, 0.7, 0.05), "exo_steel"), ring(0.98, 0.23, 0.18, 0.028, "exo_dark"),
         box((0, 1.6, -0.19), (0.66, 0.06, 0.06), "exo_steel"), ring(1.7, 0.12, 0.11, 0.02, "exo_steel")]
for k in range(5):  # vertebrae clamps
    parts.append(box((0, 1.05 + k * 0.13, -0.235), (0.14, 0.04, 0.05), "exo_dark"))
for s in (-1, 1):  # straps over the shoulders and hydraulic lines
    parts.append(tube([(s * 0.2, 1.6, -0.18), (s * 0.24, 1.66, 0.0), (s * 0.18, 1.5, 0.17), (s * 0.15, 1.25, 0.16)], 0.02, "exo_dark"))
    parts.append(tube([(s * 0.05, 1.15, -0.25), (s * 0.18, 1.0, -0.2), (s * 0.2, 0.96, -0.05)], 0.012, "exo_orange"))
join(parts, "exo_frame")
join([box((0, 1.3, -0.27), (0.24, 0.32, 0.09), "exo_steel"), box((0, 1.3, -0.315), (0.13, 0.22, 0.02), "core_glow"),
      *[box((s * 0.1, 1.3, -0.3), (0.025, 0.3, 0.03), "exo_orange") for s in (-1, 1)]], "exo_core")
join([cyl((0.075, -0.02, 0), (0.075, -0.27, 0), 0.022, "exo_steel", 10), cyl((0.075, -0.06, 0.03), (0.075, -0.22, 0.03), 0.012, "tank_metal", 8),
      cyl((0.06, -0.31, 0), (0.1, -0.31, 0), 0.045, "exo_dark", 14), cyl((0.075, -0.33, 0), (0.075, -0.55, 0), 0.02, "exo_steel", 10)], "exo_arm")
join([cyl((0.1, -0.02, 0), (0.1, -0.42, 0), 0.025, "exo_steel", 10), cyl((0.1, -0.08, 0.035), (0.1, -0.36, 0.035), 0.013, "tank_metal", 8),
      cyl((0.085, -0.45, 0), (0.13, -0.45, 0), 0.05, "exo_dark", 14), box((0.1, -0.2, 0), (0.03, 0.06, 0.12), "exo_orange")], "exo_thigh")
join([cyl((0.1, -0.03, 0), (0.1, -0.42, 0), 0.022, "exo_steel", 10), box((0.0, -0.47, 0.03), (0.14, 0.03, 0.26), "exo_dark"),
      box((0.1, -0.44, 0.0), (0.03, 0.06, 0.08), "exo_steel")], "exo_shin")

# ===================================================================== 實驗獵犬: implants along the back and a collar (dog body), skull plate and lens (dog head)
parts = [ring(0.7, 0.12, 0.1, 0.018, "exo_dark")]
parts[0].location = B(0, 0, 0.38); activate(parts[0]); bpy.ops.object.transform_apply(location=True)
parts += [box((0, 0.6, 0.47), (0.05, 0.06, 0.012), "buckle"), ball((0.03, 0.6, 0.475), 0.01, "led_red", 8)]
for s in (-1, 1):
    parts.append(tube([(s * 0.04, 0.82, -0.32), (s * 0.05, 0.86, 0.0), (s * 0.04, 0.82, 0.3)], 0.012, "iv_tube"))
for k in range(5):
    parts.append(box((0, 0.83, -0.25 + k * 0.13), (0.12, 0.04, 0.05), "exo_steel"))
join(parts, "labdog_gear")
join([ball((0, 0.085, -0.01), (0.075, 0.025, 0.09), "exo_steel", 14), *[ball((s * 0.05, 0.1, k * 0.05 - 0.04), 0.008, "buckle", 6) for s in (-1, 1) for k in range(3)],
      cyl((0.045, 0.035, 0.085), (0.045, 0.035, 0.105), 0.022, "exo_dark", 12), cyl((0.045, 0.035, 0.105), (0.045, 0.035, 0.11), 0.016, "lens_green", 12),
      tube([(-0.02, 0.1, -0.08), (-0.03, 0.08, -0.16), (-0.02, 0.0, -0.2)], 0.006, "led_red")], "labdog_head")

# ===================================================================== 零號病人: restraints and lines (屍王 body frame), cuffs (hand), spikes and tendrils for the later phases
parts = []
for s in (-1, 1):  # crossed restraint straps with buckles
    parts.append(tube([(s * 0.3, 1.62, -0.1), (s * 0.18, 1.5, 0.22), (-s * 0.12, 1.22, 0.23), (-s * 0.27, 1.05, 0.12)], 0.03, "leather", [1, 1.2, 1.2, 1]))
    parts.append(box((s * 0.03, 1.36, 0.25), (0.07, 0.05, 0.02), "buckle"))
for k in range(4):  # electrode pads and their wires
    x, y = (-0.12, 0.12, -0.08, 0.1)[k], (1.45, 1.48, 1.2, 1.15)[k]
    parts += [cyl((x, y, 0.21), (x, y, 0.23), 0.03, "iv_tube", 12), tube([(x, y, 0.23), (x * 1.6, y - 0.25, 0.2), (x * 1.3, y - 0.55, 0.12)], 0.006, "pz_vein")]
parts.append(ring(1.69, 0.14, 0.13, 0.03, "buckle"))                                           # a burst neck brace
parts.append(tube([(0.3, 1.5, 0.05), (0.42, 1.3, 0.1), (0.5, 0.95, 0.15), (0.45, 0.6, 0.2)], 0.008, "iv_tube"))  # a torn IV line
parts.append(box((0.45, 0.58, 0.2), (0.09, 0.14, 0.03), "iv_tube"))
join(parts, "pz_gear")
parts = [ring(-0.03, 0.065, 0.06, 0.016, "buckle")]
for k in range(5):  # a length of broken chain
    y = -0.08 - k * 0.07
    parts.append(ring(y, 0.02 if k % 2 else 0.006, 0.006 if k % 2 else 0.02, 0.006, "buckle", 10))
join(parts, "pz_cuff")
parts = []
for k in range(7):
    y = 1.05 + k * 0.1
    parts.append(cyl((0, y, -0.22), (random.uniform(-0.05, 0.05), y + 0.12, -0.42 - k * 0.01), 0.04, "bone", 8, 0.0))
for s in (-1, 1):
    for k in range(3):
        parts.append(cyl((s * (0.22 + k * 0.05), 1.62, -0.05), (s * (0.32 + k * 0.08), 1.85 + k * 0.05, -0.12), 0.035, "bone", 8, 0.0))
join(parts, "pz_spikes")
parts = []
for k, (sx, up) in enumerate(((-1, 0.2), (1, 0.15), (-0.5, 0.45), (0.6, 0.5))):
    pts = [(sx * 0.1, 1.45, -0.2), (sx * 0.35, 1.6 + up, -0.5), (sx * 0.55, 1.95 + up, -0.7), (sx * 0.6, 2.35 + up, -0.6)]
    parts.append(tube(pts, 0.07, "pz_flesh", [1, 0.8, 0.5, 0.15]))
    for j in range(3):
        p = Vector(pts[j]).lerp(Vector(pts[j + 1]), 0.5)
        parts.append(ball(tuple(p + Vector((0, 0.04, 0.03))), 0.02, "pz_vein", 8))
join(parts, "pz_tendrils")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"hazmat_hood": (-1.6, 1.5), "hazmat_tank": (-1.6, 0), "exo_frame": (-0.5, 0), "exo_core": (-0.5, 0), "exo_arm": (0.2, 1.3),
              "exo_thigh": (0.35, 1.0), "exo_shin": (0.35, 0.45), "labdog_gear": (1.0, 0.2), "labdog_head": (1.0, 1.2),
              "pz_gear": (1.8, 0), "pz_spikes": (1.8, 0), "pz_tendrils": (1.8, 0), "pz_cuff": (2.5, 1.2)}
    for ob in PARTS:
        x, y = layout.get(ob.name, (0, 0)); ob.location = B(x, y, 0); ob.rotation_euler = (0, 0, math.radians(150))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 5.0
    cam.location = B(0.4, 1.2, 8); cam.rotation_euler = (B(0.4, 1.2, 0) - B(0.4, 1.2, 8)).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((3, 5, 6), 1500), ((-4, 2, 4), 600)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 5; l.location = B(*loc); l.rotation_euler = (B(0.4, 1, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
