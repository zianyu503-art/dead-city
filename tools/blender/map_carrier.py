"""Level 12 aircraft carrier map for 死城突圍, built headless with the blender-modeling skill.

Run from the project root:
  blender -b -P tools/blender/map_carrier.py -- assets/models/map_carrier.glb .claude/work/map_carrier.png
Writes the glb and three previews: deck level (the given path), low over the water (_low.png) and
over the deck edge (_edge.png).

Game coordinates (+Y up, +Z toward the bow, metres) become Blender coordinates with G(x, y, z) = (x, -z, y),
so the glTF export lands back on the game axes. Ground_deck is exactly y = 0 with the DECK outline. Walkable
deck details stay at or under y = 0.05 except the island (x 28.8..37.2, z -12.2..28.2; mast platform at
y 25.5 near (33, 7)). Ground_stains is a soft alpha overlay at y = 0.02; markings sit above it.
The hull runs down to y = -20. No sea, sky, aircraft or gameplay objects are built here.
"""

import math
import os
import random
import sys
import time

sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bkit  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "assets/models/map_carrier.glb")
PREVIEW = os.path.abspath(argv[1] if len(argv) > 1 else ".claude/work/map_carrier.png")
PREVIEW_LOW = PREVIEW[:-4] + "_low.png"
PREVIEW_EDGE = PREVIEW[:-4] + "_edge.png"
TEX_DIR = os.path.join(os.path.dirname(PREVIEW), "map_carrier_tex")
RES_W = int(os.environ.get("MAP_RES", "1280"))
SAMPLES = int(os.environ.get("MAP_SAMPLES", "48"))
RENDER = os.environ.get("MAP_RENDER", "1") == "1"
SEED = 77
rng = random.Random(SEED)
nprng = np.random.default_rng(SEED)

DECK = [(-34, -128), (34, -128), (38, -112), (38, 92), (30, 116), (16, 128), (-16, 128), (-30, 116),
        (-40, 92), (-42, 30), (-42, -20), (-38, -112)]
KEY_Y = [0.0, -9.0, -12.0, -14.5, -17.5, -20.0]                 # ring scale keys
KEY_S = [1.0, 0.955, 0.94, 0.92, 0.905, 0.87]                     # flared at the deck, tumbled home below
HULL_Y = [0.0 - 1.5 * i for i in range(9)] + [-12.0, -14.5, -17.5, -20.0]   # ring heights, every 1.5 m
HULL_Y = sorted(set(HULL_Y), reverse=True)
BANDS = []
for _k in range(len(HULL_Y) - 1):
    _mid = (HULL_Y[_k] + HULL_Y[_k + 1]) / 2
    BANDS.append("boot" if -17.5 < _mid < -14.5 else ("antifoul" if _mid <= -17.5 else "hull_paint"))
DENSE = 10                                                        # hull outline points per DECK edge
MARK_Y = 0.035                                                    # markings sit above the stains overlay
STAIN_N = 512
STAIN_X = (-42.0, 38.0)
STAIN_Z = (-128.0, 128.0)

TILE = {}
MAT = {}
OBJS = []
COLL = None


# ---------------------------------------------------------------- coordinates
def G(p):
    """game (x, y, z) -> blender (x, -z, y)"""
    return (p[0], -p[2], p[1])


def Bd(v):
    """game direction or point -> blender vector"""
    return Vector((v[0], -v[2], v[1]))


def inside(x, z, poly=DECK):
    c = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def inside_mask(X, Z):
    c = np.zeros(X.shape, bool)
    n = len(DECK)
    for i in range(n):
        x1, z1 = DECK[i]
        x2, z2 = DECK[(i + 1) % n]
        if z1 == z2:
            continue
        cond = (z1 > Z) != (z2 > Z)
        xint = (x2 - x1) * (Z - z1) / (z2 - z1) + x1
        c ^= cond & (X < xint)
    return c.astype(float)


def hs(y):
    """hull ring scale at height y (piecewise linear between KEY_Y)"""
    for i in range(len(KEY_Y) - 1):
        y0, y1 = KEY_Y[i], KEY_Y[i + 1]
        if y0 >= y >= y1:
            f = (y0 - y) / (y0 - y1)
            return KEY_S[i] * (1 - f) + KEY_S[i + 1] * f
    return KEY_S[-1]


def densify(pts, k):
    out = []
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        for t in range(k):
            f = t / k
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


HULL_PTS = densify(DECK, DENSE)
HULL_C = (sum(x for x, _ in HULL_PTS) / len(HULL_PTS), sum(z for _, z in HULL_PTS) / len(HULL_PTS))


def ring(y):
    s = hs(y)
    return [(x * s, z * s) for x, z in HULL_PTS]


def half_w(z, s):
    """deck half-width on side s (+1 starboard, -1 port) at length z"""
    vals = []
    n = len(DECK)
    for i in range(n):
        (xa, za), (xb, zb) = DECK[i], DECK[(i + 1) % n]
        if za == zb or not (min(za, zb) <= z <= max(za, zb)):
            continue
        x = xa + (z - za) * (xb - xa) / (zb - za)
        if x * s > 0:
            vals.append(abs(x))
    return max(vals) if vals else 0.0


def hull_x(s, y, z):
    """hull side surface x (signed by s) at height y and length z"""
    return s * half_w(z, s) * hs(y)


