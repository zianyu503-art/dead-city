# Costumes and gear for the 第十二關 (航空母艦) zombies of 死城突圍.
#
#   blender -b -P tools/blender/naval_zombies.py -- assets/models/navalzombie.glb [preview.png]
#
# Like fest_zombies.py these dress the game's zombie body, each piece in the frame of the joint it hangs
# from (game coordinates, +Y up, +Z the way the zombie faces):
#   head frame - the head pivot; skull centre at y 0.13, top of the skull y ~0.27, face toward +z
#   body frame - feet on the origin; chest around y 1.35, the front of the torso at z ~0.15, back at z ~-0.15
#   hand frame - the wrist; the fingers hang toward -y
# The game keeps these materials (no swapping); "led" glows.
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "navalzombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(12)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {
    "cap_white": ((0.82, 0.82, 0.78), 0.8, 0.0), "navy": ((0.03, 0.05, 0.12), 0.8, 0.0), "vest_orange": ((0.9, 0.28, 0.02), 0.6, 0.0),
    "reflect": ((0.85, 0.88, 0.9), 0.25, 0.6), "strap": ((0.05, 0.05, 0.05), 0.8, 0.0), "buckle": ((0.1, 0.1, 0.1), 0.4, 0.5),
    "shell": ((0.55, 0.12, 0.05), 0.35, 0.1), "shell_dark": ((0.28, 0.05, 0.03), 0.4, 0.1), "barnacle": ((0.7, 0.68, 0.6), 0.9, 0.0),
    "claw_tip": ((0.08, 0.05, 0.04), 0.3, 0.0), "seaweed": ((0.1, 0.22, 0.06), 0.55, 0.0), "kelp": ((0.25, 0.22, 0.06), 0.6, 0.0),
    "olive_drab": ((0.16, 0.18, 0.1), 0.75, 0.0), "metal": ((0.15, 0.15, 0.16), 0.4, 0.8), "led": ((0.2, 1.0, 0.3), 0.3, 0.0),
    "led_red": ((1.0, 0.1, 0.05), 0.3, 0.0),
}
MAT = {}
for n, (c, r, mt) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if n.startswith("led"):
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


def tube(pts, r, mat, res=4, radii=None):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 1; cu.resolution_u = res; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = B(*p); bp.handle_left_type = bp.handle_right_type = "AUTO"; bp.radius = radii[i] if radii else 1
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def shell(cy, h, rx, rz, mat, a0, a1, t=0.03, n=24):
    """A curved band around the torso: an elliptical wall from angle a0 to a1 (0 = front, +x side positive)."""
    vs, fs = [], []
    for k in range(n + 1):
        a = a0 + (a1 - a0) * k / n
        for y in (cy - h / 2, cy + h / 2):
            vs.append(B(math.sin(a) * rx, y, math.cos(a) * rz))
    for k in range(n):
        i = k * 2; fs.append((i, i + 2, i + 3, i + 1))
    me = bpy.data.meshes.new("band"); me.from_pydata(vs, [], fs)
    ob = bpy.data.objects.new("band", me); scene.collection.objects.link(ob)
    so = ob.modifiers.new("s", "SOLIDIFY"); so.thickness = t; so.offset = 1; apply_mods(ob)
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== 水兵殭屍: white dixie-cup cap (head frame) and life vest (body frame)
parts = [cyl((0, 0.215, 0.0), (0, 0.33, -0.01), 0.125, "cap_white", 24, 0.112),
         ball((0, 0.33, -0.01), (0.112, 0.022, 0.112), "cap_white", 20),
         cyl((0, 0.21, 0.0), (0, 0.25, 0.0), 0.15, "cap_white", 24, 0.142)]  # the rolled-up brim
parts.append(cyl((0, 0.212, 0.0), (0, 0.222, 0.0), 0.151, "navy", 24))
cap = join(parts, "sailor_cap")
cap.rotation_euler = (0, math.radians(-12), 0); activate(cap); bpy.ops.object.transform_apply(rotation=True)  # worn tipped back

parts = []
for s in (-1, 1):  # two puffy front panels with a gap down the middle, and the back
    parts.append(shell(1.3, 0.42, 0.215, 0.165, "vest_orange", s * 0.12, s * 1.75, 0.05))
parts.append(shell(1.3, 0.42, 0.215, 0.165, "vest_orange", 1.75, math.tau - 1.75, 0.05))
for y in (1.17, 1.43):  # reflective tape around the vest
    for s in (-1, 1):
        parts.append(shell(y, 0.035, 0.27, 0.218, "reflect", s * 0.13, s * 1.6, 0.006))
