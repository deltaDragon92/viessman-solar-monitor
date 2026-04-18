"""
MQTT publishing bridge with Home Assistant discovery support.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


@dataclass
class MqttConfig:
    enabled: bool
    host: str
    port: int
    username: str | None
    password: str | None
    client_id: str
    keepalive: int
    base_topic: str
    discovery_prefix: str
    ha_status_topic: str
    retain: bool
    qos: int
    device_id: str
    device_name: str
    manufacturer: str
    model: str
    support_url: str | None

    @classmethod
    def from_env(cls, plant_id: str | None = None) -> "MqttConfig":
        raw_device_id = os.getenv("MQTT_DEVICE_ID") or plant_id or socket.gethostname()
        device_id = _slugify(raw_device_id or "viessmann_solar_monitor")
        return cls(
            enabled=_env_flag("MQTT_ENABLED", False),
            host=os.getenv("MQTT_HOST", "127.0.0.1"),
            port=int(os.getenv("MQTT_PORT", "1883")),
            username=os.getenv("MQTT_USERNAME") or None,
            password=os.getenv("MQTT_PASSWORD") or None,
            client_id=os.getenv("MQTT_CLIENT_ID", f"viessmann-solar-{device_id}"),
            keepalive=int(os.getenv("MQTT_KEEPALIVE_SECONDS", "30")),
            base_topic=os.getenv("MQTT_BASE_TOPIC", "viessmann_solar"),
            discovery_prefix=os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            ha_status_topic=os.getenv("MQTT_HA_STATUS_TOPIC", "homeassistant/status"),
            retain=_env_flag("MQTT_RETAIN", True),
            qos=int(os.getenv("MQTT_QOS", "1")),
            device_id=device_id,
            device_name=os.getenv("MQTT_DEVICE_NAME", "Viessmann Solar Plant"),
            manufacturer=os.getenv("MQTT_DEVICE_MANUFACTURER", "Viessmann"),
            model=os.getenv("MQTT_DEVICE_MODEL", "SEMS Portal Bridge"),
            support_url=os.getenv("MQTT_SUPPORT_URL") or None,
        )


def _value_from_path(payload: dict[str, Any] | None, path: str, default: Any = None) -> Any:
    current: Any = payload or {}
    for key in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _compute_house_load(snapshot: dict[str, Any] | None) -> float:
    if not snapshot:
        return 0.0
    realtime = snapshot.get("realtime", {})
    grid = snapshot.get("grid", {})
    battery = snapshot.get("battery", {})
    pv_power = float(realtime.get("pv_power_watts", 0) or 0)
    grid_power = float(grid.get("power_watts", 0) or 0)
    battery_power = abs(float(battery.get("power_watts", 0) or 0))
    battery_mode = str(battery.get("mode_label", "Standby"))
    importing = abs(grid_power) if grid_power < 0 else 0.0
    exporting = grid_power if grid_power > 0 else 0.0
    charging = battery_power if battery_mode == "Charging" else 0.0
    discharging = battery_power if battery_mode == "Discharging" else 0.0
    return max(0.0, pv_power + importing + discharging - exporting - charging)


def _flatten_snapshot(snapshot: dict[str, Any] | None, last_error: str | None = None) -> dict[str, Any]:
    snapshot = snapshot or {}
    realtime = snapshot.get("realtime", {})
    battery = snapshot.get("battery", {})
    grid = snapshot.get("grid", {})
    inverter = snapshot.get("inverter", {})
    totals = snapshot.get("totals", {})
    stats = snapshot.get("stats", {})
    weather = snapshot.get("weather", {})
    plant = snapshot.get("plant", {})
    status = snapshot.get("status", {})

    grid_power = float(grid.get("power_watts", 0) or 0)

    return {
        "fetched_at": snapshot.get("fetched_at"),
        "plant_name": plant.get("name"),
        "plant_address": plant.get("address"),
        "pv_power_watts": realtime.get("pv_power_watts"),
        "house_load_watts": _compute_house_load(snapshot),
        "grid_power_watts": grid_power,
        "grid_import_watts": abs(grid_power) if grid_power < 0 else 0,
        "grid_export_watts": grid_power if grid_power > 0 else 0,
        "today_kwh": realtime.get("today_kwh"),
        "month_kwh": realtime.get("month_kwh"),
        "total_kwh": realtime.get("total_kwh"),
        "battery_soc_percent": battery.get("soc_percent"),
        "battery_voltage_volts": battery.get("voltage_volts"),
        "battery_current_amps": battery.get("current_amps"),
        "battery_power_watts": battery.get("power_watts"),
        "battery_mode": battery.get("mode_label"),
        "grid_voltage_volts": grid.get("voltage_volts"),
        "grid_frequency_hz": grid.get("frequency_hz"),
        "grid_buy_kwh": totals.get("grid_buy_kwh"),
        "grid_sell_kwh": totals.get("grid_sell_kwh"),
        "battery_charge_kwh": totals.get("battery_charge_kwh"),
        "battery_discharge_kwh": totals.get("battery_discharge_kwh"),
        "runtime_hours": totals.get("runtime_hours"),
        "pv1_voltage_volts": inverter.get("pv1_voltage_volts"),
        "pv1_current_amps": inverter.get("pv1_current_amps"),
        "pv2_voltage_volts": inverter.get("pv2_voltage_volts"),
        "pv2_current_amps": inverter.get("pv2_current_amps"),
        "inverter_temperature_celsius": inverter.get("temperature_celsius"),
        "self_use_rate_percent": stats.get("self_use_rate_percent"),
        "contributing_rate_percent": stats.get("contributing_rate_percent"),
        "weather_today_text": weather.get("today_text"),
        "weather_tomorrow_text": weather.get("tomorrow_text"),
        "last_success_at": status.get("last_success_at"),
        "token_refresh_count": status.get("token_refresh_count"),
        "token_age_seconds": status.get("token_age_seconds"),
        "api_base": status.get("api_base"),
        "last_error": last_error or status.get("last_error"),
    }


def _sensor_entity(
    *,
    key: str,
    name: str,
    path: str,
    icon: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    unit: str | None = None,
    entity_category: str | None = None,
    options: list[str] | None = None,
    suggested_precision: int | None = None,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "platform": "sensor",
        "name": name,
        "unique_suffix": key,
        "value_template": "{{ value_json." + path + " }}",
    }
    if icon:
        entity["icon"] = icon
    if device_class:
        entity["device_class"] = device_class
    if state_class:
        entity["state_class"] = state_class
    if unit:
        entity["unit_of_measurement"] = unit
    if entity_category:
        entity["entity_category"] = entity_category
    if options:
        entity["options"] = options
    if suggested_precision is not None:
        entity["suggested_display_precision"] = suggested_precision
    return entity


def _binary_entity(*, key: str, name: str, path: str, device_class: str | None = None) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "platform": "binary_sensor",
        "name": name,
        "unique_suffix": key,
        "value_template": "{{ value_json." + path + " }}",
        "payload_on": "True",
        "payload_off": "False",
    }
    if device_class:
        entity["device_class"] = device_class
    return entity


ENTITY_DEFINITIONS: list[dict[str, Any]] = [
    _sensor_entity(key="pv_power", name="PV Power", path="pv_power_watts", icon="mdi:solar-power", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="house_load", name="House Load", path="house_load_watts", icon="mdi:home-lightning-bolt", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="grid_power", name="Grid Power", path="grid_power_watts", icon="mdi:transmission-tower", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="grid_import", name="Grid Import", path="grid_import_watts", icon="mdi:transmission-tower-import", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="grid_export", name="Grid Export", path="grid_export_watts", icon="mdi:transmission-tower-export", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="battery_power", name="Battery Power", path="battery_power_watts", icon="mdi:battery-high", device_class="power", state_class="measurement", unit="W"),
    _sensor_entity(key="battery_soc", name="Battery SOC", path="battery_soc_percent", icon="mdi:battery", device_class="battery", state_class="measurement", unit="%"),
    _sensor_entity(key="battery_voltage", name="Battery Voltage", path="battery_voltage_volts", icon="mdi:sine-wave", device_class="voltage", state_class="measurement", unit="V", suggested_precision=1),
    _sensor_entity(key="battery_current", name="Battery Current", path="battery_current_amps", icon="mdi:current-dc", device_class="current", state_class="measurement", unit="A", suggested_precision=1),
    _sensor_entity(key="battery_mode", name="Battery Mode", path="battery_mode", icon="mdi:battery-sync", device_class="enum", options=["Standby", "Charging", "Discharging"]),
    _sensor_entity(key="inverter_temp", name="Inverter Temperature", path="inverter_temperature_celsius", icon="mdi:thermometer", device_class="temperature", state_class="measurement", unit="°C", suggested_precision=1),
    _sensor_entity(key="grid_voltage", name="Grid Voltage", path="grid_voltage_volts", icon="mdi:sine-wave", device_class="voltage", state_class="measurement", unit="V", suggested_precision=1),
    _sensor_entity(key="grid_frequency", name="Grid Frequency", path="grid_frequency_hz", icon="mdi:sine-wave", device_class="frequency", state_class="measurement", unit="Hz", suggested_precision=2),
    _sensor_entity(key="pv1_voltage", name="PV1 Voltage", path="pv1_voltage_volts", icon="mdi:solar-panel", device_class="voltage", state_class="measurement", unit="V", suggested_precision=1),
    _sensor_entity(key="pv1_current", name="PV1 Current", path="pv1_current_amps", icon="mdi:current-dc", device_class="current", state_class="measurement", unit="A", suggested_precision=1),
    _sensor_entity(key="pv2_voltage", name="PV2 Voltage", path="pv2_voltage_volts", icon="mdi:solar-panel", device_class="voltage", state_class="measurement", unit="V", suggested_precision=1),
    _sensor_entity(key="pv2_current", name="PV2 Current", path="pv2_current_amps", icon="mdi:current-dc", device_class="current", state_class="measurement", unit="A", suggested_precision=1),
    _sensor_entity(key="today_energy", name="Today Production", path="today_kwh", icon="mdi:calendar-today", device_class="energy", unit="kWh", suggested_precision=2),
    _sensor_entity(key="month_energy", name="Month Production", path="month_kwh", icon="mdi:calendar-month", device_class="energy", unit="kWh", suggested_precision=2),
    _sensor_entity(key="total_energy", name="Total Production", path="total_kwh", icon="mdi:solar-power-variant", device_class="energy", state_class="total_increasing", unit="kWh", suggested_precision=2),
    _sensor_entity(key="grid_buy_total", name="Grid Bought Total", path="grid_buy_kwh", icon="mdi:transmission-tower-import", device_class="energy", state_class="total_increasing", unit="kWh", suggested_precision=2),
    _sensor_entity(key="grid_sell_total", name="Grid Sold Total", path="grid_sell_kwh", icon="mdi:transmission-tower-export", device_class="energy", state_class="total_increasing", unit="kWh", suggested_precision=2),
    _sensor_entity(key="battery_charge_total", name="Battery Charge Total", path="battery_charge_kwh", icon="mdi:battery-plus", device_class="energy", state_class="total_increasing", unit="kWh", suggested_precision=2),
    _sensor_entity(key="battery_discharge_total", name="Battery Discharge Total", path="battery_discharge_kwh", icon="mdi:battery-minus", device_class="energy", state_class="total_increasing", unit="kWh", suggested_precision=2),
    _sensor_entity(key="self_use_rate", name="Self Use Rate", path="self_use_rate_percent", icon="mdi:home-percent", state_class="measurement", unit="%", suggested_precision=1),
    _sensor_entity(key="contributing_rate", name="Contribution Rate", path="contributing_rate_percent", icon="mdi:percent-circle", state_class="measurement", unit="%", suggested_precision=1),
    _sensor_entity(key="weather_today", name="Weather Today", path="weather_today_text", icon="mdi:weather-partly-cloudy"),
    _sensor_entity(key="weather_tomorrow", name="Weather Tomorrow", path="weather_tomorrow_text", icon="mdi:weather-partly-cloudy"),
    _sensor_entity(key="token_age", name="Token Age", path="token_age_seconds", icon="mdi:timer-outline", unit="s", entity_category="diagnostic"),
    _sensor_entity(key="token_refreshes", name="Token Refreshes", path="token_refresh_count", icon="mdi:key-refresh", entity_category="diagnostic"),
    _sensor_entity(key="api_base", name="API Base", path="api_base", icon="mdi:api", entity_category="diagnostic"),
    _sensor_entity(key="last_error", name="Last Error", path="last_error", icon="mdi:alert-circle-outline", entity_category="diagnostic"),
    _sensor_entity(key="last_success", name="Last Success", path="last_success_at", icon="mdi:clock-check-outline", device_class="timestamp", entity_category="diagnostic"),
    _binary_entity(key="backend_online", name="Backend Online", path="backend_online", device_class="connectivity"),
]


class HomeAssistantMqttBridge:
    """Publishes solar data to MQTT and exposes Home Assistant discovery."""

    def __init__(self, config: MqttConfig) -> None:
        self.config = config
        self.client: mqtt.Client | None = None
        self._lock = threading.Lock()
        self._connected = False
        self._last_state: dict[str, Any] | None = None
        self._discovery_sent = False

        self.state_topic = f"{self.config.base_topic}/{self.config.device_id}/state"
        self.availability_topic = f"{self.config.base_topic}/{self.config.device_id}/availability"

    def start(self) -> None:
        if not self.config.enabled:
            return

        client = mqtt.Client(client_id=self.config.client_id, clean_session=True)
        if self.config.username:
            client.username_pw_set(self.config.username, self.config.password)

        client.will_set(
            self.availability_topic,
            payload="offline",
            qos=self.config.qos,
            retain=True,
        )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect_async(self.config.host, self.config.port, keepalive=self.config.keepalive)
        client.loop_start()
        self.client = client

    def stop(self) -> None:
        if not self.client:
            return
        try:
            if self._connected:
                self.client.publish(self.availability_topic, payload="offline", qos=self.config.qos, retain=True)
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def publish_snapshot(self, snapshot: dict[str, Any], last_error: str | None = None) -> None:
        if not self.config.enabled:
            return
        payload = _flatten_snapshot(snapshot, last_error=last_error)
        payload["backend_online"] = last_error is None
        with self._lock:
            self._last_state = payload
        self._publish_state()

    def publish_error(self, snapshot: dict[str, Any] | None, error_message: str) -> None:
        if not self.config.enabled:
            return
        payload = _flatten_snapshot(snapshot, last_error=error_message)
        payload["backend_online"] = False
        with self._lock:
            self._last_state = payload
        self._publish_state()

    def _publish_state(self) -> None:
        if not self.client or not self._connected:
            return
        with self._lock:
            payload = dict(self._last_state or {})
        self.client.publish(
            self.state_topic,
            payload=json.dumps(payload),
            qos=self.config.qos,
            retain=self.config.retain,
        )

    def _publish_discovery(self) -> None:
        if not self.client:
            return

        device = {
            "identifiers": [self.config.device_id],
            "manufacturer": self.config.manufacturer,
            "model": self.config.model,
            "name": self.config.device_name,
        }
        if self.config.support_url:
            device["configuration_url"] = self.config.support_url

        for entity in ENTITY_DEFINITIONS:
            unique_id = f"{self.config.device_id}_{entity['unique_suffix']}"
            component = entity["platform"]
            topic = f"{self.config.discovery_prefix}/{component}/{unique_id}/config"
            payload = {
                "name": entity["name"],
                "unique_id": unique_id,
                "state_topic": self.state_topic,
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
                "value_template": entity["value_template"],
            }
            for option in (
                "icon",
                "device_class",
                "state_class",
                "unit_of_measurement",
                "entity_category",
                "options",
                "suggested_display_precision",
                "payload_on",
                "payload_off",
            ):
                if option in entity:
                    payload[option] = entity[option]

            self.client.publish(topic, payload=json.dumps(payload), qos=self.config.qos, retain=True)

        self._discovery_sent = True

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: int, _properties: Any = None) -> None:
        self._connected = reason_code == 0
        if not self._connected:
            return
        client.subscribe(self.config.ha_status_topic, qos=self.config.qos)
        client.publish(self.availability_topic, payload="online", qos=self.config.qos, retain=True)
        self._publish_discovery()
        self._publish_state()

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _reason_code: int, _properties: Any = None) -> None:
        self._connected = False

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        if message.topic == self.config.ha_status_topic and message.payload.decode("utf-8", errors="ignore") == "online":
            self._publish_discovery()
            self._publish_state()
