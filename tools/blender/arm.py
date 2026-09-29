# Builds the first-person forearm + gloved hand for 死城突圍 and exports it as glTF.
#
#   blender -b -P tools/blender/arm.py -- assets/models/arm.glb [preview.png]
#
# The hand grips a bar of radius GRIP that runs along X through the origin; that
# point is placed on the weapon's grip in the game. The forearm runs toward -Y and
# the back of the hand faces +Z, which after glTF's Y-up conversion becomes
# "forearm toward +Z, back of the hand toward +Y" in three.js (Object3D.lookAt aims +Z).
import bpy, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "arm.glb"
PREVIEW = argv[1] if len(argv) > 1 else None

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
GRIP = 0.018


# ---------------------------------------------------------------- materials
def weave_image(name, base, W=128):
    """Tight fabric weave with a little mottling, for the jacket sleeve."""
    img = bpy.data.images.new(name, W, W)
    px = [0.0] * (W * W * 4)
    import random
    random.seed(4)
    for y in range(W):
        for x in range(W):
            warp = 0.06 * math.sin(x * 1.9) * math.sin(y * 0.35)
            weft = 0.05 * math.sin(y * 1.9) * math.sin(x * 0.35)
            m = 0.04 * math.sin(x * 0.05 + y * 0.08) + random.uniform(-0.025, 0.025)
            k = 1 + warp + weft + m
            i = (y * W + x) * 4
            px[i:i + 4] = (base[0] * k, base[1] * k, base[2] * k, 1)
    img.pixels.foreach_set(px)
    img.pack()
    return img


