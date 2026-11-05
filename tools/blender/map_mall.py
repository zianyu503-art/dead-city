"""星光購物中心 (starlight mall, snowy night plaza) level map for 射擊遊戲, built headless with the
blender-modeling skill. Same conventions as map_downtown.py (copied and adapted).

Run from the project root:   blender -b -P tools/blender/map_mall.py
Writes assets/models/map_mall.glb and previews to .claude/work/. Compress afterwards with
tools/blender/compress_map.py.

Positions are GAME coordinates (x, y up, z on the ground), turned into Blender coordinates by
G(x, y, z) = (x, -z, y) when each mesh is created, so the glTF export lands back on the game's axes.

Gameplay data read by the game (buildCityMap in index.html):
  COL_<n>   axis-aligned box, 3 m tall = collider (buildings, cars, trunks, kiosks, benches...)
  LAMP_<n>  empty at a street lamp head = a night light position
  Ground*   ground meshes (roads, sidewalks, grass, lots) - they do not cast shadows

Snow: snow roofs, snowbanks along the kerbs, snow on car roofs and tree crowns, tyre tracks on
the lanes. Env switches: MAP_RENDER=top,street|none, MAP_EXPORT=0|1, MAP_SAMPLES=n, MAP_RES=width.
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
TEX_DIR = os.path.join(WORK, "map_mall_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_mall.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_mall_top.png"),
    "street": os.path.join(WORK, "map_mall_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 19

# ---------------------------------------------------------------- city layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # inner block centres
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                              # block half size (44 m slab)
WALK_H = 0.16                                            # sidewalk top
GH = 4.4                                                 # ground floor height
FH = 3.6                                                 # upper floor height
LAMP_OFFS = (-14.0, 0.0, 14.0)                           # lamps every 14 m per block side
LAMP_INSET = 21.2                                        # pole 0.8 m inside the kerb
START = (-28.0, 0.0)                                     # player start (game), road x=-28

# block kinds: row j = z index, column i = x index.  T office tower, Q four corner buildings,
# lot parking lot with snow-covered cars and carts, mall the Starlight mall, cinema, dept store
# (department store), carpark multi-storey car park, park small park, rink park with a skating rink
ROWS = {
    0: ["Q", "T", "Q", "Q", "T"],
    1: ["T", "Q", "carpark", "Q", "Q"],
    2: ["Q", "cinema", "mall", "dept", "T"],
    3: ["T", "lot", "rink", "Q", "Q"],
    4: ["Q", "T", "Q", "T", "Q"],
}

UPV = (0.0, 1.0, 0.0)
MAT = {}
TILE = {}
COLS = []        # (x0, x1, z0, z1) collider boxes, 3 m tall
LAMPS = []       # (x, y, z) lamp light positions
LAMP_POLES = []  # (x, z, rot) street lamp posts
TREE_SPOTS = []  # (x, z, scale) trees (trunk collider each)
CAR_SPOTS = []   # (x, z, rot, paint, wrecked) cars (collider each)


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
    """Lumpy low-poly sphere for tree canopies and bag piles."""
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


def quad_flat(mb, x0, x1, z0, z1, y, mat, n=UPV):
    mb.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], mat, n)


def rect_at(mb, x0, x1, z0, z1, y, mat):
    quad_flat(mb, x0, x1, z0, z1, y, mat)


# ---------------------------------------------------------------- materials
PH_SETS = {
    "asphalt": ("asphalt_snow", 4.0),
    "sidewalk": ("snow_floor", 2.0),
    "grass": ("snow_02", 3.0),
    "brick": ("brick_wall_001", 2.0),
    "concrete": ("concrete_wall_004", 3.0),
    "stone": ("beige_wall_001", 3.0),
    "roof": ("snow_01", 3.0),
    "bark": ("bark_brown_02", 1.2),
    "plywood": ("plywood", 1.2),
    "snowbank": ("snow_03", 1.5),
}

CONST = {
    # name: (rgb, roughness, metallic, specular)
    "glass": ((0.05, 0.085, 0.10), 0.04, 0.0, 0.7),
    "dark": ((0.012, 0.012, 0.014), 0.85, 0.0, 0.3),
    "frame": ((0.80, 0.78, 0.74), 0.5, 0.0, 0.5),
    "frame_dark": ((0.11, 0.11, 0.12), 0.4, 0.5, 0.5),
    "spandrel": ((0.22, 0.22, 0.23), 0.6, 0.0, 0.5),
    "door": ((0.10, 0.20, 0.16), 0.5, 0.0, 0.5),
    "metal_dark": ((0.07, 0.07, 0.08), 0.45, 0.8, 0.5),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0.5),
    "ac": ((0.52, 0.53, 0.55), 0.5, 0.6, 0.5),
    "tank": ((0.42, 0.28, 0.17), 0.6, 0.5, 0.5),
    "lamp_head": ((0.86, 0.82, 0.66), 0.25, 0.0, 0.6),
    "leaf_a": ((0.10, 0.27, 0.07), 0.8, 0.0, 0.4),
    "leaf_b": ((0.18, 0.33, 0.09), 0.8, 0.0, 0.4),
    "leaf_c": ((0.28, 0.31, 0.11), 0.8, 0.0, 0.4),
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "manhole": ((0.09, 0.09, 0.09), 0.6, 0.7, 0.5),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "glass_car": ((0.04, 0.07, 0.09), 0.05, 0.0, 0.8),
    "burnt": ((0.035, 0.03, 0.028), 0.9, 0.0, 0.3),
    "headlight": ((0.95, 0.92, 0.84), 0.2, 0.0, 0.6),
    "tail": ((0.55, 0.05, 0.04), 0.3, 0.0, 0.5),
    "bench_wood": ((0.34, 0.23, 0.13), 0.75, 0.0, 0.4),
    "dumpster": ((0.12, 0.28, 0.17), 0.7, 0.15, 0.4),
    "dumpster_lid": ((0.07, 0.17, 0.10), 0.75, 0.1, 0.4),
    "bin": ((0.10, 0.12, 0.10), 0.5, 0.3, 0.5),
    "hydrant": ((0.66, 0.12, 0.08), 0.5, 0.2, 0.5),
    "cone": ((0.95, 0.38, 0.05), 0.5, 0.0, 0.5),
    "cone_base": ((0.05, 0.05, 0.05), 0.6, 0.0, 0.5),
    "bag": ((0.03, 0.03, 0.035), 0.6, 0.0, 0.4),
    "cardboard": ((0.45, 0.33, 0.20), 0.9, 0.0, 0.3),
    "debris": ((0.35, 0.33, 0.31), 0.95, 0.0, 0.3),
    "awning_red": ((0.48, 0.09, 0.07), 0.9, 0.0, 0.3),
    "awning_green": ((0.07, 0.25, 0.14), 0.9, 0.0, 0.3),
    "awning_cream": ((0.62, 0.56, 0.42), 0.9, 0.0, 0.3),
    "awning_navy": ((0.07, 0.10, 0.25), 0.9, 0.0, 0.3),
    "sign_red": ((0.42, 0.08, 0.06), 0.5, 0.0, 0.5),
    "sign_navy": ((0.07, 0.10, 0.26), 0.5, 0.0, 0.5),
    "sign_green": ((0.07, 0.22, 0.11), 0.5, 0.0, 0.5),
    "sign_ochre": ((0.60, 0.42, 0.10), 0.5, 0.0, 0.5),
    "sign_cream": ((0.66, 0.61, 0.50), 0.5, 0.0, 0.5),
    "sign_dark": ((0.09, 0.09, 0.10), 0.5, 0.0, 0.5),
    "car_red": ((0.50, 0.06, 0.05), 0.32, 0.25, 0.5),
    "car_blue": ((0.07, 0.17, 0.42), 0.32, 0.25, 0.5),
    "car_white": ((0.78, 0.78, 0.76), 0.35, 0.2, 0.5),
    "car_silver": ((0.45, 0.47, 0.50), 0.3, 0.45, 0.5),
    "car_black": ((0.03, 0.03, 0.035), 0.3, 0.3, 0.5),
    "car_green": ((0.13, 0.30, 0.16), 0.35, 0.25, 0.5),
    "car_yellow": ((0.72, 0.52, 0.10), 0.35, 0.2, 0.5),
}


def cmat(name, rgb, rough, metal, spec):
    import bpy as _b
    mat = _b.data.materials.new(name)
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
    for name, (rgb, rough, metal, spec) in list(CONST.items()) + list(MALL_CONST.items()):
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name, (rgb, strength) in EMIT.items():
        MAT[name] = cmat_emit(name, rgb, strength)
    for name in list(CONST) + list(MALL_CONST) + list(EMIT):
        TILE.setdefault(name, 1.0)


PAINTS = ["car_red", "car_blue", "car_white", "car_silver", "car_black", "car_green", "car_yellow"]
SIGNS = ["sign_red", "sign_navy", "sign_green", "sign_ochre", "sign_cream", "sign_dark"]
AWNINGS = ["awning_red", "awning_green", "awning_cream", "awning_navy"]


# ---------------------------------------------------------------- facades
def face_frames(cx, cz, hx, hz, y0):
    """The four side walls of a box footprint: (frame, length)."""
    return [
        (((cx - hx, y0, cz + hz), (1, 0, 0), (0, 0, 1)), 2 * hx),
        (((cx + hx, y0, cz - hz), (-1, 0, 0), (0, 0, -1)), 2 * hx),
        (((cx + hx, y0, cz + hz), (0, 0, -1), (1, 0, 0)), 2 * hz),
        (((cx - hx, y0, cz - hz), (0, 0, 1), (-1, 0, 0)), 2 * hz),
    ]


def wall_face(mb, fr, L, H, st, rng):
    """One facade: recessed ground floor and storefronts, recessed window openings in the
    lower floors, flat inset windows above, ledges, pilasters, fire escape, awning."""
    _, U, N = fr
    bays = st["bays"]
    b = L / bays
    nf = st["nf"]
    bf = min(st["bf"], nf)
    band_top = min(H, GH + bf * FH)
    holes = []    # (u0, u1, v0, v1, depth, kind)
    decals = []   # (u0, u1, v0, v1, kind) flat windows and the door
    plates = []   # boarded storefronts (plywood over the wall)
    door = st.get("door", -1)
    mids = []
    band = st["band"]
    for i in range(bays):
        u0, u1 = i * b, (i + 1) * b
        if i == door:
            mid = (u0 + u1) / 2
            holes.append((u0 + 0.2, mid - 0.7, 0.35, GH - 0.9, 0.5, "glass"))
            holes.append((mid + 0.7, u1 - 0.2, 0.35, GH - 0.9, 0.5, "glass"))
            decals.append((mid - 0.5, mid + 0.5, 0.0, 2.4, "door"))
            continue
        hole = (u0 + 0.2, u1 - 0.2, 0.35, GH - 0.9)
        r = rng.random()
        if r < 0.14:
            plates.append(hole)
        elif r < 0.24:
            holes.append((*hole, 0.5, "dark"))
            mids.append(((u0 + u1) / 2, hole))
        else:
            holes.append((*hole, 0.5, "glass"))
            mids.append(((u0 + u1) / 2, hole))
    ww, wh, sill = st["win_w"], st["win_h"], 0.9
    for k in range(bf):
        base = GH + k * FH
        for i in range(bays):
            uc = (i + 0.5) * b
            v0 = base + sill
            kind = "dark" if rng.random() < 0.08 else "glass"
            holes.append((uc - ww / 2, uc + ww / 2, v0, v0 + wh, 0.3, kind))
    for k in range(bf, nf):
        base = GH + k * FH
        for i in range(bays):
            uc = (i + 0.5) * b
            v0 = base + sill
            kind = "dark" if rng.random() < 0.08 else "glass"
            if st.get("decal", True):
                decals.append((uc - ww / 2, uc + ww / 2, v0, v0 + wh, kind))

    # wall with holes: a grid over the band, skipping the openings
    us = sorted({0.0, L} | {h[0] for h in holes} | {h[1] for h in holes})
    vs = sorted({0.0, band_top} | {h[2] for h in holes} | {h[3] for h in holes})
    for a in range(len(us) - 1):
        for c in range(len(vs) - 1):
            u0, u1, v0, v1 = us[a], us[a + 1], vs[c], vs[c + 1]
            cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
            if any(h[0] < cu < h[1] and h[2] < cv < h[3] for h in holes):
                continue
            mb.poly([P(fr, u0, v0), P(fr, u1, v0), P(fr, u1, v1), P(fr, u0, v1)], band, N)
    # upper wall
    if H > band_top + 1e-6:
        mb.poly([P(fr, 0, band_top), P(fr, L, band_top), P(fr, L, H), P(fr, 0, H)], st["upper"], N)

    # reveals and the glass or dark interior behind each opening
    for (u0, u1, v0, v1, d, kind) in holes:
        if d > 0:
            mb.poly([P(fr, u0, v1, 0), P(fr, u1, v1, 0), P(fr, u1, v1, -d), P(fr, u0, v1, -d)], band, vmul(UPV, -1))
            mb.poly([P(fr, u0, v0, 0), P(fr, u0, v0, -d), P(fr, u1, v0, -d), P(fr, u1, v0, 0)], band, UPV)
            mb.poly([P(fr, u0, v0, 0), P(fr, u0, v0, -d), P(fr, u0, v1, -d), P(fr, u0, v1, 0)], band, U)
            mb.poly([P(fr, u1, v0, 0), P(fr, u1, v1, 0), P(fr, u1, v1, -d), P(fr, u1, v0, -d)], band, vmul(U, -1))
        gm = "glass" if kind == "glass" else "dark"
        mb.poly([P(fr, u0, v0, -d), P(fr, u1, v0, -d), P(fr, u1, v1, -d), P(fr, u0, v1, -d)], gm, N)
        if d == 0.3:  # window sill
            wbox(mb, fr, u0 - 0.12, u1 + 0.12, v0 - 0.12, v0, 0.0, 0.14, band)
    # storefront mullions
    for mid, (u0, u1, v0, v1) in mids:
        wbox(mb, fr, mid - 0.05, mid + 0.05, v0, v1, 0.0, 0.1, "frame")
    # boarded storefronts: plywood sheets over the glass
    for (u0, u1, v0, v1) in plates:
        mb.poly([P(fr, u0 - 0.05, v0 - 0.05, 0.03), P(fr, u1 + 0.05, v0 - 0.05, 0.03),
                 P(fr, u1 + 0.05, v1 + 0.05, 0.03), P(fr, u0 - 0.05, v1 + 0.05, 0.03)], "plywood", N)
    # flat windows and door on the upper wall
    for (u0, u1, v0, v1, kind) in decals:
        if kind == "door":
            mb.poly([P(fr, u0, v0, 0.03), P(fr, u1, v0, 0.03), P(fr, u1, v1, 0.03), P(fr, u0, v1, 0.03)], "door", N)
            continue
        mb.poly([P(fr, u0 - 0.06, v0 - 0.06, 0.02), P(fr, u1 + 0.06, v0 - 0.06, 0.02),
                 P(fr, u1 + 0.06, v1 + 0.06, 0.02), P(fr, u0 - 0.06, v1 + 0.06, 0.02)], "frame", N)
        gm = "glass" if kind == "glass" else "dark"
        mb.poly([P(fr, u0, v0, 0.035), P(fr, u1, v0, 0.035), P(fr, u1, v1, 0.035), P(fr, u0, v1, 0.035)], gm, N)

    # sign band over the shops, awnings
    wbox(mb, fr, 0.15, L - 0.15, GH - 0.85, GH - 0.12, 0.0, 0.22, st["sign"])
    if st.get("awning"):
        for (u0, u1, v0, v1, _d, _k) in [h for h in holes if h[5] == "glass" and h[2] < 0.5][:2]:
            mb.poly([P(fr, u0 - 0.1, 3.45, 0.0), P(fr, u1 + 0.1, 3.45, 0.0),
                     P(fr, u1 + 0.1, 3.0, 0.95), P(fr, u0 - 0.1, 3.0, 0.95)],
                    st["awning"], vnorm(vadd(N, UPV)))
    # belt courses
    if st.get("belts"):
        for k in range(4, nf, 4):
            v = GH + k * FH
            wbox(mb, fr, -0.1, L + 0.1, v - 0.14, v + 0.14, 0.0, 0.2, band)
    # curtain walls: mullions and spandrels
    if st.get("curtain"):
        for i in range(bays + 1):
            ui = i * b
            wbox(mb, fr, ui - 0.05, ui + 0.05, band_top, H, 0.0, 0.14, "frame_dark")
        for k in range(1, nf + 1, st.get("spand_every", 1)):
            v = GH + k * FH
            wbox(mb, fr, 0.0, L, v - 0.9, v, 0.0, 0.12, "spandrel")
    # corner pilasters give the building edges a catch-light
    if st.get("pilaster"):
        wbox(mb, fr, 0.0, 0.45, 0.0, H, 0.0, 0.2, st["upper"] if st["upper"] != "glass" else band)
        wbox(mb, fr, L - 0.45, L, 0.0, H, 0.0, 0.2, st["upper"] if st["upper"] != "glass" else band)
    # fire escape
    fi = st.get("fire", -1)
    if fi >= 0:
        uc = (fi + 0.5) * b
        for k in range(1, nf):
            y = GH + k * FH
            wbox(mb, fr, uc - 0.85, uc + 0.85, y - 0.1, y, 0.0, 1.0, "metal_dark")
            wbox(mb, fr, uc - 0.85, uc + 0.85, y + 0.92, y + 1.0, 0.92, 1.0, "metal_dark")
            wbox(mb, fr, uc - 0.87, uc - 0.83, y, y + 1.0, 0.0, 1.0, "metal_dark")
            wbox(mb, fr, uc + 0.83, uc + 0.87, y, y + 1.0, 0.0, 1.0, "metal_dark")
            if k < nf - 1:
                a0 = vnorm(vadd(vmul(U, -1.2), vmul(UPV, FH)))
                cen = P(fr, uc, y + FH / 2, 0.5)
                obox(mb, cen, [a0, N, vnorm(vcross(a0, N))], (1.85, 0.42, 0.05), "metal_dark")


def roof_and_top(mb, cx, cz, hx, hz, H, st, rng, parapet_mat, cornice=True):
    """Cornice, parapet and flat roof; H is the height above the sidewalk top."""
    y0 = WALK_H
    for fr, L in face_frames(cx, cz, hx, hz, y0):
        if cornice:
            wbox(mb, fr, -0.2, L + 0.2, H - 0.7, H, 0.0, 0.42, "concrete" if st["kind"] != "brick" else "concrete")
        wbox(mb, fr, 0.0, L, H, H + 0.9, 0.0, 0.22, parapet_mat)
        wbox(mb, fr, -0.04, L + 0.04, H + 0.9, H + 1.05, -0.03, 0.26, "snow_cap")
    mb.poly([(cx - hx, y0 + H, cz - hz), (cx + hx, y0 + H, cz - hz),
             (cx + hx, y0 + H, cz + hz), (cx - hx, y0 + H, cz + hz)], "roof", UPV)


def rooftop(mb, cx, cz, hx, hz, H, rng, tower=False):
    y = WALK_H + H
    for _ in range(rng.randint(1, 3)):
        x = cx + rng.uniform(-hx * 0.55, hx * 0.55)
        z = cz + rng.uniform(-hz * 0.55, hz * 0.55)
        obox(mb, (x, y + 0.55, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.85, 0.55, 0.6), "ac")
    if rng.random() < 0.45 and min(hx, hz) > 6:
        x = cx + rng.uniform(-hx * 0.4, hx * 0.4)
        z = cz + rng.uniform(-hz * 0.4, hz * 0.4)
        for sx in (-0.7, 0.7):
            for sz in (-0.7, 0.7):
                obox(mb, (x + sx, y + 0.8, z + sz), [(1, 0, 0), UPV, (0, 0, 1)], (0.07, 0.8, 0.07), "metal")
        vcyl(mb, x, y + 1.6, z, 1.0, 1.0, 2.0, 10, "tank")
    if tower or rng.random() < 0.3:
        x = cx + rng.uniform(-hx * 0.5, hx * 0.5)
        z = cz + rng.uniform(-hz * 0.5, hz * 0.5)
        vcyl(mb, x, y, z, 0.05, 0.03, 6.0 if tower else 3.0, 6, "metal_dark")
    for _ in range(rng.randint(0, 2)):
        x = cx + rng.uniform(-hx * 0.6, hx * 0.6)
        z = cz + rng.uniform(-hz * 0.6, hz * 0.6)
        vcyl(mb, x, y, z, 0.16, 0.16, 0.9, 8, "metal")


def building(mb_name, cx, cz, W, D, H, kind, rng, fire_face=-1, facade=None):
    """One building: shell, storefronts, windows, roof and rooftop clutter.
    Returns the Mesh; H is the height above the sidewalk top."""
    mb = Mesh(mb_name)
    hx, hz = W / 2, D / 2
    frames = face_frames(cx, cz, hx, hz, WALK_H)
    nf = max(1, round((H - GH) / FH))
    H = GH + nf * FH
    for fi, (fr, L) in enumerate(frames):
        bay_w = {"brick": 3.4, "office": 3.5, "curtain": 4.0, "ring": 6.0}[kind]
        bays = max(2, round(L / bay_w))
        if kind == "brick":
            st = {"band": "brick", "upper": "brick", "bf": 2, "win_w": 1.5, "win_h": 1.7}
        elif kind == "office":
            st = {"band": "concrete", "upper": "concrete", "bf": 2, "win_w": 1.9, "win_h": 2.2}
        else:
            st = {"band": "concrete", "upper": "glass", "bf": 0, "win_w": 1.9, "win_h": 2.2,
                  "curtain": True, "spand_every": 1 if kind == "curtain" else 4, "decal": False}
        st.update({"bays": bays, "nf": nf, "kind": kind, "sign": rng.choice(SIGNS),
                   "door": rng.randrange(bays) if rng.random() < 0.6 else -1,
                   "awning": rng.choice(AWNINGS) if rng.random() < 0.5 else None,
                   "belts": kind in ("office", "brick", "ring"),
                   "pilaster": kind in ("brick", "office"),
                   "fire": (bays - 1) if fi == fire_face else -1})
        wall_face(mb, fr, L, H, st, rng)
    if kind == "brick":
        parapet = "brick"
    elif kind == "office":
        parapet = "concrete"
    else:
        parapet = "frame_dark"
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": kind}, rng, parapet)
    rooftop(mb, cx, cz, hx, hz, H, rng, tower=(kind == "curtain" and W > 30))
    return mb, H


def add_col(x0, x1, z0, z1, h=3.0):
    COLS.append((x0, x1, z0, z1, 0.0, h))


# ---------------------------------------------------------------- street furniture
def footprint(x, z, rot, half_len, half_wid):
    """Axis-aligned footprint for rot 0 (length along z) or pi/2 (length along x)."""
    if abs(math.sin(rot)) < 0.5:
        return (x - half_wid, x + half_wid, z - half_len, z + half_len)
    return (x - half_len, x + half_len, z - half_wid, z + half_wid)


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
    if not wrecked:
        obox(mb, vadd(base, (0, 1.37, 0), vmul(f, -0.25)), ax, (0.74, 0.03, 1.1), "snow_cap")
        obox(mb, vadd(base, (0, 0.79, 0), vmul(f, 1.55)), ax, (0.8, 0.02, 0.5), "snow_cap")


def bench(mb, x, z, rot, y0=WALK_H):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    obox(mb, (x, y0 + 0.45, z), ax, (0.9, 0.04, 0.22), "bench_wood")
    obox(mb, (x, y0 + 0.44, z), ax, (0.9, 0.035, 0.22), "bench_wood")
    obox(mb, vadd((x, y0 + 0.85, z), vmul(f, -0.22)), ax, (0.9, 0.3, 0.03), "bench_wood")
    for sg in (-1, 1):
        obox(mb, (x + s[0] * 0.75 * sg, y0 + 0.22, z + s[2] * 0.75 * sg), ax, (0.04, 0.22, 0.2), "metal_dark")


def dumpster(mb, x, z, rot, y0=WALK_H):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    obox(mb, (x, y0 + 0.55, z), ax, (0.6, 0.55, 1.2), "dumpster")
    obox(mb, (x, y0 + 1.12, z), ax, (0.63, 0.04, 1.22), "dumpster_lid")


def barrier(mb, x, z, rot, y0=WALK_H):
    """Concrete jersey barrier, 3 m long, trapezoid profile."""
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


def cone(mb, x, z, y0=0.0):
    ocyl(mb, (x, y0 + 0.36, z), (0, 1, 0), 0.2, 0.03, 0.7, 8, "cone")
    obox(mb, (x, y0 + 0.015, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.21, 0.015, 0.21), "cone_base")


def hydrant(mb, x, z, y0=WALK_H):
    vcyl(mb, x, y0, z, 0.13, 0.13, 0.7, 8, "hydrant")
    vcyl(mb, x, y0 + 0.7, z, 0.1, 0.1, 0.08, 8, "hydrant")
    obox(mb, (x, y0 + 0.4, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.2, 0.05, 0.05), "hydrant")


def bin_(mb, x, z, y0=WALK_H):
    vcyl(mb, x, y0, z, 0.28, 0.25, 0.95, 8, "bin")
    vcyl(mb, x, y0 + 0.95, z, 0.3, 0.3, 0.06, 8, "bin")


def tree(mb, x, z, s, rng, y0=WALK_H):
    h = 3.4 * s
    vcyl(mb, x, y0, z, 0.24 * s, 0.15 * s, h, 7, "bark")
    for _ in range(3):
        cx = x + rng.uniform(-0.9, 0.9) * s
        cz = z + rng.uniform(-0.9, 0.9) * s
        cy = y0 + h + rng.uniform(0.2, 1.3) * s
        rr = rng.uniform(1.3, 1.8) * s
        blob(mb, (cx, cy, cz), rr, rng.choice(["leaf_a", "leaf_b", "leaf_c"]), rng)
        blob(mb, (cx, cy + rr * 0.6, cz), rr * 0.6, "snow_cap", rng, rings=2, segs=5, sy=0.35)


def lamp_post(mb, x, z, rot):
    dx, dz = math.sin(rot), math.cos(rot)
    lat = (math.cos(rot), 0.0, -math.sin(rot))
    vcyl(mb, x, WALK_H, z, 0.09, 0.065, 6.84, 8, "metal_dark")
    ax = [(dx, 0.0, dz), UPV, lat]
    obox(mb, (x + dx * 0.78, 6.92, z + dz * 0.78), ax, (0.78, 0.04, 0.04), "metal_dark")
    obox(mb, (x + dx * 1.55, 6.82, z + dz * 1.55), ax, (0.31, 0.06, 0.17), "lamp_head")
    LAMPS.append((x + dx * 1.55, 6.3, z + dz * 1.55))


# ---------------------------------------------------------------- blocks
def block_slab(mb, cx, cz):
    """Raised sidewalk slab with a kerb face on each side."""
    h = WALK_H
    x0, x1, z0, z1 = cx - HALF, cx + HALF, cz - HALF, cz + HALF
    mb.poly([(x0, h, z0), (x1, h, z0), (x1, h, z1), (x0, h, z1)], "sidewalk", UPV)
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], "concrete", (0, 0, -1))
    mb.poly([(x0, 0, z1), (x0, h, z1), (x1, h, z1), (x1, 0, z1)], "concrete", (0, 0, 1))
    mb.poly([(x0, 0, z0), (x0, h, z0), (x0, h, z1), (x0, 0, z1)], "concrete", (-1, 0, 0))
    mb.poly([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], "concrete", (1, 0, 0))


def block_lamps(cx, cz):
    for off in LAMP_OFFS:
        LAMP_POLES.append((cx + LAMP_INSET, cz + off, math.pi / 2))
        LAMP_POLES.append((cx - LAMP_INSET, cz + off, -math.pi / 2))
        LAMP_POLES.append((cx + off, cz + LAMP_INSET, 0.0))
        LAMP_POLES.append((cx + off, cz - LAMP_INSET, math.pi))


def build_lot(gl, cx, cz, rng, furn, cars_mb):
    """Parking lot: asphalt over the slab, two rows of parked cars, stall lines."""
    rect_at(gl, cx - 18, cx + 18, cz - 18, cz + 18, WALK_H + 0.012, "asphalt")
    for row_z in (cz - 8, cz + 8):
        for k in range(9):
            x = cx - 12 + 3.0 * k
            for lx in (x - 1.5,):
                rect_at(gl, lx - 0.06, lx + 0.06, row_z - 2.5, row_z + 2.5, WALK_H + 0.02, "paint_white")
            if rng.random() < 0.38:
                wrecked = rng.random() < 0.12
                car(cars_mb, x, row_z, 0.0, rng.choice(PAINTS) if not wrecked else "burnt", WALK_H + 0.012, wrecked, rng)
                CAR_SPOTS.append((x, row_z, 0.0, wrecked))
                COLS.append(footprint_col(x, row_z, 0.0, 2.3, 0.95))
    for k in range(3):
        for sx, sz in ((-1, -1), (1, 1), (-1, 1)):
            cone(furn, cx + sx * 16.0 + k * 0.5, cz + sz * 16.0, WALK_H + 0.012)


def footprint_col(x, z, rot, half_len, half_wid):
    x0, x1, z0, z1 = footprint(x, z, rot, half_len, half_wid)
    return (x0, x1, z0, z1, 0.0, 3.0)



# ================================================================ mall palette and helpers
from mathutils import Matrix  # noqa: E402

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
# 星光購物中心: 32 x 34 m, three storeys, entrance on the west face toward the plaza
MALL = dict(cx=3.0, cz=0.0, hx=16.0, hz=17.0, gh=5.2, fh=4.2, nf=2)
GLYPHS = {"P": ["1111.", "1...1", "1111.", "1....", "1...."]}
GARLANDS = []    # (p0, p1) game points of festive bulb strings between lamp heads
SIGN_OBJS = []   # 3D lettering (Blender text converted to mesh)
_FONTS = []

MALL_CONST = {
    # name: (rgb, roughness, metallic, specular)
    "snow_cap": ((0.90, 0.93, 0.99), 0.7, 0.0, 0.5),
    "fir": ((0.05, 0.16, 0.08), 0.75, 0.0, 0.4),
    "orn_red": ((0.60, 0.04, 0.04), 0.3, 0.4, 0.6),
    "orn_gold": ((0.85, 0.62, 0.18), 0.25, 0.9, 0.6),
    "orn_blue": ((0.06, 0.18, 0.60), 0.3, 0.4, 0.6),
    "orn_white": ((0.92, 0.92, 0.90), 0.3, 0.0, 0.6),
    "ice": ((0.62, 0.78, 0.90), 0.05, 0.0, 0.8),
    "rink_board": ((0.88, 0.89, 0.92), 0.4, 0.0, 0.5),
    "track": ((0.27, 0.27, 0.29), 0.9, 0.0, 0.3),
    "interior_warm": ((0.80, 0.50, 0.26), 0.6, 0.0, 0.4),
    "cart_wire": ((0.42, 0.43, 0.46), 0.45, 0.85, 0.5),
    "kiosk_red": ((0.55, 0.08, 0.07), 0.6, 0.0, 0.5),
    "sign_board": ((0.05, 0.08, 0.20), 0.4, 0.0, 0.5),
    "letter_white": ((0.90, 0.90, 0.88), 0.4, 0.0, 0.5),
}
EMIT = {
    # name: (rgb, emission strength) - lit signs and festive bulbs
    "sign_lit": ((1.0, 0.78, 0.38), 2.0),
    "sign_lit_red": ((1.0, 0.20, 0.14), 2.0),
    "bulb_red": ((1.0, 0.12, 0.08), 3.0),
    "bulb_green": ((0.15, 1.0, 0.30), 3.0),
    "bulb_gold": ((1.0, 0.80, 0.35), 3.0),
    "bulb_blue": ((0.25, 0.55, 1.0), 3.0),
}


def cmat_emit(name, rgb, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Emission Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def font():
    if not _FONTS:
        _FONTS.append(bpy.data.fonts.load(FONT_PATH))
    return _FONTS[0]


def sign_text(name, text, mat, centre, U, width, depth=0.14):
    """3D lettering on a facade. The text reads along the game vector U as seen from outside
    the wall and stands out along N = U x up. centre is a game point on the wall plane.
    Blender text is converted to a mesh so it exports with the map."""
    cu = bpy.data.curves.new(name + "_txt", "FONT")
    cu.body = text
    cu.font = font()
    cu.size = 1.0
    cu.extrude = depth
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 1
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    view = bpy.context.view_layer
    for o in view.objects:
        o.select_set(False)
    view.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob.select_set(False)
    s = width / ob.dimensions.x
    X = Vector(G(U)).normalized()
    Y = Vector((0.0, 0.0, 1.0))
    Z = X.cross(Y)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Matrix((X, Y, Z)).transposed().to_quaternion()
    ob.scale = (s, s, s)
    ob.location = G(centre)
    ob.data.materials.append(MAT[mat])
    SIGN_OBJS.append(ob)
    return ob


def face_panel(mb, fr, L, v0, v1, holes, mat):
    """A flat wall band from v0 to v1 with rectangular openings. A hole is
    (u0, u1, hv0, hv1, depth, backing): backing is the material of the glass or warm
    interior behind it, None = see-through. depth > 0 adds reveals."""
    _, U, N = fr
    us = sorted({0.0, L} | {h[0] for h in holes} | {h[1] for h in holes})
    vs = sorted({v0, v1} | {h[2] for h in holes} | {h[3] for h in holes})
    for a in range(len(us) - 1):
        for c in range(len(vs) - 1):
            u0, u1, w0, w1 = us[a], us[a + 1], vs[c], vs[c + 1]
            cu, cv = (u0 + u1) / 2, (w0 + w1) / 2
            if any(h[0] < cu < h[1] and h[2] < cv < h[3] for h in holes):
                continue
            mb.poly([P(fr, u0, w0), P(fr, u1, w0), P(fr, u1, w1), P(fr, u0, w1)], mat, N)
    for (u0, u1, w0, w1, d, back) in holes:
        if back is None:
            continue
        if d > 0:
            mb.poly([P(fr, u0, w1, 0), P(fr, u1, w1, 0), P(fr, u1, w1, -d), P(fr, u0, w1, -d)], mat, vmul(UPV, -1))
            mb.poly([P(fr, u0, w0, 0), P(fr, u0, w0, -d), P(fr, u1, w0, -d), P(fr, u1, w0, 0)], mat, UPV)
            mb.poly([P(fr, u0, w0, 0), P(fr, u0, w0, -d), P(fr, u0, w1, -d), P(fr, u0, w1, 0)], mat, U)
            mb.poly([P(fr, u1, w0, 0), P(fr, u1, w1, 0), P(fr, u1, w1, -d), P(fr, u1, w0, -d)], mat, vmul(U, -1))
        mb.poly([P(fr, u0, w0, -d), P(fr, u1, w0, -d), P(fr, u1, w1, -d), P(fr, u0, w1, -d)], back, N)


def storefront_face(mb, fr, L, gh, fh, nf, rng, bay_g=4.0, bay_u=2.8):
    """Ground floor: glazed storefronts, about 40% with warm display interiors. Upper floors:
    a glass curtain wall with frame mullions and floor belts. Pilasters at both ends."""
    H = gh + nf * fh
    bg = max(3, round(L / bay_g))
    bw = L / bg
    ground = []
    for i in range(bg):
        u0 = i * bw + 0.3
        u1 = (i + 1) * bw - 0.3
        back = "interior_warm" if rng.random() < 0.4 else "glass"
        ground.append((u0, u1, 0.9, gh - 0.55, 0.35, back))
    face_panel(mb, fr, L, 0.0, gh, ground, "concrete")
    for i in range(1, bg):
        b = i * bw
        wbox(mb, fr, b - 0.07, b + 0.07, 0.9, gh - 0.55, 0.0, 0.16, "frame")
    bu = max(3, round(L / bay_u))
    wu = L / bu
    upper = []
    for k in range(nf):
        base = gh + k * fh
        for i in range(bu):
            upper.append((i * wu + 0.2, (i + 1) * wu - 0.2, base + 0.5, base + fh - 0.4, 0.25, "glass"))
    face_panel(mb, fr, L, gh, H, upper, "frame_dark")
    for k in range(nf + 1):
        v = gh + k * fh
        wbox(mb, fr, -0.12, L + 0.12, v - 0.14, v + 0.14, 0.0, 0.26, "concrete")
    wbox(mb, fr, 0.0, 0.5, 0.0, H, 0.0, 0.22, "concrete")
    wbox(mb, fr, L - 0.5, L, 0.0, H, 0.0, 0.22, "concrete")


def kiosk(mb, x, z, y0=WALK_H):
    """Snack kiosk with a serving hatch and a snow roof. Collider 3 m tall."""
    ax = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    obox(mb, (x, y0 + 1.35, z), ax, (1.5, 1.35, 1.1), "kiosk_red")
    obox(mb, (x, y0 + 1.2, z + 1.12), ax, (1.1, 0.5, 0.02), "glass")
    obox(mb, (x, y0 + 2.78, z), ax, (1.65, 0.08, 1.25), "snow_cap")
    COLS.append((x - 1.5, x + 1.5, z - 1.1, z + 1.1, 0.0, 3.0))


def bus_stop(mb, x, z, y0=WALK_H):
    """Bus shelter along the kerb (long side along z), glass screen, bench, route sign."""
    ax = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    for px in (x - 0.7, x + 0.7):
        for pz in (z - 1.6, z + 1.6):
            vcyl(mb, px, y0, pz, 0.04, 0.04, 2.4, 6, "metal_dark")
    obox(mb, (x, y0 + 2.5, z), ax, (0.85, 0.05, 1.85), "metal_dark")
    obox(mb, (x, y0 + 2.57, z), ax, (0.82, 0.03, 1.8), "snow_cap")
    obox(mb, (x - 0.7, y0 + 1.25, z), ax, (0.03, 0.85, 1.6), "glass")
    bench(mb, x + 0.2, z, math.pi / 2, y0)
    vcyl(mb, x + 1.0, y0, z + 2.1, 0.04, 0.04, 2.9, 6, "metal_dark")
    obox(mb, (x + 1.0, y0 + 2.95, z + 2.1), ax, (0.02, 0.25, 0.25), "sign_lit")
    COLS.append((x - 0.9, x + 0.9, z - 1.8, z + 1.8, 0.0, 3.0))


def christmas_tree(mb, x, z, rng, y0=WALK_H):
    """Giant fir on a stone planter: five stacked cones, a gold star, ~70 bauble clusters."""
    vcyl(mb, x, y0, z, 1.9, 1.75, 0.6, 16, "stone")
    tiers = [(0.6, 3.2, 3.0), (2.4, 2.6, 2.8), (4.0, 2.0, 2.6), (5.4, 1.4, 2.3), (6.6, 0.85, 2.1)]
    for (yb, R, h) in tiers:
        ocyl(mb, (x, y0 + yb + h / 2, z), (0.0, 1.0, 0.0), R, R * 0.12, h, 12, "fir")
    ocyl(mb, (x, y0 + 8.75, z), (0.0, 1.0, 0.0), 0.42, 0.06, 0.4, 5, "orn_gold")
    for _ in range(70):
        yb, R, h = rng.choice(tiers)
        f = rng.uniform(0.12, 0.92)
        r = R * (1.0 - 0.88 * f) + 0.06
        th = rng.uniform(0.0, 2 * math.pi)
        p = (x + r * math.cos(th), y0 + yb + h * f, z + r * math.sin(th))
        blob(mb, p, 0.14, rng.choice(["orn_red", "orn_gold", "orn_blue", "orn_white"]), rng,
             rings=2, segs=5, sy=1.0)
    COLS.append((x - 1.9, x + 1.9, z - 1.9, z + 1.9, 0.0, 3.0))


def garland(mb, p0, p1, rng, spacing=0.9):
    """Festive bulb string hanging between two lamp heads."""
    cols = ["bulb_red", "bulb_green", "bulb_gold", "bulb_blue"]
    n = max(2, int(math.dist(p0, p1) / spacing))
    for k in range(n + 1):
        t = k / n
        x = p0[0] + (p1[0] - p0[0]) * t
        z = p0[2] + (p1[2] - p0[2]) * t
        y = p0[1] + (p1[1] - p0[1]) * t - 0.7 * 4 * t * (1 - t)
        blob(mb, (x, y, z), 0.08, cols[k % 4], rng, rings=2, segs=4, sy=1.0)


def block_garlands(cx, cz, rng):
    """About a quarter of the lamp spans on each block side get a festive garland."""
    sides = [
        [(cx + LAMP_INSET, cz + o, math.pi / 2) for o in LAMP_OFFS],
        [(cx - LAMP_INSET, cz + o, -math.pi / 2) for o in LAMP_OFFS],
        [(cx + o, cz + LAMP_INSET, 0.0) for o in LAMP_OFFS],
        [(cx + o, cz - LAMP_INSET, math.pi) for o in LAMP_OFFS],
    ]

    def tip(p):
        x, z, r = p
        return (x + math.sin(r) * 1.55, 6.78, z + math.cos(r) * 1.55)

    for side in sides:
        for a, b in zip(side, side[1:]):
            if rng.random() < 0.12:
                GARLANDS.append((tip(a), tip(b)))


def snow_banks(mb, cx, cz, rng, skip=()):
    """Snowbanks piled on the sidewalk against each kerb of a block: a lumpy ridge
    0.3 m tall, kept off the road so the lanes stay open."""
    sides = [((1.0, 0.0), 0), ((-1.0, 0.0), 1), ((0.0, 1.0), 2), ((0.0, -1.0), 3)]
    for (o, idx) in sides:
        if idx in skip or rng.random() < 0.2:
            continue
        ox, oz = o
        tx, tz = -oz, ox
        ts = [-21.0 + 3.0 * k for k in range(15)]
        hs = [0.12 + 0.2 * rng.random() for _ in ts]

        def pt(d, t, h):
            return (cx + ox * d + tx * t, WALK_H + h, cz + oz * d + tz * t)

        for k in range(len(ts) - 1):
            t0, t1 = ts[k], ts[k + 1]
            h0, h1 = hs[k], hs[k + 1]
            A = pt(19.6, t0, 0.004)
            B = pt(19.6, t1, 0.004)
            C = pt(20.25, t1, h1)
            D = pt(20.25, t0, h0)
            E = pt(20.9, t0, 0.004)
            F = pt(20.9, t1, 0.004)
            mb.poly([A, B, C, D], "snowbank", vnorm(vadd(vmul((ox, 0.0, oz), -1.0), UPV)))
            mb.poly([D, C, F, E], "snowbank", vnorm(vadd((ox, 0.0, oz), UPV)))


def tire_tracks(mb, rng):
    """Dark tyre tracks worn into the snow on the road lanes."""
    for rc in ROADS:
        for _ in range(9):
            lane = rng.choice([-3.0, 3.0])
            a = rng.uniform(-140.0, 120.0)
            L = rng.uniform(8.0, 20.0)
            rect_at(mb, rc + lane - 0.55, rc + lane - 0.25, a, a + L, 0.014, "track")
            rect_at(mb, rc + lane + 0.25, rc + lane + 0.55, a, a + L, 0.014, "track")
            a = rng.uniform(-140.0, 120.0)
            rect_at(mb, a, a + L, rc + lane - 0.55, rc + lane - 0.25, 0.014, "track")
            rect_at(mb, a, a + L, rc + lane + 0.25, rc + lane + 0.55, 0.014, "track")


def cart(mb, x, z, rot, y0=WALK_H + 0.012):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    obox(mb, (x, y0 + 0.55, z), ax, (0.3, 0.2, 0.42), "cart_wire")
    obox(mb, (x, y0 + 0.12, z), ax, (0.3, 0.02, 0.42), "cart_wire")
    for sg in (-1, 1):
        for sf in (-1, 1):
            ocyl(mb, vadd((x, y0 + 0.04, z), vmul(s, 0.25 * sg), vmul(f, 0.38 * sf)), s, 0.04, 0.04, 0.03, 6, "tire")


def carts(mb, cx, cz, rng, n):
    for _ in range(n):
        x = cx + rng.uniform(-15.0, 15.0)
        z = cz + rng.choice([-14.0, 14.0]) + rng.uniform(-1.0, 1.0)
        cart(mb, x, z, rng.uniform(0.0, math.pi))


def seg_col(x, z, rot, half_len, half_wid):
    """Collider for a part whose long side runs along (cos rot, -sin rot), as benches do."""
    ex = abs(math.cos(rot)) * half_len + abs(math.sin(rot)) * half_wid
    ez = abs(math.sin(rot)) * half_len + abs(math.cos(rot)) * half_wid
    return (x - ex, x + ex, z - ez, z + ez, 0.0, 3.0)


# ================================================================ buildings
def build_mall(mb, decor, furn, rng):
    cx, cz, hx, hz = MALL["cx"], MALL["cz"], MALL["hx"], MALL["hz"]
    gh, fh, nf = MALL["gh"], MALL["fh"], MALL["nf"]
    H = gh + nf * fh
    faces = face_frames(cx, cz, hx, hz, WALK_H)
    for fr, L in faces:
        storefront_face(mb, fr, L, gh, fh, nf, rng)
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": "office"}, rng, "frame_dark")
    ax = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    # atrium skylight: glass top, frame sides
    obox(mb, (cx + 1.0, WALK_H + H + 1.0, cz), ax, (6.0, 1.0, 7.5),
         ["frame", "frame", "glass", "frame", "frame", "frame"])
    for (x, z) in ((cx - 11.0, cz - 11.0), (cx - 11.0, cz + 11.0), (cx + 12.0, cz - 11.0), (cx + 12.0, cz + 11.0)):
        obox(mb, (x, WALK_H + H + 0.6, z), ax, (1.2, 0.6, 0.9), "ac")
    # west face: entrance canopy, columns, revolving door, roof-edge sign
    fw, Lw = faces[3]
    wbox(mb, fw, 10.9, 23.1, 4.1, 4.5, 0.0, 4.2, "frame_dark")
    wbox(mb, fw, 10.9, 23.1, 4.5, 4.6, 0.0, 4.3, "snow_cap")
    for u in (12.0, 15.3, 18.7, 22.0):
        p = P(fw, u, 0.0, 3.8)
        vcyl(mb, p[0], p[1], p[2], 0.2, 0.2, 4.1, 10, "stone")
    p = P(fw, 17.0, 0.0, 1.2)
    vcyl(mb, p[0], p[1], p[2], 1.45, 1.45, gh - 0.7, 14, "glass")
    vcyl(mb, p[0], p[1] + gh - 0.7, p[2], 1.55, 1.55, 0.12, 14, "frame")
    wbox(mb, fw, 3.5, Lw - 3.5, H + 0.8, H + 4.4, 0.0, 0.5, "sign_board")
    sign_text("mall_sign_cn", "星光購物中心", "sign_lit", P(fw, 17.0, H + 3.0, 0.5), fw[1], 13.0)
    sign_text("mall_sign_en", "STARLIGHT MALL", "sign_lit", P(fw, 17.0, H + 1.3, 0.5), fw[1], 9.0)
    # plaza: giant tree, snack kiosk, benches, bus stop
    christmas_tree(decor, -17.0, -11.0, rng)
    kiosk(decor, -18.0, 9.5)
    for (x, z) in ((-20.0, 0.0), (-20.0, 14.0)):
        bench(furn, x, z, math.pi / 2, WALK_H)
        COLS.append(seg_col(x, z, math.pi / 2, 0.9, 0.3))
    bus_stop(decor, -20.4, 17.5)


def cinema(mb, rng, cx, cz):
    hx, hz = 12.0, 17.0
    gh, fh, nf = 4.6, 4.4, 1
    H = gh + nf * fh
    faces = face_frames(cx, cz, hx, hz, WALK_H)
    for idx, (fr, L) in enumerate(faces):
        storefront_face(mb, fr, L, gh, fh, nf, rng)
        if idx != 2:     # film posters on the other three faces
            for u0 in (L * 0.2, L * 0.62):
                wbox(mb, fr, u0, u0 + 3.0, 5.4, 7.6, 0.0, 0.12, rng.choice(["sign_red", "sign_navy", "sign_ochre", "sign_green"]))
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": "office"}, rng, "concrete")
    fe, Le = faces[2]
    # marquee over the east entrance, lit fascia with the name
    wbox(mb, fe, 5.0, Le - 5.0, 4.3, 5.9, 0.0, 5.0, "frame_dark")
    wbox(mb, fe, 5.0, Le - 5.0, 4.3, 5.9, 5.0, 5.12, "sign_board")
    sign_text("cinema_sign", "星光電影城", "sign_lit", P(fe, Le / 2, 5.1, 5.13), fe[1], 8.0)
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, 0.0, 3.0))


def dept_store(mb, rng, cx, cz):
    hx = hz = 14.0
    gh, fh, nf = 4.6, 3.8, 4
    H = gh + nf * fh
    faces = face_frames(cx, cz, hx, hz, WALK_H)
    for fr, L in faces:
        storefront_face(mb, fr, L, gh, fh, nf, rng)
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": "office"}, rng, "frame_dark")
    fw, Lw = faces[3]
    wbox(mb, fw, 3.0, Lw - 3.0, H + 0.8, H + 3.0, 0.0, 0.5, "sign_board")
    sign_text("dept_sign", "星光百貨", "sign_lit", P(fw, Lw / 2, H + 1.9, 0.5), fw[1], 9.0)
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, 0.0, 3.0))


def parking_garage(mb, cars_mb, rng, cx, cz):
    """Six-level open car park, 36 x 36 m, cars on the top deck, P sign on the north face."""
    hx, hz = 18.0, 18.0
    lv, nlv = 3.4, 6
    H = lv * nlv
    faces = face_frames(cx, cz, hx, hz, WALK_H)
    for k in range(1, nlv):
        obox(mb, (cx, WALK_H + k * lv, cz), [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)], (hx, 0.2, hz), "concrete")
    ow, nop = 4.0, 6
    pier = (2 * hx - nop * ow) / (nop + 1)
    for fr, L in faces:
        for k in range(nlv):
            base = k * lv
            wbox(mb, fr, -0.2, L + 0.2, base, base + 0.9, 0.0, 0.3, "concrete")
            wbox(mb, fr, -0.2, L + 0.2, base + 3.0, base + lv, 0.0, 0.3, "concrete")
            for p in range(nop + 1):
                p0 = p * (ow + pier)
                wbox(mb, fr, p0, p0 + pier, base + 0.9, base + 3.0, 0.0, 0.3, "concrete")
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": "office"}, rng, "concrete")
    fs = faces[0][0]
    wbox(mb, fs, 10.0, 26.0, H + 0.6, H + 3.4, 0.15, 0.4, "sign_navy")
    glyph_row(mb, fs, "P", 18.0, H + 1.0, 0.45, 0.4, 0.5, "letter_white", gap=0.0)
    for x, z, rot in ((cx - 9.0, cz - 8.0, 0.0), (cx - 3.0, cz + 8.0, 0.0), (cx + 3.5, cz - 6.0, 0.0),
                      (cx + 9.0, cz + 5.0, 0.0), (cx + 1.0, cz + 2.0, math.pi / 2)):
        car(cars_mb, x, z, rot, rng.choice(PAINTS), WALK_H + H, False, rng)
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, 0.0, 3.0))


def glyph_row(mb, fr, text, uc, v0, cell, t0, t1, mat, gap=0.14):
    """Block lettering on a facade frame (only the glyphs used here)."""
    width = len(text) * 5 * cell + (len(text) - 1) * gap
    u = uc - width / 2
    for ch in text:
        for r, line in enumerate(GLYPHS[ch]):
            vb = v0 + (4 - r) * cell
            c = 0
            while c < 5:
                if line[c] == "1":
                    e = c
                    while e + 1 < 5 and line[e + 1] == "1":
                        e += 1
                    wbox(mb, fr, u + c * cell, u + (e + 1) * cell, vb, vb + cell, t0, t1, mat)
                    c = e + 1
                else:
                    c += 1
        u += 5 * cell + gap


def build_park(gl, cx, cz, rng, trees_mb, furn, rink=False):
    """Small park with paths and trees. With rink=True the middle is a 22 x 12 m skating
    rink with low boards on all four sides and a warming hut."""
    rect_at(gl, cx - 18, cx + 18, cz - 18, cz + 18, WALK_H + 0.012, "grass")
    rect_at(gl, cx - 18, cx + 18, cz - 1.2, cz + 1.2, WALK_H + 0.02, "sidewalk")
    rect_at(gl, cx - 1.2, cx + 1.2, cz - 18, cz - 1.2, WALK_H + 0.02, "sidewalk")
    rect_at(gl, cx - 1.2, cx + 1.2, cz + 1.2, cz + 18, WALK_H + 0.02, "sidewalk")
    if rink:
        rect_at(gl, cx - 11, cx + 11, cz - 6, cz + 6, WALK_H + 0.03, "ice")
        ax = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
        obox(furn, (cx, WALK_H + 0.45, cz - 6.2), ax, (11.2, 0.45, 0.12), "rink_board")
        obox(furn, (cx, WALK_H + 0.45, cz + 6.2), ax, (11.2, 0.45, 0.12), "rink_board")
        obox(furn, (cx - 11.2, WALK_H + 0.45, cz), ax, (0.12, 0.45, 6.2), "rink_board")
        obox(furn, (cx + 11.2, WALK_H + 0.45, cz), ax, (0.12, 0.45, 6.2), "rink_board")
        COLS.append((cx - 11.4, cx + 11.4, cz - 6.4, cz - 5.9, 0.0, 3.0))
        COLS.append((cx - 11.4, cx + 11.4, cz + 5.9, cz + 6.4, 0.0, 3.0))
        COLS.append((cx - 11.4, cx - 10.9, cz - 6.0, cz + 6.0, 0.0, 3.0))
        COLS.append((cx + 10.9, cx + 11.4, cz - 6.0, cz + 6.0, 0.0, 3.0))
        kiosk(furn, cx + 14.0, cz + 10.0)
        spots = [(cx - 15.0, cz + 3.0, math.pi / 2), (cx + 15.0, cz - 3.0, math.pi / 2),
                 (cx - 3.0, cz - 12.5, 0.0), (cx + 4.0, cz + 12.5, 0.0)]
        n_trees = 8
    else:
        spots = [(cx - 8, cz + 4.0, math.pi / 2), (cx + 8, cz - 4.0, math.pi / 2),
                 (cx - 4.0, cz - 8, 0.0), (cx + 4.0, cz + 8, 0.0)]
        n_trees = 10
    for (x, z, r) in spots:
        bench(furn, x, z, r, WALK_H + 0.012)
        COLS.append(seg_col(x, z, r, 0.9, 0.3))
    n = 0
    tries = 0
    while n < n_trees and tries < 400:
        tries += 1
        x = cx + rng.uniform(-15, 15)
        z = cz + rng.uniform(-15, 15)
        if abs(x - cx) < 2.2 or abs(z - cz) < 2.2:
            continue
        if rink and abs(x - cx) < 13.0 and abs(z - cz) < 8.0:
            continue
        if any(math.hypot(x - sx, z - sz) < 3.0 for sx, sz, _ in spots):
            continue
        s = rng.uniform(0.9, 1.25)
        tree(trees_mb, x, z, s, rng, WALK_H + 0.012)
        TREE_SPOTS.append((x, z, s))
        COLS.append((x - 0.3 * s, x + 0.3 * s, z - 0.3 * s, z + 0.3 * s, 0.0, 3.0))
        n += 1


def city_block(i, j, cx, cz, kind, rng, bldgs, furn, trees, cars):
    """Downtown-style blocks: a tower (T) or four corner buildings (Q) around a cross alley."""
    if kind == "T":
        W = D = rng.choice([28.0, 30.0, 32.0, 34.0, 36.0])
        n_floors = rng.randint(9, 18)
        H = GH + n_floors * FH
        style = rng.choice(["office", "curtain"])
        mb, h = building(f"Bldg_{i}{j}_tower", cx, cz, W, D, H, style, rng, fire_face=-1)
        bldgs.append(mb)
        COLS.append((cx - W / 2, cx + W / 2, cz - D / 2, cz + D / 2, 0.0, 3.0))
        return
    for sx in (-1, 1):
        for sz in (-1, 1):
            wx = rng.choice([12.0, 13.0, 14.0, 15.0, 16.0])
            wz = rng.choice([12.0, 13.0, 14.0, 15.0, 16.0])
            ox = 19.0 - rng.uniform(0.0, 0.6)
            oz = 19.0 - rng.uniform(0.0, 0.6)
            bx = cx + sx * (ox - wx / 2)
            bz = cz + sz * (oz - wz / 2)
            if rng.random() < 0.5:
                n_floors = rng.randint(2, 6)
                bkind = "brick"
            else:
                n_floors = rng.randint(8, 16)
                bkind = rng.choice(["office", "curtain"])
            H = GH + n_floors * FH
            fire = rng.randrange(4) if bkind == "brick" and rng.random() < 0.6 else -1
            mb, h = building(f"Bldg_{i}{j}_{'n' if sz > 0 else 's'}{'e' if sx > 0 else 'w'}", bx, bz,
                             wx, wz, H, bkind, rng, fire_face=fire)
            bldgs.append(mb)
            COLS.append((bx - wx / 2, bx + wx / 2, bz - wz / 2, bz + wz / 2, 0.0, 3.0))
    for sx, sz in ((-1, 1), (1, -1)):
        x, z = cx + sx * 1.9, cz + sz * 13.0
        dumpster(furn, x, z, 0.0, WALK_H)
        COLS.append(footprint_col(x, z, 0.0, 1.2, 0.6))
        for _ in range(2):
            blob(furn, (x + rng.uniform(-0.8, 0.8), WALK_H + 0.2, z + rng.uniform(-1.8, 1.8)), 0.3, "bag", rng)
    for side, (ex, ez) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
        if rng.random() < 0.5:
            for along in (-6.0, 6.0):
                if rng.random() < 0.6:
                    if ez:
                        x, z = cx + along, cz + ez * 20.0
                    else:
                        x, z = cx + ex * 20.0, cz + along
                    s = rng.uniform(0.85, 1.1)
                    tree(trees, x, z, s, rng, WALK_H)
                    TREE_SPOTS.append((x, z, s))
                    COLS.append((x - 0.3 * s, x + 0.3 * s, z - 0.3 * s, z + 0.3 * s, 0.0, 3.0))
        if rng.random() < 0.35:
            along = rng.choice([-10.0, 10.0])
            if ez:
                x, z, r = cx + along, cz + ez * 20.4, math.pi / 2
            else:
                x, z, r = cx + ex * 20.4, cz + along, 0.0
            bench(furn, x, z, r, WALK_H)
            COLS.append(seg_col(x, z, r, 0.9, 0.3))
        if rng.random() < 0.3:
            along = rng.choice([-17.0, 17.0])
            if ez:
                x, z = cx + along, cz + ez * 20.0
            else:
                x, z = cx + ex * 20.0, cz + along
            bin_(furn, x, z, WALK_H)
            COLS.append((x - 0.3, x + 0.3, z - 0.3, z + 0.3, 0.0, 3.0))
        if rng.random() < 0.25:
            along = rng.choice([-19.0, 19.0])
            if ez:
                x, z = cx + along, cz + ez * 21.0
            else:
                x, z = cx + ex * 21.0, cz + along
            hydrant(furn, x, z, WALK_H)
            COLS.append((x - 0.2, x + 0.2, z - 0.2, z + 0.2, 0.0, 3.0))
    if rng.random() < 0.4:
        x = cx + rng.choice([-1, 1]) * 20.0
        z = cz + rng.choice([-1, 1]) * 20.0
        rot = 0.0 if rng.random() < 0.5 else math.pi / 2
        barrier(furn, x, z, rot, WALK_H)
        COLS.append(footprint_col(x, z, rot, 1.5, 0.3))


# ================================================================ scene assembly
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

    print("MAP stage: ground, roads, sidewalks")
    ground_road = Mesh("Ground_road")
    ground_road.poly([(-200, 0, -200), (200, 0, -200), (200, 0, 200), (-200, 0, 200)], "asphalt", UPV)
    ground_side = Mesh("Ground_sidewalk")
    ground_grass = Mesh("Ground_grass")
    ground_lot = Mesh("Ground_lot")
    markings = Mesh("Ground_markings")
    tracks = Mesh("Ground_tracks")
    ring_blocks = [(x, z) for z in RING_C for x in RING_C if abs(x) == 168 or abs(z) == 168]
    for cz in BC:
        for cx in BC:
            block_slab(ground_side, cx, cz)
    for cx, cz in ring_blocks:
        block_slab(ground_side, cx, cz)

    for rc in ROADS:
        t = -146.0
        while t < 146.0:
            c = t + 1.5
            if all(abs(c - rd) > 9.0 for rd in ROADS):
                rect_at(markings, rc - 0.08, rc + 0.08, c - 1.5, c + 1.5, 0.012, "paint_white")
                rect_at(markings, c - 1.5, c + 1.5, rc - 0.08, rc + 0.08, 0.012, "paint_white")
            t += 6.0
    for rc in ROADS:
        for rd in ROADS:
            for sgn in (-1, 1):
                zc = rd + sgn * 7.5
                for k in range(-5, 6):
                    xc = rc + k * 1.1
                    rect_at(markings, xc - 0.33, xc + 0.33, zc - 1.5, zc + 1.5, 0.012, "paint_white")
                xc = rc + sgn * 7.5
                for k in range(-5, 6):
                    zc2 = rd + k * 1.1
                    rect_at(markings, xc - 1.5, xc + 1.5, zc2 - 0.33, zc2 + 0.33, 0.012, "paint_white")
    cand = 0
    while cand < 18:
        cand += 1
        rc = rng.choice(ROADS)
        p = rng.uniform(-130, 130)
        if rng.random() < 0.5:
            x, z = rc + 3.2, p
        else:
            x, z = p, rc + 3.2
        if math.hypot(x - START[0], z - START[1]) < 14:
            continue
        if any(abs(p - rd) < 9 for rd in ROADS):
            continue
        for k in range(10):
            a0 = 2 * math.pi * k / 10
            a1 = 2 * math.pi * (k + 1) / 10
            markings.poly([(x, 0.013, z), (x + 0.36 * math.cos(a0), 0.013, z + 0.36 * math.sin(a0)),
                           (x + 0.36 * math.cos(a1), 0.013, z + 0.36 * math.sin(a1))], "manhole", UPV)
    tire_tracks(tracks, rng)

    print("MAP stage: blocks, mall and buildings")
    furn = Mesh("Furniture")
    trees = Mesh("Trees", smooth=True)
    cars = Mesh("Cars")
    street_lamps = Mesh("StreetLamps")
    debris = Mesh("Debris")
    decor = Mesh("MallDecor", smooth=True)
    garl = Mesh("Garlands", smooth=True)
    banks = Mesh("Snowbanks")
    bldgs = []
    kinds = {}
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            kind = ROWS[j][i]
            kinds[(i, j)] = kind
            block_lamps(cx, cz)
            block_garlands(cx, cz, rng)
            snow_banks(banks, cx, cz, rng, skip=(1,) if kind == "mall" else ())
            if kind == "lot":
                build_lot(ground_lot, cx, cz, rng, furn, cars)
                carts(furn, cx, cz, rng, 6)
                continue
            if kind == "park":
                build_park(ground_grass, cx, cz, rng, trees, furn)
                continue
            if kind == "rink":
                build_park(ground_grass, cx, cz, rng, trees, furn, rink=True)
                continue
            if kind == "mall":
                mall_mb = Mesh("Mall")
                build_mall(mall_mb, decor, furn, rng)
                bldgs.append(mall_mb)
                continue
            if kind == "cinema":
                mb = Mesh("Cinema")
                cinema(mb, rng, cx, cz)
                bldgs.append(mb)
                continue
            if kind == "dept":
                mb = Mesh("DeptStore")
                dept_store(mb, rng, cx, cz)
                bldgs.append(mb)
                continue
            if kind == "carpark":
                mb = Mesh("CarPark")
                parking_garage(mb, cars, rng, cx, cz)
                bldgs.append(mb)
                continue
            city_block(i, j, cx, cz, kind, rng, bldgs, furn, trees, cars)

    for cx, cz in ring_blocks:
        W = D = rng.choice([26.0, 28.0, 30.0, 32.0, 34.0])
        H = rng.uniform(60.0, 110.0)
        mb, h = building(f"Ring_{int(cx)}_{int(cz)}", cx, cz, W, D, H, "ring", rng)
        bldgs.append(mb)
        COLS.append((cx - W / 2, cx + W / 2, cz - D / 2, cz + D / 2, 0.0, 3.0))

    kerb_cars = 0
    cand = []
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            if ROWS[j][i] in ("T", "Q"):
                cand.append((cx + 23.2, cz + rng.uniform(-12, 12), 0.0))
                cand.append((cx + rng.uniform(-12, 12), cz + 23.2, math.pi / 2))
    rng.shuffle(cand)
    for x, z, r in cand:
        if kerb_cars >= 8:
            break
        if math.hypot(x - START[0], z - START[1]) < 14:
            continue
        if abs(x - START[0]) < 3 and abs(z - START[1]) < 14:
            continue
        car(cars, x, z, r, rng.choice(PAINTS), 0.0, rng.random() < 0.15, rng)
        CAR_SPOTS.append((x, z, r, False))
        COLS.append(footprint_col(x, z, r, 2.3, 0.95))
        kerb_cars += 1
    for (rc, bc_, off) in [(84.0, -56.0, 3.2), (-84.0, 56.0, -3.2), (28.0, -112.0, 3.2)]:
        x, z = rc + off, bc_
        car(cars, x, z, 0.0, "burnt", 0.0, True, rng)
        CAR_SPOTS.append((x, z, 0.0, True))
        COLS.append(footprint_col(x, z, 0.0, 2.3, 0.95))

    for _ in range(60):
        rc = rng.choice(ROADS)
        p = rng.uniform(-140, 140)
        if rng.random() < 0.5:
            x, z = rc + rng.uniform(-4, 4), p
        else:
            x, z = p, rc + rng.uniform(-4, 4)
        if math.hypot(x - START[0], z - START[1]) < 10:
            continue
        if abs(x) > 146 or abs(z) > 146:
            continue
        obox(debris, (x, 0.12, z), [(1, 0, 0), UPV, (0, 0, 1)],
             (rng.uniform(0.15, 0.6), 0.1, rng.uniform(0.15, 0.5)), "debris")
    for _ in range(3):
        x = rng.uniform(-40, 40)
        z = rng.uniform(-40, 40)
        if math.hypot(x - START[0], z - START[1]) < 10:
            continue
        obox(debris, (x, 0.3, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.42, 0.3, 0.3), "cardboard")

    for (x, z, r) in LAMP_POLES:
        lamp_post(street_lamps, x, z, r)
        COLS.append((x - 0.15, x + 0.15, z - 0.15, z + 0.15, 0.0, 3.0))
    for (a, b) in GARLANDS:
        garland(garl, a, b, rng)

    print("MAP stage: build objects")
    meshes = [ground_road, ground_side, ground_grass, ground_lot, markings, tracks, furn, trees, cars,
              street_lamps, debris, decor, garl, banks] + bldgs
    objs = []
    tri_total = 0
    for mb in meshes:
        if mb.faces:
            objs.append(mb.build(coll))
            tri_total += mb.tris()
            if ENV.get("MAP_DEBUG"):
                print("MAP tris", mb.name, mb.tris())

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
    for o in SIGN_OBJS:
        objs.append(o)
        o.data.calc_loop_triangles()
        tri_total += len(o.data.loop_triangles)
    print(f"MAP counts: visual_tris={tri_total} COL={len(COLS)} LAMP={len(LAMPS)} "
          f"garlands={len(GARLANDS)} signs={len(SIGN_OBJS)} trees={len(TREE_SPOTS)} cars={len(CAR_SPOTS)} "
          f"buildings={len(bldgs)} col_tris={12 * len(COLS)} total_tris={tri_total + 12 * len(COLS)}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        bkit.export_glb(OUT_GLB, objs, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


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
    sun = bkit.sun(elevation=38, azimuth=150, strength=2.6, softness=1.5)
    hidden = [o for o in objs if o.name.startswith(("COL_", "LAMP_"))]
    for o in hidden:
        o.hide_render = True
    for name in [w.strip() for w in RENDER_LIST.split(",") if w.strip()]:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (-27.0, 1.7, 20.0), (-6.0, 10.0, -4.0), lens=26.0)
        else:
            continue
        scene.camera = cam
        scene.render.filepath = PREVIEWS[name]
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("MAP preview", name, round(time.time() - t0, 1), "s ->", PREVIEWS[name])
        bpy.data.objects.remove(cam)
    bpy.data.objects.remove(sun)
    for o in hidden:
        o.hide_render = False


if __name__ == "__main__":
    main()
