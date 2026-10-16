# The 地下實驗室 of 死城突圍's level 13 (see CONTEXT.md, .scratch/level-13/spec.md).
#
#   blender -b -P tools/blender/lab.py -- assets/models/lab.glb [preview.png]
#
# Game coordinates (+Y up, front toward +Z). Every piece stands on its own origin; the game lays them out and
# instances the repeated ones. The ceiling is at y 7.2. Untextured, so exported without UVs.
#   lab_wall       a 6 m concrete wall panel with a hazard-striped skirting, pipes and a vent, face toward +Z
#   lab_light      a ceiling light panel (hangs from y 0 down)
#   lab_pillar     a square pillar with striped corner guards, 7.2 m
#   lab_tank       the 收容槽's base, top ring and pipes;  lab_tank_glass  its glass;  lab_tank_fluid  the green fluid and the figure inside
#   lab_tank_broken  jagged glass left on the base and the spilled fluid, shown once it bursts
#   lab_tube       a culture tube with a specimen;  lab_office  a glass-walled lab room 12 x 8 m
#   lab_rack       a server rack;  lab_arch  a decontamination arch;  lab_elevator  the freight lift's doors;  lab_beacon  a red alarm light
import bpy, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "lab.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(13)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, alpha, emission)
    "concrete": ((0.32, 0.33, 0.34), 0.9, 0.0, 1, 0), "concrete_dark": ((0.16, 0.17, 0.18), 0.9, 0.0, 1, 0),
    "steel": ((0.45, 0.47, 0.5), 0.35, 0.9, 1, 0), "steel_dark": ((0.12, 0.13, 0.14), 0.45, 0.8, 1, 0),
    "hazard_yellow": ((0.75, 0.55, 0.04), 0.6, 0.1, 1, 0), "hazard_black": ((0.03, 0.03, 0.03), 0.6, 0.1, 1, 0),
    "white_panel": ((0.75, 0.77, 0.78), 0.5, 0.1, 1, 0), "light_panel": ((0.85, 0.92, 1.0), 0.3, 0.0, 1, 3.0),
    "glass": ((0.6, 0.8, 0.85), 0.05, 0.0, 0.22, 0), "fluid": ((0.2, 0.9, 0.45), 0.2, 0.0, 0.55, 0.9),
    "specimen": ((0.12, 0.08, 0.08), 0.6, 0.0, 1, 0), "rubber": ((0.04, 0.04, 0.04), 0.8, 0.0, 1, 0),
    "screen": ((0.1, 0.45, 0.6), 0.2, 0.0, 1, 1.4), "led_green": ((0.2, 1.0, 0.3), 0.3, 0.0, 1, 4.0),
    "led_red": ((1.0, 0.1, 0.05), 0.3, 0.0, 1, 4.0), "beacon": ((1.0, 0.1, 0.05), 0.3, 0.0, 1, 3.0), "pipe_red": ((0.45, 0.06, 0.04), 0.5, 0.4, 1, 0),
    "pipe_blue": ((0.1, 0.2, 0.4), 0.5, 0.4, 1, 0), "desk": ((0.55, 0.56, 0.58), 0.6, 0.2, 1, 0),
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


def settle(ob, mat):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    return ob


def box(c, s, mat, rot_y=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=(0, 0, -rot_y))
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=16, r1=None, cap=True):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2,
                                    end_fill_type="NGON" if cap else "NOTHING")
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat)


def ball(c, r, mat, segs=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat)


