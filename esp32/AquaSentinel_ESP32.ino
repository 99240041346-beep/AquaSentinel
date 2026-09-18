#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
const char* WIFI_SSID="YOUR_WIFI_NAME";
const char* WIFI_PASSWORD="YOUR_WIFI_PASSWORD";
const char* API_URL="https://YOUR-RENDER-SERVICE.onrender.com/api/readings";
const char* DEVICE_API_KEY="YOUR_RENDER_DEVICE_API_KEY";
#define TEMP_PIN 4
#define TURBIDITY_PIN 34
#define PH_PIN 35
OneWire oneWire(TEMP_PIN); DallasTemperature tempSensor(&oneWire);
unsigned long lastSend=0; const unsigned long SEND_EVERY_MS=10000;
float readPH(){int raw=analogRead(PH_PIN);float v=(raw/4095.0)*3.3;return 7.0+(2.50-v)*3.0;}
float readTurbidity(){int raw=analogRead(TURBIDITY_PIN);float v=(raw/4095.0)*3.3;return max(0.0f,(3.3-v)*100.0f);}
void setup(){Serial.begin(115200);analogReadResolution(12);analogSetPinAttenuation(PH_PIN,ADC_11db);analogSetPinAttenuation(TURBIDITY_PIN,ADC_11db);tempSensor.begin();WiFi.begin(WIFI_SSID,WIFI_PASSWORD);while(WiFi.status()!=WL_CONNECTED){delay(500);Serial.print(".");}Serial.println(WiFi.localIP());}
void loop(){if(millis()-lastSend<SEND_EVERY_MS)return;lastSend=millis();tempSensor.requestTemperatures();float t=tempSensor.getTempCByIndex(0),p=readPH(),tu=readTurbidity();if(WiFi.status()!=WL_CONNECTED){WiFi.reconnect();return;}HTTPClient http;http.begin(API_URL);http.addHeader("Content-Type","application/json");http.addHeader("X-Device-Key",DEVICE_API_KEY);String body="{\"temperature\":"+String(t,2)+",\"ph\":"+String(p,2)+",\"turbidity\":"+String(tu,2)+"}";int code=http.POST(body);Serial.printf("POST %d %s\n",code,body.c_str());http.end();}