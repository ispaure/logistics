from typing import *
from pathlib import Path
from commonUtils import spreadsheetUtils as shUtils
from commonUtils.fileTypes.csvType import CSVFile
from features.aviation_tools.resources import DATA_DIR
from commonUtils import logUtils
from features.aviation_tools.plane import planeCruisePerformance
from features.aviation_tools.plane import planeAirspeedCalibration


class Aircraft:
    def __init__(self, registration):
        self.registration = registration.strip().upper()
        if self.registration not in {path.stem for path in (DATA_DIR / 'aircraft').glob('*.csv')}:
            raise ValueError(f'Unknown aircraft: {registration}')
        self.model = None
        self.fuel_tank_capacity = None
        self.max_take_off_weight = None
        self.basic_empty_weight = None
        self.arm_datum = None
        self.import_data()

    def import_data(self):
        aircraft_dir = Path(DATA_DIR, 'aircraft')
        aircraft_sh = shUtils.Spreadsheet('Aircraft Datasheet')
        aircraft_sh.import_file(CSVFile(Path(aircraft_dir, self.registration + '.csv')))
        aircraft_sh_rows = aircraft_sh.get_rows()
        aircraft_data_dict = {}
        for aircraft_sh_row in aircraft_sh_rows:
            aircraft_data_dict[aircraft_sh_row.get_cell(0).txt] = aircraft_sh_row.get_cell(1).txt
        self.model = Airplane(aircraft_data_dict['Model'])
        self.fuel_tank_capacity = aircraft_data_dict['Fuel Tank Capacity']
        self.max_take_off_weight = aircraft_data_dict['Max Takeoff Weight']
        self.basic_empty_weight = aircraft_data_dict['Basic Empty Weight']
        self.arm_datum = aircraft_data_dict['Arm/Datum']

    def print_info(self):
        info_str = (f'Aircraft Registration: {self.registration}\n'
                    f'Model: {self.model.model}\n'
                    f'Fuel Tank Capacity: {self.fuel_tank_capacity}\n'
                    f'Max Takeoff Weight: {self.max_take_off_weight}\n'
                    f'Basic Empty Weight: {self.basic_empty_weight}\n'
                    f'ARM/Datum: {self.arm_datum}')
        print(info_str)


class Airplane:
    def __init__(self, model: str):
        self.model = model
        if model not in {path.name for path in (DATA_DIR / 'airplane').iterdir() if path.is_dir()}:
            raise ValueError(f'Unknown airplane model: {model}')
        self.cfg_folder = self.get_cfg_folder()
        self.cruise_performance_chart: Union[None, planeCruisePerformance.CruisePerformanceChart] = None
        self.set_cruise_performance_chart()
        self.airspeed_calibration_chart: Union[None, planeAirspeedCalibration.AirspeedCalibrationChart] = None
        self.set_airspeed_calibration_chart()

    def get_cfg_folder(self):
        return Path(DATA_DIR, 'airplane', self.model)

    def set_cruise_performance_chart(self):
        cruise_perf_chart_path = Path(self.cfg_folder, 'cruise_performance_chart.csv')
        self.cruise_performance_chart = planeCruisePerformance.CruisePerformanceChart(cruise_perf_chart_path)

    def set_airspeed_calibration_chart(self):
        airspeed_chart_path = Path(self.cfg_folder, 'airspeed_calibration_normal_static_source.csv')
        self.airspeed_calibration_chart = planeAirspeedCalibration.AirspeedCalibrationChart(airspeed_chart_path)


def get_aircraft_dict() -> Dict[str, Aircraft]:
    """
    Get a dictionary of all aircraft as classes
    """
    logUtils.log_msg('Getting Aircraft Dictionary')

    aircraft_file_lst = sorted((DATA_DIR / 'aircraft').glob('*.csv'))

    aircraft_cls_dict: Dict[str, Aircraft] = {}
    for aircraft_file in aircraft_file_lst:
        registration = aircraft_file.stem
        aircraft_cls = Aircraft(registration)
        aircraft_cls_dict[registration] = aircraft_cls

    return aircraft_cls_dict
