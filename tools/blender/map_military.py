"""陸軍基地 (army base in a dust storm, outside the city) level map for 射擊遊戲, built headless with the blender-modeling skill.

Run from the project root:   blender -b -P tools/blender/map_military.py
Writes assets/models/map_military.glb and previews to .claude/work/.

Positions are written in GAME coordinates (x, y up, z on the ground) and turned into Blender
coordinates with G(x, y, z) = (x, -z, y) when each mesh is created, so the glTF export lands back
exactly on the game's axes.

Gameplay data read by the game (index.html, the map loader):
  COL_<n>     axis-aligned box = a collider (buildings, vehicles, walls, fences, towers, barriers...)
  LAMP_<n>    empty at a floodlight head = a night light position
  BARREL_<n>  empty = an explosive red fuel barrel the game places itself (only x and z are read)
  Ground*     ground meshes (sand, roads, pads, dune slopes) - they do not cast shadows

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
TEX_DIR = os.path.join(WORK, "map_military_tex")
OUT_GLB = os.path.join(PROJ, "assets", "models", "map_military.glb")
PREVIEWS = {
    "top": os.path.join(WORK, "map_military_top.png"),
    "street": os.path.join(WORK, "map_military_street.png"),
}
ENV = os.environ
RENDER_LIST = ENV.get("MAP_RENDER", "top,street")
DO_EXPORT = ENV.get("MAP_EXPORT", "1") == "1"
SAMPLES = int(ENV.get("MAP_SAMPLES", "48"))
RES_W = int(ENV.get("MAP_RES", "1400"))
SEED = 31

# ---------------------------------------------------------------- base layout (game metres)
ROADS = [-140.0, -84.0, -28.0, 28.0, 84.0, 140.0]      # road centre lines, 12 m wide
BC = [-112.0, -56.0, 0.0, 56.0, 112.0]                  # inner block centres, 44 m blocks
HALF = 22.0                                              # block half size
ROAD_HW = 6.0                                            # road half width
BASE = 147.5                                             # perimeter fence line, outside the perimeter road
FENCE_H = 2.4                                            # chain-link height (barbed wire above)
OFF = 0.08                                               # dune slopes sit this far above the sand plane
START = (28.0, -140.0)                                   # player start on the road x=28

# block kinds, ROWS[j][i]: j = z index, i = x index
ROWS = {
    0: ["BARRACKS", "MOTOR", "BARRACKS", "HANGAR", "FUEL"],
    1: ["HANGAR", "BARRACKS", "MOTOR", "TENTS", "BARRACKS"],
    2: ["MOTOR", "BARRACKS", "HQ", "HESCO", "HANGAR"],
    3: ["BARRACKS", "FUEL", "HANGAR", "MOTOR", "BARRACKS"],
    4: ["TENTS", "HANGAR", "MOTOR", "BARRACKS", "SANDBAG"],
}
# outer ring (background): hangars on flattened pads, rocky hills
RING_HANGARS = [(168.0, -56.0, 1), (-168.0, 56.0, -1), (56.0, -168.0, 1), (-56.0, 168.0, -1)]
PADS = [(cx, cz, 18.0, 13.0) for cx, cz, _ in RING_HANGARS]   # flattened ring pads (x, z, half w, half d)
HILLS = [(-180.0, -100.0, 18.0, 26.0), (120.0, 182.0, 16.0, 26.0), (180.0, 110.0, 12.0, 20.0),
         (160.0, -180.0, 11.0, 20.0)]                            # (x, z, height, radius)
TOWERS = [(-131.0, -131.0), (131.0, -131.0), (-131.0, 131.0), (131.0, 131.0),
          (0.0, -131.0), (0.0, 131.0), (-131.0, 0.0), (131.0, 0.0)]

UPV = (0.0, 1.0, 0.0)
UPAX = [(1.0, 0.0, 0.0), UPV, (0.0, 0.0, 1.0)]
AX0 = UPAX
MAT = {}
TILE = {}
COLS = []        # (x0, x1, z0, z1, y0, y1) collider boxes
LAMPS = []       # (x, y, z) floodlight head positions
BARRELS = []     # (x, z) explosive barrel spots


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


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


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
# A facade frame is (O, U, N): O = bottom-left corner of the face, U = unit horizontal direction
# left->right seen from outside, N = outward normal.  u runs along U, v up, t out of the wall.
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
    """Lumpy low-poly sphere for tree canopies, sandbags and boulders."""
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
    quad_flat(mb, min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1), y, mat)


def disk(mb, cx, cz, r, y, mat, seg=24):
    for k in range(seg):
        a0 = 2 * math.pi * k / seg
        a1 = 2 * math.pi * (k + 1) / seg
        mb.poly([(cx, y, cz), (cx + r * math.cos(a0), y, cz + r * math.sin(a0)),
                 (cx + r * math.cos(a1), y, cz + r * math.sin(a1))], mat, UPV)


def ring_flat(mb, cx, cz, r0, r1, y, mat, seg=32):
    for k in range(seg):
        a0 = 2 * math.pi * k / seg
        a1 = 2 * math.pi * (k + 1) / seg
        p0 = (cx + r0 * math.cos(a0), y, cz + r0 * math.sin(a0))
        p1 = (cx + r0 * math.cos(a1), y, cz + r0 * math.sin(a1))
        q1 = (cx + r1 * math.cos(a1), y, cz + r1 * math.sin(a1))
        q0 = (cx + r1 * math.cos(a0), y, cz + r1 * math.sin(a0))
        mb.poly([p0, p1, q1, q0], mat, UPV)


# ---------------------------------------------------------------- materials
PH_SETS = {
    "sand": ("coast_sand_05", 4.0),         # compacted desert sand
    "dirt": ("red_dirt_mud_01", 3.0),       # dirt edges and track
    "road": ("dirty_concrete", 3.0),        # cracked base roads
    "pad": ("rough_concrete", 3.0),         # concrete pads
    "concrete": ("concrete_wall_004", 3.0), # HQ and jersey barriers
    "rock": ("rock_face_03", 4.0),          # hill slopes
    "boulder": ("rock_boulder_dry", 2.0),
}
TINTS = {   # key: (texture id, tile metres, tint)
    "corr_olive": ("corrugated_iron_02", 2.0, (0.66, 0.70, 0.44)),
    "corr_tan": ("corrugated_iron_02", 2.0, (0.94, 0.80, 0.58)),
    "corr_dark": ("corrugated_iron_02", 2.0, (0.50, 0.52, 0.40)),
    "sandbag": ("hessian_230", 1.0, (0.85, 0.74, 0.54)),
    "tent": ("rough_linen", 1.5, (0.74, 0.68, 0.50)),
}

CONST = {
    # name: (rgb, roughness, metallic, specular)
    "glass": ((0.05, 0.085, 0.10), 0.04, 0.0, 0.7),
    "dark": ((0.012, 0.012, 0.014), 0.85, 0.0, 0.3),
    "frame": ((0.50, 0.49, 0.45), 0.6, 0.0, 0.5),
    "frame_dark": ((0.11, 0.11, 0.12), 0.4, 0.5, 0.5),
    "metal": ((0.33, 0.34, 0.36), 0.4, 0.9, 0.5),
    "metal_dark": ((0.07, 0.07, 0.08), 0.45, 0.8, 0.5),
    "pole": ((0.25, 0.24, 0.22), 0.5, 0.7, 0.5),
    "olive": ((0.23, 0.25, 0.14), 0.65, 0.25, 0.5),
    "olive_dark": ((0.12, 0.13, 0.08), 0.7, 0.2, 0.5),
    "canvas_olive": ((0.27, 0.29, 0.18), 0.9, 0.0, 0.3),
    "tank_tan": ((0.52, 0.45, 0.32), 0.55, 0.45, 0.5),
    "hesco": ((0.50, 0.43, 0.30), 0.95, 0.0, 0.3),
    "crate": ((0.20, 0.23, 0.13), 0.7, 0.1, 0.4),
    "stencil": ((0.62, 0.60, 0.45), 0.7, 0.0, 0.4),
    "camo": ((0.19, 0.21, 0.11), 0.9, 0.0, 0.3),
    "paint_white": ((0.85, 0.85, 0.82), 0.7, 0.0, 0.5),
    "lamp_head": ((0.86, 0.82, 0.66), 0.25, 0.0, 0.6),
    "tire": ((0.02, 0.02, 0.02), 0.9, 0.0, 0.3),
    "glass_car": ((0.04, 0.07, 0.09), 0.05, 0.0, 0.8),
    "flag": ((0.45, 0.07, 0.06), 0.8, 0.0, 0.3),
    "crack": ((0.06, 0.055, 0.05), 0.95, 0.0, 0.3),
    "barb": ((0.16, 0.16, 0.16), 0.5, 0.7, 0.5),
    "fence": ((0.25, 0.26, 0.25), 0.5, 0.8, 0.5),          # chain-link: alpha below
}
ALPHA = {"fence": 0.38}


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
    loaded = {}
    for key, (aid, tile, rgb) in TINTS.items():
        if aid not in loaded:
            maps = bkit.polyhaven_texture(aid, res="1k")
            loaded[aid] = {k: v for k, v in maps.items() if k in ("color", "normal", "roughness")}
        MAT[key] = bkit.pbr_material(key, loaded[aid], scale=1.0, tint=rgb, coords="UV")
        TILE[key] = tile
    print("MAP texture tinted", sorted(TINTS))
    for name, (rgb, rough, metal, spec) in CONST.items():
        MAT[name] = cmat(name, rgb, rough, metal, spec)
    for name in CONST:
        TILE.setdefault(name, 1.0)


# ---------------------------------------------------------------- facades and roofs
def face_frames(cx, cz, hx, hz, y0):
    """The four side walls of a box footprint: (frame, length). Face 0 +z, 1 -z, 2 +x, 3 -x."""
    return [
        (((cx - hx, y0, cz + hz), (1, 0, 0), (0, 0, 1)), 2 * hx),
        (((cx + hx, y0, cz - hz), (-1, 0, 0), (0, 0, -1)), 2 * hx),
        (((cx + hx, y0, cz + hz), (0, 0, -1), (1, 0, 0)), 2 * hz),
        (((cx - hx, y0, cz - hz), (0, 0, 1), (-1, 0, 0)), 2 * hz),
    ]


def corr_face(mb, fr, L, v0, v1, mat, pitch=0.3, depth=0.05, u0=0.0, u1=None, t0=0.0):
    """Corrugated sheet on a facade frame: a zigzag profile along u, extruded from v0 to v1."""
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


def gable(mb, cx, cz, hx, hz, y0, H, rise, roof, wall):
    """Gable roof along x over a box: walls top at y0+H, ridge rise above, triangular ends."""
    yt = y0 + H
    A = (cx - hx, yt, cz - hz)
    B = (cx + hx, yt, cz - hz)
    C = (cx + hx, yt + rise, cz)
    D = (cx - hx, yt + rise, cz)
    E = (cx + hx, yt, cz + hz)
    F = (cx - hx, yt, cz + hz)
    mb.poly([A, B, C, D], roof, (0.0, hz, -rise))
    mb.poly([D, C, E, F], roof, (0.0, hz, rise))
    for sx in (-1, 1):
        xe = cx + sx * hx
        mb.poly([(xe, yt, cz - hz), (xe, yt, cz + hz), (xe, yt + rise, cz)], wall, (sx, 0.0, 0.0))


def axes_of(rot):
    f = (math.sin(rot), 0.0, math.cos(rot))
    s = (math.cos(rot), 0.0, -math.sin(rot))
    return f, s, [s, UPV, f]


def at(b, s, f, lat, up, fw):
    return vadd(b, vmul(s, lat), (0.0, up, 0.0), vmul(f, fw))


def col_fp(x, z, rot, half_len, half_wid, h=3.0, y0=0.0):
    """Collider for a footprint: half_len along the heading (rot), half_wid across it."""
    if abs(math.sin(rot)) < 0.5:
        return (x - half_wid, x + half_wid, z - half_len, z + half_len, y0, y0 + h)
    return (x - half_len, x + half_len, z - half_wid, z + half_wid, y0, y0 + h)


# ---------------------------------------------------------------- vehicles and props
def humvee(mb, x, z, rot, y0=0.0, collide=True):
    f, s, ax = axes_of(rot)
    b = (x, y0, z)
    obox(mb, at(b, s, f, 0, 0.78, 0), ax, (1.05, 0.28, 2.3), "olive")
    obox(mb, at(b, s, f, 0, 1.5, -0.25), ax, (0.92, 0.42, 1.25), ["glass", "glass", "olive", "olive_dark", "olive", "olive"])
    for lat in (-1.05, 1.05):
        for fw in (-1.6, 1.6):
            ocyl(mb, at(b, s, f, lat, 0.42, fw), s, 0.42, 0.42, 0.34, 10, "tire")
    if collide:
        COLS.append(col_fp(x, z, rot, 2.4, 1.1, y0=y0))


def truck(mb, x, z, rot, y0=0.0, collide=True):
    """Military 6x6 cargo truck, olive drab: chassis, canvas cargo box, cab, six wheels."""
    f, s, ax = axes_of(rot)
    b = (x, y0, z)
    obox(mb, at(b, s, f, 0, 1.0, 0), ax, (1.15, 0.2, 3.6), "olive_dark")
    obox(mb, at(b, s, f, 0, 2.35, -1.0), ax, (1.15, 0.95, 2.3), "canvas_olive")
    obox(mb, at(b, s, f, 0, 2.2, 2.5), ax, (1.15, 0.95, 1.05), ["glass", "glass", "olive", "olive_dark", "olive", "olive"])
    for lat in (-1.15, 1.15):
        for fw in (2.5, -1.5, -2.6):
            ocyl(mb, at(b, s, f, lat, 0.5, fw), s, 0.5, 0.5, 0.4, 10, "tire")
    if collide:
        COLS.append(col_fp(x, z, rot, 3.8, 1.3, y0=y0))


def crate(mb, x, z, rot, y0=0.0):
    f, s, ax = axes_of(rot)
    b = (x, y0, z)
    obox(mb, at(b, s, f, 0, 0.3, 0), ax, (0.6, 0.3, 0.4), "crate")
    obox(mb, at(b, s, f, 0, 0.61, 0), ax, (0.45, 0.01, 0.12), "stencil")
    COLS.append(col_fp(x, z, rot, 0.6, 0.6, h=0.7, y0=y0))


def tent(mb, x, z):
    """Ridge tent, 6 x 4.2 m, eaves at 1.0 m, ridge at 2.6 m, ridge along x."""
    hx, hz = 3.0, 2.1
    A = (x - hx, 1.0, z - hz)
    B = (x + hx, 1.0, z - hz)
    C = (x + hx, 2.6, z)
    D = (x - hx, 2.6, z)
    E = (x + hx, 1.0, z + hz)
    F = (x - hx, 1.0, z + hz)
    mb.poly([A, B, C, D], "tent", (0.0, hz, -1.6))
    mb.poly([D, C, E, F], "tent", (0.0, hz, 1.6))
    for sx in (-1, 1):
        xe = x + sx * hx
        mb.poly([(xe, 1.0, z - hz), (xe, 1.0, z + hz), (xe, 2.6, z)], "tent", (sx, 0.0, 0.0))
    COLS.append((x - hx - 0.2, x + hx + 0.2, z - hz - 0.1, z + hz + 0.1, 0.0, 2.6))


def camo_net(mb, x, z, w, d, y=3.4):
    """Camouflage net on four poles, double-sided (top and underside)."""
    for sx in (-1, 1):
        for sz in (-1, 1):
            px, pz = x + sx * w / 2, z + sz * d / 2
            vcyl(mb, px, 0.0, pz, 0.06, 0.06, y, 6, "pole")
            COLS.append((px - 0.2, px + 0.2, pz - 0.2, pz + 0.2, 0.0, y))
    x0, x1, z0, z1 = x - w / 2, x + w / 2, z - d / 2, z + d / 2
    quad_flat(mb, x0, x1, z0, z1, y, "camo", UPV)
    quad_flat(mb, x0, x1, z0, z1, y, "camo", (0.0, -1.0, 0.0))


def hesco_run(mb, a, b):
    """HESCO barrier: 2 m wire-basket modules, 2.2 m tall, along a straight axis-aligned run."""
    ax_, az_ = a
    bx, bz = b
    L = math.hypot(bx - ax_, bz - az_)
    dx, dz = (bx - ax_) / L, (bz - az_) / L
    d3 = (dx, 0.0, dz)
    perp = (-dz, 0.0, dx)
    n = max(1, round(L / 2.0))
    seg = L / n
    for i in range(n):
        t = (i + 0.5) * seg
        cx_, cz_ = ax_ + dx * t, az_ + dz * t
        obox(mb, (cx_, 1.1, cz_), [d3, UPV, perp], (seg / 2, 1.1, 0.75), "hesco")
    x0, x1, z0, z1 = min(ax_, bx), max(ax_, bx), min(az_, bz), max(az_, bz)
    COLS.append((x0 - 0.8, x1 + 0.8, z0 - 0.8, z1 + 0.8, 0.0, 2.2))


def bag_wall(mb, x0, z0, x1, z1, rng, rows=2):
    """Sandbag wall: rows of bags along a straight run, every other row offset by half a bag."""
    L = math.hypot(x1 - x0, z1 - z0)
    ux, uz = (x1 - x0) / L, (z1 - z0) / L
    for r in range(rows):
        off = 0.31 if r % 2 else 0.0
        t = off
        while t <= L + 1e-6:
            px = x0 + ux * t + rng.uniform(-0.04, 0.04)
            pz = z0 + uz * t + rng.uniform(-0.04, 0.04)
            blob(mb, (px, 0.22 + r * 0.34, pz), 0.34 + rng.uniform(-0.02, 0.02), "sandbag", rng,
                 rings=3, segs=6, sy=0.6)
            t += 0.62
    COLS.append((min(x0, x1) - 0.4, max(x0, x1) + 0.4, min(z0, z1) - 0.4, max(z0, z1) + 0.4, 0.0, rows * 0.36 + 0.3))


def barrier(mb, x, z, rot, y0=0.0):
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
    COLS.append(col_fp(x, z, rot, 1.5, 0.3, y0=y0))


def watchtower(mb, x, z):
    """Perimeter watchtower: four leg posts, platform with rails, cabin with glass sides, lamp."""
    for sx in (-1, 1):
        for sz in (-1, 1):
            obox(mb, (x + sx * 1.0, 3.5, z + sz * 1.0), AX0, (0.12, 3.5, 0.12), "pole")
    obox(mb, (x, 7.0, z), AX0, (1.5, 0.12, 1.5), "metal_dark")
    obox(mb, (x, 8.5, z), AX0, (1.2, 1.0, 1.2), ["glass", "glass", "olive", "olive_dark", "olive", "olive"])
    obox(mb, (x, 9.7, z), AX0, (1.4, 0.1, 1.4), "olive_dark")
    for sx, sz in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        obox(mb, (x + sx * 1.45, 7.6, z + sz * 1.45), AX0, (1.5 if sz != 0 else 0.05, 0.05, 1.5 if sx != 0 else 0.05),
             "metal_dark")
    obox(mb, (x, 10.0, z), AX0, (0.3, 0.15, 0.3), "lamp_head")
    LAMPS.append((x, 10.4, z))
    COLS.append((x - 1.3, x + 1.3, z - 1.3, z + 1.3, 0.0, 10.0))


def floodlight(mb, x, z, fx, fz, y0=0.0):
    """22 m pole with a light bank on top, facing (fx, fz) (unit, horizontal). The lamp is a LAMP_
    empty at the head, where the game's night light sits."""
    vcyl(mb, x, y0, z, 0.22, 0.12, 22.0, 8, "pole")
    top = y0 + 22.0
    ax0 = (-fz, 0.0, fx)
    axes = [ax0, UPV, (fx, 0.0, fz)]
    obox(mb, (x, top + 0.4, z), axes, (1.2, 0.35, 0.3), "frame_dark")
    obox(mb, (x + fx * 0.31, top + 0.4, z + fz * 0.31), axes, (1.05, 0.28, 0.03), "lamp_head")
    LAMPS.append((x, top - 0.2, z))
    COLS.append((x - 0.4, x + 0.4, z - 0.4, z + 0.4, y0, y0 + 3.0))


