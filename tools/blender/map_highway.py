"""撤離公路 (evacuation highway) level map for 射擊遊戲, built headless with the blender-modeling skill.

Run from the project root:   blender -b -P tools/blender/map_highway.py
Writes assets/models/map_highway.glb and previews to .claude/work/.

Same grid and conventions as map_downtown.py: game coordinates (x, y up, z on the ground),
G(x, y, z) = (x, -z, y) when each mesh is created.

Gameplay data read by the game:
  COL_<n>   axis-aligned box = a collider (cars, buildings, billboard posts, fence panels, poles...)
  LAMP_<n>  empty at a lamp head = a night light (intersections and the gas station)
  FIRE_<n>  empty 1.3 m above a burnt wreck = the game sets it on fire
  Ground*   ground meshes (roads, grass, markings) - they do not cast shadows

Vehicles are linked duplicates: one mesh per (type, paint, wrecked, door open) is built once
and every car is an object that points at it, so the file holds each shape only once.

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
TEX_DIR = os.path.join(WORK, "map_highway_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_highway.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_highway_top.png"),
    "street": os.path.join(WORK, "map_highway_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "40"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 23

# ---------------------------------------------------------------- layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide, 4 lanes
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # block centres
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                              # block half size (44 m)
WALK_H = 0.16                                            # block slab top
GH = 4.4
FH = 3.6
ROAD_HALF = 6.0
LANE_X = (-4.5, -1.5, 1.5, 4.5)                          # lane centres from the road centre line
INSET = 21.2                                             # poles 0.8 m inside a block edge
CORNER = 6.8                                             # poles at intersection corners
START = (-28.0, 0.0)                                     # player start (road x=-28)
GRASS_Y = WALK_H + 0.012
DIRT_Y = WALK_H + 0.03
PAINT_Y = 0.012
AX = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
UPV = (0.0, 1.0, 0.0)

# block kinds: row j = z index, column i = x index. GAS is the centre block.
ROWS = {
    0: ["field", "motel", "farm", "billboard", "field"],
    1: ["farm", "field", "motel", "field", "billboard"],
    2: ["motel", "billboard", "GAS", "field", "farm"],
    3: ["field", "farm", "field", "motel", "field"],
    4: ["billboard", "field", "motel", "farm", "field"],
}

# free stretches of road between intersections (same on every road)
FREE = [(ROADS[i] + ROAD_HALF, ROADS[i + 1] - ROAD_HALF) for i in range(len(ROADS) - 1)]

MAT = {}
TILE = {}
COLS = []        # (x0, x1, z0, z1, y0, y1) collider boxes
LAMPS = []       # (x, y, z) light positions
LAMP_POLES = []  # (x, z, rot) street lamp posts
FIRES = []       # (x, y, z) burning wrecks
VEH_TPL = {}     # (kind, paint, wrecked, door) -> (mesh data, tris)
VEH_OBJS = []    # instance objects (link duplicates)
VEH_TRIS = []    # tris per instance
VEH_HALF = {"sedan": (2.25, 0.95, 1.6), "suv": (2.45, 1.0, 1.9), "van": (2.6, 1.0, 2.3),
            "truck": (4.6, 1.2, 3.3), "bus": (6.0, 1.3, 3.3)}
PAINTS = ["car_red", "car_blue", "car_white", "car_silver", "car_black", "car_green", "car_yellow"]
SIGNS = ["sign_red", "sign_navy", "sign_green", "sign_ochre", "sign_cream", "sign_dark"]
AWNINGS = ["awning_red", "awning_green", "awning_cream", "awning_navy"]


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
    """Collects polygons in game coordinates, then becomes one Blender mesh.

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
        tile = TILE.get(mat, 1.0)
        uv = [(p[ua] / tile, p[va] / tile) for p in clean]
        self.faces.append(([self._vi(p) for p in clean], mat, uv))

    def to_data(self, name):
        me = bpy.data.meshes.new(name)
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
        return me

    def build(self, coll):
        obj = bpy.data.objects.new(self.name, self.to_data(self.name))
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
    """Lumpy low-poly sphere for tree canopies and hills."""
    grid = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        row = []
        for j in range(segs):
            th = 2 * math.pi * j / segs
            rr = r * (1 + rng.uniform(-0.12, 0.12)) if 0 < i < rings else r
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


def quad_v(mb, pts, mat, n):
    mb.poly(pts, mat, n)


