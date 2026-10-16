"""Messages dell'adapter pachimud in en: codice stabile -> testo."""

MESSAGES: dict[str, str] = {
    "world.not_pachimud": 'This feature needs a pachimud world (the selected world is "{kind}").',
    "world.unavailable": "The world database is not usable: {detail}",
    "world.field_unsupported": 'The field "{field}" does not exist in this world\'s database schema: only the neutral value is accepted.',
    "common.editor.in_use": "Cannot delete: the item is still used by other data.",
    "common.editor.invalid_reference": "Invalid reference: the linked item does not exist.",
    "common.editor.duplicate": "An item with the same unique values already exists.",
    "common.editor.constraint_violation": "Operation not allowed by the database constraints.",
}