# ---------------------------------------------------------------- buildings
def barracks(mb, cx, cz):
    """Long single-storey barracks, 26 x 9 m, corrugated walls and roof, windows and doors."""
    hx, hz, H, RISE = 13.0, 4.5, 3.6, 1.2
    for fi, (fr, L) in enumerate(face_frames(cx, cz, hx, hz, 0.0)):
        corr_face(mb, fr, L, 0.0, H, "corr_tan", pitch=0.45, depth=0.05)
        wbox(mb, fr, -0.1, L + 0.1, H - 0.1, H + 0.12, 0.0, 0.18, "frame")
        if fi < 2:
            for k in range(5):
                uc = (k + 0.5) * L / 5
                wbox(mb, fr, uc - 0.6, uc + 0.6, 1.3, 2.5, 0.0, 0.07, "glass")
        else:
            wbox(mb, fr, L / 2 - 0.6, L / 2 + 0.6, 0.0, 2.3, 0.0, 0.07, "dark")
    gable(mb, cx, cz, hx, hz, 0.0, H, RISE, "corr_dark", "corr_tan")
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, 0.0, H + RISE))


def hangar(mb_b, mb_v, mb_p, cx, cz, door_sign, g, rng):
    """Vehicle hangar 30 x 20 m, 7 m walls, corrugated gable roof. The door opening (16 x 6.5 m)
    is open on the door_sign side: leaves folded flat on the wall, a truck and a humvee inside.
    g = ground height under the hangar (pads sit on it)."""
    hx, hz, H, RISE = 15.0, 10.0, 7.0, 3.5
    OW, OH = 16.0, 6.5
    door_fi = 0 if door_sign > 0 else 1
    wall = rng.choice(["corr_olive", "corr_olive", "corr_tan"])
    for fi, (fr, L) in enumerate(face_frames(cx, cz, hx, hz, g)):
        if fi == door_fi:
            uL, uR = (L - OW) / 2, (L + OW) / 2
            corr_face(mb_b, fr, L, 0.0, H, wall, pitch=0.4, depth=0.06, u0=0.0, u1=uL)
            corr_face(mb_b, fr, L, 0.0, H, wall, pitch=0.4, depth=0.06, u0=uR, u1=L)
            corr_face(mb_b, fr, L, OH, H, wall, pitch=0.4, depth=0.06, u0=uL, u1=uR)
            wbox(mb_b, fr, uL - 0.3, uL, 0.0, OH, 0.0, 0.3, "frame_dark")
            wbox(mb_b, fr, uR, uR + 0.3, 0.0, OH, 0.0, 0.3, "frame_dark")
            wbox(mb_b, fr, uL - 5.4, uL - 0.3, 0.0, OH - 0.1, 0.12, 0.2, "corr_dark")
            wbox(mb_b, fr, uR + 0.3, uR + 5.4, 0.0, OH - 0.1, 0.12, 0.2, "corr_dark")
        else:
            corr_face(mb_b, fr, L, 0.0, H, wall, pitch=0.4, depth=0.06)
    gable(mb_b, cx, cz, hx, hz, g, H, RISE, "corr_dark", wall)
    quad_flat(mb_b, cx - hx + 0.3, cx + hx - 0.3, cz - hz + 0.3, cz + hz - 0.3, g + 0.07, "pad")
    truck(mb_v, cx - 6.0, cz - door_sign * 3.0, math.pi / 2, y0=g, collide=False)
    humvee(mb_v, cx + 8.0, cz - door_sign * 2.5, math.pi / 2, y0=g, collide=False)
    COLS.append((cx - hx, cx + hx, cz - hz, cz + hz, g, g + H + RISE))


