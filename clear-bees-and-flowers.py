import bpy


# Remove all objects that are duplicates of the keep_names objects
def cleanup_objects(keep_names):
    to_remove = []
    for obj in bpy.data.objects:
        base_name = obj.name.split(".")[0]  # Get the base name before the dot
        if obj.name not in keep_names:
            if any(base_name.startswith(name) for name in keep_names):
                to_remove.extend([obj] + list(obj.children_recursive))

    # Remove objects from scene and data blocks
    while to_remove:
        obj = to_remove.pop()
        bpy.data.objects.remove(obj, do_unlink=True)


# Initial cleanup to remove existing duplicates
cleanup_objects(["Bee", "Flower"])
default_animated_items = ["Bee", "Flower", "Pod"]
for item in default_animated_items:
    obj = bpy.data.objects.get(item)
    if obj.animation_data:
        obj.animation_data_clear()
