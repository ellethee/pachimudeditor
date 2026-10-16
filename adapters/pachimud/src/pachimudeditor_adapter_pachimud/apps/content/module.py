from pachifast import AppModule

module = AppModule(
    name="content",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.content.root",),
    locale_package="pachimudeditor_adapter_pachimud.apps.content.locale",
)
