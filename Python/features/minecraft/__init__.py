"""
Minecraft feature integration for Logistics.
"""


FEATURE_NAME = "minecraft"
FEATURE_LABEL = "Minecraft"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.minecraft.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
