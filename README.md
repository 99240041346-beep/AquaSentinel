# AquaSentinel
IoT-enabled real-time water-quality monitoring for aquaculture.

Architecture: ESP32 + sensors -> HTTPS REST API -> PostgreSQL/SQLite -> private Flask dashboard -> charts and alerts.

Features: private login, password hashing, device API-key authentication, live readings, historical chart, configurable thresholds, alert history, browser notifications while dashboard is open, PostgreSQL on Render, SQLite fallback, ESP32 firmware and health endpoint.

Sensors: DS18B20 waterproof temperature, pH interface and turbidity interface.

Local: create a Python virtual environment, install requirements.txt, set ADMIN_USERNAME, ADMIN_PASSWORD and DEVICE_API_KEY, then run python app.py. Open http://127.0.0.1:5000.

Render: use the included render.yaml. Set ADMIN_PASSWORD in Render. Render generates SECRET_KEY and DEVICE_API_KEY.

ESP32 API: POST /api/readings with header X-Device-Key and JSON containing temperature, ph and turbidity.

Prototype defaults: temperature 20-32 C, pH 6.5-8.5 and turbidity <=50 NTU. Change these to values appropriate to the species, pond and measurement method.

Never commit Wi-Fi passwords or API keys.