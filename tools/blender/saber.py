# The red lightsaber (光劍) view model for 死城突圍.
#
#   blender -b -P tools/blender/saber.py -- assets/models/saber.glb [preview.png]
#
# Same frame as the katana: Blender +Y runs up the blade, the hilt hangs toward -Y and the
# activation switch sits on top (+Z). The emitter mouth is the origin, so the game can grow
# the blade out of it by scaling. glTF's Y-up conversion turns this into blade toward -Z in three.js.
#
# Exported objects: "saber_hilt" and "saber_blade". Material names tell the game which of its
# own materials to use (the blade glow is drawn additively in the game).
import bpy, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "saber.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
BLADE = 0.9


def mat(name, color, metal=0.0, rough=0.5, emit=None, strength=0.0, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    return m


M_CHROME = mat("saber_metal", (0.78, 0.79, 0.8), 1.0, 0.2)
M_DARK = mat("saber_dark", (0.03, 0.03, 0.035), 0.85, 0.35)
M_GRIP = mat("saber_grip", (0.015, 0.015, 0.015), 0.0, 0.7)
M_LED = mat("saber_led", (0.6, 0.02, 0.01), 0.0, 0.3, (1.0, 0.05, 0.02), 6.0)
M_CORE = mat("saber_core", (1.0, 0.9, 0.9), 0.0, 0.5, (1.0, 0.82, 0.8), 25.0)
def glow(name, color, strength, falloff, opacity):
    """Emissive shell that fades to nothing toward its silhouette, so the light looks soft."""
    m = bpy.data.materials.new(name); m.use_nodes = True; m.surface_render_method = "BLENDED"
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1); em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.5
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = falloff
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMixShader")
    op = nt.nodes.new("ShaderNodeMath"); op.operation = "MULTIPLY"; op.inputs[1].default_value = opacity
    nt.links.new(lw.outputs["Facing"], inv.inputs[1]); nt.links.new(inv.outputs[0], pw.inputs[0]); nt.links.new(pw.outputs[0], op.inputs[0])
    nt.links.new(op.outputs[0], mx.inputs[0]); nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


