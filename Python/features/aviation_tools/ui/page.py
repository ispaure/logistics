"""Popup calculators and browsable datasets from the Flight Tools project."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
    QLabel, QDialog, QGridLayout, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView,
)
from ..mathUtils import flightUtils as flight
from ..plane import planeUtils
from ..location import locationUtils
from ..resources import DATA_DIR


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Enter a finite number.')
    return result


def text(value):
    return value.strip()


class Calculator(QWidget):
    """A form with explicit units, read-only results and recoverable input errors."""
    def __init__(self, description, fields, calculate, parent=None):
        super().__init__(parent)
        self.calculate = calculate
        self.fields = {}
        layout = QVBoxLayout(self)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        form = QFormLayout()
        for key, label, default, converter in fields:
            if isinstance(default, tuple):
                widget = QComboBox()
                widget.addItems(default)
            else:
                widget = QLineEdit(str(default))
                widget.returnPressed.connect(self.run)
            self.fields[key] = (widget, converter)
            form.addRow(label, widget)
        layout.addLayout(form)
        self.calculate_button = QPushButton('Calculate')
        self.calculate_button.clicked.connect(self.run)
        layout.addWidget(self.calculate_button)
        self.result = QLabel('Enter values and select Calculate.')
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(self.result.textInteractionFlags() | Qt.TextSelectableByMouse)
        layout.addWidget(self.result)
        layout.addStretch()

    def run(self):
        try:
            values = {key: converter(widget.currentText() if isinstance(widget, QComboBox)
                                      else widget.text())
                      for key, (widget, converter) in self.fields.items()}
            result = self.calculate(**values)
        except (ValueError, TypeError, OSError, KeyError, AttributeError, ArithmeticError) as error:
            self.result.setText(f'Cannot calculate: {error}')
        else:
            self.result.setText(result)


def coordinates(latitude_1, longitude_1, latitude_2, longitude_2):
    for latitude in (latitude_1, latitude_2):
        if not -90 <= latitude <= 90:
            raise ValueError('Latitude must be between -90 and 90 degrees.')
    for longitude in (longitude_1, longitude_2):
        if not -180 <= longitude <= 180:
            raise ValueError('Longitude must be between -180 and 180 degrees.')
    return flight.Coordinate(latitude_1, longitude_1), flight.Coordinate(latitude_2, longitude_2)


def distance(**values):
    return f'Distance: {flight.distance_from_coords(*coordinates(**values)):.2f} NM'


def course(deviation, direction, **values):
    true = flight.true_course_from_coords(*coordinates(**values))
    magnetic = flight.magnetic_course(true, flight.MagneticDeviation(deviation, direction))
    return f'True course: {true:.2f}°\nMagnetic course: {magnetic:.2f}°'


def headings(airport, **values):
    correction = flight.wind_correction_angle(**values)
    true = flight.true_heading(**values)
    magnetic = flight.magnetic_heading(true, locationUtils.get_airport_from_iata(airport).magnetic_deviation)
    return f'Wind correction angle: {correction:.2f}°\nTrue heading: {true:.2f}°\nMagnetic heading: {magnetic:.2f}°'


def ground_speed(**values):
    return f'Ground speed: {flight.ground_speed(**values):.2f} kt'


def indicated_speed(ktas, altitude):
    return f'Indicated airspeed: {flight.ktas_to_kias(ktas, altitude):.2f} KIAS'


def calibrated_speed(registration, kias):
    result = planeUtils.Aircraft(registration).model.airspeed_calibration_chart.get_kcas(kias)
    if result is None:
        raise ValueError('Airspeed is outside the supplied flaps-up calibration chart.')
    return f'Calibrated airspeed: {result:.2f} KCAS'


def cruise(registration, **values):
    entry = planeUtils.Aircraft(registration).model.cruise_performance_chart.get_cruise_performance(**values)
    if entry is None:
        raise ValueError('No chart row matches the nearest altitude, temperature and RPM.')
    return (f'Power: {entry.percent_bhp:.2f}% BHP\nTrue airspeed: {entry.true_air_speed:.2f} KTAS\n'
            f'Fuel consumption: {entry.cons_gallon_per_hour:.2f} US gal/h\n'
            f'Chart row: {entry.pressure_altitude:g} ft, {entry.rpm:g} RPM, '
            f'{entry.temperature:g} °C reference temperature')


class AviationToolsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel('Aviation Tools')
        layout.addWidget(title)
        instruction = QLabel('Choose a tool to open its window. You can keep several tools open together.')
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        buttons = QGridLayout()
        layout.addLayout(buttons)
        layout.addStretch()
        self.calculators = {}
        self.tool_buttons = {}
        self._dialogs = {}
        coordinate_fields = [
            ('latitude_1', 'Origin latitude (°)', '45.60667', number),
            ('longitude_1', 'Origin longitude (°)', '-73.015', number),
            ('latitude_2', 'Destination latitude (°)', '46.7909', number),
            ('longitude_2', 'Destination longitude (°)', '-71.3886', number),
        ]
        wind_fields = [
            ('true_course', 'True course (°)', '54.6', number),
            ('true_airspeed', 'True airspeed (kt)', '111', number),
            ('wind_direction', 'Wind from (° true)', '300', number),
            ('wind_speed', 'Wind speed (kt)', '6', number),
        ]
        registrations = tuple(sorted((path.stem for path in (DATA_DIR / 'aircraft').glob('*.csv')),
                                     key=lambda name: (name != 'C-GUCH', name)))
        airports = tuple(airport.iata for airport in locationUtils.get_airport_dict().values())
        aircraft_field = ('registration', 'Aircraft registration', registrations, text)
        definitions = [
            ('Distance', 'Great-circle distance between two decimal-degree coordinates.', coordinate_fields, distance),
            ('Course', 'Initial true and magnetic course between two coordinates.', coordinate_fields + [
                ('deviation', 'Magnetic deviation (°)', '14', number),
                ('direction', 'Direction', ('west', 'east'), text)], course),
            ('Wind / Headings', 'Original Flight Tools vector approximation and stored airport magnetic deviation.', wind_fields + [
                ('airport', 'Airport code', airports, text)], headings),
            ('Ground Speed', 'Original Flight Tools vector estimate from true course, airspeed and wind.', wind_fields, ground_speed),
            ('KTAS → KIAS', 'Original density-ratio approximation; only 2,000 ft is supported.', [
                ('ktas', 'True airspeed (KTAS)', '111', number),
                ('altitude', 'Altitude (ft)', '2000', number)], indicated_speed),
            ('KIAS → KCAS', 'Linear interpolation of the supplied normal-static-source chart, flaps up.', [
                aircraft_field, ('kias', 'Indicated airspeed (KIAS)', '107', number)], calibrated_speed),
            ('Cruise Performance', 'Nearest supplied chart values; no interpolation.', [
                aircraft_field, ('pressure_altitude', 'Pressure altitude (ft)', '2000', number),
                ('rpm', 'Engine speed (RPM)', '2400', number),
                ('ground_temp', 'Temperature at sea level (°C)', '7', number)], cruise),
        ]
        self._definitions = {name: (description, fields, callback)
                             for name, description, fields, callback in definitions}
        for index, name in enumerate((*self._definitions, 'Aircraft / Airports')):
            button = QPushButton(name)
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, name=name: self.open_tool(name))
            self.tool_buttons[name] = button
            buttons.addWidget(button, index // 2, index % 2)

    def open_tool(self, name):
        """Open modeless tools, retaining inputs when a window is closed/reopened."""
        if name not in self._dialogs:
            dialog = QDialog(self)
            dialog.setWindowTitle(f'Aviation Tools — {name}')
            dialog.setModal(False)
            layout = QVBoxLayout(dialog)
            if name == 'Aircraft / Airports':
                content = DatasetBrowser(dialog)
                dialog.resize(900, 500)
            else:
                description, fields, callback = self._definitions[name]
                content = Calculator(description, fields, callback, dialog)
                self.calculators[name] = content
                dialog.resize(560, 420)
            layout.addWidget(content)
            dialog.setMinimumSize(420, 300)
            self._dialogs[name] = dialog
        dialog = self._dialogs[name]
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog


class DatasetBrowser(QWidget):
    """Read-only aircraft, airport and model chart tables in a popup window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.dataset = QComboBox()
        self.dataset.addItem('Airports', DATA_DIR / 'airports.csv')
        for path in sorted((DATA_DIR / 'aircraft').glob('*.csv')):
            self.dataset.addItem(f'Aircraft: {path.stem}', path)
        for path in sorted((DATA_DIR / 'airplane').glob('*/*.csv')):
            self.dataset.addItem(f'{path.parent.name}: {path.stem.replace("_", " ")}', path)
        layout.addWidget(self.dataset)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        self.dataset.currentIndexChanged.connect(self._load_dataset)
        self._load_dataset()

    def _load_dataset(self, _index=0):
        from commonUtils.formats.csvType import CSVFile
        path = self.dataset.currentData()
        rows = CSVFile(path).read_csv()
        self.table.clear()
        self.table.setColumnCount(len(rows[0]))
        self.table.setRowCount(len(rows) - 1)
        self.table.setHorizontalHeaderLabels(rows[0])
        for row_index, row in enumerate(rows[1:]):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem(value))
