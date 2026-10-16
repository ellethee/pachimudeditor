from pachifast import AppModule

module = AppModule(
    name="rooms",
    kind="app",
    router_modules=("pachimudeditor.apps.rooms.root",),
    locale_package="pachimudeditor.apps.rooms.locale",
)
