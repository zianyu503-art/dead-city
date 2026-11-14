"""Broodmother (巢母) boss for 死城突圍 - Blender -> assets/models/brood.glb.

Run (from the project root, output scratch dir as the argument):
    nohup python3 /Users/alex/.claude/skills/blender-modeling/scripts/run.py \
        tools/blender/brood.py <scratch_dir> > <scratch_dir>/run.log 2>&1 &

Game space: +Y up, +Z forward, metres. B() maps game -> Blender (Z-up); the glTF
exporter (Y-up) maps it back, so the GLB is in game space. Parts keep the game's
names, origins and scale:
  brood_body   body space, origin on the ground
  brood_fangs  body space, ring of fangs and split mandibles around the mouth
  brood_leg    one leg, origin at the hip, reaching +X (the game mirrors it)
  brood_sac    one egg sac, origin at its centre

Method: Skin modifier along a Catmull-Rom spine (the same idea as zombie.py), then
Subdivision, then per-vertex displacement for bulges, eggs, plates and dishes.
body, fangs and leg share one baked 2048 texture set; the sac is a separate mesh
with UVs and its own flat translucent material (the game overrides it).
"""
import math
import os
import random
import sys

sys.path.insert(0, "/Users/alex/.claude/skills/blender-modeling/scripts")
import bpy
import bmesh
from mathutils import Matrix, Vector

import bkit

ROOT = "/Users/alex/射擊遊戲"
GLB = os.path.join(ROOT, "assets/models/brood.glb")
PREV = os.path.join(ROOT, ".claude/work")
OUT = sys.argv[sys.argv.index("--") + 1]
TEX = os.path.join(OUT, "textures")
os.makedirs(PREV, exist_ok=True)
os.makedirs(os.path.dirname(GLB), exist_ok=True)


# ------------------------------------------------------------------ coordinates

def B(x, y, z):
    """Game (+Y up, +Z forward) -> Blender (+Z up, -Y forward), as zombie.py does."""
    return Vector((x, -z, y))


def G(v):
    """Blender vector -> game tuple."""
    return (v.x, v.z, -v.y)


def lerp(a, b, t):
    return a + (b - a) * t


def dist3(a, b):
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b)))


def interp(z, zs, vs):
    if z <= zs[0]:
        return vs[0]
    for i in range(len(zs) - 1):
        if z <= zs[i + 1]:
            return lerp(vs[i], vs[i + 1], (z - zs[i]) / (zs[i + 1] - zs[i]))
    return vs[-1]


def cr(p0, p1, p2, p3, t):
    """Catmull-Rom point between p1 and p2 (works on any tuple length)."""
    t2, t3 = t * t, t * t * t
    return tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2
                        + (-a + 3 * b - 3 * c + d) * t3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def sample(keys, sub):
    """Smooth path through keys; each key is (x, y, z, rx, ry)."""
    out, n = [], len(keys)
    for i in range(n - 1):
        p0, p1, p2, p3 = keys[max(i - 1, 0)], keys[i], keys[i + 1], keys[min(i + 2, n - 1)]
        for k in range(sub):
            out.append(cr(p0, p1, p2, p3, k / sub))
    out.append(keys[-1])
    return out


# ------------------------------------------------------------------ materials

