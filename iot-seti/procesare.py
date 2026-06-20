import json
import os
import time
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()

MQTT_SERVER = os.getenv("MQTT_SERVER", "broker.hivemq.com")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER   = os.getenv("MQTT_USER", "")
MQTT_PASS   = os.getenv("MQTT_PASS", "")
MQTT_CLIENT = os.getenv("MQTT_CLIENT", "python-backend-001")

PREFIX = os.getenv("PREFIX", "seti2025/grupaX")
TOPIC_TEMP   = f"{PREFIX}/senzor/temperatura"
TOPIC_HUMID  = f"{PREFIX}/senzor/umiditate"
TOPIC_PRES   = f"{PREFIX}/senzor/presiune"
TOPIC_STATUS = f"{PREFIX}/senzor/status"
TOPIC_FAN      = f"{PREFIX}/cmd/ventilator"
TOPIC_ALARM    = f"{PREFIX}/cmd/alarma"
TOPIC_PRES_CMD = f"{PREFIX}/cmd/presiune"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB  = os.getenv("MONGO_DB", "seti_iot")

TEMP_MAX  = 30.0
TEMP_MIN  = 15.0
HUMID_MAX = 80.0
HUMID_MIN = 20.0
PRES_LOW  = 975.0
PRES_HIGH = 1025.0

ENABLE_EMAIL = os.getenv("ENABLE_EMAIL", "False").lower() == "true"
SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASS", "")
EMAIL_TO     = os.getenv("EMAIL_TO", "")
EMAIL_COOLDOWN = int(os.getenv("EMAIL_COOLDOWN", "10"))

mongo = MongoClient(MONGO_URI)
db = mongo[MONGO_DB]
col_istoric = db["istoric"]
col_events  = db["events"]


def salveaza_citire(tip, valoare, unitate, device="esp32-seti-001"):
    col_istoric.insert_one({
        "tip": tip,
        "valoare": float(valoare),
        "unitate": unitate,
        "device": device,
        "data": datetime.now(timezone.utc),
    })


def salveaza_event(tip, mesaj, valoare=None):
    col_events.insert_one({
        "tip": tip,
        "mesaj": mesaj,
        "valoare": valoare,
        "data": datetime.now(timezone.utc),
    })


def get_statistici(tip, ultimele_n=20):
    cur = col_istoric.find({"tip": tip}).sort("data", DESCENDING).limit(ultimele_n)
    valori = np.array([d["valoare"] for d in cur], dtype=float)
    if valori.size == 0:
        return None
    return {
        "medie": round(float(np.mean(valori)), 2),
        "min":   round(float(np.min(valori)), 2),
        "max":   round(float(np.max(valori)), 2),
        "std":   round(float(np.std(valori)), 2),
        "count": int(valori.size),
    }


_last_email = {}

def trimite_email(subiect, corp, tip="general"):
    if not ENABLE_EMAIL:
        return
    now = time.time()
    if now - _last_email.get(tip, 0) < EMAIL_COOLDOWN:
        return  # throttle alerts of the same type
    _last_email[tip] = now
    try:
        msg = MIMEText(corp, _charset="utf-8")
        msg["Subject"] = subiect
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        print(f"  [EMAIL] Trimis: {subiect}")
    except Exception as e:
        print(f"  [EMAIL] Eroare: {e}")


_fan_state   = False
_alarm_state = False
_pres_state  = False