def material(name, color, roughness=0.6, metallic=0.0, image=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    if image:
        t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = image
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    return m


M_SLEEVE = material("sleeve", (1, 1, 1), 0.92, image=weave_image("weave", (0.075, 0.08, 0.088)))
M_CUFF = material("cuff", (0.05, 0.053, 0.058), 0.9)
M_GLOVE = material("glove", (0.045, 0.038, 0.032), 0.62)
M_PAD = material("pad", (0.018, 0.018, 0.02), 0.85)
M_STRAP = material("strap", (0.11, 0.11, 0.115), 0.95)


def smooth(ob, subdiv=0):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if subdiv:
        mod = ob.modifiers.new("sub", "SUBSURF"); mod.levels = subdiv; mod.render_levels = subdiv
    bpy.ops.object.shade_smooth()
    ob.select_set(False)


def capsule_between(name, a, b, r, mat, r2=None):
    """A rounded limb segment from a to b (used for finger bones)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=1, depth=1, location=(a + b) / 2)
    ob = bpy.context.object; ob.name = name
    ob.scale = (r, r, d.length)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    ob.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    smooth(ob)
    for p, rr in ((a, r), (b, r2 or r)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=rr, location=p)
        j = bpy.context.object; j.name = name + "_joint"; j.data.materials.append(mat); smooth(j)
    return ob


def rounded_block(name, size, loc, mat, rot=(0, 0, 0), subdiv=1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.object; ob.name = name
    ob.scale = size
    ob.data.materials.append(mat)
    bpy.ops.object.transform_apply(scale=True)
    bev = ob.modifiers.new("bev", "BEVEL"); bev.width = min(size) * 0.35; bev.segments = 3
    smooth(ob, subdiv)
    return ob


# ---------------------------------------------------------------- sleeve with cloth wrinkles
bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=1, depth=0.46, location=(0, -0.31, 0.03), rotation=(math.pi / 2, 0, 0))
sleeve = bpy.context.object; sleeve.name = "sleeve"
sleeve.data.materials.append(M_SLEEVE)
sleeve.scale = (0.055, 0.052, 1)
bpy.ops.object.transform_apply(rotation=True, scale=True)
# taper toward the wrist
for v in sleeve.data.vertices:
    k = (v.co.y + 0.08) / -0.46                  # 0 at the cuff end, 1 at the elbow end
    s = 0.86 + 0.14 * max(0, min(1, k))
    v.co.x *= s; v.co.z = 0.03 + (v.co.z - 0.03) * s
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.subdivide(number_cuts=3); bpy.ops.object.mode_set(mode="OBJECT")
tex = bpy.data.textures.new("folds", "CLOUDS"); tex.noise_scale = 0.045; tex.noise_depth = 0
disp = sleeve.modifiers.new("folds", "DISPLACE"); disp.texture = tex; disp.strength = 0.005; disp.mid_level = 0.5
smooth(sleeve, 1)

# rolled cuff with a velcro tab
bpy.ops.mesh.primitive_torus_add(major_radius=0.049, minor_radius=0.006, major_segments=36, minor_segments=10,
                                 location=(0, -0.085, 0.03), rotation=(math.pi / 2, 0, 0))
cuff = bpy.context.object; cuff.name = "cuff"; cuff.scale = (1, 0.95, 1)
cuff.data.materials.append(M_CUFF); bpy.ops.object.transform_apply(rotation=True, scale=True); smooth(cuff)
rounded_block("cuff_tab", (0.026, 0.02, 0.005), (0.0, -0.092, 0.081), M_CUFF, subdiv=1)

# ---------------------------------------------------------------- glove
# wrist and back of the hand, resting on top of the grip
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1, depth=0.075, location=(0, -0.062, 0.03), rotation=(math.pi / 2, 0, 0))
wrist = bpy.context.object; wrist.name = "wrist"; wrist.scale = (0.044, 0.04, 1)
wrist.data.materials.append(M_GLOVE); bpy.ops.object.transform_apply(rotation=True, scale=True); smooth(wrist)
bpy.ops.mesh.primitive_torus_add(major_radius=0.0445, minor_radius=0.0055, major_segments=32, minor_segments=8,
                                 location=(0, -0.045, 0.03), rotation=(math.pi / 2, 0, 0))
strap = bpy.context.object; strap.name = "wrist_strap"; strap.scale = (1.0, 0.92, 1)
strap.data.materials.append(M_STRAP); bpy.ops.object.transform_apply(rotation=True, scale=True); smooth(strap)
rounded_block("strap_tab", (0.028, 0.016, 0.006), (0.0, -0.045, 0.073), M_STRAP, subdiv=1)

rounded_block("palm", (0.078, 0.078, 0.03), (0, 0.004, GRIP + 0.012), M_GLOVE, rot=(0.12, 0, 0))
rounded_block("heel", (0.07, 0.04, 0.03), (0, -0.03, GRIP + 0.006), M_GLOVE)
rounded_block("knuckle_pad", (0.07, 0.022, 0.012), (0, 0.03, GRIP + 0.03), M_PAD, rot=(0.25, 0, 0))
rounded_block("back_pad", (0.05, 0.03, 0.008), (0, -0.002, GRIP + 0.03), M_PAD, rot=(0.1, 0, 0))

# fingers curl over the front of the grip and underneath it
R = GRIP + 0.0095
for i, (x, length) in enumerate(((0.027, 0.86), (0.009, 1.0), (-0.009, 0.95), (-0.026, 0.78))):
    angles = [math.radians(a) for a in (38, 38 + 58 * length, 38 + 112 * length, 38 + 158 * length)]
    pts = [(x, R * math.sin(a) + 0.03 * (j == 0), R * math.cos(a) + 0.004 * (j == 0)) for j, a in enumerate(angles)]
    pts[0] = (x, 0.036, GRIP + 0.018)          # knuckle on the front edge of the palm
    radii = (0.0098, 0.0092, 0.0086, 0.0082)
    for j in range(3):
        capsule_between(f"finger{i}_{j}", pts[j], pts[j + 1], radii[j], M_GLOVE, radii[j + 1])

# thumb wraps around the far side of the grip
th = [(0.044, -0.012, GRIP + 0.008), (0.046, 0.012, 0.004), (0.036, 0.03, -0.012), (0.024, 0.042, -0.02)]
for j in range(3):
    capsule_between(f"thumb_{j}", th[j], th[j + 1], 0.011 - j * 0.0008, M_GLOVE, 0.0105 - j * 0.0008)

# ---------------------------------------------------------------- export
for ob in scene.objects:
    ob.select_set(ob.type == "MESH")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
print("exported", OUT)

if PREVIEW:
    # show the hand holding a stand-in grip bar
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=GRIP, depth=0.2, rotation=(0, math.pi / 2, 0))
    bar = bpy.context.object; bar.data.materials.append(material("bar", (0.02, 0.02, 0.02), 0.5, 0.6)); smooth(bar)
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
    cam.data.lens = 60
    target = Vector((0, -0.06, 0.01))
    cam.location = (0.34, 0.26, 0.2)
    cam.rotation_euler = (target - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    for loc, energy, size in (((0.4, 0.2, 0.5), 6, 0.6), ((-0.4, -0.2, 0.3), 2.5, 0.8), ((0.1, 0.5, -0.2), 1.5, 0.6)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = energy; l.data.size = size; l.location = loc
        l.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 900, 600
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
