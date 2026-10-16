"""Modulo pachifast dell'adapter BasedMud: i messaggi it/en (si registra solo se esiste un mondo `kind: basedmud`)."""

from pachifast import AppModule

module = AppModule(name="pachimudeditor_adapter_basedmud", kind="common", locale_package="pachimudeditor_adapter_basedmud.locale")
