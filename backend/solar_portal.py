"""
Reusable SolarPortal client with session refresh support.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = "https://www.semsportal.com"
LOGIN_HEADERS = {
    "Content-Type": "application/json",
    "Token": json.dumps({"version": "v2.1.0", "client": "web", "language": "en"}),
}
SESSION_MAX_AGE_SECONDS = int(os.getenv("SOLAR_SESSION_MAX_AGE_SECONDS", "900"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("SOLAR_REQUEST_TIMEOUT_SECONDS", "10"))


class SolarPortalError(Exception):
    """Base error for Solar Portal access."""


class SessionExpiredError(SolarPortalError):
    """Raised when the upstream API rejects the current token."""


@dataclass
class Credentials:
    email: str
    password: str
    plant_id: str


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class SolarPortalClient:
    """Manages login, token reuse, and automatic re-authentication."""

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self.session = requests.Session()
        self._lock = threading.Lock()
        self.token_data: dict[str, Any] | None = None
        self.api_base = "https://eu.semsportal.com/api/"
        self.login_at = 0.0
        self.last_success_at = 0.0
        self.last_error: str | None = None
        self.consecutive_errors = 0
        self.token_refresh_count = 0

    @classmethod
    def from_env(cls) -> "SolarPortalClient":
        load_dotenv(PROJECT_ROOT / ".env")
        email = os.getenv("EMAIL")
        password = os.getenv("PASSWORD")
        plant_id = os.getenv("PLANT_ID")
        missing = [name for name, value in {
            "EMAIL": email,
            "PASSWORD": password,
            "PLANT_ID": plant_id,
        }.items() if not value]
        if missing:
            raise SolarPortalError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(Credentials(email=email, password=password, plant_id=plant_id))

    def login(self, force: bool = False) -> None:
        """Logs in if there is no valid token or if a refresh is forced."""
        with self._lock:
            if not force and self.token_data and not self._token_should_refresh():
                return

            response = self.session.post(
                f"{BASE_URL}/api/v1/Common/CrossLogin",
                headers=LOGIN_HEADERS,
                json={"account": self.credentials.email, "pwd": self.credentials.password},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("hasError") or payload.get("code") != 0:
                message = payload.get("msg", "Unknown login error")
                raise SolarPortalError(f"Login failed: {message}")

            self.token_data = payload["data"]
            self.api_base = payload.get("api", "https://eu.semsportal.com/api/")
            self.login_at = time.time()
            self.token_refresh_count += 1
            self.last_error = None

    def fetch_plant_data(self) -> dict[str, Any]:
        """Fetches plant data and retries once with a fresh login if needed."""
        self.login()

        try:
            return self._fetch_plant_data_once()
        except SessionExpiredError:
            try:
                self.login(force=True)
                return self._fetch_plant_data_once()
            except Exception as exc:
                self.last_error = str(exc)
                self.consecutive_errors += 1
                raise
        except Exception as exc:
            self.last_error = str(exc)
            self.consecutive_errors += 1
            raise

    def _fetch_plant_data_once(self) -> dict[str, Any]:
        if not self.token_data:
            raise SolarPortalError("No token available for plant data request")

        response = self.session.post(
            f"{self.api_base}v2/PowerStation/GetMonitorDetailByPowerstationId",
            headers=self._build_auth_headers(),
            json={"powerStationId": self.credentials.plant_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code in (401, 403):
            raise SessionExpiredError("Session rejected by upstream API")

        response.raise_for_status()
        payload = response.json()

        if payload.get("hasError"):
            message = payload.get("msg", "Unknown API error")
            if self._looks_like_session_error(message):
                raise SessionExpiredError(message)
            raise SolarPortalError(message)

        self.last_success_at = time.time()
        self.last_error = None
        self.consecutive_errors = 0
        return payload["data"]

    def _build_auth_headers(self) -> dict[str, str]:
        assert self.token_data is not None
        token_json = json.dumps({
            "uid": self.token_data["uid"],
            "timestamp": self.token_data["timestamp"],
            "token": self.token_data["token"],
            "client": self.token_data.get("client", "web"),
            "version": self.token_data.get("version", ""),
            "language": self.token_data.get("language", "en"),
        })
        return {
            "Content-Type": "application/json",
            "Token": token_json,
        }

    def _token_should_refresh(self) -> bool:
        return (time.time() - self.login_at) >= SESSION_MAX_AGE_SECONDS

    @staticmethod
    def _looks_like_session_error(message: str) -> bool:
        lowered = str(message).lower()
        markers = (
            "token",
            "session",
            "login",
            "expired",
            "auth",
            "unauthorized",
        )
        return any(marker in lowered for marker in markers)

    def get_status(self) -> dict[str, Any]:
        """Returns a frontend-friendly status snapshot."""
        token_age_seconds = max(0.0, time.time() - self.login_at) if self.login_at else None
        return {
            "logged_in": self.token_data is not None,
            "token_age_seconds": token_age_seconds,
            "token_refresh_count": self.token_refresh_count,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
            "api_base": self.api_base,
            "session_max_age_seconds": SESSION_MAX_AGE_SECONDS,
        }


def normalize_snapshot(data: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    """Converts the raw SolarPortal payload into a compact UI-friendly snapshot."""
    info = data.get("info", {})
    kpi = data.get("kpi", {})
    inverter_list = data.get("inverter", [])
    inverter = inverter_list[0] if inverter_list else {}
    inverter_full = inverter.get("invert_full", {})
    weather_block = {}
    forecast = []

    try:
        forecast = data["weather"]["HeWeather6"][0]["daily_forecast"]
        weather_block = {
            "location_label": "Perugia",
            "today_text": forecast[0]["cond_txt_d"],
            "today_min_celsius": forecast[0]["tmp_min"],
            "today_max_celsius": forecast[0]["tmp_max"],
            "today_humidity_percent": forecast[0]["hum"],
            "tomorrow_text": forecast[1]["cond_txt_d"],
            "tomorrow_min_celsius": forecast[1]["tmp_min"],
            "tomorrow_max_celsius": forecast[1]["tmp_max"],
            "tomorrow_humidity_percent": forecast[1]["hum"],
        }
    except (KeyError, IndexError, TypeError):
        weather_block = {}

    battery_mode = int(_safe_float(inverter_full.get("battary_work_mode"), 0))
    battery_mode_label = {
        0: "Standby",
        1: "Charging",
        2: "Discharging",
    }.get(battery_mode, str(battery_mode))

    stats = data.get("energeStatisticsTotals", {})

    return {
        "status": status,
        "fetched_at": time.time(),
        "plant": {
            "name": info.get("stationname", "N/A"),
            "address": info.get("address", "N/A"),
            "turn_on_time": info.get("turnon_time", "N/A"),
        },
        "realtime": {
            "pv_power_watts": _safe_float(kpi.get("pac")),
            "today_kwh": _safe_float(kpi.get("power")),
            "month_kwh": _safe_float(kpi.get("month_generation")),
            "total_kwh": _safe_float(kpi.get("total_power")),
        },
        "inverter": {
            "type": inverter.get("type", "N/A"),
            "serial_number": inverter.get("sn", "N/A"),
            "temperature_celsius": _safe_float(inverter.get("tempperature")),
            "last_refresh_time": inverter.get("last_refresh_time", "N/A"),
            "pv1_voltage_volts": _safe_float(inverter_full.get("vpv1")),
            "pv1_current_amps": _safe_float(inverter_full.get("ipv1")),
            "pv2_voltage_volts": _safe_float(inverter_full.get("vpv2")),
            "pv2_current_amps": _safe_float(inverter_full.get("ipv2")),
        },
        "battery": {
            "soc_percent": _safe_float(inverter_full.get("soc")),
            "voltage_volts": _safe_float(inverter_full.get("vbattery1")),
            "current_amps": _safe_float(inverter_full.get("ibattery1")),
            "power_watts": _safe_float(inverter_full.get("total_pbattery")),
            "mode": battery_mode,
            "mode_label": battery_mode_label,
        },
        "grid": {
            "power_watts": _safe_float(inverter_full.get("pmeter")),
            "voltage_volts": _safe_float(inverter_full.get("vac1")),
            "frequency_hz": _safe_float(inverter_full.get("fac1")),
        },
        "totals": {
            "grid_buy_kwh": _safe_float(inverter_full.get("total_buy")),
            "grid_sell_kwh": _safe_float(inverter_full.get("total_sell")),
            "battery_charge_kwh": _safe_float(inverter_full.get("eBatteryCharge")),
            "battery_discharge_kwh": _safe_float(inverter_full.get("eBatteryDischarge")),
            "runtime_hours": _safe_float(inverter_full.get("hour_total")),
        },
        "stats": {
            "self_use_rate_percent": _safe_float(stats.get("selfUseRate")) * 100,
            "contributing_rate_percent": _safe_float(stats.get("contributingRate")) * 100,
        },
        "weather": weather_block,
        "raw": data,
    }
