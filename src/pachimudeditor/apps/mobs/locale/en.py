"""Messages of mobs in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "mobs.not_found": "Mob not found",
    "mobs.vnum_taken": "A mob with vnum {vnum} already exists.",
    "mobs.in_reset_usage": "Cannot delete: the mob is referenced by {count} reset commands ({zones}). Update or remove them first.",
    "mobs.vnum_in_use": "Cannot change the vnum: the mob is referenced by {count} reset commands ({zones}).",
    "mobs.has_instances": "Cannot delete: {count} live instances of the mob exist.",
}
