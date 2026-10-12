"""
Minecraft feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Discover local Minecraft servers, launch them and open their settings.'


FEATURE_NAME = "minecraft"
FEATURE_LABEL = "Minecraft Server"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.minecraft.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
