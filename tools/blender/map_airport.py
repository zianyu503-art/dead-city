"""國際機場 (international airport at dusk) level map for 射擊遊戲, built headless with the blender-modeling skill.

Run from the project root:   blender -b -P tools/blender/map_airport.py
Writes assets/models/map_airport.glb and previews to .claude/work/.

Same conventions as map_downtown.py: positions are GAME coordinates (x, y up, z on the ground), turned into
Blender coordinates with G(p) = (x, -z, y) when each mesh is created, so the glTF export lands back on the
game's axes.

Gameplay data read by the game:
  COL_<n>   axis-aligned box = a collider (terminal, hangar, tower, airliner fuselage and engines, vehicles,
            barriers, fence, trees, floodlight poles)
  LAMP_<n>  empty at a floodlight head = a night light position
  Ground*   ground meshes (grass, taxiways, apron, runway) - they do not cast shadows
The CENTRE block (x=0, z=0) gets only apron concrete and parking markings: the game parks the transport plane there.

Env switches (defaults build everything): MAP_RENDER=top,street|none, MAP_EXPORT=0|1, MAP_SAMPLES=n, MAP_RES=width.
"""

import math
import os
import random
import sys
import time

sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bkit  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

PROJ = "/Users/alex/射擊遊戲"
WORK = os.path.join(PROJ, ".claude", "work")
TEX_DIR = os.path.join(WORK, "map_airport_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_airport.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_airport_top.png"),
    "street": os.path.join(WORK, "map_airport_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 23

# ---------------------------------------------------------------- layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]   # taxiway centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]               # inner block centres, 44 m blocks
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                          # block half size
WALK_H = 0.16                                        # apron top
TAXI_H = 0.004                                       # taxiway concrete, just under the apron
TAXI_LINE_H = 0.012
EXT = 200.0                                          # ground edge
FENCE = 194.0                                        # perimeter fence line
RWY_Z = -168.5                                       # runway centre line (45 m wide)
RWY_HW = 22.5
TERM_F = -115.5                                      # terminal glass front (faces +z, the apron)
TERM_B = -128.5
TERM_Z = -112.0
HANGAR_Z = 112.0
TOWER = (112.0, 0.0)
FUEL_C = (-168.0, 168.0)
HILLS = [(-265.0, -120.0), (-268.0, 20.0), (-262.0, 150.0), (265.0, -150.0), (268.0, 30.0),
         (262.0, 165.0), (-60.0, -265.0), (70.0, -262.0), (-150.0, 262.0), (120.0, 266.0)]
# the 13 inner blocks that hold a parked airliner (row -112 is the terminal, (112,0) the tower,
# row 112 the hangars, (0,0) the empty centre)
AIR_BLOCKS = [(cx, -56.0) for cx in BC] + [(cx, 0.0) for cx in (-112.0, -56.0, 56.0)] + [(cx, 56.0) for cx in BC]
BUS_X, BUS_Z = -56.0, -99.0                          # burnt-out bus on the terminal apron

UPV = (0.0, 1.0, 0.0)
AX = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
MAT = {}
TILE = {}
COLS = []        # (x0, x1, z0, z1, y0, y1) collider boxes
LAMPS = []       # (x, y, z) floodlight head positions


def G(p):
    """game (x, y, z) -> blender (x, -z, y)"""
    return (p[0], -p[2], p[1])


def vadd(*vs):
    return tuple(sum(c) for c in zip(*vs))


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vnorm(v):
    ln = math.sqrt(vdot(v, v)) or 1.0
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def centroid(P):
    n = len(P)
    return tuple(sum(p[k] for p in P) / n for k in range(3))


# ---------------------------------------------------------------- mesh builder
class Mesh:
    """Collects polygons in game coordinates, then becomes one Blender object.

    Vertices are welded by position; each polygon keeps its material name and
    world-scale UVs (meters / tile size of the material), so textures keep real size.
    """

    def __init__(self, name, smooth=False):
        self.name = name
        self.smooth = smooth
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
        if n is not None and vdot(nn, n) < 0:
            clean.reverse()
            nn = vmul(nn, -1.0)
        ax = max(range(3), key=lambda q: abs(nn[q]))
        ua, va = (0, 2) if ax == 1 else ((2, 1) if ax == 0 else (0, 1))
        tile = TILE.get(mat, 2.0)
        uv = [(p[ua] / tile, p[va] / tile) for p in clean]
        self.faces.append(([self._vi(p) for p in clean], mat, uv))

    def build(self, coll):
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
            if self.smooth:
                poly.use_smooth = True
            for k in range(len(poly.vertices)):
                uvl.data[poly.loop_start + k].uv = uv[k]
        obj = bpy.data.objects.new(self.name, me)
        coll.objects.link(obj)
        return obj

    def tris(self):
        return sum(len(f[0]) - 2 for f in self.faces)


# ---------------------------------------------------------------- primitives
def quad_flat(mb, x0, x1, z0, z1, y, mat, n=UPV):
    mb.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], mat, n)


def rect_at(mb, x0, x1, z0, z1, y, mat):
    quad_flat(mb, x0, x1, z0, z1, y, mat)


