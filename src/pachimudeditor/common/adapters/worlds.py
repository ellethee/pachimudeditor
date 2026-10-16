"""Mondi configurati e relative capability. Prefisso `/api/worlds`."""

from pachifast.router_factory import get_router

from pachimudeditor.common.adapters.base import AdapterInfo
from pachimudeditor.common.adapters.registry import get_registry

router = get_router(name="worlds")


@router.get("", response_model=list[AdapterInfo])
async def list_worlds() -> list[AdapterInfo]:
    """Ogni mondo configurato: id, tipo, nome, capability e campi delle risorse; `default` marca quello usato
    quando la richiesta non indica `X-World`/`?world=`."""
    return get_registry().describe_all()