def headquarters(mb_b, mb_p, mb_mast, mb_v, cx, cz, rng):
    """Two-storey concrete command post, 24 x 13 m, with windows, a door on the helipad side,
    a lattice antenna mast, a flagpole, a helipad with its H, sandbags and two humvees."""
    W, D, H = 24.0, 13.0, 7.6
    bx, bz = cx - 3.0, cz - 5.5
    obox(mb_b, (bx, H / 2, bz), UPAX, (W / 2, H / 2, D / 2), "concrete")
    faces = face_frames(bx, bz, W / 2, D / 2, 0.0)
    for fi, (fr, L) in enumerate(faces):
        n = max(2, int(L / 3.4))
        for k in range(2):
            v0 = 1.2 + k * 3.8
            for m in range(n):
                uc = (m + 0.5) * L / n
                if fi == 0 and abs(uc - L / 2) < 1.5:
                    continue
                wbox(mb_b, fr, uc - 0.7, uc + 0.7, v0, v0 + 1.5, 0.0, 0.05, "glass")
    fr0, L0 = faces[0]
    wbox(mb_b, fr0, L0 / 2 - 1.1, L0 / 2 + 1.1, 0.0, 2.6, 0.0, 0.08, "dark")
    obox(mb_b, (bx + 6.0, H + 0.5, bz + 2.0), UPAX, (1.2, 0.5, 0.9), "metal")
    obox(mb_b, (bx - 6.0, H + 0.5, bz - 2.5), UPAX, (1.2, 0.5, 0.9), "metal")
    COLS.append((bx - W / 2, bx + W / 2, bz - D / 2, bz + D / 2, 0.0, H))

    # lattice mast, 24 m, legs on a 1.4 m square
    mx, mz = cx + 14.0, cz - 10.0
    for sx in (-1, 1):
        for sz in (-1, 1):
            obox(mb_mast, (mx + sx * 0.7, 12.0, mz + sz * 0.7), UPAX, (0.05, 12.0, 0.05), "metal")
    for lvl in range(1, 8):
        y = lvl * 3.0
        for sz in (-1, 1):
            obox(mb_mast, (mx, y, mz + sz * 0.7), UPAX, (0.7, 0.04, 0.04), "metal")
        for sx in (-1, 1):
            obox(mb_mast, (mx + sx * 0.7, y, mz), UPAX, (0.04, 0.04, 0.7), "metal")
    vcyl(mb_mast, mx, 24.0, mz, 0.05, 0.02, 1.0, 6, "metal")
    COLS.append((mx - 0.9, mx + 0.9, mz - 0.9, mz + 0.9, 0.0, 24.0))

    # flagpole and flag, flag hangs toward +x
    fx, fz = cx - 17.0, cz - 4.0
    vcyl(mb_mast, fx, 0.0, fz, 0.06, 0.05, 8.0, 6, "pole")
    COLS.append((fx - 0.3, fx + 0.3, fz - 0.3, fz + 0.3, 0.0, 8.0))
    mb_mast.poly([(fx + 0.1, 6.6, fz), (fx + 2.3, 6.6, fz), (fx + 2.3, 8.0, fz), (fx + 0.1, 8.0, fz)], "flag", (0, 0, 1))
    mb_mast.poly([(fx + 0.1, 6.6, fz), (fx + 0.1, 8.0, fz), (fx + 2.3, 8.0, fz), (fx + 2.3, 6.6, fz)], "flag", (0, 0, -1))

    # helipad: concrete disk, white rim and H
    hx_, hz_ = cx + 12.0, cz + 12.0
    disk(mb_p, hx_, hz_, 7.5, 0.07, "pad")
    ring_flat(mb_p, hx_, hz_, 7.1, 7.5, 0.075, "paint_white")
    rect_at(mb_p, hx_ - 1.9, hx_ - 1.3, hz_ - 2.6, hz_ + 2.6, 0.08, "paint_white")
    rect_at(mb_p, hx_ + 1.3, hx_ + 1.9, hz_ - 2.6, hz_ + 2.6, 0.08, "paint_white")
    rect_at(mb_p, hx_ - 1.3, hx_ + 1.3, hz_ - 0.3, hz_ + 0.3, 0.08, "paint_white")

    bag_wall(mb_p, cx - 12.0, cz + 3.0, cx + 4.0, cz + 3.0, rng, rows=2)
    humvee(mb_v, cx - 14.0, cz + 10.0, 0.0)
    humvee(mb_v, cx - 4.0, cz - 16.0, math.pi / 2)


