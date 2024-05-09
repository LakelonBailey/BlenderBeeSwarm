import bpy
from mathutils import Vector, Quaternion
import random
import math
from typing import Literal


hive = bpy.data.objects.get("Hive")

# Number of frames to pause before animating objects
INITIAL_PAUSE_FRAMES = 50

# Number of frames to animate objects for
MINIMUM_FRAME_COUNT = 1500

# Total number of frames
FRAME_COUNT = MINIMUM_FRAME_COUNT + INITIAL_PAUSE_FRAMES

# Number of frames to step by
FRAME_STEP = 1

# Bee speed
BEE_SPEED = 1

# Range in which flowers can be detected by bees
COGNITION_RANGE = 20

# Range in which other bees can be detected by bees
SOCIAL_RANGE = 15

# Cognition weight
COGNITION = 2

# Social weight
SOCIAL = 2

# Inertia weight
INERTIA = 1

# Scalar that is multiplied by the personal best score of an adjacent bee
SOCIAL_SCENT_COEFFICIENT = 1

# How close a bee must be to a flower to pollinate it
FLOWER_POLLINATION_PROXIMITY = 10

# Width of flower patch that Bees have access to
FLOWER_PATCH_WIDTH = 120

# Bounds of bee positioning by axis
BEE_POSITION_BOUNDS = {
    "x": [-1 * FLOWER_PATCH_WIDTH, FLOWER_PATCH_WIDTH],
    "y": [-1 * FLOWER_PATCH_WIDTH, FLOWER_PATCH_WIDTH],
    "z": [5, hive.location.z],
}

# Max number of bees that can attach to the flower
MAX_NEARBY_BEES = 5

# Minimum amount of time it takes in seconds to pollinate
# a flower
MIN_POLLINATION_TIME = 12

# Frames per second
FRAME_RATE = 24

# Number of pollinations that must occur in order for a flower
# to be marked pollinated
POLLINATION_THRESHOLD = (FRAME_RATE * MIN_POLLINATION_TIME) * MAX_NEARBY_BEES

# Max Bee turning radius
MAX_TURNING_RADIUS = 30

# Frame in which the Bees begin swarming instead of just leaving the bee hive
START_SWARMING_FRAME = 50 + INITIAL_PAUSE_FRAMES

# Frames remaining cutoff at which the bees will return to their nest
RETURN_TO_HIVE_FRAME_REMAINDER = (
    int(math.sqrt(2) * FLOWER_PATCH_WIDTH) / BEE_SPEED + 100
)

# Global variables used to generate flower and bee ids
flower_count = 0
bee_count = 0


# Helper function to generate random velocity
def random_velocity():
    return Vector(
        (
            random.uniform(-1, 1),
            random.uniform(-1, 1),
            random.uniform(-1, 1),
        )
    ).normalized()


# General wrapper for a Blender Object
class BaseObject:
    def __init__(self, object, id: int = None):
        self.id = id
        self.obj = object
        self.child_cache = {}
        self.pos = self.obj.location.copy()

    # Clear all keyframe data
    def clear_animation_data(self):
        if self.obj.animation_data:
            self.obj.animation_data_clear()

    # Get list of children
    def children(self):
        return self.obj.children_recursive

    # Find the first child with the given prefix
    def find_child(self, prefix: str):
        if prefix in self.child_cache:
            return self.child_cache[prefix]

        for child in self.children():
            if child.name.startswith(prefix):
                child_obj = BaseObject(child, random.randint(1, 5000))
                self.child_cache[prefix] = child_obj
                return child_obj
        return None

    # Change color of node material
    def set_color(self, color: tuple[float], frame: int = None):
        material = self.obj.active_material
        if material and material.use_nodes:
            bsdf_node = material.node_tree.nodes.get("Principled BSDF")
            bsdf_node.inputs["Base Color"].default_value = color
            if frame is not None:
                bpy.context.scene.frame_set(frame)
            bsdf_node.inputs["Base Color"].keyframe_insert(
                data_path="default_value", frame=bpy.context.scene.frame_current
            )

    # Calculate distance from another object
    def dist(self, other_obj_position_vec) -> float:
        self_global_pos = self.obj.location
        return (self_global_pos - other_obj_position_vec).magnitude


