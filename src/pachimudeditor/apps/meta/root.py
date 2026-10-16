"""Metadati dell'editor: liste di opzioni per le select del frontend e contenuti YAML (razze/classi).

Il liveness probe e' `GET /api/health/` del core di pachifast (sostituisce il vecchio `/ping`).
Router sottile: i dati vengono dall'adapter del mondo attivo.
"""

from pachifast.router_factory import get_router

from pachimudeditor.common.adapters.models import ContentRef, Option
from pachimudeditor.common.adapters.registry import AdapterDep

router = get_router()


@router.get("/enums", response_model=dict[str, list[Option]])
async def enums(adapter: AdapterDep) -> dict[str, list[Option]]:
    """`{name: [{value, label}]}` per ogni enum che i form usano."""
    return await adapter.enums()


@router.get("/races", response_model=list[ContentRef])
async def races(adapter: AdapterDep) -> list[ContentRef]:
    """Le razze del mondo (pachimud: `definitions/races/*.yaml`, rilette ad ogni chiamata)."""
    return await adapter.races()


@router.get("/classes", response_model=list[ContentRef])
async def classes(adapter: AdapterDep) -> list[ContentRef]:
    """Le classi del mondo (pachimud: `definitions/classes/*.yaml`, rilette ad ogni chiamata)."""
    return await adapter.classes()
