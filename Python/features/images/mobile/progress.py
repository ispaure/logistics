"""Standalone image zoom relative to the native canvas's fit scale."""

from math import isfinite


class ImageViewport:
    def __init__(self, progress, saved):
        self.progress = progress
        zoom = saved.get('zoom')
        self.zoom = zoom if type(zoom) in (float, int) and isfinite(zoom) and 1 <= zoom <= 6 else 1

    def restore(self, canvas):
        canvas.set_zoom(self.zoom)

    def observe(self, canvas):
        zoom = canvas.zoom_scale
        if type(zoom) in (int, float) and isfinite(zoom) and 1 <= zoom <= 6 and abs(zoom - self.zoom) >= .01:
            token = self.progress.observe(dict(zoom=zoom))
            if token is not None:
                self.zoom = zoom
            return token
        return None
