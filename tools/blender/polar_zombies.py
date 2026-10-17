# The 第十四關 (南極研究站) zombies of 死城突圍 and its boss, the 遠古巨獸 (see CONTEXT.md).
#
#   blender -b -P tools/blender/polar_zombies.py -- assets/models/polarzombie.glb [preview.png]
#
# Gear is modelled in the frame of the joint it hangs from (game coordinates, +Y up, +Z the way it faces):
#   head frame - skull centre y 0.13, top y ~0.27, face toward +z;  body frame - feet on the origin, chest ~1.35, front z ~0.15
#   arm frame  - the shoulder pivot, upper arm down to the elbow at y -0.31, drawn on the right arm (+x outward)
# The 遠古巨獸 is its own creature, built at full size on the ground (shoulder ~4.6 m, facing +Z):
#   ancient_body (origin on the ground under its middle), ancient_head (origin at the neck joint, (0, 3.9, 3.3) on the body),
#   ancient_leg_front / ancient_leg_back (origin at the hip, the leg hanging to y -2.9), ancient_tail (origin at its root (0, 3.7, -3.4)),
#   ancient_crystals (body frame; the weak point).  ice_spikes: the spikes it raises from the ground (origin on the ground).
#   ln2_canister: the 液態氮罐 a 極地科學家 throws (centred).
# Untextured: exported without UVs.
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "polarzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(41)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, alpha, emission)
    "ice": ((0.6, 0.82, 0.95), 0.08, 0.0, 0.8, 0.15), "ice_dark": ((0.3, 0.5, 0.68), 0.12, 0.0, 1, 0),
    "yeti_fur": ((0.82, 0.83, 0.85), 0.95, 0.0, 1, 0), "yeti_skin": ((0.35, 0.38, 0.45), 0.7, 0.0, 1, 0), "horn": ((0.25, 0.22, 0.2), 0.6, 0.0, 1, 0),
    "parka": ((0.85, 0.3, 0.04), 0.7, 0.0, 1, 0), "fur_trim": ((0.75, 0.72, 0.66), 0.95, 0.0, 1, 0), "goggle": ((0.05, 0.06, 0.08), 0.1, 0.5, 1, 0),
    "lens": ((0.9, 0.55, 0.1), 0.05, 0.6, 1, 0.3), "strap": ((0.06, 0.06, 0.06), 0.8, 0.0, 1, 0), "steel": ((0.6, 0.62, 0.65), 0.3, 0.9, 1, 0),
    "cap_blue": ((0.1, 0.3, 0.8), 0.4, 0.2, 1, 0), "pack": ((0.12, 0.18, 0.28), 0.8, 0.0, 1, 0),
    "ancient_fur": ((0.24, 0.19, 0.15), 0.95, 0.0, 1, 0), "ancient_skin": ((0.3, 0.33, 0.38), 0.7, 0.0, 1, 0), "ivory": ((0.85, 0.8, 0.68), 0.45, 0.0, 1, 0),
    "crystal": ((0.35, 0.85, 1.0), 0.1, 0.0, 1, 3.0), "eye_glow": ((0.4, 0.9, 1.0), 0.2, 0.0, 1, 5.0), "frost_crust": ((0.78, 0.88, 0.95), 0.4, 0.0, 1, 0),
}
MAT = {}
for n, (c, r, mt, a, em) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if a < 1:
        b.inputs["Alpha"].default_value = a
        try: m.surface_render_method = "BLENDED"
        except Exception: m.blend_method = "BLEND"
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


def cyl(p0, p1, r, mat, verts=12, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=14):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def box(c, s, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat, False)


def lump(c, r, mat, amp=0.25, sub=1, seed=0.0, smooth=False):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1, location=(0, 0, 0))
    ob = bpy.context.object
    for v in ob.data.vertices:
        p = v.co.copy(); v.co = p * (1 + amp * pnoise(p * 2.2 + Vector((seed, seed * 1.7, seed * 2.3))))
    ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r); ob.location = B(*c)
    return settle(ob, mat, smooth)


def tube(pts, r, mat, radii=None, res=4):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 2; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def tuft(p0, p1, r, mat):
    """A clump of fur: a short tapering cone."""
    return cyl(p0, p1, r, mat, 6, r * 0.15)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== 冰甲殭屍: ice over the torso, the head and the arms
