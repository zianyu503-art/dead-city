# The player's own zombie (Zombie_Preview_v38.blend, made by the user in Blender) turned into the
# game's skinned zombie body.
#
#   blender -b --disable-autoexec <Zombie_Preview_v38.blend> -P tools/blender/zombie_body.py -- assets/models/zombiebody.glb [preview.png]
#
# The source is a 1.7M-triangle studio model with no rig. This script:
#   1. builds low-poly layers (skin with eyes and teeth, shirt with the gauze, jacket, tie, trousers,
#      boots, a hair shell) and bakes each one's colour (with ambient occlusion) from the original;
#   2. weights the body to the game's joints with bone heat, then gives every layer the weights of
#      the nearest body surface (shirt and jacket only follow the torso and upper arms, trousers the
#      legs, the hair the head...);
#   3. moves everything from the model's own pose into the game's rest pose (arms and legs straight
#      down, legs a little apart) and scales it to the game's size;
#   4. exports the layers as skinned meshes, plus an invisible hit shape per joint and the joint
#      layout (empty "zb_layout", custom property "layout"), which the game reads.
#
# The game builds its zombies from joint groups (torso, head pivot, jaw, shoulders, elbows, hands,
# hips, knees) and animates them by rotating those groups, so the exported bones carry those names
# and the game binds the meshes to its own groups.
#
# Coordinates: the source faces -Y with Z up (Blender's front view). The game frame is +Y up and
# +Z forward; B() converts a game point to Blender axes and the glTF exporter converts back.
#
# Set ZB_WORK=<file.blend> to save the baked stage there; running the script on that file skips
# the slow part.
import bpy, bmesh, math, sys, os, time, json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "zombiebody.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
WORK = os.environ.get("ZB_WORK")
scene = bpy.context.scene
T0 = time.time()


def log(*a):
    print(f"[zb {time.time() - T0:6.1f}s]", *a, flush=True)


S, ZOFF, SPLAY = 1.07, -0.032, 0.11  # scale to game size, forward shift, how far the legs stand apart (rad)
BONES = ["torso", "head", "jaw", "arm0", "elbow0", "hand0", "arm1", "elbow1", "hand1", "leg0", "knee0", "leg1", "knee1"]
BI = {b: i for i, b in enumerate(BONES)}
NB = len(BONES)
HP = (0.0, 1.72, 0.03)  # the game's head pivot (body frame)
TARGET = dict(skin=3300, eyes=60, teeth=220, shirt=1000, gauze=160, jacket=1400, tie=150, trousers=1000, boot=260, hair=800)
TEX = dict(skin=2048, shirt=1024, jacket=1024, tie=256, trousers=1024, boots=512)


def V(*a):
    return Vector(a)


def B(x, y, z):
    return Vector((x, -z, y))


def to_game(v):
    return [round(v.x, 5), round(v.z, 5), round(-v.y, 5)]


# the model's joints, read off front and side renders (source frame); x is for the +X (its left) side
J = dict(shoulder=V(0.175, -0.03, 1.46), elbow=V(0.178, -0.045, 1.21), wrist=V(0.108, -0.225, 1.035), tip=V(0.092, -0.34, 0.935),
         hip=V(0.085, -0.03, 0.95), knee=V(0.165, -0.035, 0.56), ankle=V(0.19, 0.0, 0.08))
TMJ = V(0, -0.075, 1.645)  # jaw hinge


def side_of(i):
    return -1 if i == 0 else 1  # the game's index 0 hangs at -x


def mj(name, s):
    v = J[name].copy(); v.x *= s
    return v


def G(p):  # source → game rest, Blender axes
    return Vector((S * p.x, S * p.y - ZOFF, S * p.z))


def Ginv(q):
    return Vector((q.x / S, (q.y + ZOFF) / S, q.z / S))


O_HEAD = Ginv(B(*HP))
DOWN = V(0, 0, -1)


