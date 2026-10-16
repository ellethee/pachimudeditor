from pachifast import AppModule

module = AppModule(
    name="meta",
    kind="app",
    router_modules=("pachimudeditor.apps.meta.root",),
    locale_package="pachimudeditor.apps.meta.locale",
)
