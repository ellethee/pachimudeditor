from pachifast import AppModule

module = AppModule(
    name="zones",
    kind="app",
    router_modules=("pachimudeditor.apps.zones.root",),
    locale_package="pachimudeditor.apps.zones.locale",
)
