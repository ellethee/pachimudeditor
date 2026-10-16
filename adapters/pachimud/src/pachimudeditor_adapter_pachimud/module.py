"""Modulo pachifast dell'adapter pachimud: i messaggi it/en dell'adapter (non ha route proprie)."""

from pachifast import AppModule

module = AppModule(name="pachimudeditor_adapter_pachimud", kind="common", locale_package="pachimudeditor_adapter_pachimud.locale")
