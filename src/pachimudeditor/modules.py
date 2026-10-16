"""Moduli pachifast dell'editor.

Il core registra solo i moduli generici; i moduli API di un adapter (es. world/players/... del mondo pachimud) li porta
il suo plugin (`AdapterPlugin.modules`) e si registrano SOLO se e' configurato almeno un mondo di quel `kind`.
"""

from collections.abc import Iterable

from pachifast import AppModule
from pachifast.presets import core_module

from pachimudeditor.apps.convert.module import module as convert_module
from pachimudeditor.apps.meta.module import module as meta_module
from pachimudeditor.apps.mobs.module import module as mobs_module
from pachimudeditor.apps.objects.module import module as objects_module
from pachimudeditor.apps.rooms.module import module as rooms_module
from pachimudeditor.apps.zones.module import module as zones_module
from pachimudeditor.common.adapters import plugins
from pachimudeditor.common.adapters.module import module as adapters_module


def build_modules(kinds: Iterable[str] = ()) -> tuple[AppModule, ...]:
    """I moduli da registrare per i `kind` di mondo configurati."""
    modules = [
        core_module,
        adapters_module,
        meta_module,
        zones_module,
        rooms_module,
        mobs_module,
        objects_module,
        convert_module,
    ]
    kinds = set(kinds)
    names = {m.name for m in modules}
    modules += [m for m in plugins.load_modules(kinds) if m.name not in names]
    return tuple(modules)


def configured_modules() -> tuple[AppModule, ...]:
    """I moduli per la configurazione corrente."""
    from pachimudeditor.common.adapters.bootstrap import prepare_worlds

    configs, _ = prepare_worlds()
    return build_modules({c.kind for c in configs})
