"""Plugin degli adapter: scoperta tramite entry point e caricamento lazy.

Un adapter e' un pacchetto Python a se' (`pachimudeditor-adapter-<kind>`) che dichiara nel proprio `pyproject.toml`::

    [project.entry-points."pachimudeditor.adapters"]
    dikumod = "pachimudeditor_adapter_dikumod.plugin:plugin"

e un oggetto `AdapterPlugin` (vedi sotto) in quel modulo. Il core NON importa mai gli adapter: li trova con
`importlib.metadata.entry_points`, importa solo il modulo `plugin` (che deve essere leggero: solo l'`AdapterPlugin`
con stringhe `"modulo:attributo"`) e carica factory, moduli API e regole di conversione al primo uso, cioe' solo per i
`kind` di cui esiste un mondo configurato. Un plugin che non si importa non fa cadere il core: resta nell'elenco con
l'errore, il suo `kind` non e' disponibile.
"""

import logging
from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import EntryPoint, PackageNotFoundError, entry_points, version
from typing import Any

log = logging.getLogger(__name__)

SDK_VERSION = "1.0"
"""Versione dell'API pubblica per gli adapter (`pachimudeditor.sdk.SDK_VERSION`): minor per le aggiunte, major per le rotture."""

ENTRY_POINT_GROUP = "pachimudeditor.adapters"
"""Gruppo di entry point in cui gli adapter si dichiarano."""

KNOWN_KINDS: dict[str, str] = {
    "pachimud": "il database del gioco pachimud (SQLAlchemy)",
    "basedmud": "basedmud / ROM (file .are)",
    "dikumod": "Diku Modificato (file dati Diku)",
    "mapping": "qualunque MUD descritto da un YAML di mappatura",
}
"""Gli adapter ufficiali (kind -> descrizione): il pacchetto e' `pachimudeditor-adapter-<kind>`, l'extra `<kind>`."""


@dataclass(frozen=True)
class AdapterPlugin:
    """Cio' che un pacchetto adapter offre al core. Tutti i riferimenti sono stringhe `"pacchetto.modulo:attributo"`,
    importate solo quando servono (un `kind` non configurato non importa nulla di pesante)."""

    kind: str
    """Il `kind` dei mondi (`kind:` in `webeditor_worlds`); deve coincidere col nome dell'entry point."""
    description: str
    """Una riga per `pachimudeditor adapters list`."""
    factory: str
    """`callable(WorldConfig) -> WorldAdapter` (di solito la classe dell'adapter)."""
    modules: tuple[str, ...] = ()
    """`AppModule` pachifast (API/locale) da registrare SOLO se esiste un mondo di questo kind."""
    flavor: str | None = None
    """Regole di conversione: un `Flavor` (classe o istanza) che traduce questo mondo da/verso il pivot; il core compone
    le coppie con i sapori degli altri adapter installati (vedi `common.adapters.convert.flavor`)."""
    validate: str | None = None
    """`callable(WorldConfig) -> None` che alza `ValueError` (messaggio per l'utente) se i parametri del mondo sono
    inutilizzabili: eseguito all'avvio, prima di servire."""
    example: str = ""
    """Esempio commentato di mondo per il `pachimudeditor.yaml` generato da `init` (righe che iniziano con `# `)."""
    sdk_version: str | None = None
    """`SDK_VERSION` con cui l'adapter e' stato scritto. Il core rifiuta il plugin se la major e' diversa da quella del core
    (minor diversa: compatibile). `None` = non dichiarata (adapter datati): nessun controllo."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Riservato (metadati liberi, ignorati dal core)."""


@dataclass
class PluginRecord:
    """Un entry point scoperto: il plugin se si e' importato, altrimenti l'errore."""

    name: str
    distribution: str | None
    plugin: AdapterPlugin | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """`True` se il plugin e' utilizzabile."""
        return self.plugin is not None


class AdapterUnavailable(ValueError):
    """Un `kind` non e' utilizzabile (non installato o plugin rotto): il messaggio dice cosa installare."""


_RECORDS: dict[str, PluginRecord] | None = None


