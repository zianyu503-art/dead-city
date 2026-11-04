"""夜間港區 (night harbour / container port) level map for 射擊遊戲, built headless with the blender-modeling skill.

Run from the project root:   blender -b -P tools/blender/map_industrial.py
Writes assets/models/map_industrial.glb and previews to .claude/work/.

Positions are written in GAME coordinates (x, y up, z on the ground) and turned into Blender
coordinates with G(x, y, z) = (x, -z, y) when each mesh is created, so the glTF export lands back
exactly on the game's axes.

Gameplay data read by the game (buildCityMap in index.html):
  COL_<n>   unit box scaled to an axis-aligned footprint; the game reads its world x/z extent only,
            so COL nodes are never rotated
  LAMP_<n>  empty at a floodlight bank = a night light position
  Ground*   ground meshes (roads, yards, markings, puddles, quay, water) - they do not cast shadows

Container stacks are instanced: one mesh per colour and type, many linked duplicates. A rotation r
about Blender Z is the game's rotation r about y, so rot 0 = long side along x, pi/2 = along z.

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
TEX_DIR = os.path.join(WORK, "map_industrial_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_industrial.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_industrial_top.png"),
    "street": os.path.join(WORK, "map_industrial_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 23

# ---------------------------------------------------------------- layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # inner block centres, 44 m blocks
RING_C = [-168.0, -112.0, -56.0, 0.0, 56.0, 112.0, 168.0]
HALF = 22.0                                              # block half size
WALK_H = 0.16                                            # yard slab top (concrete)
WATER_Y = -0.9                                           # harbour water surface
QUAY_Z = 170.0                                           # quay edge, water beyond
QUAY_CZ = 158.0                                          # quay-row blocks sit on land z 146..170
CONT_L, CONT_W, CONT_H = 12.19, 2.438, 2.591             # 40 ft container
START = (-28.0, 0.0)                                     # player start (road x=-28)
KEEP = (-98.0, -91.0, 129.0, 133.0)                      # x0, x1, z0, z1: the game's wall spot, no meshes
UPV = (0.0, 1.0, 0.0)
MAT = {}
TILE = {}
COLS = []         # (x0, x1, z0, z1, y0, y1) collider boxes
LAMPS = []        # (x, y, z) floodlight bank positions
OCC = []          # (x0, x1, z0, z1) footprints already taken, for placement checks
CONT_MESH = {}    # (colour, heavy) -> (mesh data, tris)
CONT_INST = []    # (key, (x, y, z), rot)
INST_OBJS = []

# block kinds, ROWS[j][i]: j = z index, i = x index.
# Y container yard, W warehouse, APRON open apron (trailers, cars, forklifts, pallets), DRUM oil-drum yard
ROWS = {
    0: ["Y", "W", "Y", "APRON", "W"],
    1: ["W", "Y", "DRUM", "Y", "APRON"],
    2: ["APRON", "Y", "W", "Y", "DRUM"],
    3: ["Y", "W", "APRON", "W", "Y"],
    4: ["APRON", "Y", "W", "DRUM", "Y"],
}
FENCED = {(-112.0, -112.0), (-56.0, -56.0), (56.0, 0.0), (-112.0, 56.0), (112.0, 112.0)}
APRON_LIGHTS = {(56.0, -112.0), (-112.0, 0.0), (0.0, 56.0)}   # aprons that get a floodlight tower
QUAY_LIGHTS = [(-100.0, 160.0), (72.0, 160.0)]
CRANE_X = (-112.0, 56.0)                                 # ship-to-shore cranes on the quay row


def ring_kind(x, z):
    """Outer background blocks (centres at +-168)."""
    if z == 168.0:   # quay row
        return {-168.0: "Y", -112.0: "CRANE", -56.0: "Y", 0.0: "W", 56.0: "CRANE", 112.0: "Y", 168.0: "Y"}[x]
    if z == -168.0:
        return {-168.0: "Y", -112.0: "W", -56.0: "Y", 0.0: "APRON", 56.0: "Y", 112.0: "W", 168.0: "Y"}[x]
    if x == -168.0:
        return {-112.0: "W", -56.0: "Y", 0.0: "APRON", 56.0: "W", 112.0: "Y"}[z]
    return {-112.0: "Y", -56.0: "W", 0.0: "Y", 56.0: "APRON", 112.0: "W"}[z]   # x == 168


# ---------------------------------------------------------------- materials
PH_SETS = {
    "asphalt": ("asphalt_02", 4.0),
    "yard": ("concrete_pavement", 2.0),
    "concrete": ("concrete_wall_004", 3.0),
    "roof": ("tarred_gravel", 3.0),
    "plywood": ("plywood", 1.2),
    "rust": ("rust_coarse_01", 2.0),
}
CORR_ID = "corrugated_iron_02"      # tinted per colour: containers, warehouse walls, trailers
TINTS = {   # multiplied over the corrugated-iron albedo
    "red": (1.0, 0.16, 0.12),
    "blue": (0.22, 0.42, 0.95),
    "green": (0.20, 0.62, 0.30),
    "orange": (1.0, 0.50, 0.14),
    "grey": (0.85, 0.87, 0.90),
    "navy": (0.22, 0.30, 0.60),
    "cream": (1.0, 0.92, 0.70),
}
CONT_COLS = ["red", "blue", "green", "orange", "grey", "navy"]
WALL_COLS = ["green", "blue", "grey", "cream", "navy"]

CONST = {
    # name: (rgb, roughness, metallic, specular)
    "glass": ((0.05, 0.085, 0.10), 0.04, 0.0, 0.7),
    "dark": ((0.012, 0.012, 0.014), 0.85, 0.0, 0.3),
    "frame": ((0.80, 0.78, 0.74), 0.5, 0.0, 0.5),
    "frame_dark": ((0.11, 0.11, 0.12), 0.4, 0.5, 0.5),
    "metal_dark": ((0.07, 0.07, 0.08), 0.45, 0.8, 0.5),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0.5),
    "rail": ((0.22, 0.20, 0.18), 0.6, 0.6, 0.5),
    "ac": ((0.52, 0.53, 0.55), 0.5, 0.6, 0.5),
    "roller": ((0.40, 0.42, 0.40), 0.6, 0.3, 0.5),
    "casting": ((0.05, 0.05, 0.05), 0.6, 0.2, 0.5),
    "crane_paint": ((0.62, 0.42, 0.12), 0.45, 0.2, 0.5),
    "lamp_head": ((0.86, 0.82, 0.66), 0.25, 0.0, 0.6),
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "burnt": ((0.035, 0.03, 0.028), 0.9, 0.0, 0.3),
    "headlight": ((0.95, 0.92, 0.84), 0.2, 0.0, 0.6),
    "tail": ((0.55, 0.05, 0.04), 0.3, 0.0, 0.5),
    "glass_car": ((0.04, 0.07, 0.09), 0.05, 0.0, 0.8),
    "car_red": ((0.50, 0.06, 0.05), 0.32, 0.25, 0.5),
    "car_blue": ((0.07, 0.17, 0.42), 0.32, 0.25, 0.5),
    "car_white": ((0.78, 0.78, 0.76), 0.35, 0.2, 0.5),
    "car_silver": ((0.45, 0.47, 0.50), 0.3, 0.45, 0.5),
    "car_black": ((0.03, 0.03, 0.035), 0.3, 0.3, 0.5),
    "car_green": ((0.13, 0.30, 0.16), 0.35, 0.25, 0.5),
    "car_yellow": ((0.72, 0.52, 0.10), 0.35, 0.2, 0.5),
    "cone": ((0.95, 0.38, 0.05), 0.5, 0.0, 0.5),
    "cone_base": ((0.05, 0.05, 0.05), 0.6, 0.0, 0.5),
    "cardboard": ((0.45, 0.33, 0.20), 0.9, 0.0, 0.3),
    "debris": ((0.35, 0.33, 0.31), 0.95, 0.0, 0.3),
    "fork_yellow": ((0.80, 0.56, 0.06), 0.45, 0.1, 0.5),
    "drum_blue": ((0.07, 0.20, 0.50), 0.5, 0.4, 0.5),
    "drum_red": ((0.50, 0.07, 0.05), 0.5, 0.4, 0.5),
    "drum_orange": ((0.75, 0.34, 0.06), 0.5, 0.4, 0.5),
    "drum_rust": ((0.34, 0.19, 0.09), 0.85, 0.3, 0.4),
    "sign_red": ((0.42, 0.08, 0.06), 0.5, 0.0, 0.5),
    "sign_navy": ((0.07, 0.10, 0.26), 0.5, 0.0, 0.5),
    "sign_ochre": ((0.60, 0.42, 0.10), 0.5, 0.0, 0.5),
    "sign_cream": ((0.66, 0.61, 0.50), 0.5, 0.0, 0.5),
    "sign_dark": ((0.09, 0.09, 0.10), 0.5, 0.0, 0.5),
    "fence": ((0.22, 0.24, 0.25), 0.5, 0.8, 0.5),          # chain-link: alpha set in cmat use below
    "puddle": ((0.008, 0.010, 0.013), 0.03, 0.0, 1.0),
    "water": ((0.008, 0.030, 0.042), 0.08, 0.0, 0.9),
    "bollard": ((0.62, 0.50, 0.10), 0.5, 0.2, 0.5),
}
ALPHA = {"fence": 0.38}
SIGNS = ["sign_red", "sign_navy", "sign_ochre", "sign_cream", "sign_dark"]
PAINTS = ["car_red", "car_blue", "car_white", "car_silver", "car_black", "car_green", "car_yellow"]
DRUMS = ["drum_blue", "drum_red", "drum_orange", "drum_rust"]


def cmat(name, rgb, rough, metal, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Specular IOR Level"].default_value = spec
    if name in ALPHA:
        bsdf.inputs["Alpha"].default_value = ALPHA[name]
        try:
            mat.surface_render_method = "BLENDED"
        except (AttributeError, TypeError):
            pass
    return mat


def load_materials():
    bkit.CACHE = TEX_DIR
    for key, (aid, tile) in PH_SETS.items():
        maps = bkit.polyhaven_texture(aid, res="1k")
        maps = {k: v for k, v in maps.items() if k in ("color", "normal", "roughness")}
        MAT[key] = bkit.pbr_material(key, maps, scale=1.0, coords="UV")
        TILE[key] = tile
        print("MAP texture", key, aid, sorted(maps))
    corr = bkit.polyhaven_texture(CORR_ID, res="1k")
    corr = {k: v for k, v in corr.items() if k in ("color", "normal", "roughness")}
    for name, rgb in TINTS.items():
        key = f"corr_{name}"
        MAT[key] = bkit.pbr_material(key, corr, scale=1.0, tint=rgb, coords="UV")
        TILE[key] = 2.0
    print("MAP texture corr tinted x", len(TINTS))
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name in CONST:
        TILE.setdefault(name, 1.0)


# ---------------------------------------------------------------- mesh builder and primitives (from map_downtown)
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



# ---------------------------------------------------------------- street furniture (from map_downtown)
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



# ---------------------------------------------------------------- placement bookkeeping
def overlaps(a, b, m=0.0):
    return not (a[1] + m <= b[0] or b[1] + m <= a[0] or a[3] + m <= b[2] or b[3] + m <= a[2])


def free(fp, margin=0.3):
    """True when a footprint (x0, x1, z0, z1) touches no taken space and not the keep-clear spot."""
    if overlaps(fp, KEEP, margin):
        return False
    return not any(overlaps(fp, o, margin) for o in OCC)


def take(fp, col=True):
    OCC.append(fp)
    if col:
        COLS.append((fp[0], fp[1], fp[2], fp[3], 0.0, 3.0))


def scatter(cx, cz, span, count, rng, half, place):
    """Try random spots in a block; place(x, z, rot) draws the item, footprint = half (len, wid)."""
    done = 0
    for _ in range(count * 30):
        if done >= count:
            break
        x = cx + rng.uniform(-span, span)
        z = cz + rng.uniform(-span, span)
        rot = 0.0 if rng.random() < 0.5 else math.pi / 2
        fp = footprint(x, z, rot, half[0], half[1])
        if not free(fp):
            continue
        place(x, z, rot)
        take(fp)
        done += 1
    return done


# ---------------------------------------------------------------- ground, quay, water
def slab(mb, x0, x1, z0, z1, quay=False):
    """Concrete yard slab on a block: top at WALK_H, kerb faces on the sides (none on the quay edge)."""
    h = WALK_H
    mb.poly([(x0, h, z0), (x1, h, z0), (x1, h, z1), (x0, h, z1)], "yard", UPV)
    mb.poly([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], "concrete", (0, 0, -1))
    if not quay:
        mb.poly([(x0, 0, z1), (x0, h, z1), (x1, h, z1), (x1, 0, z1)], "concrete", (0, 0, 1))
    mb.poly([(x0, 0, z0), (x0, h, z0), (x0, h, z1), (x0, 0, z1)], "concrete", (-1, 0, 0))
    mb.poly([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], "concrete", (1, 0, 0))


def road_ground(mb):
    """Asphalt over the whole map up to the quay edge."""
    mb.poly([(-200.0, 0.0, -200.0), (200.0, 0.0, -200.0), (200.0, 0.0, QUAY_Z), (-200.0, 0.0, QUAY_Z)],
            "asphalt", UPV)


def quay_wall(mb):
    """Vertical quay face from the harbour water up to the yard top, facing the water."""
    mb.poly([(-200.0, WATER_Y, QUAY_Z), (200.0, WATER_Y, QUAY_Z), (200.0, WALK_H, QUAY_Z),
             (-200.0, WALK_H, QUAY_Z)], "concrete", (0, 0, 1))


def water_plane(mb):
    mb.poly([(-200.0, WATER_Y, QUAY_Z), (200.0, WATER_Y, QUAY_Z), (200.0, WATER_Y, 200.0),
             (-200.0, WATER_Y, 200.0)], "water", UPV)


def markings_all(mb):
    """Centre dashes on every road, crosswalks on all four arms of every intersection."""
    for rc in ROADS:
        t = -146.0
        while t < 146.0:
            c = t + 1.5
            if all(abs(c - rd) > 9.0 for rd in ROADS):
                rect_at(mb, rc - 0.08, rc + 0.08, c - 1.5, c + 1.5, 0.012, "paint_white")
                rect_at(mb, c - 1.5, c + 1.5, rc - 0.08, rc + 0.08, 0.012, "paint_white")
            t += 6.0
    for rc in ROADS:
        for rd in ROADS:
            for sgn in (-1, 1):
                zc = rd + sgn * 7.5
                for k in range(-5, 6):
                    xc = rc + k * 1.1
                    rect_at(mb, xc - 0.33, xc + 0.33, zc - 1.5, zc + 1.5, 0.012, "paint_white")
                xc = rc + sgn * 7.5
                for k in range(-5, 6):
                    zc2 = rd + k * 1.1
                    rect_at(mb, xc - 1.5, xc + 1.5, zc2 - 0.33, zc2 + 0.33, 0.012, "paint_white")


def manholes(mb, rng):
    cand = 0
    while cand < 14:
        cand += 1
        rc = rng.choice(ROADS)
        p = rng.uniform(-130, 130)
        x, z = (rc + 3.2, p) if rng.random() < 0.5 else (p, rc + 3.2)
        if any(abs(p - rd) < 9 for rd in ROADS) or overlaps((x - 0.4, x + 0.4, z - 0.4, z + 0.4), KEEP):
            continue
        for k in range(14):
            a0 = 2 * math.pi * k / 14
            a1 = 2 * math.pi * (k + 1) / 14
            mb.poly([(x, 0.013, z), (x + 0.36 * math.cos(a0), 0.013, z + 0.36 * math.sin(a0)),
                     (x + 0.36 * math.cos(a1), 0.013, z + 0.36 * math.sin(a1))], "metal_dark", UPV)


def puddle(mb, x, z, r, y, rng):
    n = 9
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rr = r * (1 + rng.uniform(-0.25, 0.25))
        pts.append((x + rr * math.cos(a), y, z + rr * math.sin(a) * 0.7))
    mb.poly(pts, "puddle", UPV)


def road_puddles(mb, rng, n):
    done = 0
    while done < n:
        rc = rng.choice(ROADS)
        p = rng.uniform(-135, 135)
        x, z = (rc + rng.uniform(-3.5, 3.5), p) if rng.random() < 0.5 else (p, rc + rng.uniform(-3.5, 3.5))
        if overlaps((x - 3, x + 3, z - 3, z + 3), KEEP):
            continue
        puddle(mb, x, z, rng.uniform(1.5, 3.2), 0.014, rng)
        done += 1


def debris(mb, rng, n):
    for _ in range(n):
        rc = rng.choice(ROADS)
        p = rng.uniform(-140, 140)
        x, z = (rc + rng.uniform(-4, 4), p) if rng.random() < 0.5 else (p, rc + rng.uniform(-4, 4))
        if math.hypot(x - START[0], z - START[1]) < 10 or overlaps((x - 1, x + 1, z - 1, z + 1), KEEP):
            continue
        obox(mb, (x, 0.12, z), [(1, 0, 0), UPV, (0, 0, 1)],
             (rng.uniform(0.15, 0.6), 0.1, rng.uniform(0.15, 0.5)), "debris")


def bollard(mb, x, z):
    vcyl(mb, x, WALK_H, z, 0.2, 0.2, 0.55, 8, "bollard")
    vcyl(mb, x, WALK_H + 0.55, z, 0.23, 0.23, 0.06, 8, "metal_dark")


def quay_bollards(mb, crane_x):
    """Mooring bollards along the quay edge, 2.2 m back from the water, clear of the crane rails."""
    x = -192.0
    while x <= 192.0:
        if all(abs(x - cx) > 22.5 for cx in crane_x):
            bollard(mb, x, QUAY_Z - 2.2)
        x += 12.0


# ---------------------------------------------------------------- corrugated sheets
def corr_face(mb, fr, L, v0, v1, mat, pitch=0.3, depth=0.05, u0=0.0, u1=None, t0=0.0):
    """Corrugated sheet on a facade frame: a zigzag profile along u (per pitch: rise, flat top,
    fall, flat bottom), extruded from v0 to v1. t0 pushes the whole sheet out from the wall."""
    _, _, N = fr
    u1 = L if u1 is None else u1
    n = max(1, round((u1 - u0) / pitch))
    p = (u1 - u0) / n
    pts = []
    for k in range(n):
        for f, t in ((0.0, 0.0), (0.25, depth), (0.5, depth), (0.75, 0.0)):
            pts.append((u0 + (k + f) * p, t0 + t))
    pts.append((u1, t0))
    for a, b in zip(pts, pts[1:]):
        mb.poly([P(fr, a[0], v0, a[1]), P(fr, b[0], v0, b[1]), P(fr, b[0], v1, b[1]), P(fr, a[0], v1, a[1])],
                mat, N)


def mesh_data(mb, coll):
    """Build a Mesh once, keep only its mesh datablock (for linked duplicates)."""
    obj = mb.build(coll)
    me = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    return me


# ---------------------------------------------------------------- containers
def container_mesh(colour, heavy):
    """40 ft container in its local frame: long side along x, base on y = 0, centred on the origin.
    heavy = corrugated sides; lite = flat sides (background yards)."""
    mb = Mesh(f"Container_{colour}_{'h' if heavy else 'l'}")
    m = f"corr_{colour}"
    L2, W2, H = CONT_L / 2, CONT_W / 2, CONT_H
    if heavy:
        corr_face(mb, ((-L2, 0.0, W2), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), CONT_L, 0.0, H, m, pitch=0.3, depth=0.05)
        corr_face(mb, ((L2, 0.0, -W2), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)), CONT_L, 0.0, H, m, pitch=0.3, depth=0.05)
    else:
        mb.poly([(-L2, 0, W2), (L2, 0, W2), (L2, H, W2), (-L2, H, W2)], m, (0, 0, 1))
        mb.poly([(-L2, 0, -W2), (-L2, H, -W2), (L2, H, -W2), (L2, 0, -W2)], m, (0, 0, -1))
    mb.poly([(-L2, H, -W2), (L2, H, -W2), (L2, H, W2), (-L2, H, W2)], m, UPV)           # roof
    mb.poly([(L2, 0, -W2), (L2, H, -W2), (L2, H, W2), (L2, 0, W2)], m, (1, 0, 0))       # front end
    mb.poly([(-L2, 0, -W2), (-L2, 0, W2), (-L2, H, W2), (-L2, H, -W2)], m, (-1, 0, 0))  # door end
    for z in (-0.8, 0.0, 0.8):                                                          # door bars
        obox(mb, (-L2 - 0.02, H / 2, z), [(1, 0, 0), UPV, (0, 0, 1)], (0.04, H / 2 - 0.1, 0.05), "dark")
    for sx in (-1, 1):                                                                  # corner castings
        for sz in (-1, 1):
            for y in (0.09, H - 0.09):
                obox(mb, (sx * L2, y, sz * W2), [(1, 0, 0), UPV, (0, 0, 1)], (0.09, 0.09, 0.09), "casting")
    return mb


def build_container_meshes(coll):
    for colour in CONT_COLS:
        for heavy in (True, False):
            mb = container_mesh(colour, heavy)
            CONT_MESH[(colour, heavy)] = (mesh_data(mb, coll), mb.tris())


def place_containers(coll):
    for k, (key, p, rot) in enumerate(CONT_INST):
        me, _ = CONT_MESH[key]
        o = bpy.data.objects.new(f"Container_{k + 1:03d}", me)
        o.location = G(p)
        o.rotation_euler = (0.0, 0.0, rot)
        coll.objects.link(o)
        INST_OBJS.append(o)


def stack_grid(cx, cz, heavy, rng):
    """3 rows (along z, 4 m aisles) x 2 stacks (along x, 4 m aisle), each stack 1-3 containers high."""
    for sx in (cx - 8.1, cx + 8.1):
        for sz in (cz - 6.44, cz, cz + 6.44):
            fp = (sx - CONT_L / 2, sx + CONT_L / 2, sz - CONT_W / 2, sz + CONT_W / 2)
            h = rng.choice([1, 2, 2, 3]) if heavy else rng.choice([1, 1, 2])
            for k in range(h):
                CONT_INST.append(((rng.choice(CONT_COLS), heavy), (sx, WALK_H + k * CONT_H, sz), 0.0))
            COLS.append((fp[0], fp[1], fp[2], fp[3], 0.0, h * CONT_H))
            OCC.append(fp)


# ---------------------------------------------------------------- fences and floodlights
def fence_run(mb, a, b):
    """Chain-link run between two axis-aligned points: steel posts every 3 m, top rail, see-through panel."""
    ax, az = a
    bx, bz = b
    L = math.hypot(bx - ax, bz - az)
    dx, dz = (bx - ax) / L, (bz - az) / L
    d3 = (dx, 0.0, dz)
    perp = (-dz, 0.0, dx)
    n = max(1, round(L / 3.0))
    for i in range(n + 1):
        px, pz = ax + (bx - ax) * i / n, az + (bz - az) * i / n
        obox(mb, (px, WALK_H + 1.2, pz), [(1, 0, 0), UPV, (0, 0, 1)], (0.04, 1.2, 0.04), "metal")
    obox(mb, ((ax + bx) / 2, WALK_H + 2.36, (az + bz) / 2), [d3, UPV, perp], (L / 2, 0.03, 0.03), "metal")
    b0, b1 = (ax, WALK_H, az), (bx, WALK_H, bz)
    t0, t1 = (ax, WALK_H + 2.3, az), (bx, WALK_H + 2.3, bz)
    mb.poly([b0, b1, t1, t0], "fence", perp)
    mb.poly([b0, t0, t1, b1], "fence", vmul(perp, -1.0))
    x0, x1, z0, z1 = min(ax, bx), max(ax, bx), min(az, bz), max(az, bz)
    if x1 - x0 < 0.2:
        x0, x1 = (x0 + x1) / 2 - 0.1, (x0 + x1) / 2 + 0.1
    if z1 - z0 < 0.2:
        z0, z1 = (z0 + z1) / 2 - 0.1, (z0 + z1) / 2 + 0.1
    COLS.append((x0, x1, z0, z1, 0.0, 2.4))


def yard_fence(mb, cx, cz):
    """Fence on the 39 m square of a yard, with a 4 m gate in the middle of the south side."""
    F, g = 19.5, 2.0
    x0, x1, z0, z1 = cx - F, cx + F, cz - F, cz + F
    fence_run(mb, (x0, z0), (cx - g, z0))
    fence_run(mb, (cx + g, z0), (x1, z0))
    fence_run(mb, (x1, z0), (x1, z1))
    fence_run(mb, (x1, z1), (x0, z1))
    fence_run(mb, (x0, z1), (x0, z0))


def floodlight(mb, x, z, face):
    """22 m pole with a light bank on top, facing `face` (an axis-aligned unit vector in x/z).
    The bank's lamp is a LAMP_ empty: the game's night light sits there."""
    vcyl(mb, x, WALK_H, z, 0.22, 0.12, 22.0, 8, "metal")
    top = WALK_H + 22.0
    fx, fz = face
    ax0 = (0.0, 0.0, 1.0) if abs(fx) > abs(fz) else (1.0, 0.0, 0.0)
    axes = [ax0, UPV, (fx, 0.0, fz)]
    obox(mb, (x, top + 0.4, z), axes, (1.2, 0.35, 0.3), "frame_dark")
    obox(mb, (x + fx * 0.31, top + 0.4, z + fz * 0.31), axes, (1.05, 0.28, 0.03), "lamp_head")
    LAMPS.append((x, top - 0.2, z))
    COLS.append((x - 0.4, x + 0.4, z - 0.4, z + 0.4, 0.0, 3.0))
    OCC.append((x - 0.5, x + 0.5, z - 0.5, z + 0.5))


# ---------------------------------------------------------------- yards
def yard(cx, cz, heavy, fenced, rng, mb_fence, mb_lights, mb_props, mb_veh, mb_drums):
    stack_grid(cx, cz, heavy, rng)
    span = 19.0
    if fenced:
        yard_fence(mb_fence, cx, cz)
        floodlight(mb_lights, cx + 15.5, cz + 15.5, (0.0, -1.0))
        span = 16.0
    scatter(cx, cz, span, 1, rng, (1.4, 0.65), lambda x, z, r: forklift(mb_veh, x, z, r, rng))
    scatter(cx, cz, span, 4, rng, (0.5, 0.6), lambda x, z, r: pallet(mb_props, x, z, r, rng))
    scatter(cx, cz, span, 6, rng, (0.3, 0.3), lambda x, z, r: drum(mb_drums, x, z, rng))


# ---------------------------------------------------------------- props and vehicles
def pallet(mb, x, z, rot, rng):
    """Wooden pallet (1.2 x 1.0 m, deck boards + stringers) with one or two layers of cardboard."""
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    y0 = WALK_H
    for k in (-0.36, 0.0, 0.36):
        obox(mb, vadd((x, y0 + 0.135, z), vmul(f, k)), ax, (0.6, 0.02, 0.12), "plywood")
    for k in (-0.5, 0.0, 0.5):
        obox(mb, vadd((x, y0 + 0.07, z), vmul(s, k)), ax, (0.1, 0.05, 0.5), "plywood")
    for layer in range(rng.choice([1, 1, 2])):
        y = y0 + 0.43 + layer * 0.55
        for k in (-0.3, 0.3):
            if layer == 1 and rng.random() < 0.4:
                continue
            obox(mb, vadd((x, y, z), vmul(s, k)), ax, (0.27, 0.27, 0.4), "cardboard")


def forklift(mb, x, z, rot, rng):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    b = (x, WALK_H, z)

    def at(lat, up, fwd):
        return vadd(b, vmul(s, lat), (0.0, up, 0.0), vmul(f, fwd))
    obox(mb, at(0, 0.55, -0.2), ax, (0.55, 0.3, 1.05), "fork_yellow")         # chassis
    obox(mb, at(0, 1.25, -0.3), ax, (0.6, 0.04, 0.7), "metal_dark")            # overhead guard roof
    for lat in (-0.5, 0.5):
        for fw in (-0.6, 0.1):
            obox(mb, at(lat, 1.1, fw), ax, (0.03, 0.2, 0.03), "metal_dark")    # guard posts
    for lat in (-0.36, 0.36):
        obox(mb, at(lat, 1.4, 1.2), ax, (0.05, 1.3, 0.05), "metal_dark")       # mast
        obox(mb, at(lat, 0.12, 1.45), ax, (0.06, 0.05, 0.6), "metal_dark")     # forks
    for lat in (-0.5, 0.5):
        for fw in (-0.8, 0.8):
            ocyl(mb, at(lat, 0.3, fw), s, 0.3, 0.3, 0.22, 8, "tire")


def trailer(mb, x, z, rot, rng):
    """Semi-trailer on its chassis: box body in a container colour, four tyres."""
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    ax = [s, UPV, f]
    b = (x, WALK_H, z)

    def at(lat, up, fwd):
        return vadd(b, vmul(s, lat), (0.0, up, 0.0), vmul(f, fwd))
    obox(mb, at(0, 1.0, 0.0), ax, (1.3, 0.12, 6.2), "metal_dark")
    obox(mb, at(0, 2.55, 0.0), ax, (1.25, 1.45, 6.2), f"corr_{rng.choice(CONT_COLS)}")
    for lat in (-1.05, 1.05):
        for fw in (-5.0, -5.9):
            ocyl(mb, at(lat, 0.5, fw), s, 0.5, 0.5, 0.35, 8, "tire")


def drum(mb, x, z, rng):
    """Steel oil drum, upright (60%) or on its side."""
    mat = rng.choice(DRUMS)
    if rng.random() < 0.4:
        ang = rng.uniform(0, math.pi)
        ocyl(mb, (x, WALK_H + 0.29, z), (math.cos(ang), 0.0, math.sin(ang)), 0.29, 0.29, 0.88, 10, mat)
        return
    vcyl(mb, x, WALK_H, z, 0.29, 0.29, 0.88, 10, mat)
    vcyl(mb, x, WALK_H + 0.86, z, 0.31, 0.31, 0.05, 10, "metal_dark")
    vcyl(mb, x, WALK_H, z, 0.31, 0.31, 0.05, 10, "metal_dark")


def parked(mb, x, z, rot, rng):
    wrecked = rng.random() < 0.15
    paint = "burnt" if wrecked else rng.choice(PAINTS)
    car(mb, x, z, rot, paint, WALK_H + 0.012, wrecked, rng)


def apron(cx, cz, ring, rng, mb_veh, mb_props, mb_lights, light):
    if light:
        floodlight(mb_lights, cx + 15.5, cz - 15.5, (-1.0, 0.0))
    scatter(cx, cz, 17.0, 2 if ring else 4, rng, (2.3, 0.95), lambda x, z, r: parked(mb_veh, x, z, r, rng))
    scatter(cx, cz, 13.0, 1 if ring else 2, rng, (6.4, 1.4), lambda x, z, r: trailer(mb_veh, x, z, r, rng))
    scatter(cx, cz, 17.0, 1, rng, (1.4, 0.65), lambda x, z, r: forklift(mb_veh, x, z, r, rng))
    scatter(cx, cz, 17.0, 3 if ring else 6, rng, (0.5, 0.6), lambda x, z, r: pallet(mb_props, x, z, r, rng))
    for _ in range(4):
        x = cx + rng.uniform(-18, 18)
        z = cz + rng.uniform(-18, 18)
        if free((x - 0.3, x + 0.3, z - 0.3, z + 0.3), 0.0):
            cone(mb_props, x, z, WALK_H + 0.012)


def drum_yard(cx, cz, rng, mb_drums, mb_props):
    scatter(cx, cz, 18.0, 34, rng, (0.3, 0.3), lambda x, z, r: drum(mb_drums, x, z, rng))
    scatter(cx, cz, 18.0, 7, rng, (0.5, 0.6), lambda x, z, r: pallet(mb_props, x, z, r, rng))


# ---------------------------------------------------------------- warehouses
def face_frames(cx, cz, hx, hz, y0):
    """The four side walls of a box footprint: (frame, length). Face 0 +z, 1 -z, 2 +x, 3 -x."""
    return [
        (((cx - hx, y0, cz + hz), (1, 0, 0), (0, 0, 1)), 2 * hx),
        (((cx + hx, y0, cz - hz), (-1, 0, 0), (0, 0, -1)), 2 * hx),
        (((cx + hx, y0, cz + hz), (0, 0, -1), (1, 0, 0)), 2 * hz),
        (((cx - hx, y0, cz - hz), (0, 0, 1), (-1, 0, 0)), 2 * hz),
    ]


def roller_door(mb, fr, L, uc, rng):
    """Roller shutter on a dock: corrugated slats proud of the wall, dock platform, bumpers, frame."""
    w, hgt, dock = 4.8, 5.0, 1.2
    corr_face(mb, fr, L, dock, dock + hgt, "roller", pitch=0.2, depth=0.035, u0=uc - w / 2, u1=uc + w / 2, t0=0.12)
    wbox(mb, fr, uc - w / 2 - 0.25, uc - w / 2, dock, dock + hgt + 0.3, 0.0, 0.3, "frame_dark")
    wbox(mb, fr, uc + w / 2, uc + w / 2 + 0.25, dock, dock + hgt + 0.3, 0.0, 0.3, "frame_dark")
    wbox(mb, fr, uc - w / 2 - 0.25, uc + w / 2 + 0.25, dock + hgt, dock + hgt + 0.35, 0.0, 0.3, "frame_dark")
    wbox(mb, fr, uc - w / 2 - 1.0, uc + w / 2 + 1.0, 0.0, dock, 0.0, 2.2, "concrete")
    for sgn in (-1, 1):
        wbox(mb, fr, uc + sgn * (w / 2 + 0.6) - 0.2, uc + sgn * (w / 2 + 0.6) + 0.2, dock + 0.4, dock + 0.9,
             0.0, 0.25, "tire")


def warehouse(cx, cz, along_x, door_faces, rng, mb_w):
    """34 x 16 m steel warehouse, 8-10 m high: corrugated walls, roller doors on loading docks,
    flat roof with skylights and vents, a sign band over the doors."""
    hx, hz = (17.0, 8.0) if along_x else (8.0, 17.0)
    H = rng.uniform(8.0, 10.0)
    y = WALK_H + H
    wall = "rust" if rng.random() < 0.2 else f"corr_{rng.choice(WALL_COLS)}"
    faces = face_frames(cx, cz, hx, hz, WALK_H)
    for fr, L in faces:
        corr_face(mb_w, fr, L, 0.0, H - 0.2, wall, pitch=0.3, depth=0.05)
        wbox(mb_w, fr, 0.0, L, 0.0, 0.7, 0.0, 0.14, "concrete")
        wbox(mb_w, fr, -0.2, L + 0.2, H - 0.2, H + 0.5, 0.0, 0.3, wall)
    mb_w.poly([(cx - hx, y, cz - hz), (cx + hx, y, cz - hz), (cx + hx, y, cz + hz), (cx - hx, y, cz + hz)],
              "roof", UPV)
    axes = [(1, 0, 0), UPV, (0, 0, 1)] if along_x else [(1, 0, 0), UPV, (0, 0, 1)]
    skymats = ["frame_dark", "frame_dark", "glass", "frame_dark", "frame_dark", "frame_dark"]
    for i in (-1, 0, 1):
        if along_x:
            obox(mb_w, (cx + i * hx * 0.5, y + 0.12, cz), axes, (2.0, 0.12, 1.4), skymats)
        else:
            obox(mb_w, (cx, y + 0.12, cz + i * hz * 0.5), axes, (1.4, 0.12, 2.0), skymats)
    for sx, sz in ((-0.55, -0.4), (0.55, 0.4)):
        obox(mb_w, (cx + sx * hx, y + 0.5, cz + sz * hz), axes, (0.6, 0.5, 0.6), "ac")
        vcyl(mb_w, cx + sx * hx + 0.8, y, cz + sz * hz, 0.15, 0.15, 1.2, 8, "metal")
    for fi in door_faces:
        fr, L = faces[fi]
        for uc in ([0.3 * L, 0.7 * L] if L > 20 else [0.5 * L]):
            roller_door(mb_w, fr, L, uc, rng)
        wbox(mb_w, fr, L * 0.2, L * 0.8, H - 1.2, H - 0.3, 0.0, 0.2, rng.choice(SIGNS))
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, 0.0, 3.0))
    OCC.append((cx - hx, cx + hx, cz - hz, cz + hz))


# ---------------------------------------------------------------- ship-to-shore cranes
def sts_crane(cx, mb):
    """Quay gantry: two portal legs on rails straddling the quay edge, a boom out over the water."""
    zi, zs = 152.0, 168.0
    AX = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
    for z in (zi, zs):
        obox(mb, (cx, WALK_H + 0.18, z), AX, (21.0, 0.18, 0.3), "rail")
    for x in (cx - 5.0, cx + 5.0):
        for z in (zi, zs):
            obox(mb, (x, WALK_H + 13.0, z), AX, (0.8, 13.0, 0.8), "crane_paint")
            COLS.append((x - 0.8, x + 0.8, z - 0.8, z + 0.8, 0.0, 3.0))
        obox(mb, (x, WALK_H + 25.5, 160.0), AX, (0.7, 0.7, 8.0), "crane_paint")
    for z in (zi, zs):
        obox(mb, (cx, WALK_H + 25.5, z), AX, (5.7, 0.7, 0.7), "crane_paint")
    obox(mb, (cx, WALK_H + 28.6, 157.0), AX, (2.2, 1.6, 2.0), "ac")
    a = (0.0, 16.5 / 21.6, -14.0 / 21.6)
    bvec = (0.0, -a[2], a[1])
    obox(mb, (cx, WALK_H + 33.75, 153.0), [(1, 0, 0), a, bvec], (0.6, 10.8, 0.6), "crane_paint")
    obox(mb, (cx, WALK_H + 26.5, 182.0), AX, (0.9, 1.0, 14.0), "crane_paint")
    obox(mb, (cx, WALK_H + 24.6, 182.0), AX, (1.1, 0.5, 1.2), "metal_dark")
    ocyl(mb, (cx, WALK_H + 12.4, 182.0), (0.0, 1.0, 0.0), 0.05, 0.05, 23.0, 6, "metal_dark")
    obox(mb, (cx, WALK_H + 1.4, 182.0), AX, (1.2, 0.3, 1.3), "metal_dark")


# ---------------------------------------------------------------- previews (night, lamps lit)
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


def setup_world():
    """Night sky: dark blue, no HDRI. The game's own lights carry the night; previews add a point
    light at each LAMP_ so the yards read as lit (preview only, never exported)."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.012, 0.016, 0.030, 1.0)
    bg.inputs["Strength"].default_value = 1.0


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
    moon = bkit.sun(elevation=32, azimuth=200, strength=1.2, softness=3.0, color=(0.6, 0.72, 1.0))
    cols = [o for o in objs if o.name.startswith("COL_") or o.name.startswith("LAMP_")]
    for o in cols:
        o.hide_render = True
    lamp_lights = []
    for o in objs:
        if o.name.startswith("LAMP_"):
            ld = bpy.data.lights.new(f"prev_{o.name}", "POINT")
            ld.energy = 6000.0
            ld.color = (1.0, 0.82, 0.55)
            ld.shadow_soft_size = 1.5
            lo = bpy.data.objects.new(ld.name, ld)
            lo.location = o.location
            scene.collection.objects.link(lo)
            lamp_lights.append(lo)
    for name in [w.strip() for w in RENDER_LIST.split(",") if w.strip()]:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (28.0, 1.7, -100.0), (28.0, 1.5, 100.0), lens=26.0)
        else:
            continue
        scene.camera = cam
        scene.render.filepath = PREVIEWS[name]
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("MAP preview", name, round(time.time() - t0, 1), "s ->", PREVIEWS[name])
        bpy.data.objects.remove(cam)
    for lo in lamp_lights:
        d = lo.data
        bpy.data.objects.remove(lo)
        bpy.data.lights.remove(d)
    bpy.data.objects.remove(moon)
    for o in cols:
        o.hide_render = False


