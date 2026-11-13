"""Lower the reader's visible track inside its full native touch area."""
from rubicon.objc import CGRect, SEL, objc_method, send_super
from toga_iOS.widgets.slider import Slider, TogaSlider
from toga_iOS.libs import (
    UIControlEventTouchCancel, UIControlEventTouchDown,
    UIControlEventTouchUpInside, UIControlEventTouchUpOutside,
    UIControlEventValueChanged,
)
from .reading.reader_progress import IOS_TRACK_OFFSET


class LogisticsReaderSlider(TogaSlider):
    @objc_method
    def trackRectForBounds_(self, bounds: CGRect) -> CGRect:
        rect = send_super(__class__, self, 'trackRectForBounds:', bounds,
                          restype=CGRect, argtypes=[CGRect])
        # The 16-point thumb remains inside the native 48-point hit row.
        rect.origin.y += min(IOS_TRACK_OFFSET, max(0, (bounds.size.height - 16) / 2))
        return rect


class ReaderSlider(Slider):
    def create(self):
        self.native = LogisticsReaderSlider.alloc().init()
        self.native.interface, self.native.impl = self.interface, self
        self.value, self.min_value, self.max_value, self.tick_count = 0, 0, 1, None
        for selector, events in (
            ('onSlide:', UIControlEventValueChanged),
            ('onPress:', UIControlEventTouchDown),
            ('onRelease:', UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel),
        ):
            self.native.addTarget(self.native, action=SEL(selector), forControlEvents=events)
        self.add_constraints()