# ---------------------------------------------------------------- mesh builder
class Mesh:
    """Polygons in game coordinates -> one Blender object. Per-polygon material and world-scale UVs."""

    def __init__(self, name):
        self.name = name
        self.keys = {}
        self.verts = []
        self.faces = []

    def _vi(self, p):
        k = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
        i = self.keys.get(k)
        if i is None:
            i = len(self.verts)
            self.keys[k] = i
            self.verts.append(k)
        return i

    def poly(self, pts, mat, n=None):
        pts = [tuple(float(c) for c in p) for p in pts]
        clean = []
        for p in pts:
            if not clean or max(abs(p[k] - clean[-1][k]) for k in range(3)) > 1e-5:
                clean.append(p)
        while len(clean) > 1 and max(abs(clean[0][k] - clean[-1][k]) for k in range(3)) <= 1e-5:
            clean.pop()
        if len(clean) < 3:
            return
        nx = ny = nz = 0.0
        m = len(clean)
        for k in range(m):
            a = clean[k]
            b = clean[(k + 1) % m]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-10:
            return
        nn = (nx / ln, ny / ln, nz / ln)
        if n is not None:
            nl = math.sqrt(sum(c * c for c in n)) or 1.0
            n = tuple(c / nl for c in n)
            if sum(nn[k] * n[k] for k in range(3)) < 0:
                clean.reverse()
                nn = tuple(-c for c in nn)
        ax = max(range(3), key=lambda q: abs(nn[q]))
        ua, va = (0, 2) if ax == 1 else ((2, 1) if ax == 0 else (0, 1))
        tile = TILE.get(mat, 2.0)
        uv = [(p[ua] / tile, p[va] / tile) for p in clean]
        self.faces.append(([self._vi(p) for p in clean], mat, uv))

    def build(self):
        if not self.faces:
            return None
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([G(v) for v in self.verts], [], [f[0] for f in self.faces])
        me.update()
        slots = {}
        for _, mat, _ in self.faces:
            if mat not in slots:
                slots[mat] = len(me.materials)
                me.materials.append(MAT[mat])
        uvl = me.uv_layers.new(name="UVMap")
        for pi, poly in enumerate(me.polygons):
            _, mat, uv = self.faces[pi]
            poly.material_index = slots[mat]
            for k in range(len(poly.vertices)):
                uvl.data[poly.loop_start + k].uv = uv[k]
        obj = bpy.data.objects.new(self.name, me)
        COLL.objects.link(obj)
        OBJS.append(obj)
        return obj


# ---------------------------------------------------------------- primitives (game coords)
def box(mb, c, h, mat):
    x, y, z = c
    hx, hy, hz = h

    def p(a, b, d):
        return (x + a * hx, y + b * hy, z + d * hz)
    mb.poly([p(1, -1, -1), p(1, 1, -1), p(1, 1, 1), p(1, -1, 1)], mat, (1, 0, 0))
    mb.poly([p(-1, -1, 1), p(-1, 1, 1), p(-1, 1, -1), p(-1, -1, -1)], mat, (-1, 0, 0))
    mb.poly([p(-1, 1, -1), p(-1, 1, 1), p(1, 1, 1), p(1, 1, -1)], mat, (0, 1, 0))
    mb.poly([p(-1, -1, -1), p(1, -1, -1), p(1, -1, 1), p(-1, -1, 1)], mat, (0, -1, 0))
    mb.poly([p(-1, -1, 1), p(1, -1, 1), p(1, 1, 1), p(-1, 1, 1)], mat, (0, 0, 1))
    mb.poly([p(1, -1, -1), p(-1, -1, -1), p(-1, 1, -1), p(1, 1, -1)], mat, (0, 0, -1))


def cyl(mb, a, b, r, mat, seg=10):
    a = Vector(a)
    b = Vector(b)
    dn = (b - a).normalized()
    t1 = dn.orthogonal()
    t2 = dn.cross(t1)
    mid = (a + b) / 2

    def ring_at(c):
        return [c + (t1 * math.cos(2 * math.pi * k / seg) + t2 * math.sin(2 * math.pi * k / seg)) * r
                for k in range(seg)]
    A = ring_at(a)
    Bq = ring_at(b)
    for k in range(seg):
        k2 = (k + 1) % seg
        cen = (A[k] + A[k2] + Bq[k2] + Bq[k]) / 4
        mb.poly([A[k], A[k2], Bq[k2], Bq[k]], mat, tuple(cen - mid))
    mb.poly(A, mat, tuple(-dn))
    mb.poly(Bq, mat, tuple(dn))


def disc(mb, c, r, normal, mat, seg=10):
    n = Vector(normal).normalized()
    t1 = n.orthogonal()
    t2 = n.cross(t1)
    c = Vector(c)
    pts = [c + (t1 * math.cos(2 * math.pi * k / seg) + t2 * math.sin(2 * math.pi * k / seg)) * r
           for k in range(seg)]
    mb.poly(pts, mat, tuple(n))


def sphere(mb, c, r, mat, seg=10, rings=5):
    c = Vector(c)
    P = []
    for i in range(rings + 1):
        th = math.pi * i / rings
        P.append([c + Vector((math.sin(th) * math.cos(2 * math.pi * k / seg), math.cos(th),
                              math.sin(th) * math.sin(2 * math.pi * k / seg))) * r for k in range(seg)])
    for i in range(rings):
        for k in range(seg):
            k2 = (k + 1) % seg
            q = [P[i][k], P[i + 1][k], P[i + 1][k2], P[i][k2]]
            mb.poly(q, mat, tuple(sum(q, Vector()) / 4 - c))


def extrude(mb, pts, axis, d0, d1, mat):
    """Closed 2D outline (u, v) pushed from depth d0 to d1 along axis.
    axis 'y': (u, v) = (x, z); axis 'z': (x, y); axis 'x': (z, y)."""
    def P3(p, d):
        if axis == "y":
            return (p[0], d, p[1])
        if axis == "z":
            return (p[0], p[1], d)
        return (d, p[1], p[0])

    def N3(e):
        if axis == "y":
            return (e[0], 0.0, e[1])
        if axis == "z":
            return (e[0], e[1], 0.0)
        return (0.0, e[1], e[0])
    m = len(pts)
    cu = sum(p[0] for p in pts) / m
    cv = sum(p[1] for p in pts) / m
    for k in range(m):
        a = pts[k]
        b = pts[(k + 1) % m]
        q = [P3(a, d0), P3(b, d0), P3(b, d1), P3(a, d1)]
        mb.poly(q, mat, N3(((a[0] + b[0]) / 2 - cu, (a[1] + b[1]) / 2 - cv)))
    up = {"y": (0, 1, 0), "z": (0, 0, 1), "x": (1, 0, 0)}[axis]
    mb.poly([P3(p, d1) for p in pts], mat, up)
    mb.poly([P3(p, d0) for p in pts], mat, tuple(-c for c in up))


