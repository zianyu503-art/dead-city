# 九霄・龍皇弓 (legendary bow) for the 射擊遊戲: the recurve dragon bow held in first person, its fire arrow, and the
# parts of the summoned fire dragon (head, body segment, tail, clawed leg).
#
#   blender -b -P tools/blender/dragonbow.py -- assets/models/dragonbow.glb .claude/work/dragonbow_preview.png
#
# Game frame (+Y up, +Z toward the viewer, -Z forward), metres. Every object is modelled about its own origin; positions
# are written in game coordinates and converted with B(). Each output object is ONE mesh built from parts that carry
# their own material slot. Material names are the game's own; dragon_fire glows.
import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "dragonbow.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

COLORS = dict(dragon_wood=(0.10, 0.06, 0.035), dragon_leather=(0.30, 0.075, 0.04), dragon_red=(0.58, 0.03, 0.025),
              dragon_gold=(0.95, 0.68, 0.26), dragon_fire=(1.0, 0.5, 0.08), dragon_horn=(0.92, 0.87, 0.74),
              dragon_scale=(0.36, 0.12, 0.07), dragon_belly=(0.95, 0.84, 0.55), dragon_cord=(0.85, 0.04, 0.04),
              dragon_feather=(0.3, 0.035, 0.03), dragon_dark=(0.025, 0.02, 0.02))
ROUGH = dict(dragon_wood=0.6, dragon_leather=0.55, dragon_red=0.22, dragon_gold=0.25, dragon_fire=0.4,
             dragon_horn=0.45, dragon_scale=0.4, dragon_belly=0.3, dragon_cord=0.6, dragon_feather=0.5, dragon_dark=0.5)
MATS = {}


def mat(name):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"); c = COLORS[name]
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Metallic"].default_value = 1.0 if name == "dragon_gold" else (0.3 if name in ("dragon_scale", "dragon_belly") else 0.0)
        b.inputs["Roughness"].default_value = ROUGH[name]
        if name == "dragon_fire":
            b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = 8
        MATS[name] = m
    return MATS[name]


def B(x, y, z):
    return Vector((x, -z, y))


class Geo:
    """One output object. Parts are added in game coordinates, each with a material name."""

    def __init__(self, name):
        self.name, self.v, self.f, self.mi, self.slots = name, [], [], [], []

    def add(self, part, m):
        verts, faces = part
        if m not in self.slots:
            self.slots.append(m)
        s, base = self.slots.index(m), len(self.v)
        self.v.extend(tuple(p) for p in verts)
        for f in faces:
            self.f.append(tuple(i + base for i in f)); self.mi.append(s)

    def build(self):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(B(*p)) for p in self.v], [], self.f)
        for m in self.slots:
            me.materials.append(mat(m))
        for poly, s in zip(me.polygons, self.mi):
            poly.material_index = s
        ob = bpy.data.objects.new(self.name, me); scene.collection.objects.link(ob)
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
        me.shade_smooth()
        return ob


# ---------------------------------------------------------------- geometry generators (all return (verts, faces))
def frame_from(t, up):
    """Two unit vectors perpendicular to the path direction t: u (toward up) and v = t x u."""
    t = t.normalized(); u = up - up.dot(t) * t
    for alt in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        if u.length > 1e-4:
            break
        u = alt - alt.dot(t) * t
    u = u.normalized()
    return u, t.cross(u)


def sweep(path, shape, up=(1, 0, 0), closed=False):
    """A tube along the polyline `path`. shape(t) gives the ring as (a, b) offsets along (u, v), t running 0..1."""
    P = [Vector(p) for p in path]; n = len(P); up = Vector(up)
    rings = []
    for i in range(n):
        if closed:
            T = P[(i + 1) % n] - P[i - 1]
        elif i == 0:
            T = P[1] - P[0]
        elif i == n - 1:
            T = P[-1] - P[-2]
        else:
            T = P[i + 1] - P[i - 1]
        u, v = frame_from(T, up)
        t = i / (n - 1) if not closed else i / n
        rings.append([P[i] + u * a + v * b for a, b in shape(t)])
    m, R = len(rings[0]), len(rings)
    verts = [p for r in rings for p in r]
    faces = []
    for i in range(R if closed else R - 1):
        j = (i + 1) % R
        for k in range(m):
            k1 = (k + 1) % m
            faces.append((i * m + k, i * m + k1, j * m + k1, j * m + k))
    if not closed:
        faces.append(tuple(range(m)))
        faces.append(tuple(range((R - 1) * m, R * m))[::-1])
    return verts, faces


