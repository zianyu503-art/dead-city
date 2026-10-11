# The aircraft carrier of level 12 (航空母艦) and its sea monster, for 死城突圍.
#
#   blender -b -P tools/blender/carrier.py -- assets/models/carrier.glb [preview.png]
#
# Game coordinates (+Y up, +Z toward the bow, metres; B() converts to Blender). The flight deck is
# the plane y = 0 that the player walks on: the hull hangs below it down past the waterline (y -16).
# Props stand on their own origin, front toward +Z. The kraken pieces face +Z too; the game turns
# them toward the deck. "radar" spins about its origin; "kraken_eye" is the weak point.
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "carrier.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(77)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PROPS = []

PALETTE = {
    "deck": ((0.09, 0.095, 0.1), 0.95, 0.1), "hull": ((0.32, 0.34, 0.36), 0.6, 0.3), "boot": ((0.35, 0.06, 0.05), 0.6, 0.1),
    "line_white": ((0.85, 0.85, 0.82), 0.8, 0.0), "line_yellow": ((0.8, 0.6, 0.08), 0.8, 0.0), "track": ((0.25, 0.26, 0.27), 0.4, 0.8),
    "island": ((0.38, 0.4, 0.42), 0.6, 0.3), "window": ((0.02, 0.03, 0.04), 0.1, 0.6), "metal": ((0.3, 0.31, 0.33), 0.4, 0.8),
    "jet_grey": ((0.42, 0.45, 0.48), 0.5, 0.3), "canopy": ((0.15, 0.13, 0.05), 0.05, 0.7), "tire": ((0.02, 0.02, 0.02), 0.9, 0.0),
    "yellow": ((0.75, 0.55, 0.05), 0.5, 0.1), "red": ((0.6, 0.05, 0.04), 0.5, 0.1), "olive": ((0.2, 0.22, 0.14), 0.7, 0.1),
    "crate": ((0.28, 0.3, 0.2), 0.8, 0.0), "net": ((0.15, 0.15, 0.13), 0.9, 0.0), "lamp_red": ((1.0, 0.1, 0.05), 0.3, 0.0),
    "kraken_skin": ((0.18, 0.06, 0.12), 0.45, 0.1), "kraken_belly": ((0.45, 0.2, 0.22), 0.5, 0.0), "kraken_eye": ((1.0, 0.75, 0.1), 0.2, 0.0),
    "kraken_pupil": ((0.02, 0.0, 0.0), 0.2, 0.0), "sucker": ((0.6, 0.35, 0.35), 0.5, 0.0), "beak": ((0.1, 0.08, 0.06), 0.3, 0.2),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if n in ("lamp_red", "kraken_eye"):
        b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 4
    MAT[n] = m


def B(x, y, z):
    return Vector((x, -z, y))


def G(v):
    return Vector((v.x, v.z, -v.y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def apply_mods(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def settle(ob, mat, angle=40, smooth=True):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
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


def plate(pts, y, t, mat, smooth=False):
    """A flat outline in the XZ plane at height y (top face), thickness t downward."""
    vs = [B(x, y, z) for x, z in pts]
    if sum(a.x * b.y - b.x * a.y for a, b in zip(vs, vs[1:] + vs[:1])) < 0:
        vs.reverse()  # wind it counter-clockwise so the face points up and the solidify grows down
    me = bpy.data.meshes.new("plate"); me.from_pydata(vs, [], [list(range(len(vs)))])
    ob = bpy.data.objects.new("plate", me); scene.collection.objects.link(ob)
    if t:
        so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = t; so.offset = -1; apply_mods(ob)
    return settle(ob, mat, 20, smooth)


def loft(rings, mat):
    """Hull from stacked outlines: rings = [(y, [(x, z), ...])], all with the same point count."""
    n = len(rings[0][1]); vs, fs = [], []
    for y, pts in rings:
        vs += [B(x, y, z) for x, z in pts]
    for i in range(len(rings) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            fs.append((a, b, b + n, a + n))
    me = bpy.data.meshes.new("loft"); me.from_pydata(vs, [], fs); me.validate()
    ob = bpy.data.objects.new("loft", me); scene.collection.objects.link(ob)
    return settle(ob, mat, 30)


def text(s, c, size, mat, rot=(0, 0, 0)):
    bpy.ops.object.text_add(location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.data.body = s; ob.data.size = size; ob.data.extrude = 0.02
    ob.data.align_x = "CENTER"; ob.data.align_y = "CENTER"
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat, 20, False)


def tube(pts, r, mat, radii=None):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 3; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PROPS.append(ob)
    return ob


# ===================================================================== hull and flight deck
DECK = [(-34, -128), (34, -128), (38, -112), (38, 92), (30, 116), (16, 128), (-16, 128), (-30, 116), (-40, 92), (-42, 30), (-42, -20), (-38, -112)]
parts = [plate(DECK, 0, 1.6, "deck")]
def shrink(pts, k, dz=0):
    return [(x * k, z * (0.97 if k < 1 else 1) + dz) for x, z in pts]
parts.append(loft([(-1.6, DECK), (-6, shrink(DECK, 0.94)), (-12, shrink(DECK, 0.82, 4)), (-15.2, shrink(DECK, 0.74, 8))], "hull"))
parts.append(loft([(-15.2, shrink(DECK, 0.74, 8)), (-17.5, shrink(DECK, 0.7, 10))], "boot"))  # red boot-top at the waterline
parts.append(text("77", (0, -6, 128.6), 6, "line_white", (math.pi / 2, 0, math.pi)))           # hull number on the bow
join(parts, "carrier_hull")

# ===================================================================== deck markings and catapult tracks
parts = []
for z in range(-120, 120, 8):  # centre line
    parts.append(box((0, 0.02, z), (0.5, 0.02, 4), "line_white", 0))
ang = math.radians(9)
for off in (-11, 11):  # the angled landing area, edged in yellow
    a = Vector((-6 + off, 0, -126)); d = Vector((-math.sin(ang), 0, math.cos(ang)))
    for k in range(0, 150, 6):
        p = a + d * k
        if p.x < -40:
            break
        parts.append(box((p.x, 0.025, p.z), (0.35, 0.02, 3.6), "line_yellow", 0, (0, -ang, 0)))
for x in (-8, 8):  # bow catapults
    parts.append(box((x, 0.03, 85), (0.5, 0.04, 80), "track", 0))
    for z in (48, 122):
        parts.append(box((x, 0.03, z), (2.2, 0.03, 0.6), "line_yellow", 0))
for z in (-100, -94, -88, -82):  # arresting wires
    parts.append(cyl((-26, 0.08, z), (18, 0.08, z + 6), 0.05, "metal", 6))
parts.append(text("77", (0, 0.05, 104), 14, "line_white", (0, 0, math.pi)))
join(parts, "deck_lines")

# ===================================================================== the island (starboard superstructure), centred on its origin
parts = [box((0, 6, 0), (8, 12, 40), "island", 0.02), box((0, 14, 4), (7, 6, 24), "island", 0.02), box((0, 19.5, 6), (6.4, 5, 14), "island", 0.02)]
for y, z0, z1 in ((10, -18, 18), (16, -7, 15), (21, 0, 12.5)):  # bridge windows on both faces
    for s in (-1, 1):
        parts.append(box((s * (4.02 if y < 12 else 3.52 if y < 18 else 3.22), y, (z0 + z1) / 2), (0.05, 1.1, z1 - z0), "window", 0))
parts += [cyl((0, 22, 6), (0, 36, 6), 0.35, "metal", 10), box((0, 30, 6), (5, 0.3, 0.3), "metal", 0), box((0, 33.5, 6), (3.5, 0.25, 0.25), "metal", 0),
          ball((0, 36.2, 6), 0.3, "lamp_red", 8), box((0, 23.5, -1), (3, 3, 5), "island", 0.05)]
for s in (-1, 1):
    parts.append(text("77", (s * 4.1, 14, -6), 4, "line_white", (math.pi / 2, 0, s * math.pi / 2)))
join(parts, "island")
join([box((0, 0, 0), (3.2, 1.6, 0.25), "metal", 0.1), cyl((0, -0.6, 0.2), (0, -0.2, 0.2), 0.12, "metal", 8)], "radar")

# ===================================================================== a fighter jet (17 m)
FY = 2.2
parts = [tube([(0, FY, 8.5), (0, FY + 0.15, 5), (0, FY + 0.2, 0), (0, FY + 0.1, -6), (0, FY + 0.1, -8.4)], 0.85, "jet_grey", [0.15, 0.85, 1.0, 1.0, 0.7])]
parts.append(ball((0, FY + 0.75, 4.2), (0.55, 0.45, 1.7), "canopy", 16))
parts.append(plate([(0, 3.5), (6.2, -2.6), (6.2, -4.2), (1.2, -3.5), (-1.2, -3.5), (-6.2, -4.2), (-6.2, -2.6)], FY - 0.1, 0.18, "jet_grey"))
parts.append(plate([(0, -5.5), (3.4, -7.8), (3.4, -8.6), (-3.4, -8.6), (-3.4, -7.8)], FY, 0.12, "jet_grey"))
for s in (-1, 1):
    me = bpy.data.meshes.new("tail"); me.from_pydata([B(s * 1.0, FY + 0.6, -5.2), B(s * 1.6, FY + 3.6, -7.6), B(s * 1.6, FY + 3.6, -8.6), B(s * 1.0, FY + 0.6, -8.4)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("tail", me); scene.collection.objects.link(ob); so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.1; apply_mods(ob)
    parts.append(settle(ob, "jet_grey", 20, False))
    parts += [cyl((s * 0.6, FY - 0.1, -8.4), (s * 0.6, FY - 0.1, -9.0), 0.5, "metal", 14, 0.45),
              box((s * 1.3, FY - 0.15, 2.0), (0.7, 0.8, 3.5), "jet_grey", 0.1),                                     # intakes
              cyl((s * 1.6, 0, -1.0), (s * 1.6, FY - 0.6, -1.0), 0.09, "metal", 6), cyl((s * 1.75, 0.38, -1.0), (s * 1.45, 0.38, -1.0), 0.38, "tire", 12)]
parts += [cyl((0, 0, 6.5), (0, FY - 0.6, 6.5), 0.09, "metal", 6), cyl((0.15, 0.3, 6.5), (-0.15, 0.3, 6.5), 0.3, "tire", 12)]
join(parts, "jet")

# ===================================================================== deck gear
join([box((0, 0.55, 0), (2.0, 0.8, 3.2), "yellow", 0.1), box((0, 1.2, -0.6), (1.6, 0.6, 1.2), "yellow", 0.1)]
     + [cyl((s * 1.05, 0.38, z), (s * 0.85, 0.38, z), 0.38, "tire", 12) for s in (-1, 1) for z in (1.0, -1.0)], "tug")
parts = [box((0, 0.45, 0), (1.6, 0.15, 3.0), "metal", 0.1)]
for k in range(3):
    parts += [cyl((0, 0.8, -1.2 + k * 0.05), (0, 0.8, 1.2 + k * 0.05), 0.22, "olive", 12), cyl((0, 0.8, 1.25), (0, 0.8, 1.6), 0.22, "olive", 12, 0.02)]
    parts[-2].location = parts[-2].location  # keep
parts += [cyl((s * 0.7, 0.2, z), (s * 0.5, 0.2, z), 0.2, "tire", 10) for s in (-1, 1) for z in (1.0, -1.0)]
join(parts, "bomb_cart")
join([box((0, 0.6, 0), (2.4, 1.2, 1.6), "crate", 0.05), box((0, 0.6, 0), (2.42, 0.1, 1.62), "metal", 0), box((0, 1.25, 0), (2.42, 0.1, 1.62), "metal", 0)], "crate")
parts = []
for k in range(6):  # a safety-net panel along the deck edge, leaning outward (+X)
    parts.append(cyl((0.0, 0, -2.5 + k), (1.6, -0.6, -2.5 + k), 0.05, "metal", 6))
for y, x in ((0.0, 0.0), (-0.3, 0.8), (-0.6, 1.6)):
    parts.append(cyl((x, y, -2.6), (x, y, 2.6), 0.03, "net", 6))
join(parts, "deck_net")

# ===================================================================== the kraken: head with the eye, and a giant tentacle
head = ball((0, 7, 0), (6, 8, 6.5), "kraken_skin", 32)
for v in head.data.vertices:
    p = G(v.co); v.co += v.normal * (0.6 * pnoise(p * 0.25) + 0.25 * pnoise(p * 0.9))
head.data.update()
parts = [head, ball((0, 1.5, 3.2), (4.8, 2.2, 3.6), "kraken_belly", 24), cyl((0, 0.8, 5.6), (0, -0.4, 7.4), 1.2, "beak", 12, 0.1)]
for k in range(8):  # ridges along the mantle
    a = (k / 7 - 0.5) * 2.0
    parts.append(tube([(math.sin(a) * 5.5, 4, math.cos(a) * 5 - 1), (math.sin(a) * 6.2, 9, math.cos(a) * 5.5 - 1.5), (math.sin(a) * 4, 14, math.cos(a) * 3.5 - 1)], 0.35, "kraken_belly", [1, 0.8, 0.3]))
for s in (-1, 1):  # stumps of tentacles around the mouth
    for k in range(3):
        a = s * (0.4 + k * 0.45)
        parts.append(tube([(math.sin(a) * 4, 0.5, math.cos(a) * 4), (math.sin(a) * 6.5, -1.5, math.cos(a) * 6.5), (math.sin(a) * 8, -4, math.cos(a) * 7)], 1.0, "kraken_skin", [1, 0.8, 0.5]))
join(parts, "kraken_head")
join([ball((0, 0, 0), (1.7, 1.7, 1.0), "kraken_eye", 24), ball((0, 0, 0.9), (0.35, 1.3, 0.2), "kraken_pupil", 16)], "kraken_eye")  # origin at the eye's centre
tpts = [(0, 0, 0), (0, 5, 0.4), (0, 10, 1.6), (0, 14.5, 3.8), (0, 17.5, 7.0), (0, 18.5, 10.5)]
parts = [tube(tpts, 1.5, "kraken_skin", [1.0, 0.85, 0.7, 0.5, 0.32, 0.12])]
for k in range(16):
    t = 0.08 + k * 0.055
    i = min(len(tpts) - 2, int(t * (len(tpts) - 1))); f = t * (len(tpts) - 1) - i
    p = Vector(tpts[i]).lerp(Vector(tpts[i + 1]), f)
    parts.append(ball((0, p.y, p.z + 1.3 * (1 - t) + 0.1), 0.32 * (1 - t * 0.6), "sucker", 10))
join(parts, "kraken_tentacle")

for ob in scene.objects:
    ob.select_set(ob in PROPS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PROPS:
    print("  prop", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"island": (33, 0, 8, 0), "jet": (-20, 0, 40, 2.6), "tug": (-10, 0, 20, 0.5), "bomb_cart": (-6, 0, 24, 0), "crate": (10, 0, -40, 0),
             "kraken_head": (-60, -14, 0, math.pi / 2), "kraken_eye": (-54.5, -6, 0, math.pi / 2), "kraken_tentacle": (-44, -16, -30, math.pi / 2),
             "radar": (33, 30, 14, 0), "deck_net": (-41, 0, 60, math.pi)}
    for ob in PROPS:
        if ob.name in place:
            x, y, z, r = place[ob.name]; ob.location = B(x, y, z); ob.rotation_euler = (0, 0, r)
    bpy.ops.mesh.primitive_plane_add(size=1200, location=B(0, -16, 0))
    sea = bpy.context.object; sm = bpy.data.materials.new("sea"); sm.use_nodes = True
    sm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.05, 0.07, 1); sea.data.materials.append(sm)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.4, 0.45, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(55), 0, math.radians(30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 22; eye, tgt = B(70, 60, -170), B(-5, 0, 10)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