def beam_xz(mb, a, b, w, y0, y1, mat):
    """horizontal bar from a to b (x, z) with width w, between heights y0 and y1"""
    dx, dz = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dz) or 1.0
    px, pz = -dz / L * w / 2, dx / L * w / 2
    pts = [(a[0] + px, a[1] + pz), (b[0] + px, b[1] + pz), (b[0] - px, b[1] - pz), (a[0] - px, a[1] - pz)]
    extrude(mb, pts, "y", y0, y1, mat)


def loft(mb, bot, top, mat):
    """quad-sided solid between two 4-point rectangles (same order)"""
    m = len(bot)
    allp = bot + top
    cen = [sum(p[c] for p in allp) / len(allp) for c in range(3)]
    for k in range(m):
        k2 = (k + 1) % m
        q = [bot[k], bot[k2], top[k2], top[k]]
        mid = tuple(sum(p[c] for p in q) / 4 - cen[c] for c in range(3))
        mb.poly(q, mat, mid)
    mb.poly(bot, mat, (0, -1, 0))
    mb.poly(top, mat, (0, 1, 0))


def side_out(P00, P10, center):
    """horizontal outward normal of the wall running from P00 to P10"""
    dx = P10[0] - P00[0]
    dz = P10[2] - P00[2]
    L = math.hypot(dx, dz) or 1.0
    n = (dz / L, 0.0, -dx / L)
    mid = ((P00[0] + P10[0]) / 2 - center[0], 0.0, (P00[2] + P10[2]) / 2 - center[2])
    if n[0] * mid[0] + n[2] * mid[2] < 0:
        n = (-n[0], 0.0, -n[2])
    return n


def quad_grid(mb, P00, P10, P01, P11, nc, nr, mat, out, off=0.05, frame=None, fr=0.13):
    """bilinear grid of glass cells on a quad; optional frame plate behind each cell"""
    def pt(u, v):
        return tuple((1 - v) * ((1 - u) * P00[c] + u * P10[c]) + v * ((1 - u) * P01[c] + u * P11[c])
                     for c in range(3))

    def shift(q, d):
        return [tuple(p[c] + out[c] * d for c in range(3)) for p in q]
    for i in range(nc):
        for j in range(nr):
            if frame:
                full = [pt(i / nc, j / nr), pt((i + 1) / nc, j / nr), pt((i + 1) / nc, (j + 1) / nr),
                        pt(i / nc, (j + 1) / nr)]
                mb.poly(shift(full, off * 0.5), frame, out)
            ua, ub = (i + fr) / nc, (i + 1 - fr) / nc
            va, vb = (j + fr) / nr, (j + 1 - fr) / nr
            q = [pt(ua, va), pt(ub, va), pt(ub, vb), pt(ua, vb)]
            mb.poly(shift(q, off), mat, out)


def seams(mb, x0, x1, z0, z1, y0, y1, mat, step=2.5):
    """thin panel seams standing proud of the walls of a box"""
    h = (y1 - y0) / 2
    yc = (y0 + y1) / 2
    for zc in np.arange(z0 + step, z1, step):
        for xf in (x0, x1):
            box(mb, (xf, yc, float(zc)), (0.03, h, 0.04), mat)
    for xc in np.arange(x0 + step, x1, step):
        for zf in (z0, z1):
            box(mb, (float(xc), yc, zf), (0.04, h, 0.03), mat)


def band_windows(mb, x0, x1, z0, z1, by0, by1, nx, nz, glass, frame):
    c = ((x0 + x1) / 2, (by0 + by1) / 2, (z0 + z1) / 2)
    for xf in (x0, x1):
        P00, P10 = (xf, by0, z0), (xf, by0, z1)
        P01, P11 = (xf, by1, z0), (xf, by1, z1)
        quad_grid(mb, P00, P10, P01, P11, nz, 1, glass, side_out(P00, P10, c), frame=frame)
    for zf in (z0, z1):
        P00, P10 = (x0, by0, zf), (x1, by0, zf)
        P01, P11 = (x0, by1, zf), (x1, by1, zf)
        quad_grid(mb, P00, P10, P01, P11, nx, 1, glass, side_out(P00, P10, c), frame=frame)


def rail_run(mb, pts2d, y_list, r, mat, post_every, post_mat, post_h=0.45, post_y0=None):
    """continuous rail through (x, z) points at heights y_list, with posts every few points"""
    n = len(pts2d)
    for i in range(n - 1):
        for y in y_list:
            cyl(mb, (pts2d[i][0], y, pts2d[i][1]), (pts2d[i + 1][0], y, pts2d[i + 1][1]), r, mat, 8)
    for i in range(0, n, post_every):
        y0 = post_y0 if post_y0 is not None else min(y_list) - 0.05
        box(mb, (pts2d[i][0], y0 + post_h / 2, pts2d[i][1]), (0.05, post_h / 2, 0.05), post_mat)


def line_pts(a, b, step):
    """points every `step` metres along the segment a -> b (inclusive of both ends)"""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    k = max(1, int(round(L / step)))
    return [(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k) for i in range(k + 1)]


def text_obj(s, c, size, mat, reading, normal, name):
    """flat extruded lettering at game point c, reading along `reading`, facing `normal`"""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = 0.02
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new(name, cu)
    COLL.objects.link(ob)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.object
    rv = Vector(reading).normalized()
    nv = Vector(normal).normalized()
    up = nv.cross(rv)
    R = Matrix((Bd(rv), Bd(up), Bd(nv))).transposed().to_4x4()
    ob.matrix_world = Matrix.Translation(Bd(c)) @ R
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.name = name
    ob.data.name = name
    ob.data.materials.clear()
    ob.data.materials.append(MAT[mat])
    OBJS.append(ob)
    return ob


# ---------------------------------------------------------------- materials
PH = {
    # key: (Poly Haven id, world-metres per texture repeat, tint)
    "deck": ("tarred_gravel", 3.0, (0.72, 0.72, 0.75)),  # the storm light is dim: a darker tint goes black in the game
}
PH_FALLBACK = {"deck": (0.10, 0.10, 0.11)}

