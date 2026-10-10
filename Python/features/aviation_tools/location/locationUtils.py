from typing import *
from pathlib import Path
from commonUtils.formats import spreadsheets as shUtils
from commonUtils.formats.csvType import CSVFile
from features.aviation_tools.mathUtils.flightUtils import *
from features.aviation_tools.resources import DATA_DIR
from commonUtils.runtime import logging as logUtils


class Airport:
    def __init__(self,
                 name: str,
                 iata: str,
                 coord: Coordinate,
                 magnetic_deviation: MagneticDeviation,
                 altitude: int):
        self.name = name
        self.iata = iata
        self.coord = coord
        self.magnetic_deviation = magnetic_deviation
        self.altitude: int = altitude

    def print_info(self):
        info_str = (f'Airport Name: {self.name}\n'
                    f'IATA Code: {self.iata}\n'
                    f'Coordinate: {self.coord.get_info()}\n'
                    f'Magnetic Deviation: {self.magnetic_deviation.get_info()}\n'
                    f'Altitude: {self.altitude}FT ASL')
        print(info_str)


def get_airport_dict() -> Dict[str, Airport]:
    """
    Get a dictionary of all airports as classes
    """
    logUtils.log_msg('Getting Airports Dictionary')

    airports_csv_path = Path(DATA_DIR, 'airports.csv')
    airports_sh = shUtils.Spreadsheet('Airports Datasheet')
    airports_sh.import_file(CSVFile(airports_csv_path))
    airport_rows = airports_sh.get_rows()

    airports_cls_dict: Dict[str, Airport] = {}
    for airport_row in airport_rows[1:]:  # Skip first row since it's just headers

        # Create additional classes
        coordinate = Coordinate(airport_row.get_cell(2).txt, airport_row.get_cell(3).txt)
        magnetic_deviation = MagneticDeviation(airport_row.get_cell(4).txt, airport_row.get_cell(5).txt)

        airport_cls = Airport(name=airport_row.get_cell(0).txt,
                              iata=airport_row.get_cell(1).txt,
                              coord=coordinate,
                              magnetic_deviation=magnetic_deviation,
                              altitude=airport_row.get_cell(6).txt)

        airports_cls_dict[airport_cls.name] = airport_cls

    return airports_cls_dict


def get_airport_from_iata(iata: str):
    """
    Get airport from IATA
    """
    airport_dict = get_airport_dict()
    for airport in airport_dict.values():
        if airport.iata.casefold() == iata.strip().casefold():
            return airport
    raise ValueError(f'Unknown airport: {iata}')
