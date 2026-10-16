from pachifast import AppModule

module = AppModule(
    name="world",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.world.root",),
    locale_package="pachimudeditor_adapter_pachimud.apps.world.locale",
)