# ---------------------------------------------------------------- materials
# name: (Poly Haven texture, tile size in metres, optional tint multiplied over the colour map)
PH_SETS = {
    "asphalt": ("asphalt_02", 4.0, None),
    "sidewalk": ("concrete_pavement", 2.0, None),
    "concrete": ("concrete_wall_004", 3.0, None),
    "motel_wall": ("concrete_wall_004", 3.0, (0.86, 0.78, 0.64)),
    "brick": ("brick_wall_001", 2.0, None),
    "roof": ("tarred_gravel", 3.0, None),
    "bark": ("bark_brown_02", 1.2, None),
    "dead_bark": ("bark_brown_02", 1.2, (0.82, 0.80, 0.76)),
    "barn": ("plywood", 1.2, (0.62, 0.27, 0.19)),
    "plywood": ("plywood", 1.2, None),
    "dry_grass": ("aerial_grass_rock", 6.0, (0.90, 0.78, 0.50)),
    "dark_hill": ("aerial_grass_rock", 16.0, (0.30, 0.28, 0.22)),
    "dirt": ("dry_ground_01", 3.0, None),
    "gravel": ("gravel_road", 3.0, None),
    "corrugated": ("corrugated_iron_02", 1.5, None),
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
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "paint_yellow": ((0.80, 0.58, 0.08), 0.6, 0.0, 0.5),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "glass_car": ((0.04, 0.07, 0.09), 0.05, 0.0, 0.8),
    "burnt": ((0.035, 0.03, 0.028), 0.9, 0.0, 0.3),
    "headlight": ((0.95, 0.92, 0.84), 0.2, 0.0, 0.6),
    "tail": ((0.55, 0.05, 0.04), 0.3, 0.0, 0.5),
    "sign_red": ((0.42, 0.08, 0.06), 0.5, 0.0, 0.5),
    "sign_navy": ((0.07, 0.10, 0.26), 0.5, 0.0, 0.5),
    "sign_green": ((0.07, 0.22, 0.11), 0.5, 0.0, 0.5),
    "sign_ochre": ((0.60, 0.42, 0.10), 0.5, 0.0, 0.5),
    "sign_cream": ((0.66, 0.61, 0.50), 0.5, 0.0, 0.5),
    "sign_dark": ((0.09, 0.09, 0.10), 0.5, 0.0, 0.5),
    "awning_red": ((0.48, 0.09, 0.07), 0.9, 0.0, 0.3),
    "awning_green": ((0.07, 0.25, 0.14), 0.9, 0.0, 0.3),
    "awning_cream": ((0.62, 0.56, 0.42), 0.9, 0.0, 0.3),
    "awning_navy": ((0.07, 0.10, 0.25), 0.9, 0.0, 0.3),
    "car_red": ((0.50, 0.06, 0.05), 0.32, 0.25, 0.5),
    "car_blue": ((0.07, 0.17, 0.42), 0.32, 0.25, 0.5),
    "car_white": ((0.78, 0.78, 0.76), 0.35, 0.2, 0.5),
    "car_silver": ((0.45, 0.47, 0.50), 0.3, 0.45, 0.5),
    "car_black": ((0.03, 0.03, 0.035), 0.3, 0.3, 0.5),
    "car_green": ((0.13, 0.30, 0.16), 0.35, 0.25, 0.5),
    "car_yellow": ((0.72, 0.52, 0.10), 0.35, 0.2, 0.5),
    "bb_yellow": ((0.80, 0.66, 0.12), 0.5, 0.0, 0.5),
    "bb_red": ((0.55, 0.07, 0.05), 0.5, 0.0, 0.5),
    "bb_cream": ((0.74, 0.70, 0.60), 0.5, 0.0, 0.5),
    "fence_grey": ((0.40, 0.41, 0.42), 0.5, 0.8, 0.5),
    "hay": ((0.56, 0.43, 0.18), 0.9, 0.0, 0.3),
    "pump_red": ((0.55, 0.06, 0.05), 0.45, 0.2, 0.5),
    "silo": ((0.60, 0.60, 0.58), 0.4, 0.6, 0.5),
    "lug_red": ((0.45, 0.08, 0.06), 0.6, 0.0, 0.4),
    "lug_navy": ((0.08, 0.10, 0.22), 0.6, 0.0, 0.4),
    "lug_brown": ((0.36, 0.25, 0.14), 0.7, 0.0, 0.4),
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


def load_materials(tex_dir):
    bkit.CACHE = tex_dir
    for key, (aid, tile, tint) in PH_SETS.items():
        maps = bkit.polyhaven_texture(aid, res="1k")
        maps = {k: v for k, v in maps.items() if k in ("color", "normal", "roughness")}
        MAT[key] = bkit.pbr_material(key, maps, scale=1.0, tint=tint, coords="UV")
        TILE[key] = tile
        print("MAP texture", key, aid, sorted(maps))
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name in CONST:
        TILE.setdefault(name, 1.0)


# ---------------------------------------------------------------- collision helpers
def footprint_col(x, z, rot, half_len, half_wid, h=3.0):
    """Axis-aligned collider for a box at (x, z) heading rot (length along rot's forward)."""
    ex = half_len * abs(math.sin(rot)) + half_wid * abs(math.cos(rot))
    ez = half_len * abs(math.cos(rot)) + half_wid * abs(math.sin(rot))
    return (x - ex, x + ex, z - ez, z + ez, 0.0, h)


def clear(x, z, m=2.0):
    """True when (x, z) is outside every collider (plus margin m)."""
    for (x0, x1, z0, z1, _, _) in COLS:
        if x0 - m < x < x1 + m and z0 - m < z < z1 + m:
            return False
    return True


# ---------------------------------------------------------------- facades (as downtown)
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
            wbox(mb, fr, -0.2, L + 0.2, H - 0.7, H, 0.0, 0.42, "concrete")
        wbox(mb, fr, 0.0, L, H, H + 0.9, 0.0, 0.22, parapet_mat)
    mb.poly([(cx - hx, y0 + H, cz - hz), (cx + hx, y0 + H, cz - hz),
             (cx + hx, y0 + H, cz + hz), (cx - hx, y0 + H, cz + hz)], "roof", UPV)


def rooftop(mb, cx, cz, hx, hz, H, rng, tower=False):
    y = WALK_H + H
    for _ in range(rng.randint(1, 3)):
        x = cx + rng.uniform(-hx * 0.55, hx * 0.55)
        z = cz + rng.uniform(-hz * 0.55, hz * 0.55)
        obox(mb, (x, y + 0.55, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.85, 0.55, 0.6), "ac")
    if tower or rng.random() < 0.3:
        x = cx + rng.uniform(-hx * 0.5, hx * 0.5)
        z = cz + rng.uniform(-hz * 0.5, hz * 0.5)
        vcyl(mb, x, y, z, 0.05, 0.03, 6.0 if tower else 3.0, 6, "metal_dark")


def building(mb_name, cx, cz, W, D, H, kind, rng, fire_face=-1):
    """One tall building (the skyline): shell, storefronts, windows, roof. H above the sidewalk."""
    mb = Mesh(mb_name)
    hx, hz = W / 2, D / 2
    frames = face_frames(cx, cz, hx, hz, WALK_H)
    nf = max(1, round((H - GH) / FH))
    H = GH + nf * FH
    for fi, (fr, L) in enumerate(frames):
        bay_w = {"office": 3.5, "curtain": 4.0, "ring": 6.0}[kind]
        bays = max(2, round(L / bay_w))
        if kind == "office":
            st = {"band": "concrete", "upper": "concrete", "bf": 2, "win_w": 1.9, "win_h": 2.2}
        else:
            st = {"band": "concrete", "upper": "glass", "bf": 0, "win_w": 1.9, "win_h": 2.2,
                  "curtain": True, "spand_every": 1 if kind == "curtain" else 4, "decal": False}
        st.update({"bays": bays, "nf": nf, "kind": kind, "sign": rng.choice(SIGNS),
                   "door": rng.randrange(bays) if rng.random() < 0.6 else -1,
                   "awning": rng.choice(AWNINGS) if rng.random() < 0.5 else None,
                   "belts": kind == "office", "pilaster": kind == "office",
                   "fire": -1})
        wall_face(mb, fr, L, H, st, rng)
    parapet = "concrete" if kind == "office" else "frame_dark"
    roof_and_top(mb, cx, cz, hx, hz, H, {"kind": kind}, rng, parapet)
    rooftop(mb, cx, cz, hx, hz, H, rng, tower=(kind == "curtain" and W > 30))
    return mb, H


# ---------------------------------------------------------------- roadside pieces
def block_slab(mb, cx, cz):
    """Raised sidewalk slab with a kerb face on each side."""
    h = WALK_H
    x0, x1, z0, z1 = cx - HALF, cx + HALF, cz - HALF, cz + HALF
    mb.poly([(x0, h, z0), (x1, h, z0), (x1, h, z1), (x0, h, z1)], "sidewalk", UPV)
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], "concrete", (0, 0, -1))
    mb.poly([(x0, 0, z1), (x0, h, z1), (x1, h, z1), (x1, 0, z1)], "concrete", (0, 0, 1))
    mb.poly([(x0, 0, z0), (x0, h, z0), (x0, h, z1), (x0, 0, z1)], "concrete", (-1, 0, 0))
    mb.poly([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], "concrete", (1, 0, 0))


