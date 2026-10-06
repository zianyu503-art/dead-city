# The zombie compass (殭屍羅盤): a radar watch strapped to the left wrist of the view-model arm.
#
#   blender -b -P tools/blender/compass.py -- assets/models/compass.glb [preview.png]
#
# Written in game coordinates of the arm slot (+Z runs up the forearm, +Y is the back of the
# wrist), with the wrist's axis through the origin so the game can turn the watch around the wrist
# to face the camera. "compass_face" is a disc facing +Y whose UVs map x → u and z → v, so the
# game can paint the radar onto it. Material names are keys for the game's own materials.
import bpy, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "compass.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

MAT = {}
for n, (c, r, mt) in {"cmp_strap": ((0.02, 0.02, 0.022), 0.75, 0.0), "cmp_metal": ((0.08, 0.085, 0.09), 0.35, 0.9),
                      "cmp_bezel": ((0.55, 0.42, 0.18), 0.3, 1.0), "cmp_face": ((0.02, 0.06, 0.03), 0.4, 0.0)}.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    MAT[n] = m


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def mesh(name, vs, fs, mat, uvs=None, smooth=True):
    me = bpy.data.meshes.new(name); me.from_pydata([B(*v) for v in vs], [], fs)
    if uvs:
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    ob.data.materials.append(MAT[mat])
    activate(ob)
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def lathe_y(name, prof, mat, n=48, y0=0.0):
    """Turned around the +Y axis (the watch's own axis): prof = [(y, radius)]."""
    vs, fs = [], []
    for y, r in prof:
        for k in range(n):
            a = k / n * math.tau
            vs.append((math.cos(a) * r, y0 + y, math.sin(a) * r))
    for i in range(len(prof) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            fs.append((a, b, b + n, a + n))
    return mesh(name, vs, fs, mat)


def band(name, r_in, r_out, z0, z1, mat, n=48, ry=0.92):
    """A strap ring around the wrist (the +Z axis), slightly flattened like a wrist."""
    vs, fs = [], []
    for z in (z0, z1):
        for r in (r_in, r_out):
            for k in range(n):
                a = k / n * math.tau
                vs.append((math.cos(a) * r, math.sin(a) * r * ry, z))
    def ring(i):
        return [i * n + k for k in range(n)]
    for (ra, rb) in ((1, 3), (0, 2)):  # outer face, inner face
        A, Bq = ring(ra), ring(rb)
        for k in range(n):
            k2 = (k + 1) % n
            fs.append((A[k], A[k2], Bq[k2], Bq[k]) if ra == 1 else (A[k2], A[k], Bq[k], Bq[k2]))
    for (ra, rb) in ((0, 1), (2, 3)):  # edges
        A, Bq = ring(ra), ring(rb)
        for k in range(n):
            k2 = (k + 1) % n
            fs.append((A[k], A[k2], Bq[k2], Bq[k]))
    return mesh(name, vs, fs, mat)


def box(c, s, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    activate(ob); bpy.ops.object.transform_apply(scale=True)
    bv = ob.modifiers.new("b", "BEVEL"); bv.width = min(s) * 0.3; bv.segments = 2
    bpy.ops.object.modifier_apply(modifier=bv.name)
    ob.data.materials.append(MAT[mat])
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# strap and the watch housing on the back of the wrist
R0 = 0.048   # wrist radius under the strap
Y0 = 0.047   # where the housing sits on the strap
parts = [band("strap", R0, R0 + 0.005, -0.012, 0.012, "cmp_strap")]
for k in range(5):  # strap holes / stitching ridges on the underside
    a = math.pi * 1.25 + k * 0.12
    parts.append(box((math.cos(a) * (R0 + 0.005), math.sin(a) * (R0 + 0.005) * 0.92, 0), (0.003, 0.002, 0.016), "cmp_strap"))
for s in (-1, 1):  # lugs
    parts.append(box((0, Y0 + 0.004, s * 0.03), (0.028, 0.008, 0.014), "cmp_metal"))
parts.append(lathe_y("case", [(0.0, 0.038), (0.003, 0.044), (0.011, 0.044), (0.013, 0.041)], "cmp_metal", 64, Y0))
parts.append(lathe_y("bezel", [(0.011, 0.0447), (0.0135, 0.0455), (0.0155, 0.043), (0.0155, 0.0385), (0.0135, 0.038)], "cmp_bezel", 72, Y0))
for k in range(4):  # bezel markers
    a = k / 4 * math.tau
    parts.append(box((math.cos(a) * 0.0418, Y0 + 0.0158, math.sin(a) * 0.0418), (0.004, 0.0012, 0.004), "cmp_metal"))
crown = lathe_y("crown", [(0, 0.0035), (0.006, 0.0035)], "cmp_bezel", 16, 0)
crown.rotation_euler = (0, math.pi / 2, 0)  # sticks out along +X in Blender (= game +X)
crown.location = B(0.045, Y0 + 0.007, 0)
activate(crown); bpy.ops.object.transform_apply(location=True, rotation=True)
parts.append(crown)
join(parts, "compass_body")

# the radar face: a disc facing +Y with u along +X and v along +Z
n, R = 64, 0.038
vs, fs, uvs = [(0, Y0 + 0.0136, 0)], [], [(0.5, 0.5)]
for k in range(n):
    a = k / n * math.tau
    x, z = math.cos(a) * R, math.sin(a) * R
    vs.append((x, Y0 + 0.0136, z)); uvs.append((0.5 + x / R / 2, 0.5 + z / R / 2))
for k in range(n):
    fs.append((0, 1 + (k + 1) % n, 1 + k))
face = mesh("compass_face", vs, fs, "cmp_face", uvs, smooth=False)
PARTS.append(face)

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT")
print("exported", OUT, [(o.name, len(o.data.polygons)) for o in PARTS])

if PREVIEW:
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 80; eye, tgt = B(0.12, 0.2, 0.18), B(0, 0.05, 0)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
    l.data.energy = 8; l.data.size = 0.4; l.location = B(0.2, 0.3, 0.2); l.rotation_euler = (tgt - l.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 32; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 800, 600
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
