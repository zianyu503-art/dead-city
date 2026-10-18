# Gear for the 第十五關 (熱帶火山島) zombies of 死城突圍 and its boss, the 火山巨人 (see CONTEXT.md).
#
#   blender -b -P tools/blender/tropic_zombies.py -- assets/models/tropiczombie.glb [preview.png]
#
# Each piece in the frame of the joint it hangs from (game coordinates, +Y up, +Z the way it faces):
#   head frame - skull centre y 0.13, top y ~0.27, face toward +z;  body frame - feet on the origin, chest ~1.35, front z ~0.15
#   (the 屍王 body the 火山巨人 wears: front ~0.2, half-width ~0.29);  arm frame - shoulder pivot, elbow at y -0.31, right arm (+x out)
#   wasp: one insect of a 毒蜂 swarm, centred;  lava_bomb: the 岩漿彈, centred.
# Untextured: exported without UVs.
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "tropiczombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(51)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, emission)
    "leaf": ((0.15, 0.36, 0.08), 0.8, 0.0, 0), "leaf_dark": ((0.07, 0.22, 0.05), 0.8, 0.0, 0), "leaf_dry": ((0.4, 0.33, 0.12), 0.85, 0.0, 0),
    "nest": ((0.55, 0.47, 0.35), 0.95, 0.0, 0), "nest_dark": ((0.2, 0.16, 0.1), 0.95, 0.0, 0), "wasp_body": ((0.85, 0.6, 0.05), 0.4, 0.1, 0),
    "wasp_dark": ((0.04, 0.03, 0.02), 0.4, 0.1, 0), "wing": ((0.85, 0.9, 0.95), 0.1, 0.0, 0),
    "crust": ((0.1, 0.08, 0.07), 0.85, 0.0, 0), "magma": ((1.0, 0.35, 0.04), 0.4, 0.0, 5.0), "obsidian": ((0.02, 0.02, 0.03), 0.15, 0.4, 0),
    "core": ((1.0, 0.55, 0.1), 0.3, 0.0, 8.0),
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


def cyl(p0, p1, r, mat, verts=8, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat, True)


def ball(c, r, mat, segs=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(5, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat, True)


def lump(c, r, mat, amp=0.3, sub=1, seed=0.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1, location=(0, 0, 0))
    ob = bpy.context.object
    for v in ob.data.vertices:
        p = v.co.copy(); v.co = p * (1 + amp * pnoise(p * 2.0 + Vector((seed, seed * 1.3, seed * 2.1))))
    ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r); ob.location = B(*c)
    return settle(ob, mat)


