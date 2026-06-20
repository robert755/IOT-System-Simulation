# 🏭 Industrial IoT Monitoring & Automation System
### SETI Project — full architecture (Wokwi C/C++ · MQTT · MongoDB · REST API · Dashboard)

An end-to-end IoT pipeline: an ESP32 node reads environmental sensors and publishes
them over MQTT; a Python backend stores the data in MongoDB, runs real-time analysis
with NumPy, applies industrial control logic and sends e-mail alerts; a Flask REST API
exposes the data; and a Streamlit dashboard visualizes everything and allows remote control.

---

## 1. Project structure

```
iot-seti/
├── sketch.ino          → IoT node — ESP32 / Arduino C++ (Wokwi)
├── diagram.json        → Wokwi circuit schematic (DHT22 + potentiometer + 3 LEDs)
├── libraries.txt       → Wokwi libraries (auto-installed)
├── procesare.py        → Processing backend: MQTT → MongoDB + NumPy + e-mail
├── api.py              → REST API backend (Flask) over MongoDB
├── dashboard.py        → Web frontend (Streamlit) — reads through the REST API
├── requirements.txt    → Python dependencies
├── Dockerfile          → Container image for all 3 Python services
├── docker-compose.yml  → Orchestrates procesare + api + dashboard
├── .env                → Real secrets (NOT committed — git-ignored)
├── .env.example        → Template for the environment variables
└── README.md           → This file
```

---

## 2. Configuration & secrets (`.env`)

All credentials and connection settings live in a **`.env` file** that is **never committed
to GitHub** (it is listed in `.gitignore`). The Python code reads them at runtime via
`python-dotenv` / `os.getenv(...)`.

### First-time setup

```bash
cp .env.example .env      # Linux/macOS
copy .env.example .env    # Windows
```

Then open `.env` and fill in your own values. Variables:

| Variable | Description |
|---|---|
| `MONGO_URI` | MongoDB connection string (local or Atlas) |
| `MONGO_DB` | Database name (default `seti_iot`) |
| `MQTT_SERVER` / `MQTT_PORT` | MQTT broker host and port |
| `MQTT_USER` / `MQTT_PASS` | MQTT credentials (leave empty for anonymous) |
| `MQTT_CLIENT` | MQTT client id for the backend |
| `PREFIX` | Topic prefix — **make it unique** on a public broker |
| `ENABLE_EMAIL` | `True`/`False` — toggle e-mail alerting |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server (Gmail: `smtp.gmail.com:587`) |
| `SMTP_USER` / `SMTP_PASS` | SMTP login (Gmail: use an **App Password**) |
| `EMAIL_TO` | Alert recipient |
| `EMAIL_COOLDOWN` | Seconds between two alerts of the same type |

> ⚠️ **Never put real credentials back into the `.py` files.** Keep them in `.env` only.
> If a secret was previously pushed to GitHub, rotate it (change the password / revoke
> the App Password) — git history keeps old versions.

> Note: `sketch.ino` runs on the device (Wokwi) and cannot read a `.env` file, so its
> Wi-Fi/MQTT settings stay in the sketch. Make sure its `MQTT_SERVER` and `PREFIX` match
> the values in your `.env`.

---

## 3. Data flow

```
[ESP32 / Wokwi]
   │  DHT22 + potentiometer
   │  publish MQTT
   ▼
[MQTT broker: Mosquitto on VM  or  public broker]
   │  subscribe
   ▼
[procesare.py] ──── writes ────► [MongoDB: seti_iot]
   │  (NumPy: mean/min/max/std)        │
   │  automatic control + e-mail       │ reads
   │  publish MQTT (cmd)               ▼
   ▼                              [api.py — Flask REST]
[ESP32 / LEDs]                         │ JSON
                                       ▼
                                [dashboard.py — Streamlit]
                                       │ POST /api/control
                                       ▼  (publish MQTT → ESP32)
```

---

## 4. Running the project

### Option A — Docker (all backend services at once)

The `docker-compose.yml` builds the image and starts the three Python services. It loads
your secrets from `.env` via `env_file`.

```bash
docker compose up --build
```

- API:        http://localhost:5000
- Dashboard:  http://localhost:8501

### Option B — natively (3 terminals)

