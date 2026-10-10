from commonUtils.formats import spreadsheets as shUtils
from commonUtils.formats.csvType import CSVFile
from commonUtils.runtime import logging as logUtils
from features.aviation_tools.mathUtils import weatherUtils
from features.aviation_tools.mathUtils import mathStuff


class CruisePerformanceChartEntry:
    def __init__(self,
                 pressure_altitude: float,
                 rpm: float,
                 temperature: float,
                 percent_bhp: float,
                 true_air_speed: float,
                 cons_gallons_per_hour: float):

        self.pressure_altitude = pressure_altitude
        self.rpm = rpm
        self.temperature = temperature
        self.percent_bhp = percent_bhp
        self.true_air_speed = true_air_speed
        self.cons_gallon_per_hour = cons_gallons_per_hour

    def print_info(self):
        info_str = (f'Pressure Altitude: {self.pressure_altitude}\n'
                    f'RPM: {self.rpm}\n'
                    f'Temperature: {self.temperature}\n'
                    f'% BHP: {self.percent_bhp}\n'
                    f'True Air Speed (KTAS): {self.true_air_speed}\n'
                    f'Consumption (GPH): {self.cons_gallon_per_hour}')


class CruisePerformanceChart:
    def __init__(self, path):
        self.path = path
        self.entries_lst = []
        self.import_entries()

    def import_entries(self):
        sh = shUtils.Spreadsheet('Cruise Performance Chart')
        sh.import_file(CSVFile(self.path))
        for row in sh.get_rows()[1:]:

            if not self.__performance_chart_row_valid(row):
                continue

            # Get the chart's temperature reading and convert to Celsius
            temp = weatherUtils.convert_isa_str_to_temp(row.get_cell(2).txt)

            # Create Cruise Performance Chart Entry
            entry_cls = CruisePerformanceChartEntry(pressure_altitude=float(row.get_cell(0).txt),
                                                    rpm=float(row.get_cell(1).txt),
                                                    temperature=float(temp),
                                                    percent_bhp=float(row.get_cell(3).txt),
                                                    true_air_speed=float(row.get_cell(4).txt),
                                                    cons_gallons_per_hour=float(row.get_cell(5).txt))

            self.entries_lst.append(entry_cls)

    def __performance_chart_row_valid(self, row: shUtils.Row):
        # Values that will be fetched later
        percent_bhp = row.get_cell(3).txt
        true_air_speed = row.get_cell(4).txt
        cons_gallons_per_hour = row.get_cell(5).txt
        # Make sure values that will be output are digits
        if mathStuff.is_number(percent_bhp) and mathStuff.is_number(true_air_speed) and mathStuff.is_number(cons_gallons_per_hour):
            return True
        else:
            return False

    def get_cruise_performance(self, pressure_altitude: float, rpm: float, ground_temp: float, method: str = 'Closest'):
        """
        Get the cruise performance from given parameters
        :param pressure_altitude: Pressure Altitude
        :param rpm: Engine's cruising RPM
        :param ground_temp: Temperature ASL
        :param method: Method to use to calculate cruise performance. Current option is only closest, which takes the
        values that are the closest to the inputs from the cruise performance chart from the airplane's POH
        """

        if method == 'Closest':
            # FIND CLOSEST VALUES
            # Pressure Altitude
            pressure_altitude_lst = self.get_entry_pressure_altitude_lst()
            closest_pressure_altitude = min(pressure_altitude_lst, key=lambda x: abs(x - pressure_altitude))
            logUtils.log_msg(f'Closest Pressure Altitude: {closest_pressure_altitude}')
            # Temperature
            temp_at_altitude = weatherUtils.get_temperature_at_altitude(ground_temp, closest_pressure_altitude)
            temp_lst = self.get_entry_temperature_lst()
            closest_temp = min(temp_lst, key=lambda x: abs(x-temp_at_altitude))
            logUtils.log_msg(f'Closest Ground Temperature: {closest_temp}')
            # RPM
            rpm_lst = self.get_rpm_lst()
            closest_rpm = min(rpm_lst, key=lambda x: abs(x-rpm))
            logUtils.log_msg(f'Closest RPM: {closest_rpm}')

            # FIND ENTRY
            for entry in self.entries_lst:
                if closest_pressure_altitude == entry.pressure_altitude:
                    if closest_temp == entry.temperature:
                        if closest_rpm == entry.rpm:
                            return entry
            return None

        else:
            raise ValueError(f'Cruise performance method {method} is invalid!')

    def get_entry_pressure_altitude_lst(self):
        pressure_altitude_lst = []
        for entry in self.entries_lst:
            if entry.pressure_altitude not in pressure_altitude_lst:
                pressure_altitude_lst.append(entry.pressure_altitude)
        return pressure_altitude_lst

    def get_entry_temperature_lst(self):
        temperature_lst = []
        for entry in self.entries_lst:
            if entry.temperature not in temperature_lst:
                temperature_lst.append(entry.temperature)
        return temperature_lst

    def get_rpm_lst(self):
        rpm_lst = []
        for entry in self.entries_lst:
            if entry.rpm not in rpm_lst:
                rpm_lst.append(entry.rpm)
        return rpm_lst

    def get_power_settings_available(self):
        pass
