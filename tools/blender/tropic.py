# The 熱帶火山島 of 死城突圍's level 15 (see CONTEXT.md, .scratch/level-15/spec.md).
#
#   blender -b -P tools/blender/tropic.py -- assets/models/tropic.glb [preview.png]
#
# Game coordinates (+Y up, front toward +Z); each piece stands on its own origin and the game lays them out.
# Untextured, so exported without UVs.
#   palm, bush, bungalow (thatched hut on stilts, steps toward +Z), beach_bar, umbrella, deckchair, tender (the landing boat),
#   totem, lava_rock (cover), rock_wall (a 10 m stretch of basalt cliff, inner face toward +Z), lava_bank (rocks along the lava),
#   bridge (a stone slab bridge 4 m wide spanning 10 m along Z), geo_lab (geothermal station with pipes and a steam vent),
#   volcano (the distant cone, ~130 m tall, its crater glowing)
import bpy, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "tropic.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(15)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, emission)
    "trunk": ((0.32, 0.22, 0.13), 0.9, 0.0, 0), "frond": ((0.12, 0.38, 0.08), 0.7, 0.0, 0), "frond_dark": ((0.06, 0.25, 0.06), 0.75, 0.0, 0),
    "coconut": ((0.25, 0.16, 0.06), 0.6, 0.0, 0), "thatch": ((0.62, 0.48, 0.22), 0.95, 0.0, 0), "wood": ((0.38, 0.24, 0.12), 0.8, 0.0, 0),
    "wood_dark": ((0.18, 0.11, 0.06), 0.85, 0.0, 0), "cloth_red": ((0.7, 0.1, 0.08), 0.8, 0.0, 0), "cloth_white": ((0.86, 0.84, 0.78), 0.8, 0.0, 0),
    "cloth_teal": ((0.05, 0.5, 0.5), 0.8, 0.0, 0), "boat": ((0.8, 0.8, 0.78), 0.5, 0.1, 0), "boat_stripe": ((0.1, 0.25, 0.6), 0.5, 0.1, 0),
    "basalt": ((0.09, 0.08, 0.08), 0.9, 0.0, 0), "basalt_light": ((0.2, 0.18, 0.17), 0.9, 0.0, 0), "lava_glow": ((1.0, 0.35, 0.05), 0.4, 0.0, 6.0),
    "concrete": ((0.5, 0.5, 0.48), 0.9, 0.0, 0), "pipe": ((0.55, 0.57, 0.6), 0.35, 0.9, 0), "pipe_rust": ((0.45, 0.2, 0.08), 0.6, 0.5, 0),
    "hazard": ((0.75, 0.55, 0.05), 0.6, 0.1, 0), "window": ((0.1, 0.15, 0.2), 0.1, 0.5, 0), "paint_tiki": ((0.7, 0.2, 0.05), 0.8, 0.0, 0),
    "volcano": ((0.16, 0.13, 0.12), 0.95, 0.0, 0), "volcano_ash": ((0.3, 0.27, 0.25), 0.95, 0.0, 0),
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


def box(c, s, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot)
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=10, r1=None):
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


def tube(pts, r, mat, radii=None, res=3):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat, True)


