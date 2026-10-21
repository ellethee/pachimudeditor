from pachifast import AppModule

module = AppModule(
    name="worldlive",
    kind="app",
    router_modules=("pachimudeditor.apps.worldlive.root",),
    locale_package="pachimudeditor.apps.worldlive.locale",
)
