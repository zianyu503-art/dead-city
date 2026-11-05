"""最後防線 (the last stand: the evacuation square at dawn) level map for 射擊遊戲, built headless
with the blender-modeling skill. Same conventions as map_downtown.py.

Run from the project root:   blender -b -P tools/blender/map_evac.py
Writes assets/models/map_evac.glb and previews to .claude/work/.

The centre block (game x and z within +-22) is left empty: only its concrete slab. The game builds
the helipad, barriers, light towers, tents and the helicopter there itself (buildEvac in index.html).

Gameplay data read by the game (buildCityMap in index.html):
  COL_<n>   axis-aligned box, 3 m tall = collider (buildings, cars, barriers, wire, rubble, poles...)
  LAMP_<n>  empty at a street lamp head or a floodlight face = a light position
  Ground*   ground meshes (roads, sidewalks, lots) - they do not cast shadows

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
TEX_DIR = os.path.join(WORK, "map_evac_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_evac.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_evac_top.png"),
    "street": os.path.join(WORK, "map_evac_street.png"),
    "corner": os.path.join(WORK, "map_evac_corner.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 31

# ---------------------------------------------------------------- city layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # inner block centres
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                              # block half size (44 m slab)
WALK_H = 0.16                                            # sidewalk top
GH = 4.4                                                 # ground floor height
FH = 3.6                                                 # upper floor height
LAMP_OFFS = (-11.0, 11.0)                           # lamps every 14 m per block side
LAMP_INSET = 21.2                                        # pole 0.8 m inside the kerb
START = (-28.0, 0.0)                                     # player start (game), road x=-28

# block kinds: row j = z index, column i = x index.  T office tower, Q four corner buildings,
# F fortified Q (sandbags, banners, soot): the eight blocks around the square. C the empty centre
# block, lot parking lot, mil military lot with abandoned trucks.
ROWS = {
    0: ["Q", "T", "Q", "lot", "T"],
    1: ["T", "F", "F", "F", "Q"],
    2: ["mil", "F", "C", "F", "T"],
    3: ["Q", "F", "F", "F", "Q"],
    4: ["T", "Q", "Q", "T", "Q"],
}
BURNING = {(4, 0), (4, 4), (0, 4)}          # (i, j) outer blocks: darkened and smoke-stained
FLOOD = {(1, 1), (3, 1), (1, 3), (3, 3)}    # blocks whose centre holds a floodlight tower
COLLAPSE = (2, 1)                           # fortified block whose inner corner has collapsed
DARK_OF = {"brick": "brick_d", "concrete": "concrete_d"}   # darkened variants for burning walls
DARK_TINT = (0.36, 0.32, 0.30)
# military checkpoints on the four approach roads (axis, road centre R, barrier line A, closed side cs,
# vehicle). The closed half of each road gets the barriers; the other 6 m stay open.
CHECKPOINTS = [
    ("z", -28.0, -10.0, +1, "apc"),
    ("z", 28.0, 10.0, -1, "truck"),
    ("x", -28.0, 10.0, +1, "truck"),
    ("x", 28.0, -10.0, -1, "apc"),
]

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
    "asphalt": ("asphalt_02", 4.0),
    "sidewalk": ("concrete_pavement", 2.0),
    "grass": ("leafy_grass", 3.0),
    "brick": ("brick_wall_001", 2.0),
    "concrete": ("concrete_wall_004", 3.0),
    "roof": ("tarred_gravel", 3.0),
    "bark": ("bark_brown_02", 1.2),
    "plywood": ("plywood", 1.2),
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
    "sandbag": ((0.45, 0.41, 0.31), 0.95, 0.0, 0.3),
    "smoke": ((0.07, 0.065, 0.06), 0.95, 0.0, 0.3),
    "banner_red": ((0.42, 0.06, 0.05), 0.85, 0.0, 0.3),
    "banner_olive": ((0.24, 0.27, 0.13), 0.85, 0.0, 0.3),
    "mil_olive": ((0.27, 0.31, 0.18), 0.6, 0.15, 0.5),
    "wire": ((0.30, 0.31, 0.33), 0.35, 0.9, 0.5),
    "rebar": ((0.32, 0.18, 0.10), 0.7, 0.5, 0.5),
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
        if key in DARK_OF:
            MAT[DARK_OF[key]] = bkit.pbr_material(DARK_OF[key], maps, scale=1.0, tint=DARK_TINT, coords="UV")
            TILE[DARK_OF[key]] = tile
        print("MAP texture", key, aid, sorted(maps))
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name in CONST:
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


def building(mb_name, cx, cz, W, D, H, kind, rng, fire_face=-1, facade=None, dark=False):
    """One building: shell, storefronts, windows, roof and rooftop clutter.
    Returns the Mesh; H is the height above the sidewalk top."""
    mb = Mesh(mb_name)
    hx, hz = W / 2, D / 2
    frames = face_frames(cx, cz, hx, hz, WALK_H)
    nf = max(1, round((H - GH) / FH))
    H = GH + nf * FH
    for fi, (fr, L) in enumerate(frames):
        bay_w = {"brick": 4.2, "office": 4.4, "curtain": 4.0, "ring": 6.0}[kind]
        bays = max(2, round(L / bay_w))
        if kind == "brick":
            st = {"band": "brick", "upper": "brick", "bf": 1, "win_w": 1.5, "win_h": 1.7}
        elif kind == "office":
            st = {"band": "concrete", "upper": "concrete", "bf": 1, "win_w": 1.9, "win_h": 2.2}
        else:
            st = {"band": "concrete", "upper": "glass", "bf": 0, "win_w": 1.9, "win_h": 2.2,
                  "curtain": True, "spand_every": 1 if kind == "curtain" else 4, "decal": False}
        st.update({"bays": bays, "nf": nf, "kind": kind, "sign": rng.choice(SIGNS),
                   "door": rng.randrange(bays) if rng.random() < 0.6 else -1,
                   "awning": rng.choice(AWNINGS) if rng.random() < 0.5 else None,
                   "belts": kind in ("office", "brick", "ring"),
                   "pilaster": kind in ("brick", "office"),
                   "fire": (bays - 1) if fi == fire_face else -1})
        if dark:
            st["band"] = DARK_OF.get(st["band"], st["band"])
            st["upper"] = DARK_OF.get(st["upper"], st["upper"])
        wall_face(mb, fr, L, H, st, rng)
    if kind == "brick":
        parapet = "brick"
    elif kind == "office":
        parapet = "concrete"
    else:
        parapet = "frame_dark"
    if dark:
        parapet = DARK_OF.get(parapet, parapet)
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
        blob(mb, (cx, cy, cz), rng.uniform(1.3, 1.8) * s, rng.choice(["leaf_a", "leaf_b", "leaf_c"]), rng)


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


def build_park(gl, cx, cz, rng, trees_mb, furn):
    rect_at(gl, cx - 18, cx + 18, cz - 18, cz + 18, WALK_H + 0.012, "grass")
    rect_at(gl, cx - 18, cx + 18, cz - 1.2, cz + 1.2, WALK_H + 0.02, "sidewalk")
    rect_at(gl, cx - 1.2, cx + 1.2, cz - 18, cz - 1.2, WALK_H + 0.02, "sidewalk")
    rect_at(gl, cx - 1.2, cx + 1.2, cz + 1.2, cz + 18, WALK_H + 0.02, "sidewalk")
    spots = [(cx - 8, cz + 4.0, math.pi / 2), (cx + 8, cz - 4.0, math.pi / 2),
             (cx - 4.0, cz - 8, 0.0), (cx + 4.0, cz + 8, 0.0)]
    for (x, z, r) in spots:
        bench(furn, x, z, r, WALK_H + 0.012)
        COLS.append(footprint_col(x, z, r, 0.9, 0.3))
    n = 0
    tries = 0
    while n < 10 and tries < 400:
        tries += 1
        x = cx + rng.uniform(-15, 15)
        z = cz + rng.uniform(-15, 15)
        if abs(x - cx) < 2.2 or abs(z - cz) < 2.2:
            continue
        if any(math.hypot(x - sx, z - sz) < 3.0 for sx, sz, _ in spots):
            continue
        s = rng.uniform(0.9, 1.25)
        tree(trees_mb, x, z, s, rng, WALK_H + 0.012)
        TREE_SPOTS.append((x, z, s))
        n += 1


def footprint_col(x, z, rot, half_len, half_wid):
    x0, x1, z0, z1 = footprint(x, z, rot, half_len, half_wid)
    return (x0, x1, z0, z1, 0.0, 3.0)


# ---------------------------------------------------------------- 最後防線 (evac) additions
def sandbag_line(mb, p0, p1, rng, rows=2):
    """Courses of sandbags from game point p0 to p1 (x, z), waist high."""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    n = max(1, int(math.hypot(dx, dz) / 0.5))
    for row in range(rows):
        y = WALK_H + 0.14 + row * 0.27
        for k in range(n):
            t = (k + 0.5) / n
            blob(mb, (p0[0] + dx * t, y, p0[1] + dz * t), 0.3, "sandbag", rng, rings=3, segs=6, sy=0.5)


def sandbag_window(mb, fr, uc, width, rng):
    """Two courses of sandbags across a ground-floor opening, standing out from the wall."""
    n = max(2, int(width / 0.6))
    for row in range(2):
        v = 0.14 + row * 0.27
        for k in range(n):
            u = uc - width / 2 + (k + 0.5) * width / n
            blob(mb, P(fr, u, v, 0.42), 0.3, "sandbag", rng, rings=2, segs=5, sy=0.5)


def banner(mb, fr, uc, v0, v1, mat):
    """Military cloth hung over a window: a coloured sheet, a white band and a rail."""
    N = fr[2]
    mb.poly([P(fr, uc - 0.8, v0, 0.08), P(fr, uc + 0.8, v0, 0.08), P(fr, uc + 0.8, v1, 0.08),
             P(fr, uc - 0.8, v1, 0.08)], mat, N)
    m = (v0 + v1) / 2
    mb.poly([P(fr, uc - 0.8, m - 0.2, 0.09), P(fr, uc + 0.8, m - 0.2, 0.09), P(fr, uc + 0.8, m + 0.2, 0.09),
             P(fr, uc - 0.8, m + 0.2, 0.09)], "paint_white", N)
    wbox(mb, fr, uc - 1.0, uc + 1.0, v1, v1 + 0.08, 0.0, 0.12, "metal_dark")


def scorch_face(mb, fr, uc, v0, rng):
    """A soot blotch on a facade above an opening."""
    w, h = rng.uniform(1.6, 2.6), rng.uniform(1.2, 2.2)
    mb.poly([P(fr, uc - w / 2, v0, 0.04), P(fr, uc + w / 2, v0, 0.04), P(fr, uc + w * 0.4, v0 + h, 0.04),
             P(fr, uc - w * 0.45, v0 + h * 1.1, 0.04)], "burnt", fr[2])


def fort_decor(mb, bx, bz, wx, wz, nf, rng):
    """Sandbagged ground-floor openings, a military banner and soot on one fortified building."""
    for fr, L in face_frames(bx, bz, wx / 2, wz / 2, WALK_H):
        bays = max(2, round(L / 3.5))
        b = L / bays
        for i in range(bays):
            if rng.random() < 0.55:
                sandbag_window(mb, fr, (i + 0.5) * b, min(0.8 * b, 2.6), rng)
        if nf >= 3 and rng.random() < 0.5:
            uc = (rng.randrange(bays) + 0.5) * b
            base = GH + rng.randrange(1, min(nf, 5)) * FH
            banner(mb, fr, uc, base + 0.5, base + 2.9, rng.choice(["banner_red", "banner_olive"]))
        if rng.random() < 0.5:
            uc = (rng.randrange(bays) + 0.5) * b
            scorch_face(mb, fr, uc, GH + rng.randrange(0, nf) * FH + 0.8, rng)


def smoke_decor(mb, bx, bz, wx, wz, nf, rng):
    """Soot streaks running down from the roof edge on every face of a burning building."""
    top = GH + nf * FH
    for fr, L in face_frames(bx, bz, wx / 2, wz / 2, WALK_H):
        for _ in range(rng.randint(2, 4)):
            w = rng.uniform(1.5, 3.0)
            h = rng.uniform(3.0, 6.0)
            u = rng.uniform(0.2, max(0.25, L - w - 0.2))
            mb.poly([P(fr, u, top - h, 0.04), P(fr, u + w, top - h, 0.04), P(fr, u + w, top, 0.04),
                     P(fr, u, top, 0.04)], "smoke", fr[2])
        if rng.random() < 0.6:
            uc = rng.uniform(2.0, max(2.5, L - 2.0))
            scorch_face(mb, fr, uc, GH + rng.randrange(0, nf) * FH + 0.8, rng)


def rubble(mb, x, z, rng):
    """A rubble pile: rounded lumps of debris, broken concrete slabs and bent rebar."""
    for _ in range(5):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 1.6)
        blob(mb, (x + math.cos(a) * d, WALK_H + 0.3, z + math.sin(a) * d), rng.uniform(0.6, 1.0), "debris",
             rng, rings=3, segs=6, sy=0.5)
    for _ in range(6):
        a = rng.uniform(0, math.pi)
        ax = [(math.cos(a), 0.0, -math.sin(a)), UPV, (math.sin(a), 0.0, math.cos(a))]
        c = (x + rng.uniform(-1.6, 1.6), WALK_H + rng.uniform(0.25, 0.7), z + rng.uniform(-1.6, 1.6))
        obox(mb, c, ax, (rng.uniform(0.3, 0.7), rng.uniform(0.15, 0.3), rng.uniform(0.25, 0.5)), "concrete")
    for _ in range(3):
        vcyl(mb, x + rng.uniform(-1.2, 1.2), WALK_H + 0.4, z + rng.uniform(-1.2, 1.2), 0.03, 0.03, 1.5, 5, "rebar")


def collapsed_corner(bx, bz, wx, wz, n_floors, name, rng, bldgs, mil):
    """The inner (+x, +z) corner of a fortified building blown out: a full-height body, a
    half-height wing beside the gap and a rubble pile in the gap. Returns the rubble centre."""
    nx, nz = wx * 0.45, wz * 0.45
    H1 = GH + n_floors * FH
    H2 = GH + max(1, n_floors // 2) * FH
    parts = [
        (name + "_a", bx, bz - nz / 2, wx, wz - nz, H1),
        (name + "_b", bx - nx / 2, bz + wz / 2 - nz / 2, wx - nx, nz, H2),
    ]
    for nm, cx_, cz_, w_, d_, h_ in parts:
        mb, _ = building(nm, cx_, cz_, w_, d_, h_, "brick", rng, fire_face=-1)
        bldgs.append(mb)
        COLS.append((cx_ - w_ / 2, cx_ + w_ / 2, cz_ - d_ / 2, cz_ + d_ / 2, 0.0, 3.0))
    px, pz = bx + wx / 2 - nx / 2, bz + wz / 2 - nz / 2
    rubble(mil, px, pz, rng)
    COLS.append((px - 2.0, px + 2.0, pz - 2.0, pz + 2.0, 0.0, 3.0))
    return px, pz


def scorch_ground(mb, x, z, rng):
    """A flat soot decal on the asphalt (no collider)."""
    r = rng.uniform(1.4, 3.0)
    n = 9
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rr = r * rng.uniform(0.6, 1.0)
        pts.append((x + rr * math.cos(a), 0.014, z + rr * math.sin(a)))
    for k in range(1, n - 1):
        mb.poly([pts[0], pts[k], pts[k + 1]], "burnt", UPV)


def _axes(rot):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    return f, s, [s, UPV, f]


def mil_truck(mb, x, z, rot, y0, wrecked):
    """Abandoned military cargo truck (olive drab, or burnt when wrecked), long axis along rot."""
    f, s, ax = _axes(rot)
    base = (x, y0, z)
    body = "burnt" if wrecked else "mil_olive"
    obox(mb, vadd(base, (0, 1.45, 0), vmul(f, -1.2)), ax, (1.2, 0.95, 2.4), body)          # cargo box
    obox(mb, vadd(base, (0, 1.2, 0), vmul(f, 2.4)), ax, (1.15, 0.85, 0.95), body)          # cab
    obox(mb, vadd(base, (0, 1.5, 0), vmul(f, 3.36)), ax, (0.9, 0.3, 0.02), "glass_car")    # windscreen
    for sg in (-1, 1):
        for sf in (-1, 1):
            if wrecked and sf > 0:
                continue
            c = vadd(base, (0, 0.5, 0), vmul(s, 1.12 * sg), vmul(f, 2.5 * sf))
            ocyl(mb, c, s, 0.5, 0.5, 0.35, 10, "tire")


def apc(mb, x, z, rot, y0):
    """Burnt-out armoured personnel carrier: charred hull, tracks, a blown turret with the gun drooping."""
    f, s, ax = _axes(rot)
    base = (x, y0, z)
    obox(mb, vadd(base, (0, 1.0, 0)), ax, (1.35, 0.85, 2.7), "burnt")
    obox(mb, vadd(base, (0, 1.85, 0), vmul(f, -0.6)), ax, (1.1, 0.12, 1.1), "debris")     # torn roof plate
    tc = vadd(base, (0, 2.0, 0), vmul(f, 0.5))
    ocyl(mb, tc, UPV, 0.75, 0.75, 0.5, 10, "burnt")
    obox(mb, vadd(tc, vmul(f, 1.4), (0, -0.05, 0)), ax, (0.08, 0.08, 1.3), "burnt")
    for sg in (-1, 1):
        obox(mb, vadd(base, (0, 0.42, 0), vmul(s, 1.45 * sg)), ax, (0.22, 0.42, 2.8), "tire")


def ab_box(axis, a0, a1, c0, c1, h=3.0):
    """Collider box from an along-road range and an across-road range."""
    la, ha = min(a0, a1), max(a0, a1)
    lc, hc = min(c0, c1), max(c0, c1)
    if axis == "z":
        return (lc, hc, la, ha, 0.0, h)
    return (la, ha, lc, hc, 0.0, h)


def checkpoint(axis, R, A, cs, veh, furn, mil, rng):
    """Military checkpoint across one approach road. The road is 12 m wide: the closed half
    (6 m) gets two jersey barriers, sandbags behind them, a razor-wire coil in front and a
    vehicle parked beyond the wire; the other 6 m stays open.
    axis 'z': the road runs along z at x = R; axis 'x': along x at z = R.
    A: the barrier line's position along the road; cs: +1 closes [R, R+6], -1 closes [R-6, R]."""
    lo, hi = (R, R + 6.0) if cs > 0 else (R - 6.0, R)
    sg = 1.0 if A > 0 else -1.0                      # outward: away from the square
    rot_bar = math.pi / 2 if axis == "z" else 0.0    # barriers run across the road
    rot_road = 0.0 if axis == "z" else math.pi / 2   # vehicles run along the road
    ax_across = (1.0, 0.0, 0.0) if axis == "z" else (0.0, 0.0, 1.0)

    def at(along, across):
        return (across, along) if axis == "z" else (along, across)

    for c in (lo + 1.5, lo + 4.5):
        x, z = at(A, c)
        barrier(furn, x, z, rot_bar, WALK_H)
        COLS.append(footprint_col(x, z, rot_bar, 1.5, 0.3))
    sandbag_line(mil, at(A - sg * 0.8, lo + 0.3), at(A - sg * 0.8, hi - 0.3), rng)
    wa = A + sg * 1.0
    for k in range(10):
        x, z = at(wa, lo + 0.3 + k * 0.6)
        ocyl(mil, (x, WALK_H + 0.3, z), ax_across, 0.3, 0.3, 0.09, 6, "wire", caps=False)
    COLS.append(ab_box(axis, wa - 0.4, wa + 0.4, lo, hi))
    for c in (lo + 0.6, hi - 0.6):
        x, z = at(A + sg * 2.2, c)
        cone(furn, x, z, WALK_H + 0.012)
    hl = 2.9 if veh == "apc" else 3.3
    x, z = at(A + sg * (3.2 + hl), (lo + hi) / 2)
    if veh == "apc":
        apc(mil, x, z, rot_road, WALK_H + 0.012)
        COLS.append(footprint_col(x, z, rot_road, 2.9, 1.35))
    else:
        mil_truck(mil, x, z, rot_road, WALK_H + 0.012, False)
        COLS.append(footprint_col(x, z, rot_road, 3.3, 1.3))


