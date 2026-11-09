"""Run a reproducible bidirectional ESP-NOW packet series over two serial ports."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import serial


BAUD_RATE = 115200
SCHEMA = "wlf.experiment-summary.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Capture:
    def __init__(self, ports: list[str], raw_path: Path) -> None:
        self.raw_path = raw_path
        self.raw_file = raw_path.open("w", encoding="utf-8", newline="\n")
        self.connections: dict[str, serial.Serial] = {}
        self.buffers = {port: bytearray() for port in ports}
        self.events: list[tuple[str, dict[str, Any]]] = []

        for port in ports:
            connection = serial.Serial()
            connection.port = port
            connection.baudrate = BAUD_RATE
            connection.timeout = 0
            connection.write_timeout = 1
            connection.dsrdtr = False
            connection.rtscts = False
            connection.dtr = False
            connection.rts = False
            connection.open()
            self.connections[port] = connection

        # The CP210x board used in this experiment needs a short DTR pulse
        # before its UART starts forwarding data reliably. RTS stays inactive.
        for connection in self.connections.values():
            if connection.port == "COM3":
                connection.dtr = True
                time.sleep(0.1)
                connection.dtr = False

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()
        self.raw_file.close()

    def record(self, port: str, event: dict[str, Any]) -> None:
        event = dict(event)
        event["host_port"] = port
        event["host_time_utc"] = utc_now()
        self.events.append((port, event))
        self.raw_file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.raw_file.flush()

    def send(self, port: str, command: str) -> None:
        self.record(
            port,
            {
                "schema": "wlf.host.v1",
                "type": "host_command",
                "command": command,
            },
        )
        self.connections[port].write((command + "\n").encode("ascii"))
        self.connections[port].flush()

    def send_all(self, command: str) -> None:
        for port in self.connections:
            self.send(port, command)

    def poll(self) -> None:
        for port, connection in self.connections.items():
            waiting = connection.in_waiting
            if waiting:
                self.buffers[port].extend(connection.read(waiting))
            buffer = self.buffers[port]
            while b"\n" in buffer:
                raw_line, _, remainder = buffer.partition(b"\n")
                self.buffers[port] = buffer = bytearray(remainder)
                text = raw_line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                    if not isinstance(event, dict):
                        raise ValueError("JSON value is not an object")
                except (json.JSONDecodeError, ValueError):
                    event = {
                        "schema": "wlf.host.v1",
                        "type": "serial_text",
                        "text": text,
                    }
                self.record(port, event)

    def wait_for(
        self,
        predicate: Callable[[str, dict[str, Any]], bool],
        timeout: float,
        start_index: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        cursor = len(self.events) if start_index is None else start_index
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.poll()
            while cursor < len(self.events):
                item = self.events[cursor]
                cursor += 1
                if predicate(*item):
                    return item
            time.sleep(0.01)
        raise TimeoutError("Timed out waiting for a serial event")


def prepare(capture: Capture, ack_delay_ms: int) -> None:
    capture.send_all("QUIET ON")
    capture.send_all("AUTO OFF")
    capture.send_all(f"ACKDELAY {ack_delay_ms}")
    capture.send_all("RESETSTATS")
    time.sleep(0.35)
    capture.poll()


def collect_statuses(capture: Capture, timeout: float = 3.0) -> dict[str, dict[str, Any]]:
    start_index = len(capture.events)
    capture.send_all("STATS")
    statuses: dict[str, dict[str, Any]] = {}
    cursor = start_index
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(statuses) < len(capture.connections):
        capture.poll()
        while cursor < len(capture.events):
            port, event = capture.events[cursor]
            cursor += 1
            if event.get("type") == "radio_info":
                statuses[port] = event
        time.sleep(0.01)
    if len(statuses) != len(capture.connections):
        missing = sorted(set(capture.connections) - set(statuses))
        raise TimeoutError(f"No STATS response from: {', '.join(missing)}")
    return statuses


def run_direction(
    capture: Capture,
    transmitter: str,
    receiver: str,
    count: int,
    interval_ms: int,
    ack_delay_ms: int,
) -> dict[str, Any]:
    prepare(capture, ack_delay_ms)
    start_index = len(capture.events)
    capture.send(transmitter, f"TEST {count} {interval_ms}")
    timeout = count * interval_ms / 1000.0 + 15.0
    _, complete = capture.wait_for(
        lambda port, event: port == transmitter
        and event.get("type") == "test_complete",
        timeout=timeout,
        start_index=start_index,
    )
    statuses = collect_statuses(capture)
    accepted = int(complete.get("accepted", 0))
    acknowledged = int(complete.get("ack_received", 0))
    success_pct = round(100.0 * acknowledged / accepted, 3) if accepted else 0.0
    return {
        "transmitter_port": transmitter,
        "receiver_port": receiver,
        "test_complete": complete,
        "application_ack_success_pct": success_pct,
        "application_ack_loss_pct": round(100.0 - success_pct, 3),
        "transmitter_stats": statuses[transmitter],
        "receiver_stats": statuses[receiver],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", default="COM3", help="First transmitter port")
    parser.add_argument("--second", default="COM7", help="Second transmitter port")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--interval-ms", type=int, default=20)
    parser.add_argument("--ack-delay-ms", type=int, default=0)
    parser.add_argument(
        "--distance-cm",
        type=int,
        default=None,
        help="Measured antenna-to-antenna distance in centimetres",
    )
    parser.add_argument(
        "--condition",
        default="bench placement",
        help="Short description of placement, obstacles, or interference",
    )
    args = parser.parse_args()

    if (
        args.count < 1
        or args.interval_ms < 10
        or not 0 <= args.ack_delay_ms <= 100
    ):
        parser.error(
            "count must be positive, interval-ms at least 10, and "
            "ack-delay-ms between 0 and 100"
        )

    project_root = Path(__file__).resolve().parents[1]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_id = f"espnow_bidirectional_{stamp}"
    raw_path = project_root / "experiments" / "raw" / f"{test_id}.jsonl"
    result_path = project_root / "experiments" / "results" / f"{test_id}_summary.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    capture = Capture([args.first, args.second], raw_path)
    try:
        time.sleep(1.0)
        capture.poll()
        capture.send_all("INFO")
        time.sleep(0.5)
        capture.poll()
        device_info: dict[str, dict[str, Any]] = {}
        for port, event in capture.events:
            if event.get("type") == "device_info":
                device_info[port] = event
        if len(device_info) != 2:
            raise RuntimeError("Both boards did not answer INFO")

        first = run_direction(
            capture,
            args.first,
            args.second,
            args.count,
            args.interval_ms,
            args.ack_delay_ms,
        )
        second = run_direction(
            capture,
            args.second,
            args.first,
            args.count,
            args.interval_ms,
            args.ack_delay_ms,
        )
        capture.send_all("AUTO OFF")
        capture.poll()

        summary = {
            "schema": SCHEMA,
            "test_id": test_id,
            "captured_at_utc": utc_now(),
            "transport": "ESP-NOW broadcast with application ACK",
            "channel": 1,
            "packet_count_per_direction": args.count,
            "interval_ms": args.interval_ms,
            "ack_delay_ms": args.ack_delay_ms,
            "distance_cm": args.distance_cm,
            "condition": args.condition,
            "nodes": device_info,
            "directions": [first, second],
            "result": "completed",
            "raw_log": raw_path.relative_to(project_root).as_posix(),
        }
        result_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"RAW={raw_path}")
        print(f"SUMMARY={result_path}")
        return 0
    finally:
        capture.close()


if __name__ == "__main__":
    raise SystemExit(main())
