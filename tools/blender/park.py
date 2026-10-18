# The 廢棄遊樂園 of 死城突圍's level 16 (see CONTEXT.md, .scratch/level-16/spec.md).
#
#   blender -b -P tools/blender/park.py -- assets/models/park.glb [preview.png]
#
# Game coordinates (+Y up, front toward +Z); each piece stands on its own origin and the game lays them out.
# Untextured, so exported without UVs.
#   park_gate        the FUNLAND entrance arch (14 m wide, the passage along Z)
#   ferris_frame     the A-frame legs and hub of the Ferris wheel (hub at y 18, the wheel turns in the XY plane)
#   ferris_wheel     the rim and spokes (origin on the hub, spins about Z);  ferris_gondola  one car (origin at its hanging point)
#   carousel_base    platform, centre pole and canopy;  carousel_ride  the horses and the turning ring (origin on the axis)
#   coaster          a stretch of roller-coaster track on its trestles (60 m along Z)
#   big_top          the circus tent (radius 14, entrance toward +Z)
#   stall, food_cart, lamp_post, light_string (10 m of bulbs between two posts, along X), fence (6 m along X),
#   bench, trash_bin, balloons, ticket_booth, circus_cannon
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "park.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(16)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, emission)
    "red": ((0.7, 0.06, 0.05), 0.6, 0.1, 0), "white": ((0.85, 0.84, 0.8), 0.6, 0.1, 0), "yellow": ((0.85, 0.65, 0.08), 0.5, 0.2, 0),
    "blue": ((0.08, 0.2, 0.6), 0.5, 0.1, 0), "green": ((0.08, 0.45, 0.2), 0.5, 0.1, 0), "purple": ((0.35, 0.08, 0.45), 0.5, 0.1, 0),
    "gold": ((0.75, 0.55, 0.18), 0.3, 0.9, 0), "steel": ((0.45, 0.47, 0.5), 0.4, 0.85, 0), "steel_dark": ((0.12, 0.13, 0.14), 0.5, 0.8, 0),
    "rust": ((0.35, 0.15, 0.07), 0.7, 0.5, 0), "wood": ((0.35, 0.22, 0.12), 0.8, 0.0, 0), "iron": ((0.05, 0.05, 0.05), 0.5, 0.7, 0),
    "bulb": ((1.0, 0.85, 0.5), 0.3, 0.0, 6.0), "bulb_red": ((1.0, 0.2, 0.15), 0.3, 0.0, 5.0), "bulb_blue": ((0.3, 0.5, 1.0), 0.3, 0.0, 5.0),
    "neon_pink": ((1.0, 0.2, 0.6), 0.3, 0.0, 4.0), "horse": ((0.88, 0.86, 0.82), 0.4, 0.1, 0), "glass": ((0.2, 0.3, 0.35), 0.1, 0.5, 0),
    "popcorn": ((0.95, 0.88, 0.6), 0.9, 0.0, 0),
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


def settle(ob, mat, smooth=False):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=10, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat, True)


