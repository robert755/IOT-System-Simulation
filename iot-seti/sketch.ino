#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

const char* MQTT_SERVER = "broker.hivemq.com";
const int   MQTT_PORT   = 1883;
const char* MQTT_USER   = "";
const char* MQTT_PASS   = "";
const char* MQTT_CLIENT = "esp32-seti-001";

// Must be unique and match PREFIX in the Python backend
#define PREFIX "seti2025/grupaX"

const char* TOPIC_TEMP     = PREFIX "/senzor/temperatura";
const char* TOPIC_HUMID    = PREFIX "/senzor/umiditate";
const char* TOPIC_PRES     = PREFIX "/senzor/presiune";
const char* TOPIC_STATUS   = PREFIX "/senzor/status";
const char* TOPIC_FAN      = PREFIX "/cmd/ventilator";
const char* TOPIC_ALARM    = PREFIX "/cmd/alarma";
const char* TOPIC_PRES_CMD = PREFIX "/cmd/presiune";

const unsigned long INTERVAL_MS = 5000;

const float TEMP_ALERT  = 30.0;
const float HUMID_ALERT = 80.0;
const float PRES_LOW    = 975.0;
const float PRES_HIGH   = 1025.0;

const float PRESSURE_MIN = 950.0;
const float PRESSURE_MAX = 1050.0;

const int PIN_DHT_DATA    = 15;
const int PIN_POT_SIG     = 34;
const int PIN_LED_STATUS  = 2;   // green  - heartbeat
const int PIN_LED_FAN     = 4;   // blue   - fan
const int PIN_LED_ALARM   = 5;   // red    - humidity alarm
const int PIN_LED_PRES    = 18;  // yellow - pressure alarm

#define DHT_TYPE  DHT22
DHT dht(PIN_DHT_DATA, DHT_TYPE);

WiFiClient   espClient;
PubSubClient client(espClient);

unsigned long lastPublish = 0;
bool fanState   = false;
bool alarmState = false;
bool presState  = false;

void blink(int pin, int times = 2, int delayMs = 100) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH); delay(delayMs);
    digitalWrite(pin, LOW);  delay(delayMs);
  }
}