def _entry_points() -> list[EntryPoint]:
    """Gli entry point del gruppo (funzione a parte: i test la sostituiscono con entry point sintetici)."""
    return list(entry_points(group=ENTRY_POINT_GROUP))


def import_string(ref: str) -> Any:
    """Importa `"pacchetto.modulo:attributo"` (anche con punti nell'attributo)."""
    module_name, _, attr = ref.partition(":")
    if not attr:
        raise ValueError(f"riferimento non valido {ref!r}: atteso 'modulo:attributo'")
    obj: Any = import_module(module_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def check_sdk_version(plugin: AdapterPlugin) -> None:
    """Alza `ValueError` se la major dell'SDK dichiarata dal plugin non e' quella del core."""
    if plugin.sdk_version is None:
        return
    declared, current = plugin.sdk_version.split(".")[0], SDK_VERSION.split(".")[0]
    if declared != current:
        raise ValueError(
            f"SDK incompatibile: l'adapter e' scritto per SDK {plugin.sdk_version}, il core offre {SDK_VERSION} "
            f"(major diversa): aggiornare l'adapter o il core"
        )


def _load(ep: EntryPoint) -> PluginRecord:
    """Importa l'entry point e controlla che sia un `AdapterPlugin` coerente col suo nome."""
    dist = getattr(getattr(ep, "dist", None), "name", None)
    record = PluginRecord(name=ep.name, distribution=dist)
    try:
        obj = ep.load()
        if callable(obj) and not isinstance(obj, AdapterPlugin):
            obj = obj()
        if not isinstance(obj, AdapterPlugin):
            raise TypeError(f"l'entry point {ep.value!r} non e' un AdapterPlugin (e' {type(obj).__name__})")
        if obj.kind != ep.name:
            raise ValueError(f"il kind del plugin ({obj.kind!r}) non coincide col nome dell'entry point ({ep.name!r})")
        check_sdk_version(obj)
        record.plugin = obj
    except Exception as exc:  # noqa: BLE001 - un plugin rotto non deve far cadere il core
        record.error = f"{type(exc).__name__}: {exc}"
        log.warning("Adapter %r (%s) non utilizzabile: %s", ep.name, dist or ep.value, record.error)
    return record


def discover(refresh: bool = False) -> dict[str, PluginRecord]:
    """Tutti i plugin installati (`kind -> record`), scoperti una sola volta per processo (`refresh` per rifarlo)."""
    global _RECORDS
    if _RECORDS is None or refresh:
        _RECORDS = {}
        for ep in _entry_points():
            if ep.name in _RECORDS:
                log.warning("Adapter %r dichiarato due volte: tengo il primo", ep.name)
                continue
            _RECORDS[ep.name] = _load(ep)
    return _RECORDS


def reset_discovery() -> None:
    """Dimentica la scoperta (test, o dopo aver installato un adapter nello stesso processo)."""
    global _RECORDS
    _RECORDS = None


def install_hint(kind: str) -> str:
    """Come procurarsi l'adapter di `kind`."""
    if kind in KNOWN_KINDS:
        return f"installare l'adapter: pip install 'pachimudeditor[{kind}]' (pacchetto pachimudeditor-adapter-{kind})"
    return "nessun adapter con questo kind e' installato (vedi `pachimudeditor adapters list`)"


def available_kinds() -> list[str]:
    """I `kind` con un plugin utilizzabile."""
    return sorted(k for k, r in discover().items() if r.ok)


def get_plugin(kind: str) -> AdapterPlugin:
    """Il plugin di `kind`.

    Raises:
        AdapterUnavailable: non installato oppure il plugin non si importa (con cosa installare / l'errore).
    """
    record = discover().get(kind)
    if record is None:
        raise AdapterUnavailable(f"kind {kind!r} non disponibile: {install_hint(kind)}")
    if record.plugin is None:
        raise AdapterUnavailable(f"kind {kind!r} non disponibile: il plugin non si carica ({record.error}); reinstallare l'adapter")
    return record.plugin


def load_modules(kinds: "set[str] | frozenset[str] | list[str]") -> list[Any]:
    """I moduli pachifast dei plugin dei `kinds` indicati; quelli non caricabili sono saltati con un avviso."""
    modules: list[Any] = []
    for kind in sorted(set(kinds)):
        record = discover().get(kind)
        if record is None or record.plugin is None:
            continue  # l'errore leggibile lo da' il registro dei mondi
        try:
            modules += [import_string(ref) for ref in record.plugin.modules]
        except Exception as exc:  # noqa: BLE001
            record.error = f"{type(exc).__name__}: {exc}"
            record.plugin = None
            log.warning("Adapter %r: moduli non caricabili, kind non disponibile: %s", kind, record.error)
    return modules


def load_factory(kind: str) -> Any:
    """La factory del plugin di `kind` (importata ora).

    Raises:
        AdapterUnavailable: kind non installato o plugin/factory non importabili.
    """
    plugin = get_plugin(kind)
    try:
        return import_string(plugin.factory)
    except Exception as exc:  # noqa: BLE001
        raise AdapterUnavailable(f"kind {kind!r} non disponibile: factory non importabile ({type(exc).__name__}: {exc})") from exc


def load_flavor(kind: str) -> Any | None:
    """Il `Flavor` (istanza) del plugin di `kind`, o `None` se non c'e' / non si carica (con avviso)."""
    record = discover().get(kind)
    if record is None or record.plugin is None or record.plugin.flavor is None:
        return None
    try:
        flavor = import_string(record.plugin.flavor)
        return flavor() if isinstance(flavor, type) else flavor
    except Exception as exc:  # noqa: BLE001
        log.warning("Adapter %r: regole di conversione non caricabili: %s: %s", kind, type(exc).__name__, exc)
        return None


def validate_world(config: Any) -> None:
    """Esegue la `validate` del plugin per il mondo `config` (se c'e'). Alza `ValueError`."""
    record = discover().get(config.kind)
    if record is not None and record.plugin is not None and record.plugin.validate:
        import_string(record.plugin.validate)(config)


@dataclass(frozen=True)
class KindStatus:
    """Lo stato di un `kind` per `adapters list` / `info` / `worlds`: installato, rotto o noto ma assente."""

    kind: str
    state: str
    """`installed`, `broken` (plugin che non si importa) o `missing` (adapter ufficiale non installato)."""
    package: str
    version: str
    description: str
    hint: str
    """Cosa fare: l'errore del plugin rotto o il comando per installare l'adapter mancante."""


def _dist_version(name: str) -> str:
    """La versione installata di una distribuzione (`-` se sconosciuta)."""
    try:
        return version(name)
    except PackageNotFoundError:
        return "-"


def kind_statuses() -> list[KindStatus]:
    """I kind installati (con eventuale errore) e quelli ufficiali non installati, ordinati per nome."""
    rows: dict[str, KindStatus] = {}
    for kind, record in discover().items():
        package = record.distribution or f"pachimudeditor-adapter-{kind}"
        description = record.plugin.description if record.plugin else KNOWN_KINDS.get(kind, "")
        rows[kind] = KindStatus(
            kind, "installed" if record.ok else "broken", package, _dist_version(package), description, record.error or ""
        )
    for kind, description in KNOWN_KINDS.items():
        if kind not in rows:
            rows[kind] = KindStatus(
                kind, "missing", f"pachimudeditor-adapter-{kind}", "-", description, f"pip install 'pachimudeditor[{kind}]'"
            )
    return [rows[k] for k in sorted(rows)]


def examples_block() -> str:
    """Gli esempi di mondo del `pachimudeditor.yaml` iniziale: quelli dei plugin installati, e una riga per ogni adapter
    ufficiale non installato con il comando per aggiungerlo."""
    parts: list[str] = []
    for status in kind_statuses():
        record = discover().get(status.kind)
        if record is not None and record.plugin is not None and record.plugin.example.strip():
            parts.append(record.plugin.example.rstrip("\n"))
        elif status.state == "missing":
            parts.append(f"# {status.kind}: adapter non installato ({status.description}) -> {status.hint}")
    return "\n".join(parts)