def lamp_post(mb, x, z, rot):
    dx, dz = math.sin(rot), math.cos(rot)
    lat = (math.cos(rot), 0.0, -math.sin(rot))
    vcyl(mb, x, WALK_H, z, 0.09, 0.065, 6.84, 8, "metal_dark")
    ax = [(dx, 0.0, dz), UPV, lat]
    obox(mb, (x + dx * 0.78, 6.92, z + dz * 0.78), ax, (0.78, 0.04, 0.04), "metal_dark")
    obox(mb, (x + dx * 1.55, 6.82, z + dz * 1.55), ax, (0.31, 0.06, 0.17), "lamp_head")
    LAMPS.append((x + dx * 1.55, 6.3, z + dz * 1.55))


def fence_run(mb, p0, p1, skip=()):
    """Chain-link run from p0 to p1 (same x or same z) in 4.2 m panels; skip = gate indices."""
    (x0, z0), (x1, z1) = p0, p1
    L = math.hypot(x1 - x0, z1 - z0)
    n = max(1, round(L / 4.2))
    seg = L / n
    dv = ((x1 - x0) / L, 0.0, (z1 - z0) / L)
    nrm = (-dv[2], 0.0, dv[0])
    ax = [dv, UPV, nrm]
    for k in range(n):
        if k in skip:
            continue
        mx = x0 + (x1 - x0) * (k + 0.5) / n
        mz = z0 + (z1 - z0) * (k + 0.5) / n
        obox(mb, (mx, WALK_H + 0.85, mz), ax, (seg / 2 - 0.03, 0.85, 0.025), "fence_grey")
        obox(mb, (mx, WALK_H + 1.72, mz), ax, (seg / 2, 0.03, 0.04), "metal_dark")
        px = x0 + (x1 - x0) * k / n
        pz = z0 + (z1 - z0) * k / n
        obox(mb, (px, WALK_H + 0.9, pz), ax, (0.04, 0.9, 0.04), "metal_dark")
        if abs(dv[0]) > 0.5:
            COLS.append((mx - seg / 2, mx + seg / 2, mz - 0.06, mz + 0.06, WALK_H, WALK_H + 1.8))
        else:
            COLS.append((mx - 0.06, mx + 0.06, mz - seg / 2, mz + seg / 2, WALK_H, WALK_H + 1.8))


def dead_tree(mb, x, z, s, rng):
    """Withered tree: bare trunk with a few broken limbs. Trunk collider."""
    h = 5.2 * s
    ocyl(mb, (x, WALK_H + h / 2, z), (0, 1, 0), 0.22 * s, 0.09 * s, h, 7, "dead_bark", caps=True)
    for _ in range(rng.randint(3, 5)):
        t = rng.uniform(0.5, 0.92)
        y = WALK_H + h * t
        az = rng.uniform(0, 2 * math.pi)
        th = rng.uniform(0.5, 1.0)
        d = (math.sin(th) * math.cos(az), math.cos(th), math.sin(th) * math.sin(az))
        L = rng.uniform(1.4, 2.6) * s
        c = (x + d[0] * L / 2, y + d[1] * L / 2, z + d[2] * L / 2)
        ocyl(mb, c, d, 0.07 * s, 0.02 * s, L, 5, "dead_bark", caps=False)
    COLS.append((x - 0.3, x + 0.3, z - 0.3, z + 0.3, 0.0, 3.0))


def dead_spot(cx, cz, rng, reach=17.0):
    for _ in range(40):
        x = cx + rng.uniform(-reach, reach)
        z = cz + rng.uniform(-reach, reach)
        if clear(x, z, 2.2) and math.hypot(x - START[0], z - START[1]) > 8:
            return x, z
    return None


def barn(mb, x0, x1, z0, z1, y0, hw, hr):
    """Gable barn with its ridge along x: walls, two roof planes, gable ends, a door."""
    xc, zc = (x0 + x1) / 2, (z0 + z1) / 2
    obox(mb, (xc, y0 + hw / 2, zc), AX, ((x1 - x0) / 2, hw / 2, (z1 - z0) / 2), "barn")
    rise = hr - hw
    w1 = zc - z0
    mb.poly([(x0 - 0.3, y0 + hw, z0 - 0.3), (x1 + 0.3, y0 + hw, z0 - 0.3),
             (x1 + 0.3, y0 + hr, zc), (x0 - 0.3, y0 + hr, zc)], "corrugated", (0, w1, -rise))
    w2 = z1 - zc
    mb.poly([(x0 - 0.3, y0 + hr, zc), (x1 + 0.3, y0 + hr, zc),
             (x1 + 0.3, y0 + hw, z1 + 0.3), (x0 - 0.3, y0 + hw, z1 + 0.3)], "corrugated", (0, w2, rise))
    for xe, ne in ((x0, -1), (x1, 1)):
        mb.poly([(xe, y0 + hw, z0), (xe, y0 + hw, z1), (xe, y0 + hr, zc)], "barn", (ne, 0, 0))
    xm = xc
    mb.poly([(xm - 1.8, y0, z0 - 0.03), (xm + 1.8, y0, z0 - 0.03), (xm + 1.8, y0 + 3.9, z0 - 0.03),
             (xm - 1.8, y0 + 3.9, z0 - 0.03)], "door", (0, 0, -1))


