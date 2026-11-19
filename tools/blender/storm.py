# 風暴發射器 (Storm Launcher) first-person model for 死城突圍.
#
#   python3 /Users/alex/.claude/skills/blender-modeling/scripts/run.py tools/blender/storm.py <work_dir>
#
# Weapon frame as the game uses it: +Y up, -Z toward the muzzle, +X right, metres.
# Blender conversion: B(x, y, z) = (x, -z, y), so the game frame maps to Blender Y-up
# after glTF export (same convention as tools/blender/guns.py).
#
# Outputs:
#   assets/models/storm.glb        objects "storm" (gun, origin at weapon origin)
#                                  and "storm_fan" (origin on the nozzle spin axis)
#   .claude/work/storm_preview.png two renders side by side: front-left 3/4, player view
# Textures are baked once (512 px JPEG inside the GLB). Coils get a separate emissive
# material after baking, because the bake only carries the base colour.
import sys, os, math
sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bkit
import bpy, bmesh
import numpy as np
from mathutils import Vector

ROOT = "/Users/alex/射擊遊戲"
GLB = os.path.join(ROOT, "assets/models/storm.glb")
PREVIEW = os.path.join(ROOT, ".claude/work/storm_preview.png")
argv = sys.argv[sys.argv.index("--") + 1:]
WORK = os.path.abspath(argv[0])
TEX = os.path.join(WORK, "storm_tex")
os.makedirs(WORK, exist_ok=True)
os.makedirs(os.path.dirname(GLB), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
AY = 0.015  # weapon axis height (game y); the nozzle mouth is at y = 0.015


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)


# ---------------------------------------------------------------- mesh helpers (game coords in)

def lathe_pts(profile, segs, cx, cy):
    """Revolve (r, z) points around the vertical axis at (cx, cy). A leading or trailing r=0 point closes that end with a fan."""
    pts = list(profile)
    cs, ce = pts[0][0] == 0, pts[-1][0] == 0
    if cs:
        pts = pts[1:]
    if ce:
        pts = pts[:-1]
    V, F, base = [], [], []
    for r, z in pts:
        base.append(len(V))
        for s in range(segs):
            a = 2 * math.pi * s / segs
            V.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    for i in range(len(pts) - 1):
        for s in range(segs):
            s2 = (s + 1) % segs
            F.append((base[i] + s, base[i] + s2, base[i + 1] + s2, base[i + 1] + s))
    if cs:
        c = len(V)
        V.append((cx, cy, profile[0][1]))
        for s in range(segs):
            F.append((c, base[0] + (s + 1) % segs, base[0] + s))
    if ce:
        c = len(V)
        V.append((cx, cy, profile[-1][1]))
        for s in range(segs):
            F.append((c, base[-1] + s, base[-1] + (s + 1) % segs))
    return V, F


def sweep(pts, r, sides=6):
    """Square/polygonal tube along a polyline (game coords), capped at both ends."""
    P = [Vector(p) for p in pts]
    n = len(P)
    V, F = [], []
    for i, p in enumerate(P):
        T = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        ref = Vector((0, 1, 0)) if abs(T.y) < 0.9 else Vector((1, 0, 0))
        N = T.cross(ref).normalized()
        Bv = T.cross(N).normalized()
        for s in range(sides):
            a = 2 * math.pi * s / sides
            q = p + r * (math.cos(a) * N + math.sin(a) * Bv)
            V.append((q.x, q.y, q.z))
    for i in range(n - 1):
        for s in range(sides):
            s2 = (s + 1) % sides
            F.append((i * sides + s, i * sides + s2, (i + 1) * sides + s2, (i + 1) * sides + s))
    for ring, flip in ((0, False), ((n - 1) * sides, True)):
        cen = sum((Vector(V[ring + s]) for s in range(sides)), Vector()) / sides
        c = len(V)
        V.append((cen.x, cen.y, cen.z))
        for s in range(sides):
            a, b = ring + s, ring + (s + 1) % sides
            F.append((c, b, a) if not flip else (c, a, b))
    return V, F


def mk(name, V, F, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(B(*v)) for v in V], [], [tuple(f) for f in F])
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


BOX_F = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]


def box(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.004):
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    ob = mk(name, V, BOX_F, mat)
    activate(ob)
    m = ob.modifiers.new("bev", "BEVEL")
    m.width, m.segments, m.limit_method = bevel, 2, "ANGLE"
    bpy.ops.object.modifier_apply(modifier="bev")
    bkit.box_uv(ob, size=1.0)
    return ob


def flag(ob, coil=0, fan=0):
    """Per-face flags that survive the join and the bake, so the coils and fan can be found afterwards."""
    me = ob.data
    for nm, val in (("coil", coil), ("fan", fan)):
        a = me.attributes.new(nm, "INT", "FACE")
        for p in me.polygons:
            a.data[p.index].value = val


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ---------------------------------------------------------------- materials

