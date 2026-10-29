# 傳世之鼓 (legendary drum weapon) for 死城突圍: the war drum and its stick for the first-person view, the giant
# sword the 戰鬥 skill brings down, and the ghostly figure the ultimate's decoys use.
#
#   blender -b -P tools/blender/drum.py -- assets/models/drum.glb [preview.png]
#
# Each object is modelled about its own origin in the game's frame (+Y up, +Z toward the camera):
#   drum         the drum, its axis along Y, top head (with the rune circle) facing +Y
#   drum_stick   the stick, grip at the origin, head toward -Z
#   giant_sword  blade pointing +Y, grip at the origin
#   ghost        a standing figure, feet at the origin, facing +Z
# Material names are what the game swaps for its own materials; drum_rune and sword_rune glow in the colour of
# the chosen skill.
import bpy, bmesh, math, random, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "drum.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(5)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

COLORS = dict(drum_red=(0.32, 0.025, 0.02), drum_hide=(0.62, 0.5, 0.33), drum_gold=(0.8, 0.55, 0.16), drum_brass=(0.55, 0.38, 0.12),
              drum_wood=(0.22, 0.11, 0.05), drum_rope=(0.5, 0.04, 0.03), drum_rune=(0.4, 0.6, 1.0), drum_dark=(0.05, 0.03, 0.025),
              sword_blade=(0.75, 0.78, 0.82), sword_gold=(0.8, 0.55, 0.16), sword_grip=(0.08, 0.05, 0.04), sword_gem=(0.9, 0.1, 0.1),
              sword_rune=(1.0, 0.8, 0.3), ghost=(0.5, 0.6, 1.0))
MATS = {}


def mat(name):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF"); c = COLORS[name]
        b.inputs["Base Color"].default_value = (*c, 1)
        metal = name in ("drum_gold", "drum_brass", "sword_gold", "sword_blade")
        b.inputs["Metallic"].default_value = 1.0 if metal else 0.0
        b.inputs["Roughness"].default_value = 0.3 if metal or name == "drum_red" else 0.75
        if name in ("drum_rune", "sword_rune", "sword_gem", "ghost"):
            b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 4
        MATS[name] = m
    return MATS[name]


