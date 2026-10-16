from pachifast import AppModule

module = AppModule(
    name="convert",
    kind="app",
    router_modules=("pachimudeditor.apps.convert.root",),
    locale_package="pachimudeditor.apps.convert.locale",
)
