"""Messages of world in en: stable code -> text.

The code is the contract with the clients; keep the same codes and {fields} in every language
(`pachifast locale check`), and use the module name as the first part of each code.
"""

MESSAGES: dict[str, str] = {
    "world.invalid_types": "Unknown search types: {types}. Use zone, room, mob, object.",
    "world.empty_query": "The search text cannot be empty.",
}