CONST = {
    # name: (rgb, roughness, metallic, emission strength)
    "hull_paint": ((0.36, 0.38, 0.40), 0.5, 0.3, 0),
    "boot": ((0.45, 0.04, 0.03), 0.6, 0.1, 0),
    "antifoul": ((0.05, 0.05, 0.06), 0.8, 0.0, 0),
    "paint": ((0.33, 0.35, 0.37), 0.5, 0.1, 0),
    "paint_dark": ((0.20, 0.21, 0.22), 0.6, 0.2, 0),
    "glass": ((0.03, 0.05, 0.07), 0.05, 0.0, 0),
    "rust": ((0.13, 0.095, 0.075), 0.9, 0.0, 0),
    "soot": ((0.04, 0.04, 0.04), 0.9, 0.0, 0),
    "dark": ((0.02, 0.02, 0.025), 0.8, 0.0, 0),
    "door": ((0.09, 0.10, 0.11), 0.6, 0.2, 0),
    "hangar": ((0.02, 0.025, 0.03), 0.9, 0.0, 0),
    "hangar_lit": ((1.0, 0.72, 0.38), 0.6, 0.0, 2.5),
    "lamp_red": ((1.0, 0.10, 0.05), 0.3, 0.0, 4.0),
    "lamp_white": ((1.0, 0.97, 0.85), 0.3, 0.0, 6.0),
    "porthole": ((0.02, 0.03, 0.04), 0.1, 0.3, 0),
    "track": ((0.25, 0.26, 0.27), 0.4, 0.8, 0),
    "yellow": ((0.80, 0.60, 0.08), 0.7, 0.0, 0),
    "white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0),
    "tie": ((0.06, 0.06, 0.065), 0.7, 0.2, 0),
    "pipe": ((0.36, 0.30, 0.22), 0.6, 0.6, 0),
    "raft": ((0.80, 0.40, 0.10), 0.7, 0.0, 0),
}


def cmat(name, rgb, rough, metal, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1.0)
        b.inputs["Emission Strength"].default_value = emit
    return m


def load_materials():
    bkit.CACHE = TEX_DIR
    for key, (aid, tile, tint) in PH.items():
        try:
            maps = bkit.polyhaven_texture(aid, res="1k")
            maps = {k: v for k, v in maps.items() if k in ("color", "normal", "roughness")}
            MAT[key] = bkit.pbr_material(key, maps, scale=1.0, tint=tint, coords="UV")
            print("CARRIER texture", key, aid)
        except Exception as e:  # offline: flat-ish fallback, reported
            print("CARRIER texture fallback", key, e)
            MAT[key] = cmat(key, PH_FALLBACK[key], 0.6, 0.3)
        TILE[key] = tile
    for name, (rgb, rough, metal, emit) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, emit)
        TILE[name] = 1.0


# ---------------------------------------------------------------- deck
def build_deck():
    deck = Mesh("Ground_deck")
    deck.poly([(x, 0.0, z) for x, z in DECK], "deck", (0, 1, 0))

    marks = Mesh("Ground_deck_marks")
    y = MARK_Y
    for z in range(-120, 120, 8):                       # centre line
        strip(marks, (0, z), (0, z + 4), 0.5, y, "white")
    ang = math.radians(9)                               # angled landing area, 9 degrees
    d = (-math.sin(ang), math.cos(ang))
    for x0 in (-17.0, 5.0):
        strip(marks, (x0, -126), (x0 + d[0] * 140, -126 + d[1] * 140), 0.35, y, "yellow")
    for k in range(0, 130, 8):
        a = (-6 + d[0] * k, -126 + d[1] * k)
        strip(marks, a, (a[0] + d[0] * 4, a[1] + d[1] * 4), 0.4, y, "white")
    for x in (-8, 8):                                   # bow catapults
        strip(marks, (x, 45), (x, 125), 1.2, y + 0.005, "track")
        for z in (48, 122):
            strip(marks, (x - 1.2, z), (x + 1.2, z), 0.5, y + 0.005, "yellow")
    for z in (-100, -94, -88, -82):                     # arresting wires, flush
        strip(marks, (-26, z), (18, z), 0.12, y + 0.005, "metal")
    for cx, cz in ((-22, 30), (22, -40)):               # elevator outlines
        hx, hz = 5.0, 7.0
        corners = [(cx - hx, cz - hz), (cx + hx, cz - hz), (cx + hx, cz + hz), (cx - hx, cz + hz)]
        for i in range(4):
            strip(marks, corners[i], corners[(i + 1) % 4], 0.3, y, "yellow")
    placed = 0
    while placed < 40:                                  # tie-down rings
        x, z = rng.uniform(-36, 36), rng.uniform(-120, 120)
        if 27 < x < 39 and -15 < z < 31:
            continue
        if all(inside(x + dx, z + dz) for dx, dz in ((0, 0), (2, 0), (-2, 0), (0, 2), (0, -2))):
            disc(marks, (x, y + 0.001, z), 0.18, (0, 1, 0), "tie", 8)
            placed += 1
    text_obj("77", (-20, y + 0.005, 60), 12, "white", (-1, 0, 0), (0, 1, 0), "deck_77")
    return [deck, marks]


def strip(mb, p0, p1, w, y, mat):
    """flat band on the deck plane between two (x, z) points"""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dz) or 1.0
    px, pz = -dz / L * w / 2, dx / L * w / 2
    pts = [(p0[0] + px, y, p0[1] + pz), (p1[0] + px, y, p1[1] + pz),
           (p1[0] - px, y, p1[1] - pz), (p0[0] - px, y, p0[1] - pz)]
    mb.poly(pts, mat, (0, 1, 0))