def fuel_depot(mb_f, cx, cz):
    """Fuel depot: four horizontal tanks on cradles, one tall tank, a pump shed, 4 barrel spots."""
    for x, z in ((cx - 7.0, cz - 8.0), (cx + 7.0, cz - 8.0), (cx - 7.0, cz + 4.0), (cx + 7.0, cz + 4.0)):
        ocyl(mb_f, (x, 2.8, z), (1, 0, 0), 2.2, 2.2, 10.0, 14, "tank_tan")
        for dx in (-3.5, 3.5):
            obox(mb_f, (x + dx, 0.4, z), UPAX, (0.4, 0.4, 1.8), "metal_dark")
        COLS.append((x - 5.0, x + 5.0, z - 2.2, z + 2.2, 0.0, 4.4))
    tx, tz = cx + 12.0, cz + 10.0
    vcyl(mb_f, tx, 0.0, tz, 3.2, 3.2, 8.0, 18, "tank_tan")
    for y in (2.5, 5.5):
        vcyl(mb_f, tx, y, tz, 3.25, 3.25, 0.25, 18, "metal_dark", caps=False)
    COLS.append((tx - 3.2, tx + 3.2, tz - 3.2, tz + 3.2, 0.0, 8.0))
    sx_, sz_ = cx - 12.0, cz + 11.0
    obox(mb_f, (sx_, 1.4, sz_), UPAX, (2.0, 1.4, 1.5), "olive")
    obox(mb_f, (sx_, 2.9, sz_), UPAX, (2.2, 0.1, 1.7), "olive_dark")
    COLS.append((sx_ - 2.0, sx_ + 2.0, sz_ - 1.5, sz_ + 1.5, 0.0, 3.0))
    BARRELS.extend([(cx - 15.0, cz + 15.0), (cx + 15.0, cz + 15.0), (cx - 15.0, cz - 15.0), (cx + 15.0, cz - 6.0)])


