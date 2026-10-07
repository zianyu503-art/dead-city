# Airport props for level 11 (國際機場) of 死城突圍.
#
#   blender -b -P tools/blender/airport.py -- assets/models/airport.glb [preview.png]
#
# Every prop stands on its own origin (base centre on the ground), its nose / front toward +Z,
# written in game coordinates (+Y up, +Z forward, metres); B() converts to Blender.
# Material names are keys the game maps to its own materials. "terminal_sign" carries UVs that
# cover the panel, so the game can paint 「出境 DEPARTURES」 onto it.
#
# The cargo plane is the level's escape: its ramp foot is at (0, 0, RAMP_Z) and its four
# propellers are separate ("cargo_prop", hub at the origin) so the game can spin them.
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "airport.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(11)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PROPS = []

PALETTE = {
    "plane_white": ((0.82, 0.83, 0.85), 0.35, 0.1), "plane_blue": ((0.04, 0.12, 0.35), 0.4, 0.1), "plane_red": ((0.6, 0.05, 0.04), 0.4, 0.1),
    "window_dark": ((0.02, 0.025, 0.03), 0.1, 0.5), "engine_grey": ((0.45, 0.46, 0.48), 0.3, 0.8), "metal": ((0.3, 0.31, 0.33), 0.4, 0.8),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0), "military": ((0.25, 0.28, 0.27), 0.6, 0.2), "interior": ((0.05, 0.05, 0.05), 0.9, 0.0),
    "concrete": ((0.55, 0.54, 0.5), 0.9, 0.0), "glass": ((0.1, 0.18, 0.22), 0.05, 0.6), "steel": ((0.55, 0.57, 0.6), 0.35, 0.9),
    "roof": ((0.35, 0.36, 0.38), 0.5, 0.6), "terminal_sign": ((0.1, 0.1, 0.12), 0.5, 0.0), "yellow": ((0.8, 0.6, 0.05), 0.5, 0.1),
    "tug_blue": ((0.08, 0.2, 0.45), 0.5, 0.2), "luggage": ((0.3, 0.2, 0.1), 0.8, 0.0), "lamp": ((1.0, 0.9, 0.6), 0.3, 0.0),
    "lamp_blue": ((0.3, 0.5, 1.0), 0.3, 0.0), "orange": ((0.85, 0.35, 0.05), 0.6, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if n.startswith("lamp"):
        b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 5
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


def settle(ob, mat, angle=40):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    return ob


def box(c, s, mat, bev=0.05, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    settle(ob, mat)
    if bev:
        bv = ob.modifiers.new("b", "BEVEL"); bv.width = min(s) * bev; bv.segments = 1; apply_mods(ob)
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


def lathe_z(prof, mat, n=24, cy=0.0, squash=1.0, name="hull"):
    """A hull turned around a line parallel to +Z at height cy: prof = [(z, radius, dy)] (dy lifts that ring)."""
    vs, fs = [], []
    for z, r, dy in prof:
        for k in range(n):
            a = k / n * math.tau
            vs.append(B(math.cos(a) * r, cy + dy + math.sin(a) * r * squash, z))
    for i in range(len(prof) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            fs.append((a, b, b + n, a + n))
    for end in (0, len(prof) - 1):  # cap the ends
        c = len(vs); z, r, dy = prof[end]; vs.append(B(0, cy + dy, z))
        for k in range(n):
            a, b = end * n + k, end * n + (k + 1) % n
            fs.append((c, b, a) if end == 0 else (c, a, b))
    me = bpy.data.meshes.new(name); me.from_pydata(vs, [], fs); me.validate()
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    return settle(ob, mat, 50)


def slab(pts, y, t, mat):
    """A flat plate (wing, fin) from an outline in the XZ plane at height y, thickness t."""
    me = bpy.data.meshes.new("slab"); me.from_pydata([B(x, y, z) for x, z in pts], [], [list(range(len(pts)))])
    ob = bpy.data.objects.new("slab", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = t; so.offset = 0; apply_mods(ob)
    return settle(ob, mat, 30)


def fin(pts, x, t, mat):
    """A vertical plate from an outline in the ZY plane at x."""
    me = bpy.data.meshes.new("fin"); me.from_pydata([B(x, y, z) for z, y in pts], [], [list(range(len(pts)))])
    ob = bpy.data.objects.new("fin", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = t; so.offset = 0; apply_mods(ob)
    return settle(ob, mat, 30)


def panel(corners, mat, name="panel"):
    me = bpy.data.meshes.new(name); me.from_pydata([B(*c) for c in corners], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, l in enumerate(me.loops):
        uv.data[i].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[l.vertex_index]
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    ob.data.materials.append(MAT[mat])
    return ob


def wheel(c, r, w, mat="tire"):
    return cyl((c[0] - w / 2, c[1], c[2]), (c[0] + w / 2, c[1], c[2]), r, mat, 14)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PROPS.append(ob)
    return ob


# ===================================================================== airliner (36 m, nose +Z)
FY = 3.3  # fuselage axis height
prof = [(18.0, 0.05, -0.3), (17.6, 0.9, -0.25), (16.8, 1.55, -0.1), (15.6, 1.95, 0), (13, 2.05, 0), (-9, 2.05, 0), (-13, 1.7, 0.35), (-16, 1.0, 0.9), (-17.6, 0.35, 1.3)]
parts = [lathe_z(prof, "plane_white", 28, FY)]
parts.append(lathe_z([(z, r * 1.006, dy) for z, r, dy in prof[3:6]], "plane_blue", 28, FY, 0.18, "stripe"))  # thin belly-line stripe band
for s in (-1, 1):  # window rows and cheatline
    parts.append(box((s * 2.03, FY + 0.55, -0.5), (0.04, 0.32, 26), "window_dark", 0))
    parts.append(box((s * 2.03, FY - 0.15, -0.5), (0.04, 0.22, 28), "plane_blue", 0))
    parts.append(box((s * 2.0, FY + 0.1, 12.8), (0.08, 1.7, 0.9), "metal", 0))  # door
parts.append(lathe_z([(16.9, 1.2, 0.55), (16.3, 1.5, 0.45), (15.9, 1.6, 0.35)], "window_dark", 20, FY, 0.35, "cockpit"))
wing = [(0, 4), (17, -3.5), (17, -5.5), (2.2, -2.5), (-2.2, -2.5), (-17, -5.5), (-17, -3.5)]
parts.append(slab(wing, FY - 1.2, 0.4, "plane_white"))
for s in (-1, 1):
    parts += [cyl((s * 6.2, FY - 2.2, 3.4), (s * 6.2, FY - 2.2, -0.6), 1.05, "engine_grey", 20), cyl((s * 6.2, FY - 2.2, 3.45), (s * 6.2, FY - 2.2, 3.4), 0.85, "window_dark", 20),
              box((s * 6.2, FY - 1.55, 1.3), (0.3, 0.7, 2.6), "plane_white", 0.1),
              box((s * 16.8, FY - 0.6, -4.6), (0.15, 1.2, 1.2), "plane_white", 0.1)]                                   # winglets
parts.append(fin([(-11.5, FY + 1.7), (-16.5, FY + 9.5), (-18.2, FY + 9.5), (-17.6, FY + 1.2)], 0, 0.35, "plane_blue"))
parts.append(fin([(-16.3, FY + 6.5), (-17.3, FY + 8.5), (-17.9, FY + 8.5), (-17.6, FY + 6.0)], 0, 0.4, "plane_red"))   # tail logo
parts.append(slab([(0, -13.8), (6.2, -17.2), (6.2, -18.2), (0, -17.6), (-6.2, -18.2), (-6.2, -17.2)], FY + 1.2, 0.25, "plane_white"))
parts += [cyl((0, 0, 14.5), (0, FY - 1.8, 14.5), 0.12, "metal", 8), wheel((0, 0.45, 14.5), 0.45, 0.4)]
for s in (-1, 1):
    parts += [cyl((s * 2.8, 0, -0.8), (s * 2.8, FY - 1.6, -0.8), 0.18, "metal", 8), wheel((s * 2.8, 0.6, -0.4), 0.6, 0.5), wheel((s * 2.8, 0.6, -1.3), 0.6, 0.5)]
join(parts, "airliner")

# ===================================================================== cargo plane (30 m, high wing, ramp down at the rear)
CY = 3.0
RAMP_Z = -19.5
prof = [(15.5, 0.1, -0.5), (15.0, 1.3, -0.35), (13.8, 2.1, -0.1), (12.5, 2.35, 0), (-9, 2.35, 0), (-12, 2.0, 0.6), (-15.5, 1.1, 1.8)]
hull = lathe_z(prof, "military", 28, CY)
parts = [hull]
parts.append(lathe_z([(14.2, 1.7, 0.75), (13.6, 1.95, 0.6), (13.2, 2.05, 0.5)], "window_dark", 20, CY, 0.3, "cockpit"))
parts.append(box((0, CY - 1.3, -11.2), (3.8, 2.2, 1.6), "interior", 0))  # dark cargo hold seen up the ramp
TOP_Y, TOP_Z = CY - 2.1, -10.4
me = bpy.data.meshes.new("ramp")
me.from_pydata([B(-1.75, TOP_Y, TOP_Z), B(1.75, TOP_Y, TOP_Z), B(1.75, 0.05, RAMP_Z), B(-1.75, 0.05, RAMP_Z)], [], [(0, 1, 2, 3)])
ramp = bpy.data.objects.new("ramp", me); scene.collection.objects.link(ramp)
so = ramp.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.22; apply_mods(ramp)
parts.append(settle(ramp, "metal", 20))
for k in range(9):  # treads on the ramp
    t = (k + 0.5) / 9
    parts.append(box((0, TOP_Y + (0.05 - TOP_Y) * t + 0.05, TOP_Z + (RAMP_Z - TOP_Z) * t), (3.3, 0.06, 0.12), "engine_grey", 0))
for s in (-1, 1):  # hydraulic struts holding the ramp
    parts.append(cyl((s * 1.6, CY - 0.6, -10.6), (s * 1.6, 0.6, -14.5), 0.07, "metal", 8))
wing = [(-18.5, 1.5), (18.5, 1.5), (18.5, -2.2), (-18.5, -2.2)]
parts.append(slab(wing, CY + 2.45, 0.45, "military"))
for x in (-9.5, -5.0, 5.0, 9.5):
    parts += [cyl((x, CY + 1.9, 3.3), (x, CY + 1.9, -2.6), 0.75, "military", 18), cyl((x, CY + 1.9, 3.4), (x, CY + 1.9, 3.9), 0.35, "engine_grey", 14, 0.08)]
parts.append(fin([(-10.5, CY + 2.2), (-14.6, CY + 9.2), (-16.4, CY + 9.2), (-15.4, CY + 2.6)], 0, 0.4, "military"))
parts.append(slab([(0, -12.8), (7, -14.6), (7, -16.4), (0, -16.0), (-7, -16.4), (-7, -14.6)], CY + 2.6, 0.3, "military"))
for s in (-1, 1):  # landing gear sponsons and wheels
    parts += [box((s * 2.2, 1.0, 0.0), (1.0, 1.4, 5.5), "military", 0.15), wheel((s * 2.35, 0.55, 1.2), 0.55, 0.45), wheel((s * 2.35, 0.55, -1.2), 0.55, 0.45)]
parts += [cyl((0, 0, 12.0), (0, CY - 2.0, 12.0), 0.12, "metal", 8), wheel((0, 0.45, 12.0), 0.45, 0.4)]
for k in range(5):  # round windows along the crew door
    parts.append(cyl((2.33, CY + 0.6, 11 - k * 1.4), (2.38, CY + 0.6, 11 - k * 1.4), 0.18, "window_dark", 12))
join(parts, "cargo_plane")
blade = []
for k in range(4):
    a = k / 4 * math.tau + 0.3
    blade.append(box((math.cos(a) * 1.0, math.sin(a) * 1.0, 0), (0.16, 1.9, 0.04), "tire", 0.2, (0, 0, -a + math.pi / 2)))
blade.append(ball((0, 0, 0.1), (0.25, 0.25, 0.3), "engine_grey", 12))
join(blade, "cargo_prop")

# ===================================================================== control tower (28 m)
parts = [cyl((0, 0, 0), (0, 21, 0), 2.6, "concrete", 20, 2.0)]
for y in range(2, 21, 3):
    parts.append(cyl((0, y, 0), (0, y + 0.15, 0), 2.7 - y * 0.03, "metal", 20))
parts += [cyl((0, 21, 0), (0, 22, 0), 4.2, "concrete", 8), cyl((0, 22, 0), (0, 25.2, 0), 4.6, "glass", 8, 4.9),
          cyl((0, 25.2, 0), (0, 26, 0), 5.1, "metal", 8), cyl((0, 26, 0), (0, 26.6, 0), 3.0, "concrete", 8),
          cyl((0, 26.6, 0), (0, 31, 0), 0.08, "metal", 6), ball((0, 31, 0), 0.25, "plane_red", 8)]
for k in range(8):  # mullions
    a = (k + 0.5) / 8 * math.tau
    parts.append(cyl((math.cos(a) * 4.5, 22, math.sin(a) * 4.5), (math.cos(a) * 4.85, 25.2, math.sin(a) * 4.85), 0.08, "metal", 6))
join(parts, "tower")

# ===================================================================== terminal (38 x 14 m, glass front toward +Z)
parts = [box((0, 0.6, 0), (38, 1.2, 14), "concrete", 0.01), box((0, 6.5, -1.5), (37.6, 10.6, 11), "concrete", 0.01),
         box((0, 5.6, 5.6), (37.4, 8.8, 0.3), "glass", 0)]
for k in range(20):  # glass wall mullions
    x = -18.5 + k * (37 / 19)
    parts.append(box((x, 5.6, 5.8), (0.18, 8.8, 0.3), "steel", 0))
for y in (3.2, 6.4):
    parts.append(box((0, y, 5.8), (37.4, 0.16, 0.32), "steel", 0))
# a gently curved roof overhanging the glass front
n = 14
for k in range(n):
    z0, z1 = -7.5 + k * (16.5 / n), -7.5 + (k + 1) * (16.5 / n)
    y0, y1 = 11.2 + 1.2 * math.sin(k / n * math.pi), 11.2 + 1.2 * math.sin((k + 1) / n * math.pi)
    parts.append(slab([(-19.5, z0), (19.5, z0), (19.5, z1), (-19.5, z1)], (y0 + y1) / 2, 0.35, "roof"))
for k in range(5):  # roof columns in front of the glass
    parts.append(cyl((-16 + k * 8, 0, 8.4), (-16 + k * 8, 11.4, 8.4), 0.3, "steel", 12))
sign = panel([(-8, 9.6, 5.98), (8, 9.6, 5.98), (8, 11.0, 5.98), (-8, 11.0, 5.98)], "terminal_sign", "sign")
parts += [box((0, 10.3, 5.85), (16.6, 1.8, 0.2), "steel", 0), sign]
join(parts, "terminal")

# ===================================================================== jet bridge (origin at the terminal end, reaching +Z 16 m)
parts = [cyl((0, 0, 1.5), (0, 7.4, 1.5), 1.6, "steel", 16), box((0, 5.3, 9.0), (2.8, 2.9, 14.5), "steel", 0.03)]
for k in range(8):  # corrugated sides
    parts.append(box((0, 5.3, 2.4 + k * 1.75), (2.9, 3.0, 0.12), "metal", 0))
parts += [box((0, 5.3, 16.6), (3.6, 3.2, 1.6), "steel", 0.05),
          box((0, 3.9, 16.6), (3.8, 0.3, 1.8), "tire", 0)]
parts += [cyl((-0.9, 0, 12.5), (-0.9, 3.9, 12.5), 0.22, "metal", 10), cyl((0.9, 0, 12.5), (0.9, 3.9, 12.5), 0.22, "metal", 10),
          box((0, 0.6, 12.5), (2.6, 0.5, 1.0), "yellow", 0.1), wheel((-1.1, 0.45, 12.5), 0.45, 0.4), wheel((1.1, 0.45, 12.5), 0.45, 0.4)]
join(parts, "jet_bridge")

# ===================================================================== hangar (30 x 26 m arched roof, open toward +Z)
parts = []
n = 18
for k in range(n):  # arch made of panels
    a0, a1 = k / n * math.pi, (k + 1) / n * math.pi
    x0, y0 = -math.cos(a0) * 15, math.sin(a0) * 12.5
    x1, y1 = -math.cos(a1) * 15, math.sin(a1) * 12.5
    me = bpy.data.meshes.new("arch"); me.from_pydata([B(x0, y0, -13), B(x1, y1, -13), B(x1, y1, 13), B(x0, y0, 13)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("arch", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.25; apply_mods(ob)
    parts.append(settle(ob, "roof", 20))
for z in (-13, -4.3, 4.3, 13):  # steel ribs
    for k in range(n):
        a0, a1 = k / n * math.pi, (k + 1) / n * math.pi
        parts.append(cyl((-math.cos(a0) * 15.15, math.sin(a0) * 12.65, z), (-math.cos(a1) * 15.15, math.sin(a1) * 12.65, z), 0.18, "steel", 6))
back = []
for k in range(n):
    a0, a1 = k / n * math.pi, (k + 1) / n * math.pi
    back.append((-math.cos(a0) * 15, math.sin(a0) * 12.5))
back.append((15, 0))
me = bpy.data.meshes.new("back"); me.from_pydata([B(x, y, -12.9) for x, y in back], [], [list(range(len(back)))])
ob = bpy.data.objects.new("back", me); scene.collection.objects.link(ob)
parts.append(settle(ob, "interior", 20))
parts.append(box((0, 0.05, 0), (29.6, 0.1, 25.8), "concrete", 0))
parts.append(box((0, 11.6, 12.8), (8, 1.2, 0.3), "yellow", 0.05))  # hangar number board
join(parts, "hangar")

# ===================================================================== light aircraft (8 m, high wing)
prof = [(3.6, 0.05, 0.05), (3.3, 0.55, 0.05), (2.0, 0.65, 0.1), (-0.5, 0.6, 0.15), (-3.6, 0.15, 0.55)]
parts = [lathe_z(prof, "plane_white", 16, 1.3)]
parts += [slab([(-5.5, 1.0), (5.5, 1.0), (5.5, -0.4), (-5.5, -0.4)], 2.05, 0.12, "plane_white"),
          box((0, 1.65, 1.2), (1.1, 0.6, 1.4), "window_dark", 0.1),
          fin([(-2.6, 1.6), (-3.4, 3.1), (-3.9, 3.1), (-3.7, 1.6)], 0, 0.1, "plane_red"),
          slab([(0, -3.0), (1.8, -3.6), (1.8, -4.0), (-1.8, -4.0), (-1.8, -3.6)], 1.75, 0.08, "plane_white"),
          box((0, 1.3, 3.75), (0.08, 1.7, 0.12), "tire", 0)]
for s in (-1, 1):
    parts += [cyl((s * 1.0, 0.35, 0.6), (s * 0.45, 1.0, 0.6), 0.04, "metal", 6), wheel((s * 1.0, 0.3, 0.6), 0.3, 0.2),
              cyl((s * 0.6, 1.4, 0.4), (s * 2.8, 2.0, 0.3), 0.03, "metal", 6)]
parts.append(wheel((0, 0.25, 2.8), 0.25, 0.15))
join(parts, "light_plane")

# ===================================================================== baggage train: tug and three carts (10 m)
parts = [box((0, 0.75, 4.2), (1.6, 0.8, 2.2), "tug_blue", 0.1), box((0, 1.5, 3.8), (1.4, 0.8, 1.0), "window_dark", 0.1),
         box((0, 1.95, 3.8), (1.5, 0.08, 1.2), "tug_blue", 0)]
for z in (4.9, 3.5):
    for s in (-1, 1):
        parts.append(wheel((s * 0.75, 0.3, z), 0.3, 0.22))
for k in range(3):
    z = 1.6 - k * 2.6
    parts += [box((0, 0.65, z), (1.5, 0.08, 2.2), "metal", 0), cyl((0, 0.5, z + 1.1), (0, 0.5, z + 1.6), 0.03, "metal", 6)]
    for s in (-1, 1):
        parts += [wheel((s * 0.7, 0.25, z + 0.7), 0.25, 0.15), wheel((s * 0.7, 0.25, z - 0.7), 0.25, 0.15),
                  cyl((s * 0.72, 0.65, z + 1.05), (s * 0.72, 1.7, z + 1.05), 0.03, "metal", 6), cyl((s * 0.72, 0.65, z - 1.05), (s * 0.72, 1.7, z - 1.05), 0.03, "metal", 6)]
    parts.append(box((0, 1.72, z), (1.55, 0.05, 2.2), "orange", 0))
    for j in range(5):  # suitcases
        parts.append(box((random.uniform(-0.4, 0.4), 0.95 + random.uniform(0, 0.4), z + random.uniform(-0.7, 0.7)),
                         (random.uniform(0.35, 0.55), random.uniform(0.25, 0.4), random.uniform(0.5, 0.7)), random.choice(("luggage", "plane_blue", "plane_red", "tire")), 0.15))
join(parts, "baggage_train")

# ===================================================================== stairs truck (7 m)
parts = [box((0, 0.9, 2.4), (2.0, 1.2, 2.2), "plane_white", 0.08), box((0, 1.75, 2.6), (1.9, 0.7, 1.4), "window_dark", 0.08),
         box((0, 0.6, -0.6), (2.0, 0.4, 4.4), "metal", 0)]
for z in (2.6, -1.8):
    for s in (-1, 1):
        parts.append(wheel((s * 1.0, 0.45, z), 0.45, 0.35))
for k in range(14):  # stairs rising toward +Z... from the back
    parts.append(box((0, 0.95 + k * 0.28, -2.6 + k * 0.32), (1.3, 0.06, 0.34), "steel", 0))
for s in (-1, 1):
    parts += [cyl((s * 0.68, 1.0, -2.7), (s * 0.68, 5.0, 1.8), 0.05, "yellow", 8), cyl((s * 0.68, 2.0, -2.7), (s * 0.68, 6.0, 1.8), 0.04, "yellow", 8)]
parts.append(box((0, 4.9, 2.2), (1.5, 0.1, 1.2), "steel", 0))
join(parts, "stairs_truck")

# ===================================================================== runway edge light
join([cyl((0, 0, 0), (0, 0.32, 0), 0.05, "yellow", 8), cyl((0, 0.32, 0), (0, 0.44, 0), 0.09, "lamp", 10)], "runway_light")
join([cyl((0, 0, 0), (0, 0.32, 0), 0.05, "yellow", 8), cyl((0, 0.32, 0), (0, 0.44, 0), 0.09, "lamp_blue", 10)], "taxi_light")

for ob in scene.objects:
    ob.select_set(ob in PROPS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PROPS:
    print("  prop", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"airliner": (-22, 0, 10, 0.6), "cargo_plane": (20, 0, 8, -0.5), "tower": (-45, 0, -30, 0), "terminal": (0, 0, -40, 0),
              "jet_bridge": (-8, 0, -33, 0), "hangar": (45, 0, -38, -0.3), "light_plane": (36, 0, -18, 0.8), "baggage_train": (0, 0, 22, 1.2),
              "stairs_truck": (-8, 0, 24, 0.4), "runway_light": (6, 0, 30, 0), "taxi_light": (8, 0, 30, 0), "cargo_prop": (20, 5, 25, 0)}
    for ob in PROPS:
        x, y, z, r = layout.get(ob.name, (0, 0, 0, 0))
        ob.location = B(x, y, z); ob.rotation_euler = (0, 0, r)
    bpy.ops.mesh.primitive_plane_add(size=300, location=(0, 0, 0))
    fl = bpy.context.object; fl.data.materials.append(MAT["concrete"])
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.42, 0.38, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(60), 0, math.radians(40))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 24; eye, tgt = B(10, 35, 75), B(0, 4, -5)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