parts = []
for k in range(14):  # chunky plates round the chest, back and shoulders
    a = k / 14 * math.tau; y = random.uniform(1.05, 1.6)
    parts.append(lump((math.sin(a) * 0.2, y, math.cos(a) * 0.16), (random.uniform(0.09, 0.14), random.uniform(0.1, 0.16), 0.07), "ice", 0.3, 1, k))
for s in (-1, 1):  # shoulder spikes
    for k in range(3):
        parts.append(cyl((s * (0.18 + k * 0.05), 1.62, -0.02 + k * 0.03), (s * (0.25 + k * 0.08), 1.9 - k * 0.05, -0.05), 0.04, "ice", 5, 0.0))
join(parts, "ice_armor_body")
join([lump((0, 0.17, -0.01), (0.16, 0.17, 0.165), "ice", 0.22, 2, 3.3), *[cyl((x, 0.28, z), (x * 1.6, 0.42, z * 1.4), 0.03, "ice", 5, 0.0) for x, z in ((-0.06, -0.04), (0.07, -0.02), (0, -0.09))],
      ball((0, 0.15, 0.13), (0.1, 0.06, 0.03), "ice_dark", 10)], "ice_armor_head")
join([lump((0.03, -0.12, 0), (0.09, 0.14, 0.09), "ice", 0.3, 1, 7.1), lump((0.04, -0.3, 0.01), (0.08, 0.06, 0.08), "ice", 0.3, 1, 2.2)], "ice_armor_arm")

# ===================================================================== 雪怪: fur over the body, a maned head, furry arms
parts = []
for k in range(60):
    a = random.uniform(0, math.tau); y = random.uniform(0.95, 1.75); r = 0.22 + 0.06 * math.sin(a) ** 2
    p0 = (math.sin(a) * r * 0.9, y, math.cos(a) * r * 0.75)
    p1 = (math.sin(a) * (r + 0.12), y - random.uniform(0.12, 0.25), math.cos(a) * (r * 0.75 + 0.1))
    parts.append(tuft(p0, p1, random.uniform(0.05, 0.08), "yeti_fur"))
for s in (-1, 1):
    parts.append(lump((s * 0.24, 1.66, -0.02), (0.16, 0.12, 0.14), "yeti_fur", 0.35, 1, s * 3))
join(parts, "yeti_fur")
parts = [lump((0, 0.2, -0.04), (0.19, 0.21, 0.19), "yeti_fur", 0.3, 2, 1.1), ball((0, 0.21, 0.13), (0.13, 0.04, 0.03), "yeti_skin", 10)]
for s in (-1, 1):
    parts += [tube([(s * 0.12, 0.3, -0.02), (s * 0.22, 0.42, -0.06), (s * 0.24, 0.55, 0.02)], 0.03, "horn", [1, 0.7, 0.2]),
              cyl((s * 0.04, 0.03, 0.15), (s * 0.045, -0.05, 0.16), 0.012, "ivory", 6, 0.0)]
for k in range(12):  # a shaggy mane down the neck
    a = random.uniform(1.6, 4.7)
    parts.append(tuft((math.sin(a) * 0.15, 0.1, math.cos(a) * 0.15), (math.sin(a) * 0.2, -0.15, math.cos(a) * 0.2), 0.05, "yeti_fur"))
join(parts, "yeti_head")
parts = []
for k in range(10):
    y = random.uniform(-0.05, -0.3); a = random.uniform(-1, 2.5)
    parts.append(tuft((math.cos(a) * 0.05, y, math.sin(a) * 0.05), (math.cos(a) * 0.12, y - 0.12, math.sin(a) * 0.1), 0.045, "yeti_fur"))
join(parts, "yeti_arm")

# ===================================================================== 極地科學家: parka hood with goggles, backpack with liquid-nitrogen canisters
parts = [ball((0, 0.17, -0.02), (0.165, 0.19, 0.175), "parka", 18)]
for k in range(16):  # fur trim round the face
    a = k / 16 * math.tau
    parts.append(ball((math.sin(a) * 0.12, 0.13 + math.cos(a) * 0.14, 0.12), 0.035, "fur_trim", 8))