def obox(mb, c, ax, half, mats):
    """Oriented box: centre c, three unit axes ax, half extents, one material or six
    (+a0, -a0, +a1, -a1, +a2, -a2)."""
    if isinstance(mats, str):
        mats = [mats] * 6
    for k in range(3):
        a, b = [m for m in range(3) if m != k]
        for s, mi in ((1, 2 * k), (-1, 2 * k + 1)):
            cf = vadd(c, vmul(ax[k], s * half[k]))
            pts = [vadd(cf, vmul(ax[a], sa * half[a]), vmul(ax[b], sb * half[b]))
                   for sa, sb in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
            mb.poly(pts, mats[mi], vmul(ax[k], s))


def ocyl(mb, c, ax, r0, r1, length, seg, mat, caps=True):
    """Cylinder centred on c along unit ax; radius r0 at the start, r1 at the end."""
    helper = (0, 1, 0) if abs(ax[1]) < 0.9 else (1, 0, 0)
    u = vnorm(vcross(ax, helper))
    w = vcross(ax, u)

    def ring(t, r):
        return [vadd(c, vmul(ax, t), vmul(u, r * math.cos(2 * math.pi * k / seg)),
                     vmul(w, r * math.sin(2 * math.pi * k / seg))) for k in range(seg)]
    A = ring(-length / 2, r0)
    B = ring(length / 2, r1)
    for k in range(seg):
        k2 = (k + 1) % seg
        mid = 2 * math.pi * (k + 0.5) / seg
        nrad = vadd(vmul(u, math.cos(mid)), vmul(w, math.sin(mid)))
        mb.poly([A[k], A[k2], B[k2], B[k]], mat, nrad)
    if caps:
        mb.poly(A, mat, vmul(ax, -1))
        mb.poly(B, mat, ax)


def vcyl(mb, x, y0, z, r0, r1, h, seg, mat, caps=True):
    ocyl(mb, (x, y0 + h / 2, z), (0, 1, 0), r0, r1, h, seg, mat, caps)


def blob(mb, c, r, mat, rng, rings=4, segs=7, sy=0.82):
    """Lumpy low-poly sphere for tree canopies."""
    grid = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        row = []
        for j in range(segs):
            th = 2 * math.pi * j / segs
            rr = r * (1 + rng.uniform(-0.14, 0.14)) if 0 < i < rings else r
            row.append(vadd(c, (rr * math.sin(phi) * math.cos(th), rr * math.cos(phi) * sy,
                                rr * math.sin(phi) * math.sin(th))))
        grid.append(row)
    for i in range(rings):
        for j in range(segs):
            j2 = (j + 1) % segs
            pts = [grid[i][j], grid[i][j2], grid[i + 1][j2], grid[i + 1][j]]
            cen = vmul(vadd(*pts), 0.25)
            mb.poly(pts, mat, vnorm(vadd(cen, vmul(c, -1))))


def extrude(mb, P, d, mat):
    """Thick flat part: polygon P (3D, coplanar) pushed along vector d."""
    Q = [vadd(p, d) for p in P]
    dn = vnorm(d)
    mb.poly(P, mat, vmul(dn, -1.0))
    mb.poly(Q, mat, dn)
    c = centroid(P)
    m = len(P)
    for k in range(m):
        a, b = P[k], P[(k + 1) % m]
        mid = vmul(vadd(a, b), 0.5)
        n = vnorm(vcross(vsub(b, a), d))
        if vdot(n, vsub(mid, c)) < 0:
            n = vmul(n, -1.0)
        mb.poly([a, b, vadd(b, d), vadd(a, d)], mat, n)


def lframe(a):
    """Vehicle frame for yaw a: side (local +x) and forward (local +z, the nose)."""
    return (math.cos(a), 0.0, -math.sin(a)), (math.sin(a), 0.0, math.cos(a))


def lpt(base, a, lx, ly, lz):
    side, fwd = lframe(a)
    return vadd(base, vmul(side, lx), (0.0, ly, 0.0), vmul(fwd, lz))


def lbox(mb, base, a, lx, lz, yb, hs, hy, hf, mats):
    """Box in a vehicle frame: lx across, lz along the nose, yb = bottom height above the apron."""
    side, fwd = lframe(a)
    obox(mb, lpt(base, a, lx, yb + hy, lz), [side, UPV, fwd], (hs, hy, hf), mats)


def local_col(base, a, lx0, lx1, lz0, lz1, y0, y1):
    """Axis-aligned collider around a rotated local rectangle."""
    pts = [lpt(base, a, lx, 0.0, lz) for lx in (lx0, lx1) for lz in (lz0, lz1)]
    xs = [p[0] for p in pts]
    zs = [p[2] for p in pts]
    COLS.append((min(xs), max(xs), min(zs), max(zs), y0, y1))


def solid_runs(cuts, lo=-EXT, hi=EXT):
    """Free intervals of [lo, hi] once the cut intervals are removed."""
    runs = []
    cur = lo
    for a, b in sorted(cuts):
        if a > cur:
            runs.append((cur, a))
        cur = max(cur, b)
    if cur < hi:
        runs.append((cur, hi))
    return runs


def tree(mb, x, z, s, rng, y0=WALK_H):
    h = 3.4 * s
    vcyl(mb, x, y0, z, 0.24 * s, 0.15 * s, h, 7, "bark")
    for _ in range(3):
        cx = x + rng.uniform(-0.9, 0.9) * s
        cz = z + rng.uniform(-0.9, 0.9) * s
        cy = y0 + h + rng.uniform(0.2, 1.3) * s
        blob(mb, (cx, cy, cz), rng.uniform(1.3, 1.8) * s, rng.choice(["leaf_a", "leaf_b", "leaf_c"]), rng)


def cone(mb, x, z, y0=0.0):
    ocyl(mb, (x, y0 + 0.36, z), (0, 1, 0), 0.2, 0.03, 0.7, 8, "cone")
    obox(mb, (x, y0 + 0.015, z), AX, (0.21, 0.015, 0.21), "cone_base")


def barrier(mb, x, z, rot, y0=WALK_H):
    """Concrete jersey barrier, 3 m long along the forward axis, trapezoid profile."""
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    prof = [(-0.3, 0.0), (0.3, 0.0), (0.1, 0.8), (-0.1, 0.8)]

    def pt(p, t):
        return vadd((x, y0, z), vmul(s, p[0]), (0, p[1], 0), vmul(f, t))
    for k in range(4):
        a, b = prof[k], prof[(k + 1) % 4]
        ex, ey = b[0] - a[0], b[1] - a[1]
        n2 = (ey, -ex)
        n3 = vnorm(vadd(vmul(s, n2[0]), vmul(UPV, n2[1])))
        mb.poly([pt(a, -1.5), pt(b, -1.5), pt(b, 1.5), pt(a, 1.5)], "concrete", n3)
    mb.poly([pt(p, -1.5) for p in prof], "concrete", vmul(f, -1))
    mb.poly([pt(p, 1.5) for p in prof], "concrete", f)


# ---------------------------------------------------------------- materials
PH_SETS = {
    # name: (polyhaven id, tile size in metres)
    "asphalt": ("asphalt_02", 4.0),
    "apron": ("concrete_pavement", 4.0),
    "grass": ("leafy_grass", 3.0),
    "concrete": ("concrete_wall_004", 3.0),
    "roof": ("tarred_gravel", 3.0),
    "bark": ("bark_brown_02", 1.2),
}

CONST = {
    # name: (rgb, roughness, metallic, specular)
    "glass": ((0.05, 0.085, 0.10), 0.04, 0.0, 0.7),
    "dark": ((0.012, 0.012, 0.014), 0.85, 0.0, 0.3),
    "frame": ((0.80, 0.78, 0.74), 0.5, 0.0, 0.5),
    "frame_dark": ((0.11, 0.11, 0.12), 0.4, 0.5, 0.5),
    "metal_dark": ((0.07, 0.07, 0.08), 0.45, 0.8, 0.5),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0.5),
    "ac": ((0.52, 0.53, 0.55), 0.5, 0.6, 0.5),
    "hangar": ((0.58, 0.60, 0.62), 0.45, 0.6, 0.5),
    "fence": ((0.20, 0.22, 0.22), 0.5, 0.6, 0.5),
    "tank": ((0.42, 0.28, 0.17), 0.6, 0.5, 0.5),
    "lamp_head": ((0.86, 0.82, 0.66), 0.25, 0.0, 0.6),
    "leaf_a": ((0.10, 0.27, 0.07), 0.8, 0.0, 0.4),
    "leaf_b": ((0.18, 0.33, 0.09), 0.8, 0.0, 0.4),
    "leaf_c": ((0.28, 0.31, 0.11), 0.8, 0.0, 0.4),
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "paint_yellow": ((0.90, 0.70, 0.10), 0.6, 0.0, 0.5),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "burnt": ((0.035, 0.03, 0.028), 0.9, 0.0, 0.3),
    "cone": ((0.95, 0.38, 0.05), 0.5, 0.0, 0.5),
    "cone_base": ((0.05, 0.05, 0.05), 0.6, 0.0, 0.5),
    "bag": ((0.03, 0.03, 0.035), 0.6, 0.0, 0.4),
    "cardboard": ((0.45, 0.33, 0.20), 0.9, 0.0, 0.3),
    "sign_red": ((0.42, 0.08, 0.06), 0.5, 0.0, 0.5),
    "sign_navy": ((0.07, 0.10, 0.26), 0.5, 0.0, 0.5),
    "sign_green": ((0.07, 0.22, 0.11), 0.5, 0.0, 0.5),
    "sign_ochre": ((0.60, 0.42, 0.10), 0.5, 0.0, 0.5),
    "sign_cream": ((0.66, 0.61, 0.50), 0.5, 0.0, 0.5),
    "car_white": ((0.78, 0.78, 0.76), 0.35, 0.2, 0.5),
    "car_yellow": ((0.72, 0.52, 0.10), 0.35, 0.2, 0.5),
    "car_red": ((0.50, 0.06, 0.05), 0.32, 0.25, 0.5),
    "car_silver": ((0.45, 0.47, 0.50), 0.3, 0.45, 0.5),
}


