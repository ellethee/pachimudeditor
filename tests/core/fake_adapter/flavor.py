"""Sapori fittizi."""

from pachimudeditor.sdk import Flavor


class FakeFlavor(Flavor):
    """Sapore `fake`."""

    kind = "fake"


class Fake2Flavor(Flavor):
    """Sapore `fake2`."""

    kind = "fake2"
