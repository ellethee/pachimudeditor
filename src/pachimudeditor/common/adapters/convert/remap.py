"""Rimappatura dei vnum: tabella `vnum sorgente -> vnum di arrivo` e riferimenti dentro i comandi di reset.

I comandi di reset contengono vnum in argomenti diversi a seconda del tipo (vedi `common.adapters.rules`):
`reset_refs` dice quali e di che tipo, `remap_reset` li sostituisce con un `resolve` fornito dal motore (che puo'
rispondere "mancante").
"""

from collections.abc import Callable

from pachimudeditor.common.enums import ZoneCommandType

from pachimudeditor.common.adapters import rules
from pachimudeditor.common.adapters.models import EntityKind, ResetCommandIn

RESET_REFS: dict[int, tuple[tuple[str, EntityKind], ...]] = {
    int(ZoneCommandType.LOAD_MOB): (("arg1", "mob"), ("arg3", "room")),
    int(ZoneCommandType.LOAD_OBJECT): (("arg1", "object"), ("arg3", "room")),
    int(ZoneCommandType.GIVE_OBJECT): (("arg1", "object"),),
    int(ZoneCommandType.EQUIP_OBJECT): (("arg1", "object"),),
    int(ZoneCommandType.PUT_OBJECT): (("arg1", "object"), ("arg3", "object")),
    int(ZoneCommandType.SET_DOOR_STATE): (("arg1", "room"),),
    int(ZoneCommandType.RANDOMIZE_EXITS): (("arg1", "room"),),
    rules.CHARM_MOB: (("arg1", "mob"),),
}
"""Per tipo di comando: (argomento, tipo di entita') che contengono un vnum. `H`/`F` (arg2 se arg1 == 7) sono a parte."""

LOADS_MOB = frozenset({int(ZoneCommandType.LOAD_MOB), rules.CHARM_MOB})
"""Comandi che caricano un mob: i successivi G/E/H/F/Z agiscono su di lui."""
ACTS_ON_LAST_MOB = frozenset(
    {int(ZoneCommandType.GIVE_OBJECT), int(ZoneCommandType.EQUIP_OBJECT), rules.SET_HATE, rules.SET_FEAR, rules.SET_MOB_ZONE}
)


def reset_refs(command: ResetCommandIn) -> list[tuple[str, EntityKind]]:
    """I riferimenti a vnum del comando: lista di `(nome argomento, tipo)`."""
    kind = int(command.command_type)
    refs = list(RESET_REFS.get(kind, ()))
    if kind in (rules.SET_HATE, rules.SET_FEAR) and command.arg1 == rules.HATE_FEAR_MOB_TYPE:
        refs.append(("arg2", "mob"))
    return refs


def remap_reset(
    command: ResetCommandIn, resolve: Callable[[EntityKind, int], int | None]
) -> tuple[ResetCommandIn | None, list[tuple[str, EntityKind, int]]]:
    """`(comando rimappato, riferimenti mancanti)`: se un riferimento non si risolve il comando e' `None`."""
    changes: dict[str, int] = {}
    missing: list[tuple[str, EntityKind, int]] = []
    for arg, kind in reset_refs(command):
        value = getattr(command, arg)
        if value is None:
            continue
        new = resolve(kind, value)
        if new is None:
            missing.append((arg, kind, value))
        else:
            changes[arg] = new
    if missing:
        return None, missing
    return command.model_copy(update=changes), []