def cmat(name, rgb, rough, metal, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Specular IOR Level"].default_value = spec
    return mat


def load_materials():
    bkit.CACHE = TEX_DIR
    for key, (aid, tile) in PH_SETS.items():
        maps = bkit.polyhaven_texture(aid, res="1k")
        maps = {k: v for k, v in maps.items() if k in ("color", "normal", "roughness")}
        MAT[key] = bkit.pbr_material(key, maps, scale=1.0, coords="UV")
        TILE[key] = tile
        print("MAP texture", key, aid, sorted(maps))
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name in CONST:
        TILE.setdefault(name, 1.0)


# ---------------------------------------------------------------- ground and markings
def block_slab(mb, cx, cz):
    """Raised apron slab (top at WALK_H) with a kerb face on each side."""
    h = WALK_H
    x0, x1, z0, z1 = cx - HALF, cx + HALF, cz - HALF, cz + HALF
    mb.poly([(x0, h, z0), (x1, h, z0), (x1, h, z1), (x0, h, z1)], "apron", UPV)
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], "concrete", (0, 0, -1))
    mb.poly([(x0, 0, z1), (x0, h, z1), (x1, h, z1), (x1, 0, z1)], "concrete", (0, 0, 1))
    mb.poly([(x0, 0, z0), (x0, h, z0), (x0, h, z1), (x0, 0, z1)], "concrete", (-1, 0, 0))
    mb.poly([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], "concrete", (1, 0, 0))


def stand_outline(mb, cx, cz, h=20.5):
    """Yellow stand box around a 44 m apron block."""
    y = WALK_H + 0.012
    rect_at(mb, cx - h, cx + h, cz + h - 0.12, cz + h + 0.12, y, "paint_yellow")
    rect_at(mb, cx - h, cx + h, cz - h - 0.12, cz - h + 0.12, y, "paint_yellow")
    rect_at(mb, cx - h - 0.12, cx - h + 0.12, cz - h, cz + h, y, "paint_yellow")
    rect_at(mb, cx + h - 0.12, cx + h + 0.12, cz - h, cz + h, y, "paint_yellow")


