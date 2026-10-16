from pachifast import AppModule

module = AppModule(
    name="mobs",
    kind="app",
    router_modules=("pachimudeditor.apps.mobs.root",),
    locale_package="pachimudeditor.apps.mobs.locale",
)
