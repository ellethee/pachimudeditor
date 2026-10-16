from pachifast import AppModule

module = AppModule(
    name="objects",
    kind="app",
    router_modules=("pachimudeditor.apps.objects.root",),
    locale_package="pachimudeditor.apps.objects.locale",
)