def make_mat(name, dark, light, rough=0.5, bump=0.35, scale=3.0, vein=None):
    """Procedural PBR on object coords; the bake turns it into the shared texture set."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = next(n for n in N if n.type == "BSDF_PRINCIPLED")
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 8.0
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    L.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if vein:
        # thin wandering vein lines: a narrow band around the noise midpoint (not a crackle grid)
        vcol, vscale, vwidth = vein
        vn = N.new("ShaderNodeTexNoise")
        vn.inputs["Scale"].default_value = vscale
        vn.inputs["Detail"].default_value = 6.0
        L.new(tc.outputs["Object"], vn.inputs["Vector"])
        vr = N.new("ShaderNodeValToRGB")
        vr.color_ramp.elements[0].position = 0.5 - vwidth
        vr.color_ramp.elements[0].color = (0, 0, 0, 1)
        vr.color_ramp.elements[1].position = 0.5
        vr.color_ramp.elements[1].color = (1, 1, 1, 1)
        e = vr.color_ramp.elements.new(0.5 + vwidth)
        e.color = (0, 0, 0, 1)
        L.new(vn.outputs["Fac"], vr.inputs["Fac"])
        mix = N.new("ShaderNodeMixRGB")
        mix.blend_type = "MIX"
        L.new(vr.outputs["Color"], mix.inputs["Fac"])
        L.new(col, mix.inputs["Color1"])
        mix.inputs["Color2"].default_value = (*vcol, 1.0)
        col = mix.outputs["Color"]
    L.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    if bump:
        bp = N.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.01
        L.new(nz.outputs["Fac"], bp.inputs["Height"])
        L.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return m


# ------------------------------------------------------------------ mesh helpers

def new_obj(name, bm, mats=()):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def tag(obj, part):
    """Face attribute that says which game part a face belongs to (survives join and bake)."""
    att = obj.data.attributes.get("part") or obj.data.attributes.new("part", "INT", "FACE")
    for i in range(len(obj.data.polygons)):
        att.data[i].value = part


def skin_obj(name, nodes, subdiv, mats, part=None):
    """Skin modifier along nodes (x, y, z, rx, ry in game space), then Subdivision, applied."""
    bm = bmesh.new()
    sl = bm.verts.layers.skin.verify()          # create the layer before any vertex exists
    vs = [bm.verts.new(B(n[0], n[1], n[2])) for n in nodes]
    for a, b in zip(vs, vs[1:]):
        bm.edges.new((a, b))
    for v, n in zip(vs, nodes):
        v[sl].radius = (n[3], n[4])
    vs[0][sl].use_root = True
    ob = new_obj(name, bm, mats)
    ob.modifiers.new("Skin", "SKIN")
    if subdiv > 0:                              # level 0 would be a disabled modifier
        sub = ob.modifiers.new("Subsurf", "SUBSURF")
        sub.levels = subdiv
        sub.render_levels = subdiv
    bkit.apply_all(ob)
    if part is not None:
        tag(ob, part)
    return ob


def warp(obj, fn):
    """Displace every vertex; fn takes and returns game-space coordinates."""
    for v in obj.data.vertices:
        g = G(v.co)
        v.co = B(*fn(*g))
    obj.data.update()


def sphere_bm(c, r, u=12, v=8):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    bmesh.ops.translate(bm, vec=B(*c), verts=bm.verts[:])
    return bm


def spine_bm(base, d, r, length):
    """Small tapered cone that starts at base and points along d (game space)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6,
                          radius1=r, radius2=0.0, depth=length)
    dv = B(*d).normalized()
    q = Vector((0, 0, 1)).rotation_difference(dv)
    M = Matrix.Translation(B(*base) + dv * (length * 0.5)) @ q.to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts[:])
    return bm


# ------------------------------------------------------------------ broodmother body

# spine keys (x, y, z, rx, ry): rear of abdomen -> swollen abdomen -> waist -> thorax -> neck -> skull -> snout
BODY_KEYS = [
    (0, 1.14, -2.22, 0.20, 0.20),
    (0, 1.18, -1.92, 0.62, 0.62),
    (0, 1.20, -1.50, 0.84, 0.84),
    (0, 1.22, -1.10, 0.93, 0.92),   # swollen egg-laden abdomen
    (0, 1.22, -0.60, 0.82, 0.80),
    (0, 1.20, -0.10, 0.60, 0.62),   # waist
    (0, 1.26, 0.35, 0.67, 0.64),    # thorax
    (0, 1.34, 0.86, 0.37, 0.36),    # neck
    (0, 1.45, 1.20, 0.32, 0.31),    # skull
    (0, 1.36, 1.45, 0.25, 0.22),    # snout
]
KZ = [k[2] for k in BODY_KEYS]
KY = [k[1] for k in BODY_KEYS]
KRX = [k[3] for k in BODY_KEYS]