```bash
pip install -r requirements.txt

# Terminal 1 — processing + storage + control
python procesare.py

# Terminal 2 — REST API
python api.py            # http://localhost:5000

# Terminal 3 — dashboard
streamlit run dashboard.py   # http://localhost:8501
```

> Quick API check: `curl http://localhost:5000/api/latest`

### The IoT node (Wokwi)

1. Go to https://wokwi.com → **New Project** → **ESP32**.
2. Replace `sketch.ino` and `diagram.json` with the files from this project.
3. Add `libraries.txt` (the "+" button) — Wokwi installs the libraries automatically.
4. Set `MQTT_SERVER` and `PREFIX` in `sketch.ino` (must match your `.env`).
5. ▶ **Run** → the Serial Monitor shows the published data.
6. Move the potentiometer to vary "pressure"; change the DHT22 temperature (click the
   sensor) to trigger the fan.

---

## 5. MQTT broker setup

You must use the **same broker and the same `PREFIX`** in `sketch.ino` and in `.env`.

### Public broker (quick demo)
Works instantly, no account. Default:
```
MQTT_SERVER=broker.hivemq.com
MQTT_PORT=1883
```
> ⚠️ The public broker is shared. **Change `PREFIX`** (e.g. `seti2025/your_name`) so your
> data does not mix with other users.

### Local Mosquitto on a VM
```bash
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
echo -e "listener 1883 0.0.0.0\nallow_anonymous true" | sudo tee /etc/mosquitto/conf.d/seti.conf
sudo systemctl restart mosquitto
```
Then set `MQTT_SERVER` in `.env` to the VM's IP.

---

## 6. MongoDB setup

- **Local:** `MONGO_URI=mongodb://localhost:27017/`
- **Atlas (free cloud):** create a free M0 cluster at https://www.mongodb.com/atlas, then
  `MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?appName=Cluster0`

---

## 7. MQTT topics

| Topic (`<PREFIX>/...`) | Direction | Payload |
|---|---|---|
| `/senzor/temperatura` | ESP32 → Python | `{"valoare":24.5,"unitate":"C"}` |
| `/senzor/umiditate` | ESP32 → Python | `{"valoare":55.0,"unitate":"%"}` |
| `/senzor/presiune` | ESP32 → Python | `{"valoare":1013.2,"unitate":"hPa"}` |
| `/senzor/status` | ESP32 → Python | `{"status":"online"}` |
| `/cmd/ventilator` | Python/API → ESP32 | `ON` / `OFF` |
| `/cmd/alarma` | Python/API → ESP32 | `ON` / `OFF` |
| `/cmd/presiune` | Python/API → ESP32 | `ON` / `OFF` (pressure LED) |

### Automatic control logic
| Condition | Action |
|---|---|
| Temperature > 30 °C | fan `ON` + log + e-mail |
| Temperature ≤ 30 °C | fan `OFF` |
| Temperature < 15 °C | log alert + e-mail |
| Humidity > 80 % | alarm `ON` + log + e-mail |
| Humidity ≤ 80 % | alarm `OFF` |
| Pressure < 975 or > 1025 hPa | pressure alarm + log |

---

## 8. REST API endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api/latest` | Latest value for each sensor type |
| GET | `/api/readings/<type>?n=100` | Last N readings for a type |
| GET | `/api/stats/<type>?n=20` | Statistics (mean/min/max/std) |
| GET | `/api/events?n=30` | Alarm / command log |
| POST | `/api/control` | Send a command over MQTT — body: `{"tinta":"ventilator","stare":"ON"}` |

---

## 9. E-mail alerting

Configured entirely through `.env`:
```
ENABLE_EMAIL=True
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password     # Gmail: 2FA → App Passwords
EMAIL_TO=destination@example.com
```
For SMS, swap the SMTP call in `procesare.py` for an HTTP request to an SMS provider
(e.g. Twilio).

---

## 10. Scalability (AWS) — for documentation

The architecture migrates without rewriting code — only connection variables change:
- **Broker**: local Mosquitto → **AWS IoT Core** (change host + certificates).
- **Database**: local MongoDB → **MongoDB Atlas** / **AWS DocumentDB**; time-series →
  **InfluxDB / Amazon Timestream**.
- **API + Dashboard**: **EC2** / **Elastic Beanstalk**; dashboard on Streamlit Cloud.
- **Device**: ESP32/Wokwi → a physical ESP32 or Raspberry Pi (same code, different pins).
