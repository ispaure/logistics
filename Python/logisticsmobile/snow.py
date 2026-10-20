"""Native, input-transparent seasonal snow. No document views are replaced."""
import asyncio
from random import Random

from services.seasonal import snow_enabled


class SeasonalSnow:
    def __init__(self, app):
        self.app = app
        self.backend = type(app._impl).__module__
        self.view = None
        self.size = None
        self.task = None
        if self.backend.startswith(('toga_iOS.', 'toga_android.')):
            self.task = app.loop.create_task(self.watch())

    def high_contrast(self):
        if self.app.preferences.values['android_eink'] == 'true':
            return True
        if self.backend.startswith('toga_iOS.'):
            return self.app.main_window._impl.native.traitCollection.accessibilityContrast == 1
        if self.backend.startswith('toga_android.'):
            from android.provider import Settings
            return Settings.Secure.getInt(self.app._impl.native.getContentResolver(),
                                          'high_text_contrast_enabled', 0) == 1
        return False

    def refresh(self):
        enabled = snow_enabled(self.app.preferences.values['seasonal_snow'] == 'true', self.high_contrast())
        # Do not animate over a privacy shield or while the app is inactive.
        privacy = getattr(self.app, 'screen_privacy', None)
        enabled = enabled and not getattr(privacy, 'inactive', False)
        if not enabled:
            self.remove()
            return
        if self.backend.startswith('toga_android.'):
            if self.view is None:
                from java import jclass
                from android.widget import FrameLayout
                self.view = jclass('io.github.ispaure.logisticsmobile.SnowView')(self.app._impl.native)
                self.app._impl.native.getWindow().getDecorView().addView(
                    self.view, FrameLayout.LayoutParams(-1, -1))
        elif self.backend.startswith('toga_iOS.'):
            self.refresh_ios()

    def refresh_ios(self):
        from rubicon.objc import ObjCClass, CGRect, CGPoint, CGSize
        window = self.app.main_window._impl.native
        size = (float(window.bounds.size.width), float(window.bounds.size.height))
        if self.view is not None and self.size == size:
            return
        self.remove()
        self.size = size
        width, height = size
        self.view = ObjCClass('UIView').alloc().initWithFrame(window.bounds)
        self.view.userInteractionEnabled = False
        self.view.isAccessibilityElement = False
        self.view.backgroundColor = ObjCClass('UIColor').clearColor
        window.addSubview(self.view)
        rng = Random(15)
        for _ in range(28):
            radius = rng.uniform(1.5, 3)
            layer = ObjCClass('CALayer').layer()
            layer.frame = CGRect(CGPoint(0, 0), CGSize(radius * 2, radius * 2))
            layer.position = CGPoint(rng.random() * width, -6)
            layer.cornerRadius = radius
            layer.backgroundColor = ObjCClass('UIColor').colorWithRed(.71, green=.8, blue=.9, alpha=.6).CGColor
            self.view.layer.addSublayer(layer)
            animation = ObjCClass('CABasicAnimation').animationWithKeyPath('transform.translation.y')
            animation.fromValue = 0
            animation.toValue = height + 12
            animation.duration = (height + 12) / rng.uniform(12, 28)
            animation.timeOffset = rng.random() * animation.duration
            animation.repeatCount = float('inf')
            layer.addAnimation(animation, forKey='snowfall')

    def remove(self):
        if self.view is not None:
            if self.backend.startswith('toga_iOS.'):
                self.view.removeFromSuperview()
            else:
                parent = self.view.getParent()
                if parent is not None:
                    parent.removeView(self.view)
            self.view = None
            self.size = None

    async def watch(self):
        while True:
            self.refresh()
            await asyncio.sleep(1)

    def dispose(self):
        if self.task is not None:
            self.task.cancel()
        self.remove()
