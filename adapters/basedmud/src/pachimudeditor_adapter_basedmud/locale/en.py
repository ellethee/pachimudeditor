"""Messages of the BasedMud adapter in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "basedmud.unsafe_text": "Text cannot be written to ROM area files: {reason}.",
    "basedmud.unencodable_text": "Text contains characters the area file encoding cannot represent: {reason}.",
    "basedmud.unknown_flag": 'Unknown flag "{name}" in table {table}.',
    "basedmud.extra_unknown": 'Unknown extra key "{key}" (known: {known}).',
    "basedmud.extra_invalid": 'Invalid value for extra "{key}".',
    "basedmud.extra_readonly": 'Extra key "{key}" is read-only.',
    "basedmud.field_unsupported": 'The field "{field}" does not exist in ROM: only the neutral value is accepted.',
    "basedmud.invalid_file_name": 'Invalid area file name: "{name}" (letters, digits, "_", "-", "." and the .are suffix only).',
    "basedmud.file_exists": 'The file "{name}" already exists.',
    "basedmud.vnum_out_of_range": "Vnum {vnum} is outside the zone range ({bottom}-{top}).",
    "basedmud.zone_vnum_is_range": "A BasedMud zone vnum is its lowest vnum: change bottomVnum instead (requested {vnum}).",
    "basedmud.reset_invalid_slot": 'Command {loc}: unknown equipment slot "{slot}".',
}