tex_metal = bkit.polyhaven_texture("metal_plate_02", "1k")
tex_paint = bkit.polyhaven_texture("rusty_painted_metal", "1k")
GUN = bkit.pbr_material("gunmetal_worn", tex_metal, scale=3.0, tint=(0.5, 0.53, 0.57))
PAINT = bkit.pbr_material("dark_painted_steel", tex_paint, scale=2.5, tint=(0.45, 0.5, 0.52))
RUBBER = bkit.procedural_material("rubber_grip", base=(0.025, 0.025, 0.027), roughness=0.78,
                                  metallic=0.0, scale=14.0, bump=0.5, grime=0.1)


def plain(name, color, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    return m


COIL_BASE = plain("coil_base", (0.6, 0.92, 1.0), 0.3)  # bake colour only


def make_glow():
    m = bpy.data.materials.new("coil_glow")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.7, 0.95, 1.0, 1)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Emission Color"].default_value = (0.55, 0.95, 1.0, 1)
    b.inputs["Emission Strength"].default_value = 6.0
    return m


# ---------------------------------------------------------------- gun parts

parts = []

# Rear housing, top rail, barrel, collar, bell (all on the weapon axis at y = AY)
parts.append(box("housing", -0.06, 0.06, AY - 0.07, AY + 0.07, 0.02, 0.15, GUN))
parts.append(box("rail", -0.014, 0.014, AY + 0.055, AY + 0.08, -0.20, 0.12, GUN))
V, F = lathe_pts([(0, 0.02), (0.06, 0.02), (0.06, -0.30), (0, -0.30)], 32, 0, AY)
parts.append(mk("barrel", V, F, GUN, smooth=True))
V, F = lathe_pts([(0.058, -0.255), (0.068, -0.26), (0.068, -0.285), (0.058, -0.29)], 24, 0, AY)
parts.append(mk("collar", V, F, GUN, smooth=True))

zs = [-0.28, -0.36, -0.44, -0.52, -0.58, -0.61, -0.625]


def r_out(z):
    t = min(max((-0.28 - z) / 0.345, 0.0), 1.0)
    return 0.06 + 0.032 * t ** 2.5  # bell flare: slow at the throat, steep at the lip


prof = [(r_out(z), z) for z in zs] + [(r_out(z) - 0.008, z) for z in reversed(zs)]
V, F = lathe_pts(prof, 28, 0, AY)
parts.append(mk("bell", V, F, GUN, smooth=True))

# Pressure tanks: one on the left of the housing, a smaller one on the right
V, F = lathe_pts([(0, 0.13), (0.030, 0.13), (0.034, 0.125), (0.034, -0.015), (0.030, -0.02), (0, -0.02)],
                 20, -0.045, 0.02)
parts.append(mk("tank_l", V, F, PAINT, smooth=True))
V, F = lathe_pts([(0, 0.135), (0.018, 0.135), (0.022, 0.13), (0.022, 0.0), (0.018, -0.005), (0, -0.005)],
                 16, 0.05, -0.02)
parts.append(mk("tank_r", V, F, PAINT, smooth=True))

# Pistol grip (rubber, hold point (0, -0.09, 0.13)), trigger guard, fore-grip (hold (0, -0.04, -0.34))
G_V = [(-0.018, -0.045, 0.095), (0.018, -0.045, 0.095), (0.018, -0.045, 0.165), (-0.018, -0.045, 0.165),
       (-0.016, -0.15, 0.11), (0.016, -0.15, 0.11), (0.016, -0.15, 0.18), (-0.016, -0.15, 0.18)]
parts.append(mk("grip", G_V, BOX_F, RUBBER, smooth=False))
V, F = sweep([(0, -0.05, 0.085), (0, -0.10, 0.085), (0, -0.115, 0.065), (0, -0.10, 0.042), (0, -0.05, 0.035)],
             0.0055, 6)
parts.append(mk("guard", V, F, GUN, smooth=True))
V, F = sweep([(0, AY - 0.035, -0.34), (0, AY - 0.115, -0.34)], 0.016, 8)
parts.append(mk("fore_grip", V, F, RUBBER, smooth=True))
parts.append(box("bracket", -0.02, 0.02, AY - 0.075, AY - 0.03, -0.37, -0.31, GUN))

# Glowing coils: 4 turns of helix wound on the barrel between the housing and the collar
pts, N, Rc = [], 64, 0.0695
for k in range(N + 1):
    t = k / N
    a = 2 * math.pi * 4 * t
    pts.append((Rc * math.cos(a), AY + Rc * math.sin(a), -0.07 + (-0.22 + 0.07) * t))
V, F = sweep(pts, 0.0055, 4)
parts.append(mk("coils", V, F, COIL_BASE, smooth=True))

