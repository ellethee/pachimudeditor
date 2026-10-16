"""Messages of transfer in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "transfer.zone_not_found": "Zone not found",
    "transfer.no_files": "No file uploaded.",
    "transfer.unsupported_file": "File «{file}» not recognised: expected a zip or zone.yaml, rooms.yaml, mobs.yaml, objects.yaml, resets.yaml.",
    "transfer.invalid_archive": "«{file}» is not a valid zip.",
    "transfer.file_too_large": "«{file}» exceeds the {max_mb} MB limit.",
    "transfer.zone_missing": "The upload has no zone.yaml.",
    "transfer.multiple_zones": "The upload contains {count} zones: import one at a time.",
    "transfer.invalid_file": "Invalid file «{file}»: {detail}",
    "transfer.confirm_required": "A real import needs dryRun=false and confirm=true.",
    "transfer.vnum_conflict": "Import blocked: {count} vnums belong to other zones ({vnums}).",
}