def motel(cx, cz, bld, furn, lot, rng):
    """Single-storey roadside motel: a row of doors and windows, a tall neon sign."""
    zc = cz + 11.0
    obox(bld, (cx, WALK_H + 1.8, zc), AX, (15.0, 1.8, 4.0), "motel_wall")
    obox(bld, (cx, WALK_H + 3.72, zc), AX, (15.3, 0.12, 4.3), "roof")
    zf = zc - 4.03
    for k in range(9):
        x0 = cx - 12.0 + k * 3.0
        bld.poly([(x0, WALK_H, zf), (x0 + 0.9, WALK_H, zf), (x0 + 0.9, WALK_H + 2.2, zf),
                  (x0, WALK_H + 2.2, zf)], "door", (0, 0, -1))
        bld.poly([(x0 + 1.1, WALK_H + 1.0, zf), (x0 + 2.4, WALK_H + 1.0, zf),
                  (x0 + 2.4, WALK_H + 2.1, zf), (x0 + 1.1, WALK_H + 2.1, zf)], "glass", (0, 0, -1))
    COLS.append((cx - 15.0, cx + 15.0, zc - 4.0, zc + 4.0, WALK_H, WALK_H + 3.6))
    rect_at(lot, cx - 20.0, cx + 20.0, cz - 6.0, zc - 4.0, DIRT_Y, "asphalt")
    px, pz = cx + 18.0, cz + 18.0
    vcyl(furn, px, WALK_H, pz, 0.18, 0.18, 8.0, 8, "metal")
    obox(furn, (px, WALK_H + 9.2, pz), AX, (1.8, 1.0, 0.14), "sign_red")
    obox(furn, (px, WALK_H + 10.4, pz), AX, (1.8, 0.2, 0.14), "sign_cream")
    COLS.append((px - 0.3, px + 0.3, pz - 0.3, pz + 0.3, WALK_H, WALK_H + 3.0))


def billboard(cx, cz, rng, furn):
    """Large billboard on two tall steel posts, face turned to the road."""
    dx, dz = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
    px, pz = cx + 17.0 * dx, cz + 17.0 * dz
    t = (0.0, 0.0, 1.0) if dx != 0 else (1.0, 0.0, 0.0)
    n = (float(dx), 0.0, float(dz))
    face = rng.choice(["bb_yellow", "bb_red", "bb_cream"])
    mats = ["metal_dark"] * 6
    mats[4] = face
    obox(furn, (px, WALK_H + 11.0, pz), [t, UPV, n], (4.5, 3.0, 0.15), mats)
    for sg in (-1, 1):
        qx, qz = px + t[0] * 3.2 * sg, pz + t[2] * 3.2 * sg
        vcyl(furn, qx, WALK_H, qz, 0.2, 0.2, 8.0, 8, "metal_dark")
        COLS.append((qx - 0.3, qx + 0.3, qz - 0.3, qz + 0.3, 0.0, 3.0))


def farm(cx, cz, rng, bld, furn, lot, fence, trees):
    rect_at(lot, cx - 19.0, cx + 19.0, cz - 19.0, cz + 19.0, DIRT_Y, "dirt")
    barn(bld, cx - 16.0, cx - 2.0, cz + 4.0, cz + 12.0, WALK_H, 5.6, 8.4)
    COLS.append((cx - 16.0, cx - 2.0, cz + 4.0, cz + 12.0, WALK_H, WALK_H + 5.6))
    vcyl(furn, cx + 10.0, WALK_H, cz - 9.0, 3.0, 3.0, 11.0, 14, "silo")
    ocyl(furn, (cx + 10.0, WALK_H + 11.9, cz - 9.0), (0, 1, 0), 3.0, 0.4, 1.8, 14, "silo")
    COLS.append((cx + 7.0, cx + 13.0, cz - 12.0, cz - 6.0, WALK_H, WALK_H + 11.0))
    for hz in (cz + 3.5, cz + 6.5):
        ocyl(furn, (cx + 7.5, WALK_H + 0.7, hz), (1, 0, 0), 0.7, 0.7, 1.4, 10, "hay")
    fence_run(fence, (cx - 19.0, cz - 19.0), (cx + 19.0, cz - 19.0), skip=(4,))
    fence_run(fence, (cx - 19.0, cz + 19.0), (cx + 19.0, cz + 19.0))
    fence_run(fence, (cx - 19.0, cz - 19.0), (cx - 19.0, cz + 19.0))
    fence_run(fence, (cx + 19.0, cz - 19.0), (cx + 19.0, cz + 19.0))
    for _ in range(2):
        s = dead_spot(cx, cz, rng, 15.0)
        if s:
            dead_tree(trees, s[0], s[1], rng.uniform(0.9, 1.15), rng)


def field(cx, cz, rng, lot, fence, trees):
    for _ in range(rng.randint(2, 4)):
        px = cx + rng.uniform(-14.0, 14.0)
        pz = cz + rng.uniform(-14.0, 14.0)
        w, d = rng.uniform(4.0, 9.0), rng.uniform(4.0, 9.0)
        rect_at(lot, px - w / 2, px + w / 2, pz - d / 2, pz + d / 2, DIRT_Y, "dirt")
    if rng.random() < 0.6:
        fence_run(fence, (cx - HALF + 2.0, cz + 20.0), (cx + HALF - 2.0, cz + 20.0), skip=(3,))
    if rng.random() < 0.5:
        fence_run(fence, (cx + 20.0, cz - HALF + 2.0), (cx + 20.0, cz + HALF - 2.0), skip=(3,))
    for _ in range(rng.randint(2, 4)):
        s = dead_spot(cx, cz, rng)
        if s:
            dead_tree(trees, s[0], s[1], rng.uniform(0.8, 1.2), rng)