def hill(mb, cx, cz, R, h, rng, n=12):
    """Low rounded hill: a height field that falls to zero at radius R."""
    xs = [cx - R + 2.0 * R * i / n for i in range(n + 1)]
    zs = [cz - R + 2.0 * R * j / n for j in range(n + 1)]
    H = [[0.0] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(n + 1):
            r2 = ((xs[i] - cx) / R) ** 2 + ((zs[j] - cz) / R) ** 2
            if r2 < 1.0:
                H[i][j] = h * (1.0 - r2) ** 1.3 * rng.uniform(0.9, 1.1)
    for i in range(n):
        for j in range(n):
            if max(H[i][j], H[i + 1][j], H[i + 1][j + 1], H[i][j + 1]) <= 0.0:
                continue
            mb.poly([(xs[i], H[i][j], zs[j]), (xs[i + 1], H[i + 1][j], zs[j]),
                     (xs[i + 1], H[i + 1][j + 1], zs[j + 1]), (xs[i], H[i][j + 1], zs[j + 1])], "grass", UPV)


# ---------------------------------------------------------------- terminal
def terminal_segment(mb, cx, k):
    """One 38 m terminal block: glass front, saw-tooth roof, airline sign band, gate plates."""
    x0, x1 = cx - 19.0, cx + 19.0
    yb = WALK_H
    zc = (TERM_B + TERM_F) / 2
    obox(mb, (cx, yb + 4.75, zc), AX, (19.0, 4.75, (TERM_F - TERM_B) / 2),
         ["concrete", "concrete", "roof", "concrete", "glass", "concrete"])
    sign = ["sign_navy", "sign_red", "sign_green", "sign_ochre", "sign_cream"][k % 5]
    obox(mb, (cx, yb + 8.9, TERM_F + 0.06), AX, (18.6, 0.4, 0.06), sign)
    for i in range(-4, 5):
        obox(mb, (cx + i * 4.75, yb + 4.6, TERM_F + 0.06), AX, (0.07, 4.4, 0.08), "frame")
    for i in (-3, -1, 1, 3):
        obox(mb, (cx + i * 4.75 + 2.375, yb + 2.2, TERM_F + 0.08), AX, (0.9, 0.3, 0.05), "sign_ochre")
    n = 4
    w = 38.0 / n
    for i in range(n):
        xa = x0 + i * w + 0.3
        xb = x0 + (i + 1) * w - 0.3
        # sloped clerestory glass rising toward the apron (normal up and back)
        mb.poly([(xa, yb + 9.5, TERM_B + 0.5), (xb, yb + 9.5, TERM_B + 0.5),
                 (xb, yb + 12.5, TERM_F), (xa, yb + 12.5, TERM_F)], "glass", (0.0, 13.0, -3.0))
        # glazed front of each tooth
        mb.poly([(xa, yb + 9.5, TERM_F), (xb, yb + 9.5, TERM_F),
                 (xb, yb + 12.5, TERM_F), (xa, yb + 12.5, TERM_F)], "glass", (0.0, 0.0, 1.0))


def connector(mb, xa, xb):
    """Glass hall between two terminal blocks (the taxiway crossings stay open at ground level)."""
    yb = WALK_H
    obox(mb, ((xa + xb) / 2, yb + 3.7, (TERM_B + TERM_F) / 2), AX, ((xb - xa) / 2, 3.7, (TERM_F - TERM_B) / 2),
         ["concrete", "concrete", "roof", "concrete", "glass", "concrete"])


def jet_bridge(mb, x):
    """Passenger jet bridge: a tunnel from the terminal front to a rotunda at z=-103."""
    yb = WALK_H
    obox(mb, (x, yb + 3.4, -109.25), AX, (1.5, 0.7, 6.25), "ac")
    obox(mb, (x, yb + 1.43, -109.0), AX, (0.4, 1.43, 0.4), "ac")
    vcyl(mb, x, yb, -101.0, 2.0, 2.0, 3.4, 12, "ac")
    vcyl(mb, x, yb + 3.4, -101.0, 2.15, 2.15, 0.2, 12, "frame_dark")
    COLS.append((x - 2.0, x + 2.0, -103.0, -99.0, 0.0, 3.0))


# ---------------------------------------------------------------- control tower
def control_tower(mb, cx, cz):
    yb = WALK_H
    vcyl(mb, cx, yb, cz, 3.5, 3.2, 30.8, 14, "concrete")           # shaft to y=31
    vcyl(mb, cx, 31.0, cz, 5.6, 5.6, 0.25, 16, "frame_dark")        # cab floor
    vcyl(mb, cx, 31.25, cz, 4.9, 4.9, 3.6, 16, "glass")             # glass cab to 34.85
    vcyl(mb, cx, 34.85, cz, 6.6, 6.6, 0.5, 16, "frame_dark")        # overhanging roof
    vcyl(mb, cx, 35.35, cz, 2.2, 2.2, 0.8, 12, "metal")             # roof cupola
    vcyl(mb, cx, 36.15, cz, 0.12, 0.12, 3.0, 6, "metal")            # radar mast
    ocyl(mb, (cx, 39.5, cz), UPV, 1.8, 1.8, 0.2, 12, "metal")       # radar dish
    obox(mb, (cx - 9.0, yb + 3.0, cz), AX, (5.0, 3.0, 9.0),
         ["concrete", "concrete", "roof", "concrete", "concrete", "concrete"])
    obox(mb, (cx - 9.0, yb + 2.2, cz + 9.06), AX, (4.2, 0.6, 0.05), "glass")
    COLS.append((cx - 14.0, cx - 4.0, cz - 9.0, cz + 9.0, 0.0, 3.0))
    COLS.append((cx - 3.5, cx + 3.5, cz - 3.5, cz + 3.5, 0.0, 3.0))


# ---------------------------------------------------------------- hangar
def hangar(mb, cx, cz, W=30.0, D=26.0, H=9.0, RH=12.0):
    """Gabled metal hangar, ridge along x, big door open toward -z."""
    yb = WALK_H
    x0, x1 = cx - W / 2, cx + W / 2
    zf, zb = cz - D / 2, cz + D / 2
    yt, yr = yb + H, yb + RH
    for xs, nx in ((x0, -1.0), (x1, 1.0)):
        mb.poly([(xs, yb, zf), (xs, yb, zb), (xs, yt, zb), (xs, yr, cz), (xs, yt, zf)], "metal", (nx, 0.0, 0.0))
    mb.poly([(x0, yb, zb), (x1, yb, zb), (x1, yt, zb), (x0, yt, zb)], "metal", (0.0, 0.0, 1.0))
    xd0, xd1, DH = cx - 13.0, cx + 13.0, 8.5
    mb.poly([(x0, yb, zf), (xd0, yb, zf), (xd0, yt, zf), (x0, yt, zf)], "metal", (0.0, 0.0, -1.0))
    mb.poly([(xd1, yb, zf), (x1, yb, zf), (x1, yt, zf), (xd1, yt, zf)], "metal", (0.0, 0.0, -1.0))
    mb.poly([(xd0, yb + DH, zf), (xd1, yb + DH, zf), (xd1, yt, zf), (xd0, yt, zf)], "metal", (0.0, 0.0, -1.0))
    mb.poly([(xd0, yb, zf + 1.2), (xd1, yb, zf + 1.2), (xd1, yb + DH, zf + 1.2), (xd0, yb + DH, zf + 1.2)],
            "dark", (0.0, 0.0, -1.0))                                      # dark interior behind the door
    for xf in (xd0 - 0.3, xd1 + 0.3):
        obox(mb, (xf, yb + DH / 2, zf - 0.1), AX, (0.3, DH / 2, 0.15), "frame_dark")
    mb.poly([(x0, yt, zf), (x1, yt, zf), (x1, yr, cz), (x0, yr, cz)], "hangar", (0.0, RH - H, -D / 2))
    mb.poly([(x0, yt, zb), (x1, yt, zb), (x1, yr, cz), (x0, yr, cz)], "hangar", (0.0, RH - H, D / 2))
    COLS.append((x0, x1, zf, zb, 0.0, 3.0))


# ---------------------------------------------------------------- airliner (built once, linked many times)
def airliner(mb):
    """A twin-engine airliner, about 35 m long, nose toward +z, on its wheels at y=0."""
    W = "paint_white"
    ocyl(mb, (0.0, 3.6, 0.0), (0, 0, 1), 1.95, 1.95, 24.0, 16, W)          # fuselage
    ocyl(mb, (0.0, 3.6, 14.75), (0, 0, 1), 1.95, 0.55, 5.5, 16, W)         # nose cone
    ocyl(mb, (0.0, 3.6, -14.75), (0, 0, -1), 1.95, 0.5, 5.5, 16, W)        # tail cone
    for sx in (-1.0, 1.0):
        for i in range(14):                                                 # passenger windows
            obox(mb, (sx * 1.84, 4.3, -9.0 + 1.5 * i), AX, (0.1, 0.2, 0.45), "glass")
        for z in (9.0, -8.0):                                               # doors
            obox(mb, (sx * 1.9, 3.2, z), AX, (0.12, 0.95, 0.5), "frame_dark")
    for sx in (-1.0, 1.0):                                                  # cockpit glass
        obox(mb, (sx * 0.45, 4.5, 15.1), AX, (0.35, 0.2, 0.05), "glass")
    wing = [(1.9, 4.5), (17.2, -3.5), (17.2, -6.0), (1.9, -3.5)]           # swept, low wing
    for sx in (-1.0, 1.0):
        extrude(mb, [(sx * x, 2.45, z) for x, z in wing], (0.0, 0.3, 0.0), W)
        ocyl(mb, (sx * 7.2, 1.45, 1.6), (0, 0, 1), 0.95, 0.85, 4.6, 12, "metal")   # nacelle
        ocyl(mb, (sx * 7.2, 1.45, -0.75), (0, 0, -1), 0.8, 0.8, 0.1, 12, "dark")   # exhaust
        obox(mb, (sx * 7.2, 2.25, 1.6), AX, (0.12, 0.3, 1.5), "metal_dark")        # pylon
    stab = [(0.9, -12.0), (5.5, -14.6), (5.5, -17.0), (0.9, -16.6)]        # (x, z) tail planes
    for sx in (-1.0, 1.0):
        extrude(mb, [(sx * x, 4.5, z) for x, z in stab], (0.0, 0.12, 0.0), W)
    fin = [(-10.5, 5.4), (-14.5, 11.6), (-17.1, 11.6), (-17.4, 4.2)]        # (z, y) tail fin
    extrude(mb, [(-0.15, y, z) for z, y in fin], (0.3, 0.0, 0.0), "car_red")
    for sx in (-1.0, 1.0):                                                  # landing gear
        for z in (-0.4, -2.0):
            ocyl(mb, (sx * 3.3, 0.6, z), (1, 0, 0), 0.6, 0.6, 0.45, 10, "tire")
        obox(mb, (sx * 3.3, 1.8, -1.2), AX, (0.12, 0.6, 0.12), "metal_dark")
        ocyl(mb, (sx * 0.5, 0.6, 12.0), (1, 0, 0), 0.6, 0.6, 0.4, 10, "tire")
    obox(mb, (0.0, 1.5, 12.0), AX, (0.14, 0.9, 0.14), "metal_dark")


def light_aircraft(mb):
    """Single-engine light aircraft parked outside a hangar, about 7.5 m long, nose toward +z."""
    W = "car_white"
    ocyl(mb, (0.0, 1.15, 0.0), (0, 0, 1), 0.6, 0.6, 7.2, 12, W)
    ocyl(mb, (0.0, 1.15, 4.0), (0, 0, 1), 0.6, 0.25, 0.8, 12, W)
    obox(mb, (0.0, 1.15, 4.5), AX, (0.05, 0.9, 0.03), "dark")              # propeller
    obox(mb, (0.0, 1.62, 1.0), AX, (0.5, 0.22, 0.9), "glass")
    obox(mb, (0.0, 1.3, 0.4), AX, (5.3, 0.06, 0.9), W)
    obox(mb, (0.0, 2.05, -3.1), AX, (0.05, 0.7, 0.55), "car_red")
    obox(mb, (0.0, 1.5, -3.0), AX, (1.8, 0.05, 0.5), W)
    for x in (-1.0, 1.0):
        ocyl(mb, (x, 0.25, -0.4), (1, 0, 0), 0.25, 0.25, 0.2, 8, "tire")
    ocyl(mb, (0.0, 0.25, 2.6), (1, 0, 0), 0.25, 0.25, 0.2, 8, "tire")


def airliner_extras(mb, cx, cz, a):
    """Stairs truck, baggage train, fuel bowser, cones and wheel chocks around one parked airliner."""
    base = (cx, WALK_H, cz)
    lbox(mb, base, a, -6.8, 8.0, 0.35, 1.3, 0.85, 3.4, "car_white")           # stairs truck
    lbox(mb, base, a, -3.4, 8.2, 0.0, 0.9, 1.3, 1.0, "metal")                 # stairs up to the door
    local_col(base, a, -8.1, -5.5, 4.6, 11.4, 0.0, 3.0)
    lbox(mb, base, a, 9.0, -5.5, 0.25, 1.0, 0.7, 1.6, "car_yellow")           # baggage tug
    for lz in (-9.5, -12.5, -15.5):                                           # baggage carts
        lbox(mb, base, a, 9.0, lz, 0.3, 1.0, 0.45, 1.1, "metal_dark")
        lbox(mb, base, a, 9.0, lz, 1.2, 0.85, 0.2, 1.0, "cardboard")
    local_col(base, a, 8.0, 10.0, -17.0, -4.0, 0.0, 1.8)
    lbox(mb, base, a, -10.0, -6.0, 0.4, 1.2, 1.0, 2.5, "car_silver")          # fuel bowser
    local_col(base, a, -11.2, -8.8, -8.5, -3.5, 0.0, 2.4)
    for lx, lz in ((-12.5, 13.0), (12.5, 13.0), (-14.0, -13.0), (14.0, -13.0)):
        wx, _, wz = lpt(base, a, lx, 0.0, lz)
        cone(mb, wx, wz, WALK_H)
    for lx in (-4.0, 4.0):                                                    # chocks at the main gear
        lbox(mb, base, a, lx, -1.3, 0.0, 0.25, 0.15, 0.35, "cone_base")


def floodlight(mb, x, z):
    """Apron floodlight mast, 24 m, with four heads that are night light positions."""
    vcyl(mb, x, WALK_H, z, 0.2, 0.14, 24.0, 8, "metal")
    obox(mb, (x, 24.4, z), AX, (1.3, 0.12, 0.8), "metal_dark")
    for dx in (-0.9, 0.9):
        for dz in (-0.5, 0.5):
            obox(mb, (x + dx, 24.25, z + dz), AX, (0.35, 0.2, 0.25), "lamp_head")
            LAMPS.append((x + dx, 24.1, z + dz))
    COLS.append((x - 0.3, x + 0.3, z - 0.3, z + 0.3, 0.0, 3.0))


def burnt_bus(mb, x, z):
    obox(mb, (x, WALK_H + 1.5, z), AX, (1.6, 1.5, 6.0), "burnt")
    for dz in (-4.0, 4.0):
        for sx in (-1.0, 1.0):
            ocyl(mb, (x + sx * 1.6, WALK_H + 0.5, z + dz), (1, 0, 0), 0.5, 0.5, 0.35, 10, "tire")
    COLS.append((x - 1.95, x + 1.95, z - 6.2, z + 6.2, 0.0, 3.0))


def lying_cart(mb, x, z):
    """Baggage cart knocked on its side, long axis along z."""
    obox(mb, (x, WALK_H + 0.55, z), [UPV, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)], (0.55, 1.0, 1.1), "metal")


