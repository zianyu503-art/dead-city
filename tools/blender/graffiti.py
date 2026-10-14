# The 兌換碼牆 of 死城突圍: an old cinder-block garden wall in 黃昏住宅區 with a 兌換碼 sprayed on it.
#
#   blender -b -P tools/blender/graffiti.py -- assets/models/graffiti.glb [preview.png]
#
# The code itself is never written in this repo: it is read from .secrets/redeem-codes.json (git-ignored,
# see docs/adr/0002-redeem-codes.md) and only reaches the .glb as letter-shaped geometry.
# Game coordinates (+Y up); the wall runs along X with its base centred on the origin, the painted face toward +Z.
import bpy, json, math, os, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "graffiti.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CODE = json.load(open(os.path.join(ROOT, ".secrets", "redeem-codes.json")))[0]["code"]
random.seed(42)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "block": ((0.42, 0.41, 0.38), 0.95, 0.0), "block_dark": ((0.3, 0.29, 0.27), 0.95, 0.0), "block_moss": ((0.27, 0.31, 0.2), 0.95, 0.0),
    "mortar": ((0.22, 0.21, 0.2), 1.0, 0.0), "cap": ((0.5, 0.49, 0.46), 0.9, 0.0),
    "paint_yellow": ((0.95, 0.78, 0.08), 0.6, 0.0), "paint_red": ((0.6, 0.04, 0.03), 0.6, 0.0), "paint_black": ((0.03, 0.03, 0.03), 0.6, 0.0),
    "paint_white": ((0.85, 0.85, 0.82), 0.6, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if n == "paint_yellow":  # a touch of glow so it stays readable at dusk
        b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 0.35
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
    return ob


def box(c, s, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def tube(pts, r, mat):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = 6
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*B(*p), 1)
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def paint(points2d, z, mat, w=0.012):
    """A spray stroke on the front face: points (x, y) on the wall, flattened against it."""
    ob = tube([(x, y, 0) for x, y in points2d], w, mat)
    ob.scale = (1, 0.25, 1); ob.location = B(0, 0, z)  # squash it flat against the wall (Blender Y is game -Z), then move it onto the face
    activate(ob); bpy.ops.object.transform_apply(location=True, scale=True)
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== the wall: cinder blocks in running bond, end pillars and a cap
LEN, H, T = 4.0, 1.8, 0.3
FRONT = T / 2
parts = [box((0, H / 2, 0), (LEN - 0.02, H, T - 0.03), "mortar")]
BW, BH, GAP = 0.4, 0.2, 0.012
rows = int(H / BH)
for r in range(rows):
    y = r * BH + BH / 2; off = (BW / 2) if r % 2 else 0
    x = -LEN / 2 - off
    while x < LEN / 2:
        x0, x1 = max(x, -LEN / 2), min(x + BW, LEN / 2)
        if x1 - x0 > 0.05:
            broken = random.random() < 0.04 and r > 2
            mat = "block_moss" if r < 2 and random.random() < 0.6 else random.choice(("block", "block", "block_dark"))
            for s in (1, -1):  # both faces
                d = (0.02 if broken else 0) * s
                parts.append(box(((x0 + x1) / 2, y + random.uniform(-0.003, 0.003), s * (T / 2 - 0.02) - d), (x1 - x0 - GAP, BH - GAP, 0.045), mat,
                                 (0, 0, random.uniform(-0.01, 0.01))))
        x += BW
for s in (-1, 1):  # end pillars
    parts.append(box((s * (LEN / 2 + 0.17), (H + 0.15) / 2, 0), (0.36, H + 0.15, 0.38), "block_dark"))
    parts.append(box((s * (LEN / 2 + 0.17), H + 0.19, 0), (0.42, 0.08, 0.44), "cap"))
parts.append(box((0, H + 0.04, 0), (LEN + 0.02, 0.08, T + 0.06), "cap"))
for k in range(5):  # chipped cap pieces lying at the foot
    parts.append(box((random.uniform(-1.6, 1.6), 0.03, FRONT + random.uniform(0.15, 0.5)), (random.uniform(0.06, 0.14), 0.05, random.uniform(0.05, 0.1)), "cap",
                     (0, random.uniform(0, 3), 0)))
join(parts, "code_wall_blocks")

# ===================================================================== the paint: decoy tags, a gift doodle and the code
Z = FRONT + 0.008
parts = []
# a big red scrawl and an X across the left end, black drips — just noise around the code
parts.append(paint([(-1.85, 1.35), (-1.6, 1.62), (-1.35, 1.3), (-1.1, 1.6), (-0.9, 1.32), (-0.7, 1.55)], Z, "paint_red", 0.02))
parts.append(paint([(-1.8, 0.35), (-1.3, 0.85)], Z, "paint_black", 0.018)); parts.append(paint([(-1.8, 0.85), (-1.3, 0.35)], Z, "paint_black", 0.018))
for x in (-1.5, -1.05, -0.8):
    parts.append(paint([(x, 1.3), (x + 0.01, 1.1 - random.uniform(0, 0.15))], Z, "paint_red", 0.006))
parts.append(paint([(1.2, 1.45), (1.45, 1.7), (1.75, 1.42), (1.5, 1.2), (1.2, 1.45)], Z, "paint_black", 0.016))
# a little gift box doodle next to the code
gx, gy = 1.35, 0.78
parts.append(paint([(gx - 0.14, gy - 0.12), (gx + 0.14, gy - 0.12), (gx + 0.14, gy + 0.1), (gx - 0.14, gy + 0.1), (gx - 0.14, gy - 0.12)], Z, "paint_white", 0.008))
parts.append(paint([(gx, gy - 0.12), (gx, gy + 0.1)], Z, "paint_white", 0.008))
parts.append(paint([(gx, gy + 0.1), (gx - 0.08, gy + 0.18), (gx - 0.02, gy + 0.1), (gx + 0.06, gy + 0.18), (gx, gy + 0.1)], Z, "paint_white", 0.007))
# the code, small and slightly crooked, as the sprayer left it
bpy.ops.object.text_add(location=B(0.2, 0.86, Z))
t = bpy.context.object; t.data.body = CODE; t.data.size = 0.17; t.data.extrude = 0.003
t.data.align_x = "CENTER"; t.data.align_y = "CENTER"; t.data.space_character = 1.08
t.rotation_euler = (math.pi / 2, 0, 0); t.rotation_euler.rotate_axis("Z", math.radians(2.5))  # tilted within the wall's plane
activate(t); bpy.ops.object.convert(target="MESH")
code = settle(bpy.context.object, "paint_yellow"); code.name = "paint"; code.data.name = "paint"
parts.append(code)
parts.append(paint([(-0.75, 0.73), (1.12, 0.69)], Z, "paint_yellow", 0.006))  # an underline
join(parts, "code_wall_paint")

# one object for the game: blocks and paint together
wall = join([PARTS.pop(), PARTS.pop()], "code_wall")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_extras=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.25, 0.2, 0.18, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 35; eye, tgt = B(1.2, 1.3, 4.2), B(0, 0.95, 0)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(60), 0, math.radians(-30))
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
