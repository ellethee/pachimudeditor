"""Modulo pachifast dell'adapter Diku Modificato: i messaggi it/en (si registra solo se esiste un mondo `kind: dikumod`)."""

from pachifast import AppModule

module = AppModule(name="pachimudeditor_adapter_dikumod", kind="common", locale_package="pachimudeditor_adapter_dikumod.locale")