def circ(a, b=None, n=10):
    b = a if b is None else b
    return [(a * math.cos(2 * math.pi * k / n), b * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rrect(a, b, n=10, s=0.4):
    """Rounded rectangle (superellipse with exponent s) with half-sizes a and b."""
    out = []
    for k in range(n):
        th = 2 * math.pi * k / n; c, si = math.cos(th), math.sin(th)
        out.append((a * math.copysign(abs(c) ** s, c), b * math.copysign(abs(si) ** s, si)))
    return out


def tube(path, r0, r1=None, n=10, up=(1, 0, 0)):
    r1 = r0 if r1 is None else r1
    return sweep(path, lambda t: circ(r0 + (r1 - r0) * t, n=n), up=up)


def ring_geo(c, R, r, normal, Rz=None, n=20, m=6):
    """A torus lying in the plane perpendicular to `normal`, centre c, major radius R (Rz: the other one if elliptic)."""
    nrm = Vector(normal).normalized(); e1 = nrm.orthogonal().normalized(); e2 = nrm.cross(e1)
    Rz = R if Rz is None else Rz
    path = [Vector(c) + e1 * (R * math.cos(2 * math.pi * k / n)) + e2 * (Rz * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return sweep(path, lambda t: circ(r, n=m), up=nrm, closed=True)


def blob_geo(c, rad, n=10, rings=6, half=False, ax=(1, 0, 0), ay=(0, 1, 0), az=(0, 0, 1)):
    """An ellipsoid with radii rad along ax, ay, az; with half=True a dome standing on its flat base (normal ay)."""
    c = Vector(c); ax, ay, az = Vector(ax), Vector(ay), Vector(az); ra, rb, rc = rad
    bot = math.pi / 2 if half else math.pi
    verts, rows = [], []
    for i in range(rings + 1):
        phi = bot * i / rings; s, co = math.sin(phi), math.cos(phi)

        def P(th):
            return c + ax * (ra * s * math.cos(th)) + ay * (rb * co) + az * (rc * s * math.sin(th))
        if i == 0 or (not half and i == rings):  # a pole: one vertex shared by the whole ring
            verts.append(P(0.0)); rows.append([len(verts) - 1] * n)
        else:
            idx = []
            for j in range(n):
                verts.append(P(2 * math.pi * j / n)); idx.append(len(verts) - 1)
            rows.append(idx)
    faces = []
    for i in range(rings):
        a, b = rows[i], rows[i + 1]
        for k in range(n):
            k1 = (k + 1) % n; q = []
            for x in (a[k], a[k1], b[k1], b[k]):
                if not q or q[-1] != x:
                    q.append(x)
            if len(q) > 1 and q[0] == q[-1]:
                q.pop()
            if len(q) >= 3:
                faces.append(tuple(q))
    if half:
        faces.append(tuple(rows[-1][::-1]))
    return verts, faces


def box_geo(c, hx, hy, hz):
    c = Vector(c)
    verts = [c + Vector((sx * hx, sy * hy, sz * hz)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    return verts, [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]


def cr(pts, per=8):
    """Catmull-Rom spline through pts (game coords), `per` samples per span, both ends kept."""
    P = [Vector(p) for p in pts]; P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for s in range(per):
            t = s / per; t2 = t * t; t3 = t2 * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return out


def at(C, f):
    """Point, unit tangent and normalised parameter at fraction f along a sampled polyline C."""
    x = f * (len(C) - 1); i = min(int(x), len(C) - 2); fr = x - i
    return C[i].lerp(C[i + 1], fr), (C[i + 1] - C[i]).normalized(), x / (len(C) - 1)


def backn(T):
    """The -Z (back) normal of a limb whose direction is T."""
    d = Vector((0, 0, -1)); return (d - d.dot(T) * T).normalized()


# =====================================================================
# dragon_bow (first-person view model, origin at the centre of the grip)
# =====================================================================
def riser_shape(t):
    return rrect(0.0135 + 0.0015 * math.sin(math.pi * t), 0.0165 + 0.001 * math.sin(math.pi * t), n=12, s=0.35)


def limb(g, s):
    """One recurve limb (s=+1 upper, -1 lower): a tapering flat blade with gold scales behind, fins and flame tongues."""
    C = cr([(0, s * y, z) for (y, z) in [(0.11, 0.0), (0.25, -0.05), (0.40, -0.065), (0.50, -0.035), (0.565, 0.045)]], per=8)
    wid = lambda t: 0.045 - 0.025 * t
    thk = lambda t: 0.02 - 0.011 * t
    g.add(sweep(C, lambda t: rrect(wid(t) / 2, thk(t) / 2, n=10, s=0.4), up=(1, 0, 0)), "dragon_red")
    for row in (0, 1):  # two staggered rows of overlapping gold scale plates on the back (-Z) face
        for k in range(7):
            p, T, t = at(C, 0.12 + 0.12 * k + 0.06 * row)
            nb = backn(T)
            c = p + Vector((-0.25 if row == 0 else 0.25, 0, 0)) * wid(t) + nb * (thk(t) / 2 - 0.002)
            g.add(blob_geo(c, (0.32 * wid(t), 0.008, 0.04), n=8, rings=2, half=True, ay=nb, az=T), "dragon_gold")
    for f in (0.22, 0.5, 0.76):  # three flame-shaped gold fins on the front (+Z) face
        p, T, t = at(C, f); fr = -backn(T)
        base = p + fr * (thk(t) / 2 - 0.002)
        path = [base, base + fr * 0.012 + T * 0.006, base + fr * 0.022 + T * 0.018, base + fr * 0.024 + T * 0.03]
        g.add(sweep(path, lambda u: circ(0.0055 * (1 - u) ** 0.7 + 0.0005, 0.002 * (1 - u) ** 0.7 + 0.0005, n=8), up=(1, 0, 0)), "dragon_gold")
    for f, xo in ((0.36, -0.008), (0.62, 0.008)):  # two glowing flame tongues
        p, T, t = at(C, f); fr = -backn(T)
        g.add(blob_geo(p + fr * (thk(t) / 2 + 0.003) + Vector((xo, 0, 0)), (0.005, 0.011, 0.005), n=8, rings=4, ay=fr, az=T), "dragon_fire")
    p, T, t = at(C, 1.0); nb = backn(T)  # tip: a small gold tail finial curling back, and the nock notch
    g.add(sweep([p, p + T * 0.012 + nb * 0.006, p + T * 0.013 + nb * 0.014, p + T * 0.002 + nb * 0.016],
                lambda u: circ(0.0034 * (1 - u) + 0.0008, n=8), up=(1, 0, 0)), "dragon_gold")
    g.add(box_geo(p, 0.002, 0.0045, 0.0022), "dragon_gold")


g = Geo("dragon_bow")
g.add(sweep([(0, -0.11 + 0.22 * k / 6, 0) for k in range(7)], riser_shape), "dragon_wood")  # riser
for k in range(13):  # leather grip wraps
    g.add(ring_geo((0, -0.042 + 0.007 * k, 0), 0.0185, 0.0028, (0, 1, 0), n=16, m=5), "dragon_leather")
g.add(box_geo((-0.0205, 0.05, 0), 0.0045, 0.0025, 0.0125), "dragon_gold")  # arrow shelf on the -X side
limb(g, 1); limb(g, -1)
# gold dragon head on top of the riser, facing -Z
g.add(blob_geo((0, 0.125, 0), (0.012, 0.016, 0.014), n=10, rings=5), "dragon_gold")
g.add(blob_geo((0, 0.158, 0), (0.017, 0.016, 0.02), n=12, rings=8), "dragon_gold")
g.add(sweep([(0, 0.16, -0.01), (0, 0.163, -0.04), (0, 0.162, -0.075)], lambda t: circ(0.013 - 0.005 * t, 0.012 - 0.005 * t, n=10), up=(1, 0, 0)), "dragon_gold")
g.add(tube(cr([(0, 0.148, -0.006), (0, 0.136, -0.035), (0, 0.112, -0.07)], per=3), 0.009, 0.006, n=8), "dragon_gold")
g.add(blob_geo((0, 0.13, -0.058), (0.0055, 0.008, 0.012), n=8, rings=4), "dragon_fire")
for s in (-1, 1):
    g.add(blob_geo((s * 0.0105, 0.172, -0.004), (0.0036, 0.0036, 0.0036), n=8, rings=4), "dragon_fire")
    g.add(blob_geo((s * 0.0105, 0.177, -0.0105), (0.0075, 0.0028, 0.0045), n=8, rings=3), "dragon_gold")
    g.add(tube(cr([(s * 0.012, 0.17, 0.0), (s * 0.02, 0.19, 0.02), (s * 0.024, 0.21, 0.045), (s * 0.02, 0.222, 0.065)], per=3), 0.0048, 0.0007, n=6), "dragon_gold")
g.add(blob_geo((0, 0.118, 0), (0.014, 0.015, 0.014), n=8, rings=4), "dragon_gold")
# gold tail ornament curling forward at the bottom of the riser, and a red tassel hanging from it
g.add(tube(cr([(0, -0.1, 0.0), (0, -0.118, -0.004), (0, -0.13, -0.016), (0, -0.128, -0.03), (0, -0.116, -0.034)], per=3), 0.0072, 0.0016, n=8), "dragon_gold")
knot = Vector((0, -0.118, 0.022))
g.add(blob_geo(knot, (0.0058, 0.0075, 0.0058), n=8, rings=4), "dragon_cord")
for j in range(8):
    a = 2 * math.pi * j / 8; ca, sa = math.cos(a), math.sin(a)
    g.add(tube([knot + Vector((0.003 * ca, -0.006, 0.003 * sa)), Vector((0.006 * ca, -0.15, 0.022 + 0.006 * sa)),
                Vector((0.009 * ca, -0.19, 0.022 + 0.009 * sa))], 0.0019, 0.0009, n=6), "dragon_cord")
bow = g.build()

# =====================================================================
# dragon_arrow (along Z: nock at +0.40, tip at -0.42)
# =====================================================================
def vane_shape(t):
    s = math.sin(math.pi * (0.15 + 0.7 * t)); rad = 0.0095 * s; b = 0.0013 * s + 0.0003
    return [(rad / 2 + rad / 2 * math.cos(2 * math.pi * k / 8), b * math.sin(2 * math.pi * k / 8)) for k in range(8)]


g = Geo("dragon_arrow")
g.add(tube([(0, 0, -0.34), (0, 0, 0.40)], 0.0045, n=10), "dragon_dark")  # shaft
g.add(tube([(0, 0, 0.372), (0, 0, 0.40)], 0.0034, 0.0026, n=8), "dragon_gold")  # nock
for z in (0.22, 0.02, -0.14):
    g.add(ring_geo((0, 0, z), 0.0047, 0.0009, (0, 0, 1), n=16, m=5), "dragon_gold")
for k in range(3):  # three red-black vanes at 120 degrees
    th = 2 * math.pi * k / 3
    path = [(0.0045 * math.cos(th), 0.0045 * math.sin(th), 0.27 + 0.11 * i / 7) for i in range(8)]
    g.add(sweep(path, vane_shape, up=(math.cos(th), math.sin(th), 0)), "dragon_feather")
# arrowhead: a tiny gold dragon head with two glowing eyes, and a flame glow behind it
g.add(blob_geo((0, 0, -0.355), (0.0085, 0.0075, 0.0095), n=10, rings=6), "dragon_gold")
g.add(sweep([(0, 0.0, -0.35), (0, 0.0, -0.38), (0, 0.0, -0.42)], lambda t: circ(0.0058 - 0.0036 * t, 0.0048 - 0.0033 * t, n=10), up=(1, 0, 0)), "dragon_gold")
g.add(tube([(0, -0.002, -0.36), (0, -0.006, -0.38), (0, -0.012, -0.4)], 0.0026, 0.001, n=6), "dragon_gold")
for s in (-1, 1):
    g.add(blob_geo((s * 0.0055, 0.0038, -0.365), (0.0018, 0.0018, 0.0018), n=6, rings=3), "dragon_fire")
g.add(blob_geo((0, 0, -0.328), (0.0105, 0.0105, 0.0085), n=8, rings=4), "dragon_fire")
arrow = g.build()

# =====================================================================
# dragon_head (eastern dragon head for the summoned dragons; origin at the neck joint, facing -Z, ~1.1 long)
# =====================================================================
def snout_r(t):
    return (0.095 - 0.045 * t, 0.105 - 0.05 * t)


def jaw_mid(z):  # centre line of the open lower jaw (drops ~20 degrees from the hinge)
    return -0.085 + 0.37 * (z + 0.3)


def snout_bottom(z):
    t = (-z - 0.25) / 0.81
    return (0.02 - 0.025 * t) - (0.105 - 0.05 * t)


g = Geo("dragon_head")
snout = [(0.0, 0.02 - 0.025 * t, -0.25 - 0.81 * t) for t in [i / 8 for i in range(9)]]
g.add(sweep(snout, lambda t: circ(*snout_r(t), n=14), up=(1, 0, 0)), "dragon_scale")
g.add(blob_geo((0, -0.005, -1.05), (0.05, 0.055, 0.035), n=12, rings=5), "dragon_scale")  # rounded nose
for s in (-1, 1):
    g.add(blob_geo((s * 0.022, 0.04, -1.0), (0.009, 0.007, 0.009), n=8, rings=4), "dragon_dark")  # nostrils
g.add(blob_geo((0, 0.02, -0.2), (0.14, 0.13, 0.2), n=16, rings=10), "dragon_scale")  # cranium
g.add(sweep(cr([(0, -0.085, -0.3), (0, -0.16, -0.5), (0, -0.27, -0.8)], per=4), lambda t: circ(0.06 - 0.03 * t, 0.04 - 0.018 * t, n=12), up=(1, 0, 0)), "dragon_scale")  # lower jaw, open
g.add(blob_geo((0, -0.115, -0.6), (0.035, 0.04, 0.07), n=10, rings=5), "dragon_fire")  # fire core in the mouth
for z in (-0.45, -0.6, -0.75):  # upper fangs
    for s in (-1, 1):
        x = s * 0.045; top = snout_bottom(z) + 0.004
        g.add(tube([(x, top, z), (x, top - 0.035, z)], 0.0075, 0.0008, n=6), "dragon_horn")
for z in (-0.55, -0.7):  # lower fangs
    for s in (-1, 1):
        x = s * 0.04; top = jaw_mid(z) + 0.03
        g.add(tube([(x, top - 0.004, z), (x, top + 0.03, z)], 0.0068, 0.0008, n=6), "dragon_horn")
for s in (-1, 1):
    g.add(blob_geo((s * 0.105, 0.1, -0.2), (0.02, 0.02, 0.02), n=8, rings=4), "dragon_fire")  # glowing eyes
    g.add(blob_geo((s * 0.1, 0.13, -0.22), (0.055, 0.02, 0.035), n=10, rings=4), "dragon_scale")  # brow ridge
    main = [(s * 0.09, 0.1, -0.12), (s * 0.15, 0.2, -0.05), (s * 0.19, 0.265, 0.05), (s * 0.2, 0.3, 0.2), (s * 0.19, 0.32, 0.3)]
    g.add(tube(cr(main, per=3), 0.02, 0.004, n=8), "dragon_horn")  # antler, sweeping back and up
    g.add(tube(cr([(s * 0.19, 0.265, 0.05), (s * 0.25, 0.28, 0.0), (s * 0.3, 0.3, -0.07)], per=3), 0.011, 0.002, n=6), "dragon_horn")
    g.add(tube(cr([(s * 0.2, 0.3, 0.2), (s * 0.25, 0.345, 0.23), (s * 0.26, 0.38, 0.27)], per=3), 0.01, 0.002, n=6), "dragon_horn")
    w = [(s * 0.055, 0.0, -0.8), (s * 0.12, 0.03, -0.93), (s * 0.19, 0.05, -1.0), (s * 0.25, 0.04, -0.94), (s * 0.3, 0.0, -0.8), (s * 0.31, -0.05, -0.62)]
    g.add(tube(cr(w, per=4), 0.0085, 0.0018, n=6), "dragon_gold")  # long whisker curling back from the snout
for k in range(9):  # flame-like mane spikes around the back of the skull
    a = math.pi * (0.1 + 0.8 * k / 8)
    R3 = Vector((math.cos(a), math.sin(a), 0))
    P0 = Vector((0.118 * math.cos(a), 0.02 + 0.109 * math.sin(a), -0.09))
    path = [P0, P0 + R3 * 0.012 + Vector((0, 0, 0.03)), P0 + R3 * 0.02 + Vector((0, 0, 0.07)), P0 + R3 * 0.01 + Vector((0, 0, 0.1))]
    g.add(sweep(path, lambda t: circ(0.011 * (1 - t) + 0.0015, 0.005 * (1 - t) + 0.0008, n=8), up=(1, 0, 0)),
          "dragon_red" if k % 2 == 0 else "dragon_gold")
head = g.build()

# =====================================================================
# dragon_segment (one body section: z=0 front joint .. z=+0.55 back joint, overlapping ends)
# =====================================================================
g = Geo("dragon_segment")
g.add(sweep([(0, 0, z) for z in (-0.03, 0.1, 0.3, 0.58)], lambda t: circ(0.22 - 0.01 * t, n=14), up=(1, 0, 0)), "dragon_scale")
for row, z in enumerate((0.06, 0.25, 0.44)):  # three rows of overlapping scales, staggered
    for k in range(9):
        th = 2 * math.pi * (k + 0.5 * (row % 2)) / 9
        rho = Vector((math.cos(th), math.sin(th), 0)); tang = Vector((-math.sin(th), math.cos(th), 0))
        g.add(blob_geo(Vector((0, 0, z)) + rho * 0.214, (0.085, 0.022, 0.11), n=6, rings=2, half=True, ax=tang, ay=rho, az=(0, 0, 1)), "dragon_scale")
for s in (-1, 1):  # pale belly plates on the underside
    for z in (0.08, 0.22, 0.36, 0.5):
        g.add(blob_geo((s * 0.06, -0.21, z), (0.06, 0.02, 0.07), n=8, rings=2, half=True, ay=(0, -1, 0)), "dragon_belly")
for k in range(6):  # dorsal crest: red spines with gold edges and tips
    z = 0.04 + k * 0.095
    path = [(0, 0.19, z), (0, 0.25, z - 0.008), (0, 0.31, z - 0.024)]
    g.add(sweep(path, lambda t: circ(0.012 * (1 - t) + 0.0015, 0.035 * (1 - t) ** 0.8 + 0.001, n=6), up=(1, 0, 0)), "dragon_red")
    g.add(blob_geo((0, 0.31, z - 0.024), (0.004, 0.006, 0.008), n=6, rings=3), "dragon_gold")
    g.add(tube([(0, 0.22, z + 0.03), (0, 0.27, z + 0.02), (0, 0.3, z)], 0.0018, 0.0008, n=5), "dragon_gold")
segment = g.build()

# =====================================================================
# dragon_tail (from z=0 at the last segment to z=1.0, ending in a flame fin)
# =====================================================================
def tail_r(t):
    return 0.16 * (1 - t) ** 0.85 + 0.006


def tail_c(t):  # the axis of the tail, with a slight sway
    return Vector((0.016 * math.sin(math.pi * t), -0.01 * t * t, t))


g = Geo("dragon_tail")
g.add(sweep([tail_c(i / 12) for i in range(13)], lambda t: circ(tail_r(t), n=12), up=(1, 0, 0)), "dragon_scale")
for z in (0.2, 0.45, 0.7):  # three rows of scales
    c0 = tail_c(z); r = tail_r(z) - 0.004
    for k in range(8):
        th = 2 * math.pi * (k + 0.5 * (int(z * 10) % 2)) / 8
        rho = Vector((math.cos(th), math.sin(th), 0)); tang = Vector((-math.sin(th), math.cos(th), 0))
        g.add(blob_geo(c0 + rho * r, (0.6 * 2 * math.pi * r / 8, 0.014, 0.13), n=6, rings=2, half=True, ax=tang, ay=rho, az=(0, 0, 1)), "dragon_scale")
for z in (0.15, 0.4, 0.65):  # dorsal crest continuing from the segment
    c0 = tail_c(z); top = tail_r(z)
    path = [c0 + Vector((0, top - 0.01, 0)), c0 + Vector((0, top + 0.03, -0.008)), c0 + Vector((0, top + 0.05, -0.02))]
    g.add(sweep(path, lambda t: circ(0.009 * (1 - t) + 0.0012, 0.028 * (1 - t) ** 0.8 + 0.001, n=6), up=(1, 0, 0)), "dragon_red")
    g.add(blob_geo(path[-1], (0.004, 0.006, 0.007), n=6, rings=3), "dragon_gold")
for path, m in (([(0, 0, 0.96), (0, 0.05, 1.07), (0, 0.1, 1.2)], "dragon_red"),  # flame-shaped tail fin
                ([(0, 0, 0.96), (0, -0.05, 1.06), (0, -0.09, 1.18)], "dragon_red"),
                ([(0, 0, 0.97), (0, 0, 1.12), (0, 0.005, 1.27)], "dragon_fire")):
    g.add(sweep(path, lambda t: circ(0.03 * (1 - t) ** 0.7 + 0.0015, 0.011 * (1 - t) ** 0.7 + 0.0008, n=8), up=(1, 0, 0)), m)
tail = g.build()

# =====================================================================
# dragon_claw (leg hanging from the hip along -Y, about 0.45 long, four talons)
# =====================================================================
g = Geo("dragon_claw")
g.add(blob_geo((0, 0, 0), (0.05, 0.05, 0.05), n=10, rings=6), "dragon_scale")  # hip
g.add(sweep([(0, 0, 0), (0.012, -0.1, 0.0), (0.03, -0.2, 0.0)], lambda t: circ(0.042 - 0.012 * t, 0.036 - 0.008 * t, n=10), up=(1, 0, 0)), "dragon_scale")
g.add(blob_geo((0.03, -0.2, 0), (0.034, 0.034, 0.034), n=10, rings=6), "dragon_scale")  # knee
g.add(sweep([(0.03, -0.2, 0), (0.026, -0.3, 0.012), (0.022, -0.38, 0.02)], lambda t: circ(0.03 - 0.008 * t, n=10), up=(1, 0, 0)), "dragon_scale")
g.add(blob_geo((0.02, -0.4, 0.02), (0.034, 0.024, 0.04), n=10, rings=5), "dragon_scale")  # foot
g.add(sweep([(0.04, -0.2, 0.0), (0.06, -0.19, -0.02), (0.075, -0.2, -0.05)], lambda t: circ(0.011 * (1 - t) + 0.001, n=8), up=(1, 0, 0)), "dragon_fire")  # elbow flame tufts
g.add(sweep([(0.035, -0.21, 0.03), (0.05, -0.19, 0.045), (0.06, -0.205, 0.07)], lambda t: circ(0.009 * (1 - t) + 0.001, n=8), up=(1, 0, 0)), "dragon_fire")
for x in (-0.024, -0.008, 0.008, 0.024):  # four curved talons
    g.add(tube([(x, -0.4, 0.0), (x, -0.44, -0.02), (x, -0.47, -0.05), (x, -0.46, -0.075)], 0.0085, 0.0009, n=6), "dragon_horn")
claw = g.build()

# ---- export
FINAL = [bow, arrow, head, segment, tail, claw]


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


bpy.ops.object.select_all(action="DESELECT")
for o in FINAL:
    o.select_set(True)
bpy.context.view_layer.objects.active = FINAL[0]
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_texcoords=False, export_yup=True)
print("exported", OUT, {o.name: len(o.data.polygons) for o in FINAL})
print("triangles", {o.name: tris(o) for o in FINAL})

# ---- previews (after the export, so these transforms never reach the exported file)
if PREVIEW:
    ENGINE = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    scene.render.engine = ENGINE
    scene.render.resolution_x, scene.render.resolution_y = 1200, 900
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.03, 0.03, 0.04, 1)


    def lights(scale):
        for o in [o for o in scene.objects if o.type == "LIGHT"]:
            bpy.data.objects.remove(o, do_unlink=True)
        for loc, e in (((2.5, 3.0, 4.0), 700), ((-3.0, 2.0, 3.0), 300), ((0.0, 3.0, -3.0), 400)):
            l = bpy.data.lights.new("l", "AREA"); l.energy = e * scale; l.size = 3
            lo = bpy.data.objects.new("l", l); scene.collection.objects.link(lo)
            lo.location = B(*loc)
            lo.rotation_euler = (B(0, 0, 0) - lo.location).to_track_quat("-Z", "Y").to_euler()


    def snap(path, cam, target, lens):
        cd = bpy.data.cameras.new("cam"); cd.lens = lens
        co = bpy.data.objects.new("cam", cd); scene.collection.objects.link(co); scene.camera = co
        co.location = B(*cam)
        co.rotation_euler = (B(*target) - co.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(co, do_unlink=True)


    def pose(ob, pos, axis, ang):
        ob.matrix_world = Matrix.Translation(B(*pos)) @ Matrix.Rotation(ang, 4, B(*axis))


    # layout 1: all six side by side (game +X to the right, viewed from +Z)
    lights(1.0)
    claw2 = bpy.data.objects.new("dragon_claw_copy", claw.data); scene.collection.objects.link(claw2)
    for ob, pos, axis, ang in [(bow, (-2.1, 0, 0), (0, 1, 0), 0.0), (arrow, (-1.5, 0, 0), (1, 0, 0), -math.pi / 2),
                               (head, (-0.1, 0, 0), (0, 1, 0), math.pi / 2), (segment, (0.6, 0, 0), (0, 1, 0), math.pi / 2),
                               (tail, (1.25, 0, 0), (0, 1, 0), math.pi / 2), (claw, (2.9, 0.5, 0), (0, 1, 0), 0.0),
                               (claw2, (3.35, 0.5, 0), (0, 1, 0), 0.0)]:
        pose(ob, pos, axis, ang)
    snap(PREVIEW, (0.6, 0.3, 10.0), (0.6, 0.0, 0.0), 50)

    # layout 2: the whole dragon, chained along a gentle S-curve (yaw), seen from above and in front
    for ob in FINAL + [claw2]:
        ob.hide_render = True
    lights(2.5)
    th = [0.5 * math.sin(2 * math.pi * k / 12) for k in range(12)]
    P = [Vector((0, 0, 0))]; D = []
    for k in range(12):
        d = Vector((math.sin(th[k]), 0, math.cos(th[k]))); D.append(d); P.append(P[-1] + d * 0.55)


    def inst(name, src, pos, yaw):
        o = bpy.data.objects.new(name, src.data); scene.collection.objects.link(o)
        o.matrix_world = Matrix.Translation(B(*pos)) @ Matrix.Rotation(yaw, 4, B(0, 1, 0))
        return o


    inst("dragon_head_p", head, P[0], th[0])
    for k in range(12):
        inst(f"dragon_seg_{k}", segment, P[k], th[k])
    inst("dragon_tail_p", tail, P[12], th[11])
    for k, side in ((4, 1), (7, -1)):
        local_x = Vector((math.cos(th[k]), 0, -math.sin(th[k])))
        hip = P[k] + D[k] * 0.27 + local_x * (side * 0.16) + Vector((0, -0.06, 0))
        inst(f"dragon_claw_{k}", claw, hip, th[k])
    zc = (P[0].z + P[12].z) / 2
    target = (0.0, 0.0, zc)
    cam = Vector(target) + Vector((1.0, 10.0, 4.5)).normalized() * 14
    snap(PREVIEW.replace(".png", "_dragon.png"), tuple(cam), target, 35)
