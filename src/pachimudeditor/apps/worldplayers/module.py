from pachifast import AppModule

module = AppModule(
    name="worldplayers",
    kind="app",
    router_modules=("pachimudeditor.apps.worldplayers.root",),
    locale_package="pachimudeditor.apps.worldplayers.locale",
)
