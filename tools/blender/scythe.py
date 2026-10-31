# 噬魂・冥王鐮刀 (legendary scythe) for 死城突圍: the scythe held in first person, and the crescent soul wave it throws.
#
#   blender -b -P tools/blender/scythe.py -- assets/models/scythe.glb [preview.png]
#
# Game frame (+Y up, +Z toward the camera), like the katana: the shaft runs along Z with the blade end toward -Z and the
# grip toward +Z; the blade sweeps out to +X and curls back toward the grip. "soul_wave" is a flat crescent in the XZ
# plane opening toward +Z. Material names are swapped for the game's own; scy_edge, scy_fire and soul_wave glow.
import bpy, bmesh, math, random, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "scythe.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(9)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
COLORS = dict(scy_wood=(0.06, 0.04, 0.035), scy_iron=(0.12, 0.12, 0.13), scy_bone=(0.72, 0.66, 0.52), scy_leather=(0.12, 0.05, 0.035),
              scy_blade=(0.16, 0.17, 0.2), scy_edge=(0.7, 0.35, 1.0), scy_fire=(0.55, 0.25, 1.0), scy_dark=(0.02, 0.01, 0.01), soul_wave=(0.6, 0.3, 1.0))
MATS = {}


def mat(name):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes.get("Principled BSDF"); c = COLORS[name]
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Metallic"].default_value = 1.0 if name in ("scy_iron", "scy_blade") else 0.0
        b.inputs["Roughness"].default_value = 0.35 if name in ("scy_iron", "scy_blade") else 0.7
        if name in ("scy_edge", "scy_fire", "soul_wave"):
            b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 6
        MATS[name] = m
    return MATS[name]


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def tidy(ob, smooth=True):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()
    if smooth:
        ob.data.shade_smooth()
    return ob


def new(name, verts, faces, m, smooth=True):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob); ob.data.materials.append(mat(m))
    return tidy(ob, smooth)


def cyl(name, p0, p1, r0, r1, m, seg=16):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=r0, radius2=r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.name = name
    ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True); ob.data.materials.append(mat(m))
    return tidy(ob)


def sphere(name, p, rad, m, seg=16, rings=10, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=rad, location=B(*p))
    ob = bpy.context.object; ob.name = name; ob.scale = (scale[0], scale[2], scale[1])
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True); ob.data.materials.append(mat(m))
    return tidy(ob)


def torus(name, R, r, m, at, axis="Z", seg=24, mseg=8):
    rot = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]  # ring around the game axis named
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=mseg)
    ob = bpy.context.object; ob.name = name; ob.rotation_euler = rot; ob.location = B(*at)
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True); ob.data.materials.append(mat(m))
    return tidy(ob)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join(); ob = bpy.context.object; ob.name = name; ob.data.name = name
    return ob


P = []
# ---- the shaft: blackened wood, twisted, bound in iron, a spine of vertebrae near the head, two leather grips
seg, n = 14, 60
verts, faces = [], []
for i in range(n + 1):
    z = 0.42 - i * (1.32 / n); r = 0.0175 + 0.0025 * math.sin(i * 0.9)
    for k in range(seg):
        a = 2 * math.pi * k / seg + z * 6  # a slow twist in the grain
        rr = r * (1 + 0.08 * math.cos(3 * a))
        verts.append(B(rr * math.cos(a), rr * math.sin(a), z))
for i in range(n):
    for k in range(seg):
        faces.append((i * seg + k, i * seg + (k + 1) % seg, (i + 1) * seg + (k + 1) % seg, (i + 1) * seg + k))
P.append(new("shaft", verts, faces, "scy_wood"))
for z in (0.42, 0.06, -0.38, -0.62):
    P.append(torus("ferrule", 0.021, 0.006, "scy_iron", (0, 0, z), "Z"))
for z0, z1 in ((0.38, 0.16), (-0.02, -0.22)):  # leather grips, wrapped in overlapping turns
    t = 0
    while z0 - t * 0.011 > z1:
        P.append(torus("wrap", 0.0205, 0.0042, "scy_leather", (0, 0, z0 - t * 0.011), "Z", 18, 6)); t += 1
for k in range(9):  # vertebrae up to the head
    z = -0.66 - k * 0.026
    P.append(cyl("vert", (0, 0, z + 0.008), (0, 0, z - 0.008), 0.026, 0.024, "scy_bone", 14))
    P.append(cyl("spur", (0, 0.02, z), (0, 0.042, z + 0.006), 0.007, 0.002, "scy_bone", 8))