def gas_station(cx, cz, rng, furn, lot, bld, street):
    """Filling station: canopy with lights over four pump islands, convenience store,
    price sign, lot lamps and an overturned tanker."""
    rect_at(lot, cx - HALF, cx + HALF, cz - HALF, cz + HALF, DIRT_Y, "asphalt")
    # canopy: slab, red fascia on both long sides, four columns
    obox(furn, (cx, WALK_H + 5.15, cz), AX, (9.0, 0.25, 6.0), "paint_white")
    obox(furn, (cx, WALK_H + 4.9, cz - 6.0), AX, (9.0, 0.45, 0.08), "sign_red")
    obox(furn, (cx, WALK_H + 4.9, cz + 6.0), AX, (9.0, 0.45, 0.08), "sign_red")
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = cx + sx * 8.4, cz + sz * 5.4
            vcyl(furn, x, WALK_H, z, 0.28, 0.28, 4.9, 8, "metal")
            COLS.append((x - 0.3, x + 0.3, z - 0.3, z + 0.3, WALK_H, WALK_H + 4.9))
    # four pump islands with two pumps each
    for sx in (-1, 1):
        for sz in (-1, 1):
            ix, iz = cx + sx * 4.6, cz + sz * 2.6
            obox(furn, (ix, WALK_H + 0.07, iz), AX, (1.9, 0.07, 0.6), "concrete")
            for px in (-1.3, 1.3):
                obox(furn, (ix + px, WALK_H + 0.85, iz), AX, (0.28, 0.75, 0.22), "pump_red")
            COLS.append((ix - 1.9, ix + 1.9, iz - 0.6, iz + 0.6, WALK_H, WALK_H + 1.6))
    # canopy lights (LAMP_ at each head)
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = cx + sx * 6.0, cz + sz * 4.2
            obox(furn, (x, WALK_H + 4.88, z), AX, (0.5, 0.06, 0.3), "lamp_head")
            LAMPS.append((x, WALK_H + 4.8, z))
    # convenience store behind the canopy, glass front facing the pumps
    sxc, szc = cx - 10.0, cz + 13.5
    obox(bld, (sxc, WALK_H + 1.8, szc), AX, (7.0, 1.8, 4.5), "brick")
    zf = szc - 4.5 - 0.03
    bld.poly([(sxc - 6.2, WALK_H + 0.4, zf), (sxc + 5.6, WALK_H + 0.4, zf),
              (sxc + 5.6, WALK_H + 3.0, zf), (sxc - 6.2, WALK_H + 3.0, zf)], "glass", (0, 0, -1))
    bld.poly([(sxc + 5.8, WALK_H, zf), (sxc + 6.7, WALK_H, zf), (sxc + 6.7, WALK_H + 2.4, zf),
              (sxc + 5.8, WALK_H + 2.4, zf)], "door", (0, 0, -1))
    obox(bld, (sxc, WALK_H + 3.75, szc - 4.6), AX, (7.0, 0.42, 0.1), "sign_red")
    obox(bld, (sxc, WALK_H + 3.72, szc), AX, (7.2, 0.12, 4.7), "roof")
    COLS.append((sxc - 7.0, sxc + 7.0, szc - 4.5, szc + 4.5, WALK_H, WALK_H + 3.6))
    # price sign pole
    px_, pz_ = cx + 14.0, cz - 15.0
    vcyl(furn, px_, WALK_H, pz_, 0.2, 0.2, 7.0, 8, "metal")
    obox(furn, (px_, WALK_H + 7.4, pz_), AX, (1.5, 1.1, 0.12), "sign_red")
    obox(furn, (px_, WALK_H + 5.7, pz_), AX, (1.5, 0.5, 0.1), "sign_dark")
    COLS.append((px_ - 0.3, px_ + 0.3, pz_ - 0.3, pz_ + 0.3, WALK_H, WALK_H + 3.0))
    # overturned tanker on the lot: tank lying on its side, cab beside it
    tz = cz - 16.5
    ocyl(furn, (cx + 3.0, WALK_H + 1.5, tz), (1, 0, 0), 1.5, 1.5, 10.0, 14, "car_white")
    obox(furn, (cx + 9.6, WALK_H + 1.2, tz), AX, (1.7, 1.2, 1.4), "car_red")
    COLS.append((cx - 2.0, cx + 11.3, tz - 1.8, tz + 1.8, WALK_H, WALK_H + 3.0))
    # two lot lamps
    for (x, z, r) in ((cx - 20.2, cz - 8.0, math.pi / 2), (cx + 20.2, cz + 8.0, -math.pi / 2)):
        lamp_post(street, x, z, r)
        COLS.append((x - 0.15, x + 0.15, z - 0.15, z + 0.15, 0.0, 3.0))