parts += [tube([(-0.16, 0.2, 0.0), (-0.1, 0.21, 0.13), (0.1, 0.21, 0.13), (0.16, 0.2, 0.0)], 0.012, "strap"),
          *[cyl((s * 0.05, 0.2, 0.125), (s * 0.05, 0.2, 0.145), 0.035, "goggle", 14) for s in (-1, 1)],
          *[cyl((s * 0.05, 0.2, 0.145), (s * 0.05, 0.2, 0.15), 0.028, "lens", 14) for s in (-1, 1)]]
join(parts, "parka_hood")
parts = [box((0, 1.32, -0.24), (0.32, 0.42, 0.16), "pack"), box((0, 1.12, -0.24), (0.34, 0.06, 0.18), "strap")]
for s in (-1, 1):
    parts += [cyl((s * 0.1, 1.15, -0.34), (s * 0.1, 1.5, -0.34), 0.05, "steel", 12), cyl((s * 0.1, 1.5, -0.34), (s * 0.1, 1.56, -0.34), 0.035, "cap_blue", 10),
              tube([(s * 0.12, 1.5, -0.16), (s * 0.15, 1.6, 0.0), (s * 0.13, 1.45, 0.17), (s * 0.12, 1.15, 0.16)], 0.016, "strap")]
parts.append(cyl((0.12, 1.55, -0.2), (0.14, 2.1, -0.24), 0.008, "steel", 6))
join(parts, "parka_pack")
join([cyl((0, -0.12, 0), (0, 0.12, 0), 0.06, "steel", 14), cyl((0, 0.12, 0), (0, 0.17, 0), 0.04, "cap_blue", 12), cyl((0, -0.02, 0), (0, 0.02, 0), 0.062, "cap_blue", 14)], "ln2_canister")

# ===================================================================== 遠古巨獸
# body: a massive shaggy trunk with a shoulder hump, ice crusted on the flanks
body = lump((0, 3.5, 0), (1.9, 1.75, 3.5), "ancient_fur", 0.12, 3, 0.5, True)
parts = [body, lump((0, 4.6, 1.3), (1.5, 0.9, 1.6), "ancient_fur", 0.15, 2, 1.5, True)]
for k in range(70):  # long fur hanging off the flanks and belly
    z = random.uniform(-3.0, 3.0); side = random.choice((-1, 1)); y = random.uniform(2.4, 3.6)
    x = side * 1.7 * math.sqrt(max(0.05, 1 - (z / 3.6) ** 2))
    parts.append(tuft((x, y, z), (x * 1.08, y - random.uniform(0.7, 1.2), z + random.uniform(-0.2, 0.2)), random.uniform(0.18, 0.28), "ancient_fur"))
for k in range(10):  # patches of frost crust
    z = random.uniform(-2.5, 2.5); side = random.choice((-1, 1))
    parts.append(lump((side * 1.65, random.uniform(3.2, 4.4), z), (0.35, 0.4, 0.6), "frost_crust", 0.3, 1, k))
join(parts, "ancient_body")
crystals = []
for k in range(8):  # glowing crystals along the spine (the weak point)
    z = -2.2 + k * 0.6; h = random.uniform(0.6, 1.2) * (1.2 if 2 < k < 6 else 1)
    for s in ((-0.25, 0.25) if k % 2 else (0,)):
        crystals.append(cyl((s, 4.9 + (0.5 if 1 < k < 6 else 0), z), (s * 2.5 + random.uniform(-0.1, 0.1), 5.6 + h, z - 0.3), 0.22, "crystal", 6, 0.0))
join(crystals, "ancient_crystals")
# head, from the neck joint: heavy skull, trunk-like snout, curling tusks, blazing eyes
parts = [lump((0, -0.1, 1.0), (1.05, 1.1, 1.35), "ancient_fur", 0.1, 2, 2.2, True), lump((0, -0.35, 2.0), (0.6, 0.6, 0.8), "ancient_skin", 0.08, 2, 0.7, True),
         tube([(0, -0.4, 2.5), (0, -1.1, 2.9), (0, -1.9, 2.8), (0, -2.4, 2.5)], 0.32, "ancient_skin", [1, 0.85, 0.6, 0.4])]