# ---------------------------------------------------------------- main
def main():
    t_start = time.time()
    rng = random.Random(SEED)
    bkit.reset_scene()
    coll = bpy.context.scene.collection
    os.makedirs(TEX_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)

    print("MAP stage: textures")
    load_materials()

    print("MAP stage: ground, slabs, quay, water, markings")
    ground_road = Mesh("Ground_road")
    ground_yard = Mesh("Ground_yard")
    ground_quay = Mesh("Ground_quay")
    ground_water = Mesh("Ground_water")
    markings = Mesh("Ground_markings")
    puddles = Mesh("Ground_puddles")
    debris_mb = Mesh("Debris")
    road_ground(ground_road)
    quay_wall(ground_quay)
    water_plane(ground_water)
    blocks = []   # (cx, cz, kind, ring)
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            blocks.append((cx, cz, ROWS[j][i], False))
    for cz in RING_C:
        for cx in RING_C:
            if abs(cx) == 168 or abs(cz) == 168:
                blocks.append((cx, cz, ring_kind(cx, cz), True))
    for cx, cz, _, _ in blocks:
        if cz == 168.0:   # quay row: land only up to the quay edge
            slab(ground_yard, cx - HALF, cx + HALF, 146.0, QUAY_Z, quay=True)
        else:
            slab(ground_yard, cx - HALF, cx + HALF, cz - HALF, cz + HALF)
    markings_all(markings)
    manholes(markings, rng)
    road_puddles(puddles, rng, 22)
    debris(debris_mb, rng, 60)

    print("MAP stage: containers")
    build_container_meshes(coll)

    fence_mb = Mesh("Fences")
    lights_mb = Mesh("Floodlights")
    props = Mesh("Props")
    veh = Mesh("Vehicles")
    drums_mb = Mesh("Drums")
    wh = Mesh("Warehouses")
    cranes = Mesh("Cranes")
    bollards = Mesh("Bollards")

    print("MAP stage: yards, warehouses, aprons, cranes")
    n_wh = 0
    for cx, cz, kind, ring in blocks:
        yc = QUAY_CZ if cz == 168.0 else cz
        if kind == "Y":
            yard(cx, yc, not ring, (cx, cz) in FENCED, rng, fence_mb, lights_mb, props, veh, drums_mb)
        elif kind == "W":
            n_wh += 1
            if cz == 168.0:
                along_x, doors = True, [1]          # quay shed: doors face the road, not the water
            else:
                along_x = rng.random() < 0.5
                doors = [rng.choice([0, 1] if along_x else [2, 3])]
            warehouse(cx, yc, along_x, doors, rng, wh)
        elif kind == "APRON":
            apron(cx, cz, ring, rng, veh, props, lights_mb, (cx, cz) in APRON_LIGHTS)
        elif kind == "DRUM":
            drum_yard(cx, cz, rng, drums_mb, props)
        elif kind == "CRANE":
            sts_crane(cx, cranes)
    for x, z in QUAY_LIGHTS:
        floodlight(lights_mb, x, z, (0.0, -1.0))
    quay_bollards(bollards, CRANE_X)

    print("MAP stage: build objects")
    groups = [ground_road, ground_yard, ground_quay, ground_water, markings, puddles, debris_mb,
              fence_mb, lights_mb, props, veh, drums_mb, wh, cranes, bollards]
    objs = []
    tri_mesh = 0
    for mb in groups:
        if mb.faces:
            objs.append(mb.build(coll))
            tri_mesh += mb.tris()
    place_containers(coll)
    tri_inst = sum(CONT_MESH[key][1] for key, _, _ in CONT_INST)
    tri_unique_cont = sum(t for _, t in CONT_MESH.values())

    # gameplay data: COL_ unit boxes (scaled, never rotated), LAMP_ empties
    cube = bpy.data.meshes.new("COL_unit")
    cube.from_pydata([(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
                      (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)], [],
                     [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)])
    cube.update()
    for i, (x0, x1, z0, z1, y0, y1) in enumerate(COLS):
        o = bpy.data.objects.new(f"COL_{i + 1:03d}", cube)
        o.location = G(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
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
    print(f"MAP counts: COL={len(COLS)} LAMP={len(LAMPS)} containers={len(CONT_INST)} "
          f"container_types={len(CONT_MESH)} warehouses={n_wh} fences_yards={len(FENCED)} "
          f"tris_unique={tri_mesh + tri_unique_cont} tris_rendered={tri_mesh + tri_inst}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        for o in objs:
            if o.name.startswith("COL_"):
                o.hide_render = False
        bkit.export_glb(OUT_GLB, objs + INST_OBJS, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