def B(x, y, z):
    return Vector((x, -z, y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def obj(name, me, m):
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    ob.data.materials.append(mat(m))
    return ob


def tidy(ob, smooth=True):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()
    if smooth:
        ob.data.shade_smooth()
    return ob


def lathe(name, prof, m, seg=48, fn=None, axis="Y"):
    """Revolve a profile [(r, h)] about the game's Y axis (or Z); fn(r, h, angle) reshapes it."""
    verts, faces, n = [], [], len(prof)
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for r, h in prof:
            rr = fn(r, h, a) if fn else r
            x, z = rr * math.cos(a), rr * math.sin(a)
            verts.append(B(x, h, z) if axis == "Y" else B(x, z, h))
    for i in range(seg):
        j = (i + 1) % seg
        for k in range(n - 1):
            faces.append((i * n + k, j * n + k, j * n + k + 1, i * n + k + 1))
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces)
    return tidy(obj(name, me, m))


def torus(name, R, r, m, y=0.0, seg=48, mseg=10, sy=1.0, rot=None, at=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=mseg)
    ob = bpy.context.object; ob.name = name
    ob.scale = (1, 1, sy)
    if rot:
        ob.rotation_euler = rot
    ob.location = B(at[0], at[1] + y, at[2])
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.append(mat(m))
    return tidy(ob)


def sphere(name, p, rad, m, seg=12, rings=8, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=rad, location=B(*p))
    ob = bpy.context.object; ob.name = name; ob.scale = (scale[0], scale[2], scale[1])
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.append(mat(m))
    return tidy(ob)


def box(name, p, size, m, rot_y=0.0, rot_x=0.0, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    ob = bpy.context.object; ob.name = name; ob.scale = (size[0], size[2], size[1])
    activate(ob); bpy.ops.object.transform_apply(scale=True)
    if bevel:
        b = ob.modifiers.new("b", "BEVEL"); b.width = bevel; b.segments = 2; bpy.ops.object.modifier_apply(modifier="b")
    ob.data.transform(Matrix.Rotation(rot_x, 4, "X") @ Matrix.Rotation(-rot_y, 4, "Z"))
    ob.data.transform(Matrix.Translation(B(*p)))
    ob.data.materials.append(mat(m))
    return tidy(ob, smooth=False)


def cyl(name, p0, p1, r0, r1, m, seg=16):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=r0, radius2=r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.name = name
    ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.append(mat(m))
    return tidy(ob)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    return ob


# =====================================================================
# the drum: a barrel of lacquered staves, two hide heads, brass tacks, gold hoops, ring handles with tassels
# =====================================================================
H, R = 0.115, 0.165  # half height, radius at the heads
parts = []


def stave_shell(r, h, a):  # bulging barrel with a groove between each of 24 staves
    bulge = 0.032 * math.cos(h / H * math.pi / 2)
    groove = 0.0025 * max(0.0, math.cos(a * 24)) ** 12
    return r + bulge - groove


prof = [(R - 0.004, -H), (R, -H + 0.004)] + [(R, -H + 0.004 + i * (2 * H - 0.008) / 20) for i in range(1, 20)] + [(R, H - 0.004), (R - 0.004, H)]
parts.append(lathe("shell", prof, "drum_red", seg=96, fn=stave_shell))
# inside of the shell, so the open rims never show the back faces
parts.append(lathe("inner", [(R - 0.012, H - 0.004), (R - 0.012, -H + 0.004)], "drum_dark", seg=48))
for sgn in (-1, 1):
    y = sgn * (H + 0.002)
    # the hide head, slightly domed, and its rolled edge lapping over the shell
    head = [(0.0, y + sgn * 0.006)] + [(R * k / 10, y + sgn * 0.006 * (1 - (k / 10) ** 2)) for k in range(1, 11)] + [(R + 0.006, y - sgn * 0.004)]
    parts.append(lathe("head", head, "drum_hide", seg=72))
    parts.append(torus("lap", R + 0.004, 0.0055, "drum_hide", y=y - sgn * 0.004, seg=72))
    # a ring of round-headed brass tacks holding the hide, and a second offset ring below it
    for ring, (dy, n, rad) in enumerate(((-sgn * 0.016, 40, 0.0055), (-sgn * 0.03, 40, 0.004))):
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * ring) / n
            rr = stave_shell(R, y + dy, a) + 0.001
            parts.append(sphere("tack", (rr * math.cos(a), y + dy, rr * math.sin(a)), rad, "drum_brass", 8, 5, (1, 1, 1)))
    # gold hoop
    parts.append(torus("hoop", stave_shell(R, y - sgn * 0.045, 0) + 0.003, 0.0045, "drum_gold", y=y - sgn * 0.045, seg=96, mseg=8))
# carved band round the waist: a gold strap with raised diamonds and cloud scrolls between them
parts.append(torus("band", R + 0.032 + 0.002, 0.007, "drum_gold", y=0.0, seg=96, mseg=8, sy=1.8))
for i in range(16):
    a = 2 * math.pi * i / 16; rr = R + 0.032 + 0.008
    d = box("diamond", (rr * math.cos(a), 0, rr * math.sin(a)), (0.016, 0.016, 0.006), "drum_gold", rot_y=-a + math.pi / 2, bevel=0.002)
    d.data.transform(Matrix.Translation(-B(rr * math.cos(a), 0, rr * math.sin(a))))
    d.data.transform(Matrix.Rotation(math.pi / 4, 4, Vector(B(math.cos(a), 0, math.sin(a)))))
    d.data.transform(Matrix.Translation(B(rr * math.cos(a), 0, rr * math.sin(a))))
    parts.append(d)
    for k in (-1, 1):  # little scrolls either side of each diamond
        b = a + k * 0.09
        parts.append(torus("scroll", 0.006, 0.0018, "drum_gold", seg=12, mseg=6, rot=(0, math.pi / 2, -b + math.pi / 2),
                           at=((rr - 0.003) * math.cos(b), 0.012 * k, (rr - 0.003) * math.sin(b))))
# two ring handles on brass mounts, each with a red tassel
for sgn in (-1, 1):
    x = sgn * (R + 0.034)
    parts.append(sphere("mount", (sgn * (R + 0.028), 0.045, 0), 0.014, "drum_brass", 16, 10, (1, 1.2, 1)))
    parts.append(torus("handle", 0.026, 0.0045, "drum_brass", seg=32, mseg=8, rot=(0, math.pi / 2, 0), at=(x + sgn * 0.012, 0.045 - 0.026, 0)))
    parts.append(sphere("knot", (x + sgn * 0.012, 0.045 - 0.054, 0), 0.008, "drum_rope", 12, 8))
    for j in range(9):  # tassel strands
        ang = 2 * math.pi * j / 9
        top = (x + sgn * 0.012 + 0.004 * math.cos(ang), 0.045 - 0.058, 0.004 * math.sin(ang))
        bot = (top[0] + 0.006 * math.cos(ang), top[1] - 0.07 - random.uniform(0, 0.012), top[2] + 0.006 * math.sin(ang))
        parts.append(cyl("strand", top, bot, 0.0026, 0.0012, "drum_rope", 6))
    parts.append(cyl("cap", (x + sgn * 0.012, 0.045 - 0.052, 0), (x + sgn * 0.012, 0.045 - 0.064, 0), 0.006, 0.008, "drum_gold", 12))
# rune circle on the top head: a double ring, eight glyphs round it and a swirl in the middle
top_y = H + 0.002 + 0.0065
for rr, w in ((0.138, 0.0028), (0.118, 0.0016), (0.05, 0.0018)):
    parts.append(torus("rune_ring", rr, w, "drum_rune", y=top_y - 0.0002 * (rr / 0.05), seg=96, mseg=6, sy=0.35))
GLYPHS = [[(0, 0, 0.022, 0), (0, 0, 0.022, 90), (0.006, 0.006, 0.01, 45)], [(0, 0, 0.022, 0), (-0.006, 0, 0.012, 60), (0.006, 0, 0.012, -60)],
          [(0, 0.007, 0.02, 0), (0, -0.007, 0.02, 0), (0, 0, 0.016, 90)], [(0, 0, 0.022, 30), (0, 0, 0.022, -30), (0, -0.008, 0.012, 0)],
          [(-0.007, 0, 0.02, 90), (0.007, 0, 0.02, 90), (0, 0.008, 0.016, 0)], [(0, 0, 0.024, 0), (0, 0.006, 0.012, 90), (0, -0.006, 0.012, 90)],
          [(0, 0, 0.02, 45), (0, 0, 0.02, -45), (0, 0, 0.012, 90)], [(0, 0.008, 0.02, 0), (-0.006, -0.002, 0.014, 70), (0.006, -0.002, 0.014, -70)]]
for i, g in enumerate(GLYPHS):
    a = 2 * math.pi * i / 8 + math.pi / 8; cx, cz = 0.0975 * math.cos(a), 0.0975 * math.sin(a)
    for (ox, oz, ln, deg) in g:
        ux, uz = math.cos(a + math.pi / 2), math.sin(a + math.pi / 2)  # glyph axes: across and along the radius
        px, pz = cx + ux * ox + math.cos(a) * oz, cz + uz * ox + math.sin(a) * oz
        parts.append(box("glyph", (px, top_y + 0.0006, pz), (0.0026, 0.0014, ln), "drum_rune", rot_y=-(a + math.radians(deg)), bevel=0.0005))
for k in range(2):  # the swirl: two comma shapes chasing each other round the centre
    for t in range(14):
        a = k * math.pi + t * 0.22; rr = 0.008 + t * 0.0028
        parts.append(sphere("swirl", (rr * math.cos(a), top_y + 0.0004, rr * math.sin(a)), 0.0032 + t * 0.0002, "drum_rune", 8, 4, (1, 0.35, 1)))
drum = join(parts, "drum")

# =====================================================================
# the stick: carved shaft, cord-wrapped grip, brass butt cap with a tassel, a cloth-wrapped striking head
# =====================================================================
sp = []
sp.append(lathe("shaft", [(0.0105, 0.07), (0.0108, 0.0), (0.0098, -0.12), (0.0088, -0.25), (0.0082, -0.30)], "drum_wood", seg=20, axis="Z"))
for z in (-0.02, -0.26, -0.275):  # carved rings
    sp.append(torus("ring", 0.0104 if z > -0.1 else 0.0088, 0.0016, "drum_gold", seg=24, mseg=6, rot=(math.pi / 2, 0, 0), at=(0, 0, z)))
for t in range(26):  # cord wrapped round the grip
    sp.append(torus("cord", 0.0112, 0.0018, "drum_rope", seg=20, mseg=6, rot=(math.pi / 2 + 0.12, 0, 0), at=(0, 0, 0.062 - t * 0.0028)))
sp.append(lathe("butt", [(0.0, 0.098), (0.008, 0.095), (0.0125, 0.085), (0.0118, 0.07)], "drum_brass", seg=20, axis="Z"))
sp.append(sphere("head", (0, 0, -0.318), 0.024, "drum_red", 20, 14, (1, 1, 1.05)))
sp.append(torus("tie", 0.0135, 0.0026, "drum_gold", seg=20, mseg=6, rot=(math.pi / 2, 0, 0), at=(0, 0, -0.297)))
for j in range(8):
    ang = 2 * math.pi * j / 8
    sp.append(cyl("tassel", (0.003 * math.cos(ang), 0.003 * math.sin(ang) - 0.004, 0.1), (0.009 * math.cos(ang), -0.06 - 0.01 * math.sin(ang), 0.115), 0.0022, 0.001, "drum_rope", 6))
stick = join(sp, "drum_stick")

# =====================================================================
# the giant sword: a diamond-section blade with a fuller and glowing runes, winged guard, wrapped grip, gem pommel
# =====================================================================
L, W, T = 1.45, 0.11, 0.022
bm = bmesh.new()
rows = []
for i in range(25):
    t = i / 24; y = 0.06 + t * L
    w = W * (1 - 0.15 * t) if t < 0.86 else W * (1 - 0.15 * 0.86) * (1 - (t - 0.86) / 0.14) ** 0.9
    th = T * (1 - 0.5 * t)
    # cross-section: edge, bevel, flat, fuller, flat, bevel, edge (and back), so the light catches the bevels
    sec = [(w, 0), (w * 0.72, th * 0.55), (w * 0.3, th), (w * 0.14, th * 0.7), (0, th * 0.62), (-w * 0.14, th * 0.7), (-w * 0.3, th), (-w * 0.72, th * 0.55),
           (-w, 0), (-w * 0.72, -th * 0.55), (-w * 0.3, -th), (-w * 0.14, -th * 0.7), (0, -th * 0.62), (w * 0.14, -th * 0.7), (w * 0.3, -th), (w * 0.72, -th * 0.55)]
    if t >= 0.999:
        sec = [(0, 0)] * len(sec)
    rows.append([bm.verts.new(B(x, y, z)) for x, z in sec])
for a, b in zip(rows, rows[1:]):
    n = len(a)
    for k in range(n):
        try:
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
        except ValueError:
            pass
bm.faces.new(rows[0][::-1])
me = bpy.data.meshes.new("blade"); bm.to_mesh(me); bm.free()
blade = tidy(obj("blade", me, "sword_blade"), smooth=False)
swp = [blade]
for i in range(9):  # rune strips down the fuller, both faces
    y = 0.16 + i * 0.12
    for s in (-1, 1):
        swp.append(box("srune", (0, y, s * T * (1 - 0.5 * (y - 0.06) / L) * 0.66), (0.008, 0.05 if i % 3 else 0.03, 0.002), "sword_rune", rot_y=0, bevel=0.0008))
        swp[-1].data.transform(Matrix.Translation(-B(0, y, 0))); swp[-1].data.transform(Matrix.Rotation(0.6 if i % 2 else -0.6, 4, Vector((0, 1, 0)))); swp[-1].data.transform(Matrix.Translation(B(0, y, 0)))
# winged crossguard
gp = [box("guard", (0, 0.03, 0), (0.24, 0.045, 0.06), "sword_gold", bevel=0.008)]
for s in (-1, 1):
    for k in range(6):
        t = k / 5
        gp.append(sphere("wing", (s * (0.12 + t * 0.11), 0.03 + 0.06 * t * t, 0), 0.026 * (1 - 0.6 * t), "sword_gold", 14, 10, (1.3, 0.9, 0.9)))
    gp.append(sphere("gem_side", (s * 0.07, 0.03, 0.032), 0.012, "sword_gem", 14, 10))
gp.append(sphere("gem", (0, 0.035, 0.034), 0.02, "sword_gem", 18, 12, (1, 1.3, 0.7)))
gp.append(sphere("gem_b", (0, 0.035, -0.034), 0.02, "sword_gem", 18, 12, (1, 1.3, 0.7)))
# grip with raised wraps, and the pommel
gp.append(cyl("grip", (0, 0.005, 0), (0, -0.3, 0), 0.026, 0.024, "sword_grip", 18))
for k in range(11):
    gp.append(torus("wrap", 0.026, 0.0045, "sword_grip", y=-0.02 - k * 0.026, seg=18, mseg=6, rot=(0.25, 0, 0)))
gp.append(sphere("pommel", (0, -0.33, 0), 0.042, "sword_gold", 20, 14, (1, 1.15, 1)))
gp.append(sphere("pgem", (0, -0.33, 0.036), 0.016, "sword_gem", 14, 10))
gp.append(sphere("pgem_b", (0, -0.33, -0.036), 0.016, "sword_gem", 14, 10))
sword = join(swp + gp, "giant_sword")

# =====================================================================
# the ghost: a robed figure, arms raised as if beating a drum (the decoys copy the player)
# =====================================================================
def skin(name, nodes, edges, m, subdiv=2):
    me = bpy.data.meshes.new(name); me.from_pydata([B(*n[:3]) for n in nodes], edges, [])
    ob = obj(name, me, m)
    sm = ob.modifiers.new("skin", "SKIN")
    for i, n in enumerate(nodes):
        sv = me.skin_vertices[0].data[i]; sv.radius = (n[3], n[4]); sv.use_root = i == 0
    sub = ob.modifiers.new("sub", "SUBSURF"); sub.levels = subdiv
    activate(ob); bpy.ops.object.convert(target="MESH")
    return tidy(ob)


body = skin("gbody", [(0, 0.95, 0, 0.14, 0.1), (0, 1.2, 0, 0.16, 0.11), (0, 1.42, 0, 0.19, 0.12), (0, 1.55, 0, 0.07, 0.06),
                      (-0.2, 1.45, 0, 0.06, 0.06), (-0.22, 1.2, 0.18, 0.05, 0.05), (-0.12, 1.25, 0.42, 0.04, 0.04),
                      (0.2, 1.45, 0, 0.06, 0.06), (0.22, 1.25, 0.2, 0.05, 0.05), (0.1, 1.3, 0.42, 0.04, 0.04)],
            [(0, 1), (1, 2), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8), (8, 9)], "ghost")
