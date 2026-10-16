"""Plugin fittizi `fake` e `fake2` (solo stringhe: nulla di pesante si importa finche' non serve)."""

from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="fake",
    description="adapter di prova",
    factory="tests.core.fake_adapter.impl:FakeAdapter",
    modules=("tests.core.fake_adapter.module:module",),
    flavor="tests.core.fake_adapter.flavor:FakeFlavor",
    validate="tests.core.fake_adapter.impl:validate",
    example="# - { id: prova, kind: fake, path: /percorso/fake }\n",
)
plugin2 = AdapterPlugin(
    kind="fake2",
    description="secondo adapter di prova",
    factory="tests.core.fake_adapter.impl:FakeAdapter",
    flavor="tests.core.fake_adapter.flavor:Fake2Flavor",
)


def _with_sdk(kind: str, sdk_version: str) -> AdapterPlugin:
    """Plugin di prova che dichiara una certa `sdk_version`."""
    return AdapterPlugin(
        kind=kind, description=f"sdk {sdk_version}", factory="tests.core.fake_adapter.impl:FakeAdapter", sdk_version=sdk_version
    )


plugin_sdk_next_major = _with_sdk("sdk_next", "2.0")
plugin_sdk_old_major = _with_sdk("sdk_old", "0.9")
plugin_sdk_newer_minor = _with_sdk("sdk_newer", "1.99")
plugin_sdk_older_minor = _with_sdk("sdk_older", "1.0")
