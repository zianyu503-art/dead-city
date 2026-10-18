# The 第十六關 (廢棄遊樂園) zombies of 死城突圍 and its boss, the 馬戲團團長 on his elephant (see CONTEXT.md).
#
#   blender -b -P tools/blender/park_zombies.py -- assets/models/parkzombie.glb [preview.png]
#
# Gear in the frame of the joint it hangs from (game coordinates, +Y up, +Z the way it faces):
#   head frame - skull centre y 0.13, top y ~0.27, face toward +z;  body frame - feet on the origin, chest ~1.35, front z ~0.15
#   knee frame - the shin hangs to the foot at y ~-0.47 (drawn for the right leg);  hand frame - the wrist, fingers toward -y
# The elephant is built at full size on the ground (shoulder ~4 m, facing +Z), like the 遠古巨獸:
#   elephant_body (origin on the ground), elephant_head (origin at the neck joint, (0, 3.6, 2.8) on the body),
#   elephant_leg_front / elephant_leg_back (origin at the hip, the leg hanging to y -2.6), elephant_tail (origin at (0, 3.4, -2.9)),
#   elephant_howdah (body frame), ringmaster_rider (body frame, seated on the howdah; the weak point)
#   balloon (a 氣球炸彈, centred), card (a playing card, centred, face toward +z), fire_hoop (a 火圈 standing in the YZ plane, rolling along Z)
# Untextured: exported without UVs.
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "parkzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(61)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, emission)
    "wig_red": ((0.8, 0.08, 0.06), 0.9, 0.0, 0), "wig_yellow": ((0.9, 0.7, 0.05), 0.9, 0.0, 0), "wig_blue": ((0.1, 0.3, 0.8), 0.9, 0.0, 0),
    "wig_green": ((0.1, 0.6, 0.2), 0.9, 0.0, 0), "nose": ((0.85, 0.03, 0.03), 0.3, 0.0, 0), "ruff": ((0.9, 0.88, 0.84), 0.8, 0.0, 0),
    "shoe": ((0.7, 0.05, 0.05), 0.4, 0.1, 0), "balloon": ((0.85, 0.1, 0.12), 0.25, 0.0, 0), "string": ((0.9, 0.9, 0.9), 0.8, 0.0, 0),
    "fur_pink": ((0.92, 0.72, 0.78), 0.95, 0.0, 0), "fur_white": ((0.92, 0.9, 0.88), 0.95, 0.0, 0), "button": ((0.02, 0.02, 0.02), 0.2, 0.3, 0),
    "stitch": ((0.25, 0.05, 0.05), 0.8, 0.0, 0), "tooth": ((0.95, 0.95, 0.9), 0.4, 0.0, 0), "stain": ((0.35, 0.03, 0.03), 0.6, 0.0, 0),
    "hat_black": ((0.03, 0.03, 0.035), 0.5, 0.1, 0), "cape_red": ((0.55, 0.03, 0.05), 0.6, 0.0, 0), "white": ((0.9, 0.9, 0.88), 0.5, 0.0, 0),
    "eleph_skin": ((0.32, 0.31, 0.32), 0.85, 0.0, 0), "eleph_dark": ((0.18, 0.17, 0.18), 0.85, 0.0, 0), "ivory": ((0.85, 0.8, 0.68), 0.4, 0.0, 0),
    "gold": ((0.8, 0.58, 0.18), 0.3, 0.9, 0), "blanket": ((0.6, 0.05, 0.08), 0.8, 0.0, 0), "plume": ((0.85, 0.15, 0.4), 0.9, 0.0, 0),
    "eye_red": ((1.0, 0.15, 0.1), 0.3, 0.0, 4.0), "coat_red": ((0.7, 0.05, 0.05), 0.6, 0.0, 0), "skin": ((0.55, 0.6, 0.48), 0.7, 0.0, 0),
    "flame": ((1.0, 0.45, 0.05), 0.4, 0.0, 6.0), "hoop": ((0.25, 0.25, 0.27), 0.4, 0.8, 0),
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


