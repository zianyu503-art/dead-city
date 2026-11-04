# Shrink a whole-map glb for the web: textures down to 512 px JPEG, geometry Draco-compressed.
#   blender -b -P tools/blender/compress_map.py -- assets/models/map_x.glb [out.glb]
# Node names (COL_*, LAMP_*, Ground*) survive the round trip; the game decodes Draco with DRACOLoader.
import bpy, sys, os
argv = sys.argv[sys.argv.index("--") + 1:]
SRC = argv[0]; OUT = argv[1] if len(argv) > 1 else SRC
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
for im in bpy.data.images:
    if im.size[0] > 512:
        im.scale(512, 512)
for o in bpy.data.objects:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_yup=True, export_image_format="JPEG",
                          export_image_quality=75, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_tangents=False)
print("compressed", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")