M_GLOW = glow("saber_glow", (1.0, 0.03, 0.012), 10.0, 1.2, 0.55)
M_HALO = glow("saber_halo", (1.0, 0.02, 0.01), 4.0, 2.5, 0.6)


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def apply_mods(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def setmat(ob, m):
    ob.data.materials.clear(); ob.data.materials.append(m); return ob


def lathe(name, profile, m, verts=48, bev=0.0):
    """Turned part: profile = [(y, radius)] around the Y axis."""
    vs, fs = [], []
    n = len(profile)
    for i, (y, r) in enumerate(profile):
        for k in range(verts):
            a = k / verts * math.tau
            vs.append((math.cos(a) * r, y, math.sin(a) * r))
    for i in range(n - 1):
        for k in range(verts):
            a, b = i * verts + k, i * verts + (k + 1) % verts
            fs.append((a, b, b + verts, a + verts))
    vs += [(0, profile[0][0], 0), (0, profile[-1][0], 0)]
    c0, c1 = len(vs) - 2, len(vs) - 1
    for k in range(verts):
        fs.append((c0, (k + 1) % verts, k))
        fs.append((c1, (n - 1) * verts + k, (n - 1) * verts + (k + 1) % verts))
    me = bpy.data.meshes.new(name); me.from_pydata(vs, [], fs); me.validate()
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    if bev:
        bm = ob.modifiers.new("b", "BEVEL"); bm.width = bev; bm.segments = 2; bm.limit_method = "ANGLE"; apply_mods(ob)
    return setmat(ob, m)


def box(c, s, m, bev=0.25, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    ob = bpy.context.object; ob.scale = s
    activate(ob); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bev:
        b = ob.modifiers.new("b", "BEVEL"); b.width = min(s) * bev; b.segments = 2; apply_mods(ob)
    activate(ob); bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return setmat(ob, m)


def cut(ob, cutters):
    for c in cutters:
        m = ob.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = c; m.solver = "EXACT"
        apply_mods(ob); bpy.data.objects.remove(c)
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    return ob


# ---------------------------------------------------------------- hilt (28 cm, two hands)
parts = []
# emitter: a flared crown with six vents, a lip ring and a dark bore the blade comes out of
emitter = lathe("emitter", [(-0.002, 0.0125), (0.0, 0.0205), (-0.006, 0.0215), (-0.03, 0.0185), (-0.042, 0.0172), (-0.048, 0.0165)], M_CHROME, 64, 0.0006)
cut(emitter, [box((math.cos(a) * 0.021, -0.014, math.sin(a) * 0.021), (0.007, 0.022, 0.007), M_CHROME, 0, (0, -a, 0)) for a in [k / 6 * math.tau + 0.26 for k in range(6)]])
parts += [emitter, lathe("bore", [(0.0005, 0.0), (0.0005, 0.0122), (-0.012, 0.0115), (-0.012, 0.0)], M_DARK, 32)]
parts.append(lathe("collar", [(-0.048, 0.0178), (-0.052, 0.0182), (-0.056, 0.0178), (-0.06, 0.0168)], M_DARK, 48, 0.0004))
# control box: switch housing, a red status LED and a pair of grub screws
parts.append(lathe("control", [(-0.06, 0.0168), (-0.112, 0.0168)], M_CHROME, 48))
parts.append(box((0, -0.084, 0.0185), (0.012, 0.036, 0.008), M_DARK, 0.3))
parts.append(box((0, -0.078, 0.0225), (0.007, 0.012, 0.004), M_CHROME, 0.4))   # activation button
parts.append(box((0, -0.096, 0.0222), (0.004, 0.005, 0.002), M_LED, 0.4))        # status LED
for sx in (-1, 1):
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.0022, depth=0.003, location=(sx * 0.0168, -0.07, 0), rotation=(0, math.pi / 2, 0))
    parts.append(setmat(bpy.context.object, M_DARK))
for y in (-0.064, -0.108):
    parts.append(lathe("ring", [(y + 0.0018, 0.0168), (y + 0.0012, 0.0176), (y - 0.0012, 0.0176), (y - 0.0018, 0.0168)], M_DARK, 48))
# grip: black rubber sleeve with raised ribs
parts.append(lathe("grip", [(-0.112, 0.0172), (-0.116, 0.018), (-0.232, 0.018), (-0.236, 0.0172)], M_GRIP, 48, 0.0008))
for k in range(8):
    a = k / 8 * math.tau
    parts.append(box((math.cos(a) * 0.0186, -0.174, math.sin(a) * 0.0186), (0.0035, 0.108, 0.0035), M_GRIP, 0.4, (0, -a, 0)))
# power cell and pommel with a belt ring
parts.append(lathe("cell", [(-0.236, 0.0172), (-0.242, 0.0178), (-0.262, 0.0178), (-0.268, 0.0186), (-0.276, 0.0184), (-0.282, 0.016), (-0.284, 0.011)], M_CHROME, 64, 0.0005))
parts.append(lathe("pommel_band", [(-0.248, 0.0182), (-0.256, 0.0182)], M_DARK, 48))
bpy.ops.mesh.primitive_torus_add(major_radius=0.007, minor_radius=0.0016, location=(0, -0.29, 0), rotation=(0, 0, math.pi / 2))
parts.append(setmat(bpy.context.object, M_CHROME))
hilt = join(parts, "saber_hilt")

# ---------------------------------------------------------------- blade: white-hot core inside two glow shells
blade = [lathe("core", [(0.0, 0.0092)] + [(BLADE - 0.012 + 0.012 * math.sin(k / 6 * math.pi / 2), 0.0092 * math.cos(k / 6 * math.pi / 2)) for k in range(7)], M_CORE, 24),
         lathe("glow", [(-0.004, 0.0165)] + [(BLADE + 0.012 * math.sin(k / 8 * math.pi / 2) - 0.004, 0.0165 * math.cos(k / 8 * math.pi / 2)) for k in range(9)], M_GLOW, 32),
         lathe("halo", [(-0.006, 0.03)] + [(BLADE + 0.02 * math.sin(k / 8 * math.pi / 2) - 0.004, 0.03 * math.cos(k / 8 * math.pi / 2)) for k in range(9)], M_HALO, 32)]
blade = join(blade, "saber_blade")

for ob in scene.objects:
    ob.select_set(ob.name in ("saber_hilt", "saber_blade"))
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
print("exported", OUT, len(hilt.data.polygons), len(blade.data.polygons))

if PREVIEW:
    root = bpy.data.objects.new("root", None); scene.collection.objects.link(root)
    hilt.parent = root; blade.parent = root
    root.rotation_euler = (math.radians(90), math.radians(50), 0)  # blade up and to the right, switch toward the camera
    root.location = (0, 0, 0)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.006, 0.006, 0.008, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 50
    target = Vector((0.27, 0, 0.21))
    cam.location = target + Vector((0, -2.05, 0.05)); cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    for loc, e, col in (((0.6, -0.8, 0.8), 25, (1, 1, 1)), ((-0.6, -0.4, -0.3), 8, (0.8, 0.85, 1))):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = e; l.data.size = 0.6; l.data.color = col; l.location = loc
        l.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    # a glowing hilt close-up beside the full saber
    scene.render.engine = "CYCLES"; scene.cycles.samples = 64; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "Standard"  # keeps the red saturated
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
    # close-up of the hilt
    hilt_mid = root.matrix_world @ Vector((0, -0.14, 0))
    cam.data.lens = 100; cam.location = hilt_mid + Vector((0.02, -0.75, 0.12))
    cam.rotation_euler = (hilt_mid - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = PREVIEW.replace(".png", "_hilt.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath)