def settle(ob, mat, smooth=True):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat, False)


def cyl(p0, p1, r, mat, verts=12, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def lump(c, r, mat, amp=0.1, sub=2, seed=0.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1, location=(0, 0, 0))
    ob = bpy.context.object
    for v in ob.data.vertices:
        p = v.co.copy(); v.co = p * (1 + amp * pnoise(p * 2.0 + Vector((seed, seed * 1.3, seed * 2.1))))
    ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r); ob.location = B(*c)
    return settle(ob, mat)


def tube(pts, r, mat, radii=None, res=5):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 2; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def sheet(pts, mat, t=0.02):
    me = bpy.data.meshes.new("s"); me.from_pydata([B(*p) for p in pts], [], [list(range(len(pts)))])
    ob = bpy.data.objects.new("s", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = t; activate(ob); bpy.ops.object.modifier_apply(modifier="s")
    return settle(ob, mat, False)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== 小丑殭屍: rainbow wig and nose (head), ruff (body), big shoe (knee), balloon bomb
parts = [ball((0, 0.115, 0.14), 0.035, "nose", 12)]
for k in range(30):
    a = random.uniform(-2.3, 2.3) + math.pi; y = random.uniform(0.16, 0.3); r = 0.13 + (0.3 - y) * 0.5
    parts.append(ball((math.sin(a) * r, y, math.cos(a) * r * 0.9), random.uniform(0.05, 0.07), ("wig_red", "wig_yellow", "wig_blue", "wig_green")[k % 4], 8))
for s in (-1, 1):  # big tufts over the ears
    for k in range(3):
        parts.append(ball((s * (0.16 + k * 0.03), 0.17 + k * 0.03, -0.02), 0.07, ("wig_red", "wig_yellow", "wig_blue")[k], 8))
parts += [cyl((0.03, 0.28, -0.02), (0.06, 0.45, -0.04), 0.06, "wig_yellow", 10, 0.0), ball((0.06, 0.46, -0.04), 0.025, "wig_red", 8)]
join(parts, "clown_wig")
parts = []
for k in range(18):  # a ring of ruffles
    a = k / 18 * math.tau
    parts.append(lump((math.sin(a) * 0.16, 1.62, math.cos(a) * 0.14), (0.07, 0.04, 0.07), "ruff", 0.15, 1, k))
for y in (1.4, 1.22, 1.04):
    parts.append(ball((0, y, 0.165), 0.035, ("wig_red", "wig_yellow", "wig_blue")[int(y * 10) % 3], 8))
join(parts, "clown_collar")
join([lump((0.0, -0.44, 0.14), (0.09, 0.07, 0.24), "shoe", 0.05, 2, 1.2), ball((0.0, -0.4, 0.33), (0.07, 0.05, 0.05), "shoe", 10)], "clown_shoe")
join([ball((0, 0.1, 0), (0.33, 0.4, 0.33), "balloon", 16), cyl((0, -0.32, 0), (0, -0.26, 0), 0.04, "balloon", 8, 0.0), tube([(0, -0.32, 0), (0.05, -0.6, 0.02), (0, -0.9, 0)], 0.006, "string")], "balloon")

# ===================================================================== 布偶殭屍: bunny head (head), fluffy suit with a tail (body), paw (hand)
parts = [lump((0, 0.2, 0.02), (0.3, 0.29, 0.29), "fur_white", 0.05, 3, 0.4)]
for s in (-1, 1):
    parts += [lump((s * 0.12, 0.62, -0.02), (0.07, 0.3, 0.05), "fur_white", 0.08, 2, s), lump((s * 0.12, 0.62, 0.015), (0.04, 0.24, 0.02), "fur_pink", 0.05, 1, s * 2),
              ball((s * 0.1, 0.27, 0.27), (0.045, 0.045, 0.02), "button", 10)]
parts += [ball((0, 0.17, 0.3), (0.04, 0.03, 0.02), "fur_pink", 8), box((0, 0.06, 0.29), (0.07, 0.06, 0.02), "tooth"),
          tube([(-0.12, 0.08, 0.27), (0, 0.04, 0.3), (0.12, 0.08, 0.27)], 0.008, "stitch"), lump((0.17, 0.32, 0.17), (0.07, 0.06, 0.04), "stain", 0.2, 1, 3)]
join(parts, "mascot_head")
join([lump((0, 1.25, 0.0), (0.36, 0.5, 0.31), "fur_white", 0.05, 3, 1.1), lump((0, 1.2, 0.22), (0.2, 0.28, 0.12), "fur_pink", 0.05, 2, 2.2),
      ball((0, 0.98, -0.33), 0.1, "fur_white", 10), lump((-0.2, 1.45, 0.2), (0.06, 0.08, 0.04), "stain", 0.3, 1, 5),
      *[lump((s * 0.2, 0.8, 0.0), (0.16, 0.16, 0.16), "fur_white", 0.05, 2, s) for s in (-1, 1)]], "mascot_suit")
join([lump((0, -0.08, 0.02), (0.1, 0.11, 0.09), "fur_white", 0.05, 2, 6.6), *[ball((x, -0.17, 0.06), 0.025, "fur_pink", 8) for x in (-0.04, 0, 0.04)]], "mascot_paw")

# ===================================================================== 魔術師殭屍: top hat (head), cape with collar and bow tie (body), wand (hand), card
join([cyl((0, 0.25, -0.01), (0, 0.28, -0.01), 0.2, "hat_black", 20), cyl((0, 0.28, -0.01), (0, 0.52, -0.01), 0.125, "hat_black", 18, 0.13),
      cyl((0, 0.3, -0.01), (0, 0.34, -0.01), 0.128, "cape_red", 18)], "magician_hat")
parts = []
for side, mat, off in (("out", "hat_black", 0), ("in", "cape_red", 0.012)):
    pts = []
    for k in range(9):
        a = math.pi * (0.25 + k / 8 * 1.5); r = 0.24
        pts.append((math.sin(a) * r, 1.6, math.cos(a) * r * 0.85 + (-off if math.cos(a) < 0 else 0)))
    bottom = [(x * 1.45, 0.65, z * 1.5 - 0.06) for x, y, z in reversed(pts)]
    me_pts = pts + bottom
    vs = [B(*p) for p in me_pts]; n = len(pts)
    fs = [(k, k + 1, 2 * n - 2 - k, 2 * n - 1 - k) for k in range(n - 1)]
    me = bpy.data.meshes.new("c"); me.from_pydata(vs, [], fs); ob = bpy.data.objects.new("c", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.015; activate(ob); bpy.ops.object.modifier_apply(modifier="s"); parts.append(settle(ob, mat))
for s in (-1, 1):  # the high collar
    parts.append(sheet([(s * 0.1, 1.6, -0.12), (s * 0.24, 1.62, -0.05), (s * 0.27, 1.92, -0.1), (s * 0.12, 1.88, -0.16)], "cape_red", 0.015))
parts += [box((0, 1.6, 0.16), (0.12, 0.05, 0.02), "hat_black"), ball((0, 1.6, 0.17), 0.02, "hat_black", 8)]
join(parts, "magician_cape")
join([cyl((0, -0.08, 0.02), (0, -0.1, 0.32), 0.012, "hat_black", 8), cyl((0, -0.1, 0.32), (0, -0.101, 0.36), 0.013, "white", 8)], "wand")
join([box((0, 0, 0), (0.07, 0.1, 0.004), "white"), box((0, 0, 0.003), (0.025, 0.03, 0.002), "nose")], "card")

# ===================================================================== the elephant
body = lump((0, 3.2, 0), (1.7, 1.55, 3.0), "eleph_skin", 0.06, 3, 0.7)
parts = [body, lump((0, 4.0, 1.4), (1.4, 0.9, 1.4), "eleph_skin", 0.06, 2, 1.7)]
for k in range(8):  # wrinkles and scars
    z = random.uniform(-2.2, 2.2); s = random.choice((-1, 1))
    parts.append(tube([(s * 1.55, 2.6 + k * 0.1, z), (s * 1.66, 3.2 + k * 0.05, z + 0.2), (s * 1.55, 3.8, z + 0.1)], 0.03, "eleph_dark" if k % 2 else "stain"))
join(parts, "elephant_body")
parts = [lump((0, 0.1, 1.0), (1.05, 1.15, 1.05), "eleph_skin", 0.05, 2, 2.4),
         tube([(0, -0.2, 1.8), (0, -1.1, 2.3), (0, -2.1, 2.5), (0, -2.9, 2.3), (0, -3.1, 2.7)], 0.32, "eleph_skin", [1, 0.85, 0.65, 0.45, 0.35])]
for s in (-1, 1):
    parts += [sheet([(s * 0.8, 0.9, 0.5), (s * 2.0, 0.6, 0.0), (s * 2.1, -0.8, -0.1), (s * 1.4, -1.4, 0.3), (s * 0.8, -0.6, 0.6)], "eleph_dark", 0.08),
              tube([(s * 0.4, -0.7, 1.6), (s * 0.6, -1.4, 2.2), (s * 0.55, -1.6, 3.0), (s * 0.4, -1.2, 3.5)], 0.13, "ivory", [1, 0.9, 0.6, 0.25]),
              ball((s * 0.6, 0.35, 1.75), (0.13, 0.1, 0.08), "eye_red", 8)]
parts += [box((0, 0.95, 1.5), (1.0, 0.25, 0.9), "gold", (math.radians(-15), 0, 0)), cyl((0, 1.0, 1.4), (0, 1.9, 1.2), 0.12, "plume", 8, 0.25),
          lump((0, 1.95, 1.2), (0.25, 0.35, 0.2), "plume", 0.3, 1, 3)]
join(parts, "elephant_head")
for name, zf in (("elephant_leg_front", 1), ("elephant_leg_back", -1)):
    parts = [lump((0, -0.3, 0), (0.7, 0.8, 0.75), "eleph_skin", 0.06, 2, zf), cyl((0, -0.8, 0), (0, -2.45, 0.05 * zf), 0.58, "eleph_skin", 14, 0.62),
             cyl((0, -2.45, 0.05 * zf), (0, -2.6, 0.05 * zf), 0.66, "eleph_dark", 14, 0.66)]
    for k in range(3):
        a = (k - 1) * 0.5
        parts.append(ball((math.sin(a) * 0.5, -2.5, math.cos(a) * 0.5 + 0.05 * zf), (0.12, 0.08, 0.06), "ivory", 8))
    join(parts, name)
join([tube([(0, 0, 0), (0, -0.7, -0.4), (0, -1.6, -0.5)], 0.08, "eleph_skin", [1, 0.7, 0.5]), lump((0, -1.7, -0.5), (0.12, 0.18, 0.12), "eleph_dark", 0.3, 1, 4)], "elephant_tail")
parts = [lump((0, 4.6, -0.2), (1.75, 0.35, 1.6), "blanket", 0.05, 2, 2.0)]
for s in (-1, 1):  # the blanket hanging over the flanks, with a gold border and tassels
    parts.append(sheet([(s * 1.55, 4.6, -1.5), (s * 1.55, 4.6, 1.1), (s * 1.75, 3.2, 1.0), (s * 1.75, 3.2, -1.4)], "blanket", 0.05))
    parts.append(box((s * 1.77, 3.2, -0.2), (0.06, 0.15, 2.5), "gold"))
    for k in range(6):
        z = -1.3 + k * 0.48
        parts += [cyl((s * 1.78, 3.15, z), (s * 1.8, 2.75, z), 0.03, "gold", 6), ball((s * 1.8, 2.7, z), 0.06, "plume", 8)]
parts += [box((0, 4.95, -0.3), (1.3, 0.3, 1.4), "gold"), box((0, 5.1, -0.3), (1.1, 0.12, 1.2), "blanket")]
join(parts, "elephant_howdah")
# the ringmaster, seated on the howdah (about 1.3 x human size, facing +Z), whip raised
parts = [lump((0, 5.85, -0.3), (0.42, 0.55, 0.32), "coat_red", 0.05, 2, 1.1), box((0, 5.6, -0.08), (0.5, 0.5, 0.06), "white"),
         *[ball((0, 5.85 - k * 0.18, 0.02), 0.035, "gold", 8) for k in range(3)],
         ball((0, 6.6, -0.28), (0.2, 0.24, 0.21), "skin", 14), ball((0, 6.6, -0.08), (0.05, 0.03, 0.03), "eye_red", 6),
         cyl((0, 6.78, -0.28), (0, 6.82, -0.28), 0.32, "hat_black", 18), cyl((0, 6.82, -0.28), (0, 7.25, -0.28), 0.19, "hat_black", 16, 0.2),
         cyl((0, 6.85, -0.28), (0, 6.92, -0.28), 0.2, "cape_red", 16)]
for s in (-1, 1):  # legs astride, arms
    parts += [cyl((s * 0.22, 5.4, -0.25), (s * 0.85, 5.0, 0.1), 0.12, "hat_black", 10), cyl((s * 0.85, 5.0, 0.1), (s * 0.95, 4.3, 0.2), 0.1, "hat_black", 10),
              ball((s * 0.95, 4.2, 0.3), (0.1, 0.08, 0.2), "hat_black", 10)]
parts += [cyl((-0.4, 6.15, -0.3), (-0.55, 5.7, 0.05), 0.09, "coat_red", 10), cyl((0.4, 6.15, -0.3), (0.75, 6.75, -0.1), 0.09, "coat_red", 10),
          tube([(0.78, 6.8, -0.08), (1.1, 7.6, 0.2), (1.6, 7.9, 0.9), (2.2, 7.3, 1.6), (2.4, 6.6, 1.9)], 0.02, "hat_black", [1.6, 1.2, 1, 0.8, 0.5])]
join(parts, "ringmaster_rider")
# 火圈: a hoop rolling along Z (it stands in the YZ plane; the game spins it about X)

bpy.ops.mesh.primitive_torus_add(major_radius=1.2, minor_radius=0.08, major_segments=40, minor_segments=6, location=(0, 0, 0), rotation=(0, math.pi / 2, 0))
parts = [settle(bpy.context.object, "hoop")]
for k in range(18):
    a = k / 18 * math.tau; y, z = math.cos(a) * 1.25, math.sin(a) * 1.25
    parts.append(cyl((0, y, z), (0, y * 1.25, z * 1.25), 0.1, "flame", 6, 0.0))
join(parts, "fire_hoop")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"elephant_body": (0, 0, 0), "elephant_howdah": (0, 0, 0), "ringmaster_rider": (0, 0, 0), "elephant_head": (0, 3.6, 2.8), "elephant_tail": (0, 3.4, -2.9),
             "fire_hoop": (6, 1.3, 3), "clown_wig": (-4, 1.72, 3.03), "clown_collar": (-4, 0, 3), "balloon": (-4.5, 1.5, 4), "mascot_head": (-5.5, 1.72, 3.03),
             "mascot_suit": (-5.5, 0, 3), "magician_hat": (-2.6, 1.72, 3.03), "magician_cape": (-2.6, 0, 3), "card": (-2, 1.2, 4)}
    legs = [("elephant_leg_front", 1.15, 2.6, 2.0), ("elephant_leg_back", 1.15, 2.6, -2.0)]
    for ob in list(PARTS):
        if ob.name in place: ob.location = B(*place[ob.name])
        elif ob.name in ("clown_shoe", "mascot_paw", "wand"): ob.location = B(0, -20, 0)
        for n, x, y, z in legs:
            if ob.name == n:
                ob.location = B(x, y, z); c = ob.copy(); c.data = ob.data; scene.collection.objects.link(c); c.location = B(-x, y, z)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.28, 0.34, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(55), 0, math.radians(40))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 28; eye, tgt = B(9, 5, 16), B(-0.5, 3, 1)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