P.append(sphere("pommel", (0, 0, 0.45), 0.03, "scy_iron", 16, 10, (1, 1, 1.4)))
for k in range(4):
    a = k * math.pi / 2
    P.append(cyl("pspike", (0.02 * math.cos(a), 0.02 * math.sin(a), 0.47), (0.034 * math.cos(a), 0.034 * math.sin(a), 0.52), 0.007, 0.001, "scy_iron", 8))
# ---- the skull where the blade meets the shaft
SK = (0.0, 0.035, -0.93)
P.append(sphere("skull", SK, 0.055, "scy_bone", 24, 16, (0.9, 1.0, 1.15)))
for sx in (-1, 1):
    P.append(sphere("socket", (SK[0] + sx * 0.022, SK[1] + 0.012, SK[2] - 0.05), 0.016, "scy_dark", 12, 8))
    P.append(sphere("eyefire", (SK[0] + sx * 0.022, SK[1] + 0.012, SK[2] - 0.056), 0.007, "scy_fire", 10, 6))
    P.append(cyl("horn", (SK[0] + sx * 0.04, SK[1] + 0.045, SK[2] + 0.01), (SK[0] + sx * 0.09, SK[1] + 0.11, SK[2] + 0.06), 0.014, 0.002, "scy_bone", 10))
P.append(sphere("jaw", (SK[0], SK[1] - 0.04, SK[2] - 0.03), 0.034, "scy_bone", 16, 10, (1, 0.5, 1.1)))
for k in range(6):
    P.append(cyl("tooth", (SK[0] - 0.02 + k * 0.008, SK[1] - 0.025, SK[2] - 0.062), (SK[0] - 0.02 + k * 0.008, SK[1] - 0.04, SK[2] - 0.06), 0.003, 0.0015, "scy_bone", 6))
P.append(cyl("collar", (0, 0, -0.88), (0, 0, -0.98), 0.03, 0.026, "scy_iron", 16))
# ---- the blade: a long crescent sweeping out to +X and curling back toward the grip, thin edge, ridged spine
bm = bmesh.new(); rows = []
N = 34
for i in range(N + 1):
    t = i / N
    ang = t * 1.25  # the curve
    cx, cz = 0.72 * math.sin(ang) / 1.0, -0.96 + 0.42 * (1 - math.cos(ang))
    tx, tz = math.cos(ang), math.sin(ang)  # along the blade
    nx, nz = -tz, tx  # toward the inner (cutting) edge
    w = 0.13 * (1 - t) ** 0.7 + 0.004
    th = 0.011 * (1 - 0.6 * t) + 0.002
    back = (cx - nx * 0.02, cz - nz * 0.02)
    sec = [(0.0, 0.0, w), (th * 0.4, 0.0, w * 0.75), (th, 0.0, w * 0.35), (th, 0.0, 0.0), (0, 0.0, -0.01), (-th, 0.0, 0.0), (-th, 0.0, w * 0.35), (-th * 0.4, 0.0, w * 0.75)]
    rows.append([bm.verts.new(B(back[0] + nx * s, y, back[1] + nz * s)) for (y, _, s) in sec])
for a, b in zip(rows, rows[1:]):
    for k in range(len(a)):
        bm.faces.new((a[k], a[(k + 1) % len(a)], b[(k + 1) % len(a)], b[k]))
bm.faces.new(rows[0][::-1]); bm.faces.new(rows[-1])
me = bpy.data.meshes.new("blade"); bm.to_mesh(me); bm.free()
blade = bpy.data.objects.new("blade", me); scene.collection.objects.link(blade); blade.data.materials.append(mat("scy_blade")); tidy(blade, False)
P.append(blade)
# the glowing edge: a thin strip just inside the cutting edge, both faces
for s in (-1, 1):
    vs, fs = [], []
    for i in range(N + 1):
        t = i / N; ang = t * 1.25
        cx, cz = 0.72 * math.sin(ang), -0.96 + 0.42 * (1 - math.cos(ang)); nx, nz = -math.sin(ang), math.cos(ang)
        w = 0.13 * (1 - t) ** 0.7 + 0.004; back = (cx - nx * 0.02, cz - nz * 0.02); th = 0.011 * (1 - 0.6 * t) + 0.002
        for f in (0.62, 0.97):
            y = s * th * (0.6 if f < 0.7 else 0.2) + s * 0.0006
            vs.append(B(back[0] + nx * w * f, y, back[1] + nz * w * f))
    for i in range(N):
        fs.append((i * 2, i * 2 + 1, i * 2 + 3, i * 2 + 2))
    P.append(new("edge", vs, fs, "scy_edge", False))