def blade(c, ang, tilt, length, width, mat):
    """A single leaf: a flat diamond pointing outward-and-down from c."""
    x, y, z = c; dx, dz = math.sin(ang), math.cos(ang)
    tip = (x + dx * length * math.cos(tilt), y - length * math.sin(tilt), z + dz * length * math.cos(tilt))
    mid = ((x + tip[0]) / 2, (y + tip[1]) / 2, (z + tip[2]) / 2)
    vs = [B(*c), B(mid[0] - dz * width, mid[1], mid[2] + dx * width), B(*tip), B(mid[0] + dz * width, mid[1], mid[2] - dx * width)]
    me = bpy.data.meshes.new("b"); me.from_pydata(vs, [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("b", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.01; activate(ob); bpy.ops.object.modifier_apply(modifier="s")
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== 叢林偽裝者: a cloak of leaves (body) and a leafy hood (head)
parts = []
for k in range(70):
    a = random.uniform(0, math.tau); y = random.uniform(0.9, 1.75); r = 0.2 + 0.05 * abs(math.cos(a))
    parts.append(blade((math.sin(a) * r * 0.9, y, math.cos(a) * r * 0.75), a + random.uniform(-0.4, 0.4), random.uniform(0.6, 1.2), random.uniform(0.18, 0.3), 0.06,
                       random.choice(("leaf", "leaf", "leaf_dark", "leaf_dry"))))
join(parts, "lurker_ghillie")
parts = [ball((0, 0.17, -0.02), (0.16, 0.18, 0.17), "leaf_dark", 12)]
for k in range(26):
    a = random.uniform(0, math.tau)
    if math.cos(a) > 0.7: continue  # keep the face mostly clear
    parts.append(blade((math.sin(a) * 0.13, random.uniform(0.15, 0.3), math.cos(a) * 0.13), a, random.uniform(0.3, 0.9), random.uniform(0.15, 0.25), 0.05,
                       random.choice(("leaf", "leaf_dark", "leaf_dry"))))
join(parts, "lurker_hood")

# ===================================================================== 蜂巢殭屍: the paper nest on the back and over half the head, and a wasp
parts = [lump((0.05, 1.42, -0.3), (0.3, 0.38, 0.26), "nest", 0.18, 2, 1.2)]
for k in range(7):  # layered paper bands
    y = 1.12 + k * 0.09; parts.append(lump((0.05, y, -0.3), (0.31 - abs(k - 3) * 0.02, 0.035, 0.27 - abs(k - 3) * 0.02), "nest_dark" if k % 2 else "nest", 0.1, 1, k))
for k in range(5):  # entrance holes
    parts.append(ball((random.uniform(-0.15, 0.25), random.uniform(1.2, 1.65), -0.55), (0.05, 0.05, 0.03), "nest_dark", 8))
parts.append(lump((0.2, 1.62, -0.05), (0.14, 0.14, 0.13), "nest", 0.2, 1, 5.5))  # spreading over a shoulder
join(parts, "hive_nest")
join([lump((0.07, 0.2, -0.03), (0.14, 0.15, 0.15), "nest", 0.2, 2, 2.4), ball((0.12, 0.2, 0.09), (0.03, 0.03, 0.02), "nest_dark", 6),
      ball((0.02, 0.28, 0.02), (0.03, 0.03, 0.02), "nest_dark", 6)], "hive_head")
join([ball((0, 0, -0.035), (0.022, 0.022, 0.04), "wasp_body", 8), ball((0, 0, 0.02), (0.016, 0.016, 0.02), "wasp_dark", 8),
      cyl((0, 0, -0.075), (0, 0, -0.09), 0.01, "wasp_dark", 5, 0.0),
      *[lump((s * 0.035, 0.015, 0.0), (0.035, 0.004, 0.014), "wing", 0.05, 1, s) for s in (-1, 1)]], "wasp")

# ===================================================================== 岩漿殭屍: cracked basalt crust with magma showing between (body, head, arm)
parts = []
for k in range(22):
    a = random.uniform(0, math.tau); y = random.uniform(1.0, 1.7); r = 0.2
    parts.append(lump((math.sin(a) * r, y, math.cos(a) * r * 0.8), (0.1, 0.11, 0.06), "crust", 0.25, 1, k))
for k in range(10):  # glowing seams
    a = random.uniform(0, math.tau); y = random.uniform(1.0, 1.65)
    parts.append(cyl((math.sin(a) * 0.205, y, math.cos(a) * 0.17), (math.sin(a + 0.3) * 0.205, y - 0.15, math.cos(a + 0.3) * 0.17), 0.012, "magma", 5))
join(parts, "magma_crust")
join([lump((0, 0.16, -0.01), (0.15, 0.17, 0.155), "crust", 0.2, 2, 3.3), *[cyl((x, 0.28, 0.0), (x * 1.3, 0.12, 0.14), 0.01, "magma", 5) for x in (-0.07, 0.04)],
      *[ball((s * 0.05, 0.15, 0.13), (0.025, 0.018, 0.01), "magma", 6) for s in (-1, 1)]], "magma_head")
join([lump((0.03, -0.12, 0), (0.08, 0.13, 0.08), "crust", 0.25, 1, 7.1), cyl((0.07, -0.05, 0.05), (0.06, -0.25, 0.06), 0.01, "magma", 5)], "magma_arm")

# ===================================================================== 火山巨人: basalt armour over the 屍王 body, the 熔岩核心, obsidian horns, rock gauntlets
parts = []
for s in (-1, 1):  # massive shoulder slabs
    parts += [lump((s * 0.36, 1.66, 0.0), (0.2, 0.14, 0.22), "crust", 0.25, 2, s * 2), lump((s * 0.42, 1.72, -0.05), (0.08, 0.16, 0.08), "obsidian", 0.3, 1, s)]
for k in range(16):  # plates over the back and flanks
    a = random.uniform(1.4, 4.9); y = random.uniform(1.05, 1.65)
    parts.append(lump((math.sin(a) * 0.3, y, math.cos(a) * 0.22), (0.12, 0.12, 0.07), "crust", 0.25, 1, k * 0.7))
for k in range(8):  # a ring of plates framing the core
    a = k / 8 * math.tau
    parts.append(lump((math.sin(a) * 0.15, 1.38 + math.cos(a) * 0.15, 0.22), (0.08, 0.08, 0.05), "crust", 0.2, 1, k * 1.1))
for k in range(12):  # magma running in the seams
    a = random.uniform(0, math.tau); y = random.uniform(1.0, 1.7)
    parts.append(cyl((math.sin(a) * 0.3, y, math.cos(a) * 0.22), (math.sin(a + 0.25) * 0.3, y - 0.2, math.cos(a + 0.25) * 0.22), 0.018, "magma", 5))
join(parts, "titan_armor")
join([ball((0, 1.38, 0.2), (0.11, 0.11, 0.07), "core", 14), *[cyl((0, 1.38, 0.2), (math.sin(a) * 0.2, 1.38 + math.cos(a) * 0.2, 0.18), 0.012, "magma", 5) for a in
      [k / 6 * math.tau for k in range(6)]]], "titan_core")
parts = [lump((0, 0.24, -0.02), (0.15, 0.08, 0.15), "crust", 0.2, 1, 3)]
for s in (-1, 1):
    parts += [cyl((s * 0.1, 0.27, 0.0), (s * 0.24, 0.45, -0.08), 0.045, "obsidian", 6, 0.02), cyl((s * 0.24, 0.45, -0.08), (s * 0.2, 0.6, 0.02), 0.02, "obsidian", 6, 0.0)]
parts += [cyl((0, 0.3, 0.02), (0, 0.48, -0.02), 0.035, "obsidian", 6, 0.0), *[ball((s * 0.05, 0.15, 0.12), (0.03, 0.02, 0.01), "core", 6) for s in (-1, 1)]]
join(parts, "titan_horns")
join([lump((0.04, -0.14, 0), (0.1, 0.15, 0.1), "crust", 0.25, 1, 4.4), lump((0.03, -0.55, 0.02), (0.1, 0.12, 0.1), "crust", 0.3, 1, 8.8),
      cyl((0.08, -0.1, 0.06), (0.08, -0.5, 0.07), 0.012, "magma", 5)], "titan_arm")
join([lump((0, 0, 0), 0.3, "crust", 0.3, 1, 1.9), *[cyl((0, 0, 0), (math.sin(a) * 0.32, math.cos(a) * 0.3, 0.1), 0.04, "magma", 5) for a in [k / 5 * math.tau for k in range(5)]],
      ball((0, 0, 0), 0.24, "magma", 10)], "lava_bomb")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"lurker_ghillie": (-1.8, 0), "lurker_hood": (-1.8, 1.5), "hive_nest": (-0.8, 0), "hive_head": (-0.8, 1.5), "wasp": (-0.2, 1.0),
              "magma_crust": (0.3, 0), "magma_head": (0.3, 1.5), "magma_arm": (0.9, 1.4), "titan_armor": (1.6, 0), "titan_core": (1.6, 0),
              "titan_horns": (1.6, 1.5), "titan_arm": (2.3, 1.4), "lava_bomb": (2.5, 0.6)}
    for ob in PARTS:
        x, y = layout.get(ob.name, (0, 0)); ob.location = B(x, y, 0); ob.rotation_euler = (0, 0, math.radians(20))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 5.2
    cam.location = B(0.3, 1.1, 8); cam.rotation_euler = (B(0.3, 1.1, 0) - B(0.3, 1.1, 8)).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((3, 5, 6), 1500), ((-4, 2, 4), 600)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 5; l.location = B(*loc); l.rotation_euler = (B(0.3, 1, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 20; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