class Bee(BaseObject):
    def __init__(self, object):
        global bee_count
        object.location = hive.location.copy() + random_velocity()
        super(Bee, self).__init__(object, bee_count)
        bee_count += 1

        self.obj.rotation_euler = (0, 0, 0)
        self.clear_animation_data()
        self.reset_personal_best()
        self.reset_global_best()
        self.velocity = Vector(
            (
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-1, -0.5),
            )
        ).normalized()

        self.is_attached: bool = False
        self.action: Literal["leaving-hive", "swarming", "returning-to-hive"] = (
            "leaving-hive"
        )
        self.is_returned_to_hive: bool = False

    def transition_action(self):
        if self.action == "leaving-hive":
            self.reset_motive()
            self.action = "swarming"
        elif self.action == "swarming":
            self.reset_personal_best()
            self.reset_global_best()
            self.velocity = (hive.location - self.pos).normalized()
            self.action = "returning-to-hive"

    # Update positioning using Particle Swarm Optimization (PSO)
    def update(self, bees: list["Bee"], flowers: list["Flower"]):

        # If swarming, detect nearby flowers and bees
        if self.action == "swarming":
            self.pollinate_nearby_flowers(flowers)
            self.detect_nearby_bees(bees)

        # If returning to hive, stop the bee if it has reached the hive
        elif self.action == "returning-to-hive":
            if self.is_returned_to_hive:
                return

            if self.dist(hive.location) < 5:
                self.is_returned_to_hive = True

        # Update location
        self.calculate_position()
        self.handle_boundaries()
        self.obj.location = self.pos

        # Insert keyframe
        self.obj.keyframe_insert(data_path="location", index=-1)

        # Fix rotation
        self._redirect(self.velocity)

    # Fix rotation if moving
    def _redirect(self, velocity):
        if velocity.magnitude > 0:
            self._set_rotation(velocity)

    # Set rotation based on starting position
    def _set_rotation(self, direction: Vector):
        forward_vector = Vector((1, 0, 0))
        direction_vector = direction.normalized()
        rotation_quaternion = forward_vector.rotation_difference(direction_vector)
        self.obj.rotation_mode = "QUATERNION"
        self.obj.rotation_quaternion = rotation_quaternion
        self.obj.keyframe_insert(data_path="rotation_quaternion")

    # Bounce off of walls based on Bee position bounds
    def handle_boundaries(self):
        for axis in ["x", "y", "z"]:
            min_pos, max_pos = BEE_POSITION_BOUNDS[axis]
            pos = getattr(self.pos, axis)
            if pos <= min_pos:
                setattr(self.pos, axis, min_pos)
                setattr(self.velocity, axis, -1 * getattr(self.velocity, axis))
            elif pos >= max_pos:
                setattr(self.pos, axis, max_pos)
                setattr(self.velocity, axis, -1 * getattr(self.velocity, axis))

    # Set position to the right spot based on PSO behavior
    def calculate_position(self):
        if self.velocity.magnitude == 0:
            return

        r1, r2 = (
            random.random(),
            random.random(),
        )
        new_velocity = self.velocity * INERTIA

        # Add cognitive component
        if self.personal_best_flower is not None:
            new_velocity += (
                COGNITION
                * r1
                * (
                    self.personal_best_flower.find_child(
                        "Pod"
                    ).obj.matrix_world.translation
                    - self.pos
                )
            )

        # Add social component
        if self.global_best_flower is not None:
            new_velocity += (
                SOCIAL
                * r2
                * (
                    self.global_best_flower.find_child(
                        "Pod"
                    ).obj.matrix_world.translation
                    - self.pos
                )
            )

        # Calculate the turning radius
        if MAX_TURNING_RADIUS is not None:
            turning_radius_radians = math.radians(MAX_TURNING_RADIUS)
            current_direction = self.velocity.normalized()
            desired_direction = new_velocity.normalized()

            # Compute the angle between the current and desired directions
            angle_between = math.acos(
                max(min(current_direction.dot(desired_direction), 1), -1)
            )

            if angle_between > turning_radius_radians:
                rotation_axis = current_direction.cross(desired_direction).normalized()
                rotation_quaternion = Quaternion(rotation_axis, turning_radius_radians)
                limited_direction = rotation_quaternion @ current_direction
                current_speed = min(new_velocity.magnitude, BEE_SPEED)
                new_velocity = limited_direction * current_speed

        self.velocity = new_velocity.normalized()
        self.pos += self.velocity * BEE_SPEED

    # Set personal best to default value
    def reset_personal_best(self):
        self.is_attached = False
        self.personal_best = float("inf")
        self.personal_best_flower = None
        self.previous_personal_best_flower = None

    # Set global best to default value
    def reset_global_best(self):
        self.is_attached = False
        self.global_best = float("inf")
        self.global_best_flower = None

    # Reset the current target of the bee
    def reset_motive(self):
        self.reset_personal_best()
        self.velocity = random_velocity()

    # Attempt to pollinate nearby flowesr
    def pollinate_nearby_flowers(self, flowers: list["Flower"]):

        # Search for the nearest flower
        self.cognition = None
        self.cognition_flower = None
        self.previous_personal_best_flower = self.personal_best_flower
        for flower in flowers:
            if flower.is_pollinated or flower.nearby_bees_count >= MAX_NEARBY_BEES:
                continue

            pod = flower.find_child("Pod")
            distance = self.dist(pod.obj.matrix_world.translation)
            if distance > COGNITION_RANGE:
                continue

            if self.cognition is None or distance < self.cognition:
                self.cognition = distance
                self.cognition_flower = flower

        # Update personal best if necessary
        if self.cognition is not None and self.cognition < self.personal_best:
            self.personal_best = self.cognition
            self.personal_best_flower = self.cognition_flower

        # No need to continue if there's no personal best
        if self.personal_best_flower is None:
            return

        # If a new best flower has been found, detach from the previous one if necessary
        if (
            self.previous_personal_best_flower is not None
            and self.personal_best_flower.id != self.previous_personal_best_flower.id
            and self.is_attached
        ):
            self.is_attached = False
            self.previous_personal_best_flower.nearby_bees_count -= 1

        # Handle pollinating a personal best
        if (
            self.personal_best <= FLOWER_POLLINATION_PROXIMITY
            and not self.personal_best_flower.is_pollinated
        ):

            # If the bee is attached already or there's room around the flower for
            # the bee, pollinate it
            if (
                self.is_attached
                or self.personal_best_flower.nearby_bees_count < MAX_NEARBY_BEES
            ):

                # Attach the bee if it wasn't attached already
                if not self.is_attached:
                    self.personal_best_flower.nearby_bees_count += 1
                    self.is_attached = True

                self.personal_best_flower.pollinate()

            # If the flower is full and the bee wasn't attached to it, find
            # a new flower
            else:
                self.reset_motive()

        # Reset the bee's motive if the flower becomes pollinated or its
        # personal best flower is full
        if self.personal_best_flower.is_pollinated or (
            not self.is_attached
            and self.personal_best_flower.nearby_bees_count >= MAX_NEARBY_BEES
        ):
            self.reset_motive()

    # Process communication from nearby bees
    def detect_nearby_bees(self, bees: list["Bee"]):

        # Search for the nearest bee
        self.social = None
        self.social_flower = None
        for bee in bees:

            # Ignore the bee if it's the current bee
            if self.id == bee.id:
                continue

            distance = self.dist(bee.obj.location)
            if distance > SOCIAL_RANGE:
                continue

            # If the bee is in range, get the best of its personal best or global best
            # flowers
            if (
                self.social is None
                or (SOCIAL_SCENT_COEFFICIENT * distance) < self.social
            ) and (
                bee.personal_best_flower
                and not bee.personal_best_flower.is_pollinated
                and bee.personal_best_flower.nearby_bees_count < MAX_NEARBY_BEES
            ):
                self.social = SOCIAL_SCENT_COEFFICIENT * bee.personal_best
                self.social_flower = bee.personal_best_flower

            if (
                self.social is None
                or (
                    bee.personal_best_flower is None
                    and (SOCIAL_SCENT_COEFFICIENT * distance) < self.social
                )
            ) and (
                bee.global_best_flower
                and not bee.global_best_flower.is_pollinated
                and bee.global_best_flower.nearby_bees_count < MAX_NEARBY_BEES
            ):
                self.social = SOCIAL_SCENT_COEFFICIENT * bee.global_best
                self.social_flower = bee.global_best_flower

        # Update global best if necessary
        if self.social is not None and self.social < self.global_best:
            self.global_best = self.social
            self.global_best_flower = self.social_flower

        # No need to continue if there's no personal best
        if self.global_best_flower is None:
            return

        # Reset the bee's velocity if the global best flower becomes pollinated
        if self.global_best_flower.is_pollinated or (
            self.global_best_flower.nearby_bees_count >= MAX_NEARBY_BEES
            and not self.is_attached
        ):
            self.reset_global_best()