def logica_control(client, tip, valoare):
    global _fan_state, _alarm_state, _pres_state

    if tip == "temperatura":
        if valoare > TEMP_MAX and not _fan_state:
            client.publish(TOPIC_FAN, "ON")
            _fan_state = True
            m = f"ALERTA: Temperatura {valoare} C > {TEMP_MAX} C -> Ventilator PORNIT"
            print(f"  [CONTROL] {m}"); salveaza_event("cmd_fan_on", m, valoare)
            trimite_email("[IoT] Temperatura ridicata", m, "temp_max")
        elif valoare <= TEMP_MAX and _fan_state:
            client.publish(TOPIC_FAN, "OFF")
            _fan_state = False
            m = f"INFO: Temperatura normalizata {valoare} C -> Ventilator OPRIT"
            print(f"  [CONTROL] {m}"); salveaza_event("cmd_fan_off", m, valoare)
        if valoare < TEMP_MIN:
            m = f"ALERTA: Temperatura prea scazuta! {valoare} C < {TEMP_MIN} C"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_temp_scazuta", m, valoare)
            trimite_email("[IoT] Temperatura scazuta", m, "temp_min")

    elif tip == "umiditate":
        if valoare > HUMID_MAX and not _alarm_state:
            client.publish(TOPIC_ALARM, "ON")
            _alarm_state = True
            m = f"ALERTA: Umiditate {valoare}% > {HUMID_MAX}% -> Alarma ACTIVATA"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_umiditate_mare", m, valoare)
            trimite_email("[IoT] Umiditate ridicata", m, "humid_max")
        elif valoare <= HUMID_MAX and _alarm_state:
            client.publish(TOPIC_ALARM, "OFF")
            _alarm_state = False
            m = f"INFO: Umiditate normalizata {valoare}% -> Alarma DEZACTIVATA"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_off", m, valoare)
        if valoare < HUMID_MIN:
            m = f"ALERTA: Umiditate prea scazuta! {valoare}% < {HUMID_MIN}%"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_umiditate_mica", m, valoare)

    elif tip == "presiune":
        anormala = valoare < PRES_LOW or valoare > PRES_HIGH
        if anormala and not _pres_state:
            client.publish(TOPIC_PRES_CMD, "ON")
            _pres_state = True
            m = f"ALERTA: Presiune anormala {valoare} hPa -> LED presiune APRINS"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_presiune_on", m, valoare)
            trimite_email("[IoT] Presiune anormala", m, "presiune")
        elif not anormala and _pres_state:
            client.publish(TOPIC_PRES_CMD, "OFF")
            _pres_state = False
            m = f"INFO: Presiune normalizata {valoare} hPa -> LED presiune STINS"
            print(f"  [CONTROL] {m}"); salveaza_event("alarma_presiune_off", m, valoare)


def on_connect(client, userdata, flags, rc):
    coduri = {0: "Conectat", 1: "Protocol gresit", 2: "Client ID invalid",
              3: "Server indisponibil", 4: "Credentiale gresite", 5: "Neautorizat"}
    print(f"[MQTT] on_connect rc={rc}: {coduri.get(rc, 'Necunoscut')}")
    if rc == 0:
        for t in (TOPIC_TEMP, TOPIC_HUMID, TOPIC_PRES, TOPIC_STATUS):
            client.subscribe(t)
        print("[MQTT] Abonat la topicurile de date.")


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    ts = datetime.now().strftime("%H:%M:%S")

    if topic in (TOPIC_FAN, TOPIC_ALARM, TOPIC_PRES_CMD):  # skip our own commands
        return

    if topic == TOPIC_STATUS:
        print(f"[{ts}] Device online: {payload}")
        return

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        print(f"[{ts}] Payload invalid pe {topic}: {payload}")
        return

    valoare = data.get("valoare")
    unitate = data.get("unitate", "?")
    if valoare is None:
        return

    tip = {TOPIC_TEMP: "temperatura",
           TOPIC_HUMID: "umiditate",
           TOPIC_PRES: "presiune"}.get(topic)
    if tip is None:
        return

    simbol = {"temperatura": "T", "umiditate": "U", "presiune": "P"}[tip]
    print(f"[{ts}] {simbol}: {valoare} {unitate}")

    salveaza_citire(tip, valoare, unitate)

    total = col_istoric.count_documents({"tip": tip})
    if total % 10 == 0:
        s = get_statistici(tip, 20)
        if s:
            print(f"  [STATS] {tip}: medie={s['medie']} min={s['min']} "
                  f"max={s['max']} std={s['std']} (n={s['count']})")

    logica_control(client, tip, valoare)


if __name__ == "__main__":
    print("=" * 60)
    print("  Backend Procesare IoT  -  MQTT + MongoDB + NumPy")
    print("=" * 60)
    print(f"[DB]  MongoDB: {MONGO_URI} / baza '{MONGO_DB}'")

    col_istoric.create_index([("tip", 1), ("data", DESCENDING)])
    col_events.create_index([("data", DESCENDING)])

    client = mqtt.Client(client_id=MQTT_CLIENT)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[MQTT] Conectare la {MQTT_SERVER}:{MQTT_PORT} ...")
    client.connect(MQTT_SERVER, MQTT_PORT, keepalive=60)

    print("[MQTT] Backend activ. Ascult date de la senzori...\n")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Oprit de utilizator.")
        client.disconnect()