for y in (1.14, 1.3):  # buckled straps across the front gap
    parts += [box((0, y, 0.225), (0.1, 0.022, 0.012), "strap", 0), box((0, y, 0.232), (0.035, 0.03, 0.012), "buckle", 0)]
parts.append(tube([(-0.16, 1.5, 0.05), (-0.08, 1.58, -0.12), (0.08, 1.58, -0.12), (0.16, 1.5, 0.05)], 0.05, "vest_orange"))  # collar float
join(parts, "life_vest")

# ===================================================================== 深海巨蟹殭屍: chest carapace, barnacles and a giant claw
parts = []
sh = ball((0, 1.33, 0.14), (0.25, 0.3, 0.1), "shell", 28)
for v in sh.data.vertices:  # only keep the front half and roughen it
    if v.co.y > -0.02:  # Blender -y is game +z (front)
        v.co.y = -0.02
for v in sh.data.vertices:
    v.co += v.normal * 0.008 * random.uniform(-1, 1)
parts.append(sh)
for k in range(9):  # spikes around the rim
    a = (k / 8 - 0.5) * 2.6
    x, y = math.sin(a) * 0.24, 1.33 + math.cos(a) * 0.29
    parts.append(cyl((x * 0.95, y * 0.98 + 0.02, 0.16), (x * 1.25, 1.33 + (y - 1.33) * 1.25, 0.17), 0.022, "shell_dark", 6, 0.0))
for y in (1.22, 1.33, 1.44):  # ridges across the plate
    parts.append(tube([(-0.17, y - 0.02, 0.2), (0, y + 0.02, 0.24), (0.17, y - 0.02, 0.2)], 0.012, "shell_dark"))
join(parts, "crab_shell")

parts = []
for k in range(26):  # barnacle clusters over the back and shoulders
    a = random.uniform(math.pi * 0.55, math.pi * 1.45); y = random.uniform(1.05, 1.6)
    x, z = math.sin(a) * 0.2, math.cos(a) * 0.16
    if k > 20:
        x, y, z = random.choice((-1, 1)) * random.uniform(0.2, 0.3), random.uniform(1.55, 1.62), random.uniform(-0.06, 0.06)
    r = random.uniform(0.018, 0.035); out = Vector((x, 0, z)).normalized() if k <= 20 else Vector((0, 1, 0))
    p0 = Vector((x, y, z)); p1 = p0 + out * r * 1.4
    parts += [cyl(tuple(p0), tuple(p1), r, "barnacle", 8, r * 0.55), cyl(tuple(p1 - out * 0.004), tuple(p1 + out * 0.002), r * 0.35, "claw_tip", 8)]
join(parts, "barnacles")

parts = [ball((0, -0.08, 0.02), (0.1, 0.13, 0.09), "shell", 20),                    # wrist joint
         ball((0, -0.3, 0.05), (0.17, 0.24, 0.13), "shell", 24)]                    # the swollen palm
fixed = [(0.08, -0.48, 0.06), (0.17, -0.62, 0.08), (0.16, -0.78, 0.1), (0.09, -0.88, 0.11)]  # fixed finger, curving in
moving = [(-0.08, -0.46, 0.05), (-0.18, -0.6, 0.06), (-0.17, -0.74, 0.08), (-0.1, -0.83, 0.09)]  # movable finger
parts += [tube(fixed, 0.07, "shell", 6, [1, 0.85, 0.55, 0.15]), tube(moving, 0.06, "shell", 6, [1, 0.8, 0.5, 0.15]),
          ball(fixed[-1], 0.018, "claw_tip", 8), ball(moving[-1], 0.016, "claw_tip", 8)]
for pts, s in ((fixed, -1), (moving, 1)):  # teeth on the inner edges
    for k in range(1, 3):
        a, b = Vector(pts[k]), Vector(pts[k + 1])
        for f in (0.2, 0.6):
            p = a.lerp(b, f)
            parts.append(cyl(tuple(p), tuple(p + Vector((s * 0.05, 0, 0))), 0.014, "shell_dark", 5, 0.0))
for k in range(6):
    parts.append(ball((random.uniform(-0.12, 0.12), random.uniform(-0.18, -0.4), 0.05 + random.choice((-1, 1)) * 0.11), 0.022, "barnacle", 8))
join(parts, "crab_claw")