def rot_between(a, b):
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


def rest_frames(k_shin=None):
    """Per bone: O (its joint in the source), P (the joint in the game's rest pose), R (turns the source limb
    to its rest direction), Rf (the rest frame's rotation) and an optional stretch K along the limb."""
    I3 = Matrix.Identity(3)
    F = {"torso": dict(O=Ginv(B(0, 1.2, 0)), P=B(0, 1.2, 0), R=I3, Rf=I3),
         "head": dict(O=O_HEAD, P=B(*HP), R=I3, Rf=I3),
         "jaw": dict(O=TMJ, P=G(TMJ), R=I3, Rf=I3)}
    for i in (0, 1):
        s = side_of(i)
        sh, el, wr, tp = (mj(n, s) for n in ("shoulder", "elbow", "wrist", "tip"))
        P = G(sh); F[f"arm{i}"] = dict(O=sh, P=P, R=rot_between(el - sh, DOWN), Rf=I3)
        P2 = P + DOWN * S * (el - sh).length; F[f"elbow{i}"] = dict(O=el, P=P2, R=rot_between(wr - el, DOWN), Rf=I3)
        P3 = P2 + DOWN * S * (wr - el).length; F[f"hand{i}"] = dict(O=wr, P=P3, R=rot_between(tp - wr, DOWN), Rf=I3)
        th = SPLAY * s; e = Vector((math.sin(th), 0, -math.cos(th))); Rf = Matrix.Rotation(-th, 3, "Y")
        hi, kn, an = (mj(n, s) for n in ("hip", "knee", "ankle"))
        P = G(hi); F[f"leg{i}"] = dict(O=hi, P=P, R=rot_between(kn - hi, e), Rf=Rf)
        P2 = P + e * S * (kn - hi).length
        k = k_shin if k_shin else (P2.z - S * an.z) / (S * (an - kn).length * math.cos(th))  # soles on the ground
        F[f"knee{i}"] = dict(O=kn, P=P2, R=rot_between(an - kn, e), Rf=Rf, K=(k, e))
    return F


def T(f, p):
    q = S * (f["R"] @ (p - f["O"]))
    if "K" in f:
        k, e = f["K"]; q = q + e * ((k - 1) * q.dot(e))
    return f["P"] + q


def heat_segments():
    seg = {"torso": (V(0, -0.03, 0.90), V(0, -0.02, 1.50)), "head": (O_HEAD, V(0, -0.09, 1.80))}
    for i in (0, 1):
        s = side_of(i)
        seg[f"arm{i}"] = (mj("shoulder", s), mj("elbow", s)); seg[f"elbow{i}"] = (mj("elbow", s), mj("wrist", s))
        seg[f"hand{i}"] = (mj("wrist", s), mj("tip", s))
        seg[f"leg{i}"] = (mj("hip", s), mj("knee", s)); seg[f"knee{i}"] = (mj("knee", s), mj("ankle", s))
    return seg


