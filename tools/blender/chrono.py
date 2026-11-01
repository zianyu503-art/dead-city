# 永劫・時空沙漏 (legendary time rifle) for 死城突圍: a clockwork rifle of gold and crystal.
#
#   blender -b -P tools/blender/chrono.py -- assets/models/chrono.glb [preview.png]
#
# Game frame (+Y up, +Z toward the camera), the same as buildGun: the muzzle toward -Z, the stock toward +Z, the grip
# below the origin. Separate objects the game turns on their own:
#   chrono        the rifle
#   chrono_gear_a/b/c   gears behind the glass on the left side, each about its own centre, turning about X
#   chrono_glass  the hourglass on top (frame and glass), about its own centre; chrono_sand the glowing sand inside it
# Materials are swapped for the game's own; chr_glow, chr_sand and chr_crystal glow or shine.
import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "chrono.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
COLORS = dict(chr_gold=(0.9, 0.62, 0.2), chr_brass=(0.55, 0.36, 0.14), chr_dark=(0.03, 0.035, 0.06), chr_crystal=(0.4, 0.85, 1.0),
              chr_glow=(0.3, 0.9, 1.0), chr_sand=(1.0, 0.75, 0.3), chr_face=(0.9, 0.86, 0.76), chr_ticks=(0.05, 0.04, 0.03))
MATS = {}


def mat(name):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes.get("Principled BSDF"); c = COLORS[name]
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Metallic"].default_value = 1.0 if name in ("chr_gold", "chr_brass") else 0.0
        b.inputs["Roughness"].default_value = 0.22 if name in ("chr_gold", "chr_brass", "chr_crystal") else 0.5
        if name in ("chr_glow", "chr_sand"):
            b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 5
        if name == "chr_crystal":
            b.inputs["Alpha"].default_value = 0.35
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
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()
    if smooth:
        ob.data.shade_smooth()
    return ob


def put(ob, m, smooth=True):
    ob.data.materials.append(mat(m)); return tidy(ob, smooth)


def box(name, p, size, m, bevel=0.004, smooth=False):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*p)); ob = bpy.context.object; ob.name = name; ob.scale = (size[0], size[2], size[1])
    activate(ob); bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = ob.modifiers.new("b", "BEVEL"); bv.width = bevel; bv.segments = 3; bpy.ops.object.modifier_apply(modifier="b")
    return put(ob, m, smooth)


def cyl(name, p0, p1, r0, r1, m, seg=24):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=r0, radius2=r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.name = name; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return put(ob, m)


def sphere(name, p, rad, m, seg=16, rings=10, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=rad, location=B(*p))
    ob = bpy.context.object; ob.name = name; ob.scale = (scale[0], scale[2], scale[1])
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return put(ob, m)


def torus(name, R, r, m, at, axis="Z", seg=32, mseg=8, arc=None):
    rot = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]  # Blender axes: Z ring = around the game's Y
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=mseg)
    ob = bpy.context.object; ob.name = name; ob.rotation_euler = rot; ob.location = B(*at)
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return put(ob, m)


def lathe(name, prof, m, seg=32):
    verts, faces, n = [], [], len(prof)
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for r, h in prof:
            verts.append(B(r * math.cos(a), h, r * math.sin(a)))
    for i in range(seg):
        j = (i + 1) % seg
        for k in range(n - 1):
            faces.append((i * n + k, j * n + k, j * n + k + 1, i * n + k + 1))
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    return put(ob, m)


