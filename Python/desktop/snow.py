"""A small, input-transparent seasonal decoration owned by the desktop shell."""
from pathlib import Path
from random import Random
from time import monotonic

from commonUtils.ui import pyside as qt
from features.settings import settings_store
from services.seasonal import snow_enabled

CONFIG = Path(__file__).resolve().parents[1] / 'configFile.ini'
FIELD = ('Appearance', 'seasonal_snow_bool')


class SnowOverlay(qt.QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(qt.Qt.FocusPolicy.NoFocus)
        self.store = settings_store(CONFIG)
        rng = Random(15)
        self.flakes = [(rng.random(), rng.random(), rng.uniform(12, 28),
                        rng.uniform(1.5, 3)) for _ in range(32)]
        self.started = monotonic()
        self.animation = qt.QTimer(self)
        self.animation.setInterval(33)
        self.animation.timeout.connect(self.update)
        self.poll = qt.QTimer(self)
        self.poll.setInterval(1000)
        self.poll.timeout.connect(self.refresh)
        self.poll.start()
        window.installEventFilter(self)
        self.style_hints = qt.QApplication.instance().styleHints()
        self.accessibility = self.style_hints.accessibility()
        self.accessibility.contrastPreferenceChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *args):
        high_contrast = (self.accessibility.contrastPreference() ==
                         qt.Qt.ContrastPreference.HighContrast)
        enabled = self.store.safe_values().get(FIELD, 'true').lower() == 'true'
        active = snow_enabled(enabled, high_contrast) and self.parentWidget().isVisible()
        self.setVisible(active)
        if active:
            self.setGeometry(self.parentWidget().rect())
            self.raise_()
        if active and not self.parentWidget().isMinimized() and self.parentWidget().isActiveWindow():
            self.animation.start()
        else:
            self.animation.stop()

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Resize, qt.QEvent.Type.Show,
                            qt.QEvent.Type.Hide, qt.QEvent.Type.WindowActivate,
                            qt.QEvent.Type.WindowDeactivate):
            self.refresh()
        return False

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.setPen(qt.Qt.PenStyle.NoPen)
        painter.setBrush(qt.QColor(180, 204, 228, 155))
        elapsed = monotonic() - self.started
        for x, y, speed, radius in self.flakes:
            painter.drawEllipse(qt.QPointF((x * self.width() + elapsed * 4) % max(1, self.width()),
                (y * self.height() + elapsed * speed) % max(1, self.height())), radius, radius)
