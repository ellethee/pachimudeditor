"""Esportazione e importazione di una zona come cartella di file YAML (il formato del gioco).

- **Export**: i file della cartella di zona cosi' come sono su disco (commenti inclusi).
- **Import**: una cartella con `zone.yaml` e i file `room*/mob*/obj*/reset*.yaml`. Anteprima per vnum (create/update/
  unchanged), conflitti con altre zone, avvisi di coerenza; applicazione: se la zona (per vnum) esiste si fa l'upsert delle
  voci nei suoi file e si sostituiscono i reset (mai cancellazioni di stanze/mob/oggetti); se non esiste si copiano i file cosi'
  come sono in una nuova cartella.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pydantic import ValidationError
from ruamel.yaml.comments import CommentedMap

from pachimudeditor.common.adapters.models import (
    Conflict,
    ImportPreview,
    ImportWarning,
    KindDiff,
    ResetCommandIn,
    ResetDiff,
    VnumChange,
    ZoneBundle,
)
from pachimudeditor.common.enums import Direction
from pachimudeditor.sdk import atomic_write_bytes
from pachimudeditor_adapter_pachimud import mapping, resets
from pachimudeditor_adapter_pachimud.loaders import LoaderResetFile, LoaderZone, validate_entry
from pachimudeditor_adapter_pachimud.store import (
    FILE_PREFIXES,
    LIST_KEY,
    PREFIX,
    STEMS,
    Kind,
    YamlStore,
    ZoneEntry,
    area_of_filename,
    new_yaml,
    plain,
)


MAX_RECORDS = 5000
"""Voci massime per file caricato (oltre: 422 `transfer.invalid_file`)."""


@dataclass
class ParsedEntry:
    """Una voce del file caricato: modello validato, mapping ruamel originale e area del file."""

    model: Any
    raw: CommentedMap
    area: str | None


@dataclass
class ParsedZone:
    """Il contenuto validato di una cartella di zona caricata."""

    zone: LoaderZone
    files: dict[str, bytes] = field(default_factory=dict)
    """Nome file -> byte (solo i file riconosciuti)."""
    entries: dict[Kind, list[ParsedEntry]] = field(default_factory=lambda: {"room": [], "mob": [], "object": []})
    resets: list[LoaderResetFile] = field(default_factory=list)
    zone_doc: CommentedMap | None = None


def bundle(store: YamlStore, zone: ZoneEntry) -> ZoneBundle:
    """I file YAML della zona come testo, con i problemi di lettura che li riguardano."""
    files = {f.path.relative_to(zone.dir).as_posix(): f.path.read_text(encoding="utf-8") for f in [zone.file, *zone.files]}
    prefix = str(zone.dir.relative_to(store.definitions))
    warnings = [i.text() for i in store.issues if i.path.startswith(prefix + "/")]
    return ZoneBundle(zone_vnum=zone.vnum, zone_name=zone.model.name, folder=zone.dir.name, files=files, warnings=warnings)


def _kind_of(name: str) -> str | None:
    """`zone`, `rooms`, `mobs`, `objects`, `resets` per un nome di file riconosciuto (`.yml` ammesso)."""
    if name == "zone.yaml":
        return "zone"
    return next((kind for prefix, kind in FILE_PREFIXES if name.startswith(prefix) and name.endswith(".yaml")), None)


def _invalid(name: str, detail: str) -> Exception:
    """422 `transfer.invalid_file`."""
    return api_error(422, "transfer.invalid_file", file=name, detail=detail)


def parse_zone_dir(directory: Path) -> ParsedZone:
    """Legge e valida i file della cartella (422 `transfer.invalid_file` al primo file non valido, `transfer.zone_missing`)."""
    zone_path = directory / "zone.yaml"
    if not zone_path.is_file():
        raise api_error(422, "transfer.zone_missing")
    parsed: ParsedZone | None = None
    for path in [zone_path, *sorted(p for p in directory.iterdir() if p.is_file() and p != zone_path)]:
        kind = _kind_of(path.name)
        if kind is None:
            continue
        data = path.read_bytes()
        try:
            doc = new_yaml().load(data.decode("utf-8")) or CommentedMap()
            if not isinstance(doc, CommentedMap):
                raise ValueError("il file non contiene una mappa YAML")
            if kind == "zone":
                parsed = ParsedZone(zone=LoaderZone.model_validate(plain(doc)), zone_doc=doc)
            elif kind == "resets":
                assert parsed is not None
                parsed.resets.append(LoaderResetFile.model_validate(plain(doc)))
            else:
                assert parsed is not None
                entity: Kind = {"rooms": "room", "mobs": "mob", "objects": "object"}[kind]  # type: ignore[assignment]
                area = next((a for stem in STEMS[kind] if (a := area_of_filename(path.name, stem))), None)
                records = doc.get(LIST_KEY[kind]) or []
                if len(records) > MAX_RECORDS:
                    raise ValueError(f"troppe voci ({len(records)}, massimo {MAX_RECORDS})")
                for raw in records:
                    parsed.entries[entity].append(ParsedEntry(validate_entry(PREFIX[entity], plain(raw)), raw, area))
        except ValidationError as error:
            raise _invalid(path.name, _short(error)) from error
        except (ValueError, UnicodeDecodeError) as error:
            raise _invalid(path.name, str(error).splitlines()[0][:200]) from error
        except Exception as error:  # noqa: BLE001 - YAML malformato: errore chiaro sul file, mai un 500
            raise _invalid(path.name, str(error).splitlines()[0][:200] if str(error) else type(error).__name__) from error
        assert parsed is not None
        parsed.files[path.name] = data
    assert parsed is not None
    return parsed


def _short(error: ValidationError) -> str:
    """Il primo errore di validazione come `campo: messaggio`."""
    first = error.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])


def _norm(model: Any) -> dict[str, Any]:
    """La voce normalizzata per il confronto (senza l'etichetta `area`)."""
    return model.model_dump(mode="json", exclude={"area"})  # type: ignore[no-any-return]


def _classify(store: YamlStore, kind: Kind, entries: list[ParsedEntry], zone: ZoneEntry | None, conflicts: list[Conflict]) -> KindDiff:
    """Confronta le voci del file con quelle del mondo (per vnum)."""
    diff = KindDiff()
    seen: set[int] = set()
    for entry in entries:
        vnum = entry.model.vnum
        seen.add(vnum)
        name = entry.model.name if kind == "room" else entry.model.short_description
        existing = store.find(kind, vnum)
        if existing is None:
            action = "create"
            diff.create += 1
        else:
            if zone is None or existing.zone is not zone:
                conflicts.append(Conflict(kind=kind, vnum=vnum, zone_vnum=existing.zone.vnum, zone_name=existing.zone.model.name))
            same = _norm(existing.model) == _norm(entry.model)
            action = "unchanged" if same else "update"
            diff.unchanged += same
            diff.update += not same
        diff.items.append(VnumChange(vnum=vnum, name=str(name), action=action))
    if zone is not None:
        diff.kept_not_in_file = sorted({i.vnum for i in zone.items[kind]} - seen)
    return diff


def preview(store: YamlStore, parsed: ParsedZone, race_ids: set[str] | None, class_ids: set[str] | None) -> ImportPreview:
    """Confronta i file validati con il mondo, senza scrivere. Vedi `ImportPreview`."""
    zdata = parsed.zone
    zone = store.zone(zdata.vnum)
    if zone is None:
        zone_change = VnumChange(vnum=zdata.vnum, name=zdata.name, action="create")
    else:
        same = zone.model.model_dump(mode="json") == zdata.model_dump(mode="json")
        zone_change = VnumChange(vnum=zdata.vnum, name=zdata.name, action="unchanged" if same else "update")
    conflicts: list[Conflict] = []
    diffs = {k: _classify(store, k, parsed.entries[k], zone, conflicts) for k in ("room", "mob", "object")}
    new_script = resets.flatten_files(parsed.resets)
    old_script = resets.flatten(zone) if zone is not None else []
    resets_diff = ResetDiff(in_file=len(new_script), in_db=len(old_script), changed=_norm_script(new_script) != _norm_script(old_script))
    return ImportPreview(
        zone=zone_change,
        rooms=diffs["room"],
        mobs=diffs["mob"],
        objects=diffs["object"],
        resets=resets_diff,
        warnings=_warnings(store, parsed, new_script, race_ids, class_ids),
        conflicts=conflicts,
    )


def _norm_script(commands: list[Any]) -> list[Any]:
    """Comandi confrontabili."""
    from pachimudeditor_adapter_pachimud.zones import _normalized

    return _normalized(commands)


def _warnings(
    store: YamlStore, parsed: ParsedZone, script: list[Any], race_ids: set[str] | None, class_ids: set[str] | None
) -> list[ImportWarning]:
    """Incongruenze non bloccanti: range, riferimenti inesistenti, razze/classi sconosciute, range sovrapposto."""
    z = parsed.zone
    mine = {k: {e.model.vnum for e in parsed.entries[k]} for k in ("room", "mob", "object")}
    known = {k: mine[k] | store.vnums(k) for k in mine}
    out: list[ImportWarning] = []
    for kind, vnums in mine.items():
        out += [
            ImportWarning(code="out_of_range", params={"kind": kind, "vnum": v})
            for v in sorted(vnums)
            if not z.bottom_vnum <= v <= z.top_vnum
        ]
    if z.bottom_vnum > z.top_vnum:
        out.append(ImportWarning(code="invalid_range", params={"bottom": z.bottom_vnum, "top": z.top_vnum}))
    for room in (e.model for e in parsed.entries["room"]):
        for key, ex in room.exits.items():
            direction = Direction[key.upper()].name.lower()
            if ex.target_vnum is not None and ex.target_vnum not in known["room"]:
                out.append(
                    ImportWarning(code="dangling_exit", params={"room": room.vnum, "direction": direction, "target": ex.target_vnum})
                )
            if ex.key_vnum is not None and ex.key_vnum not in known["object"]:
                out.append(ImportWarning(code="unknown_key", params={"room": room.vnum, "direction": direction, "vnum": ex.key_vnum}))
    from pachimudeditor.common.enums import ZoneCommandType as T

    for index, (t, a1, _a2, a3, _a4, _s) in enumerate(script):
        refs = {T.LOAD_MOB: [("mob", a1), ("room", a3)], T.LOAD_OBJECT: [("object", a1), ("room", a3)], T.PUT_OBJECT: [("object", a1), ("object", a3)],
                T.GIVE_OBJECT: [("object", a1)], T.EQUIP_OBJECT: [("object", a1)], T.SET_DOOR_STATE: [("room", a1)]}.get(t, [])  # fmt: skip
        out += [
            ImportWarning(code="unknown_reset_ref", params={"index": index, "kind": kind, "vnum": vnum})
            for kind, vnum in refs
            if vnum is not None and vnum not in known[kind]
        ]
    for mob in (e.model for e in parsed.entries["mob"]):
        if race_ids is not None and mob.race_id is not None and mob.race_id not in race_ids:
            out.append(ImportWarning(code="unknown_race", params={"mob": mob.vnum, "id": mob.race_id}))
        if class_ids is not None and mob.class_id is not None and mob.class_id not in class_ids:
            out.append(ImportWarning(code="unknown_class", params={"mob": mob.vnum, "id": mob.class_id}))
    for other in store.zones:
        if other.vnum != z.vnum and z.bottom_vnum <= other.model.top_vnum and other.model.bottom_vnum <= z.top_vnum:
            out.append(ImportWarning(code="range_overlap", params={"zone": other.model.name, "zone_vnum": other.vnum}))
    return out


def apply(store: YamlStore, parsed: ParsedZone) -> None:
    """Applica l'import (il chiamante ha gia' escluso i conflitti ed ha il lock di scrittura)."""
    zone = store.zone(parsed.zone.vnum)
    if zone is None:
        from pachimudeditor_adapter_pachimud.zones import slug

        folder = store.free_folder(slug(parsed.zone.name) or f"Zona{parsed.zone.vnum}")
        target = store.safe_folder(folder)
        target.mkdir(parents=True)
        for name, data in parsed.files.items():
            atomic_write_bytes(target / name, data)
        store.invalidate()
        return
    touched = set()
    if zone.model.model_dump(mode="json") != parsed.zone.model_dump(mode="json"):
        for key, value in parsed.zone.model_dump(mode="json").items():
            mapping.put(zone.file.doc, key, value, required=True)
        zone.revalidate()
        touched.add(zone.file)
    for kind in ("room", "mob", "object"):
        for entry in parsed.entries[kind]:  # type: ignore[index]
            item = store.find(kind, entry.model.vnum)  # type: ignore[arg-type]
            if item is None:
                file = store.file_for(zone, kind, entry.area)  # type: ignore[arg-type]
                file.list_of(create=True).append(entry.raw)
                touched.add(file)
            elif _norm(item.model) != _norm(entry.model):
                new = plain(entry.raw)
                for key in [k for k in item.raw if k not in new]:
                    del item.raw[key]
                for key, value in new.items():
                    mapping.put(item.raw, key, value, required=True)
                touched.add(item.file)
    new_script = resets.flatten_files(parsed.resets)
    store.save(*touched) if touched else None
    if _norm_script(new_script) != _norm_script(resets.flatten(zone)):
        zone = store.zone(zone.vnum)  # type: ignore[assignment]
        resets.write(
            store,
            zone,
            [ResetCommandIn(command_type=t, arg1=a1, arg2=a2, arg3=a3, arg4=a4, arg_str=s) for t, a1, a2, a3, a4, s in new_script],
        )