# spikes along the spine and soul flames licking off it
for k in range(7):
    t = 0.08 + k * 0.12; ang = t * 1.25
    cx, cz = 0.72 * math.sin(ang), -0.96 + 0.42 * (1 - math.cos(ang)); nx, nz = -math.sin(ang), math.cos(ang)
    bx, bz = cx - nx * 0.022, cz - nz * 0.022
    P.append(cyl("spike", (bx, 0, bz), (bx - nx * 0.05, 0, bz - nz * 0.05 - 0.01), 0.008, 0.001, "scy_iron", 8))
    if k % 2 == 0:
        P.append(cyl("flame", (bx, 0, bz), (bx - nx * 0.09 + random.uniform(-0.02, 0.02), 0.01, bz - nz * 0.09 - 0.04), 0.016, 0.001, "scy_fire", 10))
# ---- the chain and its lantern, hanging from under the skull
y0 = -0.03
for k in range(9):
    P.append(torus("link", 0.011, 0.0028, "scy_iron", (0.0, y0 - k * 0.019, -0.9), "X" if k % 2 else "Y", 14, 6))
LY = y0 - 9 * 0.019 - 0.05
P.append(cyl("lcap", (0, LY + 0.04, -0.9), (0, LY + 0.025, -0.9), 0.012, 0.03, "scy_iron", 14))
P.append(cyl("lbase", (0, LY - 0.04, -0.9), (0, LY - 0.05, -0.9), 0.03, 0.018, "scy_iron", 14))
for k in range(6):
    a = k * math.pi / 3
    P.append(cyl("bar", (0.026 * math.cos(a), LY + 0.025, -0.9 + 0.026 * math.sin(a)), (0.03 * math.cos(a), LY - 0.04, -0.9 + 0.03 * math.sin(a)), 0.0025, 0.0025, "scy_iron", 6))
P.append(sphere("lfire", (0, LY - 0.005, -0.9), 0.02, "scy_fire", 14, 10, (1, 1.3, 1)))
P.append(sphere("lskull", (0, LY - 0.03, -0.9), 0.012, "scy_bone", 12, 8))
scythe = join(P, "scythe")

# ---- the soul wave: a crescent of soul fire, thick in the middle and drawn out to points
vs, fs = [], []
M = 40
for i in range(M + 1):
    t = i / M; a = math.radians(-70 + 140 * t); w = 0.22 * math.sin(math.pi * t) ** 0.8 + 0.004
    for r, y in ((0.9, 0.0), (0.9 - w * 0.5, 0.025 * math.sin(math.pi * t)), (0.9 - w, 0.0), (0.9 - w * 0.5, -0.025 * math.sin(math.pi * t))):
        vs.append(B(r * math.sin(a), y, -r * math.cos(a) + 0.6))
for i in range(M):
    for k in range(4):
        fs.append((i * 4 + k, i * 4 + (k + 1) % 4, (i + 1) * 4 + (k + 1) % 4, (i + 1) * 4 + k))
wave = new("soul_wave", vs, fs, "soul_wave")

for o in (scythe, wave):
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_texcoords=False, export_yup=True)
print("exported", OUT, {o.name: len(o.data.polygons) for o in (scythe, wave)})

if PREVIEW:
    scythe.rotation_euler = (math.radians(90), 0, 0); scythe.location = (-0.15, 0, 0.5)
    wave.location = (0.75, 0, 0.9); wave.rotation_euler = (math.radians(70), 0, 0)
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    cam = bpy.data.cameras.new("cam"); cam.lens = 50; co = bpy.data.objects.new("cam", cam); scene.collection.objects.link(co); scene.camera = co
    co.location = (0.25, -2.6, 1.0); co.rotation_euler = (math.radians(90), 0, 0)
    for loc, e in (((2, -3, 3), 500), ((-3, -2, 2), 200), ((0, 3, 2), 300)):
        l = bpy.data.lights.new("l", "AREA"); l.energy = e; l.size = 2; lo = bpy.data.objects.new("l", l); lo.location = loc; scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    scene.render.resolution_x, scene.render.resolution_y = 1100, 900; scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