def build_mil_lot(gl, cx, cz, rng, mil):
    """Military lot: asphalt, two rows of abandoned trucks (some burnt), cones, a sandbag wall."""
    rect_at(gl, cx - 18, cx + 18, cz - 18, cz + 18, WALK_H + 0.012, "asphalt")
    for z in (cz - 7.0, cz + 7.0):
        for x in (cx - 12.0, cx, cx + 12.0):
            mil_truck(mil, x, z, math.pi / 2, WALK_H + 0.012, rng.random() < 0.3)
            COLS.append(footprint_col(x, z, math.pi / 2, 3.3, 1.3))
    for sx, sz in ((-1, -1), (1, 1), (-1, 1)):
        cone(mil, cx + sx * 16.0, cz + sz * 16.0, WALK_H + 0.012)
    sandbag_line(mil, (cx + 18.5, cz - 8.0), (cx + 18.5, cz + 8.0), rng)
    COLS.append((cx + 18.2, cx + 18.8, cz - 8.0, cz + 8.0, 0.0, 3.0))


def flood_tower(mb, x, z):
    """Floodlight tower: a 10.6 m mast, a lamp housing with a lit face, a concrete foot.
    A LAMP_ empty sits at the lit face."""
    vcyl(mb, x, WALK_H, z, 0.16, 0.10, 10.6, 8, "metal")
    vcyl(mb, x, WALK_H, z, 0.5, 0.5, 0.35, 8, "concrete")
    axes = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    obox(mb, (x, 10.9, z), axes, (1.05, 0.34, 0.3), "frame_dark")
    obox(mb, (x, 10.9, z + 0.31), axes, (0.95, 0.26, 0.02), "lamp_head")
    COLS.append((x - 0.7, x + 0.7, z - 0.7, z + 0.7, 0.0, 3.0))
    LAMPS.append((x, 10.9, z + 0.33))