def gear(name, R, teeth, thick, m, hole=0.3):
    """A gear lying in the game's YZ plane (axle along X), centred on the origin, with spokes cut out."""
    bm = bmesh.new(); outer = []
    for i in range(teeth * 4):
        a = 2 * math.pi * i / (teeth * 4); r = R if (i % 4) in (1, 2) else R * 0.84
        outer.append((r * math.cos(a), r * math.sin(a)))
    inner = [(R * hole * math.cos(2 * math.pi * i / 24), R * hole * math.sin(2 * math.pi * i / 24)) for i in range(24)]
    rim = [(R * 0.72 * math.cos(2 * math.pi * i / 48), R * 0.72 * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    def ring(pts_a, pts_b, x):
        va = [bm.verts.new(B(x, p[1], p[0])) for p in pts_a]; vb = [bm.verts.new(B(x, p[1], p[0])) for p in pts_b]; return va, vb
    for x in (-thick / 2, thick / 2):
        pass
    # teeth band (outer -> rim) and hub (rim -> hole) as two flat annuli on each face, joined at the edges
    faces_sets = []
    def annulus(pa, pb, x, flip):
        na, nb = len(pa), len(pb)
        va = [bm.verts.new(B(x, p[1], p[0])) for p in pa]; vb = [bm.verts.new(B(x, p[1], p[0])) for p in pb]
        # resample the coarser ring onto the finer one's index
        for i in range(na):
            j0 = int(i * nb / na) % nb; j1 = int((i + 1) * nb / na) % nb
            quad = [va[i], va[(i + 1) % na], vb[j1], vb[j0]] if j1 != j0 else [va[i], va[(i + 1) % na], vb[j0]]
            try:
                bm.faces.new(quad[::-1] if flip else quad)
            except ValueError:
                pass
        return va, vb
    fa = annulus(outer, rim, -thick / 2, True); fb = annulus(outer, rim, thick / 2, False)
    ha = annulus(rim, inner, -thick / 2 * 1.4, True); hb = annulus(rim, inner, thick / 2 * 1.4, False)
    for (a, b) in ((fa[0], fb[0]), (ha[1], hb[1])):  # side walls: teeth outline and axle hole
        n = len(a)
        for i in range(n):
            try:
                bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
            except ValueError:
                pass
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    put(ob, m, smooth=False)
    parts = [ob, torus(name + "_hub", R * 0.3, R * 0.06, m, (0, 0, 0), "X", 24, 6)]
    for k in range(5):  # spokes
        a = 2 * math.pi * k / 5
        parts.append(cyl(name + "_spoke", (0, R * 0.3 * math.sin(a), R * 0.3 * math.cos(a)), (0, R * 0.72 * math.sin(a), R * 0.72 * math.cos(a)), R * 0.06, R * 0.05, m, 8))
    return join(parts, name)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join(); ob = bpy.context.object; ob.name = name; ob.data.name = name
    return ob


R = []
# ---- receiver: a dark enamel body with gold trim and a clock face on the right
R.append(box("body", (0, 0.0, 0.0), (0.06, 0.085, 0.3), "chr_dark", 0.012, True))
for y in (0.044, -0.044):
    R.append(box("trim", (0, y, 0.0), (0.064, 0.008, 0.31), "chr_gold", 0.003))
R.append(cyl("bezel", (0.03, 0.0, 0.0), (0.036, 0.0, 0.0), 0.04, 0.04, "chr_gold", 40))
R.append(cyl("face", (0.0365, 0.0, 0.0), (0.0375, 0.0, 0.0), 0.034, 0.034, "chr_face", 40))
for k in range(12):
    a = 2 * math.pi * k / 12; L = 0.008 if k % 3 == 0 else 0.004
    R.append(box("tick", (0.038, 0.027 * math.cos(a), 0.027 * math.sin(a)), (0.002, L, 0.0016), "chr_ticks", 0))
    R[-1].data.transform(Matrix.Translation(-B(0.038, 0.027 * math.cos(a), 0.027 * math.sin(a))))
    R[-1].data.transform(Matrix.Rotation(-a, 4, "Y")); R[-1].data.transform(Matrix.Translation(B(0.038, 0.027 * math.cos(a), 0.027 * math.sin(a))))
R.append(box("hand_h", (0.0385, 0.008, -0.002), (0.0015, 0.018, 0.003), "chr_ticks", 0))
R.append(box("hand_m", (0.0385, 0.0, -0.011), (0.0015, 0.003, 0.024), "chr_ticks", 0))
R.append(sphere("pin", (0.039, 0, 0), 0.003, "chr_gold", 8, 6))
# left side: a crystal window over the gear chamber
R.append(box("window", (-0.031, 0.0, -0.01), (0.004, 0.07, 0.2), "chr_crystal", 0.003, True))
R.append(box("frame_w", (-0.033, 0.037, -0.01), (0.004, 0.006, 0.21), "chr_gold", 0.002)); R.append(box("frame_w", (-0.033, -0.037, -0.01), (0.004, 0.006, 0.21), "chr_gold", 0.002))
# ---- barrel: crystal sheath round a glowing core, gold rings, a crowned muzzle with two swept fins
R.append(cyl("sheath", (0, 0.012, -0.15), (0, 0.012, -0.6), 0.022, 0.019, "chr_crystal", 28))
R.append(cyl("core", (0, 0.012, -0.14), (0, 0.012, -0.61), 0.008, 0.007, "chr_glow", 16))
for z in (-0.16, -0.27, -0.38, -0.49, -0.58):
    R.append(torus("ring", 0.023, 0.0035, "chr_gold", (0, 0.012, z), "Y", 32, 8))
R.append(cyl("crown", (0, 0.012, -0.6), (0, 0.012, -0.64), 0.024, 0.02, "chr_gold", 28))
for k in range(6):
    a = 2 * math.pi * k / 6
    R.append(cyl("prong", (0.02 * math.cos(a), 0.012 + 0.02 * math.sin(a), -0.635), (0.024 * math.cos(a), 0.012 + 0.024 * math.sin(a), -0.67), 0.004, 0.001, "chr_gold", 8))
for s in (-1, 1):
    pts = [(s * 0.02, 0.03, -0.5), (s * 0.055, 0.05, -0.43), (s * 0.06, 0.02, -0.36), (s * 0.02, 0.02, -0.4)]
    for a, b in zip(pts, pts[1:]):
        R.append(cyl("fin", a, b, 0.004, 0.003, "chr_gold", 8))
    R.append(sphere("finball", (s * 0.06, 0.05, -0.43), 0.007, "chr_glow", 10, 8))
# underbarrel rail with gold beads
R.append(box("rail", (0, -0.035, -0.26), (0.022, 0.012, 0.26), "chr_brass", 0.003))
for k in range(8):
    R.append(sphere("bead", (0, -0.044, -0.15 - k * 0.032), 0.005, "chr_gold", 8, 6))
# ---- grip, trigger, guard
R.append(box("grip", (0, -0.09, 0.07), (0.042, 0.12, 0.05), "chr_dark", 0.01, True))
R[-1].data.transform(Matrix.Translation(-B(0, -0.09, 0.07))); R[-1].data.transform(Matrix.Rotation(-0.28, 4, "X")); R[-1].data.transform(Matrix.Translation(B(0, -0.09, 0.07)))
R.append(box("inlay", (0.0215, -0.09, 0.072), (0.003, 0.09, 0.02), "chr_gold", 0.001))
R[-1].data.transform(Matrix.Translation(-B(0, -0.09, 0.07))); R[-1].data.transform(Matrix.Rotation(-0.28, 4, "X")); R[-1].data.transform(Matrix.Translation(B(0, -0.09, 0.07)))
R.append(torus("guard", 0.03, 0.004, "chr_gold", (0, -0.05, 0.02), "X", 24, 6))
R.append(box("trigger", (0, -0.055, 0.018), (0.006, 0.026, 0.008), "chr_gold", 0.002))
# ---- stock: a skeletal gold frame with a swinging-pendulum disc
for y0, y1 in ((0.03, 0.02), (-0.03, -0.07)):
    R.append(cyl("stock", (0, y0, 0.14), (0, y1, 0.36), 0.008, 0.007, "chr_gold", 12))
R.append(box("butt", (0, -0.025, 0.37), (0.04, 0.11, 0.025), "chr_dark", 0.008, True))
R.append(cyl("pend", (0, 0.02, 0.24), (0, -0.04, 0.24), 0.0025, 0.0025, "chr_brass", 8))
R.append(cyl("pdisc", (-0.004, -0.05, 0.24), (0.004, -0.05, 0.24), 0.016, 0.016, "chr_gold", 24))
# ---- the hourglass mount on top
R.append(box("mount", (0, 0.052, -0.02), (0.05, 0.012, 0.09), "chr_gold", 0.003))
rifle = join(R, "chrono")

# ---- gears (each about its own centre)
ga = gear("chrono_gear_a", 0.03, 14, 0.006, "chr_gold")
gb = gear("chrono_gear_b", 0.02, 10, 0.006, "chr_brass")
gc = gear("chrono_gear_c", 0.024, 12, 0.006, "chr_gold")
# ---- hourglass: two glass bulbs in a three-pillar gold frame, sand inside
H = []
bulb = [(0.002, 0.0), (0.012, 0.004), (0.026, 0.018), (0.03, 0.032), (0.024, 0.046), (0.014, 0.052)]
up = lathe("bulb_u", [(r, h) for r, h in bulb], "chr_crystal", 28)
dn = lathe("bulb_d", [(r, -h) for r, h in bulb][::-1], "chr_crystal", 28)
H += [up, dn]
for y in (0.056, -0.056):
    H.append(cyl("cap", (0, y - 0.004, 0), (0, y + 0.004, 0), 0.036, 0.036, "chr_gold", 28))
    H.append(torus("capring", 0.036, 0.003, "chr_gold", (0, y, 0), "Z", 32, 6))
for k in range(3):
    a = 2 * math.pi * k / 3 + 0.5
    H.append(cyl("post", (0.032 * math.cos(a), -0.056, 0.032 * math.sin(a)), (0.032 * math.cos(a), 0.056, 0.032 * math.sin(a)), 0.0035, 0.0035, "chr_gold", 10))
    for y in (-0.03, 0.0, 0.03):
        H.append(sphere("knob", (0.032 * math.cos(a), y, 0.032 * math.sin(a)), 0.005, "chr_gold", 8, 6))
glass = join(H, "chrono_glass")
S = [lathe("sand_u", [(0.0, 0.006), (0.022, 0.03), (0.0, 0.03)], "chr_sand", 20), lathe("sand_d", [(0.0, -0.05), (0.026, -0.05), (0.0, -0.02)], "chr_sand", 20),
     cyl("stream", (0, 0.006, 0), (0, -0.02, 0), 0.0015, 0.0015, "chr_sand", 8)]
sand = join(S, "chrono_sand")

objs = (rifle, ga, gb, gc, glass, sand)
for o in objs:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_texcoords=False, export_yup=True)
print("exported", OUT, {o.name: len(o.data.polygons) for o in objs})

if PREVIEW:
    # assemble as the game does, for the picture
    for g_, p in ((ga, (-0.036, -0.005, -0.06)), (gb, (-0.036, 0.018, 0.0)), (gc, (-0.036, -0.012, 0.04))):
        g_.location = B(*p)
    glass.location = B(0, 0.12, -0.02); sand.location = B(0, 0.12, -0.02)
    for o in objs:
        o.location = o.location + Vector((0, 0, 0))
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    cam = bpy.data.cameras.new("cam"); cam.lens = 60; co = bpy.data.objects.new("cam", cam); scene.collection.objects.link(co); scene.camera = co
    co.location = (0.75, -0.35, 0.22); target = Vector((0, 0.12, 0.02))
    co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
    for loc, e in (((1, -1, 1.5), 150), ((-1, 1, 1), 80), ((1, 0.5, -0.5), 50)):
        l = bpy.data.lights.new("l", "AREA"); l.energy = e; l.size = 1; lo = bpy.data.objects.new("l", l); lo.location = loc; scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.05, 1)
    scene.render.resolution_x, scene.render.resolution_y = 1100, 700; scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