def luggage(mb, cx, rng):
    """Suitcases and cartons scattered on the apron in front of a terminal block."""
    placed = 0
    while placed < 7:
        x = cx + rng.uniform(-16.0, 16.0)
        if abs(x - (cx - 9.0)) < 2.5 or abs(x - (cx + 9.0)) < 2.5:
            continue
        z = rng.uniform(-113.5, -107.0)
        a = rng.uniform(0.0, math.pi)
        side, fwd = lframe(a)
        if rng.random() < 0.5:
            obox(mb, (x, WALK_H + 0.25, z), [side, UPV, fwd], (0.4, 0.25, 0.28), "bag")
        else:
            obox(mb, (x, WALK_H + 0.2, z), [side, UPV, fwd], (0.35, 0.2, 0.3), "cardboard")
        placed += 1


def fuel_farm(mb):
    fx, fz = FUEL_C
    for dx, dz in ((-10.0, 8.0), (4.0, 8.0), (-10.0, -6.0), (4.0, -6.0)):
        x, z = fx + dx, fz + dz
        vcyl(mb, x, 0.0, z, 5.0, 5.0, 9.0, 16, "tank")
        COLS.append((x - 5.0, x + 5.0, z - 5.0, z + 5.0, 0.0, 3.0))
    obox(mb, (fx + 12.0, 1.5, fz + 4.0), AX, (3.0, 1.5, 2.5), "concrete")
    COLS.append((fx + 9.0, fx + 15.0, fz + 1.5, fz + 6.5, 0.0, 3.0))
    obox(mb, (fx + 3.0, 2.2, fz + 0.5), AX, (7.0, 0.15, 0.15), "metal")