# ===================================================================== 溺死者: seaweed hanging from the head (head frame)
parts = []
for k in range(14):
    a = (k / 14) * math.tau; x, z = math.sin(a) * 0.1, math.cos(a) * 0.1 - 0.01
    if z > 0.06 and abs(x) < 0.05:
        continue  # leave the face clear
    top = (x * 0.6, 0.27, z * 0.6)
    drop = random.uniform(0.25, 0.42)
    pts = [top, (x * 1.35, 0.18, z * 1.35), (x * 1.5 + random.uniform(-0.03, 0.03), 0.18 - drop * 0.5, z * 1.5), (x * 1.6, 0.18 - drop, z * 1.6 + random.uniform(-0.03, 0.03))]
    parts.append(tube(pts, 0.014, "seaweed" if k % 3 else "kelp", 4, [1, 1.3, 1.1, 0.5]))
for k in range(4):  # a couple of flat kelp blades over the shoulders
    s = 1 if k % 2 else -1
    parts.append(tube([(0.08 * s, 0.24, -0.04), (0.17 * s, 0.1, -0.06), (0.21 * s, -0.1, -0.04 + k * 0.02), (0.22 * s, -0.25, 0.0)], 0.02, "kelp", 4, [0.5, 1, 1, 0.6]))
join(parts, "seaweed")

# ===================================================================== 電子戰殭屍: jammer backpack (body frame) and headset (head frame)
parts = [box((0, 1.3, -0.25), (0.34, 0.44, 0.17), "olive_drab", 0.1), box((0, 1.12, -0.25), (0.36, 0.06, 0.19), "metal", 0.2),
         box((0.0, 1.38, -0.337), (0.22, 0.14, 0.01), "metal", 0)]
for k in range(4):  # a row of status lights
    parts.append(box((-0.07 + k * 0.045, 1.38, -0.343), (0.02, 0.02, 0.006), "led" if k % 3 else "led_red", 0))
for x, h in ((-0.12, 0.55), (0.0, 0.42), (0.12, 0.6)):  # whip antennas
    parts += [cyl((x, 1.52, -0.27), (x, 1.52 + h, -0.3), 0.007, "metal", 6), ball((x, 1.52 + h, -0.3), 0.012, "led_red", 8)]
parts.append(box((0.13, 1.6, -0.26), (0.05, 0.16, 0.05), "metal", 0.2))  # a dish antenna mount
parts.append(cyl((0.13, 1.7, -0.24), (0.13, 1.72, -0.18), 0.06, "metal", 16, 0.01))
for s in (-1, 1):  # shoulder straps
    parts.append(tube([(0.12 * s, 1.5, -0.17), (0.14 * s, 1.6, -0.03), (0.13 * s, 1.55, 0.13), (0.12 * s, 1.25, 0.16), (0.14 * s, 1.1, 0.12)], 0.012, "strap"))
parts.append(tube([(0.1, 1.45, -0.18), (0.25, 1.3, -0.1), (0.24, 1.1, 0.05), (0.08, 0.95, 0.12)], 0.009, "strap"))  # a cable to the hand unit
join(parts, "jammer_pack")

parts = [tube([(-0.125, 0.13, 0.0), (-0.11, 0.25, 0.0), (0, 0.295, 0.0), (0.11, 0.25, 0.0), (0.125, 0.13, 0.0)], 0.012, "strap")]
for s in (-1, 1):
    parts += [cyl((0.115 * s, 0.13, 0.0), (0.15 * s, 0.13, 0.0), 0.05, "olive_drab", 16), cyl((0.15 * s, 0.13, 0.0), (0.155 * s, 0.13, 0.0), 0.04, "metal", 16)]
parts += [tube([(0.14, 0.11, 0.02), (0.13, 0.06, 0.09), (0.06, 0.05, 0.14)], 0.006, "metal"), ball((0.05, 0.05, 0.145), 0.014, "strap", 8)]
join(parts, "headset")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    layout = {"sailor_cap": (-1.5, 1.4), "life_vest": (-1.5, 0), "crab_shell": (-0.5, 0), "barnacles": (-0.5, 0), "crab_claw": (0.3, 1.2),
              "seaweed": (0.6, 1.5), "jammer_pack": (1.4, 0), "headset": (1.4, 1.5)}
    for ob in PARTS:
        x, y = layout.get(ob.name, (0, 0))
        ob.location = B(x, y, 0); ob.rotation_euler = (0, 0, math.radians(30))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 4.2
    cam.location = B(0, 1.0, 8); cam.rotation_euler = (B(0, 1.0, 0) - B(0, 1.0, 8)).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((3, 5, 6), 1500), ((-4, 2, 4), 600)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 5; l.location = B(*loc)
        l.rotation_euler = (B(0, 1, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