def text(s, c, size, mat):
    bpy.ops.object.text_add(location=B(*c), rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.object; ob.data.body = s; ob.data.size = size; ob.data.extrude = 0.01
    ob.data.align_x = "CENTER"; ob.data.align_y = "CENTER"
    activate(ob); bpy.ops.object.convert(target="MESH")
    return settle(bpy.context.object, mat)


def figure(c, h, mat):
    """A slumped humanoid silhouette (the thing in the tank), height h, centred at c."""
    x, y, z = c; k = h / 1.8
    return [ball((x, y + 1.55 * k, z), 0.13 * k, mat), cyl((x, y + 0.85 * k, z), (x, y + 1.42 * k, z), 0.2 * k, mat, 10, 0.16 * k),
            cyl((x - 0.24 * k, y + 1.35 * k, z), (x - 0.42 * k, y + 0.85 * k, z + 0.1 * k), 0.06 * k, mat, 8),
            cyl((x + 0.24 * k, y + 1.35 * k, z), (x + 0.45 * k, y + 0.9 * k, z - 0.05 * k), 0.06 * k, mat, 8),
            cyl((x - 0.1 * k, y + 0.85 * k, z), (x - 0.14 * k, y, z + 0.1 * k), 0.08 * k, mat, 8),
            cyl((x + 0.1 * k, y + 0.85 * k, z), (x + 0.16 * k, y + 0.05 * k, z - 0.05 * k), 0.08 * k, mat, 8)]


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


H = 7.2
# ===================================================================== wall panel (6 m), face toward +Z
parts = [box((0, H / 2, -0.2), (6.0, H, 0.4), "concrete"), box((0, 0.35, 0.02), (6.0, 0.7, 0.04), "hazard_yellow")]
for k in range(8):  # black chevrons on the skirting
    parts.append(box((-2.6 + k * 0.75, 0.35, 0.045), (0.28, 0.75, 0.02), "hazard_black", 0))
parts.append(box((0, 0.72, 0.03), (6.0, 0.05, 0.06), "steel_dark"))
for y, mat in ((5.6, "pipe_red"), (5.9, "pipe_blue")):  # pipes along the top
    parts.append(cyl((-3, y, 0.2), (3, y, 0.2), 0.11, mat, 10))
for x in (-2.0, 2.0):
    parts.append(box((x, 5.75, 0.1), (0.12, 0.6, 0.2), "steel_dark"))
parts += [box((1.6, 3.2, 0.03), (1.0, 0.7, 0.06), "steel_dark")] + [box((1.6, 2.93 + k * 0.11, 0.065), (0.9, 0.04, 0.02), "steel") for k in range(6)]  # vent
parts.append(box((-1.6, H - 0.35, 0.0), (6.0, 0.06, 0.06), "concrete_dark"))
join(parts, "lab_wall")

# ===================================================================== ceiling light
join([box((0, -0.08, 0), (2.5, 0.12, 0.7), "steel_dark"), box((0, -0.15, 0), (2.3, 0.02, 0.55), "light_panel")], "lab_light")

# ===================================================================== pillar
parts = [box((0, H / 2, 0), (1.2, H, 1.2), "concrete")]
for sx in (-1, 1):
    for sz in (-1, 1):
        for k in range(4):
            parts.append(box((sx * 0.6, 0.15 + k * 0.3, sz * 0.6), (0.08, 0.15, 0.08), "hazard_yellow" if k % 2 == 0 else "hazard_black"))
parts.append(box((0, H - 0.2, 0), (1.5, 0.4, 1.5), "concrete_dark"))
join(parts, "lab_pillar")

# ===================================================================== the 收容槽: base, glass, fluid with the figure, and the broken state
R, TH = 4.8, 5.4
parts = [cyl((0, 0, 0), (0, 0.8, 0), R + 0.7, "steel_dark", 40), cyl((0, 0.8, 0), (0, 0.9, 0), R + 0.35, "steel", 40),
         cyl((0, 0.8 + TH, 0), (0, 1.8 + TH, 0), R + 0.5, "steel_dark", 40), cyl((0, 0.75 + TH, 0), (0, 0.85 + TH, 0), R + 0.2, "steel", 40)]
for k in range(8):  # steel ribs holding the glass, and pipes up into the ceiling
    a = k / 8 * math.tau
    parts.append(box((math.sin(a) * (R + 0.05), 0.9 + TH / 2, math.cos(a) * (R + 0.05)), (0.25, TH, 0.25), "steel", a))
for k in range(4):
    a = (k + 0.5) / 4 * math.tau
    parts.append(cyl((math.sin(a) * 2.5, 1.8 + TH, math.cos(a) * 2.5), (math.sin(a) * 2.5, H + 0.5, math.cos(a) * 2.5), 0.3, "pipe_blue" if k % 2 else "steel", 12))
for k in range(6):  # control consoles round the base
    a = (k + 0.25) / 6 * math.tau
    parts.append(box((math.sin(a) * (R + 1.1), 0.5, math.cos(a) * (R + 1.1)), (1.0, 1.0, 0.5), "steel_dark", a))
    parts.append(box((math.sin(a) * (R + 1.33), 1.05, math.cos(a) * (R + 1.33)), (0.8, 0.45, 0.04), "screen", a))
join(parts, "lab_tank")
join([cyl((0, 0.9, 0), (0, 0.8 + TH, 0), R, "glass", 40, cap=False)], "lab_tank_glass")
fl = [cyl((0, 0.9, 0), (0, 0.4 + TH, 0), R - 0.1, "fluid", 32)] + figure((0, 1.5, 0), 3.4, "specimen")
for k in range(10):  # bubbles
    fl.append(ball((random.uniform(-2.5, 2.5), random.uniform(1.5, 5.5), random.uniform(-2.5, 2.5)), random.uniform(0.06, 0.15), "fluid", 8))
join(fl, "lab_tank_fluid")
parts = [cyl((0, 0.9, 0), (0, 0.95, 0), R + 0.2, "fluid", 32)]
for k in range(22):  # jagged glass teeth left in the base ring
    a = k / 22 * math.tau + random.uniform(-0.05, 0.05); h = random.uniform(0.3, 1.8)
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.35, radius2=0.0, depth=h, location=B(math.sin(a) * R, 0.9 + h / 2, math.cos(a) * R))
    ob = bpy.context.object; ob.rotation_euler = (random.uniform(-0.2, 0.2), random.uniform(-0.2, 0.2), -a); parts.append(settle(ob, "glass"))
