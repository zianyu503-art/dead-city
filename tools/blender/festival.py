# Street-festival props for the 國慶特別版 level of 死城突圍.
#
#   blender -b -P tools/blender/festival.py -- assets/models/festival.glb [preview.png]
#
# Every prop stands on its own origin (base centre on the ground, or the hanging point for the
# lantern), faces +Z in the game, and is written in game coordinates (+Y up, +Z forward, metres);
# B() converts to Blender. Material names are keys the game maps to its own materials, and the
# text panels ("banner_v", "banner_h", "arch_sign", "screen", "stall_sign", "crate_label") carry
# UVs that cover the panel exactly, so the game can paint 「歡度國慶」 and friends onto them.
import bpy, bmesh, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "festival.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(10)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PROPS = []

PALETTE = {  # preview colours (the game swaps in its own materials by name)
    "lantern_silk": ((0.75, 0.04, 0.02), 0.5, 0.0, (1.0, 0.18, 0.05), 3.0), "gold": ((0.8, 0.55, 0.15), 0.3, 1.0, None, 0),
    "tassel": ((0.6, 0.03, 0.02), 0.8, 0.0, None, 0), "wire": ((0.03, 0.03, 0.03), 0.6, 0.3, None, 0),
    "pole_red": ((0.45, 0.03, 0.02), 0.35, 0.1, None, 0), "pennant_red": ((0.7, 0.04, 0.03), 0.8, 0, None, 0),
    "pennant_gold": ((0.85, 0.6, 0.08), 0.8, 0, None, 0), "pennant_white": ((0.85, 0.83, 0.78), 0.8, 0, None, 0),
    "pennant_orange": ((0.9, 0.3, 0.04), 0.8, 0, None, 0), "banner_v": ((0.7, 0.05, 0.03), 0.85, 0, None, 0),
    "banner_h": ((0.7, 0.05, 0.03), 0.85, 0, None, 0), "arch_sign": ((0.7, 0.05, 0.03), 0.5, 0, (1, 0.3, 0.1), 1.0),
    "bulb": ((1.0, 0.85, 0.5), 0.3, 0, (1.0, 0.8, 0.45), 6.0), "bulb_color": ((1.0, 0.3, 0.3), 0.3, 0, (1.0, 0.3, 0.2), 6.0),
    "screen": ((0.05, 0.02, 0.02), 0.2, 0, (1.0, 0.3, 0.1), 1.5), "truss": ((0.6, 0.62, 0.65), 0.35, 1.0, None, 0),
    "speaker": ((0.02, 0.02, 0.02), 0.7, 0, None, 0), "stage_floor": ((0.06, 0.05, 0.05), 0.6, 0, None, 0),
    "carpet": ((0.45, 0.02, 0.02), 0.95, 0, None, 0), "spot_lens": ((1, 1, 0.9), 0.1, 0, (1, 0.95, 0.85), 8.0),
    "wood": ((0.32, 0.18, 0.08), 0.7, 0, None, 0), "awning_red": ((0.7, 0.04, 0.03), 0.8, 0, None, 0),
    "awning_white": ((0.85, 0.83, 0.78), 0.8, 0, None, 0), "stall_sign": ((0.8, 0.6, 0.1), 0.6, 0, (1, 0.8, 0.4), 0.6),
    "metal": ((0.25, 0.26, 0.28), 0.4, 0.8, None, 0), "paper_red": ((0.6, 0.05, 0.03), 0.8, 0, None, 0),
    "paper_gold": ((0.8, 0.55, 0.12), 0.6, 0.3, None, 0), "fuse": ((0.15, 0.12, 0.08), 0.9, 0, None, 0),
    "crate_label": ((0.9, 0.85, 0.7), 0.7, 0, None, 0), "balloon_red": ((0.75, 0.03, 0.02), 0.25, 0, None, 0),
    "balloon_gold": ((0.85, 0.6, 0.1), 0.25, 0.6, None, 0), "balloon_white": ((0.9, 0.9, 0.88), 0.25, 0, None, 0),
    "string": ((0.8, 0.8, 0.8), 0.6, 0, None, 0), "bark": ((0.12, 0.08, 0.05), 0.9, 0, None, 0),
    "foliage": ((0.03, 0.12, 0.05), 0.9, 0, None, 0), "flower_red": ((0.7, 0.02, 0.04), 0.7, 0, None, 0),
    "flower_gold": ((0.9, 0.6, 0.05), 0.6, 0, None, 0), "fringe": ((0.85, 0.6, 0.1), 0.5, 0.6, None, 0),
    "float_body": ((0.55, 0.04, 0.03), 0.4, 0.1, None, 0), "tire": ((0.02, 0.02, 0.02), 0.9, 0, None, 0),
}
MAT = {}
for n, (c, r, mt, em, es) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if em:
        b.inputs["Emission Color"].default_value = (*em, 1); b.inputs["Emission Strength"].default_value = es
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