# ---------------------------------------------------------------- vehicles
def vehicle_mesh(mb, kind, paint, wrecked, door):
    """One vehicle at the origin heading +z (rot 0). door = 0 closed, or -1/+1 for an open side door."""
    ax = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    lift = -0.06 if wrecked else 0.0
    bm = "burnt" if wrecked else paint

    def C(x, y, z):
        return (x, y + lift, z)

    def lights(hz, hx, y):
        if wrecked:
            return
        for sx in (-1, 1):
            obox(mb, C(sx * hx, y, hz), ax, (0.18, 0.07, 0.04), "headlight")
            obox(mb, C(sx * hx, y, -hz), ax, (0.18, 0.07, 0.04), "tail")

    door_hz = 0.0
    if kind == "sedan":
        obox(mb, C(0, 0.52, 0), ax, (0.9, 0.24, 2.25), bm)
        obox(mb, C(0, 1.08, -0.25), ax, (0.8, 0.27, 1.2), ["glass_car", "glass_car", bm, "dark", "glass_car", "glass_car"])
        wr, wheels, hz_l, door_hz, door_hw = 0.36, [(-0.8, 1.45), (0.8, 1.45), (-0.8, -1.45), (0.8, -1.45)], 2.25, 0.9, 0.9
        lights(hz_l, 0.6, 0.66)
    elif kind == "suv":
        obox(mb, C(0, 0.74, 0), ax, (0.98, 0.4, 2.4), bm)
        obox(mb, C(0, 1.5, -0.2), ax, (0.9, 0.36, 1.45), ["glass_car", "glass_car", bm, "dark", "glass_car", "glass_car"])
        wr, wheels, hz_l, door_hz, door_hw = 0.4, [(-0.85, 1.6), (0.85, 1.6), (-0.85, -1.5), (0.85, -1.5)], 2.4, 1.0, 0.98
        lights(hz_l, 0.62, 0.76)
    elif kind == "van":
        obox(mb, C(0, 1.2, 0), ax, (1.0, 0.85, 2.6), bm)
        obox(mb, C(0, 1.5, 2.6), ax, (0.88, 0.28, 0.02), "glass_car")
        wr, wheels, hz_l, door_hz, door_hw = 0.38, [(-0.9, 1.6), (0.9, 1.6), (-0.9, -1.6), (0.9, -1.6)], 2.6, 1.3, 1.0
        lights(hz_l, 0.7, 0.9)
    elif kind == "truck":
        obox(mb, C(0, 1.3, 3.2), ax, (1.15, 0.9, 1.2), bm)
        obox(mb, C(0, 1.55, 4.42), ax, (1.0, 0.3, 0.02), "glass_car")
        obox(mb, C(0, 0.35, 0), ax, (1.05, 0.12, 4.4), "dark")
        obox(mb, C(0, 1.85, -1.25), ax, (1.2, 1.35, 3.25), "car_silver")
        wr, wheels, hz_l = 0.45, [(-1.0, 3.5), (1.0, 3.5), (-1.0, -2.6), (1.0, -2.6), (-1.0, -3.9), (1.0, -3.9)], 4.4
    else:  # bus
        obox(mb, C(0, 1.9, 0), ax, (1.25, 1.2, 6.0), bm)
        for sx in (-1, 1):
            obox(mb, C(sx * 1.26, 2.5, 0), ax, (0.03, 0.35, 5.5), "glass_car")
        obox(mb, C(0, 2.1, 6.02), ax, (1.0, 0.8, 0.02), "glass_car")
        wr, wheels, hz_l = 0.5, [(-1.1, 4.3), (1.1, 4.3), (-1.1, -4.3), (1.1, -4.3)], 6.0
    for k, (x, z) in enumerate(wheels):
        if wrecked and k in (1, 2):
            continue  # torn-off wheels on a wreck
        ocyl(mb, C(x, wr, z), (1.0, 0.0, 0.0), wr, wr, 0.26, 10, "tire")
    if door and not wrecked and kind in ("sedan", "suv", "van"):
        # side door swung open ~70 degrees
        dv = (door * math.sin(math.radians(70)), 0.0, -math.cos(math.radians(70)))
        hinge = (door * door_hw, 0.55, door_hz)
        c = vadd(hinge, vmul(dv, 0.5))
        n3 = vnorm(vcross(dv, UPV))
        obox(mb, c, [dv, UPV, n3], (0.5, 0.42, 0.03), bm)


def vehicle_template(kind, paint, wrecked, door):
    key = (kind, paint, wrecked, door)
    if key not in VEH_TPL:
        mb = Mesh(f"veh_{kind}_{paint}_{int(wrecked)}_{door}")
        vehicle_mesh(mb, kind, paint, wrecked, door)
        VEH_TPL[key] = (mb.to_data(mb.name), mb.tris())
    return VEH_TPL[key]


def spawn_vehicle(coll, kind, paint, x, z, rot, wrecked, door, n):
    me, tris = vehicle_template(kind, paint, wrecked, door)
    o = bpy.data.objects.new(f"Car_{n:03d}_{kind}", me)
    coll.objects.link(o)
    o.location = G((x, 0.02, z))
    o.rotation_euler = (0.0, 0.0, rot)
    hl, hw, hh = VEH_HALF[kind]
    COLS.append(footprint_col(x, z, rot, hl, hw, hh))
    VEH_OBJS.append(o)
    VEH_TRIS.append(tris)
    if wrecked:
        FIRES.append((x, 1.3, z))


def road_marks(mb, rc, axis, o0, o1, s0, s1, mat):
    """Paint strip across road rc (offset o0..o1 from its centre line), from s0 to s1 along it."""
    if axis == "z":
        rect_at(mb, rc + o0, rc + o1, s0, s1, PAINT_Y, mat)
    else:
        rect_at(mb, s0, s1, rc + o0, rc + o1, PAINT_Y, mat)


def jam(coll, rng):
    """Bumper-to-bumper evacuation traffic: 2-3 of the 4 lanes on every free stretch of road."""
    counts = {"truck": 0, "bus": 0}
    n = 0
    for axis in ("z", "x"):
        for rc in ROADS:
            for (a, b) in FREE:
                for li in rng.sample(range(4), rng.choice([2, 3])):
                    if rng.random() < 0.3:
                        continue
                    off = LANE_X[li]
                    if axis == "z":
                        rot = 0.0 if off < 0 else math.pi
                    else:
                        rot = math.pi / 2 if off < 0 else -math.pi / 2
                    s = a + rng.uniform(0.0, 1.2)
                    while True:
                        room = b - s
                        r = rng.random()
                        if r < 0.46:
                            kind = "sedan"
                        elif r < 0.66:
                            kind = "suv"
                        elif r < 0.82:
                            kind = "van"
                        elif r < 0.93 and counts["truck"] < 16 and room >= 9.4:
                            kind = "truck"
                        elif counts["bus"] < 4 and room >= 12.2:
                            kind = "bus"
                        else:
                            kind = "sedan"
                        hl, hw, hh = VEH_HALF[kind]
                        if 2 * hl > room:
                            break
                        c = s + hl
                        x, z = (rc + off, c) if axis == "z" else (c, rc + off)
                        if kind == "truck":
                            counts["truck"] += 1
                        if kind == "bus":
                            counts["bus"] += 1
                        if math.hypot(x - START[0], z - START[1]) > 10:
                            wrecked = rng.random() < 0.10
                            paint = "burnt" if wrecked else rng.choice(PAINTS)
                            door = 0
                            if not wrecked and kind in ("sedan", "suv", "van") and rng.random() < 0.22:
                                door = rng.choice((-1, 1))
                            crash = (not wrecked) and rng.random() < 0.05
                            yaw = rot + (rng.uniform(0.12, 0.25) * rng.choice((-1, 1)) if crash else 0.0)
                            spawn_vehicle(coll, kind, paint, x, z, yaw, wrecked, door, n)
                            n += 1
                        step = 2 * hl + (rng.uniform(0.2, 0.9) if rng.random() < 0.6 else rng.uniform(2.5, 6.0))
                        s += step
                        if s >= b - 2.0:
                            break
    return n


