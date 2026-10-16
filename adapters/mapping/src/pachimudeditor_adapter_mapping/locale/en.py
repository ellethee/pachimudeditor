"""Messages of the Mapping adapter in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "mapping.unknown_flag": 'Unknown flag "{name}" in table {table}.',
    "mapping.unknown_name": 'Unknown name "{name}" in table {table}.',
    "mapping.extra_unknown": 'Unknown extra key "{key}" (known: {known}).',
    "mapping.extra_invalid": 'Invalid value for extra "{key}".',
    "mapping.extra_readonly": 'Extra key "{key}" is read-only.',
    "mapping.field_unsupported": 'The field "{field}" does not exist in this MUD: only the neutral value is accepted.',
    "mapping.field_readonly": 'The field "{field}" is read-only in this mapping.',
    "mapping.unsupported_value": 'The value "{value}" of field "{field}" cannot be represented in this MUD.',
    "mapping.invalid_file_name": 'Invalid file name: "{name}" (no separators, must match {pattern}).',
    "mapping.file_exists": 'The file "{name}" already exists.',
    "mapping.vnum_out_of_range": "Vnum {vnum} is outside the zone range ({bottom}-{top}).",
    "mapping.zone_vnum_is_range": "A zone vnum is one end of its range: change the range instead (requested {vnum}).",
    "mapping.zone_top_not_last": "With this layout a new zone goes last: topVnum {top} must exceed the last one ({last}).",
    "mapping.zone_bottom_derived": "A zone's bottom vnum is derived from the previous zone: it must be {bottom}.",
    "mapping.zone_top_order": "The top vnum {top} would overlap the previous or next zone.",
    "mapping.zone_range_has_items": "The new top vnum {top} would move rooms, mobs or objects into another zone.",
    "mapping.clone_unsupported": "This layout does not support zone cloning.",
    "mapping.unknown_style": 'Unknown zone header style "{style}".',
    "mapping.reset_type_unsupported": "This MUD has no reset command {type}.",
    "mapping.reset_unmapped_commands": "The zone has {count} reset commands the mapping does not know: replacing the script would delete them.",
    "mapping.no_file_for": 'No data file can hold records of type "{entity}".',
}
"""Messaggi dell'adapter Mapping: codice stabile -> testo."""