def motor_pool(mb_v, mb_p, cx, cz, rng):
    """Six parked vehicles in three columns and two rows, some crates, one barrel spot."""
    for xo in (-12.0, 0.0, 12.0):
        for zo in (-7.0, 6.0):
            x, z = cx + xo, cz + zo
            if rng.random() < 0.55:
                truck(mb_v, x, z, 0.0)
            else:
                humvee(mb_v, x, z, 0.0)
    crate(mb_p, cx + 16.0, cz - 14.0, 0.0)
    crate(mb_p, cx + 17.2, cz - 14.0, 0.0)
    BARRELS.append((cx - 16.0, cz + 14.0))


def tent_block(mb_t, mb_v, mb_p, cx, cz):
    for xo in (-12.0, 0.0, 12.0):
        for zo in (-8.0, 6.0):
            tent(mb_t, cx + xo, cz + zo)
    truck(mb_v, cx - 16.0, cz + 14.0, 0.0)
    truck(mb_v, cx + 16.0, cz - 14.0, math.pi / 2)
    for x, z in ((cx - 3.0, cz + 15.0), (cx - 1.5, cz + 15.0), (cx - 2.25, cz + 16.5)):
        crate(mb_p, x, z, 0.0)


def hesco_block(mb_p, mb_v, cx, cz, rng):
    """HESCO compound: three walls with a gap, sandbag bunkers inside, jersey barriers, crates."""
    hesco_run(mb_p, (cx - 16.0, cz - 8.0), (cx - 2.0, cz - 8.0))
    hesco_run(mb_p, (cx + 2.0, cz - 8.0), (cx + 16.0, cz - 8.0))
    hesco_run(mb_p, (cx - 16.0, cz - 8.0), (cx - 16.0, cz + 8.0))
    hesco_run(mb_p, (cx + 16.0, cz - 8.0), (cx + 16.0, cz + 8.0))
    bag_wall(mb_p, cx - 11.0, cz + 10.0, cx - 3.0, cz + 10.0, rng)
    bag_wall(mb_p, cx + 4.0, cz - 4.0, cx + 12.0, cz - 4.0, rng)
    barrier(mb_p, cx - 6.0, cz + 1.0, math.pi / 2)
    barrier(mb_p, cx + 6.0, cz + 14.0, 0.0)
    for x, z in ((cx - 13.0, cz - 1.0), (cx - 13.0, cz + 1.2), (cx - 11.8, cz + 0.1)):
        crate(mb_p, x, z, 0.0)
    BARRELS.extend([(cx + 14.0, cz - 12.0), (cx - 14.0, cz + 6.0)])


