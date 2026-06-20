import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from datetime import datetime
import time

API = "http://api:5000"
TEMP_MAX, TEMP_MIN = 30.0, 15.0
HUMID_MAX, HUMID_MIN = 80.0, 20.0
PRES_LOW, PRES_HIGH = 975.0, 1025.0

st.set_page_config(
    page_title="Monitorizare Industriala IoT",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_data(ttl=1)
def api_readings(tip, n):
    try:
        r = requests.get(f"{API}/api/readings/{tip}", params={"n": n}, timeout=3)
        df = pd.DataFrame(r.json())
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"])
        return df
    except:
        return pd.DataFrame()


@st.cache_data(ttl=1)
def api_latest():
    try:
        return requests.get(f"{API}/api/latest", timeout=3).json()
    except:
        return {}


@st.cache_data(ttl=1)
def api_events(n=10):
    try:
        return pd.DataFrame(requests.get(f"{API}/api/events", params={"n": n}, timeout=3).json())
    except:
        return pd.DataFrame()


def api_control(tinta, stare):
    try:
        r = requests.post(f"{API}/api/control",
                          json={"tinta": tinta, "stare": stare}, timeout=5)
        j = r.json()
        return j.get("ok", False), j.get("mesaj", "")
    except Exception as e:
        return False, str(e)


latest = api_latest()

temp_val = latest.get("temperatura", {}).get("valoare", 0.0)
humid_val = latest.get("umiditate", {}).get("valoare", 0.0)
pres_val = latest.get("presiune", {}).get("valoare", 0.0)

st_vent = latest.get("ventilator", {}).get("valoare") == "ON" or temp_val > TEMP_MAX
st_alarma = latest.get("alarma", {}).get("valoare") == "ON" or humid_val > HUMID_MAX
st_pres_critica = pres_val < PRES_LOW or pres_val > PRES_HIGH

with st.sidebar:
    st.markdown("### Configurare Vizualizare")
    n_citiri = st.slider("Numar puncte pe grafic", 10, 200, 50, step=10)
    st.divider()

    st.markdown("### Status Conexiune")
    if latest:
        st.success("Sistem Online (Broker Cloud)")
    else:
        st.error("Sistem Offline (Eroare API)")

    st.caption(f"Ultimul sync: {datetime.now().strftime('%H:%M:%S')}")

    st.divider()
    st.markdown("### Control de la Distanta")

    def _trimite(tinta, stare):
        ok, m = api_control(tinta, stare)
        if ok:
            st.toast(f"✅ {m}", icon="✅")
        else:
            st.toast(f"❌ {m}", icon="⚠️")

    st.markdown("**🌀 Ventilator**")
    c1, c2 = st.columns(2)
    if c1.button("▶ ON",  key="fan_on",  use_container_width=True, type="primary"):
        _trimite("ventilator", "ON")
    if c2.button("⏹ OFF", key="fan_off", use_container_width=True):
        _trimite("ventilator", "OFF")

    st.markdown("**🚨 Alarma Umiditate**")
    c3, c4 = st.columns(2)
    if c3.button("🔔 ON",  key="alarm_on",  use_container_width=True, type="primary"):
        _trimite("alarma", "ON")
    if c4.button("🔕 OFF", key="alarm_off", use_container_width=True):
        _trimite("alarma", "OFF")

    st.markdown("**🟡 LED Presiune**")
    c5, c6 = st.columns(2)
    if c5.button("💡 ON",  key="pres_on",  use_container_width=True, type="primary"):
        _trimite("presiune", "ON")
    if c6.button("⚫ OFF", key="pres_off", use_container_width=True):
        _trimite("presiune", "OFF")

st.title("Monitorizare Industriala Automatizata")
st.caption("Actualizare automata continua • Interval esantionare: 3s")

if st_vent or st_alarma or st_pres_critica:
    st.subheader("Stari Sistem si Activari Automate")

    col_al1, col_al2, col_al3 = st.columns(3)

    with col_al1:
        if st_vent:
            st.warning(f"**Ventilator PORNIT**\n\nTemperatura ({temp_val:.1f}C) a depasit pragul critic de {TEMP_MAX}C. Racire activa.")

    with col_al2:
        if st_alarma:
            st.error(f"**Alarma Umiditate ACTIVA**\n\nUmiditate critica detectata: {humid_val:.1f}%. Risc crescut de condens.")

    with col_al3:
        if st_pres_critica:
            st.error(f"**LED Presiune APRINS**\n\nPresiune in afara limitelor nominale ({pres_val:.1f} hPa). Verificati supapa.")
    st.divider()

k1, k2, k3, k4 = st.columns(4)


def render_kpi(col, date_senzor, eticheta, val, lo, hi, unit):
    if date_senzor:
        stare = "ALERTA" if (val > hi or val < lo) else "Normal"
        col.metric(eticheta, f"{val:.1f} {unit}", delta=stare, delta_color="inverse" if (val > hi or val < lo) else "normal")
    else:
        col.metric(eticheta, "–", "Fara semnal")


render_kpi(k1, latest.get("temperatura"), "Temperatura Mediu", temp_val, TEMP_MIN, TEMP_MAX, "C")
render_kpi(k2, latest.get("umiditate"), "Umiditate Relativa", humid_val, HUMID_MIN, HUMID_MAX, "%")
render_kpi(k3, latest.get("presiune"), "Presiune Atmosferica", pres_val, PRES_LOW, PRES_HIGH, "hPa")

df_t = api_readings("temperatura", n_citiri)
k4.metric("Max Temp Inregistrata", f"{df_t['valoare'].max():.1f} C" if not df_t.empty else "–", delta="Istoric subset")

st.subheader("Analiza Grafica Progresiva")
t1, t2, t3 = st.tabs(["Monitorizare Temperatura", "Grafic Umiditate", "Evolutie Presiune"])

for tab, tip, color, unit in [
    (t1, "temperatura", "#FF6B6B", "C"),
    (t2, "umiditate", "#4ECDC4", "%"),
    (t3, "presiune", "#A855F7", "hPa")
]:
    with tab:
        df = api_readings(tip, n_citiri)
        if not df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["data"],
                y=df["valoare"],
                mode="lines+markers",
                name=tip.capitalize(),
                line=dict(color=color, width=2.5),
                marker=dict(size=6)
            ))

            fig.update_layout(
                height=280,
                margin=dict(l=20, r=20, t=10, b=20),
                yaxis_title=unit,
                hovermode="x unified",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Se incarca datele din baza de date...")

st.subheader("Jurnal Evenimente Recente (MongoDB Audit)")
df_ev = api_events(5)
if not df_ev.empty:
    st.dataframe(
        df_ev[["data", "tip", "mesaj"]].rename(columns={"data": "Timestamp", "tip": "Tip Eveniment", "mesaj": "Descriere Operationala"}),
        use_container_width=True
    )
else:
    st.info("Niciun eveniment critic inregistrat in ultimele cicluri.")

time.sleep(3)
st.rerun()
