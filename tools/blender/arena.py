# The 競技場 of 死城突圍: a ruined Roman arena (see CONTEXT.md, .scratch/arena/spec.md).
#
#   blender -b -P tools/blender/arena.py -- assets/models/arena.glb [preview.png]
#
# Game coordinates (+Y up, north is -Z), centred on the middle of the sand. Kept low-poly on purpose:
# the claude.ai mirror inlines every model and has little room left.
#   arena_bowl    sand floor, podium wall with the two gate gaps (north and south), stepped stands, outer wall
#   arena_gate    an iron portcullis in its stone frame, 7 m wide, facing +Z (the game turns it for each gate)
#   arena_banner  a hanging banner on a pole; its "banner" material is recoloured red or blue by the game
#   arena_brazier a bronze fire bowl on a tripod (the game adds the flames)
#   arena_ruin    a broken column lying on its plinth, cover on the sand
import bpy, bmesh, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "arena.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(7)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "sand": ((0.55, 0.42, 0.26), 1.0, 0.0), "sand_dark": ((0.4, 0.29, 0.17), 1.0, 0.0), "stone": ((0.52, 0.47, 0.4), 0.9, 0.0),
    "stone_dark": ((0.3, 0.27, 0.23), 0.9, 0.0), "stone_light": ((0.66, 0.61, 0.53), 0.85, 0.0), "iron": ((0.08, 0.075, 0.07), 0.5, 0.8),
    "wood": ((0.22, 0.13, 0.07), 0.8, 0.0), "banner": ((0.6, 0.6, 0.6), 0.8, 0.0), "bronze": ((0.45, 0.28, 0.12), 0.4, 0.9),
    "blood": ((0.25, 0.02, 0.02), 0.6, 0.0), "tunnel": ((0.02, 0.02, 0.02), 1.0, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    MAT[n] = m

R_SAND, R_POD, H_POD = 32.0, 33.4, 4.2           # sand radius, podium wall outer radius and height
GATE_HALF = 3.8 / R_SAND                          # half the gate gap, as an angle on the podium circle
SEG = 72


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def settle(ob, mat):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    return ob


def mesh_from(vs, fs, mat, smooth=False):
    me = bpy.data.meshes.new("m"); me.from_pydata(vs, [], fs); me.validate()
    ob = bpy.data.objects.new("m", me); scene.collection.objects.link(ob)
    settle(ob, mat)
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def ring_band(r0, r1, y0, y1, mat, a0=0.0, a1=math.tau, seg=SEG, top=True, inner=True, outer=True):
    """A thick ring (or arc) between radii r0..r1 and heights y0..y1, angle 0 = north (-Z), growing clockwise seen from above."""
    n = max(2, int(seg * (a1 - a0) / math.tau)); vs, fs = [], []
    P = lambda r, y, a: B(math.sin(a) * r, y, -math.cos(a) * r)
    for k in range(n + 1):
        a = a0 + (a1 - a0) * k / n
        vs += [P(r0, y0, a), P(r0, y1, a), P(r1, y1, a), P(r1, y0, a)]
    for k in range(n):
        i, j = k * 4, (k + 1) * 4
        if inner: fs.append((i, j, j + 1, i + 1))
        if top: fs.append((i + 1, j + 1, j + 2, i + 2))
        if outer: fs.append((i + 2, j + 2, j + 3, i + 3))
    if a1 - a0 < math.tau - 1e-6:  # cap the ends of an arc
        fs.append((0, 1, 2, 3)); e = n * 4; fs.append((e + 3, e + 2, e + 1, e))
    return mesh_from(vs, fs, mat)


def box(c, s, mat, rot_y=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=(0, 0, -rot_y))
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=12, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== the bowl
parts = []
# sand: a disc with a slightly darker, trampled ring and a few dark stains
bpy.ops.mesh.primitive_circle_add(vertices=64, radius=R_SAND + 0.2, fill_type="TRIFAN", location=(0, 0, 0))
parts.append(settle(bpy.context.object, "sand"))
parts.append(ring_band(10, 16, 0.006, 0.006, "sand_dark", top=True, inner=False, outer=False, seg=48))
for k in range(5):
    a = random.uniform(0, math.tau); r = random.uniform(4, 26)
    bpy.ops.mesh.primitive_circle_add(vertices=10, radius=random.uniform(0.6, 1.4), fill_type="TRIFAN", location=B(math.sin(a) * r, 0.012, math.cos(a) * r))
    ob = bpy.context.object; ob.scale = (1, random.uniform(0.5, 1), 1); parts.append(settle(ob, "blood"))
# the podium wall, broken by the north and south gates
for a0, a1 in ((GATE_HALF, math.pi - GATE_HALF), (math.pi + GATE_HALF, math.tau - GATE_HALF)):
    parts.append(ring_band(R_SAND, R_POD, 0, 0.9, "stone_dark", a0, a1))
    parts.append(ring_band(R_SAND, R_POD, 0.9, H_POD, "stone", a0, a1))
    parts.append(ring_band(R_SAND - 0.25, R_POD + 0.1, H_POD, H_POD + 0.35, "stone_light", a0, a1))   # coping
# the stands: stepped tiers rising to the outer wall (continuous over the gate tunnels)
r, y = R_POD, H_POD + 0.35
for k in range(9):
    parts.append(ring_band(r, r + 2.2, y, y + 1.35, "stone" if k % 2 else "stone_light", seg=SEG, inner=True, top=True, outer=False))
    r += 2.2; y += 1.35
# the outer wall above the top tier, with pilasters on its inner face
R_OUT = r
parts.append(ring_band(R_OUT, R_OUT + 1.5, y - 1.35, y + 5.5, "stone", seg=SEG))
parts.append(ring_band(R_OUT - 0.2, R_OUT + 1.7, y + 5.5, y + 6.1, "stone_light", seg=SEG))
for k in range(36):
    a = k / 36 * math.tau
    parts.append(box((math.sin(a) * (R_OUT - 0.25), y + 2.1, -math.cos(a) * (R_OUT - 0.25)), (0.9, 6.8, 0.5), "stone_light", a))
    if k % 2:  # dark arch openings between them
        b = a + math.tau / 72
        parts.append(box((math.sin(b) * (R_OUT - 0.02), y + 2.4, -math.cos(b) * (R_OUT - 0.02)), (2.0, 3.6, 0.05), "tunnel", b))
# the dark tunnels behind the gates
for a in (0, math.pi):
    parts.append(box((math.sin(a) * (R_POD + 3), 2.4, -math.cos(a) * (R_POD + 3)), (7.6, 4.8, 6), "tunnel", a))
join(parts, "arena_bowl")

# ===================================================================== a gate: stone frame and an iron portcullis, facing +Z
parts = [box((s * 4.2, 3.0, 0), (1.0, 6.0, 1.6), "stone_light") for s in (-1, 1)]
parts.append(box((0, 6.3, 0), (9.4, 1.2, 1.7), "stone_light"))
parts.append(box((0, 7.05, 0.05), (2.2, 0.5, 1.8), "stone"))
for k in range(9):  # vertical bars with spikes at the foot
    x = -3.4 + k * 0.85
    parts += [box((x, 2.85, 0.1), (0.1, 5.5, 0.1), "iron"), cyl((x, 0.12, 0.1), (x, -0.05, 0.1), 0.06, "iron", 6, 0.0)]
for yb in (1.2, 2.6, 4.0, 5.3):
    parts.append(box((0, yb, 0.16), (7.0, 0.12, 0.08), "iron"))
join(parts, "arena_gate")

# ===================================================================== a banner on a pole
parts = [cyl((-0.95, 0, 0), (0.95, 0, 0), 0.05, "wood", 8)]
for s in (-1, 1):
    parts.append(cyl((s * 0.95, 0, 0), (s * 1.02, 0, 0), 0.08, "bronze", 8))
vs = [];
for j in range(7):  # the cloth hangs in a gentle wave and ends in a swallowtail
    yy = -0.05 - j * 0.5
    for x in (-0.8, 0.8):
        z = 0.04 * math.sin(j * 1.3 + x)
        vs.append(B(x, yy if not (j == 6 and abs(x) > 0) else yy, z))
vs.append(B(0, -2.55, 0.02))
fs = [(j * 2, j * 2 + 1, j * 2 + 3, j * 2 + 2) for j in range(6)] + [(12, 13, 14)]
cloth = mesh_from(vs, fs, "banner")
so = cloth.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.03; activate(cloth); bpy.ops.object.modifier_apply(modifier="s")
parts.append(cloth)
join(parts, "arena_banner")

# ===================================================================== a brazier
parts = [cyl((0, 0.9, 0), (0, 1.25, 0), 0.55, "bronze", 16, 0.75), cyl((0, 1.25, 0), (0, 1.3, 0), 0.78, "bronze", 16)]
for k in range(3):
    a = k / 3 * math.tau
    parts.append(cyl((math.sin(a) * 0.5, 0.95, math.cos(a) * 0.5), (math.sin(a) * 0.75, 0, math.cos(a) * 0.75), 0.05, "iron", 6))
parts.append(cyl((0, 1.18, 0), (0, 1.3, 0), 0.6, "tunnel", 14))  # coals
join(parts, "arena_brazier")

# ===================================================================== a fallen column on its plinth (cover)
parts = [box((0, 0.35, 0), (2.4, 0.7, 2.4), "stone_dark"), cyl((0, 0.7, 0), (0, 2.6, 0), 0.75, "stone_light", 14, 0.7)]
parts.append(cyl((-0.6, 0.6, 1.4), (2.4, 0.6, 2.6), 0.62, "stone_light", 14))   # the toppled drum beside it
parts.append(box((0.4, 2.65, 0), (1.9, 0.25, 1.9), "stone"))
join(parts, "arena_ruin")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)  # untextured: no UVs, smaller file
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"arena_gate": [(0, 0, -R_SAND - 0.4, 0), (0, 0, R_SAND + 0.4, math.pi)], "arena_ruin": [(9, 0, 6, 0.3), (-10, 0, -7, 2.0)],
             "arena_brazier": [(14, H_POD + 0.35, -29, 0)], "arena_banner": [(5.2, H_POD - 0.3, -R_SAND + 0.1, 0)]}
    for ob in list(PARTS):
        for i, (x, yy, z, rot) in enumerate(place.get(ob.name, [])):
            o = ob if i == 0 else ob.copy()
            if i: scene.collection.objects.link(o)
            o.location = B(x, yy, z); o.rotation_euler = (0, 0, -rot)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.42, 0.35, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(65), 0, math.radians(40))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 18; eye, tgt = B(0, 22, 48), B(0, 2, -6)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
