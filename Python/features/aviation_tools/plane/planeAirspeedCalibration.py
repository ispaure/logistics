from commonUtils import spreadsheetUtils as shUtils
from commonUtils.fileTypes.csvType import CSVFile


class AirspeedCalibrationEntry:
    def __init__(self, kias: float, flaps: float, kcas: float):
        self.kias = kias
        self.flaps = flaps
        self.kcas = kcas


class AirspeedCalibrationChart:
    def __init__(self, path):
        self.path = path
        self.entries_lst = []
        self.import_entries()

    def import_entries(self):
        sh = shUtils.Spreadsheet('Cruise Performance Chart')
        sh.import_file(CSVFile(self.path))
        for row in sh.get_rows()[1:]:  # Skip first row which is just headers
            entry_cls = AirspeedCalibrationEntry(kias=float(row.get_cell(0).txt),
                                                 flaps=float(row.get_cell(1).txt),
                                                 kcas=float(row.get_cell(2).txt))
            self.entries_lst.append(entry_cls)

    def get_kcas(self, kias: float, flaps: float = 0):

        # Get entries with same flaps variable
        same_flaps_entries = []
        for entry in self.entries_lst:
            if entry.flaps == flaps:
                same_flaps_entries.append(entry)

        # Sort entries
        same_flaps_entries.sort(key=lambda x: x.kias)

        for i in range(len(same_flaps_entries) - 1):
            entry1 = same_flaps_entries[i]
            entry2 = same_flaps_entries[i + 1]

            # Check if the kias_value lies between the current range
            if entry1.kias <= kias <= entry2.kias:
                # Linear interpolation formula
                kcas_value = entry1.kcas + (kias - entry1.kias) * (
                        (entry2.kcas - entry1.kcas) / (entry2.kias - entry1.kias)
                )
                return kcas_value
        return None
