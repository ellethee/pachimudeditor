from pachifast import AppModule

module = AppModule(
    name="players",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.players.root",),
    locale_package="pachimudeditor_adapter_pachimud.apps.players.locale",
)
