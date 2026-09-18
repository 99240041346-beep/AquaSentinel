# ESP32 setup
DS18B20: VCC to 3V3, GND to GND, DATA to P4/GPIO4. Add 4.7k pull-up DATA to 3V3 if needed.
pH module: VCC to 5V/VIN, GND to GND, PO/AO to P35/GPIO35. DO unused.
Turbidity module: VCC to 5V/VIN, GND to GND, AO to P34/GPIO34.
IMPORTANT: P34/P35 are ESP32 ADC inputs and must not receive more than 3.3V. Verify the sensor analog output or use a suitable divider before connecting.
The pH and turbidity formulas are prototype conversions and must be calibrated with known standards before real aquaculture decisions.
Install OneWire, DallasTemperature and the ESP32 board package. Edit Wi-Fi, API URL and DEVICE_API_KEY in the .ino file.