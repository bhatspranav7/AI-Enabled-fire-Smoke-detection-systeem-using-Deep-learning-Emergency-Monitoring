/*
 * ESP32 sensor gateway + low-voltage actuator controller (PDF section 12).
 *
 * - reads MQ-2 smoke/gas (analog) and a temperature sensor at a fixed interval
 * - filters readings with a simple moving average
 * - POSTs {"device_id","smoke","temperature","timestamp"} to the backend /sensors
 * - polls /devices/{id}/commands; drives buzzer + isolated relay only on an approved command
 * - heartbeat via the same POST; fails safe (actuators OFF) if the backend is unreachable
 *
 * SAFETY: relay switches an ISOLATED LOW-VOLTAGE prototype load only (LED/mini pump).
 * Never connect to mains, building fire pumps, gas systems or certified suppression gear.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* BACKEND   = "http://192.168.1.10:8000";   // laptop running backend/app.py
const char* DEVICE_ID = "esp32-01";

const int PIN_MQ2    = 34;   // analog
const int PIN_TEMP   = 35;   // analog (LM35) - swap for DHT22/DS18B20 if used
const int PIN_BUZZER = 25;
const int PIN_RELAY  = 26;
const int PIN_LED    = 2;

const unsigned long SAMPLE_MS = 1000;
const unsigned long CMD_MS    = 1000;
const unsigned long FAILSAFE_MS = 15000;   // no backend contact for this long -> actuators off

float smokeAvg = 0, tempAvg = 0;
unsigned long lastSample = 0, lastCmd = 0, lastOk = 0;
bool buzzerOn = false, relayOn = false, estop = false;

void setActuators(bool buzzer, bool relay) {
  if (estop) { buzzer = false; relay = false; }
  digitalWrite(PIN_BUZZER, buzzer ? HIGH : LOW);
  digitalWrite(PIN_RELAY,  relay  ? HIGH : LOW);
  digitalWrite(PIN_LED,    (buzzer || relay) ? HIGH : LOW);
  buzzerOn = buzzer; relayOn = relay;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT); pinMode(PIN_RELAY, OUTPUT); pinMode(PIN_LED, OUTPUT);
  setActuators(false, false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
}

void postSensors() {
  HTTPClient http;
  http.begin(String(BACKEND) + "/sensors");
  http.addHeader("Content-Type", "application/json");
  StaticJsonDocument<200> doc;
  doc["device_id"] = DEVICE_ID; doc["smoke"] = smokeAvg; doc["temperature"] = tempAvg;
  String body; serializeJson(doc, body);
  int code = http.POST(body);
  if (code > 0 && code < 300) lastOk = millis();
  http.end();
}

void pollCommands() {
  HTTPClient http;
  http.begin(String(BACKEND) + "/devices/" + DEVICE_ID + "/commands");
  int code = http.GET();
  if (code == 200) {
    lastOk = millis();
    StaticJsonDocument<1024> doc;
    if (deserializeJson(doc, http.getString()) == DeserializationError::Ok) {
      estop = doc["emergency_stop"] | false;
      for (JsonObject c : doc["commands"].as<JsonArray>()) {
        const char* type = c["type"];
        if (!strcmp(type, "buzzer"))   setActuators(c["on"] | false, relayOn);
        if (!strcmp(type, "actuator")) setActuators(buzzerOn, c["on"] | false);
        if (!strcmp(type, "ack"))      setActuators(false, false);
      }
      if (estop) setActuators(false, false);
    }
  }
  http.end();
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    int raw = analogRead(PIN_MQ2);
    float t = analogRead(PIN_TEMP) * (3.3 / 4095.0) * 100.0;   // LM35: 10 mV / C
    smokeAvg = smokeAvg == 0 ? raw : smokeAvg * 0.7 + raw * 0.3;
    tempAvg  = tempAvg  == 0 ? t   : tempAvg  * 0.7 + t   * 0.3;
    if (WiFi.status() == WL_CONNECTED) postSensors();
  }
  if (now - lastCmd >= CMD_MS) { lastCmd = now; if (WiFi.status() == WL_CONNECTED) pollCommands(); }
  if (now - lastOk > FAILSAFE_MS && (buzzerOn || relayOn)) { setActuators(false, false); Serial.println("FAILSAFE: backend lost, actuators off"); }
}