def sandbag_block(mb_p, mb_c, cx, cz, rng):
    """Sandbag positions: four bag walls, a camouflage net on poles, jersey barriers, a humvee."""
    bag_wall(mb_p, cx - 14.0, cz - 10.0, cx - 2.0, cz - 10.0, rng)
    bag_wall(mb_p, cx - 10.0, cz + 6.0, cx - 10.0, cz + 15.0, rng)
    bag_wall(mb_p, cx + 4.0, cz + 2.0, cx + 14.0, cz + 2.0, rng)
    bag_wall(mb_p, cx + 4.0, cz - 12.0, cx + 12.0, cz - 12.0, rng)
    camo_net(mb_c, cx - 2.0, cz + 10.0, 8.0, 6.0)
    barrier(mb_p, cx + 12.0, cz + 12.0, 0.0)
    barrier(mb_p, cx - 14.0, cz + 13.0, math.pi / 2)
    BARRELS.extend([(cx - 6.0, cz + 0.0), (cx + 10.0, cz - 6.0)])


# ---------------------------------------------------------------- perimeter, towers and ground helpers
def fence_run(mb, a, b):
    """Chain-link run between two axis-aligned points: steel posts every 3 m, top rail, see-through
    panel, three barbed-wire strands. One collider for the whole run."""
    ax_, az_ = a
    bx, bz = b
    L = math.hypot(bx - ax_, bz - az_)
    dx, dz = (bx - ax_) / L, (bz - az_) / L
    d3 = (dx, 0.0, dz)
    perp = (-dz, 0.0, dx)
    n = max(1, round(L / 3.0))
    for i in range(n + 1):
        px, pz = ax_ + (bx - ax_) * i / n, az_ + (bz - az_) * i / n
        obox(mb, (px, 1.2, pz), UPAX, (0.04, 1.2, 0.04), "metal")
    mx, mz = (ax_ + bx) / 2, (az_ + bz) / 2
    obox(mb, (mx, 2.36, mz), [d3, UPV, perp], (L / 2, 0.03, 0.03), "metal")
    for hgt in (2.45, 2.62, 2.79):
        obox(mb, (mx, hgt, mz), [d3, UPV, perp], (L / 2, 0.025, 0.025), "barb")
    b0, b1 = (ax_, 0.0, az_), (bx, 0.0, bz)
    t0, t1 = (ax_, FENCE_H, az_), (bx, FENCE_H, bz)
    mb.poly([b0, b1, t1, t0], "fence", perp)
    mb.poly([b0, t0, t1, b1], "fence", vmul(perp, -1.0))
    x0, x1, z0, z1 = min(ax_, bx), max(ax_, bx), min(az_, bz), max(az_, bz)
    COLS.append((x0 - 0.12, x1 + 0.12, z0 - 0.12, z1 + 0.12, 0.0, 2.8))


def ground_h(x, z):
    """Height of the desert outside the base: dunes rising from the fence line, hills, flat
    corridors for the roads that leave the base, and flat pads for the ring hangars."""
    d = max(abs(x), abs(z)) - BASE
    if d <= 0:
        return 0.0
    w = smoothstep(0.0, 16.0, d)
    h = w * (1.4 + 2.6 * (0.5 + 0.5 * math.sin(x * 0.047 + z * 0.023 + 0.7)) * (0.55 + 0.45 * math.cos(z * 0.039 - x * 0.021))
             + 0.9 * math.sin(x * 0.12 + 1.1) ** 2 * math.cos(z * 0.09) ** 2)
    for hx, hz, hh, rr in HILLS:
        r = math.hypot(x - hx, z - hz)
        if r < rr:
            h += hh * (1 - r / rr) ** 1.6
    cands = []
    for rc in (-140.0, 140.0):
        if abs(z) >= BASE:
            cands.append(abs(x - rc))
        if abs(x) >= BASE:
            cands.append(abs(z - rc))
    if cands:
        h *= smoothstep(7.0, 13.0, min(cands))
    for px, pz, hw, hd in PADS:
        dx = max(abs(x - px) - hw, 0.0)
        dz = max(abs(z - pz) - hd, 0.0)
        h *= smoothstep(0.0, 8.0, math.hypot(dx, dz))
    return h


