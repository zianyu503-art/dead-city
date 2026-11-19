# 第十四關 BOSS 遠古巨獸 (ice-age mammoth, thawed and infected) for 死城突圍.
#
#   python3 tools/blender/ancient.py  (via run.py)  -> assets/models/ancient.glb + previews
#   nohup python3 /Users/alex/.claude/skills/blender-modeling/scripts/run.py tools/blender/ancient.py .claude/work
#
# Game frame: +Y up, +Z forward, metres. Blender is Z-up, so B(x,y,z) = (x, -z, y) and glTF export is Y-up.
# Objects keep the names/origins the game expects:
#   ancient_body      origin on the ground under the middle (body centred (0, 3.5, 0))
#   ancient_crystals  body frame (glowing ice spine + infected veins; the weak point)
#   ancient_head      origin at the neck joint (0, 3.9, 3.3) on the body
#   ancient_leg_front / ancient_leg_back   origin at the hip (mesh hangs to y -2.9); the game
#                     places them at (+-1.25, 2.9, +-2.2) and mirrors them, so they are symmetric in x
#   ancient_tail      origin at its root (0, 3.7, -3.4)
# Only the hide parts (body, head, legs, tail) share one baked 1024 texture set; crystals are a flat emissive material.
import sys, math, random

sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bpy, bmesh
from mathutils import Vector
from mathutils.noise import noise as pnoise
import bkit

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW_DIR = argv[0] if argv else "/Users/alex/射擊遊戲/.claude/work"
GLB = "/Users/alex/射擊遊戲/assets/models/ancient.glb"
BAKE_DIR = "/private/tmp/claude-504/-Users-alex-----/69755db1-c3e1-420f-87ae-2eed74aa1f3b/scratchpad/ancient_bake"
BUDGET = 14000

bkit.reset_scene()
random.seed(11)


def B(x, y, z):
    """game (+Y up, +Z forward) -> Blender (Z up)"""
    return Vector((x, -z, y))


def nz(p, f, seed):
    return pnoise(Vector(p) * f + Vector((seed, seed * 0.37, seed * 0.71)))


# ------------------------------------------------------------------ materials
def mkmat(name, base, rough, var=0.2, scale=4.0, bump=0.3, grime=0.3):
    """Procedural PBR (object coords); baked into the shared hide texture set."""
    return bkit.procedural_material(name, base, variation=var, roughness=rough, scale=scale, bump=bump, grime=grime)