SACS = [(0.0, 1.95, -1.05), (-0.48, 1.72, -0.45), (0.5, 1.78, -0.3)]
EYES = [(0.1, 1.55, 1.52), (-0.1, 1.55, 1.52), (0.19, 1.5, 1.44),
        (-0.19, 1.5, 1.44), (0.07, 1.64, 1.46), (-0.07, 1.64, 1.46)]
MOUTH = (0.0, 1.33, 1.62)


def axis_y(z):
    return interp(z, KZ, KY)


def rad_x(z):
    return interp(z, KZ, KRX)


rng = random.Random(7)
EGGS = []                                  # bulging eggs under the stretched abdomen skin
while len(EGGS) < 14:
    z = rng.uniform(-2.0, -0.5)
    th = rng.uniform(-2.3, 2.3)
    R = rad_x(z)
    c = (R * math.sin(th), axis_y(z) + R * math.cos(th), z)
    if any(dist3(c, s) < 0.42 for s in SACS):
        continue
    EGGS.append((c, rng.uniform(0.07, 0.11), rng.uniform(0.12, 0.16)))


def body_warp(x, y, z):
    ay = axis_y(z)
    dx, dy = x, y - ay
    r = math.hypot(dx, dy) or 1e-6
    nx, ny = dx / r, dy / r
    p = (x, y, z)
    d = 0.009 * math.sin(7 * x + 3 * z) * math.sin(5 * y + 2 * z) + 0.006 * math.sin(19 * z + 11 * x)
    for c, h, s in EGGS:
        q = dist3(p, c)
        d += h * math.exp(-q * q / (2 * s * s))
    if -0.35 < z < 0.7 and ny > 0.05:          # overlapping dorsal chitin plates on the thorax
        u = (z + 0.35) / 0.13
        f = u - math.floor(u)
        d += 0.03 * f * f * min(1.0, (ny - 0.05) / 0.25)
    for c in SACS:                             # cradles: dish inside, rim around
        q = dist3(p, c)
        if q < 0.34:
            d -= 0.05 * (1 - (q / 0.34) ** 2)
        elif q < 0.46:
            d += 0.025 * (1 - (q - 0.34) / 0.12)
    for c in EYES:                             # eye sockets
        q = dist3(p, c)
        if q < 0.075:
            d -= 0.03 * (1 - (q / 0.075) ** 2)
    dz = 0.0
    q = dist3(p, MOUTH)
    if q < 0.13:                               # mouth pit, dished along the snout axis
        dz = -0.07 * (1 - (q / 0.13) ** 2)
    return (x + nx * d, y + ny * d, z + dz)


def body_slot(x, y, z):
    """0 flesh, 1 chitin, 2 dark cavity (eye sockets, mouth)."""
    if any(dist3((x, y, z), c) < 0.075 for c in EYES) or dist3((x, y, z), MOUTH) < 0.13:
        return 2
    ay = axis_y(z)
    r = math.hypot(x, y - ay) or 1e-6
    if -0.35 < z < 0.7 and (y - ay) / r > 0.15:
        return 1
    return 0


def build_body(mats):
    body = skin_obj("brood_body", sample(BODY_KEYS, 3), 2, mats, part=0)
    warp(body, body_warp)
    bkit.shade_smooth(body)
    for poly in body.data.polygons:
        poly.material_index = body_slot(*G(poly.center))
    return body


# ------------------------------------------------------------------ fangs and mandibles