def build_outer(mb, rng):
    """Dune and hill heightfield outside the fence, 5 m cells, sand or rock by height."""
    xs = [-200.0 + 5.0 * i for i in range(81)]
    hs = [[ground_h(x, z) + OFF for z in xs] for x in xs]
    for i in range(80):
        for j in range(80):
            x0, x1, z0, z1 = xs[i], xs[i + 1], xs[j], xs[j + 1]
            if x0 >= -BASE and x1 <= BASE and z0 >= -BASE and z1 <= BASE:
                continue
            p00 = (x0, hs[i][j], z0)
            p10 = (x1, hs[i + 1][j], z0)
            p11 = (x1, hs[i + 1][j + 1], z1)
            p01 = (x0, hs[i][j + 1], z1)
            avg = (hs[i][j] + hs[i + 1][j] + hs[i + 1][j + 1] + hs[i][j + 1]) / 4
            mat = "rock" if avg > OFF + 6.0 else "sand"
            mb.poly([p00, p10, p11], mat, UPV)
            mb.poly([p00, p11, p01], mat, UPV)


def road_pieces(rc, lo=-BASE, hi=BASE):
    """Pieces of an x-running road band (z = rc) that do not cross the z-running roads."""
    pieces = []
    prev = lo
    for cut in ROADS:
        a, b = cut - ROAD_HW, cut + ROAD_HW
        if a > prev + 0.01:
            pieces.append((prev, a))
        prev = max(prev, b)
    if hi > prev + 0.01:
        pieces.append((prev, hi))
    return pieces


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

    print("MAP stage: ground, roads, pads, dunes")
    names = ["Ground_sand", "Ground_road", "Ground_pad", "Ground_dirt", "Ground_outer", "Ground_track",
             "Rocks", "Fences", "Towers", "Buildings", "Vehicles", "Tents", "Fuel", "Props", "Lights"]
    M = {n: Mesh(n) for n in names}
    rect_at(M["Ground_sand"], -200, 200, -200, 200, 0.0, "sand")
    # roads: full-length z bands, x bands cut where they cross them; shoulders of dirt either side
    for rc in ROADS:
        rect_at(M["Ground_road"], rc - ROAD_HW, rc + ROAD_HW, -BASE, BASE, 0.035, "road")
        rect_at(M["Ground_dirt"], rc - ROAD_HW - 1.5, rc - ROAD_HW, -BASE, BASE, 0.015, "dirt")
        rect_at(M["Ground_dirt"], rc + ROAD_HW, rc + ROAD_HW + 1.5, -BASE, BASE, 0.015, "dirt")
        for a, b in road_pieces(rc):
            rect_at(M["Ground_road"], a, b, rc - ROAD_HW, rc + ROAD_HW, 0.035, "road")
            rect_at(M["Ground_dirt"], a, b, rc - ROAD_HW - 1.5, rc - ROAD_HW, 0.015, "dirt")
            rect_at(M["Ground_dirt"], a, b, rc + ROAD_HW, rc + ROAD_HW + 1.5, 0.015, "dirt")
    for _ in range(70):   # cracks across the roads
        rc = rng.choice(ROADS)
        if rng.random() < 0.5:
            x = rc + rng.uniform(-4.5, 4.5)
            z = rng.uniform(-BASE + 2, BASE - 2)
            rect_at(M["Ground_road"], x - 0.04, x + 0.04, z, z + rng.uniform(1.5, 4.5), 0.04, "crack")
        else:
            z = rc + rng.uniform(-4.5, 4.5)
            x = rng.uniform(-BASE + 2, BASE - 2)
            rect_at(M["Ground_road"], x, x + rng.uniform(1.5, 4.5), z - 0.04, z + 0.04, 0.04, "crack")
    # block ground: concrete pads or dirt patches
    kinds = {}
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            kind = ROWS[j][i]
            kinds[(cx, cz)] = kind
            if kind in ("BARRACKS", "HANGAR", "HQ"):
                rect_at(M["Ground_pad"], cx - HALF, cx + HALF, cz - HALF, cz + HALF, 0.05, "pad")
            else:
                rect_at(M["Ground_dirt"], cx - 20.0, cx + 20.0, cz - 20.0, cz + 20.0, 0.02, "dirt")
    for cx, cz, _ in RING_HANGARS:
        rect_at(M["Ground_pad"], cx - 18.0, cx + 18.0, cz - 13.0, cz + 13.0, OFF + 0.05, "pad")
    build_outer(M["Ground_outer"], rng)
    for rc in (-140.0, 140.0):   # roads leaving the base, as dirt tracks to the edge of the map
        for sg in (-1.0, 1.0):
            rect_at(M["Ground_track"], rc - 6.0, rc + 6.0, sg * (BASE - 2.0), sg * 200.0, OFF + 0.04, "dirt")
            rect_at(M["Ground_track"], sg * (BASE - 2.0), sg * 200.0, rc - 6.0, rc + 6.0, OFF + 0.04, "dirt")

    # boulders on the dunes and hills, away from the tracks
    nb = 0
    tries = 0
    while nb < 90 and tries < 2000:
        tries += 1
        x = rng.uniform(-199, 199)
        z = rng.uniform(-199, 199)
        if max(abs(x), abs(z)) <= BASE + 3:
            continue
        if any((abs(x - rc) < 9 and abs(z) > BASE) or (abs(z - rc) < 9 and abs(x) > BASE) for rc in (-140.0, 140.0)):
            continue
        r = rng.uniform(0.8, 2.6)
        blob(M["Rocks"], (x, ground_h(x, z) + OFF + r * 0.35, z), r, "boulder", rng, rings=3, segs=6, sy=0.7)
        nb += 1

    print("MAP stage: perimeter fence and watchtowers")
    F = BASE
    fence_run(M["Fences"], (-134.0, -F), (134.0, -F))
    fence_run(M["Fences"], (-134.0, F), (134.0, F))
    fence_run(M["Fences"], (-F, -134.0), (-F, 134.0))
    fence_run(M["Fences"], (F, -134.0), (F, 134.0))
    for x, z in TOWERS:
        watchtower(M["Towers"], x, z)

    print("MAP stage: blocks")
    for j, cz in enumerate(BC):
        for i, cx in enumerate(BC):
            kind = ROWS[j][i]
            corners = [(-1, -1), (1, 1)] if (i + j) % 2 == 0 else [(1, -1), (-1, 1)]
            if kind in ("HQ", "FUEL", "MOTOR", "SANDBAG"):
                corners = [(-1, -1), (1, 1), (1, -1), (-1, 1)]
            for sx, sz in corners:
                lx, lz = cx + sx * 16.0, cz + sz * 16.0
                d = math.hypot(sx, sz)
                floodlight(M["Lights"], lx, lz, -sx / d, -sz / d)
            if kind == "BARRACKS":
                barracks(M["Buildings"], cx, cz - 8.5)
                barracks(M["Buildings"], cx, cz + 8.5)
                humvee(M["Vehicles"], cx, cz, math.pi / 2)
                crate(M["Props"], cx + 12.0, cz - 17.0, 0.0)
                crate(M["Props"], cx + 13.2, cz - 17.0, 0.0)
                crate(M["Props"], cx - 12.0, cz + 17.0, 0.0)
            elif kind == "HANGAR":
                sign = 1 if rng.random() < 0.5 else -1
                hangar(M["Buildings"], M["Vehicles"], M["Props"], cx, cz, sign, 0.0, rng)
                humvee(M["Vehicles"], cx + 12.0, cz + sign * 15.0, 0.0)
                crate(M["Props"], cx - 13.0, cz + sign * 15.0, 0.0)
                crate(M["Props"], cx - 11.8, cz + sign * 15.0, 0.0)
            elif kind == "MOTOR":
                motor_pool(M["Vehicles"], M["Props"], cx, cz, rng)
            elif kind == "FUEL":
                fuel_depot(M["Fuel"], cx, cz)
                humvee(M["Vehicles"], cx + 18.0, cz + 4.0, 0.0)
            elif kind == "TENTS":
                tent_block(M["Tents"], M["Vehicles"], M["Props"], cx, cz)
            elif kind == "HQ":
                headquarters(M["Buildings"], M["Props"], M["Towers"], M["Vehicles"], cx, cz, rng)
            elif kind == "HESCO":
                hesco_block(M["Props"], M["Vehicles"], cx, cz, rng)
            elif kind == "SANDBAG":
                sandbag_block(M["Props"], M["Props"], cx, cz, rng)

    print("MAP stage: ring hangars and floodlights")
    for cx, cz, sign in RING_HANGARS:
        g = OFF
        hangar(M["Buildings"], M["Vehicles"], M["Props"], cx, cz, sign, g, rng)
        for ox, oz in ((-16.0, -11.0), (16.0, 11.0)):
            x, z = cx + ox, cz + oz
            d = math.hypot(ox, oz)
            floodlight(M["Lights"], x, z, -ox / d, -oz / d, y0=ground_h(x, z) + OFF)
    print("MAP stage: build objects")
    groups = [M[n] for n in names]
    objs = []
    tri_mesh = 0
    for mb in groups:
        if mb.faces:
            objs.append(mb.build(coll))
            tri_mesh += mb.tris()

    # gameplay data: COL_ unit boxes (scaled, never rotated), LAMP_ and BARREL_ empties
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
    for i, (x, z) in enumerate(BARRELS):
        o = bpy.data.objects.new(f"BARREL_{i + 1:02d}", None)
        o.empty_display_type = "PLAIN_AXES"
        o.empty_display_size = 0.3
        o.location = G((x, 0.45, z))
        coll.objects.link(o)
        objs.append(o)

    tri_col = 12 * len(COLS)
    tri_total = tri_mesh + tri_col
    # overlap check on the colliders (footprints that intersect by more than 0.2 m on both axes)
    overl = 0
    for a in range(len(COLS)):
        ax0, ax1, az0, az1, ay0, ay1 = COLS[a]
        for b in range(a + 1, len(COLS)):
            bx0, bx1, bz0, bz1, by0, by1 = COLS[b]
            if min(ax1, bx1) - max(ax0, bx0) > 0.2 and min(az1, bz1) - max(az0, bz0) > 0.2:
                overl += 1
                if overl <= 40:
                    print(f"MAP overlap {a + 1}:{tuple(round(v, 1) for v in COLS[a][:4])} "
                          f"{b + 1}:{tuple(round(v, 1) for v in COLS[b][:4])}")
    print(f"MAP counts: COL={len(COLS)} LAMP={len(LAMPS)} BARREL={len(BARRELS)} "
          f"tris_mesh={tri_mesh} tris_col={tri_col} tris_total={tri_total} col_overlaps={overl} rocks={nb}")

    if RENDER_LIST != "none":
        render_previews(objs)

    if DO_EXPORT:
        for o in objs:
            if o.name.startswith("COL_"):
                o.hide_render = False
        bkit.export_glb(OUT_GLB, objs, image_format="JPEG")
        print("MAP exported", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")
    print(f"MAP done in {time.time() - t_start:.0f}s")


# ---------------------------------------------------------------- previews (day, dust storm)
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
    """Dust-storm sky: hazy ochre, low and bright, no HDRI so it works offline."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.62, 0.52, 0.38, 1.0)
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
    sun = bkit.sun(elevation=24, azimuth=150, strength=2.2, softness=3.0, color=(1.0, 0.86, 0.62))
    cols = [o for o in objs if o.name.startswith("COL_") or o.name.startswith("LAMP_")]
    for o in cols:
        o.hide_render = True
    for name in [w.strip() for w in RENDER_LIST.split(",") if w.strip()]:
        if name == "top":
            scene.render.resolution_x = scene.render.resolution_y = RES_W
            cam = make_camera("CamTop", (0, 400, 0), (0, 0, 0), ortho=430.0)
        elif name == "street":
            scene.render.resolution_x = RES_W
            scene.render.resolution_y = int(RES_W * 0.62)
            cam = make_camera("CamStreet", (START[0], 1.7, START[1]), (START[0], 1.5, 140.0), lens=26.0)
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