class Flower(BaseObject):
    def __init__(self, object):
        global flower_count
        super(Flower, self).__init__(object, flower_count)
        flower_count += 1
        self.clear_animation_data()
        self.obj.rotation_euler = (
            0,
            0,
            random.uniform(0, math.radians(90)),
        )
        self.is_pollinated: bool = False
        self.pollination_count: int = 0
        self.nearby_bees_count: int = 0
        self.blue: tuple[int] = (0.0, 0.0, 1.0, 1.0)
        self.yellow: tuple[int] = (1.0, 1.0, 0.0, 1.0)
        self.pos: Vector = self.obj.matrix_world.translation.copy()

    def clear_animation_data(self):
        material = self.obj.active_material
        if material.animation_data and material.animation_data.action:
            material.animation_data_clear()

        super().clear_animation_data()

    # Iterate the flower's pollination count and set it to pollinated
    # if its pollination count reaches the threshold
    def pollinate(self):
        if self.is_pollinated:
            return

        self.pollination_count += 1
        self.is_pollinated = self.pollination_count >= POLLINATION_THRESHOLD

    # Set the pollination to false
    def depollinate(self):
        self.is_pollinated = False

    def update(self):

        # Update the pod color to reflect pollination
        color = self.yellow if self.is_pollinated else self.blue
        self.find_child("Pod").set_color(color)