def ball(c, r, mat, segs=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(5, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat, True)


def tor(c, R, r, mat, axis="z", segs=32):
    rot = {"z": (math.pi / 2, 0, 0), "x": (0, math.pi / 2, 0), "y": (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=segs, minor_segments=6, location=B(*c), rotation=rot)
    return settle(bpy.context.object, mat, True)


def tube(pts, r, mat, res=6):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat, True)


def text(s, c, size, mat, depth=0.08):
    bpy.ops.object.text_add(location=B(*c), rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.object; ob.data.body = s; ob.data.size = size; ob.data.extrude = depth
    ob.data.align_x = "CENTER"; ob.data.align_y = "CENTER"
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== entrance arch
parts = []
for s in (-1, 1):
    parts += [cyl((s * 7, 0, 0), (s * 7, 8, 0), 0.6, "red", 14), cyl((s * 7, 8, 0), (s * 7, 9.5, 0), 0.9, "gold", 14, 0.2), ball((s * 7, 9.8, 0), 0.4, "bulb", 10)]
parts.append(tube([(-7, 7.5, 0), (-3.5, 10.5, 0), (3.5, 10.5, 0), (7, 7.5, 0)], 0.35, "yellow", 10))
parts.append(box((0, 8.9, 0.1), (9, 1.8, 0.3), "purple"))
parts.append(text("FUNLAND", (0, 8.9, 0.32), 1.25, "neon_pink"))
for k in range(16):  # bulbs along the arch
    t = k / 15; x = -7 + 14 * t; y = 7.5 + math.sin(t * math.pi) * 3.0
    parts.append(ball((x, y + 0.4, 0.3), 0.14, "bulb" if k % 2 else "bulb_red", 6))
join(parts, "park_gate")

# ===================================================================== Ferris wheel: frame, wheel and one gondola
HUB = 18.0; R = 15.0
parts = []
for z in (-1.6, 1.6):
    for s in (-1, 1):
        parts.append(cyl((s * 9, 0, z * 2.5), (0, HUB, z), 0.4, "steel", 10))
parts += [cyl((0, HUB, -2.2), (0, HUB, 2.2), 0.6, "steel_dark", 14), box((0, 0.3, 0), (22, 0.6, 8), "steel_dark"), box((0, 1.2, 4.2), (6, 2.4, 3), "purple")]
join(parts, "ferris_frame")
parts = [tor((0, 0, -0.9), R, 0.18, "white", "z", 48), tor((0, 0, 0.9), R, 0.18, "white", "z", 48)]
for k in range(12):
    a = k / 12 * math.tau
    for z in (-0.9, 0.9):
        parts.append(cyl((0, 0, z), (math.sin(a) * R, math.cos(a) * R, z), 0.07, "white", 6))
    parts.append(cyl((math.sin(a) * R, math.cos(a) * R, -1.1), (math.sin(a) * R, math.cos(a) * R, 1.1), 0.09, "steel", 6))
for k in range(36):
    a = k / 36 * math.tau
    parts.append(ball((math.sin(a) * (R + 0.25), math.cos(a) * (R + 0.25), 0.95), 0.12, ("bulb", "bulb_red", "bulb_blue")[k % 3], 6))
join(parts, "ferris_wheel")
join([cyl((0, 0, -0.9), (0, -0.8, -0.9), 0.05, "steel", 6), cyl((0, 0, 0.9), (0, -0.8, 0.9), 0.05, "steel", 6), box((0, -1.5, 0), (2.0, 1.4, 1.8), "red"),
      box((0, -0.75, 0), (2.2, 0.12, 2.0), "yellow"), box((0, -1.4, 0.91), (1.6, 0.6, 0.04), "glass")], "ferris_gondola")

# ===================================================================== carousel: base + turning ride
parts = [cyl((0, 0, 0), (0, 0.6, 0), 9, "white", 32), cyl((0, 0.6, 0), (0, 0.7, 0), 9.2, "gold", 32), cyl((0, 0.7, 0), (0, 7, 0), 0.9, "gold", 16)]
bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=10, radius2=0.5, depth=3, location=B(0, 7.8, 0)); canopy = bpy.context.object; parts.append(settle(canopy, "red"))
for k in range(16):  # stripes and bulbs round the canopy edge
    a = k / 16 * math.tau
    parts.append(ball((math.sin(a) * 9.9, 6.35, math.cos(a) * 9.9), 0.15, "bulb", 6))
    if k % 2: parts.append(box((math.sin(a) * 9.6, 6.6, math.cos(a) * 9.6), (3.8, 0.6, 0.06), "white", (0, 0, -a)))
parts.append(ball((0, 9.6, 0), 0.5, "gold", 12))
join(parts, "carousel_base")
parts = []
for k in range(12):
    a = k / 12 * math.tau; r = 6.2 if k % 2 else 4.4; x, z = math.sin(a) * r, math.cos(a) * r
    y = 1.6 + (k % 3) * 0.2
    hx, hz = math.cos(a), -math.sin(a)  # horses face along the turning direction
    parts += [cyl((x, 0.7, z), (x, 6.3, z), 0.05, "gold", 6),
              ball((x, y, z), (0.35, 0.35, 0.8), "horse", 10) if False else box((x, y, z), (0.35, 0.45, 1.2), "horse", (0, 0, -a + math.pi / 2)),
              box((x + hx * 0.6, y + 0.45, z + hz * 0.6), (0.25, 0.6, 0.3), "horse", (0, 0, -a + math.pi / 2)),
              box((x, y + 0.3, z), (0.4, 0.08, 0.5), ("red", "blue", "purple")[k % 3], (0, 0, -a + math.pi / 2))]
    for s in (-1, 1):
        parts.append(cyl((x + hz * 0.15 * s, y - 0.2, z - hx * 0.15 * s), (x + hz * 0.15 * s + hx * 0.4, y - 0.9, z - hx * 0.15 * s + hz * 0.4), 0.06, "horse", 6))
parts.append(cyl((0, 5.9, 0), (0, 6.3, 0), 8.6, "gold", 32))
join(parts, "carousel_ride")

# ===================================================================== roller-coaster stretch (60 m along Z): a hill and a loop on trestles
pts = [(0, 6, -30), (0, 8, -22), (0, 18, -12), (0, 9, -2), (0, 6, 6), (0, 6, 12), (0, 6, 30)]
parts = []
for s in (-0.6, 0.6):
    parts.append(tube([(x + s, y, z) for x, y, z in pts], 0.12, "red", 12))
loop = [(0.6 * math.sin(t * math.pi * 2) * 0, 6 + 6 * (1 - math.cos(t * math.tau)), 18 + 6 * math.sin(t * math.tau)) for t in [k / 16 for k in range(17)]]
for s in (-0.6, 0.6):
    parts.append(tube([(s + k * 0.08, y, z) for k, (x, y, z) in enumerate(loop)], 0.12, "red", 16))
for x, y, z in pts:
    parts.append(cyl((0, 0, z), (0, y - 0.2, z), 0.25, "steel", 8))
    for s in (-1, 1):
        parts.append(cyl((s * 1.6, 0, z), (0, y * 0.6, z), 0.12, "steel", 6))
for k in range(30):  # sleepers
    t = k / 29; z = -30 + 60 * t
    y = min((p[1] for p in pts), key=lambda v: v) if False else None
parts.append(box((0, 0.2, 0), (6, 0.4, 62), "steel_dark"))
join(parts, "coaster")

# ===================================================================== circus big top (radius 14, ~14 m high, entrance toward +Z)
parts = []
N = 16
for k in range(N):  # striped walls
    a0, a1 = k / N * math.tau, (k + 1) / N * math.tau
    vs = [B(math.sin(a0) * 14, 0, math.cos(a0) * 14), B(math.sin(a1) * 14, 0, math.cos(a1) * 14), B(math.sin(a1) * 14, 5, math.cos(a1) * 14), B(math.sin(a0) * 14, 5, math.cos(a0) * 14),
          B(0, 14, 0)]
    if abs(math.atan2(math.sin((a0 + a1) / 2), math.cos((a0 + a1) / 2))) > 0.3:  # leave the entrance open
        me = bpy.data.meshes.new("w"); me.from_pydata(vs[:4], [], [(0, 1, 2, 3)]); ob = bpy.data.objects.new("w", me); scene.collection.objects.link(ob)
        so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.1; activate(ob); bpy.ops.object.modifier_apply(modifier="s"); parts.append(settle(ob, "red" if k % 2 else "white"))
    me = bpy.data.meshes.new("r"); me.from_pydata([vs[3], vs[2], vs[4]], [], [(0, 1, 2)]); ob = bpy.data.objects.new("r", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.1; activate(ob); bpy.ops.object.modifier_apply(modifier="s"); parts.append(settle(ob, "white" if k % 2 else "red"))
parts += [cyl((0, 0, 0), (0, 16, 0), 0.25, "gold", 8), *[box((0.6, 15.2 + k * 0.01, 0), (1.2, 0.7, 0.04), ("red", "yellow")[k], (0, 0, 0)) for k in range(1)]]
for s in (-1, 1):  # entrance poles and a sign
    parts += [cyl((s * 2.6, 0, 14.2), (s * 2.6, 6, 14.2), 0.18, "gold", 8)]
parts += [box((0, 6.4, 14.3), (7, 1.4, 0.2), "purple"), text("CIRCUS", (0, 6.4, 14.45), 0.9, "bulb")]
join(parts, "big_top")

# ===================================================================== small pieces
parts = [box((0, 0.55, 0), (4, 1.1, 1.4), "wood"), box((0, 1.15, 0.2), (4.2, 0.08, 1.6), "yellow")]
for x in (-1.9, 1.9):
    parts.append(cyl((x, 1.1, -0.6), (x, 3.0, -0.6), 0.07, "wood", 6)); parts.append(cyl((x, 1.1, 0.7), (x, 3.0, 0.7), 0.07, "wood", 6))
for k in range(6):  # striped awning
    parts.append(box((-1.75 + k * 0.7, 3.1, 0.1), (0.7, 0.08, 1.8), "red" if k % 2 else "white", (math.radians(-12), 0, 0)))
for k in range(5):  # prizes on the back shelf
    parts.append(ball((-1.6 + k * 0.8, 1.5, -0.5), 0.22, ("purple", "blue", "green", "yellow", "red")[k], 8))
parts.append(box((0, 2.2, -0.62), (4, 1.6, 0.06), "purple"))
join(parts, "stall")
join([box((0, 0.9, 0), (1.4, 1.0, 0.9), "red"), box((0, 1.9, 0), (1.2, 1.0, 0.8), "glass"), box((0, 1.6, 0), (1.15, 0.5, 0.75), "popcorn"),
      box((0, 2.5, 0), (1.5, 0.15, 1.0), "yellow"), *[cyl((s * 0.6, 0.4, 0), (s * 0.7, 0.4, 0), 0.38, "steel_dark", 12) for s in (-1, 1)]], "food_cart")
join([cyl((0, 0, 0), (0, 4.6, 0), 0.08, "iron", 8), cyl((0, 0, 0), (0, 0.5, 0), 0.2, "iron", 8, 0.1), tube([(0, 4.4, 0), (0.3, 4.9, 0), (0.6, 4.7, 0)], 0.04, "iron"),
      ball((0.6, 4.45, 0), 0.22, "bulb", 10), ball((0, 4.75, 0), 0.12, "gold", 8)], "lamp_post")
parts = [tube([(-5, 4.2, 0), (-2.5, 3.5, 0), (0, 3.3, 0), (2.5, 3.5, 0), (5, 4.2, 0)], 0.015, "iron")]
for k in range(11):
    x = -5 + k; y = 4.2 - 0.9 * (1 - (x / 5) ** 2) - 0.12
    parts.append(ball((x, y, 0), 0.08, ("bulb", "bulb_red", "bulb_blue")[k % 3], 6))
join(parts, "light_string")
parts = [box((0, 0.1, 0), (6, 0.08, 0.08), "iron"), box((0, 1.6, 0), (6, 0.08, 0.08), "iron")]
for k in range(13):
    x = -3 + k * 0.5; parts += [cyl((x, 0, 0), (x, 1.8, 0), 0.025, "iron", 5), cyl((x, 1.8, 0), (x, 1.95, 0), 0.04, "iron", 4, 0.0)]
for x in (-3, 3):
    parts.append(box((x, 1.0, 0), (0.15, 2.0, 0.15), "iron"))
join(parts, "fence")
join([box((0, 0.45, 0), (1.8, 0.08, 0.5), "wood"), box((0, 0.8, -0.22), (1.8, 0.5, 0.06), "wood"), *[box((s * 0.8, 0.22, 0), (0.08, 0.45, 0.5), "iron") for s in (-1, 1)]], "bench")
join([cyl((0, 0, 0), (0, 0.95, 0), 0.32, "green", 12), cyl((0, 0.95, 0), (0, 1.05, 0), 0.34, "iron", 12)], "trash_bin")
parts = [cyl((0, 0, 0), (0, 1.0, 0), 0.04, "iron", 6)]
for k in range(7):
    a = random.uniform(0, math.tau); h = random.uniform(2.2, 3.2); x, z = math.sin(a) * 0.35, math.cos(a) * 0.35
    parts += [tube([(0, 1.0, 0), (x * 0.5, h * 0.7, z * 0.5), (x, h - 0.3, z)], 0.006, "white"), ball((x, h, z), (0.24, 0.3, 0.24), ("red", "blue", "yellow", "purple", "green")[k % 5], 10)]
join(parts, "balloons")
join([box((0, 1.4, 0), (2.4, 2.8, 2.0), "purple"), box((0, 1.5, 1.01), (1.4, 0.8, 0.04), "glass"), box((0, 3.0, 0), (2.8, 0.25, 2.4), "yellow"),
      text("TICKETS", (0, 2.4, 1.05), 0.32, "bulb", 0.03)], "ticket_booth")
join([cyl((0, 1.2, -1.5), (0, 3.2, 2.2), 0.65, "red", 16, 0.5), cyl((0, 3.2, 2.2), (0, 3.35, 2.45), 0.62, "gold", 16), box((0, 0.6, -0.8), (1.8, 1.2, 2.4), "blue"),
      *[cyl((s * 1.0, 0.6, z), (s * 1.15, 0.6, z), 0.55, "gold", 14) for s in (-1, 1) for z in (-1.4, 0.2)]], "circus_cannon")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"park_gate": (0, 0, 22), "ferris_frame": (-26, 0, -18), "ferris_wheel": (-26, 18, -18), "carousel_base": (14, 0, 2), "carousel_ride": (14, 0, 2),
             "coaster": (40, 0, -8), "big_top": (0, 0, -40), "stall": (-8, 0, 8), "food_cart": (-3, 0, 12), "lamp_post": (4, 0, 14), "bench": (6, 0, 16),
             "balloons": (-5, 0, 16), "ticket_booth": (10, 0, 22), "circus_cannon": (12, 0, -26), "fence": (0, 0, 26), "trash_bin": (2, 0, 16),
             "light_string": (0, 0, 18)}
    for ob in PARTS:
        ob.location = B(*place.get(ob.name, (0, -50, 0)))
    bpy.ops.mesh.primitive_plane_add(size=300, location=(0, 0, 0)); gp = bpy.context.object; gp.data.materials.append(MAT["steel_dark"])
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.03, 0.08, 1)
    moon = bpy.data.objects.new("m", bpy.data.lights.new("m", "SUN")); scene.collection.objects.link(moon)
    moon.data.energy = 1.2; moon.rotation_euler = (math.radians(50), 0, math.radians(30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 20; eye, tgt = B(4, 10, 46), B(0, 6, -10)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
