#!/usr/bin/env python3
"""
Viessmann Solar Portal - Script di lettura dati inverter
=========================================================
Legge i dati in tempo reale dal tuo inverter Viessmann HINV6.0-B1
tramite le API del portale SolarPortal (backend GoodWe SEMS).

Utilizzo:
    pip install requests
    python viessmann_solar.py

Autore: generato con Claude - Anthropic
"""

import requests
import json
import hashlib
from datetime import datetime

# ============================================================
#  CONFIGURAZIONE — modifica solo questa sezione
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

# Header base per il login (Token come JSON, password in chiaro — funziona con v1)
HEADERS_LOGIN = {
    "Content-Type": "application/json",
    "Token": json.dumps({"version": "v2.1.0", "client": "web", "language": "en"})
}


def login(email: str, password: str) -> dict:
    """
    Autentica sul portale e restituisce il token di sessione.
    Usa l'endpoint v1 con password in chiaro (metodo verificato funzionante).
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
    Costruisce gli header di autenticazione per le chiamate successive al login.
    Il Token deve contenere uid, timestamp e token ottenuti dal login.
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
    Recupera tutti i dati dell'impianto in tempo reale:
    produzione FV, consumo, batteria, rete, meteo, KPI storici.
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
    Stampa i dati più utili in modo leggibile.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n{'='*55}")
    print(f"  ⚡ VIESSMANN HINV6.0-B1  —  {now}")
    print(f"{'='*55}")

    # --- Info impianto ---
    info = data.get("info", {})
    print(f"\n🏠 Impianto : {info.get('stationname', 'N/A')}")
    print(f"📍 Indirizzo: {info.get('address', 'N/A')}")
    print(f"📅 Attivo dal: {info.get('turnon_time', 'N/A')}")

    # --- KPI in tempo reale ---
    kpi = data.get("kpi", {})
    print(f"\n{'─'*55}")
    print(f"  PRODUZIONE IN TEMPO REALE")
    print(f"{'─'*55}")
    print(f"  ☀️  Potenza FV istantanea : {kpi.get('pac', 0):.1f} W")
    print(f"  📦 Produzione oggi        : {kpi.get('power', 0):.2f} kWh")
    print(f"  📆 Produzione questo mese : {kpi.get('month_generation', 0):.1f} kWh")
    print(f"  📈 Produzione totale      : {kpi.get('total_power', 0):.1f} kWh")

    # --- Dati inverter dettagliati ---
    inverters = data.get("inverter", [])
    if inverters:
        inv = inverters[0]
        d   = inv.get("d", {})
        full = inv.get("invert_full", {})

        print(f"\n{'─'*55}")
        print(f"  INVERTER  ({inv.get('type', 'N/A')}  SN: {inv.get('sn', 'N/A')})")
        print(f"{'─'*55}")

        # Rete
        pmeter = full.get("pmeter", 0)
        if pmeter < 0:
            print(f"  🔌 Rete         : ⬇️  Acquisto  {abs(pmeter):.0f} W")
        elif pmeter > 0:
            print(f"  🔌 Rete         : ⬆️  Vendita   {pmeter:.0f} W")
        else:
            print(f"  🔌 Rete         : ↔️  Bilanciato  0 W")

        # Batteria
        soc    = full.get("soc", 0)
        vbat   = full.get("vbattery1", 0)
        ibat   = full.get("ibattery1", 0)
        pbat   = full.get("total_pbattery", 0)
        bmode  = full.get("battary_work_mode", 0)
        bmode_str = {0: "Standby", 1: "Carica", 2: "Scarica"}.get(bmode, str(bmode))
        print(f"  🔋 Batteria SOC : {soc:.0f}%  ({vbat:.1f}V / {ibat:.1f}A / {pbat:.0f}W)")
        print(f"  🔋 Modalità bat : {bmode_str}")

        # Pannelli FV
        vpv1 = full.get("vpv1", 0)
        vpv2 = full.get("vpv2", 0)
        ipv1 = full.get("ipv1", 0)
        ipv2 = full.get("ipv2", 0)
        print(f"  ☀️  Stringa PV1  : {vpv1:.1f}V / {ipv1:.1f}A")
        print(f"  ☀️  Stringa PV2  : {vpv2:.1f}V / {ipv2:.1f}A")

        # Rete AC
        print(f"  ⚡ Tensione rete : {full.get('vac1', 0):.1f} V")
        print(f"  ⚡ Frequenza     : {full.get('fac1', 0):.2f} Hz")
        print(f"  🌡️  Temperatura   : {inv.get('tempperature', 0):.1f} °C")

        # Contatori energia
        print(f"\n{'─'*55}")
        print(f"  CONTATORI ENERGIA TOTALI")
        print(f"{'─'*55}")
        print(f"  📥 Acquistata dalla rete : {full.get('total_buy', 0):.1f} kWh")
        print(f"  📤 Venduta alla rete     : {full.get('total_sell', 0):.2f} kWh")
        print(f"  🔋 Carica batteria tot.  : {full.get('eBatteryCharge', 0):.1f} kWh")
        print(f"  🔋 Scarica batteria tot. : {full.get('eBatteryDischarge', 0):.1f} kWh")
        print(f"  ⏱️  Ore di funzionamento  : {full.get('hour_total', 0):.0f} h")

        # Ultimo aggiornamento
        print(f"\n  🕐 Ultimo refresh: {inv.get('last_refresh_time', 'N/A')}")

    # --- Statistiche energetiche totali ---
    stats = data.get("energeStatisticsTotals", {})
    if stats:
        print(f"\n{'─'*55}")
        print(f"  STATISTICHE COMPLESSIVE")
        print(f"{'─'*55}")
        print(f"  ♻️  Autoconsumo FV      : {stats.get('selfUseRate', 0)*100:.0f}%")
        print(f"  📊 Tasso contribuzione : {stats.get('contributingRate', 0)*100:.0f}%")

    # --- Meteo ---
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
    Salva la risposta completa in un file JSON per analisi successive.
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

        # 2. Recupera dati
        plant_data = get_plant_data(token_data, api_base, PLANT_ID)

        # 3. Stampa riepilogo leggibile
        stampa_dati(plant_data)

        # 4. (Opzionale) salva JSON completo — decommenta se vuoi
        # salva_json(plant_data)

    except requests.exceptions.ConnectionError:
        print("❌ Errore di connessione — controlla la rete")
    except requests.exceptions.Timeout:
        print("❌ Timeout — il server non risponde")
    except Exception as e:
        print(f"❌ Errore: {e}")