# ---------------------------------------------------------------- helpers
def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def apply_mods(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def src(*keys, exclude=()):
    return [o for o in bpy.data.objects if o.type in ("MESH", "CURVE") and any(k in o.name for k in keys)
            and not any(x in o.name for x in exclude) and not o.name.startswith("zb_")]


def mesh_copy(o, name, keep=("SUBSURF", "BEVEL", "SOLIDIFY"), sub_max=None):
    """A world-space mesh of o with only the `keep` modifiers applied."""
    c = o.copy(); c.data = o.data.copy(); scene.collection.objects.link(c)
    for m in list(c.modifiers):
        if m.type not in keep:
            c.modifiers.remove(m)
        elif m.type == "SUBSURF" and sub_max is not None:
            m.levels = m.render_levels = min(m.levels, sub_max)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(c.evaluated_get(dg)); me.transform(o.matrix_world)
    data = c.data; bpy.data.objects.remove(c)
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    return ob


def join(objs, name):
    bm = bmesh.new()
    for o in objs:
        bm.from_mesh(o.data)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    groups = [g.name for g in objs[0].vertex_groups] if objs and objs[0].vertex_groups else []
    for o in objs:
        bpy.data.objects.remove(o)
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    for g in groups:
        ob.vertex_groups.new(name=g)
    return ob


def merge(ob, dist=0.0004):
    """Weld, then cut the cloth open where more than two faces share an edge: collapsing stalls on those."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0002)
    bmesh.ops.split_edges(bm, edges=[e for e in bm.edges if not e.is_manifold and not e.is_boundary])
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data); bm.free()


def decimate(ob, n):
    t0 = t = tris(ob)
    for _ in range(5):  # one collapse pass can stop short on torn cloth and remeshed shells
        if t <= n * 1.1:
            break
        m = ob.modifiers.new("dec", "DECIMATE"); m.decimate_type = "COLLAPSE"; m.ratio = n / t; m.use_collapse_triangulate = True
        apply_mods(ob); t = tris(ob)
    log(f"  {ob.name}: {t0} -> {t} tris")


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- weights
def heat_weights(body):
    """Bone-heat weights on the base body mesh (source frame), as an (n, NB) array."""
    arm = bpy.data.armatures.new("zb_heat"); ao = bpy.data.objects.new("zb_heat", arm); scene.collection.objects.link(ao)
    activate(ao); bpy.ops.object.mode_set(mode="EDIT")
    for name, (h, t) in heat_segments().items():
        eb = arm.edit_bones.new(name); eb.head = h; eb.tail = t
    bpy.ops.object.mode_set(mode="OBJECT")
    activate(body); ao.select_set(True); bpy.context.view_layer.objects.active = ao
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    me = body.data; n = len(me.vertices)
    W = np.zeros((n, NB)); names = {g.index: g.name for g in body.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            nm = names[g.group]
            if nm in BI:
                W[v.index, BI[nm]] = g.weight
    co = np.array([v.co[:] for v in me.vertices])
    lost = W.sum(1) < 1e-4
    if lost.any():  # heat found no solution here: nearest bone segment
        log(f"  heat left {lost.sum()} vertices unweighted; using the nearest bone")
        segs = heat_segments()
        for vi in np.nonzero(lost)[0]:
            p = Vector(co[vi]); best = min(segs, key=lambda b: dist_seg(p, *segs[b])); W[vi, BI[best]] = 1
    # the jaw: the chin and lower lip, from the source's geometry
    h = W[:, BI["head"]]
    f = smoothstep(1.607, 1.595, co[:, 2]) * smoothstep(-0.065, -0.095, co[:, 1]) * smoothstep(1.535, 1.565, co[:, 2])
    W[:, BI["jaw"]] = h * f; W[:, BI["head"]] = h * (1 - f)
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    body.parent = None; body.modifiers.clear(); body.vertex_groups.clear()
    bpy.data.objects.remove(ao)
    return W


def dist_seg(p, a, b):
    ab = b - a; t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


class WeightSource:
    """Hands out the body's weights at any point, through the nearest body surface whose main bone is allowed."""
    def __init__(self, body, W):
        me = body.data
        self.verts = [v.co.copy() for v in me.vertices]; self.polys = [tuple(p.vertices) for p in me.polygons]; self.W = W
        self.dom = [int(np.argmax(W[list(p)].mean(0))) for p in self.polys]
        self.trees = {}

    def tree(self, mask):
        key = tuple(sorted(mask))
        if key not in self.trees:
            idx = [i for i, d in enumerate(self.dom) if d in mask]
            self.trees[key] = (BVHTree.FromPolygons(self.verts, [self.polys[i] for i in idx]), idx)
        return self.trees[key]

    def sample(self, pts, mask=None):
        mask = set(range(NB)) if mask is None else {BI[b] if isinstance(b, str) else b for b in mask}
        t, idx = self.tree(mask); keep = np.zeros(NB); keep[list(mask)] = 1
        out = np.zeros((len(pts), NB))
        for k, p in enumerate(pts):
            loc, _, fi, _ = t.find_nearest(p)
            poly = self.polys[idx[fi]]
            bw = poly_3d_calc([self.verts[i] for i in poly], loc)
            w = sum(b * self.W[i] for b, i in zip(bw, poly)) * keep
            s = w.sum()
            if s > 1e-6:
                out[k] = w / s
            else:
                out[k, self.dom[idx[fi]]] = 1
        return out


def set_weights(ob, W):
    """Keep each vertex's 4 strongest bones and store them as vertex groups."""
    ob.vertex_groups.clear()
    vgs = [ob.vertex_groups.new(name=b) for b in BONES]
    W = W.copy()
    if NB > 4:
        cut = np.argsort(W, 1)[:, :-4]
        np.put_along_axis(W, cut, 0, 1)
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    for vi, row in enumerate(W):
        for bi in np.nonzero(row > 1e-4)[0]:
            vgs[bi].add([vi], float(row[bi]), "REPLACE")


def get_weights(ob):
    W = np.zeros((len(ob.data.vertices), NB)); names = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        for g in v.groups:
            if names[g.group] in BI:
                W[v.index, BI[names[g.group]]] = g.weight
    return W / np.maximum(W.sum(1, keepdims=True), 1e-9)


# ---------------------------------------------------------------- low-poly layers
def garment_bvh(objs):
    bm = bmesh.new()
    for o in objs:
        c = mesh_copy(o, "zb_tmp"); bm.from_mesh(c.data); me = c.data; bpy.data.objects.remove(c); bpy.data.meshes.remove(me)
    t = BVHTree.FromBMesh(bm); bm.free()
    return t


def strip_covered(ob, ws, garments):
    """Delete the skin hidden under the clothes (rays from it all hit cloth within 5 cm); hands and head are kept."""
    tree = garment_bvh(garments)
    me = ob.data
    centers = [p.center.copy() for p in me.polygons]
    dom = np.argmax(ws.sample(centers), 1)
    keep_b = {BI[b] for b in ("hand0", "hand1", "head", "jaw")}
    gone = []
    for p, d in zip(me.polygons, dom):
        if d in keep_b:
            continue
        n = p.normal; t1 = n.orthogonal().normalized(); t2 = n.cross(t1)
        c = p.center + n * 0.0005
        if all(tree.ray_cast(c, r.normalized(), 0.05)[0] is not None
               for r in (n, n + 0.7 * t1, n - 0.7 * t1, n + 0.7 * t2, n - 0.7 * t2)):
            gone.append(p.index)
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in gone], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me); bm.free()
    log(f"  skin under clothes removed: {len(gone)} of {len(centers)} faces")