# Fan: six pitched blades and a hub, built in world coordinates (axis at z = -0.56)
A = Vector((0.0, AY, -0.56))
FV, FF = [], []
alpha = math.radians(35)
for i in range(6):
    phi = i * math.pi / 3
    u = Vector((math.cos(phi), math.sin(phi), 0))
    t = Vector((-math.sin(phi), math.cos(phi), 0))
    z = Vector((0, 0, 1))
    v = t * math.cos(alpha) + z * math.sin(alpha)
    w = -t * math.sin(alpha) + z * math.cos(alpha)
    base = len(FV)
    for r in (0.02, 0.064):
        for c in (-0.012, 0.012):
            for th in (-0.0025, 0.0025):
                p = A + r * u + c * v + th * w
                FV.append((p.x, p.y, p.z))
    FF += [tuple(base + k for k in f) for f in
           [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]]
hv, hf = lathe_pts([(0, -0.59), (0.022, -0.59), (0.022, -0.53), (0, -0.53)], 12, 0.0, AY)
off = len(FV)
FV += hv
FF += [tuple(k + off for k in f) for f in hf]
FAN_MAT = plain("fan_blade", (0.5, 0.52, 0.55), 0.35)  # light steel so the blades read inside the dark bell
parts.append(mk("fan", FV, FF, FAN_MAT, smooth=False))

# Flags: coils and fan are identified by face attribute after the bake
for ob in parts:
    flag(ob, coil=1 if ob.name == "coils" else 0, fan=1 if ob.name == "fan" else 0)

pre = sum(tris(o) for o in parts)
print(f"BKIT_PARTS tris_before_bevel_and_bake={pre}")

# ---------------------------------------------------------------- join, bake, split

bkit.join(parts, "storm")
storm = bpy.data.objects["storm"]
me = storm.data
print("BKIT_ATTRS", [a.name for a in me.attributes])
bkit.bake_to_textures(storm, TEX, size=512, samples=16)

me = storm.data
coil_flag = [a.value for a in me.attributes["coil"].data]
fan_flag = [a.value for a in me.attributes["fan"].data]
print(f"BKIT_FLAGS coil_faces={sum(coil_flag)} fan_faces={sum(fan_flag)}")

glow = make_glow()
me.materials.append(glow)
for p in me.polygons:
    p.material_index = 1 if coil_flag[p.index] else 0

# split the fan out of the storm mesh, keeping the baked UVs
before = {o.name for o in bpy.data.objects}
activate(storm)
bpy.ops.object.mode_set(mode="EDIT")
bm = bmesh.from_edit_mesh(me)
bm.faces.ensure_lookup_table()
bpy.ops.mesh.select_all(action="DESELECT")
for f in bm.faces:
    f.select_set(bool(fan_flag[f.index]))
bmesh.update_edit_mesh(me)
bpy.ops.mesh.separate(type="SELECTED")
bpy.ops.object.mode_set(mode="OBJECT")
fan = next(o for o in bpy.data.objects if o.name not in before)
fan.name = "storm_fan"
fan.data.name = "storm_fan"

# fan origin on the nozzle spin axis (world = weapon frame)
scene.cursor.location = B(0.0, AY, -0.56)
activate(fan)
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
scene.cursor.location = (0, 0, 0)

print(f"BKIT_TRIS storm={tris(storm)} storm_fan={tris(fan)} total={tris(storm) + tris(fan)}")
bkit.check([storm, fan], max_tris=3000, ground=False)
bkit.export_glb(GLB, objs=[storm, fan], image_format="JPEG")
print(f"BKIT_FILE {GLB} bytes={os.path.getsize(GLB)}")

# ---------------------------------------------------------------- preview: front-left 3/4 and player view

bkit.light_studio()


def render_cam(path, eye, target, lens, size):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cam = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(cam)
    cam.location = B(*eye)
    d = (B(*target) - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.film_transparent = False
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return path


SZ = 640
p1 = render_cam(os.path.join(WORK, "view_3q.png"), (0.62, 0.40, -1.00), (0.0, 0.0, -0.24), 50, SZ)
p2 = render_cam(os.path.join(WORK, "view_player.png"), (0.0, 0.22, 0.62), (0.0, -0.02, -0.22), 35, SZ)

imgs = [bpy.data.images.load(p, check_existing=False) for p in (p1, p2)]
arrs = [np.array(im.pixels[:], dtype=np.float32).reshape(SZ, SZ, 4) for im in imgs]
combined = np.concatenate(arrs, axis=1)
out = bpy.data.images.new("storm_preview", 2 * SZ, SZ, alpha=True)
out.pixels.foreach_set(combined.ravel())
out.filepath_raw = PREVIEW
out.file_format = "PNG"
out.save()
print(f"BKIT_PREVIEW {PREVIEW}")