# a long coat that flares and ripples toward the hem, a sash, a topknot
robe = lathe("robe", [(0.0, 1.05), (0.15, 1.04), (0.17, 0.96), (0.15, 0.9), (0.19, 0.7), (0.24, 0.45), (0.29, 0.2), (0.31, 0.04), (0.29, 0.0), (0.0, 0.0)],
             "ghost", seg=48, fn=lambda r, h, a: r * (1 + 0.06 * (1 - h) * math.sin(a * 7 + h * 6)))
sash = torus("sash", 0.165, 0.018, "ghost", y=0.93, seg=40, mseg=8, sy=1.6)
collar = torus("collar", 0.08, 0.02, "ghost", y=1.53, seg=24, mseg=8)
head = sphere("ghead", (0, 1.67, 0.012), 0.098, "ghost", 24, 16, (0.88, 1.12, 1))
knot = sphere("topknot", (0, 1.8, -0.03), 0.035, "ghost", 14, 10)
hands = [sphere("ghand", p, 0.04, "ghost", 14, 10) for p in ((-0.12, 1.25, 0.45), (0.1, 1.3, 0.45))]
ghost = join([body, robe, sash, collar, head, knot] + hands, "ghost")

# =====================================================================
for o in (drum, stick, sword, ghost):
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_texcoords=False, export_yup=True)
print("exported", OUT, {o.name: len(o.data.polygons) for o in (drum, stick, sword, ghost)})

if PREVIEW:
    drum.location = B(-0.45, 1.2, 0); drum.rotation_euler = (math.radians(55), 0, math.radians(20))
    stick.location = B(-0.1, 1.45, 0.1); stick.rotation_euler = (0, math.radians(-30), math.radians(35))
    sword.location = B(0.45, 0.35, 0); sword.rotation_euler = (0, math.radians(-12), 0)
    ghost.location = B(1.25, 0, 0)
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    cam = bpy.data.cameras.new("cam"); cam.lens = 50; co = bpy.data.objects.new("cam", cam); scene.collection.objects.link(co); scene.camera = co
    co.location = (0.35, -3.4, 1.15); co.rotation_euler = (math.radians(88), 0, 0)
    for loc, e in (((2, -3, 3), 600), ((-3, -2, 2), 250), ((0, 3, 2), 300)):
        l = bpy.data.lights.new("l", "AREA"); l.energy = e; l.size = 2; lo = bpy.data.objects.new("l", l); lo.location = loc; scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0.3, 0, 1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.04, 0.05, 1)
    scene.render.resolution_x, scene.render.resolution_y = 1100, 800; scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