for k in range(12):  # shards on the floor
    a = random.uniform(0, math.tau); r = random.uniform(R + 1, R + 6)
    parts.append(box((math.sin(a) * r, 0.03, math.cos(a) * r), (random.uniform(0.2, 0.6), 0.03, random.uniform(0.1, 0.4)), "glass", random.uniform(0, 3)))
bpy.ops.mesh.primitive_circle_add(vertices=24, radius=R + 4, fill_type="TRIFAN", location=B(0, 0.02, 0)); ob = bpy.context.object; ob.scale = (1, 0.8, 1)
parts.append(settle(ob, "fluid"))
join(parts, "lab_tank_broken")

# ===================================================================== culture tube
parts = [cyl((0, 0, 0), (0, 0.4, 0), 0.75, "steel_dark", 20), cyl((0, 2.9, 0), (0, 3.2, 0), 0.75, "steel_dark", 20),
         cyl((0, 0.4, 0), (0, 2.9, 0), 0.6, "glass", 20, cap=False), cyl((0, 0.45, 0), (0, 2.6, 0), 0.55, "fluid", 16),
         cyl((0, 3.2, 0), (0, H, 0), 0.12, "steel", 8), box((0, 0.25, 0.72), (0.3, 0.2, 0.05), "led_green")]
parts += figure((0, 0.7, 0), 1.3, "specimen")
join(parts, "lab_tube")

# ===================================================================== glass-walled lab room 12 x 8 (closed)
W, D, RH = 12.0, 8.0, 3.2
parts = [box((0, 0.05, 0), (W, 0.1, D), "white_panel"), box((0, RH, 0), (W + 0.2, 0.2, D + 0.2), "white_panel")]
for x in (-W / 2, -W / 6, W / 6, W / 2):
    for z in (-D / 2, D / 2):
        parts.append(box((x, RH / 2, z), (0.15, RH, 0.15), "steel"))
for z in (-D / 2, D / 2):
    parts.append(box((0, RH / 2, z), (W, RH - 0.2, 0.04), "glass"))
    parts.append(box((0, 0.5, z), (W, 1.0, 0.06), "white_panel"))
for x in (-W / 2, W / 2):
    parts.append(box((x, RH / 2, 0), (0.04, RH - 0.2, D), "glass"))
    parts.append(box((x, 0.5, 0), (0.06, 1.0, D), "white_panel"))
