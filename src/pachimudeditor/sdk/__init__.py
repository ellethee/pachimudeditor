"""API pubblica per scrivere un adapter esterno (vedi `docs/adapters/index.md`).

Tutto cio' che un pacchetto `pachimudeditor-adapter-*` puo' importare dal core stabilmente sta qui o nei moduli
`pachimudeditor.common.adapters.models` (DTO neutri) e `pachimudeditor.common.enums` (enum dei DTO), anch'essi pubblici.
Il resto del core e' interno e puo' cambiare senza preavviso. Compatibilita': `SDK_VERSION` cresce di minor per le
aggiunte e di major per le rotture; gli adapter dichiarano `pachimudeditor>=X,<Y` nel loro `pyproject.toml`.
"""

from pachimudeditor.common.adapters import rules
from pachimudeditor.common.adapters.base import (
    AdapterCapabilities,
    AdapterInfo,
    ExtraFieldDescriptor,
    FieldDescriptor,
    ResourceInfo,
    ResourceType,
    WorldAdapter,
)
from pachimudeditor.common.adapters.convert import helpers as convert_helpers
from pachimudeditor.common.adapters.convert import tables as convert_tables
from pachimudeditor.common.adapters.convert.converter import (
    ConvertContext,
    Converted,
    PairConverter,
    extra_dropped,
    loss,
    to_in,
)
from pachimudeditor.common.adapters.convert.flavor import ComposedConverter, Flavor
from pachimudeditor.common.adapters.describe import describe_resource, diagnostic, finish_resource, xf
from pachimudeditor.common.adapters.paging import make_page, paginate_list
from pachimudeditor.common.adapters.plugins import ENTRY_POINT_GROUP, SDK_VERSION, AdapterPlugin, AdapterUnavailable
from pachimudeditor.common.adapters.registry import (
    AdapterDep,
    WorldConfig,
    WriteAdapterDep,
    get_registry,
    register_kind,
    require_capability,
)
from pachimudeditor.common.rate_limit import heavy_rate_limit
from pachimudeditor.common.editor.errors import conflict, not_found
from pachimudeditor.common.editor.schemas import PatchModel
from pachimudeditor.sdk.files import atomic_write_bytes

__all__ = [
    "ENTRY_POINT_GROUP",
    "SDK_VERSION",
    "AdapterCapabilities",
    "AdapterDep",
    "AdapterInfo",
    "AdapterPlugin",
    "AdapterUnavailable",
    "ComposedConverter",
    "ConvertContext",
    "Converted",
    "ExtraFieldDescriptor",
    "FieldDescriptor",
    "Flavor",
    "PairConverter",
    "PatchModel",
    "ResourceInfo",
    "ResourceType",
    "WorldAdapter",
    "WorldConfig",
    "WriteAdapterDep",
    "atomic_write_bytes",
    "conflict",
    "convert_helpers",
    "convert_tables",
    "describe_resource",
    "diagnostic",
    "extra_dropped",
    "finish_resource",
    "get_registry",
    "loss",
    "heavy_rate_limit",
    "make_page",
    "not_found",
    "paginate_list",
    "register_kind",
    "require_capability",
    "rules",
    "to_in",
    "xf",
]