for s in (-1, 1):
    parts += [tube([(s * 0.45, -0.6, 2.0), (s * 0.85, -1.6, 2.7), (s * 1.1, -2.0, 3.6), (s * 0.85, -1.3, 4.4)], 0.17, "ivory", [1, 0.9, 0.7, 0.3]),
              ball((s * 0.55, 0.2, 1.95), (0.16, 0.12, 0.1), "eye_glow", 10), lump((s * 0.95, 0.2, 0.6), (0.15, 0.55, 0.45), "ancient_skin", 0.1, 1, s)]
join(parts, "ancient_head")
for name, zf in (("ancient_leg_front", 1), ("ancient_leg_back", -1)):
    parts = [lump((0, -0.6, 0), (0.75, 1.0, 0.8), "ancient_fur", 0.12, 2, zf, True), cyl((0, -1.2, 0), (0, -2.7, 0.08 * zf), 0.55, "ancient_skin", 12, 0.6),
             cyl((0, -2.7, 0.1 * zf), (0, -2.95, 0.15 * zf), 0.72, "ancient_skin", 14, 0.75)]
    for k in range(10):
        a = random.uniform(0, math.tau)
        parts.append(tuft((math.sin(a) * 0.6, -0.6, math.cos(a) * 0.6), (math.sin(a) * 0.75, -1.7, math.cos(a) * 0.75), 0.18, "ancient_fur"))
    for k in range(3):
        a = (k - 1) * 0.5
        parts.append(cyl((math.sin(a) * 0.55, -2.85, 0.5 * zf + 0.2), (math.sin(a) * 0.7, -2.95, 0.8 * zf + 0.2), 0.14, "ivory", 6, 0.02))
    join(parts, name)
join([tube([(0, 0, 0), (0, -0.6, -1.0), (0, -1.6, -1.6), (0, -2.4, -1.7)], 0.35, "ancient_fur", [1, 0.8, 0.5, 0.25]),
      tuft((0, -2.2, -1.7), (0, -2.9, -1.75), 0.25, "ancient_fur")], "ancient_tail")

# ===================================================================== ice spikes (radius ~3)
parts = []
for k in range(16):
    a = random.uniform(0, math.tau); r = random.uniform(0, 2.6); h = random.uniform(1.4, 3.4) * (1.2 - r / 4)
    tip = (math.sin(a) * (r + 0.5), h, math.cos(a) * (r + 0.5))
    parts.append(cyl((math.sin(a) * r, -0.3, math.cos(a) * r), tip, random.uniform(0.25, 0.45), "ice", 6, 0.0))
parts.append(lump((0, 0.1, 0), (3.0, 0.3, 3.0), "frost_crust", 0.25, 2, 9.9))
join(parts, "ice_spikes")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"ancient_body": (0, 0, 0), "ancient_crystals": (0, 0, 0), "ancient_head": (0, 3.9, 3.3), "ancient_tail": (0, 3.7, -3.4), "ice_spikes": (7, 0, 2),
             "ice_armor_body": (-4, 0, 3), "ice_armor_head": (-4, 1.72, 3.03), "yeti_fur": (-5.5, 0, 3), "yeti_head": (-5.5, 1.72, 3.03),
             "parka_hood": (-2.5, 1.72, 3.03), "parka_pack": (-2.5, 0, 3), "ln2_canister": (-2, 0.5, 4)}
    legs = [("ancient_leg_front", 1.25, 2.9, 2.2), ("ancient_leg_back", 1.25, 2.9, -2.2)]
    for ob in list(PARTS):
        if ob.name in place:
            ob.location = B(*place[ob.name])
        for n, x, y, z in legs:
            if ob.name == n:
                ob.location = B(x, y, z); c = ob.copy(); c.data = ob.data; scene.collection.objects.link(c); c.location = B(-x, y, z)
        if ob.name in ("ice_armor_arm", "yeti_arm"): ob.location = B(0, -10, 0)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.55, 0.62, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(55), 0, math.radians(40))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 28; eye, tgt = B(9, 5, 15), B(-0.5, 2.4, 1)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
