"""Messages of players in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "players.account_not_found": "Account not found",
    "players.username_taken": 'An account with username "{username}" already exists.',
    "players.email_taken": 'An account with email "{email}" already exists.',
    "players.account_has_characters": "Cannot delete: the account has {count} characters. Delete them first or use cascade delete.",
    "players.character_not_found": "Character not found",
    "players.name_taken": 'A character named "{name}" already exists.',
    "players.invalid_account": "Account {id} does not exist.",
    "players.invalid_room": "Room {id} does not exist.",
    "players.invalid_class": 'Class "{id}" does not exist in the definitions.',
    "players.invalid_race": 'Race "{id}" does not exist in the definitions.',
    "players.character_has_items": "Cannot delete: the character owns {count} items. Empty the inventory or use cascade delete.",
    "players.item_not_found": "Item not in the character's inventory",
    "players.invalid_prototype": "Object prototype not found.",
    "players.prototype_required": "Provide prototypeId or vnum.",
    "players.item_in_container": "The item is inside a container: it cannot be equipped.",
}
