"""Click-to-open model selection with readable, wrapping model names."""
from commonUtils.ui import pyside as qt


class ModelPicker(qt.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False)
        self.setMinimumWidth(90)
        self.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Fixed)
        self.currentTextChanged.connect(self.refresh_name)

    def setCurrentText(self, text):
        # Saved conversations can name a model before server discovery runs.
        if text and self.findText(text) < 0:
            self.addItem(text)
        super().setCurrentText(text)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(max(90, self.fontMetrics().horizontalAdvance(self.currentText()) + 38))
        return hint

    def minimumSizeHint(self):
        return qt.QSize(90, super().minimumSizeHint().height())

    def name_layout(self):
        option = qt.QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(qt.QStyle.ComplexControl.CC_ComboBox, option,
                                          qt.QStyle.SubControl.SC_ComboBoxEditField, self)
        layout = qt.QTextLayout(self.currentText(), self.font())
        text_option = qt.QTextOption()
        text_option.setWrapMode(qt.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(text_option)
        layout.beginLayout()
        height = 0
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, rect.width()))
            line.setPosition(qt.QPointF(0, height))
            height += line.height()
        layout.endLayout()
        return rect, layout, height

    def refresh_name(self):
        self.setToolTip(self.currentText() or 'Choose a model; refresh models beside Server')
        _, _, height = self.name_layout()
        target = max(super().sizeHint().height(), round(height) + 8)
        if self.height() != target:
            self.setFixedHeight(target)
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_name()

    def paintEvent(self, event):
        option = qt.QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ''
        painter = qt.QPainter(self)
        self.style().drawComplexControl(qt.QStyle.ComplexControl.CC_ComboBox, option, painter, self)
        rect, layout, height = self.name_layout()
        painter.setPen(self.palette().color(qt.QPalette.ColorRole.ButtonText))
        layout.draw(painter, qt.QPointF(rect.left(), (self.height() - height) / 2))

    def showPopup(self):
        width = max((self.fontMetrics().horizontalAdvance(self.itemText(index)) for index in range(self.count())), default=0)
        self.view().setMinimumWidth(min(width + 40, self.screen().availableGeometry().width() - 40))
        super().showPopup()
