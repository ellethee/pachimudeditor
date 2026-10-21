"""Messages of worldplayers in en: stable code -> text."""

MESSAGES: dict[str, str] = {
    "worldplayers.not_found": "Player not found.",
    "worldplayers.server_running": "The game server seems to be running: the change must be explicitly confirmed (the game may overwrite the file).",
    "worldplayers.conflict": "The player file changed after it was read: reload and try again.",
    "worldplayers.invalid_value": 'Invalid value for "{field}" ({reason}).',
    "worldplayers.file_unwritable": "The player file cannot be edited ({problem}).",
    "worldplayers.unknown_object": "Object {vnum} does not exist in the world.",
    "worldplayers.item_not_found": "Inventory item not found.",
    "worldplayers.item_invalid": "Invalid inventory operation ({reason}).",
}
