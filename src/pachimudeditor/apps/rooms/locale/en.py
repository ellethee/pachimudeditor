"""Messages of rooms in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "rooms.not_found": "Room not found",
    "rooms.exit_not_found": "Exit not found",
    "rooms.extra_not_found": "Extra description not found",
    "rooms.vnum_taken": "A room with vnum {vnum} already exists.",
    "rooms.in_reset_usage": "Cannot delete: the room is referenced by {count} reset commands ({zones}). Update or remove them first.",
    "rooms.exit_direction_taken": "An exit towards {direction} already exists from this room.",
    "rooms.exit_not_in_room": "The exit does not belong to this room.",
    "rooms.extra_not_in_room": "The extra description does not belong to this room.",
    "rooms.vnum_in_use": "Cannot change the vnum: the room is referenced by {count} reset commands ({zones}).",
    "rooms.has_instances": "Cannot delete: the room holds {mobs} mobs, {objects} objects and is the last room of {players} characters.",
    "rooms.exit_door_state_invalid": "An exit without a door cannot be closed or locked.",
    "rooms.exit_locked_needs_key": "A locked exit requires a keyVnum.",
    "rooms.exit_key_unknown": "The key object with vnum {vnum} does not exist.",
    "rooms.exit_self_loop": "An exit cannot lead to the same room.",
}