def flat(name, base, rough, alpha=1.0, emit=None, strength=0.0):
    """Plain Principled values only, so glTF keeps the colour/emission (no node-driven inputs)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


MAT = {
    "fur": mkmat("ancient_fur", (0.28, 0.23, 0.19), 0.9, var=0.35, scale=6.0, bump=0.2, grime=0.4),
    "skin": mkmat("ancient_skin", (0.36, 0.39, 0.44), 0.7, var=0.2, scale=5.0, bump=0.08, grime=0.2),
    "frost": mkmat("frost_crust", (0.80, 0.88, 0.95), 0.35, var=0.08, scale=5.0, bump=0.0, grime=0.0),
    "ivory": mkmat("ivory", (0.84, 0.79, 0.67), 0.4, var=0.1, scale=6.0, bump=0.0, grime=0.1),
    "crack": mkmat("crack", (0.10, 0.08, 0.06), 0.8, var=0.1, scale=8.0, bump=0.05, grime=0.3),
    "eye": mkmat("eye", (0.50, 0.85, 1.0), 0.2, var=0.05, scale=8.0, bump=0.0, grime=0.0),
    "crystal": flat("ancient_crystal", (0.45, 0.85, 1.0), 0.08, alpha=0.72, emit=(0.30, 0.85, 1.0), strength=1.6),
    "vein": flat("ancient_vein", (0.10, 0.12, 0.14), 0.5, emit=(0.55, 0.90, 1.0), strength=4.0),
}
HIDE = {"fur", "skin", "frost", "ivory", "crack", "eye"}


# ------------------------------------------------------------------ geometry (local game coords)
def jit(p, c, amp, seed):
    if not amp:
        return p
    d = p - c
    if d.length < 1e-6:
        return p
    return p + d.normalized() * amp * nz(p, 1.6, seed)


def shell(rings, c0=None, c1=None):
    S = len(rings[0])
    V, F, idx = [], [], []
    for ring in rings:
        idx.append(len(V))
        V += ring
    for k in range(len(rings) - 1):
        a, b = idx[k], idx[k + 1]
        for j in range(S):
            j2 = (j + 1) % S
            F.append((a + j, a + j2, b + j2, b + j))
    if c0 is not None:
        ci = len(V); V.append(c0)
        for j in range(S):
            F.append((ci, idx[0] + (j + 1) % S, idx[0] + j))
    if c1 is not None:
        ci = len(V); V.append(c1); a = idx[-1]
        for j in range(S):
            F.append((ci, a + j, a + (j + 1) % S))
    return V, F


def ell(c, r, mat, sides=24, rows=12, amp=0.0, seed=0.0):
    c = Vector(c); r = Vector(r); rings = []
    for i in range(1, rows):
        th = math.pi * i / rows
        ring = []
        for j in range(sides):
            ph = math.tau * j / sides
            p = c + Vector((math.sin(th) * math.cos(ph) * r.x, math.cos(th) * r.y, math.sin(th) * math.sin(ph) * r.z))
            ring.append(jit(p, c, amp, seed))
        rings.append(ring)
    V, F = shell(rings, c + Vector((0, r.y, 0)), c - Vector((0, r.y, 0)))
    return (V, F, mat)


def _cr(path, radii, sub):
    P = [Vector(p) for p in path]; n = len(P)
    rad = list(radii) if isinstance(radii, (list, tuple)) else [radii] * n
    out_p, out_r = [], []
    for s in range(n - 1):
        p0, p1, p2, p3 = P[max(s - 1, 0)], P[s], P[s + 1], P[min(s + 2, n - 1)]
        for k in range(sub):
            t = k / sub; t2 = t * t; t3 = t2 * t
            out_p.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
            out_r.append(rad[s] + (rad[s + 1] - rad[s]) * t)
    out_p.append(P[-1]); out_r.append(rad[-1])
    return out_p, out_r


def tube(path, radii, mat, sides=10, sub=3, amp=0.0, seed=0.0):
    pts, rs = _cr(path, radii, sub)
    n = len(pts); rings = []
    for i in range(n):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 1, 0)))
        if u.length < 0.2:
            u = t.cross(Vector((1, 0, 0)))
        u.normalize(); w = t.cross(u).normalized()
        ring = []
        for j in range(sides):
            a = math.tau * j / sides
            d = u * math.cos(a) + w * math.sin(a)
            q = pts[i] + d * rs[i]
            if amp:
                q = q + d * rs[i] * amp * nz(q, 2.0, seed)
            ring.append(q)
        rings.append(ring)
    V, F = shell(rings, pts[0], pts[-1])
    return (V, F, mat)


def tuft(root, tip, r, mat, sides=6, seed=0.0, bend=0.0):
    root = Vector(root); tip = Vector(tip)
    mid = root.lerp(tip, 0.5) + Vector((bend, 0, bend * 0.5))
    return tube([root, mid, tip], [r, r * 0.75, r * 0.2], mat, sides=sides, sub=2, amp=0.22, seed=seed)


def build(name, loc, pieces):
    """One mesh object: pieces are (verts, faces, material key); verts are local to loc."""
    verts, faces, mids, keys = [], [], [], []
    for V, F, key in pieces:
        if key not in keys:
            keys.append(key)
        base = len(verts)
        verts += [B(*p) for p in V]
        faces += [tuple(base + i for i in f) for f in F]
        mids += [keys.index(key)] * len(F)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for k in keys:
        me.materials.append(MAT[k])
    for p, mi in zip(me.polygons, mids):
        p.material_index = mi
        p.use_smooth = True
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(*loc)
    return ob


# ------------------------------------------------------------------ body shape helpers
def surf_x(y, z):  # half-width of the trunk at height y, depth z
    return 1.9 * math.sqrt(max(0.03, 1 - ((y - 3.5) / 1.75) ** 2 - (z / 3.5) ** 2))


def top_y(z):  # top of trunk and shoulder hump at depth z
    y = 3.5 + 1.75 * math.sqrt(max(0.03, 1 - (z / 3.5) ** 2))
    if z > -0.3:
        y = max(y, 4.7 + 0.95 * math.sqrt(max(0.0, 1 - ((z - 1.3) / 1.5) ** 2)))
    return y


# ------------------------------------------------------------------ ancient_body
body_p = [
    ell((0, 3.5, 0), (1.9, 1.75, 3.5), "fur", sides=28, rows=16, amp=0.05, seed=1),
    ell((0, 4.7, 1.3), (1.45, 0.95, 1.5), "fur", sides=20, rows=10, amp=0.08, seed=2),
]
for k in range(30):  # matted clumps hanging off the flanks and belly
    side = random.choice((-1, 1)); z = random.uniform(-3.0, 3.0); y = random.uniform(2.4, 4.0)
    x = side * surf_x(y, z) * 0.97
    tip = (x * 1.06 + side * 0.05, y - random.uniform(0.9, 1.5), z + random.uniform(-0.25, 0.25))
    body_p.append(tuft((x, y, z), tip, random.uniform(0.16, 0.26), "fur", sides=6, seed=k))
for k in range(8):  # clumps falling over the shoulder hump
    z = random.uniform(0.2, 2.2); x = random.uniform(-0.9, 0.9); y = top_y(z) - 0.25
    body_p.append(tuft((x, y, z), (x * 1.2, y - 1.0, z + 0.1), 0.17, "fur", sides=6, seed=100 + k))
for k in range(5):  # frostbitten bare grey skin on the flanks
    side = random.choice((-1, 1)); z = random.uniform(-2.2, 2.2); y = random.uniform(2.8, 4.0)
    body_p.append(ell((side * (surf_x(y, z) - 0.05), y, z), (0.2, 0.32, 0.45), "skin", sides=12, rows=6, amp=0.1, seed=k))
for k in range(6):  # frost crust on the hump and flanks
    if k < 3:
        z = random.uniform(0.3, 2.2); c = (random.uniform(-0.8, 0.8), top_y(z) - 0.1, z)
        body_p.append(ell(c, (0.35, 0.12, 0.4), "frost", sides=12, rows=6, amp=0.1, seed=k))
    else:
        side = random.choice((-1, 1)); z = random.uniform(-2.0, 2.0); y = random.uniform(3.2, 4.2)
        body_p.append(ell((side * surf_x(y, z), y, z), (0.12, 0.3, 0.4), "frost", sides=12, rows=6, amp=0.1, seed=k))
for k in range(14):  # icicles hanging from the belly
    side = random.choice((-1, 1)); z = random.uniform(-2.5, 2.5); y = 2.2
    root = (side * surf_x(y, z) * 0.98, y, z)
    body_p.append(tube([root, (root[0], y - random.uniform(0.5, 0.9), z)], [0.06, 0.01], "frost", sides=5, sub=2))
body = build("ancient_body", (0, 0, 0), body_p)

# ------------------------------------------------------------------ ancient_crystals (body frame)
cr = []
for k in range(14):  # jagged ice crystals growing out of the spine and hump
    z = -2.7 + k * 0.4 + random.uniform(-0.1, 0.1)
    x = [-0.45, -0.15, 0.15, 0.45][k % 4] + random.uniform(-0.08, 0.08)
    yb = top_y(z) - 0.45 - x * x * 0.25
    h = random.uniform(0.9, 1.6); lean = random.uniform(-0.4, 0.4)
    mid = (x + lean * 0.1 + random.uniform(-0.05, 0.05), yb + h * 0.5, z - 0.05)
    tip = (x + lean * 0.5, yb + h, z - random.uniform(0.2, 0.5))
    cr.append(tube([(x, yb, z), mid, tip], [0.2, 0.15, 0.02], "crystal", sides=5, sub=2, amp=0.08, seed=k))
for k in range(6):  # infected pale-blue veins running down the flanks from the crystals
    side = 1 if k % 2 else -1; z = -2.5 + k * 1.0 + random.uniform(-0.2, 0.2)
    pts = [(side * (surf_x(y, z) + 0.03) + random.uniform(-0.05, 0.05), y, z + 0.15 * math.sin(y * 5 + k))
           for y in (4.9, 4.1, 3.3, 2.6)]
    cr.append(tube(pts, [0.04, 0.035, 0.03, 0.02], "vein", sides=4, sub=2))
crystals = build("ancient_crystals", (0, 0, 0), cr)

# ------------------------------------------------------------------ ancient_head (origin at the neck joint)
head_p = [
    ell((0, -0.1, 1.0), (1.05, 1.1, 1.35), "fur", sides=24, rows=14, amp=0.05, seed=3),
    ell((0, 0.35, 1.5), (0.95, 0.35, 0.6), "fur", sides=20, rows=8, amp=0.05, seed=4),
    ell((0, -0.35, 2.0), (0.6, 0.6, 0.8), "skin", sides=16, rows=10, amp=0.04, seed=5),
    tube([(0, -0.4, 2.5), (0, -1.1, 2.9), (0, -1.9, 2.8), (0, -2.4, 2.5)], [0.32, 0.27, 0.2, 0.13], "skin", sides=12, sub=3, amp=0.05, seed=6),
]
for s in (-1, 1):
    head_p.append(ell((s * 0.95, 0.2, 0.6), (0.15, 0.55, 0.45), "skin", sides=12, rows=6, amp=0.05, seed=7 + s))
    head_p.append(ell((s * 0.55, 0.2, 1.95), (0.16, 0.12, 0.1), "eye", sides=10, rows=6))
# right tusk is cracked: two segments with a dark crack band between them
head_p.append(tube([(0.45, -0.6, 2.0), (0.85, -1.6, 2.7), (1.02, -1.85, 3.15)], [0.17, 0.15, 0.13], "ivory", sides=10, sub=3))
head_p.append(tube([(1.02, -1.85, 3.15), (1.06, -1.9, 3.25)], [0.135, 0.12], "crack", sides=10, sub=1))
head_p.append(tube([(1.06, -1.9, 3.25), (1.12, -2.0, 3.6), (0.85, -1.3, 4.4)], [0.12, 0.09, 0.02], "ivory", sides=10, sub=3))
head_p.append(tube([(-0.45, -0.6, 2.0), (-0.85, -1.6, 2.7), (-1.1, -2.0, 3.6), (-0.85, -1.3, 4.4)], [0.17, 0.15, 0.13, 0.05], "ivory", sides=10, sub=3))
for k in range(12):  # matted hair hanging off the skull
    s = random.choice((-1, 1)); x = s * random.uniform(0.6, 0.95)
    y = random.uniform(-0.3, 0.4); z = random.uniform(0.3, 1.4)
    head_p.append(tuft((x, y, z), (x + s * 0.1, y - random.uniform(0.7, 1.1), z + random.uniform(-0.1, 0.2)), 0.14, "fur", sides=6, seed=200 + k))
head = build("ancient_head", (0, 3.9, 3.3), head_p)


# ------------------------------------------------------------------ ancient_leg_front / ancient_leg_back (origin at the hip)
def leg_pieces(zf):
    p = [
        ell((0, -0.6, 0), (0.75, 1.0, 0.8), "fur", sides=20, rows=12, amp=0.08, seed=zf),
        tube([(0, -1.1, 0), (0, -2.0, 0.02), (0, -2.7, 0.0)], [0.6, 0.5, 0.48], "skin", sides=14, sub=2, amp=0.03, seed=5),
        ell((0, -2.7, 0.1), (0.8, 0.2, 0.85), "skin", sides=20, rows=8, amp=0.03, seed=8),
    ]
    for x in (-0.4, 0.0, 0.4):  # toenails, pointing forward
        p.append(tube([(x, -2.78, 0.7), (x, -2.9, 0.92)], [0.12, 0.06], "ivory", sides=6, sub=1))
    for k in range(9):  # matted hair hanging off the thigh and pillar
        a = random.uniform(0, math.tau)
        p.append(tuft((math.sin(a) * 0.55, -0.6 - random.uniform(0, 0.6), math.cos(a) * 0.55),
                      (math.sin(a) * 0.75, -2.0 - random.uniform(0, 0.4), math.cos(a) * 0.75), 0.16, "fur", sides=6, seed=300 + k))
    return p


leg_front = build("ancient_leg_front", (0, 0, 0), leg_pieces(1))
leg_back = build("ancient_leg_back", (0, 0, 0), leg_pieces(-1))

# ------------------------------------------------------------------ ancient_tail (origin at its root)
tail_p = [tube([(0, 0, 0), (0, -0.5, -0.7), (0, -1.2, -1.1), (0, -2.0, -1.3)], [0.35, 0.3, 0.2, 0.1], "fur", sides=10, sub=3, amp=0.06, seed=6),
          tuft((0, -1.8, -1.25), (0, -2.4, -1.35), 0.2, "fur", sides=6, seed=400),
          tuft((0.05, -1.9, -1.2), (0.05, -2.5, -1.3), 0.15, "fur", sides=6, seed=401),
          tuft((-0.05, -1.9, -1.2), (-0.05, -2.45, -1.3), 0.15, "fur", sides=6, seed=402)]
tail = build("ancient_tail", (0, 3.7, -3.4), tail_p)

ORIG = [body, crystals, head, leg_front, leg_back, tail]
HIDE_OBJS = [body, head, leg_front, leg_back, tail]

# ------------------------------------------------------------------ one shared 1024 texture set for the hide
src = HIDE_OBJS
comb_V, comb_F, comb_mat_idx, poly_start = [], [], [], {}
mats_all = []
for ob in src:
    me = ob.data
    vb = len(comb_V)
    comb_V += [ob.matrix_world @ v.co for v in me.vertices]
    poly_start[ob.name] = len(comb_F)
    for p in me.polygons:
        comb_F.append(tuple(vb + i for i in p.vertices))
        key = me.materials[p.material_index]
        if key not in mats_all:
            mats_all.append(key)
        comb_mat_idx.append(mats_all.index(key))
cme = bpy.data.meshes.new("ancient_combined")
cme.from_pydata(comb_V, [], comb_F)
for m in mats_all:
    cme.materials.append(m)
for p, mi in zip(cme.polygons, comb_mat_idx):
    p.material_index = mi
comb = bpy.data.objects.new("ancient_combined", cme)
bpy.context.scene.collection.objects.link(comb)
bkit.bake_to_textures(comb, BAKE_DIR, size=1024, samples=16)
bake_mat = cme.materials[0]
cuv = cme.uv_layers["UVMap"].data
for ob in src:
    me = ob.data
    s = poly_start[ob.name]
    me.materials.clear(); me.materials.append(bake_mat)
    for p in me.polygons:
        p.material_index = 0
    uv = me.uv_layers.new(name="UVMap")
    for j, p in enumerate(me.polygons):
        cp = cme.polygons[s + j]
        for li, lc in zip(p.loop_indices, cp.loop_indices):
            uv.data[li].uv = cuv[lc].uv
bpy.data.objects.remove(comb, do_unlink=True)
bpy.data.meshes.remove(cme)
bkit.uv_unwrap(crystals)

# ------------------------------------------------------------------ checks, report, export
bkit.check(objs=ORIG, max_tris=BUDGET, ground=False)
rep = bkit.report(ORIG)
print("BKIT_PARTS", {o.name: bkit.tri_count(o) for o in ORIG})
_placed = {o: o.location.copy() for o in ORIG}
for o in ORIG:  # the game hangs each part at its own joint, so the file keeps every part at the origin
    o.location = (0, 0, 0)
bkit.export_glb(GLB, objs=ORIG, image_format="JPEG")
for o, loc in _placed.items():  # back in place for the previews
    o.location = loc
print("BKIT_GLB", GLB)

# ------------------------------------------------------------------ previews in the game pose (legs at their pivots)
legs_inst = []
for src_leg, xs, zs in ((leg_front, (1.25, -1.25), 2.2), (leg_back, (1.25, -1.25), -2.2)):
    for x in xs:
        o = bpy.data.objects.new(src_leg.name + "_pose", src_leg.data)
        bpy.context.scene.collection.objects.link(o)
        o.location = B(x, 2.9, zs)
        legs_inst.append(o)
assembled = [body, crystals, head, tail] + legs_inst

scene = bpy.context.scene
bkit.light_studio()
sl = bpy.data.lights.new("sun", "SUN"); sl.energy = 3.0
so = bpy.data.objects.new("sun", sl)
scene.collection.objects.link(so)
so.rotation_euler = (math.radians(50), 0, math.radians(30))
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.render.resolution_x = scene.render.resolution_y = 900
scene.render.image_settings.file_format = "PNG"


def shot(name, direction):
    bkit._frame_camera(assembled, direction, margin=0.9)
    scene.render.filepath = f"{PREVIEW_DIR}/{name}"
    bpy.ops.render.render(write_still=True)
    print("BKIT_PREVIEW", f"{PREVIEW_DIR}/{name}")


shot("ancient_side.png", (1, 0, 0))                 # side view (game +X)
shot("ancient_front34.png", (0.7, -0.7, 0.25))      # front three-quarter (game +Z and +X)
