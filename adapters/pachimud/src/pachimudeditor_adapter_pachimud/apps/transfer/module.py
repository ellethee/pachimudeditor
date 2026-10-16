from pachifast import AppModule

module = AppModule(
    name="transfer",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.transfer.root",),
    locale_package="pachimudeditor_adapter_pachimud.apps.transfer.locale",
)
