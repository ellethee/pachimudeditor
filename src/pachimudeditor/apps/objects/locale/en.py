"""Messages of objects in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "objects.not_found": "Object not found",
    "objects.vnum_taken": "An object with vnum {vnum} already exists.",
    "objects.in_reset_usage": "Cannot delete: the object is referenced by {count} reset commands ({zones}). Update or remove them first.",
    "objects.vnum_in_use": "Cannot change the vnum: the object is used {count} times (resets or exit keys) in: {zones}.",
    "objects.in_exit_key_usage": "Cannot delete: the object is the key of {count} exits ({zones}).",
    "objects.has_instances": "Cannot delete: {count} live instances of the object exist.",
}