def leaf(base, ang, length, droop, mat, width=0.5):
    """A palm frond: a strip arching out from the crown and drooping, built as a bent quad strip."""
    vs, fs = [], []; n = 6
    dx, dz = math.sin(ang), math.cos(ang)
    for k in range(n + 1):
        t = k / n; d = length * t; y = base[1] + math.sin(t * math.pi * 0.55) * length * 0.25 - droop * t * t
        w = width * math.sin(math.pi * min(0.98, t * 0.9 + 0.1))
        cx, cz = base[0] + dx * d, base[2] + dz * d
        vs += [B(cx - dz * w, y, cz + dx * w), B(cx + dz * w, y - 0.05, cz - dx * w)]
    for k in range(n):
        i = k * 2; fs.append((i, i + 1, i + 3, i + 2))
    me = bpy.data.meshes.new("leaf"); me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new("leaf", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = 0.04; activate(ob); bpy.ops.object.modifier_apply(modifier="s")
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== palm and bush
top = (1.2, 9.0, 0.4)
parts = [tube([(0, 0, 0), (0.3, 3, 0.1), (0.9, 6, 0.25), top], 0.28, "trunk", [1.3, 1.0, 0.85, 0.7])]
for k in range(9):
    parts.append(leaf(top, k / 9 * math.tau + random.uniform(-0.15, 0.15), random.uniform(3.2, 4.2), random.uniform(1.6, 2.4), "frond" if k % 2 else "frond_dark"))
for k in range(4):
    a = k / 4 * math.tau; parts.append(ball((top[0] + math.sin(a) * 0.3, top[1] - 0.35, top[2] + math.cos(a) * 0.3), 0.2, "coconut", 8))
join(parts, "palm")
parts = []
for k in range(7):
    a = random.uniform(0, math.tau)
    parts.append(leaf((0, 0.1, 0), a, random.uniform(1.0, 1.6), 0.5, "frond_dark" if k % 2 else "frond", 0.35))
parts.append(lump((0, 0.5, 0), (0.8, 0.6, 0.8), "frond_dark", 0.35, 1, 2.0))
join(parts, "bush")

# ===================================================================== resort: thatched bungalow, beach bar, umbrella, deck chair, totem
parts = [box((0, 1.0, 0), (6, 0.2, 5), "wood")]
for x in (-2.7, 2.7):
    for z in (-2.2, 2.2):
        parts.append(cyl((x, 0, z), (x, 1.0, z), 0.12, "wood_dark", 8))
parts += [box((0, 2.3, 0), (5.4, 2.4, 4.4), "wood"), box((0, 1.9, 2.21), (1.0, 1.6, 0.05), "wood_dark"),
          *[box((s * 1.6, 2.4, 2.21), (1.0, 0.8, 0.05), "window") for s in (-1, 1)]]
for k in range(3):
    parts.append(box((0, 0.75 - k * 0.3, 2.9 + k * 0.35), (1.2, 0.08, 0.35), "wood"))
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=4.8, radius2=0, depth=2.6, location=B(0, 4.8, 0), rotation=(0, 0, math.pi / 4))
roof = bpy.context.object; roof.scale = (1.15, 1.0, 1); parts.append(settle(roof, "thatch"))
join(parts, "bungalow")
parts = [box((0, 0.55, 0), (5, 1.1, 1.0), "wood"), box((0, 1.15, 0), (5.4, 0.1, 1.3), "wood_dark")]
for x in (-2.4, 2.4):
    for z in (-1.2, 1.2):
        parts.append(cyl((x, 0, z), (x, 2.8, z), 0.1, "wood_dark", 8))
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=4.0, radius2=0, depth=1.4, location=B(0, 3.4, 0), rotation=(0, 0, math.pi / 4))
r = bpy.context.object; r.scale = (1.25, 0.65, 1); parts.append(settle(r, "thatch"))
for x in (-1.6, 0, 1.6):
    parts += [cyl((x, 0, 1.2), (x, 0.75, 1.2), 0.05, "wood_dark", 6), cyl((x, 0.75, 1.2), (x, 0.8, 1.2), 0.25, "wood", 10)]
join(parts, "beach_bar")
join([cyl((0, 0, 0), (0, 2.4, 0), 0.04, "wood", 6), cyl((0, 2.2, 0), (0, 2.6, 0), 1.6, "cloth_red", 12, 0.05),
      cyl((0, 2.19, 0), (0, 2.21, 0), 1.6, "cloth_white", 12)], "umbrella")
join([box((0, 0.3, 0), (0.7, 0.06, 1.4), "cloth_teal"), box((0, 0.55, -0.85), (0.7, 0.06, 0.6), "cloth_teal", (math.radians(55), 0, 0)),
      *[cyl((sx * 0.32, 0, z), (sx * 0.32, 0.3, z), 0.02, "wood_dark", 6) for sx in (-1, 1) for z in (-0.6, 0.6)]], "deckchair")
parts = [cyl((0, 0, 0), (0, 3.2, 0), 0.45, "wood", 10)]
for k, y in enumerate((0.7, 1.6, 2.5)):
    parts += [box((0, y, 0.42), (0.6, 0.5, 0.12), "paint_tiki" if k % 2 else "wood_dark"), *[box((s * 0.18, y + 0.1, 0.48), (0.12, 0.08, 0.04), "cloth_white") for s in (-1, 1)]]
parts.append(box((0, 3.3, 0), (1.3, 0.12, 0.3), "wood_dark"))
join(parts, "totem")

# ===================================================================== the landing boat, beached (bow toward -Z, up the sand)
parts = [lump((0, 0.55, 0), (1.2, 0.55, 3.0), "boat", 0.05, 2, 1.0), box((0, 1.05, 0.5), (2.2, 0.1, 4.5), "boat"),
         box((0, 0.75, 0), (2.42, 0.18, 5.5), "boat_stripe"), box((0, 1.5, 1.2), (1.2, 0.8, 1.0), "boat"), box((0, 1.7, 0.69), (1.0, 0.4, 0.04), "window"),
         cyl((0, 0.6, 3.0), (0, 0.6, 3.5), 0.15, "pipe", 8)]
join(parts, "tender")

# ===================================================================== volcanic rocks: cover, cliff stretches, lava banks
join([lump((0, 1.0, 0), (1.6, 1.2, 1.4), "basalt", 0.3, 2, 1.7), lump((0.9, 0.5, 0.7), (0.8, 0.6, 0.8), "basalt_light", 0.35, 1, 3.1)], "lava_rock")
parts = []
for k in range(5):
    x = -4 + k * 2 + random.uniform(-0.4, 0.4); h = random.uniform(7, 12)
    parts.append(lump((x, h / 2, -random.uniform(1, 2)), (1.8, h / 2, 2.0), "basalt" if k % 2 else "basalt_light", 0.3, 1, k * 1.7))
