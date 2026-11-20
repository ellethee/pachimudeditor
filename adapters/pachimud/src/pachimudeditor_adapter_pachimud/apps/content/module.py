from pachifast import AppModule

module = AppModule(
    name="content",
    kind="app",
    router_modules=("pachimudeditor_adapter_pachimud.apps.content.root", "pachimudeditor_adapter_pachimud.apps.content.shops"),
    locale_package="pachimudeditor_adapter_pachimud.apps.content.locale",
)
