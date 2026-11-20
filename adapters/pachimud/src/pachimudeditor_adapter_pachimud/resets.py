"""Script di reset: dai file `resets*.yaml` (strutturati) ai comandi piatti dell'editor e ritorno.

Il gioco descrive i reset come strutture annidate (`objects` a terra con `contains`, `mobs` con `inventory`, `doors`);
l'editor li mostra come lo script ROM M/O/G/E/P/D (l'ordine e' la posizione, `id == orderIndex`):

- oggetto a terra -> `O` (arg1 oggetto, arg2 massimo, arg3 stanza, arg4 massimo per stanza) e, per ogni contenuto, `P`
  (arg1 oggetto, arg2 massimo, arg3 vnum del contenitore);
- mob -> `M` (arg1 mob, arg2 massimo, arg3 stanza, arg4 massimo per stanza) e, per ogni oggetto dell'inventario, `G`
  (senza `wear_slot`) o `E` (`argStr` = `wear_slot`) con i suoi `P`;
- porta -> `D` (arg1 stanza, arg2 direzione, `argStr` = stato).

L'ordine di emissione e' sempre oggetti, mob, porte (come li esegue il gioco). Il percorso inverso (`build`) ricostruisce
la struttura: un `G`/`E` appartiene all'ultimo `M`, un `P` all'ultimo oggetto con il vnum del contenitore emesso dopo
l'ultimo `M`/`O`; `R` (rimescola le uscite) non esiste nel gioco.
"""

from typing import Any

from ruamel.yaml.comments import CommentedMap

from pachifast.i18n import api_error

from pachimudeditor.common.adapters.models import ResetCommandIn, ResetCommandOut
from pachimudeditor.common.enums import Direction, ZoneCommandType
from pachimudeditor_adapter_pachimud.loaders import LoaderResetContent, LoaderResetFile
from pachimudeditor_adapter_pachimud.store import YamlStore, ZoneEntry

Tuple = tuple[ZoneCommandType, int | None, int | None, int | None, int | None, str | None]
"""`(tipo, arg1, arg2, arg3, arg4, arg_str)`: la forma confrontabile di un comando."""


def _contents(items: list[LoaderResetContent], parent: int) -> list[Tuple]:
    """I `P` dei contenuti di un oggetto (ricorsivi)."""
    out: list[Tuple] = []
    for item in items:
        out.append((ZoneCommandType.PUT_OBJECT, item.obj_vnum, item.max_existing, parent, None, None))
        out += _contents(item.contains, item.obj_vnum)
    return out


def flatten(zone: ZoneEntry) -> list[Tuple]:
    """Lo script piatto della zona (tutti i `resets*.yaml` leggibili, in ordine di percorso)."""
    return flatten_files([f.resets for f in zone.of_kind("resets") if f.resets is not None])


def flatten_files(files: list[LoaderResetFile]) -> list[Tuple]:
    """Lo script piatto di una serie di file di reset gia' validati."""
    out: list[Tuple] = []
    for file in files:
        r = file.resets
        for o in r.objects:
            out.append((ZoneCommandType.LOAD_OBJECT, o.obj_vnum, o.max_existing, o.room_vnum, o.room_limit, None))
            out += _contents(o.contains, o.obj_vnum)
        for m in r.mobs:
            out.append((ZoneCommandType.LOAD_MOB, m.mob_vnum, m.max_existing, m.room_vnum, m.room_limit, None))
            for i in m.inventory:
                kind = ZoneCommandType.EQUIP_OBJECT if i.wear_slot else ZoneCommandType.GIVE_OBJECT
                out.append((kind, i.obj_vnum, i.max_existing, None, None, i.wear_slot or None))
                out += _contents(i.contains, i.obj_vnum)
        for d in r.doors:
            direction = int(Direction[d.direction.upper()]) if d.direction.upper() in Direction.__members__ else 0
            out.append((ZoneCommandType.SET_DOOR_STATE, d.room_vnum, direction, None, None, d.state.upper()))
    return out


def to_out(zone_vnum: int, commands: list[Tuple]) -> list[ResetCommandOut]:
    """I comandi come DTO (`id == orderIndex`)."""
    return [
        ResetCommandOut(
            id=i, zone_id=zone_vnum, order_index=i, command_type=t, if_flag=False, arg1=a1, arg2=a2, arg3=a3, arg4=a4, arg_str=s
        )
        for i, (t, a1, a2, a3, a4, s) in enumerate(commands)
    ]


def _content(arg1: int, arg2: int | None) -> dict[str, Any]:
    """Un oggetto senza stanza (`max_existing` assente = nessun limite)."""
    return {"obj_vnum": arg1, **({} if arg2 is None else {"max_existing": arg2})}