for z in (-1.6, 1.6):  # lab benches with monitors and equipment
    parts.append(box((0, 0.9, z), (8.5, 0.08, 1.2), "desk")); parts.append(box((0, 0.45, z), (8.3, 0.9, 1.0), "white_panel"))
    for x in (-3, -0.5, 2.5):
        parts += [box((x, 1.25, z - 0.3 * (1 if z > 0 else -1)), (0.6, 0.4, 0.04), "screen"), box((x, 1.0, z), (0.08, 0.2, 0.08), "steel_dark")]
    parts += [cyl((-1.8, 0.94, z), (-1.8, 1.3, z), 0.08, "glass", 10), cyl((1.2, 0.94, z), (1.2, 1.15, z), 0.12, "fluid", 10)]
join(parts, "lab_office")

# ===================================================================== server rack
parts = [box((0, 1.1, 0), (0.8, 2.2, 1.2), "steel_dark"), box((0, 1.1, 0.605), (0.7, 2.0, 0.02), "rubber")]
for k in range(10):
    y = 0.3 + k * 0.18
    parts.append(box((0, y, 0.62), (0.6, 0.12, 0.02), "steel_dark"))
    parts.append(box((random.uniform(-0.25, 0.25), y, 0.635), (0.04, 0.03, 0.01), random.choice(("led_green", "led_green", "led_red"))))
join(parts, "lab_rack")

# ===================================================================== decontamination arch (4 m), the passage along Z
parts = []
for s in (-1, 1):
    parts += [box((s * 2.1, 1.6, 0), (0.35, 3.2, 1.2), "white_panel"), box((s * 2.1, 0.2, 0), (0.4, 0.4, 1.25), "hazard_yellow")]
    for y in (0.8, 1.6, 2.4):
        parts.append(cyl((s * 1.92, y, 0), (s * 1.78, y, 0), 0.06, "steel", 8))
parts += [box((0, 3.35, 0), (4.6, 0.35, 1.2), "white_panel"), box((0, 3.35, 0.61), (3.0, 0.15, 0.02), "hazard_yellow"), box((0, 3.35, 0.62), (0.5, 0.2, 0.02), "led_red")]
join(parts, "lab_arch")

# ===================================================================== freight lift doors (on a wall, face toward +Z) with the level sign
parts = [box((0, 2.2, 0.05), (5.2, 4.4, 0.1), "steel_dark")]
for s in (-1, 1):
    parts.append(box((s * 1.25, 1.9, 0.15), (2.4, 3.8, 0.1), "steel"))
    for k in range(5):
        parts.append(box((s * 1.25, 0.5 + k * 0.7, 0.21), (2.3, 0.06, 0.02), "steel_dark"))
parts += [box((0, 4.1, 0.12), (4.8, 0.5, 0.06), "hazard_yellow"), text("B5", (0, 4.75, 0.12), 0.7, "white_panel"), text("BSL-4", (2.0, 4.75, 0.12), 0.35, "led_red")]
join(parts, "lab_elevator")

# ===================================================================== alarm beacon (on a wall bracket, face toward +Z)
join([box((0, 0, 0.08), (0.25, 0.25, 0.16), "steel_dark"), ball((0, 0, 0.28), (0.14, 0.12, 0.14), "beacon", 12), cyl((0, -0.09, 0.28), (0, -0.05, 0.28), 0.15, "steel", 12)], "lab_beacon")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"lab_tank": (0, 0, 0), "lab_tank_glass": (0, 0, 0), "lab_tank_fluid": (0, 0, 0), "lab_tube": (-9, 0, 4), "lab_office": (14, 0, -4),
             "lab_rack": (-8, 0, -6), "lab_arch": (6, 0, 10), "lab_pillar": (-12, 0, -10), "lab_wall": (0, 0, -14), "lab_elevator": (6, 0, -13.6),
             "lab_beacon": (-3, 5, -13.6), "lab_tank_broken": (0, -30, 0), "lab_light": (0, -30, 0)}
    for ob in PARTS:
        x, y, z = place.get(ob.name, (0, -30, 0)); ob.location = B(x, y, z)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    for loc, e in (((10, 14, 18), 12000), ((-14, 10, 6), 6000)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 10; l.location = B(*loc); l.rotation_euler = (B(0, 2, 0) - B(*loc)).to_track_quat("-Z", "Y").to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 20; eye, tgt = B(4, 7, 24), B(0, 2.5, -2)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
