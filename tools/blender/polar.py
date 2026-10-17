# The 南極研究站 of 死城突圍's level 14 (see CONTEXT.md, .scratch/level-14/spec.md).
#
#   blender -b -P tools/blender/polar.py -- assets/models/polar.glb [preview.png]
#
# Game coordinates (+Y up, front toward +Z); every piece stands on its own origin and the game lays them out.
# Untextured, so exported without UVs.
#   polar_module   an orange prefab building on stilts (12 x 6 m), door and stairs on the front
#   polar_dome     a radar dome on its base;  polar_tank  a pair of fuel tanks on saddles
#   polar_turbine  a wind turbine's tower and nacelle;  polar_blades  its rotor (origin on the hub, spins about Z)
#   polar_snowcat  a tracked snow vehicle;  polar_mast  a lattice antenna mast;  polar_flag  a pole with flags
#   polar_drill    the drilling derrick over its borehole
#   ice_block      the 冰封巨塊;  ice_shadow  the beast's shape frozen inside it;  ice_block_broken  what is left once it bursts
#   ice_ridge      a 10 m stretch of jagged ice cliff for the edge of the map;  ice_rock  an ice boulder (cover)
#   polar_plane    the ski-equipped supply plane at the start
import bpy, bmesh, math, random, sys
from mathutils import Vector
from mathutils.noise import noise as pnoise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "polar.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
random.seed(14)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []

PALETTE = {  # name: (colour, roughness, metallic, alpha, emission)
    "orange": ((0.8, 0.22, 0.03), 0.55, 0.1, 1, 0), "red": ((0.6, 0.05, 0.04), 0.5, 0.1, 1, 0), "white_paint": ((0.82, 0.84, 0.86), 0.5, 0.1, 1, 0),
    "steel": ((0.42, 0.44, 0.47), 0.4, 0.85, 1, 0), "steel_dark": ((0.12, 0.13, 0.14), 0.5, 0.8, 1, 0), "window": ((0.05, 0.1, 0.16), 0.1, 0.5, 1, 0.4),
    "yellow": ((0.75, 0.55, 0.05), 0.5, 0.1, 1, 0), "tracks": ((0.03, 0.03, 0.03), 0.9, 0.0, 1, 0), "snow": ((0.85, 0.88, 0.92), 0.95, 0.0, 1, 0),
    "ice": ((0.55, 0.78, 0.92), 0.08, 0.0, 0.72, 0), "ice_dark": ((0.28, 0.45, 0.6), 0.15, 0.0, 1, 0), "shadow": ((0.04, 0.05, 0.07), 0.6, 0.0, 1, 0),
    "flag_blue": ((0.05, 0.15, 0.55), 0.8, 0.0, 1, 0), "flag_green": ((0.05, 0.4, 0.15), 0.8, 0.0, 1, 0), "lamp": ((1.0, 0.85, 0.5), 0.3, 0.0, 1, 3.0),
    "borehole": ((0.01, 0.01, 0.015), 1.0, 0.0, 1, 0),
}
MAT = {}
for n, (c, r, mt, a, em) in PALETTE.items():
    m = bpy.data.materials.new(n); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1); b.inputs["Roughness"].default_value = r; b.inputs["Metallic"].default_value = mt
    if a < 1:
        b.inputs["Alpha"].default_value = a
        try: m.surface_render_method = "BLENDED"
        except Exception: m.blend_method = "BLEND"
    if em:
        b.inputs["Emission Color"].default_value = (*c, 1); b.inputs["Emission Strength"].default_value = em
    MAT[n] = m


def B(x, y, z):
    return Vector((x, -z, y))


def G(v):
    return Vector((v.x, v.z, -v.y))


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)


def settle(ob, mat, smooth=False):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear(); ob.data.materials.append(MAT[mat])
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return ob


