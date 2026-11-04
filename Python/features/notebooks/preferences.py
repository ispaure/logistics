"""Display-only notebook preferences, separate from native ink colors."""
from pathlib import Path


def paper_preview_enabled():
    from commonUtils.configuration.settings import get_setting
    return get_setting('Preview', 'paper_pro_colors_bool', True,
                       path=Path(__file__).with_name('config.ini'))