# Clear all animation data from all objects
def clear_all_animation_data():
    # Clear animation data from all objects
    for obj in bpy.data.objects:
        obj.animation_data_clear()

    # Clear animation data from all materials
    for mat in bpy.data.materials:
        if mat.animation_data:
            mat.animation_data_clear()

    # Clear animation data from worlds
    for world in bpy.data.worlds:
        if world.animation_data:
            world.animation_data_clear()

    # Clear animation data from scenes
    for scene in bpy.data.scenes:
        if scene.animation_data:
            scene.animation_data_clear()


clear_all_animation_data()


bees = [Bee(obj) for obj in bpy.data.objects if obj.name.startswith("Bee")]
flowers = [Flower(obj) for obj in bpy.data.objects if obj.name.startswith("Flower")]

for frame in range(1, FRAME_COUNT, FRAME_STEP):

    # Set the global frame
    bpy.context.scene.frame_set(frame)

    # Don't do anything if within the initial pause
    if frame <= INITIAL_PAUSE_FRAMES:
        continue

    # Update bees
    for bee in bees:
        bee.update(bees, flowers)

        # Transition bee state if necessary
        if frame >= START_SWARMING_FRAME and bee.action != "swarming":
            bee.transition_action()
        elif (
            FRAME_COUNT - frame <= RETURN_TO_HIVE_FRAME_REMAINDER
            and bee.action != "returning-to-hive"
        ):
            bee.transition_action()

    # Update flowers
    for flower in flowers:
        flower.update()