def luggage_and_debris(rng, debris, skid):
    """Suitcases spilled on the road and a few skid marks near the wrecks."""
    n = tries = 0
    while n < 40 and tries < 3000:
        tries += 1
        axis = rng.choice(("z", "x"))
        rc = rng.choice(ROADS)
        a, b = rng.choice(FREE)
        s = rng.uniform(a + 1.0, b - 1.0)
        off = rng.uniform(-5.0, 5.0)
        x, z = (rc + off, s) if axis == "z" else (s, rc + off)
        if math.hypot(x - START[0], z - START[1]) < 10:
            continue
        y = rng.uniform(0, 2 * math.pi)
        ax0 = (math.cos(y), 0.0, -math.sin(y))
        ax2 = (math.sin(y), 0.0, math.cos(y))
        obox(debris, (x, 0.13, z), [ax0, UPV, ax2], (0.45, 0.13, 0.28),
             rng.choice(["lug_red", "lug_navy", "lug_brown"]))
        n += 1
    for _ in range(25):
        axis = rng.choice(("z", "x"))
        rc = rng.choice(ROADS)
        a, b = rng.choice(FREE)
        s = rng.uniform(a + 2.0, b - 6.0)
        off = rng.uniform(-4.5, 4.5)
        L = rng.uniform(3.0, 6.0)
        if axis == "z":
            rect_at(skid, rc + off - 0.12, rc + off + 0.12, s, s + L, PAINT_Y + 0.002, "burnt")
        else:
            rect_at(skid, s, s + L, rc + off - 0.12, rc + off + 0.12, PAINT_Y + 0.002, "burnt")


# ---------------------------------------------------------------- power lines
def wire_span(mb, p0, p1, sag, mat, segs=5):
    pts = []
    for k in range(segs + 1):
        t = k / segs
        pts.append((p0[0] + (p1[0] - p0[0]) * t,
                    p0[1] + (p1[1] - p0[1]) * t - sag * 4 * t * (1 - t),
                    p0[2] + (p1[2] - p0[2]) * t))
    for k in range(segs):
        d = vadd(pts[k + 1], vmul(pts[k], -1))
        L = math.sqrt(vdot(d, d))
        a = vnorm(d)
        mid = vmul(vadd(pts[k + 1], pts[k]), 0.5)
        perp = vnorm(vcross(a, UPV))
        up2 = vcross(perp, a)
        obox(mb, mid, [a, perp, up2], (L / 2, 0.025, 0.025), mat)


