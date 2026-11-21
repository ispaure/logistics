"""Display-only notebook preferences, separate from native ink colors."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path


def paper_preview_enabled():
    from commonUtils.configuration.settings import get_setting
    return get_setting('Preview', 'paper_pro_colors_bool', True,
                       path=Path(__file__).with_name('config.ini'))
