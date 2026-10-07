# Level 11 (國際機場) creatures for 死城突圍: the parasite swarm, the winged flyer and the virus mother.
#
#   blender -b -P tools/blender/airport_zombies.py -- assets/models/airportzombie.glb [preview.png]
#
# Game coordinates (+Y up, +Z the way the creature faces, metres); B() converts to Blender.
#   bug_body        origin on the ground under the bug; bug_leg: one right-hand leg from its hip (origin), reaching +X
#   flyer_body      origin at the flyer's centre of mass; flyer_wing: the right wing from its root (origin), spreading +X
#   mother_body     origin on the ground at the mound's centre, the maw toward +Z
#   mother_core     a glowing virus core centred on its origin (the game sets three into the body)
#   mother_tentacle origin where it leaves the ground, rising along +Y and curling toward +Z at the tip
#   spore_pod       a seed pod centred on its origin
# Material names are keys the game maps to its own materials.
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "airportzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(23)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "bug_shell": ((0.08, 0.05, 0.03), 0.3, 0.2), "bug_glow": ((0.4, 1.0, 0.2), 0.3, 0.0), "flesh": ((0.42, 0.14, 0.12), 0.55, 0.0),
    "flesh_dark": ((0.2, 0.05, 0.05), 0.6, 0.0), "membrane": ((0.25, 0.04, 0.05), 0.5, 0.0), "bone": ((0.7, 0.62, 0.45), 0.5, 0.0),
    "sac_glow": ((1.0, 0.45, 0.1), 0.4, 0.0), "core_glow": ((0.35, 1.0, 0.3), 0.3, 0.0), "mouth_dark": ((0.05, 0.0, 0.0), 0.4, 0.0),
    "teeth": ((0.75, 0.68, 0.5), 0.4, 0.0), "vein": ((0.3, 0.08, 0.35), 0.5, 0.0), "eye_yellow": ((1.0, 0.85, 0.2), 0.2, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if n in ("bug_glow", "sac_glow", "core_glow", "eye_yellow"):
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


def settle(ob, mat, smooth=True):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
        bpy.ops.object.shade_smooth()
    return ob


def skin(nodes, edges, mat, subdiv=2):
    me = bpy.data.meshes.new("s"); me.from_pydata([B(*n[:3]) for n in nodes], edges, [])
    ob = bpy.data.objects.new("s", me); scene.collection.objects.link(ob)
    sk = ob.modifiers.new("skin", "SKIN"); sk.use_smooth_shade = True
    for i, n in enumerate(nodes):
        sv = me.skin_vertices[0].data[i]; sv.radius = (n[3], n[4]); sv.use_root = i == 0
    if subdiv:
        sd = ob.modifiers.new("sub", "SUBSURF"); sd.levels = subdiv
    apply_mods(ob)
    return settle(ob, mat)


def chain(points, radii, mat, subdiv=2):
    nodes = [(*p, r, r) for p, r in zip(points, radii)]
    return skin(nodes, [(i, i + 1) for i in range(len(nodes) - 1)], mat, subdiv)


def ball(c, r, mat, segs=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def cone(p0, p1, r0, r1, mat, verts=10):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r0, radius2=r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def lumpy(ob, amp, freq, seed=0.0):
    me = ob.data
    for v in me.vertices:
        p = G(v.co)
        v.co += v.normal * amp * pnoise(p * freq + Vector((seed, 0, 0)))
    me.update()


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== parasite (about 0.6 m long)
parts = [chain([(0, 0.17, -0.3), (0, 0.2, -0.18), (0, 0.19, -0.02), (0, 0.17, 0.12), (0, 0.15, 0.22)], [0.07, 0.11, 0.1, 0.085, 0.07], "bug_shell")]
for k in range(5):  # armour plates along the abdomen
    z = -0.26 + k * 0.08
    parts.append(ball((0, 0.24 - abs(z + 0.1) * 0.12, z), (0.11 - abs(z + 0.1) * 0.15, 0.04, 0.05), "bug_shell", 12))
for s in (-1, 1):
    parts += [ball((s * 0.045, 0.19, 0.27), 0.022, "bug_glow", 10), ball((s * 0.02, 0.21, 0.28), 0.013, "bug_glow", 8),
              cone((s * 0.03, 0.13, 0.27), (s * 0.015, 0.1, 0.38), 0.022, 0.003, "bone", 8)]  # mandibles
parts.append(cone((0, 0.17, -0.34), (0, 0.24, -0.5), 0.04, 0.004, "bug_shell", 8))  # stinger
join(parts, "bug_body")
leg = chain([(0, 0, 0), (0.12, 0.06, 0.0), (0.22, -0.06, 0.02), (0.28, -0.17, 0.03)], [0.022, 0.02, 0.014, 0.006], "bug_shell", 1)
join([leg], "bug_leg")

# ===================================================================== flyer (about 1.3 m body)
body = chain([(0, -0.5, -0.05), (0, -0.25, 0.0), (0, 0.05, 0.02), (0, 0.32, -0.02), (0, 0.48, 0.06)], [0.11, 0.2, 0.24, 0.2, 0.09], "flesh")
lumpy(body, 0.02, 9)
parts = [body,
         ball((0, 0.62, 0.12), (0.12, 0.13, 0.14), "flesh", 18),                       # hunched head
         ball((0, -0.18, 0.15), (0.17, 0.2, 0.15), "sac_glow", 18)]                    # glowing explosive sac on the belly
for s in (-1, 1):
    parts += [ball((s * 0.05, 0.65, 0.24), 0.025, "eye_yellow", 8),
              chain([(s * 0.2, 0.28, 0.02), (s * 0.3, 0.05, 0.12), (s * 0.26, -0.18, 0.2), (s * 0.2, -0.3, 0.24)], [0.05, 0.04, 0.032, 0.02], "flesh"),   # dangling arms
              chain([(s * 0.1, -0.48, -0.02), (s * 0.13, -0.75, 0.05), (s * 0.12, -1.0, -0.08)], [0.06, 0.045, 0.03], "flesh_dark")]                   # withered legs
for k in range(6):  # bone spurs along the spine
    parts.append(cone((0, 0.35 - k * 0.14, -0.2 + k * 0.01), (0, 0.38 - k * 0.14, -0.33 + k * 0.01), 0.03, 0.003, "bone", 8))
parts.append(ball((0, 0.55, 0.22), (0.07, 0.03, 0.04), "mouth_dark", 10))
join(parts, "flyer_body")
# the right wing: bony fingers with a membrane between them
fingers = [(0.0, 0.0, 0.0), (0.35, 0.12, -0.05), (0.75, 0.2, -0.05), (1.15, 0.15, -0.12)]
bones = [chain(fingers, [0.05, 0.04, 0.03, 0.015], "bone", 1)]
tips = [(1.15, 0.15, -0.12), (1.05, -0.25, -0.25), (0.8, -0.5, -0.28), (0.45, -0.55, -0.22), (0.15, -0.3, -0.12)]
for t in tips[1:4]:
    bones.append(chain([(0.75, 0.2, -0.05), t], [0.025, 0.01], "bone", 1))
mem = [(0.0, 0.0, 0.0)] + tips
me = bpy.data.meshes.new("membrane"); me.from_pydata([B(*p) for p in mem], [], [list(range(len(mem)))])
ob = bpy.data.objects.new("membrane", me); scene.collection.objects.link(ob)
so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.01; apply_mods(ob)
bones.append(settle(ob, "membrane"))
join(bones, "flyer_wing")

# ===================================================================== virus mother (about 6 m tall)
mound = chain([(0, 0.8, -1.6), (0, 2.0, -0.6), (0, 3.1, 0.4), (0, 3.9, 1.2), (0, 4.4, 1.6)], [2.6, 3.0, 2.6, 1.9, 1.3], "flesh", 3)
lumpy(mound, 0.35, 0.6, 1.0)
lumpy(mound, 0.12, 2.0, 5.0)
for v in mound.data.vertices:  # flatten the base onto the ground
    p = G(v.co)
    if p.y < 0.15:
        v.co = B(p.x, 0.15 - (0.15 - p.y) * 0.1, p.z)
mound.data.update()
parts = [mound]
parts += [ball((0, 3.2, 2.85), (1.15, 0.85, 0.5), "mouth_dark", 24)]                      # the maw
for k in range(14):  # rings of teeth around the maw
    a = k / 14 * math.tau
    x, y = math.cos(a) * 1.05, 3.2 + math.sin(a) * 0.78
    inward = Vector((-math.cos(a), -math.sin(a), 0)) * 0.35
    parts.append(cone((x, y, 2.95), (x + inward.x, y + inward.y, 3.25), 0.09, 0.005, "teeth", 8))
for k in range(9):  # eyes scattered over the mass
    a = random.uniform(-1.2, 1.2); y = random.uniform(3.6, 5.0)
    parts.append(ball((math.sin(a) * 1.5, y, 1.2 + math.cos(a) * 0.9), random.uniform(0.12, 0.22), "eye_yellow", 12))
for k in range(16):  # bulging veins
    a = random.uniform(0, math.tau)
    pts = [(math.sin(a) * r, 0.6 + t * 4.3, -0.4 + math.cos(a) * r) for t, r in ((0, 2.5), (0.35, 2.7), (0.7, 2.05), (1.0, 1.0))]
    parts.append(chain(pts, [0.12, 0.1, 0.08, 0.05], "vein", 1))
for k in range(10):  # stumps where tentacles burrow into the ground
    a = k / 10 * math.tau
    parts.append(chain([(math.sin(a) * 2.4, 0.9, math.cos(a) * 2.2 - 0.6), (math.sin(a) * 3.3, 0.4, math.cos(a) * 3.1 - 0.6), (math.sin(a) * 3.9, 0.05, math.cos(a) * 3.6 - 0.6)],
                       [0.4, 0.3, 0.2], "flesh_dark", 1))
join(parts, "mother_body")
core = [ball((0, 0, 0), 0.62, "core_glow", 24)]
for k in range(6):  # a cage of membrane ribs holding the core
    a = k / 6 * math.tau
    core.append(chain([(math.cos(a) * 0.4, -0.55, math.sin(a) * 0.4), (math.cos(a) * 0.72, 0, math.sin(a) * 0.72), (math.cos(a) * 0.4, 0.55, math.sin(a) * 0.4)],
                      [0.07, 0.09, 0.07], "flesh_dark", 1))
join(core, "mother_core")
tpts = [(0, 0, 0), (0, 1.3, 0.1), (0, 2.6, 0.35), (0, 3.8, 0.8), (0, 4.7, 1.5), (0, 5.1, 2.3)]
tent = chain(tpts, [0.5, 0.42, 0.34, 0.26, 0.17, 0.08], "flesh", 2)
lumpy(tent, 0.04, 3)
parts = [tent]
for k in range(10):  # suckers along the inner side
    t = 0.12 + k * 0.08
    i = min(len(tpts) - 2, int(t * (len(tpts) - 1))); f = t * (len(tpts) - 1) - i
    p = Vector(tpts[i]).lerp(Vector(tpts[i + 1]), f)
    parts.append(ball((0, p.y, p.z + 0.42 * (1 - t) + 0.05), 0.09 * (1 - t * 0.5), "flesh_dark", 10))
join(parts, "mother_tentacle")
pod = [ball((0, 0, 0), (0.22, 0.3, 0.22), "flesh_dark", 16)]
lumpy(pod[0], 0.03, 8)
pod.append(ball((0, 0.05, 0), (0.15, 0.2, 0.15), "core_glow", 12))
join(pod, "spore_pod")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"mother_body": (0, 0, 0), "mother_core": (-1.8, 3.2, 2.0), "mother_tentacle": (4.5, 0, 1.5), "spore_pod": (6.0, 0.4, 3.0),
              "flyer_body": (-5.0, 3.0, 3.0), "flyer_wing": (-4.75, 3.25, 3.0), "bug_body": (-3.0, 0, 4.0), "bug_leg": (-2.92, 0.16, 4.0)}
    for ob in PARTS:
        x, y, z = layout.get(ob.name, (0, 0, 0))
        ob.location = B(x, y, z)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.25, 0.25, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 30; eye, tgt = B(2, 5, 16), B(0, 2.6, 0)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
