"""Reader animation policy over shared platform transitions."""
from commonUtils.ui.native.transitions import (
    page_direction as page_direction, begin_page_slide as begin_slide, finish_page_slide as finish_slide,
)


def begin_page_slide(content, direction, preferences):
    return begin_slide(content, direction, enabled=preferences.get('android_eink') != 'true')


def finish_page_slide(content, direction, preferences):
    return finish_slide(content, direction, enabled=preferences.get('android_eink') != 'true')