def settle(ob, mat, smooth=True):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, bev=0.15, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    settle(ob, mat)
    if bev:
        bv = ob.modifiers.new("b", "BEVEL"); bv.width = min(s) * bev; bv.segments = 2; apply_mods(ob)
    return ob


def cyl(p0, p1, r, mat, verts=16, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def tube(pts, r, mat, res=6):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*B(*p), 1)
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def panel(corners, mat, name="panel"):
    """A quad with UVs spanning 0..1 (bottom-left, bottom-right, top-right, top-left), for text textures."""
    me = bpy.data.meshes.new(name); me.from_pydata([B(*c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, l in enumerate(me.loops):
        uv.data[i].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[l.vertex_index]
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    return settle(ob, mat, smooth=False)


def cloth(w, h, mat, waves=3, amp=0.06, segs=(24, 8), name="cloth"):
    """A hanging fabric panel in the XY plane facing +Z, gently rippled, UVs spanning the panel."""
    nx, ny = segs
    vs, fs, uvs = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            vs.append(B((u - 0.5) * w, (v - 1) * h, amp * math.sin(u * waves * math.tau) * (0.4 + 0.6 * (1 - v))))
            uvs.append((u, v))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            fs.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new(name); me.from_pydata(vs, [], fs)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uv.data[li].uv = uvs[me.loops[li].vertex_index]
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.012; apply_mods(ob)
    return settle(ob, mat)


def lathe(profile, mat, verts=24, ribs=0, rib_amp=0.0):
    """Turned shape around the vertical axis: profile = [(y, radius)], optional vertical ribs."""
    vs, fs = [], []
    for y, r in profile:
        for k in range(verts):
            a = k / verts * math.tau
            rr = r * (1 + rib_amp * abs(math.cos(a * ribs / 2))) if ribs else r
            vs.append(B(math.cos(a) * rr, y, math.sin(a) * rr))
    n = len(profile)
    for i in range(n - 1):
        for k in range(verts):
            a, b = i * verts + k, i * verts + (k + 1) % verts
            fs.append((a, b, b + verts, a + verts))
    me = bpy.data.meshes.new("lathe"); me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new("lathe", me); scene.collection.objects.link(ob)
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    activate(ob); bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    PROPS.append(ob)
    return ob


def lantern_parts(top, s=1.0):
    """Round red silk lantern hanging from `top` (game coords), about 0.6 m tall at s = 1."""
    x, y, z = top
    h, r = 0.5 * s, 0.25 * s
    prof = [(y - 0.06 * s - h * t, r * (0.45 + 0.55 * math.sin(t * math.pi))) for t in [k / 12 for k in range(13)]]
    parts = [lathe([(py, pr) for py, pr in prof], "lantern_silk", 24, 12, 0.05)]
    for p in parts:
        p.location = B(x, 0, z) - B(0, 0, 0)
        activate(p); bpy.ops.object.transform_apply(location=True)
    parts += [cyl((x, y, z), (x, y - 0.075 * s, z), 0.11 * s, "gold", 16), cyl((x, y - 0.06 * s - h, z), (x, y - 0.1 * s - h, z), 0.11 * s, "gold", 16)]
    parts.append(cyl((x, y - 0.1 * s - h, z), (x, y - 0.42 * s - h, z), 0.035 * s, "tassel", 8, 0.06 * s))
    return parts


def catenary(x0, x1, y, sag, n=24, z=0.0):
    return [(x0 + (x1 - x0) * t, y - sag * 4 * t * (1 - t), z) for t in [k / n for k in range(n + 1)]]


def span_poles(half, height):
    parts = []
    for sx in (-1, 1):
        parts += [cyl((sx * half, 0, 0), (sx * half, height, 0), 0.08, "pole_red", 12),
                  ball((sx * half, height + 0.08, 0), 0.13, "gold", 12), cyl((sx * half, 0, 0), (sx * half, 0.3, 0), 0.16, "gold", 12)]
    return parts


# ---------------------------------------------------------------- lantern (origin at the hanging point)
join(lantern_parts((0, 0, 0)), "lantern")

# ---------------------------------------------------------------- lantern span across a road (poles 14 m apart)
H, HALF = 6.6, 7.0
parts = span_poles(HALF, H + 0.4)
wire = catenary(-HALF, HALF, H, 0.9)
parts.append(tube(wire, 0.012, "wire"))
for k in range(1, 8):
    t = k / 8
    p = wire[round(t * 24)]
    parts.append(cyl(p, (p[0], p[1] - 0.25, p[2]), 0.006, "wire", 6))
    parts += lantern_parts((p[0], p[1] - 0.25, p[2]), 0.9)
join(parts, "lantern_span")

# ---------------------------------------------------------------- bunting: triangular pennants on a line
parts = span_poles(HALF, H + 0.4)
for row, (y0, sag) in enumerate(((H, 1.0), (H - 0.6, 1.3))):
    line = catenary(-HALF, HALF, y0, sag, 40)
    parts.append(tube(line, 0.008, "wire"))
    cols = ["pennant_red", "pennant_gold", "pennant_white", "pennant_orange"]
    for k in range(2, 39, 2):
        a, b = line[k], line[k + 1]
        tip = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.42, 0.0)
        me = bpy.data.meshes.new("pennant"); me.from_pydata([B(*a), B(*b), B(*tip)], [], [(0, 1, 2)])
        ob = bpy.data.objects.new("pennant", me); scene.collection.objects.link(ob)
        so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.004; apply_mods(ob)
        parts.append(settle(ob, cols[(k // 2 + row) % 4]))
join(parts, "bunting_span")

# ---------------------------------------------------------------- vertical banner for building fronts (6 m)
b = cloth(1.3, 6.0, "banner_v", 2, 0.05, (8, 24))
parts = [b, cyl((-0.75, 0.06, 0.02), (0.75, 0.06, 0.02), 0.04, "gold", 12), cyl((-0.75, -6.04, 0.02), (0.75, -6.04, 0.02), 0.04, "gold", 12)]
for sx in (-1, 1):
    parts += [ball((sx * 0.78, 0.06, 0.02), 0.06, "gold", 12), ball((sx * 0.78, -6.04, 0.02), 0.06, "gold", 12)]
    parts += lantern_parts((sx * 0.78, -6.1, 0.02), 0.45)
join(parts, "drop_banner")  # origin at the top rod; the game hangs it on a wall

# ---------------------------------------------------------------- horizontal banner across a road
parts = span_poles(HALF, 7.2)
parts.append(cyl((-HALF, 6.9, 0), (HALF, 6.9, 0), 0.02, "wire", 8))
hb = cloth(10.0, 1.3, "banner_h", 5, 0.08, (40, 6)); hb.location = B(0, 6.85, 0); activate(hb); bpy.ops.object.transform_apply(location=True)
parts.append(hb)
for sx in (-1, 1):
    parts.append(cyl((sx * 5.0, 6.85, 0), (sx * HALF, 6.9, 0), 0.01, "wire", 6))
join(parts, "road_banner")

# ---------------------------------------------------------------- the 「歡度國慶」 arch over a road (14 m wide, 10 m high)
parts = []
for sx in (-1, 1):
    parts += [box((sx * 7.2, 4.6, 0), (1.2, 9.2, 1.2), "pole_red", 0.05), box((sx * 7.2, 0.35, 0), (1.7, 0.7, 1.7), "gold", 0.1),
              box((sx * 7.2, 9.3, 0), (1.5, 0.3, 1.5), "gold", 0.15)]
    for y in (2.5, 5.0, 7.5):
        parts.append(box((sx * 7.2, y, 0), (1.26, 0.12, 1.26), "gold", 0.2))
parts += [box((0, 8.6, 0), (15.6, 0.7, 1.0), "pole_red", 0.05), box((0, 9.75, 0), (16.4, 0.35, 1.4), "gold", 0.1),
          box((0, 6.95, 0), (11.0, 2.5, 0.5), "gold", 0.04)]
parts.append(panel([(-5.2, 5.85, 0.26), (5.2, 5.85, 0.26), (5.2, 8.05, 0.26), (-5.2, 8.05, 0.26)], "arch_sign"))
parts.append(panel([(5.2, 5.85, -0.26), (-5.2, 5.85, -0.26), (-5.2, 8.05, -0.26), (5.2, 8.05, -0.26)], "arch_sign"))
for k in range(40):  # marquee bulbs around the sign and along the beam
    t = k / 39
    parts.append(ball((-5.45 + 10.9 * t, 8.3, 0.28), 0.06, "bulb", 8))
    parts.append(ball((-5.45 + 10.9 * t, 5.6, 0.28), 0.06, "bulb", 8))
    parts.append(ball((-7.8 + 15.6 * t, 9.95, 0.72), 0.07, "bulb_color", 8))
for sx in (-1, 1):
    for k in range(8):
        parts.append(ball((sx * 5.45, 5.6 + k * 0.385, 0.28), 0.06, "bulb", 8))
    for ox in (4.0, 6.2):
        parts += lantern_parts((sx * ox, 8.25, 0.0), 1.2)
join(parts, "arch")

# ---------------------------------------------------------------- stage with an LED wall
parts = [box((0, 0.6, 0), (12, 1.2, 7), "stage_floor", 0.02), box((0, 1.21, 0), (11.6, 0.02, 6.6), "carpet", 0)]
for k in range(4):  # front steps
    parts.append(box((0, 0.15 + k * 0.3, 3.5 + 0.35 * (4 - k)), (3.2, 0.3, 0.7), "stage_floor", 0.05))
parts += [box((0, 4.3, -3.3), (10.6, 6.2, 0.3), "speaker", 0.02),
          panel([(-5.0, 1.6, -3.14), (5.0, 1.6, -3.14), (5.0, 7.2, -3.14), (-5.0, 7.2, -3.14)], "screen")]
for sx in (-1, 1):  # truss towers and the top truss with spotlights
    for oz in (-3.3, 2.8):
        for c in ((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)):
            parts.append(cyl((sx * 6.2 + c[0], 0, oz + c[1]), (sx * 6.2 + c[0], 8.4, oz + c[1]), 0.035, "truss", 8))
        for y in [k * 0.7 for k in range(13)]:
            parts.append(box((sx * 6.2, y, oz), (0.55, 0.04, 0.55), "truss", 0))
    parts += [box((sx * 6.2, 1.6, 0.6), (1.1, 2.0, 0.9), "speaker", 0.06), box((sx * 6.2, 3.1, 0.6), (0.9, 1.0, 0.8), "speaker", 0.06)]
for oz in (-3.3, 2.8):
    for c in ((-0.25,), (0.25,)):
        for yy in (8.15, 8.65):
            parts.append(cyl((-6.2, yy, oz + c[0]), (6.2, yy, oz + c[0]), 0.035, "truss", 8))
for sx in (-1, 1):
    for c in (-0.25, 0.25):
        for yy in (8.15, 8.65):
            parts.append(cyl((sx * 6.2 + c, yy, -3.3), (sx * 6.2 + c, yy, 2.8), 0.035, "truss", 8))
for k in range(6):
    x = -4.5 + k * 1.8
    parts += [cyl((x, 8.0, 2.8), (x, 7.6, 3.0), 0.16, "speaker", 12, 0.2), cyl((x, 7.6, 3.0), (x, 7.58, 3.01), 0.17, "spot_lens", 12)]
join(parts, "stage")

# ---------------------------------------------------------------- red carpet (3 x 18 m, gold edges)
parts = [box((0, 0.012, 0), (3.0, 0.024, 18), "carpet", 0)]
for sx in (-1, 1):
    parts.append(box((sx * 1.45, 0.02, 0), (0.1, 0.03, 18), "gold", 0))
join(parts, "carpet")

# ---------------------------------------------------------------- night-market stall (3 m)
parts = [box((0, 0.5, 0.6), (2.9, 1.0, 0.7), "wood", 0.05), box((0, 1.03, 0.65), (3.0, 0.06, 0.85), "wood", 0.1),
         box((0, 1.4, -0.7), (2.9, 2.8, 0.1), "wood", 0.05)]
for sx in (-1, 1):
    for oz in (-0.7, 1.0):
        parts.append(box((sx * 1.4, 1.3, oz), (0.08, 2.6, 0.08), "metal", 0.1))
for k in range(10):  # striped awning sloping toward the street
    x0 = -1.6 + k * 0.32
    me = bpy.data.meshes.new("aw")
    me.from_pydata([B(x0, 2.75, -0.8), B(x0 + 0.32, 2.75, -0.8), B(x0 + 0.32, 2.3, 1.55), B(x0, 2.3, 1.55)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("aw", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.02; apply_mods(ob)
    parts.append(settle(ob, "awning_red" if k % 2 == 0 else "awning_white"))
    parts.append(cyl((x0 + 0.16, 2.3, 1.55), (x0 + 0.16, 2.12, 1.58), 0.16, "awning_red" if k % 2 == 0 else "awning_white", 3))  # scalloped edge
parts.append(box((0, 3.0, -0.75), (2.6, 0.55, 0.08), "wood", 0.1))
parts.append(panel([(-1.2, 2.77, -0.7), (1.2, 2.77, -0.7), (1.2, 3.23, -0.7), (-1.2, 3.23, -0.7)], "stall_sign"))
for k in range(9):
    parts.append(ball((-1.5 + k * 0.375, 2.08, 1.6), 0.05, "bulb", 8))
for k in range(4):  # pots and trays on the counter
    parts.append(cyl((-1.0 + k * 0.65, 1.06, 0.6), (-1.0 + k * 0.65, 1.2 + (k % 2) * 0.1, 0.6), 0.16, "metal", 14))
join(parts, "stall")

# ---------------------------------------------------------------- parade float (also the boss's float)
parts = [box((0, 0.9, 0), (2.8, 0.7, 6.4), "float_body", 0.05)]
for sx in (-1, 1):
    for oz in (-2.2, 2.2):
        parts.append(cyl((sx * 1.25, 0.45, oz), (sx * 1.5, 0.45, oz), 0.42, "tire", 18))
    for k in range(32):  # gold fringe skirt
        parts.append(box((sx * 1.42, 0.45, -3.1 + k * 0.2), (0.02, 0.5, 0.1), "fringe", 0))
for k in range(14):
    parts.append(box((-1.3 + k * 0.2, 0.45, 3.22), (0.1, 0.5, 0.02), "fringe", 0))
for k in range(26):  # mounds of red and gold flowers
    a = random.uniform(0, math.tau); r = random.uniform(0, 1)
    parts.append(ball((math.cos(a) * r * 1.1, 1.35 + random.uniform(0, 0.3), -1.5 + math.sin(a) * r * 1.6 + random.choice((0, 3))), random.uniform(0.25, 0.42),
                      random.choice(("flower_red", "flower_red", "flower_gold")), 10))
parts += lantern_parts((0, 4.6, 0.2), 3.0)
parts += [cyl((0, 1.3, 0.2), (0, 4.65, 0.2), 0.05, "gold", 10)]
for sx in (-1, 1):  # balloon arches over the deck
    pts = [(sx * 1.2, 1.2 + 2.2 * math.sin(t * math.pi), -3.0 + 6.0 * t) for t in [k / 14 for k in range(15)]]
    for k, p in enumerate(pts):
        parts.append(ball(p, (0.2, 0.24, 0.2), ("balloon_red", "balloon_gold", "balloon_white")[k % 3], 12))
join(parts, "parade_float")

# ---------------------------------------------------------------- firework mortar rack
parts = [box((0, 0.35, 0), (1.6, 0.7, 1.0), "wood", 0.05)]
for i in range(4):
    for j in range(3):
        x, z = -0.57 + i * 0.38, -0.32 + j * 0.32
        parts += [cyl((x, 0.7, z), (x, 1.25, z), 0.12, "paper_red", 14), cyl((x, 1.25, z), (x, 1.27, z), 0.125, "paper_gold", 14)]
parts.append(tube([(-0.8, 0.5, 0.52), (-0.2, 0.55, 0.6), (0.4, 0.5, 0.55), (0.9, 0.3, 0.7)], 0.01, "fuse"))
join(parts, "firework_rack")

# ---------------------------------------------------------------- firework crate (explodes when shot)
parts = [box((0, 0.33, 0), (0.95, 0.66, 0.7), "wood", 0.04), box((0.08, 0.7, -0.05), (0.97, 0.05, 0.72), "wood", 0.2, (0.0, 0.0, 0.18))]
for k in range(6):
    x = -0.32 + k * 0.13
    parts += [cyl((x, 0.5, 0.12), (x, 0.92, 0.12), 0.05, ("paper_red", "paper_gold")[k % 2], 10), cyl((x, 0.92, 0.12), (x, 1.0, 0.12), 0.006, "fuse", 6)]
parts.append(panel([(-0.36, 0.12, 0.352), (0.36, 0.12, 0.352), (0.36, 0.56, 0.352), (-0.36, 0.56, 0.352)], "crate_label"))
join(parts, "firework_crate")

# ---------------------------------------------------------------- balloon bunch
parts = [cyl((0, 0, 0), (0, 0.12, 0), 0.2, "gold", 16)]
for k in range(7):
    a = k / 7 * math.tau + random.uniform(-0.2, 0.2)
    top = (math.cos(a) * 0.35, 2.6 + random.uniform(-0.2, 0.4), math.sin(a) * 0.35)
    parts += [tube([(0, 0.12, 0), (top[0] * 0.5, 1.4, top[2] * 0.5), (top[0], top[1] - 0.22, top[2])], 0.004, "string"),
              ball(top, (0.2, 0.25, 0.2), ("balloon_red", "balloon_gold", "balloon_white", "balloon_red")[k % 4], 14)]
join(parts, "balloons")

# ---------------------------------------------------------------- tree wrapped in festive lights
parts = [cyl((0, 0, 0), (0, 2.0, 0), 0.14, "bark", 10, 0.1)]
for k, (y, r) in enumerate(((2.4, 1.3), (3.2, 1.05), (3.9, 0.75))):
    parts.append(ball((0, y, 0), (r, 0.75, r), "foliage", 14))
for k in range(70):
    t = k / 70; y = 1.9 + t * 2.4; r = 1.32 * (1 - t * 0.55)
    a = t * 6 * math.tau
    parts.append(ball((math.cos(a) * r, y, math.sin(a) * r), 0.05, "bulb" if k % 3 else "bulb_color", 6))
join(parts, "light_tree")

# ---------------------------------------------------------------- crowd barrier
parts = [cyl((-1.1, 1.05, 0), (1.1, 1.05, 0), 0.025, "metal", 8), cyl((-1.1, 0.25, 0), (1.1, 0.25, 0), 0.025, "metal", 8)]
for sx in (-1, 1):
    parts += [cyl((sx * 1.1, 0.05, 0), (sx * 1.1, 1.08, 0), 0.025, "metal", 8), box((sx * 1.0, 0.03, 0), (0.08, 0.04, 0.6), "metal", 0)]
for k in range(1, 14):
    x = -1.1 + k * 2.2 / 14
    parts.append(cyl((x, 0.25, 0), (x, 1.05, 0), 0.01, "metal", 6))
join(parts, "barrier")

for ob in scene.objects:
    ob.select_set(ob in PROPS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PROPS:
    print("  prop", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"arch": (0, 0, -6), "stage": (0, 0, -22), "parade_float": (-9, 0, 2), "stall": (8, 0, 2), "lantern_span": (0, 0, 6),
              "bunting_span": (0, 0, 12), "road_banner": (0, 0, 17), "carpet": (0, 0, -12), "firework_rack": (5, 0, -10),
              "firework_crate": (6.5, 0, -10), "balloons": (-5, 0, -10), "light_tree": (-9, 0, -8), "barrier": (3, 0, -2),
              "lantern": (2, 2.4, 2), "drop_banner": (11, 7, -8)}
    for ob in PROPS:
        x, y, z = layout.get(ob.name, (0, 0, 0))
        ob.location = B(x, y, z)
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    fl = bpy.context.object; fm = bpy.data.materials.new("floor"); fm.use_nodes = True
    fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1); fl.data.materials.append(fm)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.01, 0.012, 0.03, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 24
    eye, target = B(16, 9, 26), B(0, 3, -4)
    cam.location = eye; cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((10, 20, 15), 4000), ((-15, 10, 5), 1500)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 10; l.location = B(*loc)
        l.rotation_euler = (B(0, 0, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 48; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
