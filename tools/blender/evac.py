# Evacuation-zone models for level 10 of 死城突圍: the rescue helicopter and the props of the
# fortified landing zone. Exports one glTF with a named object per part.
#
#   blender -b -P tools/blender/evac.py -- assets/models/evac.glb [preview.png]
#
# Coordinates are written in the game's frame (+Y up, +Z forward = the helicopter's nose)
# and converted with B(). Every part is baked with its origin where the game places it:
#   heli_body        helicopter origin on the ground between the skids
#   heli_rotor       main rotor, origin at the hub (game spins it about Y)
#   heli_tail_rotor  tail rotor, origin at its hub (game spins it about X)
#   flood_tower / flood_lamps   light tower, origin at its foot; lamps get an emissive material
#   tent, jersey     army tent and concrete barrier, origin at the ground centre
import bpy, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "evac.glb"
PREVIEW = argv[1] if len(argv) > 1 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARTS = []


def B(x, y, z):
    return Vector((x, -z, y))


def to_three(v):
    return (v.x, v.z, -v.y)


def activate(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)


def bake(ob):
    activate(ob); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def finish(ob, name, subdiv=0, smooth=True):
    activate(ob)
    if subdiv:
        m = ob.modifiers.new("sub", "SUBSURF"); m.levels = subdiv
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.shade_smooth() if smooth else bpy.ops.object.shade_flat()
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    bake(ob)
    ob.name = name; ob.data.name = name
    PARTS.append(ob)
    return ob


def join(objs, name):
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name
    return ob


def skin(nodes, edges, name="s"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([B(*n[:3]) for n in nodes], edges, [])
    ob = bpy.data.objects.new(name, me); scene.collection.objects.link(ob)
    ob.modifiers.new("skin", "SKIN")
    for i, n in enumerate(nodes):
        sv = me.skin_vertices[0].data[i]; sv.radius = (n[3], n[4]); sv.use_root = i == 0
    activate(ob)
    m = ob.modifiers.new("sub", "SUBSURF"); m.levels = 2
    bpy.ops.object.convert(target="MESH")
    return ob


def box(center, size, bevel=0.15, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=B(*center), rotation=rot)
    ob = bpy.context.object; ob.scale = (size[0], size[2], size[1]); bake(ob)
    if bevel:
        m = ob.modifiers.new("bev", "BEVEL"); m.width = min(size) * bevel; m.segments = 2
        activate(ob); bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def ellipsoid(center, radii, segs=24, rings=14):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=1, location=B(*center))
    ob = bpy.context.object; ob.scale = (radii[0], radii[2], radii[1]); return bake(ob)


def tube(p0, p1, r, verts=12):
    a, b = B(*p0), B(*p1); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(a + b) / 2)
    ob = bpy.context.object; ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return bake(ob)


# ================================================================ helicopter
hull = skin([
    (0, 1.35, 3.3, 0.55, 0.62),    # nose
    (0, 1.5, 2.2, 0.95, 1.0),      # cockpit
    (0, 1.6, 0.8, 1.15, 1.2),      # cabin
    (0, 1.65, -0.9, 1.05, 1.15),   # rear cabin
    (0, 1.95, -2.4, 0.5, 0.55),    # tail boom root
    (0, 2.2, -5.2, 0.24, 0.26),
    (0, 2.35, -6.6, 0.16, 0.2),    # tail end
    (0, 3.3, -6.8, 0.07, 0.35),    # vertical fin
], [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)], "hull")
# flatten the belly and square the cabin sides a little
for v in hull.data.vertices:
    x, y, z = to_three(v.co)
    if y < 1.0 and z > -2.5:
        y = 1.0 + (y - 1.0) * 0.45
    if abs(x) > 0.8 and -1.5 < z < 2.0:
        x = math.copysign(0.8 + (abs(x) - 0.8) * 0.6, x)
    v.co = B(x, y, z)
engine = ellipsoid((0, 2.72, 0.1), (0.62, 0.36, 1.7), 24, 12)
exhaust = [tube((s * 0.45, 2.7, -1.2), (s * 0.55, 2.62, -1.9), 0.16) for s in (-1, 1)]
mast = tube((0, 2.9, 0.2), (0, 3.25, 0.2), 0.14)
stab = box((0, 2.3, -6.1), (2.0, 0.05, 0.45), 0.3)
wings = [box((s * 1.45, 1.55, 0.3), (1.1, 0.08, 0.7), 0.3) for s in (-1, 1)]
pods = [tube((s * 1.9, 1.35, 1.0), (s * 1.9, 1.35, -0.5), 0.14, 14) for s in (-1, 1)]
skids = []
for s in (-1, 1):
    skids.append(tube((s * 1.15, 0.08, 2.4), (s * 1.15, 0.08, -2.0), 0.06))
    skids.append(tube((s * 1.15, 0.08, 2.4), (s * 1.1, 0.25, 2.85), 0.06))
    for zz in (1.4, -1.0):
        skids.append(tube((s * 1.15, 0.08, zz), (s * 0.75, 0.85, zz), 0.055))
door_rails = [box((s * 1.18, 2.05, 0.2), (0.06, 0.06, 2.2), 0.3) for s in (-1, 1)]
finish(join([hull, engine, mast, stab] + exhaust + wings + pods + skids + door_rails, "heli_body"), "heli_body")
glass = ellipsoid((0, 1.8, 2.35), (0.86, 0.6, 0.95), 24, 14)
for v in glass.data.vertices:            # keep only the upper front of the canopy
    x, y, z = to_three(v.co)
    v.co = B(x, max(y, 1.55), max(z, 1.7))
finish(glass, "heli_glass")