# ---------------------------------------------------------------- soft stains overlay (Ground_stains)
def vnoise(n):
    """smooth value noise on the stain grid, n cells across"""
    g = nprng.random((n + 1, n + 1))
    xs = np.arange(STAIN_N) / STAIN_N * n
    X, Y = np.meshgrid(xs, xs)
    i = np.floor(X).astype(int)
    j = np.floor(Y).astype(int)
    fx = X - i
    fy = Y - j
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = g[j, i]
    b = g[j, i + 1]
    c = g[j + 1, i]
    d = g[j + 1, i + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def smooth_band(f, lo, hi):
    t = np.clip((f - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def seg_dist(X, Z, a, b):
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz or 1.0
    t = np.clip(((X - ax) * dx + (Z - az) * dz) / L2, 0, 1)
    return np.hypot(X - (ax + t * dx), Z - (az + t * dz))


def make_stain_array():
    N = STAIN_N
    colx = STAIN_X[0] + (np.arange(N) + 0.5) / N * (STAIN_X[1] - STAIN_X[0])
    rowz = STAIN_Z[0] + (np.arange(N) + 0.5) / N * (STAIN_Z[1] - STAIN_Z[0])
    X, Z = np.meshgrid(colx, rowz)
    mask = inside_mask(X, Z)
    f1 = 0.5 * vnoise(4) + 0.3 * vnoise(9) + 0.2 * vnoise(22)
    f1n = np.percentile(f1, 84)
    oil = smooth_band(f1, f1n - 0.05, f1n + 0.05)                    # soft oil patches, ~16% cover
    f2 = 0.5 * vnoise(6) + 0.5 * vnoise(18)
    worn = smooth_band(f2, np.percentile(f2, 80), np.percentile(f2, 92)) * 0.55
    tyre = np.zeros((N, N))
    ang = math.radians(9)
    d = (-math.sin(ang), math.cos(ang))
    for _ in range(12):                                             # tyre streaks through the landing area
        x0 = nprng.uniform(-16, 4)
        L = nprng.uniform(70, 140)
        a = (x0, -126.0)
        b = (x0 + d[0] * L, -126.0 + d[1] * L)
        w = nprng.uniform(0.5, 1.0)
        tyre = np.maximum(tyre, np.exp(-(seg_dist(X, Z, a, b) / w) ** 2) * nprng.uniform(0.4, 0.7))
    tyre *= 0.6 + 0.4 * vnoise(40)
    cat = np.zeros((N, N))                                          # darker around the catapults
    for x in (-8.0, 8.0):
        cat = np.maximum(cat, np.exp(-(seg_dist(X, Z, (x, 40.0), (x, 128.0)) / 3.2) ** 2) * 0.45)
    dark = np.clip(oil * 0.8 + tyre * 0.7 + cat, 0, 1)
    alpha = np.clip(np.maximum(dark, worn), 0, 1) * mask
    wd = dark / np.maximum(dark + worn, 1e-6)
    dark_rgb = np.array([0.012, 0.012, 0.014])
    light_rgb = np.array([0.24, 0.23, 0.22])
    rgb = dark_rgb[None, None, :] * wd[..., None] + light_rgb[None, None, :] * (1 - wd)[..., None]
    return np.concatenate([rgb, alpha[..., None]], axis=2).astype(np.float32)


def build_stains():
    arr = make_stain_array()
    os.makedirs(TEX_DIR, exist_ok=True)
    img = bpy.data.images.new("ground_stains", STAIN_N, STAIN_N, alpha=True)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = os.path.join(TEX_DIR, "ground_stains.png")
    img.file_format = "PNG"
    img.save()
    img = bpy.data.images.load(img.filepath_raw, check_existing=False)
    m = bpy.data.materials.new("Ground_stains")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.9
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception as e:
            print("CARRIER stains", attr, e)
    corners = [(-42, -128), (-42, 128), (38, 128), (38, -128)]
    uvs = [(0, 0), (0, 1), (1, 1), (1, 0)]
    me = bpy.data.meshes.new("Ground_stains")
    me.from_pydata([G((x, 0.02, z)) for x, z in corners], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for li, uv in enumerate(uvs):
        uvl.data[li].uv = uv
    me.materials.append(m)
    ob = bpy.data.objects.new("Ground_stains", me)
    COLL.objects.link(ob)
    OBJS.append(ob)


# ---------------------------------------------------------------- hull
def build_hull():
    hull = Mesh("Hull")
    for k in range(len(HULL_Y) - 1):
        A = [(x, HULL_Y[k], z) for x, z in ring(HULL_Y[k])]
        Bp = [(x, HULL_Y[k + 1], z) for x, z in ring(HULL_Y[k + 1])]
        m = len(A)
        for i in range(m):
            j = (i + 1) % m
            mx = (A[i][0] + A[j][0]) / 2
            mz = (A[i][2] + A[j][2]) / 2
            hull.poly([A[i], A[j], Bp[j], Bp[i]], BANDS[k], (mx, 0.0, mz))
    hull.poly([(x, HULL_Y[-1], z) for x, z in ring(HULL_Y[-1])], "antifoul", (0, -1, 0))
    text_obj("77", (0, -4.0, 125.9), 6, "white", (1, 0, 0), (0, 0, 1), "bow_77")
    return hull


def build_details():
    det = Mesh("Hull_details")
    # sponsons: solid cross-section merged into the hull, sloped undersides
    for s in (-1, 1):
        pts = [(s * 36.0, -1.6), (s * 45.5, -2.2), (s * 46.5, -2.8), (s * 44.0, -4.6), (s * 41.0, -8.2),
               (s * 36.0, -8.2)]
        extrude(det, pts, "z", -84.0, 44.0, "hull_paint")
        for z in range(-84, 45, 4):                                  # ribs under the sponson
            box(det, (s * 42.0, -6.8, z + 0.5), (1.0, 1.4, 0.12), "paint_dark")
        for z in range(-80, 45, 12):                                 # bracing under the sponson
            cyl(det, (s * 37.5, -8.0, z), (s * 44.0, -4.6, z), 0.3, "paint_dark", 8)
            cyl(det, (s * 41.0, -8.2, z), (s * 44.0, -4.6, z), 0.22, "paint_dark", 6)
    # continuous catwalk and rails 5 m out from the hull, all the way round the ship
    s_c = hs(-2.6)
    O = []
    for x, z in HULL_PTS:
        qx, qz = x * s_c, z * s_c
        dx, dz = qx - HULL_C[0] * s_c, qz - HULL_C[1] * s_c
        L = math.hypot(dx, dz) or 1.0
        O.append((qx + dx / L * 5.0, qz + dz / L * 5.0))
    n = len(O)
    for i in range(n):
        beam_xz(det, O[i], O[(i + 1) % n], 1.6, -2.7, -2.3, "paint_dark")
    rail_run(det, O + [O[0]], (-1.4, -1.9), 0.05, "metal", 3, "metal", post_h=0.5, post_y0=-2.3)
    for i in range(0, n, 4):                                         # struts from hull to catwalk
        hx, hz = HULL_PTS[i][0] * hs(-3.0), HULL_PTS[i][1] * hs(-3.0)
        cyl(det, (hx, -3.0, hz), (O[i][0], -2.5, O[i][1]), 0.18, "paint_dark", 6)
    for s in (-1, 1):                                                # gun tubs with CIWS mounts
        for z in (-70, -10, 30):
            box(det, (s * 45.0, -1.9, z), (1.4, 0.4, 1.4), "dark")
            cyl(det, (s * 45.0, -1.5, z), (s * 45.0, -0.4, z), 0.32, "metal", 10)
            sphere(det, (s * 45.0, -0.4, z), 0.55, "paint", 10, 5)
        for z in (-60.0, -40.0, 14.0):                               # lifeboat canisters
            cyl(det, (s * 41.4, -7.0, z - 2.2), (s * 41.4, -7.0, z + 2.2), 0.8, "raft", 12)
        # hangar bay openings: dark frame and a lit interior set just inside
        for z0, z1 in ((-108.0, -92.0), (76.0, 92.0)):
            det.poly([(hull_x(s, -2.0, z0) + s * 0.10, -2.0, z0), (hull_x(s, -2.0, z1) + s * 0.10, -2.0, z1),
                      (hull_x(s, -9.0, z1) + s * 0.10, -9.0, z1), (hull_x(s, -9.0, z0) + s * 0.10, -9.0, z0)],
                     "hangar", (s, 0, 0))
            za, zb = z0 + 1.5, z1 - 1.5
            det.poly([(hull_x(s, -2.8, za) + s * 0.16, -2.8, za), (hull_x(s, -2.8, zb) + s * 0.16, -2.8, zb),
                      (hull_x(s, -8.2, zb) + s * 0.16, -8.2, zb), (hull_x(s, -8.2, za) + s * 0.16, -8.2, za)],
                     "hangar_lit", (s, 0, 0))
        for y in (-10.5, -12.2):                                     # rows of portholes
            for z in range(-108, 110, 4):
                disc(det, (hull_x(s, y, z) + s * 0.06, y, z), 0.25, (s, 0, 0), "porthole", 8)
        for z in range(-112, 112, 6):                                # rust streaks from the scuppers
            zz = z + rng.uniform(-2, 2)
            y2 = -rng.uniform(3.0, 12.0)
            w = rng.uniform(0.08, 0.26)
            det.poly([(hull_x(s, -0.3, zz - w) + s * 0.05, -0.3, zz - w),
                      (hull_x(s, -0.3, zz + w) + s * 0.05, -0.3, zz + w),
                      (hull_x(s, y2, zz + w) + s * 0.05, y2, zz + w),
                      (hull_x(s, y2, zz - w) + s * 0.05, y2, zz - w)], "rust", (s, 0, 0))
    # hull ribs, stringers along the outline and rivets along the stringers
    for s in (-1, 1):
        for z in range(-112, 112, 4):
            box(det, (hull_x(s, -6.5, z) + s * 0.12, -6.5, z), (0.12, 6.0, 0.12), "paint_dark")
    for yl in (-1.5, -4.5, -7.5, -10.5, -13.5):
        ol = []
        for x, z in HULL_PTS:
            sc = hs(yl)
            qx, qz = x * sc, z * sc
            dx, dz = qx - HULL_C[0] * sc, qz - HULL_C[1] * sc
            L = math.hypot(dx, dz) or 1.0
            ol.append((qx + dx / L * 0.15, qz + dz / L * 0.15, dx / L, dz / L))
        m = len(ol)
        for i in range(m):
            a, b = ol[i], ol[(i + 1) % m]
            beam_xz(det, (a[0], a[1]), (b[0], b[1]), 0.22, yl - 0.07, yl + 0.07, "paint_dark")
            if i % 2 == 0:
                disc(det, (a[0] + a[2] * 0.08, yl, a[1] + a[3] * 0.08), 0.06, (a[2], 0, a[3]), "metal", 6)
    for s in (-1, 1):                                                # anchors in hawse pipes on the bow
        x0 = s * 9.0
        cyl(det, (x0, -3.5, 117.0), (x0, -3.5, 129.0), 0.6, "metal", 12)
        cyl(det, (x0, -3.5, 129.0), (x0, -9.0, 129.0), 0.25, "metal", 8)
        cyl(det, (x0 - 1.5, -9.4, 129.0), (x0 + 1.5, -9.4, 129.0), 0.2, "metal", 8)
        det.poly([(x0, -9.0, 129.0), (x0 + 1.2, -10.6, 129.0), (x0, -11.4, 129.0), (x0 - 1.2, -10.6, 129.0)],
                 "metal", (0, 0, 1))
    return det


# ---------------------------------------------------------------- island (x 28.8..37.2, z -12.2..28.2)
def build_island():
    isl = Mesh("Island")
    P = "paint"
    box(isl, (33, 4.0, 8.0), (3.6, 4.0, 19.6), P)                   # level A, 0..8
    box(isl, (33, 12.0, 8.0), (3.0, 4.0, 15.0), P)                  # level B, 8..16
    band_windows(isl, 29.4, 36.6, -11.6, 27.6, 5.0, 6.6, 9, 9, "glass", "paint_dark")
    band_windows(isl, 30.0, 36.0, -7.0, 23.0, 10.0, 14.0, 8, 8, "glass", "paint_dark")
    quad_grid(isl, (36.6, 0.0, 4.0), (36.6, 0.0, 5.6), (36.6, 2.4, 4.0), (36.6, 2.4, 5.6), 1, 1, "door",
              (1, 0, 0), off=0.03)                                  # doors at the ground
    quad_grid(isl, (31.0, 0.0, -11.6), (32.6, 0.0, -11.6), (31.0, 2.4, -11.6), (32.6, 2.4, -11.6), 1, 1, "door",
              (0, 0, -1), off=0.03)
    # bridge: slanted outward toward the top, with wraparound windows on all four sides
    bot = [(30.6, 16.0, -3.0), (35.4, 16.0, -3.0), (35.4, 16.0, 19.0), (30.6, 16.0, 19.0)]
    top = [(30.0, 22.0, -3.6), (36.0, 22.0, -3.6), (36.0, 22.0, 19.6), (30.0, 22.0, 19.6)]
    loft(isl, bot, top, P)
    cc = (33.0, 19.0, 8.0)
    for i, nc in zip(range(4), (4, 5, 4, 5)):
        P00, P10 = bot[i], bot[(i + 1) % 4]
        P01, P11 = top[i], top[(i + 1) % 4]
        quad_grid(isl, P00, P10, P01, P11, nc, 2, "glass", side_out(P00, P10, cc), frame="paint_dark")
    # protruding flight control bay with a slanted glass front
    bay_bot = [(31.2, 18.0, 18.5), (34.8, 18.0, 18.5), (34.8, 18.0, 25.0), (31.2, 18.0, 25.0)]
    bay_top = [(31.0, 23.0, 19.0), (35.0, 23.0, 19.0), (35.0, 23.0, 25.5), (31.0, 23.0, 25.5)]
    loft(isl, bay_bot, bay_top, P)
    quad_grid(isl, bay_bot[2], bay_bot[3], bay_top[2], bay_top[3], 3, 1, "glass", (0, 0, 1), frame="paint_dark")
    # flight control box and mast platform
    box(isl, (33, 23.25, 5.0), (1.8, 1.25, 6.0), P)
    quad_grid(isl, (31.2, 22.6, 11.0), (34.8, 22.6, 11.0), (31.2, 24.0, 11.0), (34.8, 24.0, 11.0), 3, 1,
              "glass", (0, 0, 1), frame="paint_dark")
    box(isl, (33, 25.0, 7.0), (2.5, 0.5, 2.5), P)                   # mast platform top y 25.5
    for xp, zp in ((30.6, 4.6), (35.4, 4.6), (30.6, 9.4), (35.4, 9.4)):
        box(isl, (xp, 26.0, zp), (0.06, 0.5, 0.06), "metal")
    rail_run(isl, [(30.5, 4.5), (35.5, 4.5), (35.5, 9.5), (30.5, 9.5), (30.5, 4.5)], (26.3,), 0.04, "metal", 1,
             "metal", post_h=0.8, post_y0=25.5)
    # lattice mast above the radar with crossbars and braces
    lo, hi = 27.5, 36.0
    corners = [(33 - 0.6, 7 - 0.6), (33 + 0.6, 7 - 0.6), (33 + 0.6, 7 + 0.6), (33 - 0.6, 7 + 0.6)]
    for x, z in corners:
        cyl(isl, (x, lo, z), (x, hi, z), 0.07, "metal", 6)
    for y in (28.5, 31.0, 33.5):
        for i in range(4):
            cyl(isl, (corners[i][0], y, corners[i][1]), (corners[(i + 1) % 4][0], y, corners[(i + 1) % 4][1]),
                0.05, "metal", 6)
    for y0, y1 in ((lo, 28.5), (28.5, 31.0), (31.0, 33.5), (33.5, hi)):
        for i in range(4):
            cyl(isl, (corners[i][0], y0, corners[i][1]), (corners[(i + 1) % 4][0], y1, corners[(i + 1) % 4][1]),
                0.035, "metal", 6)
    sphere(isl, (33, 36.3, 7), 0.2, "lamp_red", 6, 3)
    for ax, az in ((31.8, 1.5), (34.2, 1.5)):                        # antennas on the flight control roof
        cyl(isl, (ax, 24.5, az), (ax, 28.5, az), 0.04, "metal", 6)
    for ax, az in ((30.4, -2.0), (35.6, 17.0)):                      # antennas on the bridge
        cyl(isl, (ax, 22.0, az), (ax, 26.0, az), 0.05, "metal", 6)
    # searchlights on the bridge front corners
    for sx in (31.0, 35.0):
        cyl(isl, (sx, 20.5, 19.4), (sx, 20.5, 20.7), 0.45, "metal", 12)
        disc(isl, (sx, 20.5, 20.75), 0.36, (0, 0, 1), "lamp_white", 12)
    # soot-darkened exhaust stack with soot streaks
    cyl(isl, (33, 16.0, -5.0), (33, 21.5, -5.0), 0.5, "paint_dark", 12)
    disc(isl, (33, 21.52, -5.0), 0.5, (0, 1, 0), "soot", 12)
    for k in range(6):
        th = k * math.pi / 3 + 0.3
        q = [(33 + 0.51 * math.cos(th - 0.12), 21.4, -5 + 0.51 * math.sin(th - 0.12)),
             (33 + 0.51 * math.cos(th + 0.12), 21.4, -5 + 0.51 * math.sin(th + 0.12)),
             (33 + 0.51 * math.cos(th + 0.12), 18.6, -5 + 0.51 * math.sin(th + 0.12)),
             (33 + 0.51 * math.cos(th - 0.12), 18.6, -5 + 0.51 * math.sin(th - 0.12))]
        isl.poly(q, "soot", (math.cos(th), 0.0, math.sin(th)))
    # vents on the bridge roof
    for vx in (31.5, 35.0):
        box(isl, (vx, 16.25, -5.5), (0.6, 0.25, 0.5), "metal")
        for k in range(4):
            box(isl, (vx, 16.52, -5.9 + k * 0.27), (0.5, 0.03, 0.04), "dark")
    # level A roof railings, life-raft canisters and exterior stairs on the west face
    for xr in (29.45, 36.55):
        rail_run(isl, line_pts((xr, -11.6), (xr, 27.6), 1.0), (8.9, 8.5), 0.03, "metal", 2, "metal",
                 post_h=0.45, post_y0=8.0)
    rail_run(isl, line_pts((29.4, -11.55), (36.6, -11.55), 1.0), (8.9, 8.5), 0.03, "metal", 2, "metal",
             post_h=0.45, post_y0=8.0)
    rail_run(isl, line_pts((29.4, 27.55), (36.6, 27.55), 1.0), (8.9, 8.5), 0.03, "metal", 2, "metal",
             post_h=0.45, post_y0=8.0)
    for zc in (-10.2, 24.5):
        cyl(isl, (29.7, 8.45, zc - 0.8), (29.7, 8.45, zc + 0.8), 0.45, "raft", 10)
    for i in range(16):                                              # exterior stairs, 0.5 m rise per step
        z0 = -11.6 + 0.5 * i
        h = 0.5 * (i + 1)
        box(isl, (29.12, h / 2, z0 + 0.25), (0.27, h / 2, 0.25), "paint_dark")
    cyl(isl, (28.92, 1.0, -11.4), (28.92, 9.0, -3.6), 0.04, "metal", 6)   # stair handrail
    # ladder on the east face, standing off the wall
    cyl(isl, (36.85, 0.0, 19.5), (36.85, 8.0, 19.5), 0.04, "metal", 8)
    cyl(isl, (36.85, 0.0, 20.5), (36.85, 8.0, 20.5), 0.04, "metal", 8)
    for k in range(1, 20):
        y = 0.4 * k
        cyl(isl, (36.85, y, 19.5), (36.85, y, 20.5), 0.025, "metal", 6)
    for y in (1.0, 3.0, 5.0, 7.0):
        box(isl, (36.72, y, 19.5), (0.13, 0.05, 0.05), "metal")
        box(isl, (36.72, y, 20.5), (0.13, 0.05, 0.05), "metal")
    # vertical pipe runs with collars
    for x, z, top_y in ((29.2, -9.0, 14.0), (36.8, -9.0, 8.0), (29.2, 26.5, 8.0)):
        cyl(isl, (x, 0.2, z), (x, top_y, z), 0.14, "pipe", 10)
        for y in range(2, int(top_y), 3):
            cyl(isl, (x - 0.05, y, z), (x + 0.05, y, z), 0.22, "pipe", 10)
    # helipad-style searchlight rail and the platform railing sit above; door plates on the bridge aft
    # weather deck rails on the level B roof, panel seams on levels A and B
    perim = (line_pts((30.1, -6.9), (35.9, -6.9), 1.0) + line_pts((35.9, -6.9), (35.9, 22.9), 1.0)[1:]
             + line_pts((35.9, 22.9), (30.1, 22.9), 1.0)[1:] + line_pts((30.1, 22.9), (30.1, -6.9), 1.0)[1:])
    rail_run(isl, perim, (16.9, 17.4), 0.035, "metal", 1, "metal", post_h=0.9, post_y0=16.0)
    seams(isl, 29.4, 36.6, -11.6, 27.6, 0.0, 8.0, "paint_dark")
    seams(isl, 30.0, 36.0, -7.0, 23.0, 8.0, 16.0, "paint_dark")
    text_obj("77", (36.62, 2.6, 12.0), 3.2, "white", (0, 0, -1), (1, 0, 0), "isl_77_e")
    text_obj("77", (29.38, 2.6, 12.0), 3.2, "white", (0, 0, 1), (-1, 0, 0), "isl_77_w")
    return isl


# ---------------------------------------------------------------- previews
def setup_world():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    try:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(bkit.polyhaven_hdri("kloofendal_overcast_puresky", "1k"),
                                         check_existing=True)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    except Exception as e:
        print("CARRIER: HDRI unavailable, flat storm sky:", e)
        bg.inputs["Color"].default_value = (0.42, 0.44, 0.47, 1)
    bg.inputs["Strength"].default_value = 0.8


def make_camera(name, eye, target, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.05
    cd.clip_end = 2000.0
    co = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(co)
    e, t = G(eye), G(target)
    co.location = e
    d = Vector(t) - Vector(e)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return co


def render_previews():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "None"
    except Exception as e:
        print("CARRIER: view transform left at default:", e)
    setup_world()
    sun = bkit.sun(elevation=25, azimuth=160, strength=1.2, softness=3.0)
    scene.render.resolution_x = RES_W
    scene.render.resolution_y = int(RES_W * 0.62)
    shots = [
        (PREVIEW, (-20, 1.7, -40), (33, 14, 8), 28.0),          # deck level, toward the island
        (PREVIEW_LOW, (-90, -6, -60), (-20, -8, -10), 30.0),    # low over the water, at the hull
        (PREVIEW_EDGE, (-42, 2, 0), (-45, -4, -20), 30.0),      # over the deck edge, at sponson and catwalk
    ]
    for path, eye, tgt, lens in shots:
        cam = make_camera("CamCarrier", eye, tgt, lens)
        scene.camera = cam
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("CARRIER preview", path, round(time.time() - t0, 1), "s")
        bpy.data.objects.remove(cam)
    bpy.data.objects.remove(sun)


# ---------------------------------------------------------------- main
def main():
    global COLL
    t_start = time.time()
    bkit.reset_scene()
    COLL = bpy.context.scene.collection
    for p in (TEX_DIR, os.path.dirname(OUT), os.path.dirname(PREVIEW)):
        os.makedirs(p, exist_ok=True)

    print("CARRIER stage: materials")
    load_materials()
    print("CARRIER stage: deck, hull, island")
    meshes = build_deck()
    meshes.append(build_hull())
    meshes.append(build_details())
    meshes.append(build_island())
    print("CARRIER stage: stains")
    build_stains()
    for m in meshes:
        m.build()

    tris = sum(bkit.tri_count(o) for o in OBJS if o.type == "MESH")
    deck = bpy.data.objects["Ground_deck"]
    assert all(abs(v.co.z) < 1e-6 for v in deck.data.vertices), "deck not at game y=0"
    print("CARRIER objects", len(OBJS), "tris", tris)
    if tris > 60000:
        print("CARRIER WARNING: over 60k triangles")

    if RENDER:
        render_previews()
    bkit.export_glb(OUT, OBJS, image_format="JPEG")
    print("CARRIER exported", OUT, os.path.getsize(OUT) // 1024, "KB")
    print(f"CARRIER done in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
