#!/usr/bin/env python3
"""
Viessmann Solar Portal - Inverter data reader script
====================================================
Reads real-time data from your Viessmann HINV6.0-B1 inverter
through the SolarPortal APIs (GoodWe SEMS backend).

Usage:
    pip install requests
    python viessmann_solar.py
"""

import requests
import json
import hashlib
from datetime import datetime

# ============================================================
#  CONFIGURATION — edit only this section
# ============================================================
from dotenv import load_dotenv
import os

load_dotenv()
EMAIL    = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
PLANT_ID = os.getenv("PLANT_ID")
# ============================================================

BASE_URL   = "https://www.semsportal.com"
TOKEN_INIT = {"version": "v2.1.0", "client": "web", "version": "", "language": "en"}

# Base header for login (Token as JSON, plain-text password — works with v1)
HEADERS_LOGIN = {
    "Content-Type": "application/json",
    "Token": json.dumps({"version": "v2.1.0", "client": "web", "language": "en"})
}


def login(email: str, password: str) -> dict:
    """
    Authenticates with the portal and returns the session token.
    Uses the v1 endpoint with a plain-text password (verified working method).
    """
    print("🔐 Login in corso...")
    resp = requests.post(
        f"{BASE_URL}/api/v1/Common/CrossLogin",
        headers=HEADERS_LOGIN,
        json={"account": email, "pwd": password},
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("hasError") or data.get("code") != 0:
        raise Exception(f"Login fallito: {data.get('msg', 'Errore sconosciuto')}")

    token_data = data["data"]
    api_base   = data.get("api", "https://eu.semsportal.com/api/")
    print(f"✅ Login OK  —  server: {api_base}")
    return token_data, api_base


def build_auth_headers(token_data: dict) -> dict:
    """
    Builds the authentication headers for calls after login.
    The Token must include the uid, timestamp, and token returned by login.
    """
    token_json = json.dumps({
        "uid":       token_data["uid"],
        "timestamp": token_data["timestamp"],
        "token":     token_data["token"],
        "client":    token_data.get("client", "web"),
        "version":   token_data.get("version", ""),
        "language":  token_data.get("language", "en"),
    })
    return {
        "Content-Type": "application/json",
        "Token": token_json
    }


def get_plant_data(token_data: dict, api_base: str, plant_id: str) -> dict:
    """
    Retrieves all real-time plant data:
    PV production, consumption, battery, grid, weather, and historical KPIs.
    """
    print("📡 Recupero dati impianto...")
    headers = build_auth_headers(token_data)
    resp = requests.post(
        f"{api_base}v2/PowerStation/GetMonitorDetailByPowerstationId",
        headers=headers,
        json={"powerStationId": plant_id},
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("hasError"):
        raise Exception(f"Errore API: {data.get('msg', 'Errore sconosciuto')}")

    return data["data"]


def stampa_dati(data: dict):
    """
    Prints the most useful data in a readable format.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n{'='*55}")
    print(f"  ⚡ VIESSMANN HINV6.0-B1  —  {now}")
    print(f"{'='*55}")

    # --- Plant info ---
    info = data.get("info", {})
    print(f"\n🏠 Impianto : {info.get('stationname', 'N/A')}")
    print(f"📍 Indirizzo: {info.get('address', 'N/A')}")
    print(f"📅 Attivo dal: {info.get('turnon_time', 'N/A')}")

    # --- Real-time KPIs ---
    kpi = data.get("kpi", {})
    print(f"\n{'─'*55}")
    print(f"  PRODUZIONE IN TEMPO REALE")
    print(f"{'─'*55}")
    print(f"  ☀️  Potenza FV istantanea : {kpi.get('pac', 0):.1f} W")
    print(f"  📦 Produzione oggi        : {kpi.get('power', 0):.2f} kWh")
    print(f"  📆 Produzione questo mese : {kpi.get('month_generation', 0):.1f} kWh")
    print(f"  📈 Produzione totale      : {kpi.get('total_power', 0):.1f} kWh")

    # --- Detailed inverter data ---
    inverters = data.get("inverter", [])
    if inverters:
        inv = inverters[0]
        d   = inv.get("d", {})
        full = inv.get("invert_full", {})

        print(f"\n{'─'*55}")
        print(f"  INVERTER  ({inv.get('type', 'N/A')}  SN: {inv.get('sn', 'N/A')})")
        print(f"{'─'*55}")

        # Grid
        pmeter = full.get("pmeter", 0)
        if pmeter < 0:
            print(f"  🔌 Rete         : ⬇️  Acquisto  {abs(pmeter):.0f} W")
        elif pmeter > 0:
            print(f"  🔌 Rete         : ⬆️  Vendita   {pmeter:.0f} W")
        else:
            print(f"  🔌 Rete         : ↔️  Bilanciato  0 W")

        # Battery
        soc    = full.get("soc", 0)
        vbat   = full.get("vbattery1", 0)
        ibat   = full.get("ibattery1", 0)
        pbat   = full.get("total_pbattery", 0)
        bmode  = full.get("battary_work_mode", 0)
        bmode_str = {0: "Standby", 1: "Carica", 2: "Scarica"}.get(bmode, str(bmode))
        print(f"  🔋 Batteria SOC : {soc:.0f}%  ({vbat:.1f}V / {ibat:.1f}A / {pbat:.0f}W)")
        print(f"  🔋 Modalità bat : {bmode_str}")

        # PV panels
        vpv1 = full.get("vpv1", 0)
        vpv2 = full.get("vpv2", 0)
        ipv1 = full.get("ipv1", 0)
        ipv2 = full.get("ipv2", 0)
        print(f"  ☀️  Stringa PV1  : {vpv1:.1f}V / {ipv1:.1f}A")
        print(f"  ☀️  Stringa PV2  : {vpv2:.1f}V / {ipv2:.1f}A")

        # AC grid
        print(f"  ⚡ Tensione rete : {full.get('vac1', 0):.1f} V")
        print(f"  ⚡ Frequenza     : {full.get('fac1', 0):.2f} Hz")
        print(f"  🌡️  Temperatura   : {inv.get('tempperature', 0):.1f} °C")

        # Energy counters
        print(f"\n{'─'*55}")
        print(f"  CONTATORI ENERGIA TOTALI")
        print(f"{'─'*55}")
        print(f"  📥 Acquistata dalla rete : {full.get('total_buy', 0):.1f} kWh")
        print(f"  📤 Venduta alla rete     : {full.get('total_sell', 0):.2f} kWh")
        print(f"  🔋 Carica batteria tot.  : {full.get('eBatteryCharge', 0):.1f} kWh")
        print(f"  🔋 Scarica batteria tot. : {full.get('eBatteryDischarge', 0):.1f} kWh")
        print(f"  ⏱️  Ore di funzionamento  : {full.get('hour_total', 0):.0f} h")

        # Last update
        print(f"\n  🕐 Ultimo refresh: {inv.get('last_refresh_time', 'N/A')}")

    # --- Overall energy statistics ---
    stats = data.get("energeStatisticsTotals", {})
    if stats:
        print(f"\n{'─'*55}")
        print(f"  STATISTICHE COMPLESSIVE")
        print(f"{'─'*55}")
        print(f"  ♻️  Autoconsumo FV      : {stats.get('selfUseRate', 0)*100:.0f}%")
        print(f"  📊 Tasso contribuzione : {stats.get('contributingRate', 0)*100:.0f}%")

    # --- Weather ---
    try:
        forecast = data["weather"]["HeWeather6"][0]["daily_forecast"]
        oggi     = forecast[0]
        domani   = forecast[1]
        print(f"\n{'─'*55}")
        print(f"  METEO — Perugia")
        print(f"{'─'*55}")
        print(f"  Oggi   : {oggi['cond_txt_d']}  {oggi['tmp_min']}°→{oggi['tmp_max']}°C  💧{oggi['hum']}%")
        print(f"  Domani : {domani['cond_txt_d']}  {domani['tmp_min']}°→{domani['tmp_max']}°C  💧{domani['hum']}%")
    except (KeyError, IndexError):
        pass

    print(f"\n{'='*55}\n")


def salva_json(data: dict, filename: str = None):
    """
    Saves the full response to a JSON file for later analysis.
    """
    if filename is None:
        filename = f"solar_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 Dati completi salvati in: {filename}")


# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    try:
        # 1. Login
        token_data, api_base = login(EMAIL, PASSWORD)

        # 2. Fetch data
        plant_data = get_plant_data(token_data, api_base, PLANT_ID)

        # 3. Print a readable summary
        stampa_dati(plant_data)

        # 4. (Optional) save the full JSON — uncomment if needed
        # salva_json(plant_data)

    except requests.exceptions.ConnectionError:
        print("❌ Errore di connessione — controlla la rete")
    except requests.exceptions.Timeout:
        print("❌ Timeout — il server non risponde")
    except Exception as e:
        print(f"❌ Errore: {e}")
