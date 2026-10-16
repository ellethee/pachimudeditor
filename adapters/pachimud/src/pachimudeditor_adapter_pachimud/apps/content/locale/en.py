"""Messages of content in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "content.not_found": "Content «{id}» not found.",
    "content.invalid_id": "Invalid id «{id}»: use only lowercase letters, digits and underscores (max 64 characters).",
    "content.id_taken": "A content item with id «{id}» already exists.",
    "content.id_mismatch": "The body id («{body_id}») differs from the path id («{id}»): the id cannot be changed.",
    "content.invalid": "Invalid content: {detail}",
    "content.race_in_use": "Cannot delete race «{id}»: it is used by {count} mob prototypes. Change their race first or disable it.",
    "content.class_in_use": "Cannot delete class «{id}»: it is used by {count} mob prototypes. Change their class first or disable it.",
}
