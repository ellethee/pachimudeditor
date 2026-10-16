from pachifast import AppModule

module = AppModule(
    name="common.adapters",
    kind="common",
    router_modules=("pachimudeditor.common.adapters.worlds",),
    settings_modules=("pachimudeditor.common.adapters.settings",),
    startup_hooks=("pachimudeditor.common.adapters.lifecycle:startup",),
    shutdown_hooks=("pachimudeditor.common.adapters.lifecycle:shutdown",),
    locale_package="pachimudeditor.common.adapters.locale",
)
