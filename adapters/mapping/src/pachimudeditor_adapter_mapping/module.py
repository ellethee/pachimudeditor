"""Modulo pachifast dell'adapter generico: i messaggi it/en (si registra solo se esiste un mondo `kind: mapping`)."""

from pachifast import AppModule

module = AppModule(name="pachimudeditor_adapter_mapping", kind="common", locale_package="pachimudeditor_adapter_mapping.locale")
