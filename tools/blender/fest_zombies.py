# Costumes and props for the 國慶特別版 zombies of 死城突圍.
#
#   blender -b -P tools/blender/fest_zombies.py -- assets/models/festzombie.glb [preview.png]
#
# They dress the game's existing zombie body (tools/blender/zombie.py), so each piece is modelled in
# the frame of the joint it hangs from, in game coordinates (+Y up, +Z the way the zombie faces):
#   head frame  - the head pivot; the skull centre is at y 0.13, the face toward +z (riot helmet: y 0.19, r ~0.17)
#   body frame  - feet on the origin; chest around y 1.35, the front of the torso at z ~0.15
#   hand frame  - the wrist; the fingers hang toward -y, the palm faces inward
#   segment     - dragon body pieces run along +z from 0 to 1 (the game stretches them between dancers)
# Material names are keys the game swaps for its own materials.
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "festzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(5)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "paper_red": ((0.6, 0.04, 0.02), 0.75, 0.0), "paper_gold": ((0.8, 0.55, 0.12), 0.5, 0.4), "fuse": ((0.15, 0.12, 0.08), 0.9, 0.0),
    "strap": ((0.12, 0.09, 0.06), 0.8, 0.0), "gold": ((0.8, 0.55, 0.15), 0.3, 1.0), "wood": ((0.3, 0.16, 0.07), 0.7, 0.0),
    "lion_red": ((0.6, 0.03, 0.02), 0.5, 0.0), "lion_gold": ((0.85, 0.6, 0.1), 0.35, 0.6), "lion_fur": ((0.9, 0.88, 0.82), 0.95, 0.0),
    "lion_green": ((0.05, 0.35, 0.12), 0.5, 0.0), "eye_white": ((0.92, 0.9, 0.85), 0.3, 0.0), "eye_black": ((0.01, 0.01, 0.01), 0.2, 0.0),
    "mirror": ((0.9, 0.92, 0.95), 0.05, 1.0), "mouth_red": ((0.25, 0.01, 0.01), 0.6, 0.0), "bronze": ((0.55, 0.35, 0.12), 0.3, 1.0),
    "sash_red": ((0.55, 0.03, 0.02), 0.8, 0.0), "dragon_scale": ((0.7, 0.42, 0.05), 0.45, 0.5), "dragon_belly": ((0.75, 0.05, 0.03), 0.6, 0.0),
    "fringe": ((0.85, 0.6, 0.1), 0.5, 0.6), "tassel": ((0.6, 0.03, 0.02), 0.8, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    MAT[n] = m


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def apply_mods(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def settle(ob, mat):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, bev=0.15, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    settle(ob, mat)
    if bev:
        bv = ob.modifiers.new("b", "BEVEL"); bv.width = min(s) * bev; bv.segments = 2; apply_mods(ob)
    return ob


def cyl(p0, p1, r, mat, verts=12, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def tube(pts, r, mat, res=4):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def tuft(c, r, mat="lion_fur"):
    """A fluffy pompom of fur: a lumpy sphere."""
    ob = ball(c, r, mat, 12)
    for v in ob.data.vertices:
        v.co += v.normal * (r if isinstance(r, float) else r[0]) * random.uniform(-0.15, 0.25)
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


def ring_points(cy, r, n, start=0.0, z0=0.0, rz=None):
    rz = rz or r
    return [(math.cos(start + k / n * math.tau) * r, cy, z0 + math.sin(start + k / n * math.tau) * rz) for k in range(n)]


# ===================================================================== 鞭炮殭屍: firecracker strings (body frame)
parts = []
def cracker_string(path, n):
    """Red firecrackers along a path with a fuse cord through them."""
    out = [tube(path, 0.004, "fuse")]
    pts = [Vector(p) for p in path]
    seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum((b - a).length for a, b in seg)
    for k in range(n):
        d = (k + 0.5) / n * total
        for a, b in seg:
            L = (b - a).length
            if d <= L:
                p = a + (b - a) * (d / L); t = (b - a).normalized()
                side = Vector((t.z, 0, -t.x)).normalized() if abs(t.y) < 0.95 else Vector((1, 0, 0))
                c = p + side * (0.012 if k % 2 else -0.012)
                out.append(cyl(tuple(c + Vector((0, 0.024, 0))), tuple(c - Vector((0, 0.024, 0))), 0.0085, "paper_red" if k % 5 else "paper_gold", 8))
                break
            d -= L
    return out
# two bandoliers crossing the chest and back, a belt of crackers, and strings hanging from the shoulders
for s in (1, -1):
    band = [(0.17 * s, 1.56, 0.06), (0.05 * s, 1.42, 0.165), (-0.12 * s, 1.18, 0.15), (-0.18 * s, 1.05, 0.0), (-0.1 * s, 1.18, -0.15), (0.06 * s, 1.42, -0.14), (0.17 * s, 1.56, 0.0)]
    parts += cracker_string(band, 34)
belt = [(math.cos(a) * 0.205, 1.06, math.sin(a) * 0.15) for a in [k / 24 * math.tau for k in range(25)]]
parts += cracker_string(belt, 30)
for s in (1, -1):
    hang = [(0.2 * s, 1.55, 0.05), (0.22 * s, 1.35, 0.1), (0.21 * s, 1.15, 0.12)]
    parts += cracker_string(hang, 12)
parts.append(ball((0.0, 1.42, 0.17), (0.035, 0.035, 0.012), "paper_gold"))  # a lucky gold knot on the chest
join(parts, "firecracker_wrap")

# ===================================================================== 煙火殭屍: a bundle of fireworks on the back (body frame)
parts = []
for i, (x, y, h, r) in enumerate(((-0.1, 1.15, 0.5, 0.05), (0.0, 1.15, 0.58, 0.055), (0.1, 1.15, 0.5, 0.05), (-0.05, 1.16, 0.44, 0.045),
                                  (0.05, 1.16, 0.46, 0.045), (-0.15, 1.18, 0.36, 0.04), (0.15, 1.18, 0.38, 0.04))):
    z = -0.22 - (0.05 if i >= 3 else 0)
    parts += [cyl((x, y, z), (x, y + h, z), r, "paper_red" if i % 2 == 0 else "paper_gold", 14),
              cyl((x, y + h, z), (x, y + h + 0.012, z), r * 1.04, "gold", 14),
              cyl((x, y + h + 0.012, z), (x + random.uniform(-0.02, 0.02), y + h + 0.08, z), 0.004, "fuse", 6)]
for k in range(4):  # rockets on sticks poking over the shoulders
    x = (-0.18, -0.06, 0.08, 0.2)[k]
    parts += [cyl((x, 1.6, -0.18), (x, 1.85, -0.18), 0.022, "paper_red", 10), cyl((x, 1.85, -0.18), (x, 1.9, -0.18), 0.022, "gold", 10, 0.002),
              cyl((x, 1.6, -0.18), (x, 1.2, -0.2), 0.004, "wood", 6)]
for y in (1.25, 1.5):  # straps over the shoulders and around the bundle
    parts.append(cyl((-0.2, y, -0.19), (0.2, y, -0.19), 0.012, "strap", 8))
for s in (1, -1):
    parts.append(tube([(0.15 * s, 1.5, -0.17), (0.17 * s, 1.6, -0.05), (0.15 * s, 1.55, 0.12), (0.13 * s, 1.3, 0.16), (0.15 * s, 1.15, 0.1)], 0.012, "strap"))
join(parts, "firework_pack")

# ===================================================================== 舞獅殭屍: lion head (head frame) and cloak (body frame)
parts = []
head_c = (0, 0.2, 0.06)
lh = ball(head_c, (0.27, 0.24, 0.26), "lion_red", 24)
for v in lh.data.vertices:  # flatten the face, swell the cheeks
    p = Vector((v.co.x, v.co.z, -v.co.y))
    if p.z > 0.14:
        v.co.y = -(0.14 + (p.z - 0.14) * 0.5)
parts.append(lh)
parts += [ball((0, 0.4, 0.06), (0.2, 0.06, 0.18), "lion_gold", 18),          # crown band
          cyl((0, 0.42, 0.14), (0, 0.52, 0.2), 0.035, "lion_green", 10, 0.012),  # unicorn horn
          ball((0, 0.33, 0.29), (0.05, 0.05, 0.012), "mirror", 16),          # mirror on the forehead (wards off evil)
          box((0, 0.025, 0.25), (0.3, 0.08, 0.1), "lion_gold", 0.3),         # upper lip
          box((0, -0.05, 0.22), (0.26, 0.05, 0.12), "lion_red", 0.3),        # jaw
          box((0, -0.01, 0.26), (0.24, 0.05, 0.05), "mouth_red", 0.2)]       # open mouth
for s in (1, -1):
    parts += [ball((0.11 * s, 0.24, 0.27), (0.07, 0.065, 0.03), "eye_white", 16), ball((0.11 * s, 0.24, 0.296), (0.032, 0.032, 0.012), "eye_black", 12),
              tube([(0.04 * s, 0.31, 0.29), (0.11 * s, 0.33, 0.29), (0.19 * s, 0.31, 0.26)], 0.012, "lion_gold"),        # brows
              ball((0.2 * s, 0.13, 0.22), (0.07, 0.06, 0.05), "lion_gold", 14),                                             # cheeks
              box((0.17 * s, 0.4, -0.02), (0.06, 0.14, 0.03), "lion_gold", 0.3, (0, 0, -0.4 * s)),                         # ears
              ball((0.08 * s, 0.07, 0.29), (0.025, 0.02, 0.01), "eye_white", 8)]                                            # teeth
    for k in range(5):  # white fur fringe along the jaw and over the eyes
        parts.append(tuft((0.06 * s + 0.045 * s * k, 0.29 + 0.012 * k, 0.29 - 0.03 * k), 0.032))
        parts.append(tuft((0.05 * s + 0.05 * s * k, -0.08 - 0.01 * k, 0.24 - 0.04 * k), 0.035))
for k in range(9):  # a beard of fur under the chin
    a = (k / 8 - 0.5) * 2.4
    parts.append(tuft((math.sin(a) * 0.17, -0.12 - 0.02 * math.cos(a), 0.12 + math.cos(a) * 0.1), 0.04))
for k in range(12):  # mane around the back of the head
    a = math.pi * 0.25 + k / 11 * math.pi * 1.5
    parts.append(tuft((math.sin(a) * 0.27, 0.22 + 0.05 * math.sin(k), 0.02 + math.cos(a) * 0.27), 0.05))
join(parts, "lion_head")

parts = []
# the cloak drapes from the back of the head down the back to the knees, scalloped with fur along the edges
cols, rows = 10, 12
vs, fs = [], []
for j in range(rows + 1):
    for i in range(cols + 1):
        u, v = i / cols - 0.5, j / rows
        y = 1.72 - v * 1.1
        w = 0.42 + v * 0.18
        z = -0.17 - 0.06 * math.sin(v * math.pi) - 0.03 * math.cos(u * math.pi * 3) * v
        vs.append(B(u * w * 2, y, z + 0.08 * math.cos(u * math.pi) - 0.08))
for j in range(rows):
    for i in range(cols):
        a = j * (cols + 1) + i
        fs.append((a, a + 1, a + cols + 2, a + cols + 1))
me = bpy.data.meshes.new("cloak"); me.from_pydata(vs, [], fs)
ob = bpy.data.objects.new("cloak", me); scene.collection.objects.link(ob)
so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.01; apply_mods(ob)
parts.append(settle(ob, "lion_red"))
for k in range(9):  # gold scales painted on as raised plates
    for j in range(3):
        parts.append(ball(((k / 8 - 0.5) * 0.7, 1.55 - j * 0.3, -0.3 - 0.05 * math.cos((k / 8 - 0.5) * math.pi)), (0.04, 0.04, 0.01), "lion_gold", 8))
for k in range(14):
    u = k / 13 - 0.5
    parts.append(tuft((u * 1.2, 0.6, -0.27 + 0.08 * math.cos(u * math.pi) - 0.08), 0.04))
join(parts, "lion_cloak")

# ===================================================================== 敲鑼殭屍: gong (left hand) and mallet (right hand), red sash (body)
parts = []
gc = (0.0, -0.2, 0.2)  # the gong hangs from the fist on a cord, its face toward +z
prof = [(0.0, 0.0), (0.012, 0.05), (0.016, 0.07), (0.01, 0.075), (0.008, 0.2), (0.0, 0.215), (-0.035, 0.22), (-0.035, 0.205)]
vs, fs, n = [], [], 48
for y, r in prof:  # turned around +z: y here is depth, r the radius
    for k in range(n):
        a = k / n * math.tau
        vs.append(B(gc[0] + math.cos(a) * r, gc[1] + math.sin(a) * r, gc[2] + y))
for i in range(len(prof) - 1):
    for k in range(n):
        a, b = i * n + k, i * n + (k + 1) % n
        fs.append((a, b, b + n, a + n))
me = bpy.data.meshes.new("gong"); me.from_pydata(vs, [], fs)
ob = bpy.data.objects.new("gong", me); scene.collection.objects.link(ob)
parts.append(settle(ob, "bronze"))
parts.append(ball((gc[0], gc[1], gc[2] + 0.013), (0.045, 0.045, 0.012), "gold", 16))
parts += [tube([(-0.02, -0.03, 0.06), (-0.1, 0.0, 0.18), (gc[0] - 0.12, gc[1] + 0.17, gc[2] - 0.02)], 0.005, "tassel"),
          tube([(0.02, -0.03, 0.06), (0.1, 0.0, 0.18), (gc[0] + 0.12, gc[1] + 0.17, gc[2] - 0.02)], 0.005, "tassel"),
          cyl((gc[0], gc[1] - 0.22, gc[2] - 0.02), (gc[0], gc[1] - 0.36, gc[2] - 0.02), 0.012, "tassel", 8, 0.03)]
join(parts, "gong")
join([cyl((0, -0.06, -0.08), (0, -0.06, 0.32), 0.012, "wood", 10), ball((0, -0.06, 0.34), (0.045, 0.045, 0.045), "paper_red", 14),
      cyl((0, -0.06, 0.3), (0, -0.06, 0.32), 0.03, "gold", 12)], "gong_mallet")
parts = []
sash = [(0.17, 1.56, 0.03), (0.0, 1.38, 0.17), (-0.17, 1.12, 0.12), (-0.19, 1.05, 0.0), (-0.05, 1.25, -0.16), (0.12, 1.45, -0.13), (0.17, 1.56, 0.0)]
parts.append(tube(sash, 0.03, "sash_red"))
parts.append(ball((-0.17, 1.1, 0.12), (0.06, 0.05, 0.03), "sash_red"))
parts += [cyl((-0.17, 1.07, 0.13), (-0.2, 0.85, 0.14), 0.02, "sash_red", 8, 0.03), cyl((-0.15, 1.07, 0.13), (-0.12, 0.88, 0.14), 0.02, "sash_red", 8, 0.03)]
join(parts, "red_sash")

# ===================================================================== 舞龍: head (head frame), body segment, tail, pole (hand frame)
parts = []
dh = ball((0, 0.24, 0.16), (0.24, 0.22, 0.34), "dragon_scale", 24)
for v in dh.data.vertices:  # a long snout
    p = Vector((v.co.x, v.co.z, -v.co.y))
    if p.z > 0.2:
        k = (p.z - 0.2) / 0.3
        v.co.x *= 1 - 0.35 * k; v.co.z = 0.24 + (p.y - 0.24) * (1 - 0.3 * k)
parts.append(dh)
parts += [box((0, 0.08, 0.32), (0.32, 0.06, 0.36), "dragon_belly", 0.3, (0.25, 0, 0)),        # open lower jaw
          box((0, 0.13, 0.4), (0.3, 0.05, 0.22), "mouth_red", 0.2)]
for s in (1, -1):
    parts += [ball((0.13 * s, 0.36, 0.3), (0.07, 0.07, 0.05), "eye_white", 16), ball((0.13 * s, 0.36, 0.345), (0.033, 0.033, 0.014), "eye_black", 12),
              tube([(0.1 * s, 0.42, 0.05), (0.2 * s, 0.6, -0.05), (0.18 * s, 0.75, -0.22)], 0.022, "lion_gold"),            # antlers
              tube([(0.15 * s, 0.6, -0.08), (0.27 * s, 0.68, -0.08)], 0.012, "lion_gold"),
              tube([(0.1 * s, 0.22, 0.5), (0.3 * s, 0.18, 0.55), (0.5 * s, 0.05, 0.45), (0.6 * s, -0.15, 0.35)], 0.008, "lion_gold"),  # whiskers
              ball((0.07 * s, 0.25, 0.53), (0.025, 0.02, 0.02), "eye_black", 8)]                                              # nostrils
    for k in range(4):
        parts.append(box((0.12 * s, 0.17 - k * 0.0, 0.36 + k * 0.05), (0.015, 0.04, 0.012), "eye_white", 0, (0.2, 0, 0)))   # fangs
for k in range(10):  # a fiery mane down the back of the head
    a = k / 9
    parts.append(cyl((0, 0.35 - a * 0.1, 0.05 - a * 0.3), (random.uniform(-0.1, 0.1), 0.55 - a * 0.15, -0.05 - a * 0.35), 0.04, "dragon_belly" if k % 2 else "lion_gold", 8, 0.004))
join(parts, "dragon_head")


def dragon_segment(name, taper=0.0):
    parts = []
    n, rings = 20, 8
    vs, fs = [], []
    for j in range(rings + 1):
        z = j / rings; r = 0.3 * (1 - taper * z)
        for k in range(n):
            a = k / n * math.tau
            vs.append(B(math.cos(a) * r, math.sin(a) * r * 0.85, z))
    for j in range(rings):
        for k in range(n):
            a, b = j * n + k, j * n + (k + 1) % n
            fs.append((a, b, b + n, a + n))
    me = bpy.data.meshes.new(name); me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.01; apply_mods(ob)
    parts.append(settle(ob, "dragon_scale"))
    belly = ball((0, -0.17 * (1 - taper * 0.5), 0.5), (0.22 * (1 - taper * 0.5), 0.1, 0.5), "dragon_belly", 16)
    parts.append(belly)
    for j in range(5):  # gold dorsal fins
        z = 0.1 + j * 0.2; r = 0.3 * (1 - taper * z)
        parts.append(box((0, r * 0.85 + 0.06, z), (0.015, 0.14 * (1 - taper * z), 0.12), "lion_gold", 0.2))
    for j in range(4):  # scale rows
        for k in range(8):
            a = math.pi * 0.15 + k / 7 * math.pi * 0.7
            z = 0.12 + j * 0.25; r = 0.305 * (1 - taper * z)
            parts.append(ball((math.cos(a) * r, math.sin(a) * r * 0.85, z), (0.045, 0.045, 0.012), "lion_gold", 6))
    for k in range(10):  # fringe hanging from the belly
        parts.append(box(((k / 9 - 0.5) * 0.4, -0.3, 0.05 + 0.1 * k), (0.02, 0.18, 0.04), "fringe", 0))
    return join(parts, name)


dragon_segment("dragon_body")
dragon_segment("dragon_tail", 0.85)
join([cyl((0, -0.05, 0), (0, 0.85, 0), 0.016, "wood", 10), cyl((0, 0.85, 0), (0, 0.88, 0), 0.025, "gold", 10)], "dragon_pole")

# ===================================================================== 遊行花車巨屍: a gold opera crown and a sash for the boss
parts = [cyl((0, 0.28, 0), (0, 0.38, 0), 0.17, "lion_gold", 24, 0.19)]
for k in range(8):
    a = k / 8 * math.tau
    parts += [box((math.sin(a) * 0.18, 0.43, math.cos(a) * 0.18), (0.06, 0.1, 0.012), "lion_gold", 0.3, (0, 0, a)),
              ball((math.sin(a) * 0.19, 0.48, math.cos(a) * 0.19), 0.02, "paper_red", 8)]
parts += [ball((0, 0.36, 0.18), (0.035, 0.035, 0.015), "mirror", 12)]
for s in (1, -1):
    parts += [tube([(0.17 * s, 0.33, 0.0), (0.24 * s, 0.25, 0.02), (0.26 * s, 0.05, 0.04)], 0.012, "tassel"), ball((0.26 * s, 0.02, 0.04), 0.03, "tassel", 8)]
join(parts, "boss_crown")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"firecracker_wrap": (-1.6, 0), "firework_pack": (-0.8, 0), "lion_head": (0.0, 1.45), "lion_cloak": (0.0, 0), "gong": (0.85, 1.0),
              "gong_mallet": (1.05, 1.0), "red_sash": (0.85, 0), "dragon_head": (1.8, 1.4), "dragon_body": (1.65, 0.6), "dragon_tail": (2.4, 0.6),
              "dragon_pole": (2.0, 0.0), "boss_crown": (-1.6, 1.55)}
    for ob in PARTS:
        x, y = layout.get(ob.name, (0, 0))
        ob.location = B(x, y, 0); ob.rotation_euler = (0, 0, math.radians(25))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 5.0
    cam.location = B(0.4, 1.1, 8); cam.rotation_euler = (B(0.4, 1.1, 0) - B(0.4, 1.1, 8)).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((3, 5, 6), 1500), ((-4, 2, 4), 600)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 5; l.location = B(*loc)
        l.rotation_euler = (B(0.4, 1, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 32; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
