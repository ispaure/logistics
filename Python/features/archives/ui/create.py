"""Source basket and format options for the archive workspace."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from services.password_prompt import confirmed_password


class NewArchiveDialog(qt.QDialog):
    def __init__(self, sources=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle('Create archive')
        self.resize(640, 440)
        self.password = None
        layout = qt.QVBoxLayout(self)
        label = qt.QLabel('Choose files and folders to pack. Each folder keeps its name and structure.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.sources = qt.QListWidget()
        self.sources.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.sources, 1)
        row = qt.QHBoxLayout()
        for title, callback in [('Add files…', self._files), ('Add folder…', self._folder), ('Remove selected', self._remove)]:
            button = qt.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.format = qt.QComboBox()
        for title, value in [('ZIP • compatible & fast', 'zip'), ('TAR + gzip • Linux sharing', 'tar.gz'),
                             ('TAR + xz • smaller archives', 'tar.xz'), ('TAR • no compression', 'tar')]:
            self.format.addItem(title, value)
        self.level = qt.QComboBox()
        for title, value in [('Store • no compression', 0), ('Fast • low CPU use', 1),
                             ('Balanced • recommended', 6), ('Maximum • smaller ZIP', 9)]:
            self.level.addItem(title, value)
        self.level.setCurrentIndex(2)
        self.encrypt = qt.QCheckBox('Protect ZIP with an AES-256 password')
        self.encrypt.setToolTip('Encrypts file contents. Entry names remain visible.')
        self.format.currentIndexChanged.connect(self._format_changed)
        self.output = qt.QLineEdit()
        self.output.setPlaceholderText('Choose an output archive outside your source folders')
        destination_row = qt.QHBoxLayout()
        destination_row.addWidget(self.output, 1)
        browse = qt.QPushButton('Browse…')
        browse.clicked.connect(self._destination)
        destination_row.addWidget(browse)
        form = qt.QFormLayout()
        form.addRow('Format', self.format)
        form.addRow('ZIP compression', self.level)
        form.addRow('Destination', destination_row)
        form.addRow('', self.encrypt)
        layout.addLayout(form)
        self.message = qt.QLabel('New archives are verified before publication. Sources are kept.')
        self.message.setWordWrap(True)
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Save | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(qt.QDialogButtonBox.StandardButton.Save).setText('Create archive')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.add_sources(sources)

    def _format_changed(self):
        is_zip = self.format.currentData() == 'zip'
        self.encrypt.setEnabled(is_zip)
        self.level.setEnabled(is_zip)

    def add_sources(self, paths):
        existing = {self.sources.item(i).text() for i in range(self.sources.count())}
        for path in paths:
            value = str(Path(path).absolute())
            if value not in existing:
                self.sources.addItem(value)
                existing.add(value)

    def _files(self):
        paths, _ = qt.QFileDialog.getOpenFileNames(self, 'Add files')
        self.add_sources(paths)

    def _folder(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Add folder')
        if path:
            self.add_sources([path])

    def _remove(self):
        for item in self.sources.selectedItems():
            self.sources.takeItem(self.sources.row(item))

    def _destination(self):
        extension = self.format.currentData()
        path, _ = qt.QFileDialog.getSaveFileName(self, 'New archive destination', self.output.text(), f'Archives (*.{extension})')
        if path:
            if not path.lower().endswith('.' + extension):
                path += '.' + extension
            self.output.setText(path)

    def _accept(self):
        if not self.sources.count() or not self.output.text().strip():
            self.message.setText('Add a source and choose a destination.')
            return
        if Path(self.output.text()).exists():
            self.message.setText('That output already exists. Choose another filename.')
            return
        if self.encrypt.isChecked() and self.format.currentData() == 'zip':
            self.password = confirmed_password(self, 'Protect file contents with AES-256. Filenames remain visible. The password is kept only for this operation.')
            if self.password is None:
                return
        self.accept()

    def options(self):
        return dict(sources=[Path(self.sources.item(i).text()) for i in range(self.sources.count())],
                    destination=Path(self.output.text().strip()), format=self.format.currentData(),
                    level=self.level.currentData(), password=self.password)
