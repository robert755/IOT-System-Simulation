import os
from datetime import datetime

import paho.mqtt.publish as publish
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient, DESCENDING

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB  = os.getenv("MONGO_DB", "seti_iot")

MQTT_SERVER = os.getenv("MQTT_SERVER", "broker.hivemq.com")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER   = os.getenv("MQTT_USER", "")
MQTT_PASS   = os.getenv("MQTT_PASS", "")

PREFIX = os.getenv("PREFIX", "seti2025/grupaX")
TOPIC_FAN   = f"{PREFIX}/cmd/ventilator"
TOPIC_ALARM = f"{PREFIX}/cmd/alarma"
TOPIC_PRES_CMD = f"{PREFIX}/cmd/presiune"

app = Flask(__name__)
CORS(app)

mongo = MongoClient(MONGO_URI)
db = mongo[MONGO_DB]
col_istoric = db["istoric"]
col_events  = db["events"]


def _serialize(doc):
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("data"), datetime):
        doc["data"] = doc["data"].isoformat()
    return doc


@app.route("/api/latest")
def latest():
    out = {}
    for tip in ("temperatura", "umiditate", "presiune"):
        d = col_istoric.find_one({"tip": tip}, sort=[("data", DESCENDING)])
        out[tip] = _serialize(d) if d else None
    return jsonify(out)


@app.route("/api/readings/<tip>")
def readings(tip):
    n = int(request.args.get("n", 100))
    cur = col_istoric.find({"tip": tip}).sort("data", DESCENDING).limit(n)
    data = [_serialize(d) for d in cur]
    data.reverse()  # chronological order for charts
    return jsonify(data)


@app.route("/api/stats/<tip>")
def stats(tip):
    n = int(request.args.get("n", 20))
    cur = col_istoric.find({"tip": tip}).sort("data", DESCENDING).limit(n)
    valori = [d["valoare"] for d in cur]
    if not valori:
        return jsonify(None)
    return jsonify({
        "medie": round(sum(valori) / len(valori), 2),
        "min": round(min(valori), 2),
        "max": round(max(valori), 2),
        "count": len(valori),
    })


@app.route("/api/events")
def events():
    n = int(request.args.get("n", 30))
    cur = col_events.find().sort("data", DESCENDING).limit(n)
    return jsonify([_serialize(d) for d in cur])


@app.route("/api/control", methods=["POST"])
def control():
    body = request.get_json(force=True)
    tinta = body.get("tinta")
    stare = str(body.get("stare", "")).upper()

    topic = {"ventilator": TOPIC_FAN, "alarma": TOPIC_ALARM, "presiune": TOPIC_PRES_CMD}.get(tinta)
    if topic is None or stare not in ("ON", "OFF"):
        return jsonify({"ok": False, "mesaj": "Parametri invalizi"}), 400

    auth = {"username": MQTT_USER, "password": MQTT_PASS} if MQTT_USER else None
    try:
        publish.single(topic, stare, hostname=MQTT_SERVER, port=MQTT_PORT, auth=auth)
        return jsonify({"ok": True, "mesaj": f"{tinta} -> {stare}"})
    except Exception as e:
        return jsonify({"ok": False, "mesaj": str(e)}), 500


@app.route("/")
def index():
    return jsonify({"serviciu": "API REST IoT SETI", "status": "activ"})


if __name__ == "__main__":
    print("[API] Pornire pe http://0.0.0.0:5000 ...")
    app.run(host="0.0.0.0", port=5000, debug=False)