void setup_wifi() {
  Serial.print("[WiFi] Conectare la ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.print("\n[WiFi] Conectat! IP: ");
  Serial.println(WiFi.localIP());
  blink(PIN_LED_STATUS, 3);
}

void callback(char* topic, byte* payload, unsigned int length) {
  String t = String(topic);
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  msg.trim(); msg.toUpperCase();

  Serial.print("[MQTT] Comanda primita -> ");
  Serial.print(t); Serial.print(": "); Serial.println(msg);

  if (t == String(TOPIC_FAN)) {
    if (msg == "ON")  { digitalWrite(PIN_LED_FAN, HIGH); fanState = true;  Serial.println("[Ventilator] PORNIT"); }
    if (msg == "OFF") { digitalWrite(PIN_LED_FAN, LOW);  fanState = false; Serial.println("[Ventilator] OPRIT"); }
  }
  else if (t == String(TOPIC_ALARM)) {
    if (msg == "ON")  { digitalWrite(PIN_LED_ALARM, HIGH); blink(PIN_LED_ALARM, 5, 50); alarmState = true; Serial.println("[Alarma] ACTIVATA"); }
    if (msg == "OFF") { digitalWrite(PIN_LED_ALARM, LOW);  alarmState = false; Serial.println("[Alarma] DEZACTIVATA"); }
  }
  else if (t == String(TOPIC_PRES_CMD)) {
    if (msg == "ON")  { digitalWrite(PIN_LED_PRES, HIGH); presState = true;  Serial.println("[Presiune] ALARMA APRINSA"); }
    if (msg == "OFF") { digitalWrite(PIN_LED_PRES, LOW);  presState = false; Serial.println("[Presiune] ALARMA STINSA"); }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("[MQTT] Conectare la broker...");
    bool ok = (strlen(MQTT_USER) > 0)
            ? client.connect(MQTT_CLIENT, MQTT_USER, MQTT_PASS)
            : client.connect(MQTT_CLIENT);
    if (ok) {
      Serial.println(" OK");
      client.subscribe(TOPIC_FAN);
      client.subscribe(TOPIC_ALARM);
      client.subscribe(TOPIC_PRES_CMD);
      Serial.println("[MQTT] Abonat la topicuri de comanda.");
      client.publish(TOPIC_STATUS, "{\"status\":\"online\",\"device\":\"esp32-seti-001\"}");
    } else {
      Serial.print(" esuat, rc="); Serial.print(client.state());
      Serial.println(" -> reincerc in 3s");
      delay(3000);
    }
  }
}

void readAndPublish() {
  float temp  = dht.readTemperature();
  float humid = dht.readHumidity();

  int raw = analogRead(PIN_POT_SIG);
  float pres = PRESSURE_MIN + (raw / 4095.0) * (PRESSURE_MAX - PRESSURE_MIN);

  if (isnan(temp) || isnan(humid)) {
    Serial.println("[Senzor] EROARE citire DHT22!");
    return;
  }

  Serial.printf("[Senzor] T=%.1f C  |  U=%.1f %%  |  P=%.1f hPa\n", temp, humid, pres);

  char buf[128];
  StaticJsonDocument<128> doc;

  doc.clear(); doc["valoare"] = round(temp  * 100) / 100.0; doc["unitate"] = "C";
  serializeJson(doc, buf); client.publish(TOPIC_TEMP, buf);

  doc.clear(); doc["valoare"] = round(humid * 100) / 100.0; doc["unitate"] = "%";
  serializeJson(doc, buf); client.publish(TOPIC_HUMID, buf);

  doc.clear(); doc["valoare"] = round(pres  * 100) / 100.0; doc["unitate"] = "hPa";
  serializeJson(doc, buf); client.publish(TOPIC_PRES, buf);

  if (temp > TEMP_ALERT && !fanState) {
    client.publish(TOPIC_FAN, "ON"); digitalWrite(PIN_LED_FAN, HIGH); fanState = true;
    Serial.printf("[AUTO] T=%.1f C > %.0f -> Ventilator PORNIT\n", temp, TEMP_ALERT);
  } else if (temp <= TEMP_ALERT && fanState) {
    client.publish(TOPIC_FAN, "OFF"); digitalWrite(PIN_LED_FAN, LOW); fanState = false;
    Serial.printf("[AUTO] T=%.1f C <= %.0f -> Ventilator OPRIT\n", temp, TEMP_ALERT);
  }

  if (humid > HUMID_ALERT && !alarmState) {
    client.publish(TOPIC_ALARM, "ON"); digitalWrite(PIN_LED_ALARM, HIGH); alarmState = true;
    Serial.printf("[AUTO] U=%.1f %% > %.0f -> Alarma ACTIVATA\n", humid, HUMID_ALERT);
  } else if (humid <= HUMID_ALERT && alarmState) {
    client.publish(TOPIC_ALARM, "OFF"); digitalWrite(PIN_LED_ALARM, LOW); alarmState = false;
    Serial.printf("[AUTO] U=%.1f %% <= %.0f -> Alarma DEZACTIVATA\n", humid, HUMID_ALERT);
  }

  bool presAnormala = (pres < PRES_LOW || pres > PRES_HIGH);
  if (presAnormala && !presState) {
    client.publish(TOPIC_PRES_CMD, "ON"); digitalWrite(PIN_LED_PRES, HIGH); presState = true;
    Serial.printf("[AUTO] P=%.1f hPa anormala -> LED presiune APRINS\n", pres);
  } else if (!presAnormala && presState) {
    client.publish(TOPIC_PRES_CMD, "OFF"); digitalWrite(PIN_LED_PRES, LOW); presState = false;
    Serial.printf("[AUTO] P=%.1f hPa normala -> LED presiune STINS\n", pres);
  }

  blink(PIN_LED_STATUS, 1, 40);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_STATUS, OUTPUT);
  pinMode(PIN_LED_FAN, OUTPUT);
  pinMode(PIN_LED_ALARM, OUTPUT);
  pinMode(PIN_LED_PRES, OUTPUT);

  Serial.println("==================================================");
  Serial.println("  Nod IoT industrial - ESP32 / Wokwi");
  Serial.println("==================================================");

  dht.begin();
  setup_wifi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();
  if (millis() - lastPublish >= INTERVAL_MS) {
    lastPublish = millis();
    readAndPublish();
  }
}
