"""Messages of instances in en: stable code -> text.

The code is the contract with the clients; keep the same codes and {fields} in every language
(`pachifast locale check`), and use the module name as the first part of each code.
"""

MESSAGES: dict[str, str] = {
    "instances.mob_not_found": "Mob instance not found",
    "instances.object_not_found": "Object instance not found",
    "instances.mob_prototype_not_found": "Mob prototype does not exist: {id}",
    "instances.object_prototype_not_found": "Object prototype does not exist: {id}",
    "instances.room_not_found": "Room does not exist: {id}",
    "instances.holder_not_found": "Location target does not exist ({kind} {id})",
    "instances.container_not_found": "Container does not exist: {id}",
    "instances.not_a_container": "Object #{id} is not a container.",
    "instances.container_self": "An object cannot contain itself.",
    "instances.container_nested": "Container #{id} is already inside another container.",
    "instances.container_in_container": "A container cannot be put inside another container.",
    "instances.container_full": "Container #{id} is full (capacity {capacity}).",
    "instances.invalid_location_kind": "Invalid location kind: {kind}.",
    "instances.location_empty": "The location cannot be empty.",
    "instances.slot_not_allowed": "Only an object held by a mob or a character can be worn.",
    "instances.slot_invalid": 'Slot "{slot}" is not valid for this object (possible slots: {allowed}).',
    "instances.slot_taken": 'Slot "{slot}" is already occupied.',
    "instances.hp_min": "Hit points must be at least 1.",
    "instances.hp_exceeds_max": "Current hit points cannot exceed the maximum.",
    "instances.negative_value": "The value of {field} cannot be negative.",
    "instances.charges_not_allowed": "Charges only apply to wands and staffs.",
    "instances.liquid_not_allowed": "Liquid amount, type and poison only apply to liquid containers.",
    "instances.invalid_contents_policy": "Invalid value for contents: {value} (allowed: destroy, drop).",
}
