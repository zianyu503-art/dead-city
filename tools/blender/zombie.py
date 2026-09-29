# Builds every zombie body part and accessory for 死城突圍 and exports them as one glTF.
#
#   blender -b -P tools/blender/zombie.py -- assets/models/zombie.glb [preview.png]
#
# The game animates zombies by rotating joints (shoulder, elbow, wrist, hip, knee, neck,
# jaw). Each part here is modelled in the local frame of the joint it hangs from, so the
# game only swaps geometry and keeps all of its animation, hit zones and per-type logic.
#
# Coordinates below are written in the game's (three.js) frame: +Y up, +Z forward
# (the direction the zombie faces), metres. B() converts them to Blender's Z-up frame;
# the glTF exporter converts back.
import bpy, bmesh, math, random, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "zombie.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []  # objects that get exported


def B(x, y, z):
    return Vector((x, -z, y))


def to_three(v):
    return (v.x, v.z, -v.y)


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)


def finish(ob, name, subdiv=1, smooth=True, part=True):
    """Apply modifiers, smooth, UV-unwrap and register a part for export."""
    activate(ob)
    if subdiv:
        m = ob.modifiers.new("sub", "SUBSURF"); m.levels = subdiv; m.render_levels = subdiv
    bpy.ops.object.convert(target="MESH")
    if smooth:
        bpy.ops.object.shade_smooth()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.name = name
    ob.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if part:
        PARTS.append(ob)
    return ob


