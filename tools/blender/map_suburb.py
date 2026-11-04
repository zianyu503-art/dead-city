"""黃昏住宅區 (suburb at dusk) level map for 射擊遊戲, built headless with the blender-modeling skill.

Run from the project root:   blender -b -P tools/blender/map_suburb.py
Writes assets/models/map_suburb.glb and previews to .claude/work/. Same conventions as
map_downtown.py: positions are GAME coordinates (x, y up, z on the ground), turned into
Blender coordinates by G(x, y, z) = (x, -z, y) when each mesh is created.

Gameplay data read by the game (buildCityMap in index.html):
  COL_<n>   axis-aligned box, 3 m tall = a collider (houses, garages, sheds, cars, trees,
            fences, hedges, poles, bins)
  LAMP_<n>  empty at the lamp head = a night light position
  Ground*   ground meshes (roads, sidewalks, lawns, driveways) - they do not cast shadows

Keep clear: the 7 x 4 m rectangle centred at game (56, -59.2) has no map mesh and no COL_,
because the game places its code wall there. The lawn and the sidewalk slab are cut open
there; the asphalt base under it stays.

Env switches (defaults build everything): MAP_RENDER=top,street|none, MAP_EXPORT=0|1,
MAP_SAMPLES=n, MAP_RES=width.
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
TEX_DIR = os.path.join(WORK, "map_suburb_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_suburb.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_suburb_top.png"),
    "street": os.path.join(WORK, "map_suburb_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 23

# ---------------------------------------------------------------- layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # inner block centres (44 m blocks)
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                              # block half size
WALK_H = 0.16                                            # sidewalk top
LAWN = 20.0                                              # lawn half size: 2 m sidewalk inside the kerb
LOT = 12.7                                               # lot pitch inside a block
LAMP_OFFS = (-14.0, 14.0)                                # one lamp every 28 m along a block side
LAMP_INSET = 21.2                                        # pole 0.8 m inside the kerb
START = (-28.0, 0.0)                                     # player start (game), road x=-28
KEEP = (52.5, 59.5, -61.2, -57.2)                        # keep clear: 7 x 4 m centred at (56, -59.2)
KEEP_BLOCK = (56.0, -56.0)                               # the block that holds it

# house dimensions (metres; heights are v above WALK_H)
FOUND = 0.45          # foundation / finished floor
WALL_TOP = 7.0        # eave of the two-storey houses
GAR_H = 3.2           # garage eave
GROUND_WIN = (1.35, 2.85)
UPPER_WIN = (4.55, 6.0)
WIN_W = 1.25
DOOR_TOP = FOUND + 2.1
GAR_DOOR_TOP = FOUND + 2.25
PORCH_D = 1.8
OVER = 0.5            # roof overhang
PITCH = 0.5           # roof slope (rise / run)
HD = 4.0              # house half depth (8 m)

UPV = (0.0, 1.0, 0.0)
MAT = {}
TILE = {}
COLS = []        # (x0, x1, z0, z1, y0, y1) collider boxes
LAMPS = []       # (x, y, z) lamp light positions
LAMP_POLES = []  # (x, z, rot) street lamp posts
OBST = [KEEP]    # (x0, x1, z0, z1) footprints that scenery must keep clear of
HOUSE_BOXES = []  # per house: footprint boxes for the 3 m path check


def G(p):
    """game (x, y, z) -> blender (x, -z, y)"""
    return (p[0], -p[2], p[1])


def vadd(*vs):
    return tuple(sum(c) for c in zip(*vs))


def vmul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vnorm(v):
    ln = math.sqrt(vdot(v, v)) or 1.0
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def v3(p):
    """2-D (x, z) -> 3-D normal/axis (x, 0, z)"""
    return (p[0], 0.0, p[1])


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
# A facade frame is (O, U, N): O = bottom-left corner of the face (game coords,
# O[1] = sidewalk top), U = unit horizontal direction left->right when seen from
# outside, N = outward normal.  u runs along U, v up, t out of the wall.
def P(fr, u, v, t=0.0):
    O, U, N = fr
    return (O[0] + U[0] * u + N[0] * t, O[1] + v, O[2] + U[2] * u + N[2] * t)


def wbox(mb, fr, u0, u1, v0, v1, t0, t1, mat):
    """Box on a facade: u along the face, v up, t from the wall plane outward."""
    _, U, N = fr
    q = lambda u, v, t: P(fr, u, v, t)
    mb.poly([q(u0, v0, t1), q(u1, v0, t1), q(u1, v1, t1), q(u0, v1, t1)], mat, N)
    if t0 > 0.01:
        mb.poly([q(u0, v0, t0), q(u0, v1, t0), q(u1, v1, t0), q(u1, v0, t0)], mat, vmul(N, -1))
    mb.poly([q(u0, v0, t0), q(u0, v0, t1), q(u0, v1, t1), q(u0, v1, t0)], mat, vmul(U, -1))
    mb.poly([q(u1, v0, t0), q(u1, v1, t0), q(u1, v1, t1), q(u1, v0, t1)], mat, U)
    mb.poly([q(u0, v0, t0), q(u1, v0, t0), q(u1, v0, t1), q(u0, v0, t1)], mat, (0, -1, 0))
    mb.poly([q(u0, v1, t0), q(u0, v1, t1), q(u1, v1, t1), q(u1, v1, t0)], mat, (0, 1, 0))


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
    """Lumpy low-poly sphere for tree canopies and hedges."""
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


def rect_at(mb, x0, x1, z0, z1, y, mat):
    mb.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], mat, UPV)


def rect_pieces(x0, x1, z0, z1, hole):
    """The rectangle minus a hole, as up to four rectangles."""
    hx0, hx1, hz0, hz1 = hole
    if hx1 <= x0 or hx0 >= x1 or hz1 <= z0 or hz0 >= z1:
        return [(x0, x1, z0, z1)]
    out = []
    if hz0 > z0:
        out.append((x0, x1, z0, hz0))
    if hz1 < z1:
        out.append((x0, x1, hz1, z1))
    zl, zh = max(z0, hz0), min(z1, hz1)
    if hx0 > x0:
        out.append((x0, hx0, zl, zh))
    if hx1 < x1:
        out.append((hx1, x1, zl, zh))
    return out


def face_frames(cx, cz, hx, hz, y0):
    """The four side walls of a box footprint: (frame, length)."""
    return [
        (((cx - hx, y0, cz + hz), (1, 0, 0), (0, 0, 1)), 2 * hx),
        (((cx + hx, y0, cz - hz), (-1, 0, 0), (0, 0, -1)), 2 * hx),
        (((cx + hx, y0, cz + hz), (0, 0, -1), (1, 0, 0)), 2 * hz),
        (((cx - hx, y0, cz - hz), (0, 0, 1), (-1, 0, 0)), 2 * hz),
    ]


def panel(mb, fr, L, v0, v1, holes, mat):
    """Flat wall piece on facade fr: u in [0, L], v in [v0, v1], minus holes (u0, u1, w0, w1).
    Each row between hole edges is one quad, so walls with many windows stay cheap."""
    N = fr[2]
    ys = sorted({v0, v1} | {h[2] for h in holes} | {h[3] for h in holes})
    for k in range(len(ys) - 1):
        w0, w1 = ys[k], ys[k + 1]
        if w1 - w0 < 1e-6:
            continue
        wc = (w0 + w1) / 2
        blocked = sorted((h[0], h[1]) for h in holes if h[2] < wc < h[3])
        x = 0.0
        for (b0, b1) in blocked + [(L, L)]:
            if b0 > x + 1e-6:
                mb.poly([P(fr, x, w0), P(fr, b0, w0), P(fr, b0, w1), P(fr, x, w1)], mat, N)
            x = max(x, b1)


def opening(mb, fr, u0, u1, w0, w1, d, mat):
    """A recessed opening: white trim reveals from the wall to depth d, then the glass or door."""
    _, U, N = fr
    mb.poly([P(fr, u0, w1), P(fr, u1, w1), P(fr, u1, w1, -d), P(fr, u0, w1, -d)], "frame", vmul(UPV, -1))
    mb.poly([P(fr, u0, w0), P(fr, u0, w0, -d), P(fr, u1, w0, -d), P(fr, u1, w0)], "frame", UPV)
    mb.poly([P(fr, u0, w0), P(fr, u0, w0, -d), P(fr, u0, w1, -d), P(fr, u0, w1)], "frame", U)
    mb.poly([P(fr, u1, w0), P(fr, u1, w1), P(fr, u1, w1, -d), P(fr, u1, w0, -d)], "frame", vmul(U, -1))
    mb.poly([P(fr, u0, w0, -d), P(fr, u1, w0, -d), P(fr, u1, w1, -d), P(fr, u0, w1, -d)], mat, N)


# ---------------------------------------------------------------- materials
# Poly Haven sets (CC0): key -> (asset id, tile size in metres)
PH_SETS = {
    "asphalt": ("asphalt_02", 4.0),
    "sidewalk": ("concrete_pavement", 2.0),
    "grass": ("leafy_grass", 3.0),
    "brick": ("brick_wall_001", 2.0),
    "concrete": ("concrete_wall_004", 3.0),
    "roof": ("tarred_gravel", 3.0),
    "bark": ("bark_brown_02", 1.2),
    "plywood": ("plywood", 1.2),
    "deck": ("wood_floor_deck", 1.5),
    "stucco": ("white_plaster_02", 3.0),     # neutral white base, tinted per house
    "planks": ("wood_planks_grey", 1.6),     # neutral grey base, tinted per house
    "shingle": ("grey_roof_tiles_02", 1.6),  # tinted per house
}
# tinted siding variants: name -> (base set, tint multiplied over the colour map)
SIDING = {
    "stucco_cream": ("stucco", (1.0, 0.93, 0.78)),
    "stucco_sage": ("stucco", (0.80, 0.90, 0.80)),
    "stucco_blue": ("stucco", (0.74, 0.84, 0.96)),
    "stucco_grey": ("stucco", (0.80, 0.80, 0.82)),
    "stucco_white": ("stucco", (1.0, 1.0, 0.98)),
    "plank_tan": ("planks", (1.0, 0.80, 0.58)),
    "plank_grey": ("planks", (0.85, 0.87, 0.90)),
    "plank_brown": ("planks", (0.80, 0.58, 0.42)),
}
LAWN_TINT = (0.62, 0.95, 0.5)   # leafy_grass is leaf litter with grass: tint it toward a green lawn
ROOFS = {  # roof shingle tints
    "shingle_grey": (1.0, 1.0, 1.0),
    "shingle_brown": (0.85, 0.62, 0.48),
    "shingle_slate": (0.72, 0.78, 0.92),
}

CONST = {
    # name: (rgb, roughness, metallic, specular)
    "glass": ((0.05, 0.085, 0.10), 0.04, 0.0, 0.7),
    "dark": ((0.012, 0.012, 0.014), 0.85, 0.0, 0.3),
    "frame": ((0.80, 0.78, 0.74), 0.5, 0.0, 0.5),
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "door": ((0.10, 0.20, 0.16), 0.5, 0.0, 0.5),
    "door_red": ((0.42, 0.08, 0.06), 0.5, 0.0, 0.5),
    "door_navy": ((0.07, 0.10, 0.26), 0.5, 0.0, 0.5),
    "metal_dark": ((0.07, 0.07, 0.08), 0.45, 0.8, 0.5),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0.5),
    "lamp_head": ((0.86, 0.82, 0.66), 0.25, 0.0, 0.6),
    "leaf_a": ((0.10, 0.27, 0.07), 0.8, 0.0, 0.4),
    "leaf_b": ((0.18, 0.33, 0.09), 0.8, 0.0, 0.4),
    "leaf_c": ((0.28, 0.31, 0.11), 0.8, 0.0, 0.4),
    "manhole": ((0.09, 0.09, 0.09), 0.6, 0.7, 0.5),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "glass_car": ((0.04, 0.07, 0.09), 0.05, 0.0, 0.8),
    "burnt": ((0.035, 0.03, 0.028), 0.9, 0.0, 0.3),
    "headlight": ((0.95, 0.92, 0.84), 0.2, 0.0, 0.6),
    "tail": ((0.55, 0.05, 0.04), 0.3, 0.0, 0.5),
    "bin": ((0.10, 0.12, 0.10), 0.5, 0.3, 0.5),
    "hydrant": ((0.66, 0.12, 0.08), 0.5, 0.2, 0.5),
    "debris": ((0.35, 0.33, 0.31), 0.95, 0.0, 0.3),
    "cardboard": ((0.45, 0.33, 0.20), 0.9, 0.0, 0.3),
    "car_red": ((0.50, 0.06, 0.05), 0.32, 0.25, 0.5),
    "car_blue": ((0.07, 0.17, 0.42), 0.32, 0.25, 0.5),
    "car_white": ((0.78, 0.78, 0.76), 0.35, 0.2, 0.5),
    "car_silver": ((0.45, 0.47, 0.50), 0.3, 0.45, 0.5),
    "car_black": ((0.03, 0.03, 0.035), 0.3, 0.3, 0.5),
    "car_green": ((0.13, 0.30, 0.16), 0.35, 0.25, 0.5),
    "car_yellow": ((0.72, 0.52, 0.10), 0.35, 0.2, 0.5),
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
    maps = {}
    for key, (aid, tile) in PH_SETS.items():
        m = bkit.polyhaven_texture(aid, res="1k")
        maps[key] = {k: v for k, v in m.items() if k in ("color", "normal", "roughness")}
        MAT[key] = bkit.pbr_material(key, maps[key], scale=1.0, coords="UV")
        TILE[key] = tile
        print("MAP texture", key, aid, sorted(maps[key]))
    for name, (base, tint) in SIDING.items():
        MAT[name] = bkit.pbr_material(name, maps[base], scale=1.0, tint=tint, coords="UV")
        TILE[name] = PH_SETS[base][1]
    for name, tint in ROOFS.items():
        MAT[name] = bkit.pbr_material(name, maps["shingle"], scale=1.0, tint=tint, coords="UV")
        TILE[name] = PH_SETS["shingle"][1]
    MAT["lawn"] = bkit.pbr_material("lawn", maps["grass"], scale=1.0, tint=LAWN_TINT, coords="UV")
    TILE["lawn"] = PH_SETS["grass"][1]
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
        TILE[name] = 1.0


PAINTS = ["car_red", "car_blue", "car_white", "car_silver", "car_black", "car_green", "car_yellow"]


# ---------------------------------------------------------------- lot helpers
def add_col(x0, x1, z0, z1, h=3.0):
    COLS.append((x0, x1, z0, z1, 0.0, h))


def lw(c, S, F, a, f, y=WALK_H):
    """Lot-local point: a along S (to the right of the house front), f out toward the road."""
    return (c[0] + S[0] * a + F[0] * f, y, c[1] + S[1] * a + F[1] * f)


def local_rect(c, S, F, a0, a1, f0, f1):
    """Axis-aligned footprint (x0, x1, z0, z1) of a lot-local rectangle."""
    pts = [lw(c, S, F, a, f) for a in (a0, a1) for f in (f0, f1)]
    xs = [p[0] for p in pts]
    zs = [p[2] for p in pts]
    return (min(xs), max(xs), min(zs), max(zs))


def free(box, margin=0.0):
    x0, x1, z0, z1 = box
    for (a0, a1, b0, b1) in OBST:
        if x0 < a1 + margin and x1 > a0 - margin and z0 < b1 + margin and z1 > b0 - margin:
            return False
    return True


def reserve(box):
    OBST.append(box)


def footprint(x, z, rot, half_len, half_wid):
    """Axis-aligned footprint for rot 0 (length along z) or pi/2 (length along x)."""
    if abs(math.sin(rot)) < 0.5:
        return (x - half_wid, x + half_wid, z - half_len, z + half_len)
    return (x - half_len, x + half_len, z - half_wid, z + half_wid)


# ---------------------------------------------------------------- roofs
def roof(mb, c, S, F, hw, hd, eave, style, mat, gable_mat, o=OVER):
    """Roof over a box centred on c (2-D), half sizes hw (along S) and hd (along F), eave at v=eave.
    style: side = ridge along S with gable walls on the +-S sides; front = ridge along F;
    hip = four slopes with a short ridge."""
    def W(a, f, v):
        return lw(c, S, F, a, f, WALK_H + v)
    S3, F3 = v3(S), v3(F)
    if style == "side":
        R = eave + PITCH * (hd + o)
        mb.poly([W(-hw - o, hd + o, eave), W(hw + o, hd + o, eave), W(hw + o, 0, R), W(-hw - o, 0, R)],
                mat, vnorm(vadd(F3, vmul(UPV, PITCH))))
        mb.poly([W(-hw - o, -hd - o, eave), W(hw + o, -hd - o, eave), W(hw + o, 0, R), W(-hw - o, 0, R)],
                mat, vnorm(vadd(vmul(F3, -1), vmul(UPV, PITCH))))
        for s in (1, -1):
            mb.poly([W(s * hw, -hd, eave), W(s * hw, hd, eave), W(s * hw, 0, R)], gable_mat, vmul(S3, s))
    elif style == "front":
        R = eave + PITCH * (hw + o)
        mb.poly([W(0, -hd - o, R), W(0, hd + o, R), W(hw + o, hd + o, eave), W(hw + o, -hd - o, eave)],
                mat, vnorm(vadd(S3, vmul(UPV, PITCH))))
        mb.poly([W(0, -hd - o, R), W(0, hd + o, R), W(-hw - o, hd + o, eave), W(-hw - o, -hd - o, eave)],
                mat, vnorm(vadd(vmul(S3, -1), vmul(UPV, PITCH))))
        for s in (1, -1):
            mb.poly([W(-hw, s * hd, eave), W(hw, s * hd, eave), W(0, s * hd, R)], gable_mat, vmul(F3, s))
    else:  # hip
        R = eave + PITCH * (hd + o)
        rh = max(0.5, hw - hd - o)
        mb.poly([W(-hw - o, hd + o, eave), W(hw + o, hd + o, eave), W(rh, 0, R), W(-rh, 0, R)],
                mat, vnorm(vadd(F3, vmul(UPV, PITCH))))
        mb.poly([W(-hw - o, -hd - o, eave), W(hw + o, -hd - o, eave), W(rh, 0, R), W(-rh, 0, R)],
                mat, vnorm(vadd(vmul(F3, -1), vmul(UPV, PITCH))))
        for s in (1, -1):
            mb.poly([W(s * (hw + o), -hd - o, eave), W(s * (hw + o), hd + o, eave), W(s * rh, 0, R)],
                    mat, vnorm(vadd(vmul(S3, s), vmul(UPV, 0.4))))


# ---------------------------------------------------------------- house parts
def face_draw(mb, fr, L, wall, top, wins, door=None, door_mat="door", gdoor=None, rng=None):
    """One facade: siding with its openings, the concrete foundation, window sills, and the
    glass (or dark / boarded) behind each opening. wins = [(u, w0, w1)] window centres."""
    N = fr[2]
    ops = []
    for (u, w0, w1) in wins:
        r = rng.random()
        kind = "dark" if r < 0.06 else ("board" if r < 0.11 else "glass")
        ops.append((u - WIN_W / 2, u + WIN_W / 2, w0, w1, kind))
    if door is not None:
        kind = "board" if rng.random() < 0.07 else door_mat
        ops.append((door - 0.5, door + 0.5, FOUND, DOOR_TOP, kind))
    if gdoor is not None:
        ops.append((gdoor[0], gdoor[1], FOUND, GAR_DOOR_TOP, "garage"))
    panel(mb, fr, L, FOUND, top, [(o[0], o[1], o[2], o[3]) for o in ops], wall)
    panel(mb, fr, L, 0.0, FOUND, [], "concrete")
    for (u0, u1, w0, w1, kind) in ops:
        if kind == "board":   # plywood over the opening, no glass behind
            mb.poly([P(fr, u0 - 0.08, w0 - 0.08, 0.035), P(fr, u1 + 0.08, w0 - 0.08, 0.035),
                     P(fr, u1 + 0.08, w1 + 0.08, 0.035), P(fr, u0 - 0.08, w1 + 0.08, 0.035)], "plywood", N)
        elif kind == "garage":
            opening(mb, fr, u0, u1, w0, w1, 0.04, "paint_white")
        elif kind in ("glass", "dark"):
            opening(mb, fr, u0, u1, w0, w1, 0.2, kind)
            wbox(mb, fr, u0 - 0.1, u1 + 0.1, w0 - 0.1, w0, 0.0, 0.16, "frame")
        else:                 # front door
            opening(mb, fr, u0, u1, w0, w1, 0.12, kind)


def ufrac(fr, t, S):
    """Fraction along face fr for t measured from the -S end of the house."""
    _, U, _ = fr
    return t if (U[0] * S[0] + U[2] * S[1]) > 0 else 1 - t


def build_house(M, c, F, rng, stats):
    """One two-storey American house on a lot: body, optional garage, porch, roof, chimney,
    driveway, car, mailbox, picket fence, hedges, back-yard shed and tree. Returns the boxes
    used for the path check."""
    S = (-F[1], F[0])
    S3, F3 = v3(S), v3(F)
    garage = rng.random() < 0.4
    style = rng.choices(["side", "front", "hip"], weights=[5, 3, 2])[0]
    wall = rng.choice(list(SIDING)) if rng.random() > 0.15 else "brick"
    roof_m = rng.choice(list(ROOFS))
    door_m = rng.choice(["door", "door_red", "door_navy"])
    hw = 3.1 if garage else 4.6
    a_b = -1.6 if garage else 0.0
    bc = lw(c, S, F, a_b, 0.0)
    bc = (bc[0], bc[2])
    hx = abs(S[0]) * hw + abs(F[0]) * HD
    hz = abs(S[1]) * hw + abs(F[1]) * HD
    boxes = [(bc[0] - hx, bc[0] + hx, bc[1] - hz, bc[1] + hz)]
    door_t = 0.3 if garage else 0.5     # door position, from the -S (non-garage) end
    door_a = a_b + (-hw + 2 * hw * door_t)
    mb = M["houses"]

    def wins_for(fr, L, role):
        if role == "front":
            specs = ([(0.78, "g"), (0.78, "u"), (0.3, "u")] if garage
                     else [(0.2, "g"), (0.2, "u"), (0.8, "g"), (0.8, "u")])
        elif role == "back":
            specs = ([(0.5, "g"), (0.5, "u")] if garage
                     else [(0.25, "g"), (0.25, "u"), (0.75, "g"), (0.75, "u")])
        elif role == "minus":
            specs = [(0.5, "g"), (0.5, "u")]
        else:  # plus side: the garage side has no windows
            specs = [] if garage else [(0.5, "g"), (0.5, "u")]
        out = []
        for t, fl in specs:
            w = GROUND_WIN if fl == "g" else UPPER_WIN
            out.append((ufrac(fr, t, S) * L, w[0], w[1]))
        return out

    for fr, L in face_frames(bc[0], bc[1], hx, hz, WALK_H):
        n = fr[2]
        dF = n[0] * F[0] + n[2] * F[1]
        dS = n[0] * S[0] + n[2] * S[1]
        role = "front" if dF > 0.5 else "back" if dF < -0.5 else "plus" if dS > 0.5 else "minus"
        door = ufrac(fr, door_t, S) * L if role == "front" else None
        face_draw(mb, fr, L, wall, WALL_TOP, wins_for(fr, L, role), door=door, door_mat=door_m, rng=rng)
        if role == "front":
            pu0, pu1 = door - 1.6, door + 1.6
            wbox(mb, fr, pu0, pu1, FOUND - 0.15, FOUND, 0.0, PORCH_D, "deck")                 # deck
            wbox(mb, fr, pu0 + 0.5, pu1 - 0.5, 0.0, FOUND - 0.15, PORCH_D, PORCH_D + 0.45, "deck")  # step
            wbox(mb, fr, pu0 - 0.12, pu1 + 0.12, 3.1, 3.3, 0.0, PORCH_D + 0.12, roof_m)        # porch roof
            wbox(mb, fr, pu0 + 0.05, pu0 + 0.25, FOUND, 3.1, PORCH_D - 0.25, PORCH_D - 0.05, "frame")
            wbox(mb, fr, pu1 - 0.25, pu1 - 0.05, FOUND, 3.1, PORCH_D - 0.25, PORCH_D - 0.05, "frame")
            porch = local_rect(c, S, F, door_a - 1.6, door_a + 1.6, HD, HD + PORCH_D + 0.45)
            boxes.append(porch)
            reserve(porch)

    roof(mb, bc, S, F, hw, HD, WALL_TOP, style, roof_m, wall)
    if rng.random() < 0.5:   # brick chimney on the back slope, from inside the roof to 1.2 m above the ridge
        v_lo, v_hi = WALL_TOP + 0.6, WALL_TOP + 2.3 + 1.2
        ctr = lw(c, S, F, a_b + hw * 0.45, -1.2, WALK_H + (v_lo + v_hi) / 2)
        obox(mb, ctr, [S3, UPV, F3], (0.42, (v_hi - v_lo) / 2, 0.42), "brick")

    if garage:
        gc = lw(c, S, F, 3.2, 1.0, 0.0)
        gcx, gcz = gc[0], gc[2]
        ghx = abs(S[0]) * 1.7 + abs(F[0]) * 3.0
        ghz = abs(S[1]) * 1.7 + abs(F[1]) * 3.0
        for fr, L in face_frames(gcx, gcz, ghx, ghz, WALK_H):
            n = fr[2]
            dF = n[0] * F[0] + n[2] * F[1]
            dS = n[0] * S[0] + n[2] * S[1]
            if dS < -0.5:            # shared with the house
                continue
            gd = (0.35, L - 0.35) if dF > 0.5 else None
            face_draw(mb, fr, L, wall, GAR_H, [], gdoor=gd, rng=rng)
        obox(mb, (gcx, WALK_H + GAR_H + 0.12, gcz), [S3, UPV, F3], (1.8, 0.12, 3.1), "roof")
        boxes.append((gcx - ghx, gcx + ghx, gcz - ghz, gcz + ghz))
        add_col(gcx - ghx, gcx + ghx, gcz - ghz, gcz + ghz)
        stats["garages"] += 1
        reserve(boxes[-1])
    add_col(*boxes[0])
    reserve(boxes[0])
    stats["houses"] += 1

    # driveway on the lawn (asphalt), and a car parked on it
    if garage or rng.random() < 0.5:
        a0, a1 = (1.5, 4.9) if garage else (1.6, 4.0)
        drect = local_rect(c, S, F, a0, a1, HD, LAWN - LOT + 1.7)
        rect_at(M["drive"], drect[0], drect[1], drect[2], drect[3], WALK_H + 0.02, "asphalt")
        reserve(drect)
        if rng.random() < (0.35 if garage else 0.15):
            p = lw(c, S, F, 3.2 if garage else 2.8, 6.6, WALK_H + 0.02)
            rot = math.atan2(F[0], F[1])
            car(M["cars"], p[0], p[2], rot, rng.choice(PAINTS), WALK_H + 0.02, False, rng)
            fp = footprint(p[0], p[2], rot, 2.3, 0.95)
            add_col(*fp)
            reserve(fp)
            stats["cars"] += 1

    # mailbox at the lawn edge, picket fence along the front lawn, hedges by the foundation
    mail = lw(c, S, F, -5.6, 6.6)
    mailbox(M["furn"], mail, S3, F3)
    if rng.random() < 0.35:
        a_end = 1.2 if garage or rng.random() < 0.5 else 4.6
        picket_fence(M["fences"], c, S, F, -4.6, a_end, 6.6, rng)
        fb = local_rect(c, S, F, -4.6, a_end, 6.55, 6.65)
        add_col(*fb)
        reserve(fb)
        stats["fences"] += 1
    if rng.random() < 0.5:
        alist = [-3.6, -2.7] if garage else [-3.6, -2.7, 2.7, 3.6]
        hedge(M["green"], c, S, F, alist, 4.6, rng)
        hb = local_rect(c, S, F, min(alist) - 0.8, max(alist) + 0.8, 3.8, 5.4)
        add_col(*hb)

    # back yard: a shed and a tree when they fit clear of everything else
    if rng.random() < 0.3:
        sa = rng.choice([-2.8, 2.8])
        sb = local_rect(c, S, F, sa - 1.2, sa + 1.2, -8.0, -6.0)
        if free(sb, 0.5):
            sp = lw(c, S, F, sa, -7.0, WALK_H + 1.2)
            obox(M["furn"], sp, [S3, UPV, F3], (1.2, 1.2, 1.0), "plywood")
            roof(M["furn"], (sp[0], sp[2]), S, F, 1.2, 1.0, 2.4, "side", "roof", "plywood", o=0.3)
            add_col(*sb)
            reserve(sb)
            stats["sheds"] += 1
    if rng.random() < 0.5:
        for _ in range(8):
            p = lw(c, S, F, rng.uniform(-3.0, 3.0), rng.uniform(-8.6, -6.0))
            cb = (p[0] - 2.2, p[0] + 2.2, p[2] - 2.2, p[2] + 2.2)
            if free(cb, 0.3):
                s = rng.uniform(0.9, 1.1)
                tree(M["green"], p[0], p[2], s, rng)
                add_col(p[0] - 0.3, p[0] + 0.3, p[2] - 0.3, p[2] + 0.3)
                reserve((p[0] - 0.3, p[0] + 0.3, p[2] - 0.3, p[2] + 0.3))
                stats["trees"] += 1
                break
    return boxes


# ---------------------------------------------------------------- street furniture
def car(mb, x, z, rot, paint, y0, wrecked, rng):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    lift = -0.06 if wrecked else 0.0
    base = (x, y0 + lift, z)
    obox(mb, vadd(base, (0, 0.52, 0)), ax, (0.9, 0.24, 2.25), paint)
    obox(mb, vadd(base, (0, 1.08, 0), vmul(f, -0.25)), ax, (0.8, 0.27, 1.2),
         ["glass_car", "glass_car", paint, "dark", "glass_car", "glass_car"])
    for sg in (-1, 1):
        for sf in (-1, 1):
            if wrecked and sg * sf == 1:
                continue
            c = vadd(base, (0, 0.36, 0), vmul(s, 0.8 * sg), vmul(f, 1.45 * sf))
            ocyl(mb, c, s, 0.36, 0.36, 0.26, 10, "tire")
    if not wrecked:
        for sg in (-1, 1):
            obox(mb, vadd(base, (0, 0.66, 0), vmul(f, 2.23), vmul(s, 0.6 * sg)), ax, (0.18, 0.07, 0.04), "headlight")
            obox(mb, vadd(base, (0, 0.66, 0), vmul(f, -2.23), vmul(s, 0.6 * sg)), ax, (0.18, 0.07, 0.04), "tail")


def car_rolled(mb, x, z, rot, paint):
    """A car lying on its side on the road."""
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    obox(mb, (x, 0.95 + 0.012, z), [UPV, s, f], (0.95, 0.72, 2.25), paint)


def car_upside(mb, x, z, rot, paint):
    """A car on its roof on the road."""
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    obox(mb, (x, 0.72 + 0.012, z), [s, UPV, f], (0.95, 0.72, 2.25), paint)


def tree(mb, x, z, s, rng, y0=WALK_H):
    """Suburban tree: a trunk and two lumpy canopy blobs."""
    h = 2.6 * s
    vcyl(mb, x, y0, z, 0.2 * s, 0.13 * s, h, 6, "bark")
    for k in range(2):
        cx = x + rng.uniform(-0.5, 0.5) * s
        cz = z + rng.uniform(-0.5, 0.5) * s
        cy = y0 + h + (0.4 + 0.7 * k) * s
        blob(mb, (cx, cy, cz), rng.uniform(1.4, 1.8) * s, rng.choice(["leaf_a", "leaf_b", "leaf_c"]),
             rng, rings=3, segs=6, sy=0.8)


def hedge(mb, c, S, F, alist, f, rng):
    for a in alist:
        p = lw(c, S, F, a, f, WALK_H + 0.7)
        blob(mb, p, rng.uniform(0.6, 0.75), rng.choice(["leaf_a", "leaf_b", "leaf_c"]), rng,
             rings=2, segs=6, sy=0.8)


def picket_fence(mb, c, S, F, a0, a1, f, rng):
    """White picket fence along the front lawn: flat double-sided pickets and two rails."""
    S3, F3 = v3(S), v3(F)
    a = a0 + 0.2
    while a <= a1 - 0.2:
        pts = [lw(c, S, F, a - 0.05, f, WALK_H + 0.1), lw(c, S, F, a + 0.05, f, WALK_H + 0.1),
               lw(c, S, F, a + 0.05, f, WALK_H + 1.0), lw(c, S, F, a - 0.05, f, WALK_H + 1.0)]
        mb.poly(pts, "paint_white", F3)
        mb.poly(pts, "paint_white", vmul(F3, -1))
        a += 0.36
    for v in (0.4, 0.85):
        m = lw(c, S, F, (a0 + a1) / 2, f, WALK_H + v)
        obox(mb, m, [S3, UPV, F3], ((a1 - a0) / 2, 0.035, 0.03), "paint_white")


def mailbox(mb, p, S3, F3):
    vcyl(mb, p[0], WALK_H, p[2], 0.04, 0.04, 1.05, 6, "metal_dark")
    obox(mb, (p[0], WALK_H + 1.13, p[2]), [S3, UPV, F3], (0.13, 0.11, 0.26), "metal")


def lamp_post(mb, x, z, rot):
    dx, dz = math.sin(rot), math.cos(rot)
    lat = (math.cos(rot), 0.0, -math.sin(rot))
    vcyl(mb, x, WALK_H, z, 0.09, 0.065, 6.84, 8, "metal_dark")
    ax = [(dx, 0.0, dz), UPV, lat]
    obox(mb, (x + dx * 0.78, 6.92, z + dz * 0.78), ax, (0.78, 0.04, 0.04), "metal_dark")
    obox(mb, (x + dx * 1.55, 6.82, z + dz * 1.55), ax, (0.31, 0.06, 0.17), "lamp_head")
    LAMPS.append((x + dx * 1.55, 6.3, z + dz * 1.55))


def bin_(mb, x, z, y0=WALK_H):
    vcyl(mb, x, y0, z, 0.28, 0.25, 0.95, 8, "bin")
    vcyl(mb, x, y0 + 0.95, z, 0.3, 0.3, 0.06, 8, "bin")


def hydrant(mb, x, z, y0=WALK_H):
    vcyl(mb, x, y0, z, 0.13, 0.13, 0.7, 8, "hydrant")
    vcyl(mb, x, y0 + 0.7, z, 0.1, 0.1, 0.08, 8, "hydrant")
    obox(mb, (x, y0 + 0.4, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.2, 0.05, 0.05), "hydrant")


# ---------------------------------------------------------------- blocks
def block_slab(mb, cx, cz, hole=None):
    """Raised sidewalk slab with a kerb face on each side (top cut open at a hole)."""
    h = WALK_H
    x0, x1, z0, z1 = cx - HALF, cx + HALF, cz - HALF, cz + HALF
    tops = [(x0, x1, z0, z1)] if hole is None else rect_pieces(x0, x1, z0, z1, hole)
    for (a, b, c, d) in tops:
        mb.poly([(a, h, c), (b, h, c), (b, h, d), (a, h, d)], "sidewalk", UPV)
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], "concrete", (0, 0, -1))
    mb.poly([(x0, 0, z1), (x0, h, z1), (x1, h, z1), (x1, 0, z1)], "concrete", (0, 0, 1))
    mb.poly([(x0, 0, z0), (x0, h, z0), (x0, h, z1), (x0, 0, z1)], "concrete", (-1, 0, 0))
    mb.poly([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], "concrete", (1, 0, 0))


def lawn(mb, cx, cz, hole=None):
    """Grass lawn inside the 2 m sidewalk strip (cut open at a hole)."""
    pieces = rect_pieces(cx - LAWN, cx + LAWN, cz - LAWN, cz + LAWN, hole) if hole else \
        [(cx - LAWN, cx + LAWN, cz - LAWN, cz + LAWN)]
    for (a, b, c, d) in pieces:
        rect_at(mb, a, b, c, d, WALK_H + 0.012, "lawn")


def block_lamps(cx, cz):
    for off in LAMP_OFFS:
        LAMP_POLES.append((cx + LAMP_INSET, cz + off, math.pi / 2))
        LAMP_POLES.append((cx - LAMP_INSET, cz + off, -math.pi / 2))
        LAMP_POLES.append((cx + off, cz + LAMP_INSET, 0.0))
        LAMP_POLES.append((cx + off, cz - LAMP_INSET, math.pi))


def build_inner_block(M, cx, cz, rng, stats):
    block_lamps(cx, cz)
    # street trees and kerb furniture on the sidewalk strip
    for ex, ez in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for along in (-7.0, 7.0):
            if rng.random() < 0.55:
                x, z = (cx + ex * 20.9, cz + along) if ez == 0 else (cx + along, cz + ez * 20.9)
                tree(M["green"], x, z, rng.uniform(0.9, 1.1), rng)
                add_col(x - 0.3, x + 0.3, z - 0.3, z + 0.3)
                stats["trees"] += 1
        if rng.random() < 0.25:
            along = rng.choice([-17.0, 17.0])
            x, z = (cx + ex * 21.0, cz + along) if ez == 0 else (cx + along, cz + ez * 21.0)
            bin_(M["furn"], x, z)
            add_col(x - 0.3, x + 0.3, z - 0.3, z + 0.3)
        if rng.random() < 0.12:
            along = rng.choice([-19.5, 19.5])
            x, z = (cx + ex * 21.0, cz + along) if ez == 0 else (cx + along, cz + ez * 21.0)
            hydrant(M["furn"], x, z)
            add_col(x - 0.2, x + 0.2, z - 0.2, z + 0.2)
    # the centre lot: three trees, kept off the keep-clear rectangle
    for _ in range(3):
        for _try in range(80):
            x = cx + rng.uniform(-6.5, 6.5)
            z = cz + rng.uniform(-6.5, 6.5)
            if free((x - 2.2, x + 2.2, z - 2.2, z + 2.2), 0.3):
                break
        else:
            continue
        tree(M["green"], x, z, rng.uniform(0.95, 1.2), rng)
        add_col(x - 0.3, x + 0.3, z - 0.3, z + 0.3)
        reserve((x - 0.3, x + 0.3, z - 0.3, z + 0.3))
        stats["trees"] += 1
    # the eight lots
    boxes = []
    for li, lj in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
        c = (cx + li * LOT, cz + lj * LOT)
        if li == 0:
            F = (0.0, float(lj))
        elif lj == 0:
            F = (float(li), 0.0)
        else:
            F = (float(li), 0.0) if rng.random() < 0.5 else (0.0, float(lj))
        boxes.append(build_house(M, c, F, rng, stats))
    # 3 m clear path between houses (footprints incl. garages and porches)
    worst = 99.0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            for a in boxes[i]:
                for b in boxes[j]:
                    gx = max(b[0] - a[1], a[0] - b[1], 0.0)
                    gz = max(b[2] - a[3], a[2] - b[3], 0.0)
                    worst = min(worst, math.hypot(gx, gz))
    stats["min_gap"] = min(stats["min_gap"], worst)
    if worst < 3.0:
        print(f"MAP path warning: block ({cx},{cz}) gap {worst:.2f} m")


def build_ring_block(M, cx, cz, rng, stats):
    """Background block beyond the grid: a few simple houses and trees, no detail."""
    ring_boxes = []
    for dx, dz in ((-9.0, -9.0), (9.0, -9.0), (0.0, 9.0)):
        F = rng.choice([(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)])
        S = (-F[1], F[0])
        hw = rng.choice([4.5, 5.5])
        eave = rng.choice([6.5, 8.5, 10.0])
        c = (cx + dx, cz + dz)
        wall = rng.choice(list(SIDING))
        obox(M["houses"], (c[0], WALK_H + eave / 2, c[1]), [v3(S), UPV, v3(F)], (hw, eave / 2, HD), wall)
        roof(M["houses"], c, S, F, hw, HD, eave, "side", rng.choice(list(ROOFS)), wall)
        hx = abs(S[0]) * hw + abs(F[0]) * HD
        hz = abs(S[1]) * hw + abs(F[1]) * HD
        add_col(c[0] - hx, c[0] + hx, c[1] - hz, c[1] + hz)
        ring_boxes.append((c[0] - hx, c[0] + hx, c[1] - hz, c[1] + hz))
        stats["houses"] += 1
    for _ in range(3):
        for _try in range(40):
            x = cx + rng.uniform(-16, 16)
            z = cz + rng.uniform(-16, 16)
            if all(not (b[0] - 2.2 < x < b[1] + 2.2 and b[2] - 2.2 < z < b[3] + 2.2) for b in ring_boxes):
                break
        tree(M["green"], x, z, rng.uniform(1.0, 1.3), rng)
        add_col(x - 0.3, x + 0.3, z - 0.3, z + 0.3)
        stats["trees"] += 1


def marks(mb, rng):
    """Centre dashes on every road (skipping intersections) and manhole covers in the lanes."""
    for rc in ROADS:
        t = -146.0
        while t < 146.0:
            c = t + 1.5
            if all(abs(c - rd) > 9.0 for rd in ROADS):
                rect_at(mb, rc - 0.08, rc + 0.08, c - 1.5, c + 1.5, 0.012, "paint_white")
                rect_at(mb, c - 1.5, c + 1.5, rc - 0.08, rc + 0.08, 0.012, "paint_white")
            t += 6.0
    cand = 0
    while cand < 18:
        cand += 1
        rc = rng.choice(ROADS)
        p = rng.uniform(-130, 130)
        if rng.random() < 0.5:
            x, z = rc + 3.2, p
        else:
            x, z = p, rc + 3.2
        if math.hypot(x - START[0], z - START[1]) < 14 or any(abs(p - rd) < 9 for rd in ROADS):
            continue
        for k in range(14):
            a0 = 2 * math.pi * k / 14
            a1 = 2 * math.pi * (k + 1) / 14
            mb.poly([(x, 0.013, z), (x + 0.36 * math.cos(a0), 0.013, z + 0.36 * math.sin(a0)),
                     (x + 0.36 * math.cos(a1), 0.013, z + 0.36 * math.sin(a1))], "manhole", UPV)


# ---------------------------------------------------------------- main
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

    print("MAP stage: ground, sidewalks, lawns")
    M = {
        "road": Mesh("Ground_road"),
        "side": Mesh("Ground_sidewalk"),
        "grass": Mesh("Ground_grass"),
        "drive": Mesh("Ground_drive"),
        "marks": Mesh("Ground_markings"),
        "houses": Mesh("Houses"),
        "fences": Mesh("Fences"),
        "green": Mesh("Trees", smooth=True),
        "cars": Mesh("Cars"),
        "furn": Mesh("Furniture"),
        "lamps": Mesh("StreetLamps"),
        "debris": Mesh("Debris"),
    }
    M["road"].poly([(-200, 0, -200), (200, 0, -200), (200, 0, 200), (-200, 0, 200)], "asphalt", UPV)
    ring_blocks = [(x, z) for z in RING_C for x in RING_C if abs(x) == 168 or abs(z) == 168]
    inner_blocks = [(cx, cz) for cz in BC for cx in BC]
    for cx, cz in inner_blocks + ring_blocks:
        hole = KEEP if (cx, cz) == KEEP_BLOCK else None
        block_slab(M["side"], cx, cz, hole)
        lawn(M["grass"], cx, cz, hole)
    marks(M["marks"], rng)

    print("MAP stage: houses, trees, street furniture")
    stats = {"houses": 0, "garages": 0, "trees": 0, "cars": 0, "fences": 0, "sheds": 0, "min_gap": 99.0}
    for cx, cz in inner_blocks:
        build_inner_block(M, cx, cz, rng, stats)
    for cx, cz in ring_blocks:
        build_ring_block(M, cx, cz, rng, stats)
    print(f"MAP path: min house-to-house gap {stats['min_gap']:.2f} m")

    print("MAP stage: wrecks, parked cars, debris, lamps")
    kerb = 0
    cand = []
    for cz in BC:
        for cx in BC:
            cand.append((cx + 23.2, cz + rng.uniform(-12, 12), 0.0))
            cand.append((cx + rng.uniform(-12, 12), cz + 23.2, math.pi / 2))
    rng.shuffle(cand)
    for x, z, r in cand:
        if kerb >= 6:
            break
        if math.hypot(x - START[0], z - START[1]) < 14:
            continue
        if abs(x - START[0]) < 3 and abs(z - START[1]) < 14:
            continue
        if not free((x - 1.0, x + 1.0, z - 2.4, z + 2.4), 0.0):
            continue
        car(M["cars"], x, z, r, rng.choice(PAINTS), 0.0, rng.random() < 0.15, rng)
        fp = footprint(x, z, r, 2.3, 0.95)
        add_col(*fp)
        reserve(fp)
        kerb += 1
    car_rolled(M["cars"], -84.0 + 3.2, -40.0, 0.0, "car_silver")
    add_col(*footprint(-84.0 + 3.2, -40.0, 0.0, 2.3, 0.95))
    car_upside(M["cars"], 28.0 - 3.2, 60.0, 0.0, "car_red")
    add_col(*footprint(28.0 - 3.2, 60.0, 0.0, 2.3, 0.95))
    for _ in range(40):
        rc = rng.choice(ROADS)
        p = rng.uniform(-140, 140)
        if rng.random() < 0.5:
            x, z = rc + rng.uniform(-4, 4), p
        else:
            x, z = p, rc + rng.uniform(-4, 4)
        if math.hypot(x - START[0], z - START[1]) < 10 or abs(x) > 146 or abs(z) > 146:
            continue
        obox(M["debris"], (x, 0.12, z), [(1, 0, 0), UPV, (0, 0, 1)],
             (rng.uniform(0.15, 0.6), 0.1, rng.uniform(0.15, 0.5)), "debris")
    for (x, z, r) in LAMP_POLES:
        lamp_post(M["lamps"], x, z, r)
        add_col(x - 0.15, x + 0.15, z - 0.15, z + 0.15)

    print("MAP stage: build objects")
    order = ["road", "side", "grass", "drive", "marks", "houses", "fences", "green", "cars", "furn",
             "lamps", "debris"]
    objs = []
    for key in order:
        if M[key].faces:
            objs.append(M[key].build(coll))
    visual_tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)

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
    print(f"MAP keep-clear: {keep_violations(objs)} map meshes or COL_ boxes inside {KEEP}")
    print(f"MAP counts: COL={len(COLS)} LAMP={len(LAMPS)} tris={visual_tris + 12} "
          f"houses={stats['houses']} garages={stats['garages']} trees={stats['trees']} "
          f"cars={stats['cars']} fences={stats['fences']} sheds={stats['sheds']} "
          f"lamp_poles={len(LAMP_POLES)}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        for o in objs:
            if o.name.startswith("COL_"):
                o.hide_render = False
        bkit.export_glb(OUT_GLB, objs, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


def keep_violations(objs):
    """Count scenery polygons and COL_ boxes whose footprint reaches into the keep-clear rectangle
    (the asphalt base, Ground_road, is the one mesh allowed there)."""
    x0, x1, z0, z1 = KEEP
    bad = []
    for o in objs:
        if o.name == "Ground_road" or o.name.startswith("LAMP_"):
            continue
        if o.name.startswith("COL_"):
            gx, gz = o.location.x, -o.location.y
            if gx - o.scale.x / 2 < x1 and gx + o.scale.x / 2 > x0 and gz - o.scale.y / 2 < z1 and gz + o.scale.y / 2 > z0:
                bad.append(o.name)
            continue
        verts = o.data.vertices
        for poly in o.data.polygons:
            xs = [verts[i].co.x for i in poly.vertices]
            zs = [-verts[i].co.y for i in poly.vertices]
            if min(xs) < x1 - 1e-3 and max(xs) > x0 + 1e-3 and min(zs) < z1 - 1e-3 and max(zs) > z0 + 1e-3:
                bad.append(o.name)
                break
    if bad:
        print("MAP keep-clear offenders:", sorted(set(bad))[:20])
    return len(bad)


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
        bg.inputs["Color"].default_value = (0.55, 0.65, 0.8, 1)
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
    # dusk light for the previews: low warm sun
    sun = bkit.sun(elevation=24, azimuth=150, strength=2.4, softness=1.5, color=(1.0, 0.84, 0.66))
    cols = [o for o in objs if o.name.startswith("COL_") or o.name.startswith("LAMP_")]
    for o in cols:
        o.hide_render = True
    wanted = [w.strip() for w in RENDER_LIST.split(",") if w.strip()]
    for name in wanted:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (-28.0, 1.7, -28.0), (-28.0, 1.5, -140.0), lens=26.0)
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
