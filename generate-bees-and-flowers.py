import bpy
from mathutils import Vector
import random


START_IN_HIVE = False

hive = bpy.data.objects.get("Hive")


# Duplicate all children of an object
def duplicate_hierarchy(obj, collection, id: int):
    bpy.ops.object.select_all(action="DESELECT")

    obj.select_set(True)
    for child in obj.children_recursive:
        child.select_set(True)

    bpy.ops.object.duplicate_move(
        OBJECT_OT_duplicate={"linked": False, "mode": "TRANSLATION"}
    )

    # Set the correct parent on duplicate objects
    duplicated_objects = [o for o in bpy.context.selected_objects if o.select_get()]
    new_parent = None
    for new_obj in duplicated_objects:
        if new_obj.parent is None:
            new_parent = new_obj

        # If it's a pod, create the pod's individual material. This allows
        # the pod's color to be updated in isolation from other pods
        elif new_obj.name.startswith("Pod"):
            new_mat = bpy.data.materials.new(name=f"Pod.{str(id).rjust(3, '0')}")
            new_mat.use_nodes = True
            bsdf_node = new_mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            output_node = new_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
            new_mat.node_tree.links.new(
                bsdf_node.outputs["BSDF"], output_node.inputs["Surface"]
            )
            new_obj.data.materials[0] = new_mat
            bsdf_node.inputs["Base Color"].default_value = (0.0, 0.0, 1.0, 1.0)

        if new_obj.name not in collection.objects:
            collection.objects.link(new_obj)

    bpy.ops.object.select_all(action="DESELECT")

    return new_parent


# Check if an object is too close to any of the other objects based
# on the min_distance
def is_too_close(new_obj, other_objs, min_distance):
    for obj in other_objs:
        if (new_obj.location - obj.location).length < min_distance:
            return True
    return False


# Place a certain number of objects by duplicating the obj variable
def place_objects(obj, count, min_distance):
    objects = []
    for i in range(count):
        new_obj = duplicate_hierarchy(obj, bpy.context.collection, i + 1)
        while True:
            if START_IN_HIVE:
                new_obj.location = hive.location.copy()
                break
            else:
                new_obj.location = Vector(
                    (random.uniform(-100, 100), random.uniform(-100, 100), 0)
                )
                if not is_too_close(new_obj, objects, min_distance):
                    break
        objects.append(new_obj)
    return objects


initial_bee = bpy.data.objects.get("Bee")
initial_flower = bpy.data.objects.get("Flower")

# Place flowers and bees
place_objects(initial_flower, 50, 10)
place_objects(initial_bee, 200, 2)