def skin(name, nodes, edges, subdiv=2):
    """Organic limb/torso from a skeleton: nodes = [(x, y, z, rx, rdepth)], edges = [(i, j)] (game frame)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([B(*n[:3]) for n in nodes], edges, [])
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    sm = ob.modifiers.new("skin", "SKIN")
    sm.use_smooth_shade = True
    for i, n in enumerate(nodes):
        sv = me.skin_vertices[0].data[i]
        sv.radius = (n[3], n[4])
        sv.use_root = i == 0
    return finish(ob, name, subdiv)


def displace(ob, fn):
    """Sculpt a mesh with a displacement function working in game coordinates."""
    for v in ob.data.vertices:
        x, y, z = to_three(v.co)
        nx, ny, nz = fn(x, y, z)
        v.co = B(nx, ny, nz)
    ob.data.update()


def gauss(d2, r):
    return math.exp(-d2 / (r * r))


def rot_noise(ob, strength=0.0022, scale=0.02, seed=0):
    tex = bpy.data.textures.new(ob.name + "_n", "CLOUDS"); tex.noise_scale = scale
    m = ob.modifiers.new("rot", "DISPLACE"); m.texture = tex; m.strength = strength; m.texture_coords = "LOCAL"
    activate(ob); bpy.ops.object.modifier_apply(modifier=m.name)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = name; ob.data.name = name
    return ob


def ellipsoid(center, radii, segs=16, rings=10, name="e", rot=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=1, location=B(*center))
    ob = bpy.context.object; ob.name = name
    ob.scale = (radii[0], radii[2], radii[1])  # game (x, y, z) radii → Blender (x, depth, height)
    if rot:
        ob.rotation_euler = rot
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def cylinder(p0, p1, r0, r1=None, verts=16, name="c", cap=True):
    a, b = B(*p0), B(*p1)
    d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r0, radius2=r1 if r1 is not None else r0, depth=d.length,
                                    location=(a + b) / 2, end_fill_type="NGON" if cap else "NOTHING")
    ob = bpy.context.object; ob.name = name
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def box(center, size, name="b", bevel=0.2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*center))
    ob = bpy.context.object; ob.name = name
    ob.scale = (size[0], size[2], size[1])
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel:
        m = ob.modifiers.new("bev", "BEVEL"); m.width = min(size) * bevel; m.segments = 2
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


# =====================================================================
# HUMANOID BODY  (frames follow the game's joint layout)
# =====================================================================
# body frame: feet at the origin.  torso frame: origin at y = 1.2 in the body frame.
torso = skin("torso", [
    (0, -0.07, 0.01, 0.14, 0.1),      # waist
    (0, 0.07, 0.015, 0.155, 0.11),    # belly
    (0, 0.22, 0.0, 0.2, 0.125),       # rib cage
    (0, 0.35, -0.01, 0.19, 0.115),    # upper chest
    (-0.23, 0.36, -0.01, 0.075, 0.07),  # shoulder caps
    (0.23, 0.36, -0.01, 0.075, 0.07),
    (0, 0.45, 0.0, 0.065, 0.06),      # base of the neck
], [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5), (3, 6)], subdiv=2)


def ribs_and_collarbones(x, y, z):
    k = 0.0
    if abs(x) > 0.08 and 0.08 < y < 0.3:               # rib ridges along the flanks
        k += 0.004 * max(0, math.sin(y * 70)) * min(1, (abs(x) - 0.08) / 0.05)
    if z > 0.06 and 0.3 < y < 0.4:                     # collarbones
        k += 0.006 * gauss((y - 0.37) ** 2, 0.02)
    if z > 0.05 and -0.06 < y < 0.08:                  # sunken, starved belly
        k -= 0.008 * gauss(x * x, 0.08)
    s = 1 + k / max(0.05, math.hypot(x, z))
    return x * s, y, z * s


displace(torso, ribs_and_collarbones)
rot_noise(torso)

skin("pelvis", [
    (0, -0.12, 0.0, 0.15, 0.105),
    (0, -0.24, -0.005, 0.165, 0.115),
    (0, -0.33, 0.0, 0.14, 0.1),
], [(0, 1), (1, 2)], subdiv=2)

neck = skin("neck", [(0, 1.6, 0.015, 0.058, 0.055), (0, 1.69, 0.025, 0.055, 0.052), (0, 1.77, 0.035, 0.05, 0.048)], [(0, 1), (1, 2)])
displace(neck, lambda x, y, z: (x, y, z + (0.006 * gauss(x * x, 0.012) if z > 0.03 else 0)))  # throat tendons

# ---- head: skull and face, in the head-pivot frame (skull centre at y 0.13) ----
bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=26, radius=0.14, location=(0, 0, 0))
head = bpy.context.object


def sculpt_head(x, y, z):
    x, y, z = x, y * 1.12, z * 1.05
    if y < 0:                                   # taper to the jaw line
        k = -y / 0.157
        x *= 1 - 0.3 * k; z *= 1 - 0.08 * k
    if z < 0:
        z *= 1.1                                # long back of the skull
    if z > 0.09:
        z = 0.09 + (z - 0.09) * 0.55            # flatter face
    fx, fy = x, y
    # brow ridge, deep sockets, gaunt cheeks, cheekbones, nose, temples
    z += 0.012 * gauss(fx * fx * 0.5 + (fy - 0.045) ** 2 * 6, 0.03) * (z > 0.05)
    for sx in (-1, 1):
        z -= 0.02 * gauss((fx - 0.05 * sx) ** 2 + (fy - 0.02) ** 2, 0.024) * (z > 0.04)
        d2 = (fx - 0.078 * sx) ** 2 + (fy + 0.02) ** 2
        x += 0.007 * sx * gauss(d2, 0.025)
        z -= 0.01 * gauss((fx - 0.06 * sx) ** 2 + (fy + 0.06) ** 2, 0.025) * (z > 0.03)
        x -= 0.007 * sx * gauss((fy - 0.035) ** 2 + (z - 0.03) ** 2, 0.03) * (abs(x) > 0.1)
    z += 0.028 * gauss(fx * fx * 9 + (fy + 0.035) ** 2, 0.022) * (z > 0.06)   # nose
    if fy < -0.075 and z > 0.02:
        z -= 0.02 * min(1, (-0.075 - fy) / 0.04)  # upper lip recedes; the jaw covers the chin
    return x, y + 0.13, z + 0.02


displace(head, sculpt_head)
ears = [ellipsoid((0.137 * s, 0.14, 0.0), (0.012, 0.034, 0.024), 10, 8, "ear") for s in (-1, 1)]
head = join([head] + ears, "head")
rot_noise(head, 0.0018, 0.012)
finish(head, "head", 0)

jaw = ellipsoid((0, -0.03, 0.055), (0.066, 0.034, 0.062), 18, 10, "jaw")
displace(jaw, lambda x, y, z: (x * (1 - 0.35 * max(0, z - 0.02) / 0.06), y - 0.01 * max(0, z) / 0.06, z))
finish(jaw, "jaw", 0)

def teeth_row(name, y, z, width):
    objs = []
    for i in range(8):
        a = (i - 3.5) / 3.5
        t = box((a * width, y, z - abs(a) ** 2 * 0.02), (0.0085, 0.013 + random.uniform(-0.002, 0.003), 0.008), "t", 0)
        t.rotation_euler = (random.uniform(-0.2, 0.2), 0, random.uniform(-0.15, 0.15))
        objs.append(t)
    ob = join(objs, name)
    return finish(ob, name, 0, smooth=False)

teeth_row("teeth_upper", 0.064, 0.118, 0.032)
teeth_row("teeth_lower", -0.008, 0.094, 0.028)
finish(ellipsoid((0, 0.045, 0.09), (0.045, 0.028, 0.035), 12, 8, "mouth"), "mouth", 0)

# ---- limbs ----
skin("upperarm", [(0, 0.02, 0, 0.062, 0.06), (0, -0.05, 0.005, 0.066, 0.062), (0, -0.18, 0, 0.055, 0.052), (0, -0.31, 0, 0.047, 0.045)],
     [(0, 1), (1, 2), (2, 3)])
skin("forearm", [(0, 0.01, 0, 0.048, 0.046), (0, -0.1, 0.005, 0.052, 0.045), (0, -0.2, 0, 0.042, 0.036), (0, -0.29, 0, 0.036, 0.026)],
     [(0, 1), (1, 2), (2, 3)])
hand_nodes = [(0, 0.0, 0, 0.033, 0.02), (0, -0.05, 0.004, 0.042, 0.018), (0, -0.09, 0.008, 0.04, 0.016)]
hand_edges = [(0, 1), (1, 2)]
for fx, ln in ((-0.027, 0.85), (-0.009, 1.0), (0.009, 0.96), (0.027, 0.8)):   # long bony fingers, curled like claws
    base = len(hand_nodes)
    hand_nodes += [(fx, -0.1, 0.012, 0.0095, 0.0085), (fx * 1.1, -0.1 - 0.04 * ln, 0.03, 0.0085, 0.0078),
                   (fx * 1.15, -0.1 - 0.07 * ln, 0.055, 0.0075, 0.007), (fx * 1.15, -0.1 - 0.085 * ln, 0.075, 0.0065, 0.006)]
    hand_edges += [(2, base), (base, base + 1), (base + 1, base + 2), (base + 2, base + 3)]
base = len(hand_nodes)
hand_nodes += [(-0.035, -0.03, 0.015, 0.012, 0.011), (-0.05, -0.065, 0.04, 0.01, 0.009), (-0.048, -0.09, 0.062, 0.008, 0.0075)]
hand_edges += [(1, base), (base, base + 1), (base + 1, base + 2)]
skin("hand", hand_nodes, hand_edges, subdiv=1)

skin("thigh", [(0, 0.03, 0, 0.09, 0.088), (0, -0.2, 0.008, 0.08, 0.078), (0, -0.4, 0.005, 0.062, 0.06), (0, -0.46, 0, 0.056, 0.055)],
     [(0, 1), (1, 2), (2, 3)])
skin("shin", [(0, 0.01, 0.005, 0.056, 0.058), (0, -0.11, -0.012, 0.062, 0.07), (0, -0.28, -0.004, 0.047, 0.05), (0, -0.42, 0, 0.038, 0.036)],
     [(0, 1), (1, 2), (2, 3)])
# worn leather shoe: heel, instep and a scuffed toe cap
skin("foot", [(0, -0.4, 0.0, 0.045, 0.045), (0, -0.455, -0.02, 0.05, 0.04), (0, -0.47, 0.06, 0.052, 0.035), (0, -0.475, 0.15, 0.045, 0.026)],
     [(0, 1), (1, 2), (2, 3)])

# =====================================================================
# ACCESSORIES  (each in the frame of the joint it is attached to)
# =====================================================================
# head frame
cap = join([cylinder((0, 0.2, 0), (0, 0.29, 0), 0.148, 0.155, 28, "crown"),
            ellipsoid((0, 0.29, 0.0), (0.158, 0.018, 0.162), 24, 8, "top"),
            ellipsoid((0, 0.205, 0.13), (0.12, 0.012, 0.07), 20, 6, "visor")], "police_cap")
finish(cap, "police_cap", 0)
finish(ellipsoid((0, 0.19, 0.0), (0.17, 0.135, 0.178), 28, 16, "riot_helmet"), "riot_helmet", 0)
finish(join([ellipsoid((0, 0.2, 0.0), (0.172, 0.12, 0.18), 28, 14, "shell"),
             ellipsoid((0, 0.16, 0.02), (0.2, 0.01, 0.22), 28, 6, "brim"),
             ellipsoid((0, 0.24, 0.0), (0.02, 0.1, 0.19), 12, 8, "ridge")], "hardhat"), "hardhat", 0)
vis = ellipsoid((0, 0.14, 0.12), (0.15, 0.06, 0.08), 24, 10, "visor_glass")
displace(vis, lambda x, y, z: (x, y, max(z, 0.1)))
finish(vis, "visor", 0)
gm = join([ellipsoid((0, 0.1, 0.125), (0.1, 0.085, 0.05), 20, 12, "face"),
           cylinder((0, 0.04, 0.15), (0, 0.035, 0.21), 0.042, 0.045, 18, "filter"),
           ellipsoid((-0.045, 0.14, 0.15), (0.03, 0.028, 0.012), 14, 8, "lensL"),
           ellipsoid((0.045, 0.14, 0.15), (0.03, 0.028, 0.012), 14, 8, "lensR")], "gasmask")
finish(gm, "gasmask", 0)
mask = ellipsoid((0, 0.06, 0.115), (0.1, 0.055, 0.04), 20, 10, "mask")
displace(mask, lambda x, y, z: (x, y, max(z, 0.1) + 0.004))
finish(mask, "surgical_mask", 0)
finish(ellipsoid((0, 0.26, 0.01), (0.13, 0.04, 0.12), 20, 8, "nurse_cap"), "nurse_cap", 0)
finish(join([ellipsoid((0, 0.19, -0.015), (0.148, 0.1, 0.15), 24, 12, "hs"),
             ellipsoid((0, 0.23, 0.05), (0.12, 0.05, 0.1), 16, 8, "fringe")], "hair_short"), "hair_short", 0)
long_hair = [ellipsoid((0, 0.17, -0.03), (0.155, 0.13, 0.15), 24, 12, "hl")]
for i in range(16):
    a = (i / 15 - 0.5) * 3.4
    x, z = math.sin(a) * 0.14, math.cos(a) * 0.13 - 0.04
    long_hair.append(cylinder((x, 0.14, z), (x * 1.2, -0.12 - random.uniform(0, 0.08), z * 1.05 - 0.02), 0.02, 0.006, 8, "strand"))
finish(join(long_hair, "hair_long"), "hair_long", 0)

# body frame
vest = join([box((0, 1.33, 0.14), (0.44, 0.5, 0.05), "front"), box((0, 1.34, -0.13), (0.42, 0.52, 0.05), "back"),
             box((-0.2, 1.3, 0.0), (0.05, 0.36, 0.24), "sideL"), box((0.2, 1.3, 0.0), (0.05, 0.36, 0.24), "sideR"),
             box((-0.1, 1.2, 0.18), (0.1, 0.12, 0.05), "pouch1"), box((0.03, 1.2, 0.18), (0.1, 0.12, 0.05), "pouch2"),
             box((0.15, 1.2, 0.18), (0.07, 0.12, 0.05), "pouch3"), box((-0.12, 1.55, 0.0), (0.06, 0.05, 0.28), "strapL"),
             box((0.12, 1.55, 0.0), (0.06, 0.05, 0.28), "strapR")], "vest")
finish(vest, "vest", 0, smooth=False)
tanks = join([cylinder((0.2, 1.05, -0.25), (0.2, 1.58, -0.25), 0.1, 0.1, 20, "tankR"),
              cylinder((-0.2, 1.05, -0.25), (-0.2, 1.58, -0.25), 0.1, 0.1, 20, "tankL"),
              ellipsoid((0.2, 1.58, -0.25), (0.1, 0.05, 0.1), 16, 8, "domeR"), ellipsoid((-0.2, 1.58, -0.25), (0.1, 0.05, 0.1), 16, 8, "domeL"),
              box((0, 1.62, -0.25), (0.46, 0.05, 0.06), "valve"), box((0, 1.3, -0.16), (0.5, 0.05, 0.03), "strap")], "fuel_tanks")
finish(tanks, "fuel_tanks", 0)
# riot shield: a curved polycarbonate plate with a clean 0..1 UV so the POLICE decal lands right
bm = bmesh.new()
cols, rows = 10, 12
grid = [[bm.verts.new(B((c / cols - 0.5) * 0.66, 0.47 + r / rows * 1.34, 0.44 + 0.07 * math.cos((c / cols - 0.5) * math.pi) - 0.07)) for c in range(cols + 1)] for r in range(rows + 1)]
uv = bm.loops.layers.uv.new("UVMap")
for r in range(rows):
    for c in range(cols):
        f = bm.faces.new((grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]))
        for loop, (cc, rr) in zip(f.loops, ((c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1))):
            loop[uv].uv = (cc / cols, rr / rows)
me = bpy.data.meshes.new("riot_shield"); bm.to_mesh(me); bm.free()
sh = bpy.data.objects.new("riot_shield", me); scene.collection.objects.link(sh)
solid = sh.modifiers.new("thick", "SOLIDIFY"); solid.thickness = 0.018
activate(sh); bpy.ops.object.modifier_apply(modifier=solid.name); bpy.ops.object.shade_smooth()
PARTS.append(sh)

# hand frame
finish(join([cylinder((0, -0.06, -0.12), (0, -0.06, 0.52), 0.02, 0.024, 12, "baton"),
             cylinder((0.0, -0.06, -0.02), (0.1, -0.06, -0.02), 0.015, 0.015, 10, "tonfa")], "baton"), "baton", 0)
finish(join([box((0, -0.05, 0.08), (0.034, 0.045, 0.2), "slide"), box((0, -0.11, 0.02), (0.03, 0.1, 0.045), "grip"),
             box((0, -0.075, 0.07), (0.028, 0.02, 0.1), "frame")], "pistol"), "pistol", 0, smooth=False)
finish(join([cylinder((0, -0.05, -0.05), (0, -0.05, 0.52), 0.022, 0.018, 14, "wand"),
             box((0, -0.09, 0.08), (0.03, 0.08, 0.05), "handle"), cylinder((0, -0.05, 0.5), (0, -0.05, 0.54), 0.03, 0.028, 14, "tip")], "flame_wand"), "flame_wand", 0)
claws = [cylinder((fx, -0.175, 0.075), (fx * 1.2, -0.205, 0.11), 0.007, 0.0005, 8, "claw") for fx in (-0.031, -0.01, 0.01, 0.031)]
finish(join(claws, "claws"), "claws", 0)

# shoulder frame
finish(ellipsoid((0, -0.02, 0.0), (0.1, 0.07, 0.11), 20, 10, "shoulder_pad"), "shoulder_pad", 0)

# loose props placed by the game
spike = cylinder((0, 0, 0), (0, 0, -0.16), 0.03, 0.002, 10, "spike")
displace(spike, lambda x, y, z: (x, y + 0.3 * z * z, z))  # curved bone spur
finish(spike, "bone_spike", 1)
boil = ellipsoid((0, 0, 0), (0.06, 0.055, 0.06), 16, 10, "boil")
rot_noise(boil, 0.008, 0.02)
finish(boil, "boil", 0)

# =====================================================================
# INFECTED DOG
# =====================================================================
dog = skin("dog_body", [
    (0, 0.6, -0.33, 0.12, 0.13),    # haunches
    (0, 0.58, -0.12, 0.1, 0.12),    # tucked waist
    (0, 0.61, 0.1, 0.125, 0.16),    # deep chest
    (0, 0.66, 0.28, 0.12, 0.15),    # shoulders
    (0, 0.74, 0.4, 0.085, 0.09),    # thick neck
], [(0, 1), (1, 2), (2, 3), (3, 4)])
displace(dog, lambda x, y, z: (x * (1 + 0.05 * max(0, math.sin(z * 55)) * (0 < z < 0.22)), y, z))  # starved ribs
rot_noise(dog, 0.004)
dh = skin("dog_head", [
    (0, 0.02, -0.01, 0.085, 0.085),  # skull
    (0, 0.0, 0.1, 0.065, 0.06),      # stop and cheeks
    (0, -0.025, 0.21, 0.045, 0.045), # muzzle
    (0, -0.035, 0.27, 0.035, 0.035), # nose
    (0.05, 0.1, -0.03, 0.02, 0.012), (0.058, 0.15, -0.04, 0.008, 0.005),     # ears
    (-0.05, 0.1, -0.03, 0.02, 0.012), (-0.058, 0.15, -0.04, 0.008, 0.005),
], [(0, 1), (1, 2), (2, 3), (0, 4), (4, 5), (0, 6), (6, 7)])
skin("dog_leg_front", [(0, 0.04, 0, 0.065, 0.07), (0, -0.2, 0.02, 0.04, 0.042), (0, -0.44, 0.0, 0.022, 0.024), (0, -0.53, 0.04, 0.026, 0.02)],
     [(0, 1), (1, 2), (2, 3)], subdiv=1)
skin("dog_leg_back", [(0, 0.04, 0, 0.075, 0.085), (0, -0.18, -0.06, 0.05, 0.055), (0, -0.36, 0.02, 0.022, 0.024), (0, -0.53, 0.0, 0.022, 0.022), (0, -0.54, 0.04, 0.026, 0.02)],
     [(0, 1), (1, 2), (2, 3), (3, 4)], subdiv=1)
skin("dog_tail", [(0, 0.72, -0.44, 0.022, 0.022), (0, 0.66, -0.6, 0.014, 0.014), (0, 0.6, -0.72, 0.006, 0.006)], [(0, 1), (1, 2)], subdiv=1)

# ---------------------------------------------------------------- export
for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                          export_materials="NONE")
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in PARTS)
print("exported", OUT, len(PARTS), "parts", tris, "triangles")
for o in PARTS:
    print("  part", o.name, sum(len(p.vertices) - 2 for p in o.data.polygons))


# ---------------------------------------------------------------- preview: assemble a few zombies in their rest pose
if PREVIEW:
    def mat(name, rgb, rough=0.8):
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
        return m
    SKIN, SHIRT, PANTS, SHOE = mat("skin", (0.2, 0.24, 0.16)), mat("shirt", (0.12, 0.05, 0.04)), mat("pants", (0.05, 0.06, 0.09)), mat("shoe", (0.02, 0.018, 0.015))
    NAVY, GLASS = mat("navy", (0.02, 0.03, 0.06)), mat("glass", (0.2, 0.25, 0.3), 0.1)
    get = lambda n: bpy.data.objects[n]

    def joint(parent, loc, rot=(0, 0, 0)):
        e = bpy.data.objects.new("j", None); scene.collection.objects.link(e)
        e.parent = parent; e.location = loc; e.rotation_euler = rot
        return e

    def place(name, material, parent, mirror=False):
        o = get(name).copy(); o.data = get(name).data.copy(); scene.collection.objects.link(o)
        o.data.materials.clear(); o.data.materials.append(material)
        o.parent = parent; o.location = (0, 0, 0)
        if mirror:
            o.scale.x = -1
        return o

    def humanoid(ox, style):
        root = joint(None, B(ox, 0, 0))
        top, legs = (NAVY, NAVY) if style == "cop" else (SHIRT, PANTS)
        tg = joint(root, B(0, 1.2, 0))
        place("torso", top, tg); place("pelvis", legs, tg); place("neck", SKIN, root)
        hp = joint(root, B(0, 1.72, 0.03))
        for n in ("head", "mouth", "teeth_upper"):
            place(n, SKIN, hp)
        jw = joint(hp, B(0, 0.07, 0.03), (0.3, 0, 0))
        for n in ("jaw", "teeth_lower"):
            place(n, SKIN, jw)
        place("police_cap" if style == "cop" else "hair_short", NAVY if style == "cop" else mat("hair", (0.02, 0.015, 0.01)), hp)
        for s in (-1, 1):
            sh = joint(root, B(0.3 * s, 1.56, 0), (-1.25 if style != "cop" else -0.4, 0, 0))
            place("upperarm", top, sh, s < 0)
            el = joint(sh, B(0, -0.31, 0), (-0.35, 0, 0)); place("forearm", SKIN if style != "cop" else top, el, s < 0)
            wr = joint(el, B(0, -0.29, 0)); place("hand", SKIN, wr, s < 0)
            hip = joint(root, B(0.11 * s, 0.95, 0), (0.25 * s, 0, 0))
            place("thigh", legs, hip)
            kn = joint(hip, B(0, -0.45, 0), (0.2 if s > 0 else 0.05, 0, 0))
            place("shin", legs, kn); place("foot", SHOE, kn)
        if style == "cop":
            place("riot_shield", GLASS, root)

    humanoid(-0.6, "walker")
    humanoid(0.6, "cop")
    dx = 1.9
    FUR = mat("fur", (0.08, 0.06, 0.045))
    droot = joint(None, B(dx, 0, 0))
    place("dog_body", FUR, droot); place("dog_tail", FUR, droot); place("dog_head", FUR, joint(droot, B(0, 0.74, 0.44)))
    for sx, sz, n in ((-0.11, 0.28, "dog_leg_front"), (0.11, 0.28, "dog_leg_front"), (-0.11, -0.28, "dog_leg_back"), (0.11, -0.28, "dog_leg_back")):
        place(n, FUR, joint(droot, B(sx, 0.55, sz)))
    for o in PARTS:
        o.hide_render = True
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
    cam.data.lens = 50
    target = B(0.65, 0.95, 0)
    cam.location = B(0.9, 1.35, 6.8)
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    for loc, energy in ((B(2, 3, 3), 140), (B(-2.5, 2, 1.5), 50), (B(0.5, 2.5, -3), 60)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = energy; l.data.size = 2; l.location = loc
        l.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1200, 700
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
