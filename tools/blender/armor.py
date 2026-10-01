# The seven body armours sold in 死城突圍's armoury, each dressed on a display mannequin.
#
#   blender -b -P tools/blender/armor.py -- assets/armor.webp
#
# Renders one sprite sheet (seven cells side by side, transparent background) that the
# shop uses as the armour pictures. Blender frame: Z up, the mannequin faces -Y.
import bpy, bmesh, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "armor.webp"
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
ORDER = ["jacket", "stab", "kevlar", "firesuit", "hazmat", "plate", "eod"]
CELL = 0.9


# ---------------------------------------------------------------- materials
def mat(name, rgb, rough=0.8, metal=0.0, bump=0.12, scale=380.0, coat=0.0, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    if bump:  # fine weave / grain so large panels don't read as plastic
        n = nt.nodes.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = scale; n.inputs["Detail"].default_value = 6
        bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = bump
        nt.links.new(n.outputs["Fac"], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


M = {
    "manq": mat("manq", (0.05, 0.052, 0.056), 0.55, bump=0),
    "leather": mat("leather", (0.075, 0.038, 0.02), 0.42, bump=0.25, scale=160, coat=0.3),
    "leather_dk": mat("leather_dk", (0.03, 0.018, 0.01), 0.5, bump=0.2, scale=160),
    "chrome": mat("chrome", (0.8, 0.8, 0.82), 0.18, 1.0, bump=0),
    "nylon_blk": mat("nylon_blk", (0.018, 0.019, 0.022), 0.85),
    "strap_gry": mat("strap_gry", (0.07, 0.072, 0.078), 0.9),
    "navy": mat("navy", (0.012, 0.02, 0.05), 0.8),
    "white": mat("white", (0.85, 0.85, 0.85), 0.6, bump=0),
    "gold": mat("gold", (0.75, 0.55, 0.18), 0.3, 1.0, bump=0),
    "tan": mat("tan", (0.32, 0.25, 0.13), 0.85, bump=0.18),
    "tan_dk": mat("tan_dk", (0.12, 0.09, 0.05), 0.85),
    "reflect": mat("reflect", (0.75, 0.76, 0.75), 0.25, 0.6, bump=0),
    "lime": mat("lime", (0.75, 0.72, 0.05), 0.55, bump=0),
    "yellow": mat("yellow", (0.72, 0.5, 0.02), 0.45, bump=0.05, coat=0.4),
    "rubber": mat("rubber", (0.015, 0.015, 0.015), 0.5, bump=0),
    "tape": mat("tape", (0.25, 0.25, 0.25), 0.6, bump=0),
    "glass": mat("glass", (0.02, 0.03, 0.035), 0.04, 0.3, bump=0, coat=1.0),
    "coyote": mat("coyote", (0.27, 0.2, 0.11), 0.88, bump=0.2),
    "coyote_dk": mat("coyote_dk", (0.17, 0.12, 0.07), 0.9),
    "velcro": mat("velcro", (0.1, 0.1, 0.08), 1.0, bump=0.4, scale=900),
    "eod": mat("eod", (0.07, 0.1, 0.055), 0.82, bump=0.15),
    "eod_dk": mat("eod_dk", (0.035, 0.048, 0.03), 0.85),
}


# ---------------------------------------------------------------- helpers
def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def apply_all(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def setmat(ob, m):
    ob.data.materials.clear(); ob.data.materials.append(M[m] if isinstance(m, str) else m)
    return ob


def smooth(ob):
    activate(ob); bpy.ops.object.shade_smooth()
    return ob


GROUP = []  # objects of the armour being built


def add(ob):
    GROUP.append(ob); return ob


def skin(nodes, edges, m, subdiv=2):
    """Body/garment from a skeleton: nodes = [(x, y, z, radius_x, radius_y)]."""
    me = bpy.data.meshes.new("s"); me.from_pydata([n[:3] for n in nodes], edges, [])
    ob = bpy.data.objects.new("s", me); scene.collection.objects.link(ob)
    sk = ob.modifiers.new("skin", "SKIN"); sk.use_smooth_shade = True
    for i, n in enumerate(nodes):
        sv = me.skin_vertices[0].data[i]; sv.radius = (n[3], n[4]); sv.use_root = i == 0
    sd = ob.modifiers.new("sub", "SUBSURF"); sd.levels = subdiv; sd.render_levels = subdiv
    apply_all(ob)
    return add(smooth(setmat(ob, m)))


def body(dr=0.0, dy=0.0, torso=None, arms=True, neck=False, hood=None, lower=0.92, m="manq", subdiv=2, arm_dr=None):
    """Mannequin skeleton, optionally inflated by dr to dress it."""
    ad = dr if arm_dr is None else arm_dr
    t = torso or [(lower, .16, .105), (1.08, .145, .095), (1.27, .17, .11), (1.4, .18, .11)]
    nodes = [(0, 0, z, rx + dr, ry + dr + dy) for z, rx, ry in t]
    top = len(nodes) - 1
    edges = [(i, i + 1) for i in range(top)]
    if neck or hood:
        nodes += [(0, 0, 1.49, .055 + dr * 0.6, .05 + dr * 0.6)]; edges.append((top, len(nodes) - 1))
        if neck:
            nodes += [(0, 0, 1.6, .05, .048)]; edges.append((len(nodes) - 2, len(nodes) - 1))
        if hood:
            for z, rx, ry in hood:
                nodes += [(0, 0, z, rx, ry)]; edges.append((len(nodes) - 2, len(nodes) - 1))
    if arms:
        for s in (-1, 1):
            k = len(nodes)
            nodes += [(s * 0.19, 0, 1.42, .055 + ad, .055 + ad), (s * 0.25, 0.01, 1.17, .042 + ad, .042 + ad), (s * 0.29, -0.02, 0.94, .033 + ad, .03 + ad)]
            edges += [(top, k), (k, k + 1), (k + 1, k + 2)]
    return skin(nodes, edges, m, subdiv)


def surf(ob, x, z, side=-1):
    """Point on the front (side -1) or back (+1) surface of ob at (x, z)."""
    hit, loc, nrm, _ = ob.ray_cast(Vector((x, side * 2, z)), Vector((0, -side, 0)))
    return loc if hit else Vector((x, side * 0.15, z))


def box(c, s, m, bev=0.25, rot=(0, 0, 0), segs=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    ob = bpy.context.object; ob.scale = s
    activate(ob); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bev:
        b = ob.modifiers.new("b", "BEVEL"); b.width = min(s) * bev; b.segments = segs; apply_all(ob)
    setmat(ob, m)
    return add(smooth(ob) if bev else ob)


def ell(c, r, m, segs=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=1, location=c)
    ob = bpy.context.object; ob.scale = r
    activate(ob); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return add(smooth(setmat(ob, m)))


def cyl(p0, p1, r, m, verts=32, r1=None):
    a, b = Vector(p0), Vector(p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    activate(ob); bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    return add(smooth(setmat(ob, m)))


def tube(pts, r, m, flat=1.0):
    cu = bpy.data.curves.new("t", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 3; cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]; bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("t", cu); scene.collection.objects.link(ob)
    activate(ob); bpy.ops.object.convert(target="MESH"); ob = bpy.context.object
    return add(smooth(setmat(ob, m)))


def on_front(ob, pts, lift=0.004):
    """Points (x, z) projected onto the front of ob, lifted off the surface."""
    out = []
    for x, z in pts:
        p = surf(ob, x, z); out.append(Vector((p.x, p.y - lift, p.z)))
    return out


def band(src, co, no, half, m, thick=0.006, keep=None):
    """A strip of src's surface between two planes, thickened outward (reflective tape, cuffs, cummerbunds)."""
    me = src.data.copy(); ob = bpy.data.objects.new("band", me); scene.collection.objects.link(ob)
    co, no = Vector(co), Vector(no).normalized()
    bm = bmesh.new(); bm.from_mesh(me)
    g = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=g, plane_co=co + no * half, plane_no=no, clear_outer=True)
    g = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=g, plane_co=co - no * half, plane_no=no, clear_inner=True)
    if keep:
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not keep(v.co)], context="VERTS")
    bm.to_mesh(me); bm.free()
    s = ob.modifiers.new("sol", "SOLIDIFY"); s.thickness = thick; s.offset = 1
    apply_all(ob)
    return add(smooth(setmat(ob, m)))


def push(ob, fn):
    """Move each vertex along its normal by fn(co) (quilting, wrinkles, padding)."""
    me = ob.data
    for v in me.vertices:
        v.co += v.normal * fn(v.co)
    me.update()


def cut(ob, cutter):
    m = ob.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = cutter; m.solver = "EXACT"
    apply_all(ob); GROUP.remove(cutter); bpy.data.objects.remove(cutter)
    return ob


def text(s, c, size, m, depth=0.002):
    bpy.ops.object.text_add(location=c, rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.object; ob.data.body = s; ob.data.size = size; ob.data.extrude = depth
    ob.data.align_x = "CENTER"; ob.data.align_y = "CENTER"
    activate(ob); bpy.ops.object.convert(target="MESH"); ob = bpy.context.object
    return add(setmat(ob, m))


def arm_point(s, t):
    """Point t of the way from elbow (0) to wrist (1), and the forearm direction."""
    e, w = Vector((s * 0.25, 0.01, 1.17)), Vector((s * 0.29, -0.02, 0.94))
    return e.lerp(w, t), (w - e).normalized()


def upper_arm(s, t):
    sh, e = Vector((s * 0.19, 0, 1.42)), Vector((s * 0.25, 0.01, 1.17))
    return sh.lerp(e, t), (e - sh).normalized()


def straps_over_shoulders(m, r=0.013, y=0.12, x=0.1):
    for s in (-1, 1):
        tube([Vector((s * x, -y, 1.36)), Vector((s * (x + 0.005), -0.075, 1.47)), Vector((s * (x + 0.008), 0, 1.5)),
              Vector((s * (x + 0.005), 0.075, 1.47)), Vector((s * x, y, 1.36))], r, m)


def mannequin(arms=True, neck=True):
    b = body(arms=arms, neck=neck)
    cyl((0, 0, 0.6), (0, 0, 0.93), 0.012, "chrome", 16)  # display stand
    return b


# ================================================================ 1. motorcycle leather jacket
def jacket():
    mannequin()
    j = body(dr=0.022, dy=0.005, torso=[(0.9, .175, .115), (1.08, .16, .105), (1.27, .185, .12), (1.4, .195, .12)], m="leather", arm_dr=0.016)
    push(j, lambda co: 0.003 * math.sin(co.z * 70 + co.x * 20) * math.sin(co.x * 30) if co.z < 1.2 else 0)  # creases
    cut(j, ell((0, -0.13, 1.47), (0.075, 0.1, 0.1), "leather"))
    tube(on_front(j, [(0.008, 1.37), (0.014, 1.28), (0.018, 1.15), (0.02, 1.0), (0.02, 0.91)], 0.003), 0.0035, "chrome")
    collar = cyl((0, 0.005, 1.45), (0, 0.012, 1.52), 0.088, "leather", 40, r1=0.094)
    activate(collar); sm = collar.modifiers.new("s", "SOLIDIFY"); sm.thickness = 0.01; apply_all(collar)
    cut(collar, ell((0, -0.12, 1.5), (0.06, 0.08, 0.1), "leather"))
    for s in (-1, 1):  # lapels folded back over the chest
        p = surf(j, s * 0.06, 1.33)
        box(Vector((s * 0.06, p.y - 0.006, 1.33)), (0.05, 0.008, 0.13), "leather", 0.3, rot=(0.1, 0, s * 0.45))
        tube(on_front(j, [(s * 0.06, 1.0), (s * 0.12, 1.11)], 0.004), 0.0025, "chrome")  # zipped pockets
        tube(on_front(j, [(s * 0.07, 1.27), (s * 0.13, 1.25)], 0.004), 0.0025, "chrome")
        p, d = arm_point(s, 0.92); band(j, p, d, 0.03, "leather_dk", 0.006, lambda c, p=p: (c - p).length < 0.09)
        box(Vector((s * 0.19, 0, 1.475)), (0.05, 0.11, 0.008), "leather_dk", 0.3, rot=(0, s * 0.35, 0))  # epaulettes
        ell(Vector((s * 0.19, -0.045, 1.478)), (0.008, 0.008, 0.005), "chrome", 12)
    band(j, (0, 0, 0.925), (0, 0, 1), 0.022, "leather_dk", 0.008, lambda c: abs(c.x) < 0.22)  # belt
    b = surf(j, 0, 0.925); box(Vector((0, b.y - 0.01, 0.925)), (0.05, 0.008, 0.04), "chrome", 0.3)


# ================================================================ 2. quilted stab vest
def stab():
    mannequin()
    v = body(dr=0.03, dy=0.012, torso=[(0.93, .16, .105), (1.08, .145, .095), (1.27, .17, .11), (1.42, .17, .1)], arms=False, m="nylon_blk", subdiv=3)
    cut(v, ell((0, -0.13, 1.46), (0.085, 0.09, 0.12), "nylon_blk"))

    def quilt(co):
        u = math.atan2(co.x, -co.y) * 0.17; w = co.z
        d = min(abs(((u + w) / 0.06) % 1 - 0.5), abs(((u - w) / 0.06) % 1 - 0.5))
        return -0.006 * max(0, 1 - d / 0.12)
    push(v, quilt)
    straps_over_shoulders("nylon_blk", 0.016, 0.11, 0.1)
    for z in (1.02, 1.2):  # side velcro straps
        band(v, (0, 0, z), (0, 0, 1), 0.022, "strap_gry", 0.006, lambda c: abs(c.x) > 0.13 and c.y > -0.08)
    p = surf(v, 0.07, 1.3); box(Vector((0.07, p.y - 0.004, 1.3)), (0.075, 0.006, 0.035), "velcro", 0.2)


# ================================================================ 3. police ballistic vest
def kevlar():
    mannequin()
    v = body(dr=0.034, dy=0.014, torso=[(0.93, .16, .105), (1.08, .15, .1), (1.27, .17, .11), (1.42, .165, .1)], arms=False, m="navy")
    cut(v, ell((0, -0.13, 1.47), (0.09, 0.09, 0.11), "navy"))
    straps_over_shoulders("navy", 0.018, 0.11, 0.098)
    band(v, (0, 0, 1.06), (0, 0, 1), 0.04, "navy", 0.012, lambda c: abs(c.x) > 0.1)  # side wraps
    for s in (-1, 1):
        p = surf(v, s * 0.13, 1.06); box(Vector((s * 0.13, p.y - 0.01, 1.06)), (0.06, 0.012, 0.075), "strap_gry", 0.2)
    p = surf(v, 0, 1.2)
    box(Vector((0, p.y - 0.006, 1.2)), (0.2, 0.01, 0.07), "navy", 0.2)
    text("POLICE", Vector((0, p.y - 0.013, 1.2)), 0.05, "white")
    p = surf(v, 0.075, 1.33); ell(Vector((0.075, p.y - 0.004, 1.33)), (0.022, 0.006, 0.026), "gold", 16)  # badge
    p = surf(v, -0.08, 1.31); box(Vector((-0.08, p.y - 0.012, 1.31)), (0.035, 0.022, 0.07), "nylon_blk", 0.25)  # radio pouch
    cyl((-0.08, p.y - 0.012, 1.345), (-0.08, p.y - 0.012, 1.4), 0.005, "rubber", 10)


# ================================================================ 4. firefighter turnout coat
def firesuit():
    mannequin()
    c = body(dr=0.03, dy=0.008, torso=[(0.8, .19, .13), (0.95, .18, .12), (1.1, .165, .11), (1.28, .19, .125), (1.41, .195, .12)], m="tan", arm_dr=0.024)
    push(c, lambda co: 0.004 * math.sin(co.z * 45 + math.sin(co.x * 25)) if co.z < 1.1 else 0)
    cut(c, ell((0, -0.13, 1.47), (0.07, 0.09, 0.09), "tan"))
    collar = cyl((0, 0, 1.43), (0, 0, 1.56), 0.085, "tan", 40, r1=0.078)
    activate(collar); s = collar.modifiers.new("s", "SOLIDIFY"); s.thickness = 0.012; apply_all(collar)
    cut(collar, box((0, -0.1, 1.5), (0.05, 0.08, 0.2), "tan", 0))
    for z in (0.86, 1.2):  # lime / silver / lime reflective trim
        k = lambda co: abs(co.x) < 0.235
        band(c, (0, 0, z), (0, 0, 1), 0.026, "lime", 0.005, k)
        band(c, (0, 0, z), (0, 0, 1), 0.009, "reflect", 0.008, k)
    for s in (-1, 1):
        for t in (0.75,):
            p, d = arm_point(s, t)
            band(c, p, d, 0.026, "lime", 0.005, lambda co, p=p: (co - p).length < 0.1)
            band(c, p, d, 0.009, "reflect", 0.008, lambda co, p=p: (co - p).length < 0.1)
        p, d = upper_arm(s, 0.7)
        band(c, p, d, 0.024, "lime", 0.005, lambda co, p=p: (co - p).length < 0.1)
        band(c, p, d, 0.008, "reflect", 0.008, lambda co, p=p: (co - p).length < 0.1)
    front = on_front(c, [(0.0, z / 100) for z in range(80, 142, 4)], 0.003)
    tube(front, 0.009, "tan_dk")
    for z in (0.9, 1.05, 1.17, 1.32):  # clasps
        p = surf(c, 0.0, z); box(Vector((0.012, p.y - 0.012, z)), (0.034, 0.008, 0.014), "chrome", 0.3)
    p = surf(c, -0.1, 1.33); box(Vector((-0.1, p.y - 0.01, 1.33)), (0.05, 0.016, 0.06), "tan_dk", 0.25)  # radio pocket
    for s in (-1, 1):
        p = surf(c, s * 0.12, 0.98); box(Vector((s * 0.12, p.y - 0.012, 0.98)), (0.1, 0.02, 0.11), "tan", 0.2)


# ================================================================ 5. hazmat suit
def hazmat():
    mannequin()
    h = body(dr=0.04, dy=0.012, torso=[(0.88, .18, .12), (1.06, .17, .115), (1.27, .19, .125), (1.41, .19, .12)], m="yellow", arm_dr=0.03,
             hood=[(1.63, .125, .13), (1.75, .11, .115)])
    tex = bpy.data.textures.new("wr", "CLOUDS"); tex.noise_scale = 0.06
    d = h.modifiers.new("wr", "DISPLACE"); d.texture = tex; d.strength = 0.018; d.texture_coords = "LOCAL"; apply_all(h)
    push(h, lambda co: -0.006 * max(0, math.sin(co.z * 60)) if co.z < 1.15 else 0)  # sagging folds
    visor = ell((0, -0.095, 1.655), (0.098, 0.05, 0.075), "glass", 32)
    cut(h, ell((0, -0.115, 1.655), (0.09, 0.05, 0.068), "yellow"))
    tube([Vector((0.093 * math.cos(a), -0.118, 1.655 + 0.07 * math.sin(a))) for a in [k / 24 * math.tau for k in range(25)]], 0.007, "rubber")  # visor seal
    for s in (-1, 1):
        p, dd = arm_point(s, 1.0)
        band(h, *arm_point(s, 0.9), 0.022, "tape", 0.006, lambda co, p=p: (co - p).length < 0.12)
        cyl(p - dd * 0.03, p + dd * 0.07, 0.042, "rubber", 24, r1=0.036)
        ell(p + dd * 0.11, (0.04, 0.034, 0.05), "rubber", 20)
    tube(on_front(h, [(0.0, z / 100) for z in range(88, 150, 4)], 0.004), 0.012, "yellow")  # zip storm flap
    p = surf(h, 0.0, 1.38); ell(Vector((0.0, p.y - 0.02, 1.36)), (0.05, 0.025, 0.035), "rubber", 20)  # air inlet valve
    cyl((0, p.y - 0.035, 1.36), (0, p.y - 0.05, 1.36), 0.022, "tape", 24)


# ================================================================ 6. plate carrier
def plate():
    mannequin()
    m = GROUP[0]
    for side, sy in ((-1, -1), (1, 1)):
        p = surf(m, 0, 1.25, side)
        box(Vector((0, p.y + sy * 0.035, 1.24)), (0.29, 0.055, 0.33), "coyote", 0.3, rot=(side * -0.08, 0, 0))
    straps_over_shoulders("coyote", 0.02, 0.1, 0.095)
    band(m, (0, 0, 1.08), (0, 0, 1), 0.055, "coyote", 0.022, lambda c: abs(c.x) > 0.06)  # cummerbund
    p = surf(m, 0, 1.25)
    y0 = p.y - 0.064
    for k in range(4):  # MOLLE webbing
        z = 1.33 - k * 0.04
        box(Vector((0, y0 - 0.003, z)), (0.27, 0.004, 0.014), "coyote_dk", 0.2)
    box(Vector((0, y0 - 0.006, 1.37)), (0.12, 0.004, 0.05), "velcro", 0.1)
    for k, x in enumerate((-0.085, 0, 0.085)):  # magazine pouches with flaps
        pc = Vector((x, y0 - 0.025, 1.13))
        box(pc, (0.072, 0.045, 0.12), "coyote", 0.2)
        box(pc + Vector((0, -0.004, 0.05)), (0.076, 0.05, 0.03), "coyote_dk", 0.3)
        box(pc + Vector((0, -0.025, 0.03)), (0.02, 0.004, 0.03), "velcro", 0.1)
    for s in (-1, 1):  # side radio / IFAK pouch
        box(Vector((s * 0.2, -0.02, 1.08)), (0.045, 0.07, 0.1), "coyote_dk", 0.25)
        box(Vector((s * 0.14, y0 + 0.02, 1.4)), (0.04, 0.05, 0.02), "chrome", 0.3)  # strap buckles


# ================================================================ 7. EOD bomb suit
def eod():
    mannequin()
    e = body(dr=0.065, dy=0.025, torso=[(0.82, .17, .11), (1.0, .16, .105), (1.25, .18, .115), (1.4, .19, .11)], m="eod", arm_dr=0.045)
    for s in (-1, 1):  # padded arm segments
        for t in (0.25, 0.6):
            p, d = arm_point(s, t); band(e, p, d, 0.035, "eod_dk", 0.014, lambda c, p=p: (c - p).length < 0.13)
        p, d = upper_arm(s, 0.45); band(e, p, d, 0.04, "eod_dk", 0.014, lambda c, p=p: (c - p).length < 0.14)
        p, d = arm_point(s, 1.0); cyl(p - d * 0.02, p + d * 0.05, 0.06, "rubber", 24, r1=0.05); ell(p + d * 0.09, (0.045, 0.04, 0.055), "rubber", 20)
    p = surf(e, 0, 1.2)
    chest = box(Vector((0, p.y - 0.035, 1.2)), (0.36, 0.07, 0.4), "eod_dk", 0.35, rot=(-0.06, 0, 0))
    box(Vector((0, p.y - 0.06, 1.2)), (0.3, 0.02, 0.33), "eod", 0.4, rot=(-0.06, 0, 0))
    p = surf(e, 0, 0.88); box(Vector((0, p.y - 0.03, 0.82)), (0.28, 0.05, 0.22), "eod_dk", 0.35)  # groin flap
    collar = cyl((0, 0, 1.42), (0, 0, 1.6), 0.165, "eod", 48, r1=0.14)
    activate(collar); s = collar.modifiers.new("s", "SOLIDIFY"); s.thickness = 0.03; apply_all(collar)
    band(collar, (0, 0, 1.59), (0, 0, 1), 0.012, "eod_dk", 0.008)
    helm = ell((0, 0.01, 1.74), (0.15, 0.165, 0.15), "eod_dk", 32)
    cut(helm, ell((0, -0.13, 1.71), (0.11, 0.08, 0.09), "eod_dk"))
    ell((0, -0.1, 1.71), (0.118, 0.06, 0.095), "glass", 32)
    tube([Vector((0.118 * math.cos(a), -0.105, 1.71 + 0.095 * math.sin(a))) for a in [k / 24 * math.tau for k in range(25)]], 0.008, "rubber")
    for s in (-1, 1):  # buckles and straps across the chest
        tube([Vector((s * 0.2, -0.17, 1.05)), Vector((s * 0.1, -0.2, 1.05)), Vector((s * 0.0, -0.205, 1.05))], 0.008, "rubber")
        box(Vector((s * 0.15, -0.21, 1.05)), (0.03, 0.01, 0.025), "chrome", 0.3)


# ---------------------------------------------------------------- lay the seven out in a row and render
BUILD = {"jacket": jacket, "stab": stab, "kevlar": kevlar, "firesuit": firesuit, "hazmat": hazmat, "plate": plate, "eod": eod}
for i, name in enumerate(ORDER):
    GROUP.clear()
    BUILD[name]()
    root = bpy.data.objects.new(name, None); scene.collection.objects.link(root)
    for o in GROUP:
        o.parent = root
    root.rotation_euler = (0, 0, -0.42)
    root.location = ((i - (len(ORDER) - 1) / 2) * CELL, 0, 0)
    print("built", name, sum(len(o.data.polygons) for o in GROUP))

W, H = 7 * 280, 360
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
cam.data.type = "ORTHO"; cam.data.ortho_scale = 7 * CELL
cam.location = (0, -8, 1.37 + 8 * math.tan(0.1)); cam.rotation_euler = (math.pi / 2 - 0.1, 0, 0)
cam.data.shift_y = 0.0
scene.camera = cam
world = bpy.data.worlds.new("w"); scene.world = world
world.color = (0.05, 0.05, 0.055)
for loc, e, size in (((-3, -5, 4), 650, 6), ((5, -3, 2), 330, 5), ((0, 4, 3), 600, 6), ((0, -4, -1), 80, 8)):
    l = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA")); scene.collection.objects.link(l)
    l.data.energy = e; l.data.size = size; l.location = loc
    l.rotation_euler = (Vector((0, 0, 1.25)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
scene.render.engine = "CYCLES"; scene.cycles.samples = 64; scene.cycles.device = "CPU"
scene.render.film_transparent = True
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.image_settings.file_format = "WEBP"; scene.render.image_settings.color_mode = "RGBA"; scene.render.image_settings.quality = 88
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("rendered", OUT)
