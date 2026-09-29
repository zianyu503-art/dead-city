# Builds the katana view model for 死城突圍 and exports it as glTF.
#
#   blender -b -P tools/blender/katana.py -- assets/models/katana.glb [preview.png]
#
# Blender axes: the blade runs along +Y, its width along +Z (spine up) and its
# thickness along X. The glTF exporter converts to Y-up, so in three.js the blade
# points down -Z with the handle toward +Z, which is what the game expects.
import bpy, bmesh, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "katana.glb"
PREVIEW = argv[1] if len(argv) > 1 else None

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ---------------------------------------------------------------- materials
def material(name, color, metallic=0.0, roughness=0.5, image=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if image:
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def hamon_image():
    """Polished steel with a frosty, wavy temper line along the edge (v = 0 at the edge)."""
    W, H = 1024, 128
    img = bpy.data.images.new("hamon", W, H)
    px = [0.0] * (W * H * 4)
    for yv in range(H):
        v = yv / (H - 1)
        for xu in range(W):
            u = xu / (W - 1)
            line = 0.34 + 0.05 * math.sin(u * 62) + 0.03 * math.sin(u * 17 + 1.3) + 0.015 * math.sin(u * 140)
            if v < 0.035:
                c = (0.93, 0.94, 0.95)                       # honed edge
            elif v < line:
                g = 0.84 + 0.06 * math.sin(u * 900 + v * 300)  # frosted hamon crystals
                c = (g, g + 0.01, g + 0.03)
            elif v < line + 0.03:
                c = (0.7, 0.72, 0.76)                        # soft nioi boundary
            elif v > 0.72:
                c = (0.38, 0.41, 0.46)                       # darker shinogi-ji above the ridge
            else:
                c = (0.56, 0.59, 0.64)                       # polished ji
            i = (yv * W + xu) * 4
            px[i:i + 4] = (*c, 1.0)
    img.pixels.foreach_set(px)
    img.pack()
    return img


M_BLADE = material("blade", (1, 1, 1), 1.0, 0.18, hamon_image())
M_BRASS = material("brass", (0.83, 0.62, 0.28), 1.0, 0.28)
M_IRON = material("iron", (0.07, 0.065, 0.06), 0.85, 0.45)
M_GOLD = material("gold", (0.9, 0.7, 0.32), 1.0, 0.22)
M_SAME = material("samegawa", (0.86, 0.83, 0.74), 0.0, 0.75)
M_ITO = material("ito", (0.025, 0.025, 0.032), 0.0, 0.55)
M_PEG = material("mekugi", (0.62, 0.5, 0.3), 0.0, 0.6)


def new_object(name, verts, faces, mat, uvs=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if uvs:
        layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[me.loops[li].vertex_index]
    for p in me.polygons:
        p.use_smooth = smooth
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def bevel(ob, width, segments=2):
    mod = ob.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"


# ---------------------------------------------------------------- blade
L, W, SORI, Y0 = 0.74, 0.032, 0.028, 0.004
N = 80
verts, faces, uvs = [], [], []
for i in range(N + 1):
    t = i / N
    y = Y0 + L * t
    height = W * (1 - 0.3 * t)
    thick = 0.0068 * (1 - 0.45 * t)
    if t > 0.9:                                  # kissaki: the edge sweeps up to meet the spine
        f = max(0.02, math.sqrt((1 - t) / 0.1))
        height *= f
        thick *= max(0.08, f)
    spine = W / 2 + SORI * t * t
    ring = [(-thick * 0.28, 0), (-thick / 2, -0.3 * height), (0, -height), (thick / 2, -0.3 * height), (thick * 0.28, 0)]
    vv = [1.0, 0.7, 0.0, 0.7, 1.0]
    for (x, dz), v in zip(ring, vv):
        verts.append((x, y, spine + dz))
        uvs.append((t, v))
R = 5
for i in range(N):
    for j in range(R):
        a, b = i * R + j, i * R + (j + 1) % R
        faces.append((a, b, b + R, a + R))
faces.append(tuple(range(R - 1, -1, -1)))       # cap hidden inside the habaki
blade = new_object("blade", verts, faces, M_BLADE, uvs, smooth=False)

# ---------------------------------------------------------------- habaki (blade collar)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, Y0 + 0.016, 0.001))
hab = bpy.context.object; hab.name = "habaki"
hab.scale = (0.0125, 0.03, 0.04)
hab.data.materials.append(M_BRASS)
bpy.ops.object.transform_apply(scale=True)
bevel(hab, 0.0018, 3)


# ---------------------------------------------------------------- oval discs: seppa, tsuba, fuchi, kashira
def oval_disc(name, rz, rx, y, depth, mat, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=1, depth=depth, location=(0, y, 0), rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.object; ob.name = name
    ob.scale = (rx, rz, 1)          # after the rotation local Y is world Z (height of the oval)
    ob.data.materials.append(mat)
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    bpy.ops.object.shade_smooth()
    return ob


for yy in (0.0015, -0.0085):
    s = oval_disc("seppa", 0.021, 0.0155, yy, 0.0022, M_BRASS)
    bevel(s, 0.0006)

tsuba = oval_disc("tsuba", 0.043, 0.0362, -0.0035, 0.0062, M_IRON, 64)
# two kogai-hitsu openings pierced through the guard
for sx in (-1, 1):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.0058, depth=0.03, location=(sx * 0.022, -0.0035, 0.004), rotation=(math.pi / 2, 0, 0))
    cutter = bpy.context.object
    cutter.scale = (1, 1.9, 1)
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    mod = tsuba.modifiers.new("hole", "BOOLEAN")
    mod.operation = "DIFFERENCE"; mod.object = cutter; mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = tsuba
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter)
bevel(tsuba, 0.0009)

bpy.ops.mesh.primitive_torus_add(major_radius=0.043, minor_radius=0.0021, major_segments=64, minor_segments=8,
                                 location=(0, -0.0035, 0), rotation=(math.pi / 2, 0, 0))
rim = bpy.context.object; rim.name = "tsuba_rim"
rim.scale = (0.842, 1, 1)
rim.data.materials.append(M_GOLD)
bpy.ops.object.transform_apply(rotation=True, scale=True)
bpy.ops.object.shade_smooth()

fuchi = oval_disc("fuchi", 0.0178, 0.0146, -0.0155, 0.012, M_IRON)
bevel(fuchi, 0.0012)

# ---------------------------------------------------------------- tsuka: ray-skin core wrapped in crossing silk bands
TY0, TY1 = -0.021, -0.266
SEG, ST = 32, 40
def radii(y):
    k = (y - TY0) / (TY1 - TY0)
    rz = 0.0164 - 0.0011 * math.sin(math.pi * k)     # slight waist in the middle of the grip
    return rz * 0.82, rz

verts, faces = [], []
for i in range(ST + 1):
    y = TY0 + (TY1 - TY0) * i / ST
    rx, rz = radii(y)
    for j in range(SEG):
        a = 2 * math.pi * j / SEG
        verts.append((rx * math.cos(a), y, rz * math.sin(a)))
for i in range(ST):
    for j in range(SEG):
        a, b = i * SEG + j, i * SEG + (j + 1) % SEG
        faces.append((a, a + SEG, b + SEG, b))
new_object("samegawa", verts, faces, M_SAME)

PITCH, HALF = 0.036, 0.0046
turns = abs(TY1 - TY0) / PITCH
for hand, lift in ((1, 0.0011), (-1, 0.0019)):
    for phase in (0.0, math.pi):
        verts, faces = [], []
        steps = int(turns * 56)
        for k in range(steps + 1):
            th = turns * 2 * math.pi * k / steps
            yc = TY0 - PITCH * th / (2 * math.pi) * 0.999
            a = phase + hand * th
            for dy in (-HALF, HALF):
                yy = max(TY1, min(TY0, yc + dy))
                rx, rz = radii(yy)
                verts.append(((rx + lift) * math.cos(a), yy, (rz + lift) * math.sin(a)))
        for k in range(steps):
            faces.append((2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2))
        new_object("ito", verts, faces, M_ITO)

# menuki ornaments under the wrap, and the bamboo peg that locks the blade
for sx in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=1, location=(sx * 0.0134, -0.13, 0.002))
    mk = bpy.context.object; mk.name = "menuki"
    mk.scale = (0.0028, 0.013, 0.0065)
    mk.data.materials.append(M_GOLD)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.0024, depth=0.03, location=(0, -0.05, 0), rotation=(0, math.pi / 2, 0))
peg = bpy.context.object; peg.name = "mekugi"; peg.data.materials.append(M_PEG)

bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1, location=(0, -0.268, 0))
kash = bpy.context.object; kash.name = "kashira"
kash.scale = (0.0142, 0.012, 0.0172)
kash.data.materials.append(M_IRON)
bpy.ops.object.transform_apply(scale=True)
bpy.ops.object.shade_smooth()

# ---------------------------------------------------------------- export
for ob in scene.objects:
    ob.select_set(ob.type == "MESH")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
print("exported", OUT)

# ---------------------------------------------------------------- optional preview render
if PREVIEW:
    world = bpy.data.worlds.new("w"); scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.1
    cam.location = (0.9, 0.235, 0.02); cam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    scene.camera = cam
    for loc, energy, size in (((0.6, 0.0, 0.6), 14, 0.8), ((0.5, 0.6, -0.4), 6, 1.0), ((-0.6, 0.2, 0.5), 7, 0.6)):
        l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
        l.data.energy = energy; l.data.size = size; l.location = loc
        l.rotation_euler = (Vector((0, 0.235, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 48; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1400, 420
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
