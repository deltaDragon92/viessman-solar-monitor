#!/usr/bin/env python3
"""
Viessmann Solar Portal - CLI snapshot reader
============================================
Reads real-time data from the Viessmann Solar Portal and prints
an easy-to-read summary in the terminal.

Usage:
    pip install -r backend/requirements.txt
    python3 backend/viessmann_solar.py
"""

from __future__ import annotations

import json
from datetime import datetime

import requests

from solar_portal import SolarPortalClient, normalize_snapshot


def print_snapshot(snapshot: dict) -> None:
    """Prints the most useful fields from the normalized snapshot."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    plant = snapshot.get("plant", {})
    realtime = snapshot.get("realtime", {})
    inverter = snapshot.get("inverter", {})
    battery = snapshot.get("battery", {})
    grid = snapshot.get("grid", {})
    totals = snapshot.get("totals", {})
    stats = snapshot.get("stats", {})
    weather = snapshot.get("weather", {})

    print(f"\n{'=' * 55}")
    print(f"  ⚡ VIESSMANN HINV6.0-B1  —  {now}")
    print(f"{'=' * 55}")

    print(f"\n🏠 Plant    : {plant.get('name', 'N/A')}")
    print(f"📍 Address  : {plant.get('address', 'N/A')}")
    print(f"📅 Online   : {plant.get('turn_on_time', 'N/A')}")

    print(f"\n{'─' * 55}")
    print("  REAL-TIME PRODUCTION")
    print(f"{'─' * 55}")
    print(f"  ☀️  PV power now       : {realtime.get('pv_power_watts', 0):.1f} W")
    print(f"  📦 Generated today     : {realtime.get('today_kwh', 0):.2f} kWh")
    print(f"  📆 Generated this month: {realtime.get('month_kwh', 0):.1f} kWh")
    print(f"  📈 Generated total     : {realtime.get('total_kwh', 0):.1f} kWh")

    print(f"\n{'─' * 55}")
    print(f"  INVERTER ({inverter.get('type', 'N/A')}  SN: {inverter.get('serial_number', 'N/A')})")
    print(f"{'─' * 55}")

    pmeter = grid.get("power_watts", 0)
    if pmeter < 0:
        print(f"  🔌 Grid          : ⬇️  Import  {abs(pmeter):.0f} W")
    elif pmeter > 0:
        print(f"  🔌 Grid          : ⬆️  Export  {pmeter:.0f} W")
    else:
        print("  🔌 Grid          : ↔️  Balanced  0 W")

    print(
        "  🔋 Battery SOC   : "
        f"{battery.get('soc_percent', 0):.0f}%  "
        f"({battery.get('voltage_volts', 0):.1f}V / "
        f"{battery.get('current_amps', 0):.1f}A / "
        f"{battery.get('power_watts', 0):.0f}W)"
    )
    print(f"  🔋 Battery mode  : {battery.get('mode_label', 'N/A')}")
    print(
        "  ☀️  PV strings    : "
        f"PV1 {inverter.get('pv1_voltage_volts', 0):.1f}V/{inverter.get('pv1_current_amps', 0):.1f}A, "
        f"PV2 {inverter.get('pv2_voltage_volts', 0):.1f}V/{inverter.get('pv2_current_amps', 0):.1f}A"
    )
    print(f"  ⚡ Grid voltage  : {grid.get('voltage_volts', 0):.1f} V")
    print(f"  ⚡ Grid frequency: {grid.get('frequency_hz', 0):.2f} Hz")
    print(f"  🌡️  Temperature   : {inverter.get('temperature_celsius', 0):.1f} °C")
    print(f"  🕐 Last refresh  : {inverter.get('last_refresh_time', 'N/A')}")

    print(f"\n{'─' * 55}")
    print("  LIFETIME COUNTERS")
    print(f"{'─' * 55}")
    print(f"  📥 Bought from grid : {totals.get('grid_buy_kwh', 0):.1f} kWh")
    print(f"  📤 Sold to grid     : {totals.get('grid_sell_kwh', 0):.2f} kWh")
    print(f"  🔋 Battery charged  : {totals.get('battery_charge_kwh', 0):.1f} kWh")
    print(f"  🔋 Battery discharged: {totals.get('battery_discharge_kwh', 0):.1f} kWh")
    print(f"  ⏱️  Runtime hours    : {totals.get('runtime_hours', 0):.0f} h")

    if stats:
        print(f"\n{'─' * 55}")
        print("  OVERALL STATISTICS")
        print(f"{'─' * 55}")
        print(f"  ♻️  Self-use rate      : {stats.get('self_use_rate_percent', 0):.0f}%")
        print(f"  📊 Contribution rate   : {stats.get('contributing_rate_percent', 0):.0f}%")

    if weather:
        print(f"\n{'─' * 55}")
        print(f"  WEATHER — {weather.get('location_label', 'N/A')}")
        print(f"{'─' * 55}")
        print(
            "  Today  : "
            f"{weather.get('today_text', 'N/A')}  "
            f"{weather.get('today_min_celsius', 'N/A')}°→{weather.get('today_max_celsius', 'N/A')}°C  "
            f"💧{weather.get('today_humidity_percent', 'N/A')}%"
        )
        print(
            "  Tomorrow: "
            f"{weather.get('tomorrow_text', 'N/A')}  "
            f"{weather.get('tomorrow_min_celsius', 'N/A')}°→{weather.get('tomorrow_max_celsius', 'N/A')}°C  "
            f"💧{weather.get('tomorrow_humidity_percent', 'N/A')}%"
        )

    print(f"\n{'=' * 55}\n")


def save_json(data: dict, filename: str | None = None) -> str:
    """Saves the normalized snapshot to a JSON file."""
    if filename is None:
        filename = f"solar_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)
    return filename


if __name__ == "__main__":
    try:
        client = SolarPortalClient.from_env()
        raw_data = client.fetch_plant_data()
        snapshot = normalize_snapshot(raw_data, client.get_status())
        print_snapshot(snapshot)

        # Optional: save the normalized snapshot to disk.
        # saved_to = save_json(snapshot)
        # print(f"💾 Snapshot saved to: {saved_to}")

    except requests.exceptions.ConnectionError:
        print("❌ Connection error — check your network")
    except requests.exceptions.Timeout:
        print("❌ Timeout — the server did not respond")
    except Exception as exc:
        print(f"❌ Error: {exc}")