join(parts, "rock_wall")
join([lump((0, 0.25, 0), (1.3, 0.45, 1.0), "basalt", 0.35, 1, 4.4), lump((0.8, 0.2, 0.3), (0.6, 0.35, 0.5), "basalt_light", 0.35, 1, 6.6)], "lava_bank")

# ===================================================================== stone bridge over the lava (4 wide, spans Z -5..5)
parts = [box((0, 0.12, 0), (4, 0.24, 10.4), "basalt_light")]
for s in (-1, 1):
    parts.append(box((s * 1.9, 0.6, 0), (0.25, 0.8, 10.4), "basalt"))
    for z in (-4.8, 4.8):
        parts.append(box((s * 1.9, 0.75, z), (0.5, 1.4, 0.5), "basalt"))
join(parts, "bridge")

# ===================================================================== geothermal station
parts = [box((0, 2, 0), (10, 4, 7), "concrete"), box((0, 4.1, 0), (10.4, 0.2, 7.4), "basalt"), box((0, 0.35, 3.52), (10, 0.7, 0.05), "hazard"),
         box((-2, 1.3, 3.52), (1.4, 2.6, 0.05), "wood_dark"), *[box((x, 2.6, 3.52), (1.4, 0.9, 0.05), "window") for x in (1.2, 3.4)]]
for k in range(3):  # pipes running out to the steam vent
    y = 1.0 + k * 0.6
    parts += [cyl((5, y, -1 + k), (9, y, -1 + k), 0.18, "pipe_rust" if k % 2 else "pipe", 10), cyl((9, y, -1 + k), (9, 0, -1 + k), 0.18, "pipe", 10)]
parts += [cyl((9, 0, 1), (9, 3.2, 1), 0.6, "pipe", 12, 0.4), cyl((-3, 4.2, -2), (-3, 7, -2), 0.25, "pipe", 10), box((3, 4.6, -1.5), (2.2, 0.8, 1.5), "pipe")]
join(parts, "geo_lab")

# ===================================================================== the volcano in the distance (base radius ~150, ~130 high, origin at its foot)
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=150, radius2=26, depth=130, location=B(0, 65, 0), end_fill_type="NOTHING")
cone = bpy.context.object
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.subdivide(number_cuts=6); bpy.ops.object.mode_set(mode="OBJECT")
for v in cone.data.vertices:
    p = cone.matrix_world @ v.co; g = Vector((p.x, p.z, -p.y))
    v.co.z += 6 * pnoise(Vector((g.x * 0.03, g.z * 0.03, 0.5))); r = math.hypot(v.co.x, v.co.y)
    v.co.x *= 1 + 0.08 * pnoise(Vector((g.x * 0.02, g.y * 0.04, g.z * 0.02))); v.co.y *= 1 + 0.08 * pnoise(Vector((g.z * 0.02, g.y * 0.04, g.x * 0.02)))
parts = [settle(cone, "volcano", True)]
bpy.ops.mesh.primitive_circle_add(vertices=32, radius=22, fill_type="TRIFAN", location=B(0, 127, 0)); parts.append(settle(bpy.context.object, "lava_glow"))
for k in range(5):  # glowing lava streams down the flanks
    a = (k / 5 - 0.5) * 1.6 + math.pi
    pts = [(math.sin(a) * 24, 128, math.cos(a) * 24), (math.sin(a + 0.1) * 70, 80, math.cos(a + 0.1) * 70), (math.sin(a + 0.15) * 120, 25, math.cos(a + 0.15) * 120)]
    parts.append(tube(pts, 2.2, "lava_glow", [1.2, 0.8, 0.4]))
parts.append(cyl((0, 0, 0), (0, 2, 0), 158, "volcano_ash", 48, 150))
join(parts, "volcano")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"palm": (-12, 0, 6), "bush": (-8, 0, 10), "bungalow": (-20, 0, -4), "beach_bar": (6, 0, 6), "umbrella": (12, 0, 12), "deckchair": (13, 0, 14),
             "totem": (-4, 0, 2), "tender": (2, 0, 16), "lava_rock": (16, 0, -2), "rock_wall": (0, 0, -24), "lava_bank": (8, 0, -8), "bridge": (-6, 0, -10),
             "geo_lab": (18, 0, -16), "volcano": (0, 0, -260)}
    for ob in PARTS:
        ob.location = B(*place.get(ob.name, (0, -50, 0)))
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0)); gp = bpy.context.object; gp.data.materials.append(MAT["thatch"])
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.6, 0.45, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 4; sun.rotation_euler = (math.radians(50), 0, math.radians(25))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 22; eye, tgt = B(4, 9, 34), B(0, 8, -40)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = 2000
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