def fence(mb):
    """Chain-link style perimeter with 2.4 m panels; gaps where the taxiways leave the airport."""
    cuts = [(rc - 6.0, rc + 6.0) for rc in ROADS]
    segs = solid_runs(cuts, -FENCE, FENCE)
    H = 2.4
    for f in (-FENCE, FENCE):
        for p0, p1 in segs:
            pts_x = [(p0, 0.0, f), (p1, 0.0, f), (p1, H, f), (p0, H, f)]
            pts_z = [(f, 0.0, p0), (f, 0.0, p1), (f, H, p1), (f, H, p0)]
            for n in ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0)):
                mb.poly(pts_x, "fence", n)
            for n in ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)):
                mb.poly(pts_z, "fence", n)
            COLS.append((p0, p1, f - 0.2, f + 0.2, 0.0, 2.5))
            t = p0
            while t <= p1 + 1e-6:
                obox(mb, (t, 1.2, f), AX, (0.06, 1.2, 0.06), "fence")
                t += 8.0
    for f in (-FENCE, FENCE):
        for p0, p1 in segs:
            COLS.append((f - 0.2, f + 0.2, p0, p1, 0.0, 2.5))
            t = p0
            while t <= p1 + 1e-6:
                obox(mb, (f, 1.2, t), AX, (0.06, 1.2, 0.06), "fence")
                t += 8.0


