# Aviation Tools

Open the **Aviation Tools** tab in Logistics. If it is hidden, enable
**Aviation Tools** under **Settings → Features**. This toggle lasts until restart.

Select a calculator button to open its window. Several tools can remain open
at once; closing and reopening a tool keeps its inputs for the session.
Enter values using the units beside each field, then select
**Calculate** or press Enter in a text field. Results appear below the button and
can be selected and copied. An invalid input displays an error there; correct it
and calculate again.

- **Distance:** decimal-degree coordinates → nautical miles.
- **Course:** coordinates and east/west magnetic deviation → true and magnetic course.
- **Wind / Headings:** true course, true airspeed, wind direction/speed and an airport
  → wind correction and true/magnetic headings, using stored airport deviation.
- **Ground Speed:** course, airspeed and wind → the original vector speed estimate.
- **KTAS → KIAS:** the original approximation supports only **2,000 ft**.
- **KIAS → KCAS:** choose a supplied aircraft and enter an indicated airspeed within
  its chart range. Uses linear interpolation and **flaps up**.
- **Cruise Performance:** choose an aircraft, pressure altitude, RPM and sea-level
  temperature. Returns the nearest chart row's power, airspeed and fuel consumption;
  the selected row is shown alongside the results.

Select **Aircraft / Airports** to open the reference window, then choose a dataset to view its read-only table.
The supplied data includes five aircraft, four airports and charts for C172M and
C172N models. Dataset files live in the feature's `data` directory; editing those
files requires restarting Logistics to refresh the selections.

These are the existing Flight Tools formulas and historical reference data.
Wind calculations retain the original vector approximation; cruise performance
uses nearest chart values, and the airspeed conversion has the limit described
above. This migration does not validate or update the original calculations or
reference data. The old project's planned weight-and-balance, flight-plan,
logbook and PDF-export tools were not implemented and are not included.

[Back to the Logistics user guide](../../../../USER_GUIDE.md)