def road_markings(markings):
    """Centre dashes and crosswalks on all four arms of every intersection."""
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


def manholes(markings, rng):
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
        for k in range(14):
            a0 = 2 * math.pi * k / 14
            a1 = 2 * math.pi * (k + 1) / 14
            markings.poly([(x, 0.013, z), (x + 0.36 * math.cos(a0), 0.013, z + 0.36 * math.sin(a0)),
                           (x + 0.36 * math.cos(a1), 0.013, z + 0.36 * math.sin(a1))], "manhole", UPV)


def check_centre(meshes):
    """The empty centre block (|x|, |z| < 22) may hold only its slab: count anything else there."""
    bad = 0
    for mb in meshes:
        lim = 0.165 if mb.name == "Ground_sidewalk" else -1.0
        for v in mb.verts:
            if abs(v[0]) < 21.99 and abs(v[2]) < 21.99 and v[1] > lim:
                bad += 1
    for (x0, x1, z0, z1, y0, y1) in COLS:
        if x1 > -21.99 and x0 < 21.99 and z1 > -21.99 and z0 < 21.99:
            bad += 1
    for (x, y, z) in LAMPS:
        if abs(x) < 21.99 and abs(z) < 21.99:
            bad += 1
    return bad


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

    print("MAP stage: ground, roads, sidewalks")
    ground_road = Mesh("Ground_road")
    ground_road.poly([(-200, 0, -200), (200, 0, -200), (200, 0, 200), (-200, 0, 200)], "asphalt", UPV)
    ground_side = Mesh("Ground_sidewalk")
    ground_lot = Mesh("Ground_lot")
    markings = Mesh("Ground_markings")
    ring_blocks = [(x, z) for z in RING_C for x in RING_C if abs(x) == 168 or abs(z) == 168]
    for cz in BC:
        for cx in BC:
            block_slab(ground_side, cx, cz)
    for cx, cz in ring_blocks:
        block_slab(ground_side, cx, cz)
    road_markings(markings)
    manholes(markings, rng)
    for _ in range(22):                      # soot on the roads around the square
        rc = rng.choice([-28.0, 28.0])
        p = rng.uniform(-95.0, 95.0)
        if rng.random() < 0.5:
            x, z = rc + rng.uniform(-4, 4), p
        else:
            x, z = p, rc + rng.uniform(-4, 4)
        scorch_ground(markings, x, z, rng)

    print("MAP stage: blocks and buildings")
    furn = Mesh("Furniture")
    trees = Mesh("Trees", smooth=True)
    cars = Mesh("Cars")
    mil = Mesh("Military")
    flood = Mesh("Floodlights")
    street_lamps = Mesh("StreetLamps")
    debris = Mesh("Debris")
    bldgs = []
    collapses = 0
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            kind = ROWS[j][i]
            if kind == "C":                  # the empty centre block: its slab only
                continue
            block_lamps(cx, cz)
            burning = (i, j) in BURNING
            fort = kind == "F"
            if kind == "lot":
                build_lot(ground_lot, cx, cz, rng, furn, cars)
                continue
            if kind == "mil":
                build_mil_lot(ground_lot, cx, cz, rng, mil)
                continue
            if kind == "T":
                W = D = rng.choice([28.0, 30.0, 32.0])
                n_floors = rng.randint(9, 16)
                mb, h = building(f"Bldg_{i}{j}_tower", cx, cz, W, D, GH + n_floors * FH,
                                 rng.choice(["office", "curtain"]), rng, fire_face=-1, dark=burning)
                bldgs.append(mb)
                COLS.append((cx - W / 2, cx + W / 2, cz - D / 2, cz + D / 2, 0.0, 3.0))
                if burning:
                    smoke_decor(mb, cx, cz, W, D, n_floors, rng)
            else:
                # four corner buildings leaving a cross-shaped alley (as in downtown)
                for sx in (-1, 1):
                    for sz in (-1, 1):
                        wx = rng.choice([12.0, 13.0, 14.0, 15.0, 16.0])
                        wz = rng.choice([12.0, 13.0, 14.0, 15.0, 16.0])
                        ox = 19.0 - rng.uniform(0.0, 0.6)
                        oz = 19.0 - rng.uniform(0.0, 0.6)
                        bx = cx + sx * (ox - wx / 2)
                        bz = cz + sz * (oz - wz / 2)
                        if rng.random() < (0.6 if fort else 0.5):
                            bkind = "brick"
                            n_floors = rng.randint(3, 5) if fort else rng.randint(2, 5)
                        else:
                            bkind = rng.choice(["office", "curtain"])
                            n_floors = rng.randint(5, 8) if fort else rng.randint(6, 11)
                        name = f"Bldg_{i}{j}_{'n' if sz > 0 else 's'}{'e' if sx > 0 else 'w'}"
                        if (i, j) == COLLAPSE and sx > 0 and sz > 0:
                            collapsed_corner(bx, bz, wx, wz, 5, name, rng, bldgs, mil)
                            collapses += 1
                            continue
                        H = GH + n_floors * FH
                        fire = rng.randrange(4) if bkind == "brick" and not fort and rng.random() < 0.6 else -1
                        mb, h = building(name, bx, bz, wx, wz, H, bkind, rng, fire_face=fire, dark=burning)
                        bldgs.append(mb)
                        COLS.append((bx - wx / 2, bx + wx / 2, bz - wz / 2, bz + wz / 2, 0.0, 3.0))
                        if fort:
                            fort_decor(mb, bx, bz, wx, wz, n_floors, rng)
                        if burning:
                            smoke_decor(mb, bx, bz, wx, wz, n_floors, rng)
                # alley clutter: two dumpsters and bags in the cross alley
                for sx, sz in ((-1, 1), (1, -1)):
                    x, z = cx + sx * 1.9, cz + sz * 13.0
                    dumpster(furn, x, z, 0.0, WALK_H)
                    COLS.append(footprint_col(x, z, 0.0, 1.2, 0.6))
                    for _ in range(2):
                        blob(furn, (x + rng.uniform(-0.8, 0.8), WALK_H + 0.2, z + rng.uniform(-1.8, 1.8)),
                             0.3, "bag", rng)
                # trees along the sidewalks and lamp furniture on the kerb sides
                for side, (ex, ez) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
                    if rng.random() < 0.5:
                        for along in (-6.0, 6.0):
                            if rng.random() < 0.6:
                                if ez:
                                    x, z = cx + along, cz + ez * 20.0
                                else:
                                    x, z = cx + ex * 20.0, cz + along
                                tree(trees, x, z, rng.uniform(0.85, 1.1), rng, WALK_H)
                                TREE_SPOTS.append((x, z, 1.0))
                    if rng.random() < 0.35:
                        along = rng.choice([-10.0, 10.0])
                        if ez:
                            x, z, r = cx + along, cz + ez * 20.4, math.pi / 2
                        else:
                            x, z, r = cx + ex * 20.4, cz + along, 0.0
                        bench(furn, x, z, r, WALK_H)
                        COLS.append(footprint_col(x, z, r, 0.9, 0.3))
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
                if (i, j) in FLOOD:
                    flood_tower(flood, cx, cz)
            if rng.random() < 0.4:
                x = cx + rng.choice([-1, 1]) * 20.0
                z = cz + rng.choice([-1, 1]) * 20.0
                rot = 0.0 if rng.random() < 0.5 else math.pi / 2
                barrier(furn, x, z, rot, WALK_H)
                COLS.append(footprint_col(x, z, rot, 1.5, 0.3))

    print("MAP stage: checkpoints, ring, wrecks")
    for axis, R, A, cs, veh in CHECKPOINTS:
        checkpoint(axis, R, A, cs, veh, furn, mil, rng)

    # ring: background towers beyond the playable grid
    for cx, cz in ring_blocks:
        W = D = rng.choice([26.0, 28.0, 30.0, 32.0, 34.0])
        H = rng.uniform(45.0, 95.0)
        mb, h = building(f"Ring_{int(cx)}_{int(cz)}", cx, cz, W, D, H, "ring", rng, dark=rng.random() < 0.25)
        bldgs.append(mb)
        COLS.append((cx - W / 2, cx + W / 2, cz - D / 2, cz + D / 2, 0.0, 3.0))
        if rng.random() < 0.25:
            smoke_decor(mb, cx, cz, W, D, int(round((h - GH) / FH)), rng)

    # abandoned cars along the kerbs of the outer blocks (away from the square)
    cand = []
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            if ROWS[j][i] in ("T", "Q") and max(abs(cx), abs(cz)) >= 112:
                cand.append((cx + 23.2, cz + rng.uniform(-12, 12), 0.0))
                cand.append((cx + rng.uniform(-12, 12), cz + 23.2, math.pi / 2))
    rng.shuffle(cand)
    kerb_cars = 0
    for x, z, r in cand:
        if kerb_cars >= 8:
            break
        car(cars, x, z, r, rng.choice(PAINTS), 0.0, rng.random() < 0.15, rng)
        CAR_SPOTS.append((x, z, r, False))
        COLS.append(footprint_col(x, z, r, 2.3, 0.95))
        kerb_cars += 1
    for (rc, bc_, off) in [(84.0, -56.0, 3.2), (-84.0, 56.0, -3.2), (28.0, -112.0, 3.2)]:
        x, z = rc + off, bc_
        car(cars, x, z, 0.0, "burnt", 0.0, True, rng)
        CAR_SPOTS.append((x, z, 0.0, True))
        COLS.append(footprint_col(x, z, 0.0, 2.3, 0.95))

    # debris on the roads and sidewalks (not solid)
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
        if abs(x) < 23 and abs(z) < 23:      # never inside the empty centre block
            continue
        obox(debris, (x, 0.3, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.42, 0.3, 0.3), "cardboard")

    # street lamps: the pole, arm and head, one joined mesh
    for (x, z, r) in LAMP_POLES:
        lamp_post(street_lamps, x, z, r)
        COLS.append((x - 0.15, x + 0.15, z - 0.15, z + 0.15, 0.0, 3.0))

    meshes = [ground_road, ground_side, ground_lot, markings, furn, trees, cars, mil, flood, street_lamps,
              debris] + bldgs
    groups = {}
    for mb in meshes:
        key = mb.name.split("_")[0] if mb.name.startswith(("Bldg", "Ring")) else mb.name
        groups[key] = groups.get(key, 0) + mb.tris()
    print("MAP tris by group", {k: v for k, v in sorted(groups.items(), key=lambda kv: -kv[1])})
    print("MAP tris ring towers", sum(mb.tris() for mb in bldgs if mb.name.startswith("Ring")),
          "tower Bldg", sum(mb.tris() for mb in bldgs if mb.name.endswith("tower")),
          "Q/F corners", sum(mb.tris() for mb in bldgs if mb.name.startswith("Bldg") and not mb.name.endswith("tower")))
    bad = check_centre(meshes)
    print("MAP centre check: intrusions into the empty centre block =", bad)

    print("MAP stage: build objects")
    objs = []
    for mb in meshes:
        if mb.faces:
            objs.append(mb.build(coll))
    tri_total = sum(mb.tris() for mb in meshes)

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
    tri_total += 12 * len(COLS)
    print(f"MAP counts: COL={len(COLS)} LAMP={len(LAMPS)} (street={len(LAMP_POLES)}, floodlights={len(FLOOD)}) "
          f"tris~{tri_total} buildings={len(bldgs)} trees={len(TREE_SPOTS)} cars={len(CAR_SPOTS)} "
          f"collapses={collapses}")

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
    sun = bkit.sun(elevation=38, azimuth=150, strength=2.6, softness=1.5)
    cols = [o for o in objs if o.name.startswith("COL_") or o.name.startswith("LAMP_")]
    for o in cols:
        o.hide_render = True
    wanted = [w.strip() for w in RENDER_LIST.split(",") if w.strip()]
    for name in wanted:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
            scene.camera = cam
        elif name == "corner":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.66)
            cam = make_camera("CamCorner", (-112, 92, -118), (-22, 4, -26), lens=34.0)
            scene.camera = cam
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (-28.0, 1.7, -42.0), (-28.0, 1.2, -6.0), lens=26.0)
            scene.camera = cam
        else:
            continue
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
