"""Desktop notebook creation using the same generated template catalog as mobile."""
from commonUtils.ui import pyside as qt
from ..notebook import Notebook
from ..templates import CATALOG, FORMATS, TEMPLATE_NOTICE, description, svg


class NotebookSetup(qt.QDialog):
    def __init__(self, parent=None, *, name='Notebook', fixed_name=False):
        super().__init__(parent)
        self.setWindowTitle('New notebook')
        self.setMinimumWidth(390)
        layout = qt.QVBoxLayout(self)
        form = qt.QFormLayout()
        self.name = qt.QLineEdit(name)
        self.name.setMaxLength(120)
        self.name.setReadOnly(fixed_name)
        self.template = qt.QComboBox()
        for key, label in CATALOG.items():
            self.template.addItem(label, key)
        self.paper_format = qt.QComboBox()
        for key, label in FORMATS.items():
            self.paper_format.addItem(label, key)
        form.addRow('Notebook name', self.name)
        form.addRow('First page template', self.template)
        form.addRow('Template size', self.paper_format)
        layout.addLayout(form)
        self.preview = qt.QLabel()
        self.preview.setFixedSize(210, 280)
        self.preview.setStyleSheet('background:white;border:1px solid #aaa')
        layout.addWidget(self.preview, alignment=qt.Qt.AlignmentFlag.AlignHCenter)
        self.description = qt.QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        hint = qt.QLabel('Change any page later in Page Template. New pages inherit the current page’s template.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        notice = qt.QLabel(TEMPLATE_NOTICE)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Cancel)
        self.create = self.buttons.addButton('Create notebook', qt.QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.template.currentIndexChanged.connect(self.update_preview)
        self.paper_format.currentIndexChanged.connect(self.update_preview)
        self.name.textChanged.connect(lambda: self.create.setEnabled(bool(self.name.text().strip())))
        self.update_preview()

    def update_preview(self):
        name = self.template.currentData()
        self.paper_format.setEnabled(name.startswith('Logistics '))
        self.description.setText(description(name))
        artwork = svg(name, self.paper_format.currentData())
        if artwork:
            image = qt.QPixmap()
            image.loadFromData(artwork.encode(), 'SVG')
            self.preview.setPixmap(image.scaled(self.preview.size(), qt.Qt.AspectRatioMode.KeepAspectRatio,
                                                qt.Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview.clear()
        self.layout().activate()
        self.adjustSize()

    def notebook(self):
        return Notebook.new(self.name.text().strip(), template=self.template.currentData(),
                            paper_format=self.paper_format.currentData())


def choose_new_notebook(parent=None, *, name='Notebook', fixed_name=False):
    dialog = NotebookSetup(parent, name=name, fixed_name=fixed_name)
    try:
        return dialog.notebook() if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()