hub = tube((0, -0.05, 0), (0, 0.12, 0), 0.22, 16)
blades = []
for k in range(4):
    a = k * math.pi / 2
    b = box((math.cos(a) * 3.7, 0.02, math.sin(a) * 3.7), (7.2, 0.04, 0.32), 0.2, rot=(0, 0, -a))
    blades.append(b)
finish(join([hub] + blades, "heli_rotor"), "heli_rotor")
thub = tube((-0.08, 0, 0), (0.08, 0, 0), 0.1, 12)
tblades = [box((0, math.cos(a) * 0.7, math.sin(a) * 0.7), (0.03, 1.4, 0.16), 0.2, rot=(a, 0, 0)) for a in (0, math.pi / 2)]
finish(join([thub] + tblades, "heli_tail_rotor"), "heli_tail_rotor")

# ================================================================ landing-zone props
legs = [tube((math.cos(a) * 0.9, 0, math.sin(a) * 0.9), (0, 3.2, 0), 0.05, 8) for a in (0.3, 2.4, 4.5)]
pole = tube((0, 0, 0), (0, 6.6, 0), 0.08, 10)
frame = box((0, 6.7, 0.1), (1.8, 1.0, 0.2), 0.1)
genbox = box((0.9, 0.35, -0.6), (1.1, 0.7, 0.8), 0.12)
finish(join(legs + [pole, frame, genbox], "flood_tower"), "flood_tower", smooth=False)
lamps = [box((x, y, 0.21), (0.36, 0.3, 0.04), 0.2) for x in (-0.6, -0.2, 0.2, 0.6) for y in (6.5, 6.9)]
finish(join(lamps, "flood_lamps"), "flood_lamps", smooth=False)

# ridge tent: sloped canvas roof over short walls, with a rolled-up door
bpy.ops.mesh.primitive_cube_add(size=1)
tent = bpy.context.object
tent.scale = (4.0, 5.0, 1.0)
bake(tent)
for v in tent.data.vertices:
    x, y, z = to_three(v.co)
    y = 1.1 if y > 0 else 0.0
    if y > 0 and abs(x) < 0.01:
        pass
    v.co = B(x, y, z)
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.mesh.subdivide(number_cuts=1); bpy.ops.object.mode_set(mode="OBJECT")
for v in tent.data.vertices:
    x, y, z = to_three(v.co)
    if y > 1.0:
        y = 1.1 + (2.0 - abs(x)) * 0.75   # ridge line along the tent
    v.co = B(x, y, z)
roll = tube((-0.6, 1.5, 2.55), (0.6, 1.5, 2.55), 0.12)
guys = [tube((s * 2.0, 1.05, zz), (s * 2.8, 0.0, zz), 0.012, 6) for s in (-1, 1) for zz in (-2.2, 0, 2.2)]
finish(join([tent, roll] + guys, "tent"), "tent", smooth=False)

# jersey barrier: the classic stepped concrete profile, extruded 3 m
prof = [(-0.3, 0.0), (0.3, 0.0), (0.3, 0.08), (0.17, 0.33), (0.08, 0.81), (-0.08, 0.81), (-0.17, 0.33), (-0.3, 0.08)]
verts = [B(x, y, z) for z in (-1.5, 1.5) for (x, y) in prof]
n = len(prof)
faces = [tuple(range(n))[::-1], tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
me = bpy.data.meshes.new("jersey"); me.from_pydata(verts, [], faces)
jer = bpy.data.objects.new("jersey", me); scene.collection.objects.link(jer)
m = jer.modifiers.new("bev", "BEVEL"); m.width = 0.02; m.segments = 2
finish(jer, "jersey", smooth=False)

# ---------------------------------------------------------------- export
for ob in scene.objects:
    ob.select_set(ob in PARTS)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="NONE")
for o in PARTS:
    print("  part", o.name, sum(len(p.vertices) - 2 for p in o.data.polygons))
print("exported", OUT)

if PREVIEW:
    def mat(name, rgb, rough=0.6, metal=0.0):
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
        return m
    colors = {"heli_body": mat("od", (0.07, 0.08, 0.05), 0.55, 0.3), "heli_glass": mat("gl", (0.02, 0.03, 0.04), 0.05, 0.6),
              "heli_rotor": mat("rt", (0.02, 0.02, 0.02), 0.5), "heli_tail_rotor": mat("rt2", (0.02, 0.02, 0.02), 0.5),
              "flood_tower": mat("ft", (0.12, 0.12, 0.1), 0.6, 0.5), "flood_lamps": mat("fl", (0.9, 0.9, 0.8), 0.2),
              "tent": mat("tn", (0.14, 0.14, 0.08), 0.95), "jersey": mat("jr", (0.4, 0.39, 0.36), 0.9)}
    place = {"heli_body": (0, 0, 0), "heli_glass": (0, 0, 0), "heli_rotor": (0, 3.25, 0.2), "heli_tail_rotor": (0.3, 3.0, -6.75),
             "flood_tower": (-6, 0, -3), "flood_lamps": (-6, 0, -3), "tent": (6.5, 0, -3), "jersey": (-3, 0, 5)}
    for o in PARTS:
        o.data.materials.append(colors[o.name]); o.location = B(*place[o.name])
    bpy.ops.mesh.primitive_plane_add(size=40); bpy.context.object.data.materials.append(mat("gr", (0.12, 0.12, 0.12), 0.9))
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.3, 0.3, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(55), 0, math.radians(35))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
    cam.data.lens = 32; target = B(0, 1.5, -1)
    cam.location = B(10, 5.5, 11)
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler(); scene.camera = cam
    scene.render.engine = "CYCLES"; scene.cycles.samples = 24; scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = 1200, 700
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print("rendered", PREVIEW)
