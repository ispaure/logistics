"""Completion percentages derived from the position the reader actually displayed."""

from math import isfinite


def page_percent(page, count, *, within=0., at_end=None):
    if type(page) is not int or not 0 <= page < count:
        return 0
    if at_end is None:
        at_end = page > 0 and page == count - 1
    if at_end:
        return 100
    if not (page or within):
        return 0
    return max(1, min(99, round(100 * (page + within) / max(1, count - 1))))


def video_percent(state):
    if state.get('completed') is True:
        return 100
    position, duration = state.get('position', 0), state.get('duration', 0)
    if (type(position) not in (int, float) or type(duration) not in (int, float)
            or not isfinite(position) or not isfinite(duration) or position <= 0 or duration <= 0):
        return 0
    return max(1, min(99, round(100 * position / duration)))