def box(c, s, mat, rot_y=0.0, rot=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*c), rotation=rot if rot else (0, 0, -rot_y))
    ob = bpy.context.object; ob.scale = (s[0], s[2], s[1])
    return settle(ob, mat)


def cyl(p0, p1, r, mat, verts=16, r1=None):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r1 is None else r1, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return settle(ob, mat, True)


def ball(c, r, mat, segs=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=max(6, segs // 2), radius=1, location=B(*c))
    ob = bpy.context.object; ob.scale = (r[0], r[2], r[1]) if isinstance(r, tuple) else (r, r, r)
    return settle(ob, mat, True)


def lump(c, r, mat, amp=0.25, freq=0.6, sub=2, seed=0.0):
    """A jagged ice/snow lump: an icosphere pushed about by noise, scaled to radii r."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1, location=(0, 0, 0))
    ob = bpy.context.object
    for v in ob.data.vertices:
        p = v.co.copy(); v.co = p * (1 + amp * pnoise(p * freq * 3 + Vector((seed, seed * 2, seed * 3))))
    ob.scale = (r[0], r[2], r[1]); ob.location = B(*c)
    return settle(ob, mat)


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


# ===================================================================== research module on stilts
W, D, H0, H = 12.0, 6.0, 1.3, 3.4
parts = [box((0, H0 + H / 2, 0), (W, H, D), "orange"), box((0, H0 + H + 0.1, 0), (W + 0.3, 0.2, D + 0.3), "white_paint"),
         box((0, H0 + 0.05, 0), (W + 0.1, 0.1, D + 0.1), "steel_dark")]
for x in (-5.4, -1.8, 1.8, 5.4):
    for z in (-2.6, 2.6):
        parts.append(cyl((x, 0, z), (x, H0, z), 0.12, "steel", 8))
for x in (-4.5, -2.7, 2.7, 4.5):  # windows down both long sides
    for s in (-1, 1):
        parts.append(box((x, H0 + 2.0, s * (D / 2 + 0.02)), (1.2, 0.9, 0.04), "window"))
parts += [box((0, H0 + 1.2, D / 2 + 0.03), (1.1, 2.2, 0.06), "white_paint"), box((0, H0 + 0.0, D / 2 + 0.9), (1.6, 0.1, 1.8), "steel_dark")]
for k in range(5):  # stairs down to the snow
    parts.append(box((0, H0 - 0.25 - k * 0.25, D / 2 + 1.9 + k * 0.3), (1.4, 0.06, 0.3), "steel"))
parts += [box((-W / 2 + 1, H0 + H + 0.6, -1), (1.4, 0.8, 1.2), "white_paint"), cyl((4, H0 + H + 0.2, 1.5), (4, H0 + H + 2.4, 1.5), 0.04, "steel", 6),
          ball((0.8, H0 + 2.9, D / 2 + 0.1), (0.15, 0.1, 0.1), "lamp", 8)]
join(parts, "polar_module")

# ===================================================================== radar dome
parts = [box((0, 1.5, 0), (7, 3, 7), "white_paint"), box((0, 3.05, 0), (7.3, 0.1, 7.3), "steel_dark"), box((0, 1.1, 3.52), (1.1, 2.2, 0.05), "orange")]
dome = ball((0, 5.4, 0), 3.4, "white_paint", 20)
parts.append(dome)
join(parts, "polar_dome")

# ===================================================================== fuel tanks
parts = []
for x in (-1.7, 1.7):
    parts += [cyl((x, 1.8, -4), (x, 1.8, 4), 1.4, "white_paint", 20), ball((x, 1.8, 4), (1.4, 1.4, 0.4), "white_paint", 16), ball((x, 1.8, -4), (1.4, 1.4, 0.4), "white_paint", 16),
              cyl((x, 1.8, -1), (x, 1.8, 1), 1.42, "red", 20)]
    for z in (-2.5, 2.5):
        parts.append(box((x, 0.5, z), (2.4, 1.0, 0.4), "steel_dark"))
parts.append(cyl((0, 3.3, 2), (0, 3.3, -2), 0.08, "steel", 8))
join(parts, "polar_tank")

# ===================================================================== wind turbine (tower + nacelle) and its rotor
join([cyl((0, 0, 0), (0, 14, 0), 0.5, "white_paint", 14, 0.3), box((0, 14.2, -0.4), (1.0, 1.0, 2.4), "white_paint"), box((0, 0.3, 0), (1.6, 0.6, 1.6), "steel_dark")], "polar_turbine")
parts = [ball((0, 0, 0), (0.45, 0.45, 0.6), "white_paint", 12)]
for k in range(3):
    a = k / 3 * math.tau
    parts.append(box((math.sin(a) * 2.6, math.cos(a) * 2.6, 0), (0.45, 5.0, 0.08), "white_paint", rot=(0, a, 0)))
    parts.append(box((math.sin(a) * 4.8, math.cos(a) * 4.8, 0), (0.46, 0.6, 0.09), "red", rot=(0, a, 0)))
join(parts, "polar_blades")

# ===================================================================== snowcat
parts = [box((0, 1.5, 0.2), (2.4, 1.2, 4.6), "orange"), box((0, 2.5, -0.4), (2.2, 1.0, 2.6), "orange"),
         box((0, 2.6, 0.92), (2.0, 0.7, 0.05), "window"), *[box((s * 1.11, 2.6, -0.4), (0.05, 0.6, 2.2), "window") for s in (-1, 1)],
         box((0, 1.0, 2.6), (2.6, 0.6, 0.3), "steel_dark"), *[ball((s * 0.7, 1.55, 2.53), (0.15, 0.12, 0.05), "lamp", 8) for s in (-1, 1)],
         box((0, 3.05, -0.4), (1.6, 0.1, 1.6), "steel_dark")]
for s in (-1, 1):  # tracks
    parts += [box((s * 1.25, 0.55, 0.2), (0.7, 1.1, 5.0), "tracks")]
    for z in (-1.8, -0.6, 0.6, 1.8):
        parts.append(cyl((s * 1.62, 0.55, z), (s * 1.6, 0.55, z), 0.42, "steel_dark", 12))
join(parts, "polar_snowcat")

# ===================================================================== antenna mast and flags
parts = []
for k in range(3):
    a = k / 3 * math.tau
    parts.append(cyl((math.sin(a) * 0.5, 0, math.cos(a) * 0.5), (math.sin(a) * 0.15, 16, math.cos(a) * 0.15), 0.05, "steel", 6))
for y in range(1, 16, 2):
    r = 0.5 - y / 16 * 0.35
    for k in range(3):
        a0, a1 = k / 3 * math.tau, (k + 1) / 3 * math.tau
        parts.append(cyl((math.sin(a0) * r, y, math.cos(a0) * r), (math.sin(a1) * r, y, math.cos(a1) * r), 0.025, "steel", 4))
parts += [cyl((0, 13, 0.3), (0, 13, 0.7), 0.9, "white_paint", 16, 0.2), ball((0, 16.1, 0), 0.12, "lamp", 8)]
join(parts, "polar_mast")
parts = [cyl((0, 0, 0), (0, 6, 0), 0.06, "steel", 8)]
for k, mat in enumerate(("red", "flag_blue", "flag_green")):
    y = 5.6 - k * 0.05; z = 0
    parts.append(box((0.03, y - k * 0.0, 0.75 + 0.0), (0.03, 0.8, 1.4), mat, rot=(0, 0, -k * 2.1)))
join(parts, "polar_flag")

# ===================================================================== drilling derrick over the borehole
parts = [box((0, 0.6, 0), (8, 1.2, 8), "steel_dark"), box((0, 1.25, 0), (8.2, 0.1, 8.2), "yellow")]
for sx in (-1, 1):
    for sz in (-1, 1):
        parts.append(cyl((sx * 2.6, 1.3, sz * 2.6), (sx * 0.6, 15, sz * 0.6), 0.14, "orange", 8))
for y in (4, 7, 10, 13):
    r = 2.6 - (y - 1.3) / 13.7 * 2.0
    for a, b in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
        parts.append(cyl((a[0] * r, y, a[1] * r), (b[0] * r, y, b[1] * r), 0.07, "orange", 6))
parts += [box((0, 15.2, 0), (1.8, 0.5, 1.8), "steel"), cyl((0, 1.3, 0), (0, 13, 0), 0.18, "steel", 10),
          box((3.2, 2.2, -2.5), (1.6, 1.8, 2.2), "white_paint"), cyl((2.6, 2.2, -1.2), (2.6, 2.2, 0.8), 0.5, "yellow", 14),
          cyl((0, 1.3, 0), (0, 1.32, 0), 0.9, "borehole", 20)]
for k in range(5):  # drill pipes racked beside it
    parts.append(cyl((-3.4 + k * 0.25, 1.3, -3.6), (-3.4 + k * 0.25, 9, -3.2), 0.1, "steel", 8))
join(parts, "polar_drill")

# ===================================================================== the 冰封巨塊 (centred on its origin, 10 x 8 x 9), the shape in it, and the burst
parts = [lump((0, 4.2, 0), (5.2, 4.4, 4.3), "ice", 0.18, 0.5, 3, 1.0)]
for k in range(9):  # crystal facets sticking out of the block
    a = random.uniform(0, math.tau); y = random.uniform(1.5, 7.5)
    parts.append(lump((math.sin(a) * 4.6, y, math.cos(a) * 3.8), (random.uniform(0.8, 1.6), random.uniform(1.2, 2.4), random.uniform(0.8, 1.4)), "ice", 0.3, 0.8, 1, k))
join(parts, "ice_block")
parts = [ball((0, 4.0, 0), (1.6, 1.8, 3.2), "shadow", 16), ball((0, 4.4, 3.1), (0.9, 0.9, 1.1), "shadow", 12)]  # body and head, curled up
for sx in (-1, 1):
    for sz in (-1.8, 1.6):
        parts.append(cyl((sx * 1.1, 3.4, sz), (sx * 1.4, 1.2, sz + 0.6), 0.45, "shadow", 8))
    parts.append(cyl((sx * 0.5, 3.8, 3.8), (sx * 0.9, 3.0, 5.0), 0.15, "shadow", 8, 0.02))  # tusks
join(parts, "ice_shadow")
parts = []
for k in range(16):  # jagged stumps where the block stood, and chunks thrown across the snow
    a = k / 16 * math.tau + random.uniform(-0.1, 0.1); r = random.uniform(3.2, 4.8)
    parts.append(lump((math.sin(a) * r, random.uniform(0.3, 1.0), math.cos(a) * r), (random.uniform(0.6, 1.2), random.uniform(0.5, 1.6), random.uniform(0.6, 1.0)), "ice", 0.35, 0.9, 1, k * 0.7))
for k in range(14):
    a = random.uniform(0, math.tau); r = random.uniform(6, 13)
    parts.append(lump((math.sin(a) * r, 0.25, math.cos(a) * r), (random.uniform(0.3, 0.8),) * 3, "ice", 0.3, 0.9, 1, k * 1.3))
join(parts, "ice_block_broken")

# ===================================================================== ice cliff segment (10 m, the inner face toward +Z) and an ice boulder
parts = []
for k in range(6):
    x = -5 + k * 2 + random.uniform(-0.3, 0.3); h = random.uniform(4, 7.5)
    parts.append(lump((x, h / 2, -random.uniform(0.5, 1.5)), (1.6, h / 2, 1.8), "ice_dark" if k % 3 == 0 else "ice", 0.3, 0.7, 1, k * 0.9))
parts.append(lump((0, 0.4, 1.0), (5.5, 0.9, 1.3), "snow", 0.2, 0.5, 2, 3.3))  # a snowdrift banked against its foot
for o in parts:
    for p in o.data.polygons:
        pass
join(parts, "ice_ridge")
join([lump((0, 0.9, 0), (1.7, 1.1, 1.5), "ice", 0.3, 0.7, 2, 5.5), lump((0.9, 0.5, 0.8), (0.8, 0.6, 0.8), "ice_dark", 0.3, 0.9, 1, 2.2),
      lump((-0.4, 0.15, 1.2), (1.6, 0.35, 0.9), "snow", 0.2, 0.6, 1, 7.7)], "ice_rock")

# ===================================================================== supply plane on skis (16 m), nose toward +Z
FY = 2.2
parts = [cyl((0, FY, -7), (0, FY, 6), 1.0, "red", 16), ball((0, FY, 6), (1.0, 1.0, 1.4), "red", 14), cyl((0, FY, -7), (0, FY + 0.6, -8.6), 1.0, "red", 14, 0.25),
         box((0, FY + 0.4, 5.2), (1.6, 0.6, 0.05), "window"), box((0, FY + 1.2, 1.2), (19.8, 0.25, 2.0), "white_paint"),
         box((0, FY + 1.0, -8.2), (6.4, 0.15, 1.4), "white_paint"), box((0, FY + 2.2, -8.1), (0.15, 2.6, 1.6), "red")]
for s in (-1, 1):
    parts += [cyl((s * 3.2, FY + 0.8, 2.8), (s * 3.2, FY + 0.8, 0.0), 0.45, "white_paint", 12), cyl((s * 3.2, FY + 0.8, 2.85), (s * 3.2, FY + 0.8, 3.0), 0.12, "steel_dark", 8),
              box((s * 3.2, FY + 0.8, 3.0), (2.6, 0.18, 0.06), "steel_dark"),
              cyl((s * 1.0, FY - 0.8, 0.5), (s * 1.6, 0.5, 0.5), 0.08, "steel", 6), box((s * 1.7, 0.25, 0.5), (0.45, 0.12, 3.0), "steel")]
    for k in range(4):
        parts.append(box((s * 1.02, FY + 0.35, 3.4 - k * 1.5), (0.04, 0.5, 0.6), "window"))
parts += [cyl((0, FY - 0.9, 4.6), (0, 0.5, 4.6), 0.08, "steel", 6), box((0, 0.25, 4.6), (0.4, 0.12, 2.0), "steel")]
join(parts, "polar_plane")

for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_texcoords=False)
for ob in PARTS:
    print("  part", ob.name, len(ob.data.polygons))
print("exported", OUT)

if PREVIEW:
    place = {"polar_module": (-18, 0, -8), "polar_dome": (14, 0, -16), "polar_tank": (20, 0, 4), "polar_turbine": (-30, 0, -24), "polar_blades": (-30, 14.2, -22.6),
             "polar_snowcat": (-6, 0, 6, 0.6), "polar_mast": (28, 0, -24), "polar_flag": (4, 0, 10), "polar_drill": (0, 0, -6), "ice_block": (-8, 0, -14),
             "ice_shadow": (-8, 0, -14), "ice_ridge": (0, 0, -30), "ice_rock": (8, 0, 8), "polar_plane": (-14, 0, 14, 0.4), "ice_block_broken": (0, -40, 0)}
    for ob in PARTS:
        v = place.get(ob.name, (0, -40, 0)); ob.location = B(v[0], v[1], v[2])
        if len(v) > 3: ob.rotation_euler = (0, 0, -v[3])
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0)); g = bpy.context.object; g.data.materials.append(MAT["snow"])
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.7, 0.75, 0.82, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(55), 0, math.radians(30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 20; eye, tgt = B(10, 14, 40), B(-2, 3, -8)
    cam.location = eye; cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"; scene.cycles.samples = 16; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