def main():
    t_start = time.time()
    rng = random.Random(SEED)
    bkit.reset_scene()
    scene = bpy.context.scene
    coll = scene.collection
    os.makedirs(TEX_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)

    print("MAP stage: textures")
    load_materials()

    print("MAP stage: ground, taxiways, runway, apron")
    g_grass = Mesh("Ground_grass")
    g_far = Mesh("Ground_far")
    g_taxi = Mesh("Ground_taxiway")
    g_apron = Mesh("Ground_apron")
    g_runway = Mesh("Ground_runway")
    markings = Mesh("Ground_markings")
    lights = Mesh("Ground_lights")
    hills = Mesh("Hills")
    g_grass.poly([(-EXT, 0, -EXT), (EXT, 0, -EXT), (EXT, 0, EXT), (-EXT, 0, EXT)], "grass", UPV)
    g_far.poly([(-330, -0.3, -330), (330, -0.3, -330), (330, -0.3, 330), (-330, -0.3, 330)], "grass", UPV)
    # taxiways: the x-running strips are whole, the z-running strips stop at the crossings, so no faces overlap
    for rc in ROADS:
        for a, b in solid_runs([(rd - 6.0, rd + 6.0) for rd in ROADS]):
            rect_at(g_taxi, rc - 6.0, rc + 6.0, a, b, TAXI_H, "apron")
        rect_at(g_taxi, -EXT, EXT, rc - 6.0, rc + 6.0, TAXI_H, "apron")
    # taxiway centre and edge lines, broken at every crossing
    runs = solid_runs([(rd - 7.0, rd + 7.0) for rd in ROADS])
    for rc in ROADS:
        for off in (0.0, -5.4, 5.4):
            p = rc + off
            for a, b in runs:
                rect_at(markings, p - 0.15, p + 0.15, a, b, TAXI_LINE_H, "paint_yellow")
                rect_at(markings, a, b, p - 0.15, p + 0.15, TAXI_LINE_H, "paint_yellow")
    # taxiway edge lights, kept off the crossings
    for rc in ROADS:
        for t in range(-160, 161, 40):
            if any(abs(t - rd) < 9.0 for rd in ROADS):
                continue
            for off in (-5.7, 5.7):
                obox(lights, (rc + off, 0.1, t), AX, (0.14, 0.1, 0.14), "lamp_head")
                obox(lights, (t, 0.1, rc + off), AX, (0.14, 0.1, 0.14), "lamp_head")
    # runway 09/27 style: asphalt, centreline dashes, edge lines, thresholds, edge lights
    rect_at(g_runway, -188.0, 188.0, RWY_Z - RWY_HW, RWY_Z + RWY_HW, 0.02, "asphalt")
    for k in range(12):
        x0 = -174.0 + 30.0 * k
        rect_at(markings, x0, x0 + 18.0, RWY_Z - 0.2, RWY_Z + 0.2, 0.03, "paint_white")
    for zz in (RWY_Z - RWY_HW + 0.5, RWY_Z + RWY_HW - 0.5):
        rect_at(markings, -188.0, 188.0, zz - 0.15, zz + 0.15, 0.03, "paint_white")
    for side in (-1.0, 1.0):
        for k in range(6):
            x0 = -186.0 + 3.2 * k if side < 0 else 186.0 - 3.2 * k - 1.6
            rect_at(markings, x0, x0 + 1.6, RWY_Z - 18.0, RWY_Z + 18.0, 0.03, "paint_white")
    for x in range(-180, 181, 30):
        for zz in (RWY_Z - RWY_HW - 0.4, RWY_Z + RWY_HW + 0.4):
            obox(lights, (x, 0.1, zz), AX, (0.2, 0.1, 0.2), "lamp_head")
    # apron slabs (all 25 inner blocks) and parking markings
    for cx in BC:
        for cz in BC:
            block_slab(g_apron, cx, cz)
    stand_outline(markings, 0.0, 0.0)                                       # centre: the transport plane's stand
    rect_at(markings, -20.5, 20.5, -0.15, 0.15, WALK_H + 0.012, "paint_yellow")
    rect_at(markings, -0.15, 0.15, -20.5, 20.5, WALK_H + 0.012, "paint_yellow")
    for cx, cz in AIR_BLOCKS:
        stand_outline(markings, cx, cz)
    for cx in BC:                                                           # terminal stand lines at each bridge
        for dx in (-9.0, 9.0):
            rect_at(markings, cx + dx - 0.12, cx + dx + 0.12, -115.0, -92.0, WALK_H + 0.012, "paint_white")
        rect_at(markings, cx - 14.0, cx + 14.0, 90.6, 91.2, WALK_H + 0.012, "paint_yellow")   # hangar hold line

    print("MAP stage: terminal, bridges, tower, hangars, hills")
    term = Mesh("Terminal")
    bridges = Mesh("JetBridges")
    tower_mb = Mesh("ControlTower")
    hangar_mb = Mesh("Hangars")
    for k, cx in enumerate(BC):
        terminal_segment(term, cx, k)
        COLS.append((cx - 19.0, cx + 19.0, TERM_B, TERM_F, 0.0, 3.0))
        for dx in (-9.0, 9.0):
            jet_bridge(bridges, cx + dx)
    for i in range(4):
        xa, xb = BC[i] + 19.0, BC[i + 1] - 19.0
        connector(term, xa, xb)
        COLS.append((xa, xb, TERM_B, TERM_F, 0.0, 3.0))
    control_tower(tower_mb, TOWER[0], TOWER[1])
    for cx in BC:
        hangar(hangar_mb, cx, HANGAR_Z)
    for hx, hz in HILLS:
        hill(hills, hx, hz, 55.0, rng.uniform(22.0, 34.0), rng)

    print("MAP stage: airliners, light aircraft, vehicles")
    air = Mesh("Airliner")
    airliner(air)
    light = Mesh("LightAircraft")
    light_aircraft(light)
    veh = Mesh("Vehicles")
    clutter = Mesh("Clutter")
    air_spots = []
    for cx, cz in AIR_BLOCKS:
        a = rng.choice([0.0, math.pi / 2, math.pi, 1.5 * math.pi])
        air_spots.append((cx, cz, a))
        base = (cx, WALK_H, cz)
        local_col(base, a, -2.0, 2.0, -17.5, 17.5, 0.0, 4.0)                  # fuselage
        local_col(base, a, 6.25, 8.15, -0.7, 3.9, 0.0, 2.4)                   # engines
        local_col(base, a, -8.15, -6.25, -0.7, 3.9, 0.0, 2.4)
        airliner_extras(veh, cx, cz, a)
    light_spots = []
    for cx in BC:
        a = rng.choice([0.0, math.pi])
        light_spots.append((cx, 93.5, a))
        local_col((cx, WALK_H, 93.5), a, -0.6, 0.6, -3.6, 4.4, 0.0, 2.0)
    for x, z in ((-62.0, -110.0), (-51.5, -110.0), (52.0, -110.0)):
        barrier(veh, x, z, 0.0, WALK_H)
        local_col((x, WALK_H, z), 0.0, -0.35, 0.35, -1.5, 1.5, 0.0, 3.0)
    burnt_bus(veh, BUS_X, BUS_Z)
    for cx in BC:
        luggage(clutter, cx, rng)
    for cz in (-3.0, 0.5, 4.0):
        lying_cart(clutter, TOWER[0] + 8.0, TOWER[1] + cz)
    COLS.append((TOWER[0] + 7.0, TOWER[0] + 9.0, TOWER[1] - 4.1, TOWER[1] + 5.1, 0.0, 1.2))
    fuel_farm(clutter)

    print("MAP stage: floodlights, fence, trees")
    masts = Mesh("Masts")
    for cx, cz in AIR_BLOCKS:
        floodlight(masts, cx + 19.0, cz + 19.0)
    for cx in BC:
        floodlight(masts, cx + 19.0, TERM_Z + 19.0)
        floodlight(masts, cx - 19.0, HANGAR_Z - 19.0)
    floodlight(masts, TOWER[0] - 19.0, TOWER[1] + 19.0)
    fence_mb = Mesh("Fence")
    fence(fence_mb)
    trees = Mesh("Trees", smooth=True)
    ring_blocks = [(x, z) for z in RING_C for x in RING_C if abs(x) == 168 or abs(z) == 168]
    for cx, cz in ring_blocks:
        if cz == -168.0 or (cx, cz) == FUEL_C:
            continue
        for _ in range(2):
            x = cx + rng.uniform(-14.0, 14.0)
            z = cz + rng.uniform(-14.0, 14.0)
            s = rng.uniform(0.9, 1.3)
            tree(trees, x, z, s, rng, 0.0)
            COLS.append((x - 0.35, x + 0.35, z - 0.35, z + 0.35, 0.0, 3.0))

    print("MAP stage: build objects")
    meshes = [g_grass, g_far, g_taxi, g_apron, g_runway, markings, lights, hills, term, bridges, tower_mb,
              hangar_mb, veh, clutter, masts, fence_mb, trees]
    objs = []
    tri_total = 0
    for mb in meshes:
        if mb.faces:
            objs.append(mb.build(coll))
            tri_total += mb.tris()

    air_obj = air.build(coll)
    air_tris = air.tris()
    for k, (cx, cz, a) in enumerate(air_spots):
        if k == 0:
            o = air_obj
        else:
            o = bpy.data.objects.new("Airliner_tmp", air_obj.data)
            coll.objects.link(o)
        o.name = f"Airliner_{k + 1:02d}"
        o.location = G((cx, WALK_H, cz))
        o.rotation_euler = (0.0, 0.0, a)
        objs.append(o)
    light_obj = light.build(coll)
    light_tris = light.tris()
    for k, (cx, cz, a) in enumerate(light_spots):
        if k == 0:
            o = light_obj
        else:
            o = bpy.data.objects.new("LightAircraft_tmp", light_obj.data)
            coll.objects.link(o)
        o.name = f"LightAircraft_{k + 1:02d}"
        o.location = G((cx, WALK_H, 93.5))
        o.rotation_euler = (0.0, 0.0, a)
        objs.append(o)
    shown_tris = tri_total + air_tris * len(air_spots) + light_tris * len(light_spots)

    # gameplay data: COL_ boxes (unit cube, scaled), LAMP_ empties
    cube = bpy.data.meshes.new("COL_unit")
    cube.from_pydata([(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
                      (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)], [],
                     [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)])
    cube.update()
    for i, (x0, x1, z0, z1, y0, y1) in enumerate(COLS):
        o = bpy.data.objects.new(f"COL_{i + 1:03d}", cube)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        o.location = G((cx, (y0 + y1) / 2, cz))
        o.scale = (x1 - x0, z1 - z0, y1 - y0)
        coll.objects.link(o)
        objs.append(o)
    for i, (x, y, z) in enumerate(LAMPS):
        o = bpy.data.objects.new(f"LAMP_{i + 1:03d}", None)
        o.empty_display_type = "PLAIN_AXES"
        o.empty_display_size = 0.25
        o.location = G((x, y, z))
        coll.objects.link(o)
        objs.append(o)
    print(f"MAP counts: visual={sum(1 for o in objs if o.type == 'MESH' and not o.name.startswith('COL_'))} "
          f"COL={len(COLS)} LAMP={len(LAMPS)} tris_unique={tri_total + air_tris + light_tris} "
          f"tris_rendered={shown_tris} airliners={len(air_spots)} hangars={len(BC)} masts={len(LAMPS) // 4}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        for o in objs:
            if o.name.startswith("COL_"):
                o.hide_render = False
        bkit.export_glb(OUT_GLB, objs, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


def setup_world():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    try:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(bkit.polyhaven_hdri("kloofendal_48d_partly_cloudy_puresky", "1k"),
                                         check_existing=True)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    except Exception as e:  # offline
        print("MAP: HDRI unavailable:", e)
        bg.inputs["Color"].default_value = (0.55, 0.6, 0.72, 1)
    bg.inputs["Strength"].default_value = 1.0


def make_camera(name, eye, target, lens=28.0, ortho=None):
    scene = bpy.context.scene
    cd = bpy.data.cameras.new(name)
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.lens = lens
    cd.clip_start = 0.05
    cd.clip_end = 2000.0
    co = bpy.data.objects.new(name, cd)
    scene.collection.objects.link(co)
    e, t = G(eye), G(target)
    co.location = e
    d = Vector(t) - Vector(e)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return co


def render_previews(objs):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "None"
    except Exception as e:  # view transform names differ between Blender versions
        print("MAP: view transform left at default:", e)
    setup_world()
    sun = bkit.sun(elevation=30, azimuth=150, strength=2.6, softness=1.5, color=(1.0, 0.8, 0.62))
    cols = [o for o in objs if o.name.startswith("COL_") or o.name.startswith("LAMP_")]
    for o in cols:
        o.hide_render = True
    wanted = [w.strip() for w in RENDER_LIST.split(",") if w.strip()]
    for name in wanted:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            # 1.7 m high on the taxiway at x=-28, looking down the taxiway toward the terminal
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (-28.0, 1.7, -40.0), (-28.0, 1.5, -130.0), lens=26.0)
        else:
            continue
        scene.camera = cam
        scene.render.filepath = PREVIEWS[name]
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("MAP preview", name, round(time.time() - t0, 1), "s ->", PREVIEWS[name])
        bpy.data.objects.remove(cam)
    bpy.data.objects.remove(sun)
    for o in cols:
        o.hide_render = False


if __name__ == "__main__":
    main()
