"""Kraken boss (level 12) for 死城突圍: kraken_head, kraken_eye, kraken_tentacle.

Game coordinates: +Y up, +Z toward the player, metres. B() maps them to Blender
(Z up, game +Z = Blender -Y); the glTF export turns this into Y-up with +Z forward.
Each object's origin is where the game expects it: head at the body base, eye at
its centre, tentacle at its base. The eye and tentacle are positioned only in the
preview; the exported file keeps them at their own origins.

Run:  python3 /Users/alex/.claude/skills/blender-modeling/scripts/run.py \
          tools/blender/kraken.py .claude/work
"""
import math
import os
import random
import sys

sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bkit  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector, noise  # noqa: E402

OUT = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
GLB = "/Users/alex/射擊遊戲/assets/models/kraken.glb"
TEX = "/private/tmp/claude-504/-Users-alex-----/69755db1-c3e1-420f-87ae-2eed74aa1f3b/scratchpad/kraken_tex"
EYE_C = (0.0, 8.5, 6.6)


# ------------------------------------------------------------------ helpers

def B(x, y, z):
    """Game coordinates to Blender."""
    return Vector((x, -z, y))


def clamp01(t):
    return min(1.0, max(0.0, t))


def smooth(e0, e1, x):
    t = clamp01((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    for i in range(len(xs) - 1):
        if x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + (ys[i + 1] - ys[i]) * t
    return ys[-1]


def fbm(p, octaves=3):
    s, a, f = 0.0, 0.5, 1.0
    for _ in range(octaves):
        s += a * noise.noise(p * f)
        a *= 0.5
        f *= 2.0
    return s


def make_obj(name, verts, faces, mats, face_mat=None):
    """Build a mesh from game-space verts, outward normals, smooth shading."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(B(*v)) for v in verts], [], faces)
    for m in mats:
        me.materials.append(m)
    if face_mat:
        for p, mi in zip(me.polygons, face_mat):
            p.material_index = mi
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    me.update()
    bkit.shade_smooth(ob)
    return ob


def catmull(ctrl, samples):
    P = [Vector(c) for c in ctrl]
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(samples):
            t = s / samples
            t2 = t * t
            t3 = t2 * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


def sweep(ctrl, rad, M, samples=4, ref=(0, 0, 1)):
    """Tube along a smooth curve. rad: list of radii spread along it, or f(t) for t in 0..1.
    Cross-sections use a frame whose normal is the projection of ref, so the +Z side
    of the tentacle is stable. Returns verts, faces and per-ring data."""
    pts = catmull(ctrl, samples)
    n = len(pts)
    if callable(rad):
        rf = rad
    else:
        xs = [i / (len(rad) - 1) for i in range(len(rad))]
        rf = lambda t: interp(xs, rad, t)  # noqa: E731
    refv = Vector(ref)
    frames = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        T = (b - a).normalized()
        N = (refv - T * T.dot(refv)).normalized()
        L = T.cross(N).normalized()
        frames.append((T, N, L))
    verts, faces, rings = [], [], []
    for i, c in enumerate(pts):
        T, N, L = frames[i]
        r = rf(i / (n - 1))
        b = len(verts)
        for k in range(M):
            a = 2 * math.pi * k / M
            verts.append(tuple(c + (N * math.cos(a) + L * math.sin(a)) * r))
        rings.append((b, c, T, N, L, r))
    for i in range(n - 1):
        b0, b1 = rings[i][0], rings[i + 1][0]
        for k in range(M):
            k1 = (k + 1) % M
            faces.append((b0 + k, b0 + k1, b1 + k1, b1 + k))
    for ri in (0, n - 1):
        b, c = rings[ri][0], rings[ri][1]
        cen = len(verts)
        verts.append(tuple(c))
        for k in range(M):
            faces.append((cen, b + k, b + (k + 1) % M))
    return verts, faces, rings


def tube_obj(name, ctrl, rad, M, samples, ref, mat):
    v, f, _ = sweep(ctrl, rad, M, samples, ref)
    return make_obj(name, v, f, [mat])


def ellipsoid(c, ax, nu, nv):
    verts, faces = [], []
    base = []
    for j in range(1, nv):
        ph = math.pi * j / nv
        start = len(verts)
        for i in range(nu):
            th = 2 * math.pi * i / nu
            verts.append((c[0] + ax[0] * math.sin(ph) * math.cos(th),
                          c[1] + ax[1] * math.sin(ph) * math.sin(th),
                          c[2] + ax[2] * math.cos(ph)))
        base.append(start)
    north = len(verts)
    verts.append((c[0], c[1], c[2] + ax[2]))
    south = len(verts)
    verts.append((c[0], c[1], c[2] - ax[2]))
    for k in range(len(base) - 1):
        b0, b1 = base[k], base[k + 1]
        for i in range(nu):
            i1 = (i + 1) % nu
            faces.append((b0 + i, b0 + i1, b1 + i1, b1 + i))
    for i in range(nu):
        i1 = (i + 1) % nu
        faces.append((north, base[0] + i, base[0] + i1))
        faces.append((south, base[-1] + i1, base[-1] + i))
    return verts, faces


# ------------------------------------------------------------------ head

RING_Y = [0.0, 1.0, 3.0, 6.0, 9.0, 11.5, 13.0, 14.0, 14.7]
RING_R = [3.7, 4.5, 5.7, 6.15, 5.95, 5.2, 3.9, 2.4, 0.9]
RIDGE_T = [(k / 7 - 0.5) * 2.0 for k in range(8)]


def mantle_point(th, y):
    """Point on the mantle: revolved profile, ridges, wrinkles, and the eye socket."""
    th = math.atan2(math.sin(th), math.cos(th))
    r = interp(RING_Y, RING_R, y)
    ridge = 0.0
    for tk in RIDGE_T:
        d = (th - tk) * r
        ridge += math.exp(-(d / 0.35) ** 2)
    ridge *= 0.10 * smooth(1.0, 3.5, y) * (1 - smooth(12.5, 14.5, y))
    x = r * math.sin(th)
    z = 0.95 * r * math.cos(th)
    f = 1.0 + ridge + 0.06 * fbm(Vector((x * 0.45, y * 1.6, z * 0.45)), 3)
    x *= f
    z *= f
    if z > 0.5:
        dxy = math.hypot(x, y - EYE_C[1])
        z -= 1.6 * smooth(2.2, 0.5, dxy)                       # deep socket floor
        z += 0.9 * math.exp(-((dxy - 2.5) / 0.5) ** 2)         # raised lid rim
    return (x, y, z)


def mantle_mesh(NU=72, NV=44):
    verts, faces = [], []
    for j in range(NV):
        y = 14.7 * j / (NV - 1)
        for i in range(NU):
            verts.append(mantle_point(2 * math.pi * i / NU, y))
    top = len(verts)
    verts.append((0.0, 15.0, 0.0))
    bot = len(verts)
    verts.append((0.0, 0.0, 0.0))

    def idx(i, j):
        return j * NU + (i % NU)

    for j in range(NV - 1):
        for i in range(NU):
            faces.append((idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)))
    for i in range(NU):
        faces.append((top, idx(i, NV - 1), idx(i + 1, NV - 1)))
        faces.append((bot, idx(i + 1, 0), idx(i, 0)))
    return verts, faces


def barnacles(seed=4, n=70):
    rnd = random.Random(seed)
    verts, faces = [], []
    placed = 0
    while placed < n:
        th = rnd.uniform(-math.pi, math.pi)
        y = rnd.uniform(1.8, 13.0)
        p = Vector(mantle_point(th, y))
        if p.z > 0.5 and math.hypot(p.x, p.y - EYE_C[1]) < 3.4:
            continue  # keep the eye socket clear
        nrm = Vector((math.sin(th), 0.12, 0.95 * math.cos(th))).normalized()
        u = nrm.cross(Vector((0, 1, 0))).normalized()
        w = nrm.cross(u)
        h = rnd.uniform(0.25, 0.45)
        rb = rnd.uniform(0.22, 0.35)
        base = p - nrm * 0.05
        b0 = len(verts)
        for k in range(6):
            a = 2 * math.pi * k / 6
            verts.append(tuple(base + (u * math.cos(a) + w * math.sin(a)) * rb))
        tip = len(verts)
        verts.append(tuple(p + nrm * h))
        for k in range(6):
            faces.append((b0 + k, b0 + (k + 1) % 6, tip))
        placed += 1
    return verts, faces


# ------------------------------------------------------------------ materials

def _nodes(mat):
    return bkit._nodes(mat)


def _mix(nt, fac, a, b):
    """Colour mix: result = a where fac is 0, b where fac is 1. a/b: socket or RGB tuple."""
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    ins = {s.identifier: s for s in n.inputs}
    nt.links.new(fac, ins["Factor_Float"])
    for key, v in (("A_Color", a), ("B_Color", b)):
        if isinstance(v, tuple):
            ins[key].default_value = (*v, 1.0)
        else:
            nt.links.new(v, ins[key])
    return {s.identifier: s for s in n.outputs}["Result_Color"]


def _ramp(nt, fac, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    for k, (pos, col) in enumerate(stops):
        e = els[k] if k < len(els) else els.new(pos)
        e.position = pos
        e.color = (*col, 1.0)
    nt.links.new(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def _noise(nt, vec, scale, detail, rough=0.5):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def skin_mat(name, seed, pale):
    """Mottled purple-red wet skin, pale underside, green-yellow veins and pustules, scars."""
    mat = bpy.data.materials.new(name)
    nt, bsdf = _nodes(mat)
    N = nt.nodes
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (seed * 5.3, seed * 2.9, seed * 7.1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    V = mp.outputs["Vector"]
    mot = _noise(nt, V, 1.3, 6, 0.55)
    fine = _noise(nt, V, 6.0, 5)
    vein = _ramp(nt, _noise(nt, V, 2.6, 7),
                 [(0.47, (0, 0, 0)), (0.5, (1, 1, 1)), (0.53, (0, 0, 0))])
    vor = N.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 4.2
    nt.links.new(V, vor.inputs["Vector"])
    pust = _ramp(nt, vor.outputs["Distance"], [(0.0, (1, 1, 1)), (0.09, (0, 0, 0))])
    scar = _ramp(nt, _noise(nt, V, 2.2, 4), [(0.58, (0, 0, 0)), (0.7, (1, 1, 1))])

    c = _mix(nt, mot, (0.11, 0.02, 0.04), (0.26, 0.05, 0.08))
    if pale:
        sep = N.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
        # ColorRamp positions are clamped to 0..1, so scale height into that range first
        hz = N.new("ShaderNodeMath")
        hz.operation = "MULTIPLY"
        hz.inputs[1].default_value = 0.2
        nt.links.new(sep.outputs["Z"], hz.inputs[0])
        under = _ramp(nt, hz.outputs["Value"], [(0.36, (1, 1, 1)), (0.9, (0, 0, 0))])
        c = _mix(nt, under, c, (0.52, 0.40, 0.36))
    c = _mix(nt, scar, c, (0.40, 0.31, 0.29))
    # veins and pustules glow faintly: keep them subtle so they do not read as camouflage
    vf = N.new("ShaderNodeMath")
    vf.operation = "MULTIPLY"
    vf.inputs[1].default_value = 0.3
    nt.links.new(vein, vf.inputs[0])
    pf = N.new("ShaderNodeMath")
    pf.operation = "MULTIPLY"
    pf.inputs[1].default_value = 0.55
    nt.links.new(pust, pf.inputs[0])
    c = _mix(nt, vf.outputs["Value"], c, (0.42, 0.60, 0.10))
    c = _mix(nt, pf.outputs["Value"], c, (0.66, 0.76, 0.16))

    m = N.new("ShaderNodeMath")
    m.operation = "MULTIPLY_ADD"
    nt.links.new(fine, m.inputs[0])
    m.inputs[1].default_value = 0.22
    m.inputs[2].default_value = 0.16
    nt.links.new(m.outputs["Value"], bsdf.inputs["Roughness"])
    nt.links.new(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Coat Weight"].default_value = 0.4
    bsdf.inputs["Coat Roughness"].default_value = 0.08
    return mat


def iris_mat():
    mat = bpy.data.materials.new("kraken_eye_iris")
    nt, bsdf = _nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n = _noise(nt, tc.outputs["Object"], 3.5, 6)
    c = _ramp(nt, n, [(0.3, (0.42, 0.13, 0.02)), (0.55, (0.95, 0.52, 0.07)), (0.8, (1.0, 0.78, 0.18))])
    nt.links.new(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.1
    return mat


def barnacle_mat():
    mat = bpy.data.materials.new("kraken_barnacle")
    nt, bsdf = _nodes(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    c = _ramp(nt, _noise(nt, tc.outputs["Object"], 9, 5),
              [(0.35, (0.36, 0.33, 0.27)), (0.7, (0.66, 0.62, 0.52))])
    nt.links.new(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    return mat


def flat_mat(name, col, rough):
    mat = bpy.data.materials.new(name)
    _, bsdf = _nodes(mat)
    bsdf.inputs["Base Color"].default_value = (*col, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def add_emission(obj, strength):
    """After baking: the glow follows the baked colour, so dark pupil stays dark."""
    mat = obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    links = bsdf.inputs["Base Color"].links
    if links:
        nt.links.new(links[0].from_socket, bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength

def render(path, pos, tgt, lens=50, res=(960, 720)):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("kraken_cam")
    cd.lens = lens
    cam = bpy.data.objects.new("kraken_cam", cd)
    bpy.context.collection.objects.link(cam)
    cam.location = B(*pos)
    cam.rotation_euler = (B(*tgt) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


# ------------------------------------------------------------------ build

bkit.reset_scene()

mat_skin = skin_mat("kraken_skin", 1, pale=True)
mat_tent = skin_mat("kraken_tentacle_skin", 2, pale=False)
mat_barn = barnacle_mat()
mat_horn = flat_mat("kraken_beak", (0.13, 0.09, 0.05), 0.35)
mat_sucker = flat_mat("kraken_sucker", (0.62, 0.58, 0.42), 0.4)
mat_iris = iris_mat()
mat_pupil = flat_mat("kraken_pupil", (0.015, 0.012, 0.01), 0.3)

# head
mv, mf = mantle_mesh()
parts = [make_obj("mantle", mv, mf, [mat_skin])]
bv, bf = barnacles()
parts.append(make_obj("barnacles", bv, bf, [mat_barn]))
parts.append(tube_obj("beak_upper",
                      [(0, 1.4, 4.2), (0, 1.2, 5.4), (0, 0.9, 6.5), (0, 0.45, 7.3), (0, 0.0, 7.4), (0, -0.15, 7.1)],
                      [1.2, 1.0, 0.75, 0.45, 0.22, 0.08], 14, 4, (0, 1, 0), mat_horn))
parts.append(tube_obj("beak_lower",
                      [(0, 0.5, 4.2), (0, 0.45, 5.4), (0, 0.35, 6.4), (0, 0.15, 6.8)],
                      [0.9, 0.7, 0.45, 0.1], 14, 4, (0, 1, 0), mat_horn))
for th in (-1.5, -0.9, -0.35, 0.35, 0.9, 1.5):  # six stumps curling down and out
    s, c = math.sin(th), math.cos(th)
    ctrl = [(3.3 * s, 0.6, 3.3 * c), (5.4 * s, -0.9, 5.0 * c), (7.3 * s, -2.4, 6.2 * c),
            (8.4 * s, -3.7, 7.0 * c + 0.5), (7.8 * s, -4.6, 7.9 * c + 0.9)]
    parts.append(tube_obj("stump", ctrl, [1.25, 1.2, 1.05, 0.9, 0.7], 12, 4, (0, 0, 1), mat_skin))
head = bkit.join(parts, "kraken_head")
bkit.bake_to_textures(head, os.path.join(TEX, "head"), size=768)

# eye: iris + horizontal slit pupil, origin at the eye's centre
iv, iff = ellipsoid((0, 0, 0), (1.7, 1.7, 1.25), 28, 14)
pv, pf = ellipsoid((0, 0, 1.1), (1.05, 0.2, 0.22), 16, 6)
eye = bkit.join([make_obj("eye_iris", iv, iff, [mat_iris]),
                 make_obj("eye_pupil", pv, pf, [mat_pupil])], "kraken_eye")
bkit.bake_to_textures(eye, os.path.join(TEX, "eye"), size=256)
add_emission(eye, 1.2)

# tentacle: base at origin, rises along +Y, curls toward +Z
TC = [(0, 0, 0), (0, 5, 0.4), (0, 10, 1.6), (0, 14.5, 3.8), (0, 17.5, 7.0), (0, 18.5, 10.5)]
tv, tf, rings = sweep(TC, lambda t: 0.12 + 1.38 * (1 - t) ** 1.5, 18, 16, (0, 0, 1))
tfm = [0] * len(tf)
for i, (b, c, T, N, L, r) in enumerate(rings):  # two rows of suckers on the +Z side
    if i < 3 or i > len(rings) - 6 or r < 0.25 or i % 2:
        continue
    for sgn in (-1, 1):
        a = sgn * 0.5
        d = N * math.cos(a) + L * math.sin(a)
        w = d.cross(T).normalized()
        s = 0.18 * r
        pc = c + d * (r + 0.1 * s)
        cen = len(tv)
        tv.append(tuple(pc + d * 0.1 * s))
        r0 = len(tv)
        for k in range(6):
            q = 2 * math.pi * k / 6
            tv.append(tuple(pc - d * 0.3 * s + (T * math.cos(q) + w * math.sin(q)) * s))
        for k in range(6):
            tf.append((cen, r0 + k, r0 + (k + 1) % 6))
            tfm.append(1)
tent = make_obj("kraken_tentacle", tv, tf, [mat_tent, mat_sucker], face_mat=tfm)
bkit.bake_to_textures(tent, os.path.join(TEX, "tentacle"), size=768)

# checks and budgets
bkit.check([head], max_tris=12000)
bkit.check([eye], max_tris=1000)
bkit.check([tent], max_tris=4000)
for ob in (head, eye, tent):
    print("BKIT_TRIS", ob.name, bkit.tri_count(ob))

bkit.export_glb(GLB, objs=[head, eye, tent], image_format="JPEG")
print("BKIT_GLB", GLB, os.path.getsize(GLB), "bytes")

# preview: place the eye in its socket and the tentacle beside the head
eye.location = B(*EYE_C)
tent.location = B(10.5, 0, 0)
bkit.light_studio()
az, el = math.radians(25), math.radians(14)
tgt = (2.0, 7.0, 1.5)
dist = 30.0
pos = (tgt[0] + dist * math.cos(el) * math.sin(az), tgt[1] + dist * math.sin(el),
       tgt[2] + dist * math.cos(el) * math.cos(az))
render(os.path.join(OUT, "kraken_front34.png"), pos, tgt)
render(os.path.join(OUT, "kraken_eye.png"), (0, 9.5, EYE_C[2] + 12.0), EYE_C, lens=85)
print("BKIT_PREVIEW", OUT)