def build_fangs(mat):
    parts = []
    for i in range(12):                        # ring of curved fangs around the mouth, lower arc
        a = math.pi + (-2.2 + 4.4 * i / 11)
        s, c = math.sin(a), math.cos(a)
        keys = [(0.20 * s, 1.36 + 0.20 * c, 1.50, 0.030, 0.030),
                (0.17 * s, 1.36 + 0.17 * c, 1.62, 0.020, 0.020),
                (0.07 * s, 1.36 + 0.07 * c, 1.78, 0.004, 0.004)]
        parts.append(skin_obj(f"fang{i}", sample(keys, 3), 0, [mat]))   # small: no subdivision, keeps the budget
    for sgn in (-1, 1):                        # split lower jaw, two hooked halves
        keys = [(sgn * 0.10, 1.22, 1.32, 0.05, 0.05),
                (sgn * 0.16, 1.02, 1.50, 0.035, 0.035),
                (sgn * 0.13, 0.95, 1.70, 0.012, 0.012)]
        parts.append(skin_obj(f"mandible{sgn}", sample(keys, 3), 1, [mat]))
    fangs = bkit.join(parts, "brood_fangs")
    tag(fangs, 1)
    return fangs


# ------------------------------------------------------------------ leg

LEG_KEYS = [(-0.22, -0.02, 0.00, 0.20, 0.20),   # starts inside the body for hip overlap
            (0.00, 0.00, 0.00, 0.17, 0.17),     # hip
            (0.50, 0.38, 0.00, 0.13, 0.12),     # knee
            (1.00, 0.12, 0.06, 0.105, 0.095),   # wrist
            (1.32, -0.75, 0.10, 0.07, 0.065),   # ankle
            (1.38, -1.18, 0.14, 0.03, 0.03)]    # foot tip
CLAW_KEYS = [(1.34, -1.10, 0.14, 0.040, 0.040), (1.40, -1.17, 0.15, 0.026, 0.026),
             (1.45, -1.20, 0.16, 0.016, 0.016), (1.44, -1.17, 0.165, 0.008, 0.008)]
JOINTS = [((0.50, 0.38, 0.00), 0.15), ((1.00, 0.12, 0.06), 0.12), ((1.32, -0.75, 0.10), 0.08)]
SPINES = [  # base, direction, radius, length
    ((0.20, 0.14, 0.00), (-0.35, 0.94, 0.0), 0.020, 0.09),
    ((0.33, 0.27, 0.00), (-0.10, 1.00, 0.0), 0.020, 0.10),
    ((0.45, 0.37, 0.00), (0.20, 0.98, 0.0), 0.022, 0.10),
    ((0.58, 0.36, 0.00), (0.40, 0.92, 0.0), 0.020, 0.09),
    ((0.75, 0.25, 0.02), (0.45, 0.90, 0.0), 0.018, 0.08),
    ((0.90, 0.07, 0.05), (0.45, -0.50, 0.0), 0.018, 0.08),
    ((1.12, -0.02, 0.07), (0.35, -0.70, 0.0), 0.016, 0.07),
    ((1.22, -0.35, 0.09), (0.45, -0.80, 0.0), 0.014, 0.06),
]


def build_leg(mat):
    parts = [skin_obj("leg_skin", sample(LEG_KEYS, 3), 2, [mat])]
    parts.append(skin_obj("claw", sample(CLAW_KEYS, 2), 1, [mat]))
    for i, (c, r) in enumerate(JOINTS):
        parts.append(new_obj(f"joint{i}", sphere_bm(c, r), [mat]))
    for i, (b, d, r, ln) in enumerate(SPINES):
        parts.append(new_obj(f"spine{i}", spine_bm(b, d, r, ln), [mat]))
    leg = bkit.join(parts, "brood_leg")
    tag(leg, 2)
    return leg


# ------------------------------------------------------------------ egg sac