def build(commands: list[ResetCommandIn]) -> dict[str, list[dict[str, Any]]]:
    """Ricostruisce `{objects, mobs, doors}` dallo script piatto.

    Raises:
        HTTPException: 422 `pachimud.reset_unsupported` (comando che il gioco non ha) o `pachimud.reset_orphan` (`G`/`E`/`P`
            senza il mob o il contenitore a cui appartengono).
    """
    objects: list[dict[str, Any]] = []
    mobs: list[dict[str, Any]] = []
    doors: list[dict[str, Any]] = []
    mob: dict[str, Any] | None = None
    placed: list[dict[str, Any]] = []  # oggetti del blocco corrente (O o inventario del mob) che possono contenere altro
    for index, c in enumerate(commands):
        t, loc = c.command_type, ("body", "commands", index)
        a1, a2, a3, a4 = c.arg1, c.arg2, c.arg3, c.arg4
        if t is ZoneCommandType.LOAD_OBJECT:
            entry = {**_content(a1, a2), "room_vnum": a3, "room_limit": 1 if a4 is None else a4, "contains": []}  # type: ignore[arg-type]
            objects.append(entry)
            mob, placed = None, [entry]
        elif t is ZoneCommandType.LOAD_MOB:
            mob = {
                "mob_vnum": a1,
                "max_existing": 1 if a2 is None else a2,
                "room_vnum": a3,
                "room_limit": 1 if a4 is None else a4,
                "inventory": [],
            }
            mobs.append(mob)
            placed = []
        elif t in (ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT):
            if mob is None:
                raise api_error(422, "pachimud.reset_orphan", loc=loc, index=index)
            entry = {**_content(a1, a2), "contains": []}  # type: ignore[arg-type]
            if t is ZoneCommandType.EQUIP_OBJECT:
                entry["wear_slot"] = (c.arg_str or "").strip()
            mob["inventory"].append(entry)
            placed.append(entry)
        elif t is ZoneCommandType.PUT_OBJECT:
            parent = next((p for p in reversed(placed) if p["obj_vnum"] == a3), None)
            if parent is None:
                raise api_error(422, "pachimud.reset_orphan", loc=loc, index=index)
            entry = {**_content(a1, a2), "contains": []}  # type: ignore[arg-type]
            parent["contains"].append(entry)
            placed.append(entry)
        elif t is ZoneCommandType.SET_DOOR_STATE:
            doors.append({"room_vnum": a1, "direction": Direction(a2).name, "state": (c.arg_str or "OPEN").upper()})  # type: ignore[arg-type]
        else:
            raise api_error(422, "pachimud.reset_unsupported", loc=loc, index=index)
    return {"objects": _prune(objects), "mobs": _prune(mobs), "doors": doors}


def _prune(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Toglie le liste `contains`/`inventory` vuote (nel file sono omesse)."""
    for entry in entries:
        for key in ("contains", "inventory"):
            if key in entry:
                if entry[key]:
                    _prune(entry[key])
                else:
                    del entry[key]
    return entries


def commented(value: Any) -> Any:
    """Dict/list annidati -> `CommentedMap`/liste (cosi' ruamel li scrive in stile blocco)."""
    if isinstance(value, dict):
        node = CommentedMap()
        for k, v in value.items():
            node[k] = commented(v)
        return node
    if isinstance(value, list):
        return [commented(v) for v in value]
    return value


def write(store: YamlStore, zone: ZoneEntry, commands: list[ResetCommandIn]) -> None:
    """Riscrive lo script della zona in `resets.yaml`, svuotando gli altri file di reset (i commenti non si conservano).

    Raises:
        HTTPException: 409 `pachimud.file_broken` se un file di reset non e' leggibile (non si sovrascrive cio' che non si
            e' potuto leggere); 422 se lo script non e' esprimibile (vedi `build`).
    """
    broken = [f for f in zone.of_kind("resets") if f.doc is None or f.resets is None]
    if broken:
        raise api_error(409, "pachimud.file_broken", file=broken[0].path.name)
    built = build(commands)
    files = zone.of_kind("resets")
    primary = next((f for f in files if f.path.name == "resets.yaml"), None) or store.new_file(zone, "resets", None)
    touched = [primary]
    for file in files:
        current = file.doc.get("resets") if file.doc is not None else None
        if file is not primary and isinstance(current, dict) and any(current.get(k) for k in ("objects", "mobs", "doors")):
            touched.append(file)
    for file in touched:
        assert file.doc is not None
        node = CommentedMap()
        for key in ("objects", "mobs", "doors"):
            if file is primary and built[key]:
                node[key] = [commented(e) for e in built[key]]
        file.doc["resets"] = node
    store.save(*touched)
