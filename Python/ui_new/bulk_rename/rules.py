"""Compact reusable controls for the filename transformation pipeline."""
from commonUtils.renameUtils import RenameRules
from commonUtils.ui import pyside as qt


class RenameRuleControls(qt.QWidget):
    changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fields = {}
        grid = qt.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        sections = [
            ('1 · Regular expression', [('regex_pattern', 'Match', ''), ('regex_replacement', 'Replace', ''),
                ('regex_include_extension', 'Include extension', False)]),
            ('2 · Name', [('name_mode', 'Mode', ['keep', 'fixed', 'remove']), ('fixed_name', 'Name', '')]),
            ('3 · Replace', [('replace_from', 'Find', ''), ('replace_to', 'With', ''),
                ('replace_case_sensitive', 'Match case', True), ('replace_first', 'First only', False)]),
            ('4 · Case', [('case_mode', 'Case', ['same', 'lower', 'upper', 'title', 'sentence', 'swap'])]),
            ('5 · Remove', [('remove_first', 'First characters', 0), ('remove_last', 'Last characters', 0),
                ('remove_start', 'From position', 0), ('remove_count', 'Count', 0), ('remove_chars', 'Characters', ''),
                ('remove_digits', 'Digits', False), ('remove_symbols', 'Symbols', False),
                ('remove_accents', 'Accents', False), ('trim', 'Trim whitespace', False)]),
            ('6 · Move / copy a part', [('part_start', 'From position', 0), ('part_count', 'Count', 0),
                ('part_position', 'To position', 0), ('copy_part', 'Copy instead of move', False)]),
            ('7 · Add', [('prefix', 'Prefix', ''), ('insert', 'Insert', ''),
                ('insert_position', 'At position', 0), ('suffix', 'Suffix', '')]),
            ('8 · Date', [('date_mode', 'Mode', ['none', 'prefix', 'suffix']),
                ('date_source', 'Source', ['modified', 'created', 'today']),
                ('date_format', 'Format', '%Y-%m-%d'), ('date_separator', 'Separator', '_'),
                ('date_offset_days', 'Offset days', 0)]),
            ('9 · Parent folder', [('folder_mode', 'Mode', ['none', 'prefix', 'suffix']),
                ('folder_levels', 'Levels', 1), ('folder_separator', 'Separator', '_')]),
            ('10 · Numbering', [('number_mode', 'Mode', ['none', 'prefix', 'suffix', 'insert']),
                ('number_start', 'Start', 1), ('number_step', 'Step', 1), ('number_padding', 'Padding', 0),
                ('number_position', 'Insert position', 0), ('number_separator', 'Separator', '_'),
                ('number_per_folder', 'Restart per folder', False)]),
            ('11 · Extension', [('extension_mode', 'Mode', ['same', 'lower', 'upper', 'fixed', 'remove']),
                ('extension', 'Extension', '')]),
        ]
        for index, (title, fields) in enumerate(sections):
            box = qt.QGroupBox(title)
            form = qt.QFormLayout(box)
            form.setContentsMargins(8, 8, 8, 8)
            for name, label, default in fields:
                if isinstance(default, bool):
                    widget = qt.QCheckBox(label)
                    widget.setChecked(default)
                    widget.toggled.connect(self.changed)
                    form.addRow(widget)
                elif isinstance(default, list):
                    widget = qt.QComboBox()
                    for value in default:
                        widget.addItem(value.replace('_', ' ').capitalize(), value)
                    widget.currentIndexChanged.connect(self.changed)
                    form.addRow(label, widget)
                elif isinstance(default, int):
                    widget = qt.QSpinBox()
                    widget.setRange(-1000000 if name in ('date_offset_days', 'number_start', 'number_step') else 0,
                                    1000000)
                    if name == 'number_padding':
                        widget.setMaximum(255)
                    if name == 'folder_levels':
                        widget.setMinimum(1)
                    widget.setValue(default)
                    widget.valueChanged.connect(self.changed)
                    form.addRow(label, widget)
                else:
                    widget = qt.QLineEdit(default)
                    widget.textChanged.connect(self.changed)
                    form.addRow(label, widget)
                widget.setAccessibleName(f'{title}: {label}')
                self.fields[name] = widget
            grid.addWidget(box, index // 4, index % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        self.fields['regex_replacement'].setToolTip(r'Python regex replacement: \1 or \g<name> for groups')
        self.fields['date_format'].setToolTip('%Y year · %m month · %d day · %H hour · %M minute · %S second')
        for name in ('remove_start', 'part_start', 'part_position', 'insert_position', 'number_position'):
            self.fields[name].setToolTip('Zero-based character position; positions beyond the name append at the end')

    def rules(self):
        values = {}
        for name, widget in self.fields.items():
            if isinstance(widget, qt.QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, qt.QComboBox):
                values[name] = widget.currentData()
            elif isinstance(widget, qt.QSpinBox):
                values[name] = widget.value()
            else:
                values[name] = widget.text()
        return RenameRules(**values)

    def set_rules(self, rules):
        rules.validate()
        # Validate before touching any control so malformed presets leave all rules intact.
        for name, widget in self.fields.items():
            value = getattr(rules, name)
            if isinstance(widget, qt.QCheckBox) and not isinstance(value, bool):
                raise ValueError(f'{name} must be a checkbox value')
            if isinstance(widget, qt.QSpinBox) and (not isinstance(value, int) or
                                                   not widget.minimum() <= value <= widget.maximum()):
                raise ValueError(f'{name} is outside the supported range')
            if isinstance(widget, qt.QLineEdit) and not isinstance(value, str):
                raise ValueError(f'{name} must be text')
        blockers = [qt.QSignalBlocker(widget) for widget in self.fields.values()]
        for name, widget in self.fields.items():
            value = getattr(rules, name)
            if isinstance(widget, qt.QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, qt.QComboBox):
                widget.setCurrentIndex(widget.findData(value))
            elif isinstance(widget, qt.QSpinBox):
                widget.setValue(value)
            else:
                widget.setText(value)
        del blockers
        self.changed.emit()
