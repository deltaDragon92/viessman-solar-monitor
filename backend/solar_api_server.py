#!/usr/bin/env python3
"""
Local HTTP server that exposes a cached real-time solar snapshot for the Tauri UI.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import mimetypes
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mqtt_bridge import HomeAssistantMqttBridge, MqttConfig
from solar_portal import SolarPortalClient, normalize_snapshot

DEFAULT_HOST = os.getenv("SOLAR_API_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("SOLAR_API_PORT", "8765"))
DEFAULT_POLL_INTERVAL_SECONDS = float(os.getenv("SOLAR_POLL_INTERVAL_SECONDS", "1"))
MAX_HISTORY_POINTS = int(os.getenv("SOLAR_HISTORY_POINTS", "60"))
MAX_BACKOFF_SECONDS = float(os.getenv("SOLAR_MAX_BACKOFF_SECONDS", "30"))
DIST_DIR = Path(os.getenv("SOLAR_WEB_DIST", Path(__file__).resolve().parents[1] / "ui" / "dist"))
HISTORY_FILE = Path(os.getenv("SOLAR_HISTORY_FILE", Path(__file__).with_name("solar_history.jsonl")))

TIMEFRAME_SPECS = {
    "minutes": {"points": 60, "step_seconds": 60},
    "hours": {"points": 24, "step_seconds": 3600},
    "days": {"points": 30, "step_seconds": 86400},
    "months": {"points": 12, "step_seconds": 30 * 86400},
    "years": {"points": 5, "step_seconds": 365 * 86400},
}


class SnapshotStore:
    """Thread-safe store containing the latest snapshot and backend state."""

    def __init__(self, poll_interval_seconds: float) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._lock = threading.Lock()
        self.snapshot: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_attempt_at: float | None = None
        self.last_update_at: float | None = None
        self.error_streak = 0
        self.next_retry_delay_seconds = poll_interval_seconds
        self.history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY_POINTS)
        self.history_file = HISTORY_FILE
        self.running = True
        self._load_history_from_disk()

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self.snapshot = snapshot
            self.last_error = None
            self.last_update_at = time.time()
            self.last_attempt_at = self.last_update_at
            self.error_streak = 0
            self.next_retry_delay_seconds = self.poll_interval_seconds
            self.history.append({
                "timestamp": snapshot.get("fetched_at", self.last_update_at),
                "pv_power_watts": snapshot.get("realtime", {}).get("pv_power_watts", 0),
                "battery_soc_percent": snapshot.get("battery", {}).get("soc_percent", 0),
                "grid_power_watts": snapshot.get("grid", {}).get("power_watts", 0),
            })
            self._append_history_to_disk(self.history[-1])

    def set_error(self, error_message: str) -> None:
        with self._lock:
            self.last_error = error_message
            self.last_attempt_at = time.time()
            self.error_streak += 1
            self.next_retry_delay_seconds = min(
                self.poll_interval_seconds * (2 ** self.error_streak),
                MAX_BACKOFF_SECONDS,
            )

    def read(self) -> dict[str, Any]:
        with self._lock:
            return {
                "snapshot": self.snapshot,
                "last_error": self.last_error,
                "last_attempt_at": self.last_attempt_at,
                "last_update_at": self.last_update_at,
                "poll_interval_seconds": self.poll_interval_seconds,
                "error_streak": self.error_streak,
                "next_retry_delay_seconds": self.next_retry_delay_seconds,
                "history": list(self.history),
            }

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_history_file()

    def _load_history_from_disk(self) -> None:
        for item in self._read_history_file()[-MAX_HISTORY_POINTS:]:
            self.history.append(item)

    def _read_history_file(self) -> list[dict[str, Any]]:
        if not self.history_file.exists():
            return []

        rows: list[dict[str, Any]] = []
        with self.history_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _append_history_to_disk(self, item: dict[str, Any]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with self.history_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item) + "\n")


def aggregate_history(history: list[dict[str, Any]], timeframe: str) -> list[dict[str, Any]]:
    spec = TIMEFRAME_SPECS.get(timeframe, TIMEFRAME_SPECS["minutes"])
    points = spec["points"]
    step_seconds = spec["step_seconds"]
    now = int(time.time())
    bucket_start = now - ((points - 1) * step_seconds)

    buckets: list[dict[str, Any]] = []
    for index in range(points):
        current_start = bucket_start + index * step_seconds
        buckets.append({
            "timestamp": current_start,
            "pv_power_watts": 0.0,
            "battery_soc_percent": 0.0,
            "grid_power_watts": 0.0,
            "count": 0,
        })

    for item in history:
        timestamp = int(float(item.get("timestamp", 0)))
        if timestamp < bucket_start:
            continue
        bucket_index = min((timestamp - bucket_start) // step_seconds, points - 1)
        bucket = buckets[int(bucket_index)]
        bucket["pv_power_watts"] += float(item.get("pv_power_watts", 0) or 0)
        bucket["battery_soc_percent"] += float(item.get("battery_soc_percent", 0) or 0)
        bucket["grid_power_watts"] += float(item.get("grid_power_watts", 0) or 0)
        bucket["count"] += 1

    aggregated: list[dict[str, Any]] = []
    for bucket in buckets:
        count = bucket.pop("count")
        if count:
            aggregated.append({
                "timestamp": bucket["timestamp"],
                "pv_power_watts": bucket["pv_power_watts"] / count,
                "battery_soc_percent": bucket["battery_soc_percent"] / count,
                "grid_power_watts": bucket["grid_power_watts"] / count,
            })
        else:
            aggregated.append({
                "timestamp": bucket["timestamp"],
                "pv_power_watts": None,
                "battery_soc_percent": None,
                "grid_power_watts": None,
            })
    return aggregated


def build_payload(store: SnapshotStore, client: SolarPortalClient, timeframe: str = "minutes") -> dict[str, Any]:
    state = store.read()
    history = aggregate_history(store.get_history(), timeframe)
    return {
        "ok": state["snapshot"] is not None and state["last_error"] is None,
        "snapshot": state["snapshot"],
        "backend": {
            "poll_interval_seconds": state["poll_interval_seconds"],
            "last_attempt_at": state["last_attempt_at"],
            "last_update_at": state["last_update_at"],
            "last_error": state["last_error"],
            "error_streak": state["error_streak"],
            "next_retry_delay_seconds": state["next_retry_delay_seconds"],
            "history": history,
            "timeframe": timeframe,
            "client_status": client.get_status(),
        },
    }


class SolarRequestHandler(BaseHTTPRequestHandler):
    """Serves the cached solar snapshot as JSON."""

    store: SnapshotStore
    client: SolarPortalClient

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        parsed = urlparse(self.path)
        request_path = parsed.path
        timeframe = "minutes"
        if parsed.query:
            for query_part in parsed.query.split("&"):
                if query_part.startswith("timeframe="):
                    timeframe = query_part.split("=", 1)[1] or "minutes"
                    break

        if request_path == "/api/status":
            self._send_json(HTTPStatus.OK, build_payload(self.store, self.client, timeframe=timeframe))
            return

        if request_path == "/api/snapshot":
            payload = build_payload(self.store, self.client, timeframe=timeframe)
            status_code = HTTPStatus.OK if payload["ok"] else HTTPStatus.SERVICE_UNAVAILABLE
            self._send_json(status_code, payload)
            return

        self._send_static(request_path)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status_code: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, request_path: str) -> None:
        dist_dir = DIST_DIR
        if not dist_dir.exists():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": f"Web build not found at {dist_dir}"},
            )
            return

        safe_path = unquote(request_path).lstrip("/") or "index.html"
        candidate = (dist_dir / safe_path).resolve()
        index_file = (dist_dir / "index.html").resolve()

        try:
            candidate.relative_to(dist_dir.resolve())
        except ValueError:
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Forbidden"})
            return

        if not candidate.exists() or candidate.is_dir():
            candidate = index_file

        if not candidate.exists():
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        body = candidate.read_bytes()
        mime_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def poll_forever(
    store: SnapshotStore,
    client: SolarPortalClient,
    mqtt_bridge: HomeAssistantMqttBridge | None = None,
) -> None:
    """Background loop that refreshes the cached snapshot."""
    while store.running:
        try:
            data = client.fetch_plant_data()
            snapshot = normalize_snapshot(data, client.get_status())
            store.set_snapshot(snapshot)
            if mqtt_bridge:
                mqtt_bridge.publish_snapshot(snapshot)
        except Exception as exc:
            store.set_error(str(exc))
            if mqtt_bridge:
                mqtt_bridge.publish_error(store.read()["snapshot"], str(exc))

        delay = store.read()["next_retry_delay_seconds"]
        time.sleep(delay)


def build_server(host: str, port: int, store: SnapshotStore, client: SolarPortalClient) -> ThreadingHTTPServer:
    handler = type(
        "BoundSolarRequestHandler",
        (SolarRequestHandler,),
        {"store": store, "client": client},
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local solar snapshot server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args()

    client = SolarPortalClient.from_env()
    store = SnapshotStore(poll_interval_seconds=args.poll_interval)
    mqtt_bridge = HomeAssistantMqttBridge(MqttConfig.from_env(client.credentials.plant_id))
    mqtt_bridge.start()

    thread = threading.Thread(target=poll_forever, args=(store, client, mqtt_bridge), daemon=True)
    thread.start()

    server = build_server(args.host, args.port, store, client)
    print(f"Solar API server listening on http://{args.host}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.running = False
        mqtt_bridge.stop()
        server.server_close()


if __name__ == "__main__":
    main()
