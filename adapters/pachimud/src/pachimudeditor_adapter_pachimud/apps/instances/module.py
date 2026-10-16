from pachifast import AppModule

module = AppModule(
    name="instances",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.instances.root",),
    locale_package="pachimudeditor_adapter_pachimud.apps.instances.locale",
)