def boot_low(side, name):
    parts = [o for o in src(f"Boot {side}") if o.type == "MESH"]
    objs = [mesh_copy(o, "zb_tmp") for o in parts]
    ob = join(objs, name)
    m = ob.modifiers.new("vox", "REMESH"); m.mode = "VOXEL"; m.voxel_size = 0.006; apply_mods(ob)
    decimate(ob, TARGET["boot"])
    return ob


def set_menu(node, sock, *options):
    for o in options:
        try:
            node.inputs[sock].default_value = o
            return
        except Exception:
            pass


def hair_low():
    pts = []
    for o in bpy.data.objects:
        if o.type == "CURVES" and "HAIR" in o.name and "eyebrow" not in o.name:
            a = np.empty(len(o.data.points) * 3, np.float32); o.data.attributes["position"].data.foreach_get("vector", a)
            a = a.reshape(-1, 3)[::3]
            M = np.array(o.matrix_world); a = a @ M[:3, :3].T + M[:3, 3]
            pts.append(a)
    pts = np.concatenate(pts)
    me = bpy.data.meshes.new("zb_hair"); me.from_pydata([tuple(p) for p in pts], [], [])
    ob = bpy.data.objects.new("zb_hair", me); scene.collection.objects.link(ob)
    ng = bpy.data.node_groups.new("zb_hairvol", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    m2p = ng.nodes.new("GeometryNodeMeshToPoints"); m2p.inputs["Radius"].default_value = 0.0055
    p2v = ng.nodes.new("GeometryNodePointsToVolume"); set_menu(p2v, "Resolution Mode", "Size", "Voxel Size", "VOXEL_SIZE")
    p2v.inputs["Voxel Size"].default_value = 0.004; p2v.inputs["Radius"].default_value = 0.0055; p2v.inputs["Density"].default_value = 1
    v2m = ng.nodes.new("GeometryNodeVolumeToMesh"); v2m.inputs["Threshold"].default_value = 0.3
    ng.links.new(gi.outputs[0], m2p.inputs["Mesh"]); ng.links.new(m2p.outputs[0], p2v.inputs["Points"])
    ng.links.new(p2v.outputs[0], v2m.inputs["Volume"]); ng.links.new(v2m.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("vol", "NODES"); mod.node_group = ng
    apply_mods(ob)
    sm = ob.modifiers.new("sm", "SMOOTH"); sm.factor = 0.6; sm.iterations = 4; apply_mods(ob)
    log(f"  hair shell from {len(pts)} strand points: {tris(ob)} tris")
    decimate(ob, TARGET["hair"])
    return ob


def build_layers():
    log("building low-poly layers")
    body_src = src("BODY ·")[0]
    base = mesh_copy(body_src, "zb_base", keep=())   # level 0: what the weights are worked out on
    W0 = heat_weights(base)
    ws = WeightSource(base, W0)
    log(f"  bone heat on {len(base.data.vertices)} vertices")

    shirt_src = src("BoneShirt", "NativeOpenBoneShirtCollar")
    gauze_src = src("left forearm continuous")
    jacket_src = src("WorkJacket", "AttachedShortWorkCollar")
    tie_src = src("LooseTie", "TuckedFlatTieBand")
    trousers_src = src("KhakiTrousers")
    boots_mesh = [o for o in src("Boot ") if o.type == "MESH"]

    skin = mesh_copy(body_src, "zb_skin", keep=("SUBSURF",), sub_max=1)
    strip_covered(skin, ws, shirt_src + gauze_src + trousers_src + boots_mesh)
    merge(skin); decimate(skin, TARGET["skin"])
    eyes = mesh_copy(src("EYES ·")[0], "zb_eyes", keep=("SUBSURF",), sub_max=1); decimate(eyes, TARGET["eyes"])
    teeth = mesh_copy(src("Real fitted upper and lower teeth")[0], "zb_teeth", keep=("SUBSURF",), sub_max=1); decimate(teeth, TARGET["teeth"])

    def cloth(objs, name, n):
        ob = join([mesh_copy(o, "zb_tmp", keep=("SUBSURF", "BEVEL"), sub_max=1) for o in objs], name)
        merge(ob); decimate(ob, n)
        return ob

    shirt = cloth(shirt_src, "zb_shirt", TARGET["shirt"]); gauze = cloth(gauze_src, "zb_gauze", TARGET["gauze"])
    jacket = cloth(jacket_src, "zb_jacket", TARGET["jacket"]); tie = cloth(tie_src, "zb_tie", TARGET["tie"])
    trousers = cloth(trousers_src, "zb_trousers", TARGET["trousers"])
    boots = join([boot_low("L", "zb_bootL"), boot_low("R", "zb_bootR")], "zb_boots")
    hair = hair_low()

    log("weights")
    arms_up = ("torso", "arm0", "arm1")
    masks = {skin: None, eyes: ("head",), teeth: ("head", "jaw"), shirt: arms_up, jacket: arms_up, tie: ("torso",),
             gauze: ("arm0", "arm1", "elbow0", "elbow1", "hand0", "hand1"), trousers: ("torso", "leg0", "leg1", "knee0", "knee1"),
             boots: ("knee0", "knee1"), hair: ("head",)}
    for ob, mask in masks.items():
        set_weights(ob, ws.sample([v.co for v in ob.data.vertices], mask))
    skin = join([skin, eyes, teeth], "zb_skin"); shirt = join([shirt, gauze], "zb_shirt")  # the weights come along
    bpy.data.objects.remove(base)
    return dict(skin=skin, shirt=shirt, jacket=jacket, tie=tie, trousers=trousers, boots=boots, hair=hair), ws


# ---------------------------------------------------------------- baking
def setup_cycles():
    scene.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"; prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception as e:
        log("  GPU unavailable, baking on the CPU:", e)
    scene.cycles.samples = 1
    if scene.world is None:
        scene.world = bpy.data.worlds.new("w")
    scene.world.light_settings.distance = 0.12


def one_source(objs, name):
    """The objects baked into one mesh (materials kept): baking from hundreds of objects crawls."""
    cs = [mesh_copy(o, name) for o in objs]
    for c, o in zip(cs, objs):
        for m in o.data.materials if o.type in ("MESH", "CURVE") else []:
            if m and m.name not in c.data.materials:
                c.data.materials.append(m)
    activate(cs[0])
    for c in cs[1:]:
        c.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = name
    return ob


def bake_layer(low, sources, size, cage=0.03, ao=0.55):
    img = bpy.data.images.new(low.name + "_col", size, size); img.colorspace_settings.name = "sRGB"
    mat = bpy.data.materials.new(low.name); mat.use_nodes = True; nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; nt.nodes.active = tex
    bsdf = nt.nodes.get("Principled BSDF"); nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    low.data.materials.clear(); low.data.materials.append(mat)
    activate(low)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    # only this layer's sources and the big occluders render: hundreds of boot details and 64k hair strands
    # in every bake make it crawl
    occluders = src("BODY ·", "BoneShirt", "WorkJacket", "KhakiTrousers")
    for o in bpy.data.objects:
        if not o.name.startswith("zb_"):
            o.hide_render = o not in sources and o not in occluders
    for o in sources:
        o.hide_render = False; o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = low; low.select_set(True)
    scene.cycles.samples = 1
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=True, cage_extrusion=cage,
                        max_ray_distance=cage * 2.7, margin=6, target="IMAGE_TEXTURES")
    if ao:
        aoimg = bpy.data.images.new(low.name + "_ao", size, size); aoimg.colorspace_settings.name = "Non-Color"
        tex.image = aoimg; scene.cycles.samples = 24
        bpy.ops.object.bake(type="AO", use_selected_to_active=True, cage_extrusion=cage, max_ray_distance=cage * 2.7, margin=6, target="IMAGE_TEXTURES")
        a = np.empty(size * size * 4, np.float32); img.pixels.foreach_get(a)
        o = np.empty(size * size * 4, np.float32); aoimg.pixels.foreach_get(o)
        f = 1 - ao * (1 - o[0::4])
        for c in range(3):
            a[c::4] *= f
        img.pixels.foreach_set(a); img.update(); tex.image = img; bpy.data.images.remove(aoimg)
    img.pack()
    log(f"  baked {low.name} ({size}px)")


def bake_all(L):
    log("baking")
    setup_cycles()
    for o in bpy.data.objects:
        if o.name.startswith("STUDIO"):
            o.hide_render = True
    jacket_bits = src("WorkJacket", "AttachedShortWorkCollar", "ChestPocket", "PocketFlap", "ChestSnap", "FadedWorkLabel",
                      "TornThinTwillTongues", "RestrainedWornTopstitches")
    bake_layer(L["skin"], src("BODY ·", "EYES ·", "Real fitted upper and lower teeth"), TEX["skin"], cage=0.008, ao=0.5)
    bake_layer(L["shirt"], src("BoneShirt", "NativeOpenBoneShirtCollar", "left forearm continuous"), TEX["shirt"])
    bake_layer(L["jacket"], jacket_bits, TEX["jacket"])
    bake_layer(L["tie"], src("LooseTie", "TuckedFlatTieBand"), TEX["tie"])
    bake_layer(L["trousers"], src("KhakiTrousers"), TEX["trousers"])
    boots = one_source(src("Boot "), "zb_tmp_boots")
    bake_layer(L["boots"], [boots], TEX["boots"], cage=0.02)
    bpy.data.objects.remove(boots)
    hm = bpy.data.materials.new("zb_hair"); hm.use_nodes = True
    hb = hm.node_tree.nodes.get("Principled BSDF"); hb.inputs["Base Color"].default_value = (0.03, 0.026, 0.022, 1); hb.inputs["Roughness"].default_value = 0.9
    L["hair"].data.materials.clear(); L["hair"].data.materials.append(hm)


# ---------------------------------------------------------------- rest pose, rig, export
def repose(L):
    log("moving into the game's rest pose")
    F = rest_frames()
    for _ in range(2):
        for name, ob in L.items():
            if "zb_src" not in ob:  # keep the source-frame positions so the pose can be redone
                ob["zb_src"] = np.array([v.co[:] for v in ob.data.vertices]).ravel().tolist()
            P0 = np.array(ob["zb_src"]).reshape(-1, 3); W = get_weights(ob)
            out = np.zeros_like(P0)
            for bi, b in enumerate(BONES):
                f = F[b]; idx = np.nonzero(W[:, bi] > 0)[0]
                if not len(idx):
                    continue
                M = np.array(f["R"]) * S; q = (P0[idx] - np.array(f["O"])) @ M.T
                if "K" in f:
                    k, e = f["K"]; e = np.array(e); q = q + np.outer((k - 1) * (q @ e), e)
                out[idx] += W[idx, bi:bi + 1] * (q + np.array(f["P"]))
            ob.data.vertices.foreach_set("co", out.ravel()); ob.data.update()
        sole = min(v.co.z for v in L["boots"].data.vertices)
        log(f"  soles at {sole * 100:.1f} cm")
        if abs(sole) < 0.002:
            break
        kn = F["knee1"]; k, e = kn["K"]; drop = kn["P"].z  # knee height; stretch the shin to put the soles on the ground
        F = rest_frames(k * (drop - 0) / (drop - sole))
    for ob in L.values():
        activate(ob); bpy.ops.object.shade_smooth()
    return F


def proxies(L, F):
    """Invisible hit shapes, one convex hull per joint, in that joint's own frame."""
    pts = {b: [] for b in BONES}
    for ob in L.values():
        W = get_weights(ob)
        for v, row in zip(ob.data.vertices, W):
            pts[BONES[int(np.argmax(row))]].append(v.co.copy())
    out = []
    for b, ps in pts.items():
        if len(ps) < 8:
            continue
        f = F[b]; inv = f["Rf"].transposed()
        bm = bmesh.new()
        for p in ps:
            bm.verts.new(inv @ (p - f["P"]))
        res = bmesh.ops.convex_hull(bm, input=bm.verts)
        loose = {v for v in res["geom_interior"] + res["geom_unused"] if isinstance(v, bmesh.types.BMVert)}
        bmesh.ops.delete(bm, geom=list(loose), context="VERTS")
        me = bpy.data.meshes.new("zp_" + b); bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new("zp_" + b, me); scene.collection.objects.link(ob); out.append(ob)
        dec = ob.modifiers.new("d", "DECIMATE"); dec.ratio = min(1, 140 / max(1, len(me.polygons))); apply_mods(ob)
    return out


def rig(L, F):
    arm = bpy.data.armatures.new("zb_rig"); ro = bpy.data.objects.new("zb_rig", arm); scene.collection.objects.link(ro)
    activate(ro); bpy.ops.object.mode_set(mode="EDIT")
    root = arm.edit_bones.new("body"); root.head = (0, 0, 0); root.tail = (0, 0, 0.1)
    for b in BONES:
        f = F[b]; eb = arm.edit_bones.new(b); eb.head = f["P"]; eb.tail = f["P"] + f["Rf"] @ Vector((0, 0, 0.05)); eb.parent = root
    bpy.ops.object.mode_set(mode="OBJECT")
    for ob in L.values():
        ob.parent = ro; m = ob.modifiers.new("rig", "ARMATURE"); m.object = ro
    return ro


def layout_empty(F):
    e = bpy.data.objects.new("zb_layout", None); scene.collection.objects.link(e)
    hp = Vector(to_game(F["head"]["P"]))
    lay = dict(arm=to_game(F["arm1"]["P"]), ua=round(S * (J["elbow"] - J["shoulder"]).length, 5),
               fa=round(S * (J["wrist"] - J["elbow"]).length, 5), leg=to_game(F["leg1"]["P"]),
               th=round((F["knee1"]["P"] - F["leg1"]["P"]).length, 5), splay=SPLAY,
               jaw=[round(c, 5) for c in (Vector(to_game(F["jaw"]["P"])) - hp)],
               eye=[round(c, 5) for c in (Vector(to_game(G(V(0.032, -0.155, 1.685)))) - hp)])
    e["layout"] = json.dumps(lay)
    log("  layout", lay)
    return e


def export(objs):
    for o in objs:  # working data the game has no use for
        for k in ("zb_src", "zb_baked"):
            if k in o:
                del o[k]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False); o.select_set(True)
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_skins=True, export_animations=False,
                              export_extras=True, export_image_format="WEBP", export_image_quality=82, export_yup=True,
                              export_texcoords=True, export_normals=True, export_apply=False)
    log(f"exported {OUT} ({os.path.getsize(OUT) / 1e6:.2f} MB)")