def build_sac(mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    for v in bm.verts:
        ux, uy, uz = G(v.co)
        lump = 0.012 * math.sin(9 * ux + 4 * uy) * math.sin(7 * uz - 3 * ux)
        vein = abs(math.sin(14 * ux + 2 * math.sin(9 * uy)) * math.sin(12 * uz + 2 * math.sin(11 * ux)))
        ridge = 0.008 * (1 - vein) ** 8        # raised veins along the zero lines
        k = 1 + lump + ridge
        v.co = B(ux * 0.28 * k, uy * 0.24 * k, uz * 0.30 * k)
    sac = new_obj("brood_sac", bm, [mat])
    bkit.uv_unwrap(sac)
    bkit.shade_smooth(sac)
    return sac


# ------------------------------------------------------------------ build

bkit.reset_scene()
bkit.light_studio()

flesh = make_mat("brood_flesh", (0.13, 0.065, 0.07), (0.36, 0.22, 0.20), rough=0.22, bump=0.25,
                 scale=2.5, vein=((0.20, 0.02, 0.03), 5.0, 0.018))
chitin = make_mat("brood_chitin", (0.035, 0.03, 0.025), (0.16, 0.12, 0.08), rough=0.36, bump=0.8, scale=6.0)
cavity = make_mat("brood_cavity", (0.01, 0.008, 0.008), (0.05, 0.03, 0.03), rough=0.12, bump=0.0, scale=4.0)
fang_m = make_mat("brood_fang", (0.42, 0.36, 0.26), (0.66, 0.58, 0.44), rough=0.30, bump=0.3, scale=8.0)
leg_m = make_mat("brood_leg_chitin", (0.06, 0.05, 0.035), (0.22, 0.17, 0.10), rough=0.35, bump=0.9, scale=7.0)

sac_m = bpy.data.materials.new("brood_sac_mat")
sac_m.use_nodes = True
sb = next(n for n in sac_m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
sb.inputs["Base Color"].default_value = (0.46, 0.62, 0.40, 1.0)
sb.inputs["Roughness"].default_value = 0.2
sb.inputs["Transmission Weight"].default_value = 0.35
sb.inputs["Emission Color"].default_value = (0.35, 0.95, 0.45, 1.0)
sb.inputs["Emission Strength"].default_value = 0.5

body = build_body([flesh, chitin, cavity])
fangs = build_fangs(fang_m)
leg = build_leg(leg_m)
sac = build_sac(sac_m)

# one texture set for body + fangs + leg: join, bake once, split back by part tag
atlas = bkit.join([body, fangs, leg], "brood_atlas")
part_ids = [a.value for a in atlas.data.attributes["part"].data]
bkit.bake_to_textures(atlas, TEX, size=2048, samples=24)
baked = atlas.data.materials[0]


def split(src, part, name):
    bm = bmesh.new()
    bm.from_mesh(src.data)
    dead = [f for f in bm.faces if part_ids[f.index] != part]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(baked)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


body_f = split(atlas, 0, "brood_body")
fangs_f = split(atlas, 1, "brood_fangs")
leg_f = split(atlas, 2, "brood_leg")
bpy.data.objects.remove(atlas, do_unlink=True)   # join keeps the active object, which is `body`

game_parts = [body_f, fangs_f, leg_f, sac]
bkit.check(objs=game_parts, max_tris=12000)
bkit.report(objs=game_parts)

bkit.export_glb(GLB, objs=game_parts, image_format="JPEG")
print("BKIT_GLB", GLB, os.path.getsize(GLB))

# ------------------------------------------------------------------ assembled preview (game pose)

leg_f.hide_render = True
sac.hide_render = True
asm = [body_f, fangs_f]
for lx in (0.55, -0.55):
    for z in (0.55, -0.1, -0.75):
        c = leg_f.copy()
        bpy.context.collection.objects.link(c)
        c.hide_render = False
        c.location = B(lx, 1.15, z)
        if lx < 0:
            c.scale.x = -1.0
        asm.append(c)
for p in SACS:
    c = sac.copy()
    bpy.context.collection.objects.link(c)
    c.location = B(*p)
    c.hide_render = False
    asm.append(c)
sac.hide_render = True


def render(path, direction):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = 800
    scene.render.film_transparent = False
    objs = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    cam = bkit._frame_camera(objs, direction, margin=1.1)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


render(os.path.join(PREV, "brood_side.png"), (1.0, 0.0, 0.12))          # side view, from +X
render(os.path.join(PREV, "brood_front34.png"), (0.6, -1.0, 0.35))      # front 3/4 (game +Z is Blender -Y)

for o in list(bpy.context.scene.objects):          # drop the preview copies, keep the originals
    if o.name.startswith(("brood_leg.", "brood_sac.")):
        bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "brood.blend"))
print("BKIT_DONE")