def power_row(cz, xs, power):
    """Wooden poles along z=cz at x positions xs, two sagging wires between each pair."""
    for x in xs:
        vcyl(power, x, WALK_H, cz, 0.14, 0.11, 9.0, 7, "bark")
        obox(power, (x, WALK_H + 8.6, cz), AX, (0.06, 0.07, 0.9), "metal_dark")
    for xa, xb in zip(xs, xs[1:]):
        for h, sag in ((8.6, 0.8), (8.1, 0.7)):
            wire_span(power, (xa, WALK_H + h, cz), (xb, WALK_H + h, cz), sag, "metal_dark")


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
    load_materials(TEX_DIR)

    print("MAP stage: ground, blocks")
    ground_road = Mesh("Ground_road")
    ground_road.poly([(-200, 0, -200), (200, 0, -200), (200, 0, 200), (-200, 0, 200)], "asphalt", UPV)
    ground_side = Mesh("Ground_sidewalk")
    ground_grass = Mesh("Ground_grass")
    ground_lot = Mesh("Ground_lot")
    markings = Mesh("Ground_markings")
    skid = Mesh("Ground_skid")
    hills = Mesh("Ground_hills", smooth=True)
    furn = Mesh("Furniture")
    trees = Mesh("Trees", smooth=True)
    bld = Mesh("Buildings")
    fences = Mesh("Fences")
    power = Mesh("PowerLines", smooth=True)
    street_lamps = Mesh("StreetLamps")
    debris = Mesh("Debris")
    ring_meshes = []

    ring_blocks = [(x, z) for z in RING_C for x in RING_C if abs(x) == 168 or abs(z) == 168]

    # grid blocks: slab, grass, and their contents
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            kind = ROWS[j][i]
            block_slab(ground_side, cx, cz)
            if kind == "GAS":
                gas_station(cx, cz, rng, furn, ground_lot, bld, street_lamps)
                continue
            rect_at(ground_grass, cx - HALF, cx + HALF, cz - HALF, cz + HALF, GRASS_Y, "dry_grass")
            if kind == "motel":
                motel(cx, cz, bld, furn, ground_lot, rng)
                for _ in range(2):
                    s = dead_spot(cx, cz, rng)
                    if s:
                        dead_tree(trees, s[0], s[1], rng.uniform(0.8, 1.1), rng)
            elif kind == "farm":
                farm(cx, cz, rng, bld, furn, ground_lot, fences, trees)
            elif kind == "billboard":
                billboard(cx, cz, rng, furn)
                field(cx, cz, rng, ground_lot, fences, trees)
            else:
                field(cx, cz, rng, ground_lot, fences, trees)

    # outer ring: a skyline on the north side, dark hills everywhere else
    for cx, cz in ring_blocks:
        block_slab(ground_side, cx, cz)
        rect_at(ground_grass, cx - HALF, cx + HALF, cz - HALF, cz + HALF, GRASS_Y, "dry_grass")
        if cz == -168.0:
            W = D = rng.choice([26.0, 28.0, 30.0, 32.0, 34.0])
            H = rng.uniform(60.0, 110.0)
            mb, _ = building(f"Ring_{int(cx)}_{int(cz)}", cx, cz, W, D, H, "ring", rng)
            ring_meshes.append(mb)
            COLS.append((cx - W / 2, cx + W / 2, cz - D / 2, cz + D / 2, 0.0, 3.0))
        else:
            px = cx + 14.0 * (cx > 1) - 14.0 * (cx < -1)
            pz = cz + 14.0 * (cz > 1) - 14.0 * (cz < -1)
            blob(hills, (px, -10.0, pz), 40.0, "dark_hill", rng, rings=6, segs=12, sy=0.4)

    # roadside power lines: rows through the block edges, and along the far ring
    for cz in BC:
        power_row(cz, sorted(cx + s * INSET for cx in BC for s in (-1, 1)), power)
    power_row(168.0, sorted(cx + s * INSET for cx in RING_C for s in (-1, 1)), power)

    print("MAP stage: roads, markings, jam")
    for axis in ("z", "x"):
        for rc in ROADS:
            for (a, b) in FREE:
                road_marks(markings, rc, axis, -0.25, -0.08, a, b, "paint_yellow")
                road_marks(markings, rc, axis, 0.08, 0.25, a, b, "paint_yellow")
                for o in (-5.7, 5.7):
                    road_marks(markings, rc, axis, o - 0.13, o + 0.13, a, b, "paint_white")
                for o in (-3.0, 3.0):
                    t = a
                    while t < b - 0.1:
                        road_marks(markings, rc, axis, o - 0.07, o + 0.07, t, min(t + 3.0, b), "paint_white")
                        t += 6.0
    n_cars = jam(coll, rng)
    luggage_and_debris(rng, debris, skid)

    print("MAP stage: street lamps at intersections")
    for rc in ROADS:
        for rd in ROADS:
            for sx in (-1, 1):
                for sz in (-1, 1):
                    px, pz = rc + sx * CORNER, rd + sz * CORNER
                    LAMP_POLES.append((px, pz, math.atan2(-sx, -sz)))
    for (x, z, r) in LAMP_POLES:
        lamp_post(street_lamps, x, z, r)
        COLS.append((x - 0.15, x + 0.15, z - 0.15, z + 0.15, 0.0, 3.0))

    print("MAP stage: build objects")
    meshes = [ground_road, ground_side, ground_grass, ground_lot, markings, skid, hills, furn, trees,
              bld, fences, power, street_lamps, debris] + ring_meshes
    objs = []
    for mb in meshes:
        if mb.faces:
            objs.append(mb.build(coll))
    tri_unique = sum(mb.tris() for mb in meshes) + sum(t for _, t in VEH_TPL.values())
    tri_inst = sum(mb.tris() for mb in meshes) + sum(VEH_TRIS)

    # gameplay data: COL_ boxes (unit cube, scaled), LAMP_ and FIRE_ empties
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
    for i, (x, y, z) in enumerate(FIRES):
        o = bpy.data.objects.new(f"FIRE_{i + 1:03d}", None)
        o.empty_display_type = "PLAIN_AXES"
        o.empty_display_size = 0.4
        o.location = G((x, y, z))
        coll.objects.link(o)
        objs.append(o)
    objs.extend(VEH_OBJS)

    print(f"MAP counts: COL={len(COLS)} LAMP={len(LAMPS)} FIRE={len(FIRES)} cars={n_cars} "
          f"vehicle_templates={len(VEH_TPL)} tris_unique={tri_unique} tris_rendered={tri_inst} "
          f"lamp_poles={len(LAMP_POLES)} buildings_ring={len(ring_meshes)}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        for o in objs:
            if o.name.startswith("COL_"):
                o.hide_render = False
        bkit.export_glb(OUT_GLB, objs, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


# ---------------------------------------------------------------- lighting and previews
def setup_world():
    """Blood-red night: a dark red sky, lit by a low red moon and the lamps."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.10, 0.025, 0.02, 1)
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


def preview_extras(eye):
    """Preview-only helpers (not exported): a red moon and point lights at the lamps near the eye."""
    scene = bpy.context.scene
    extras = []
    bpy.ops.mesh.primitive_uv_sphere_add(radius=18.0, segments=24, ring_count=12, location=G((-28.0, 80.0, -260.0)))
    moon = bpy.context.active_object
    moon.name = "PV_moon"
    mm = bpy.data.materials.new("PV_moon_mat")
    mm.use_nodes = True
    bsdf = next(n for n in mm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.2, 0.05, 0.03, 1)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.16, 0.08, 1)
    bsdf.inputs["Emission Strength"].default_value = 6.0
    moon.data.materials.append(mm)
    extras.append(moon)
    for (x, y, z) in LAMPS:
        if math.hypot(x - eye[0], z - eye[1]) > 110:
            continue
        ld = bpy.data.lights.new("PV_lamp", "POINT")
        ld.energy = 260.0
        ld.color = (1.0, 0.76, 0.48)
        ld.shadow_soft_size = 0.3
        lo = bpy.data.objects.new("PV_lamp", ld)
        lo.location = G((x, y - 0.3, z))
        scene.collection.objects.link(lo)
        extras.append(lo)
    return extras


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
    moon_sun = bkit.sun(elevation=24, azimuth=205, strength=2.2, softness=2.0, color=(1.0, 0.34, 0.24))
    cols = [o for o in objs if o.name.startswith(("COL_", "LAMP_", "FIRE_"))]
    for o in cols:
        o.hide_render = True
    wanted = [w.strip() for w in RENDER_LIST.split(",") if w.strip()]
    for name in wanted:
        extras = []
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (-28.0, 1.7, 0.0), (-28.0, 1.4, -140.0), lens=26.0)
            extras = preview_extras((-28.0, 0.0))
        else:
            continue
        scene.camera = cam
        scene.render.filepath = PREVIEWS[name]
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("MAP preview", name, round(time.time() - t0, 1), "s ->", PREVIEWS[name])
        bpy.data.objects.remove(cam)
        for o in extras:
            bpy.data.objects.remove(o)
    bpy.data.objects.remove(moon_sun)
    for o in cols:
        o.hide_render = False


if __name__ == "__main__":
    main()