def preview(L, path):
    for o in bpy.data.objects:
        o.hide_render = not (o.name.startswith("zb_") and o.type == "MESH")
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    cam = bpy.data.cameras.new("zb_cam"); cam.lens = 70; co = bpy.data.objects.new("zb_cam", cam); scene.collection.objects.link(co)
    co.location = (1.6, -3.6, 1.35); co.rotation_euler = (math.radians(88), 0, math.radians(24)); scene.camera = co
    for ld in ((3, -3, 4, 900), (-3, -2, 2, 300), (0, 3, 3, 400)):
        l = bpy.data.lights.new("zb_l", "AREA"); l.energy = ld[3]; l.size = 2
        lo = bpy.data.objects.new("zb_l", l); lo.location = ld[:3]; scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 1)) - Vector(ld[:3])).to_track_quat("-Z", "Y").to_euler()
    w = scene.world; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.055, 1)
    scene.render.resolution_x, scene.render.resolution_y = 800, 1000; scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------- run
if bpy.data.objects.get("zb_skin") and bpy.data.objects["zb_skin"].get("zb_baked"):
    log("using the baked layers in this file")
    L = {k: bpy.data.objects["zb_" + k] for k in ("skin", "shirt", "jacket", "tie", "trousers", "boots", "hair")}
else:
    L, _ = build_layers()
    bake_all(L)
    L["skin"]["zb_baked"] = True
    if WORK:
        bpy.ops.wm.save_as_mainfile(filepath=WORK, copy=True)
        log("saved", WORK)
F = repose(L)
P = proxies(L, F)
R = rig(L, F)
E = layout_empty(F)
export(list(L.values()) + P + [R, E])
if PREVIEW:
    preview(L, PREVIEW)
log("done")
