#!/usr/bin/env python3
"""Extract the five standardized ESP8266/ESP32-S3 failover cycles.

The GUI log also contains a long idle period and earlier diagnostics.  This
script selects the last five complete cycles, reconstructs their timing and
window metrics, and records the observed preparation-time protocol deviation.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_LOG = ROOT / "experiments" / "raw" / "serial_20261109_005533_standardized_s3_snapshot.jsonl"
RESULTS = ROOT / "experiments" / "results"
RUN_PREFIX = "failover_8266_s3_standardized_repeat"
SUMMARY_NAME = "failover_8266_s3_standardized_5x_20261109_summary.json"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def duration_ms(start: dict[str, Any], end: dict[str, Any]) -> int:
    return round((parse_time(end["host_time"]) - parse_time(start["host_time"])).total_seconds() * 1000)


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "host_time" not in event or "type" not in event:
                continue
            event["_line"] = line_number
            events.append(event)
    return events


def first_event(events: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    return next((event for event in events if predicate(event)), None)


def percent(acks: int, probes: int) -> float:
    return round(acks * 100.0 / probes, 3) if probes else 0.0


def describe(values: list[int]) -> dict[str, float | int]:
    return {
        "minimum": min(values),
        "average": round(statistics.mean(values), 3),
        "median": statistics.median(values),
        "maximum": max(values),
        "sample_standard_deviation": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
    }


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if not key.startswith("_")}


def find_complete_cycles(
    events: list[dict[str, Any]], allowed_nodes: set[str]
) -> list[dict[str, Any]]:
    starts = [
        index
        for index, event in enumerate(events)
        if event.get("type") == "failover_enabled" and event.get("node_id") in allowed_nodes
    ]
    cycles: list[dict[str, Any]] = []

    for position, start_index in enumerate(starts):
        stop_index = starts[position + 1] if position + 1 < len(starts) else len(events)
        chunk = events[start_index:stop_index]
        start = chunk[0]
        sender = start["node_id"]

        fault_on = first_event(
            chunk,
            lambda event: event.get("type") == "fault_control"
            and event.get("active") is True
            and event.get("node_id") != sender,
        )
        if not fault_on:
            continue
        receiver = fault_on["node_id"]
        fallback = first_event(
            chunk,
            lambda event: event.get("type") == "failover_transition"
            and event.get("node_id") == sender
            and event.get("from") == "esp-now"
            and event.get("to") == "udp"
            and parse_time(event["host_time"]) >= parse_time(fault_on["host_time"]),
        )
        if not fallback:
            continue
        fault_off = first_event(
            chunk,
            lambda event: event.get("type") == "fault_control"
            and event.get("active") is False
            and event.get("node_id") == receiver
            and parse_time(event["host_time"]) >= parse_time(fallback["host_time"]),
        )
        if not fault_off:
            continue
        recovery = first_event(
            chunk,
            lambda event: event.get("type") == "failover_transition"
            and event.get("node_id") == sender
            and event.get("from") == "udp"
            and event.get("to") == "esp-now"
            and parse_time(event["host_time"]) >= parse_time(fault_off["host_time"]),
        )
        if not recovery:
            continue

        cycles.append(
            {
                "chunk": chunk,
                "start": start,
                "sender": sender,
                "receiver": receiver,
                "fault_on": fault_on,
                "fallback": fallback,
                "fault_off": fault_off,
                "recovery": recovery,
            }
        )
    return cycles


def latest_wifi_status(events: list[dict[str, Any]], node: str, before: datetime) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event.get("type") == "wifi_status"
        and event.get("node_id") == node
        and parse_time(event["host_time"]) <= before
    ]
    return public_event(matches[-1]) if matches else None


def build_run(
    cycle: dict[str, Any],
    repeat: int,
    raw_relative: str,
    run_prefix: str,
    preparation_tolerance_ms: int = 0,
) -> dict[str, Any]:
    chunk = cycle["chunk"]
    start = cycle["start"]
    sender = cycle["sender"]
    receiver = cycle["receiver"]
    fault_on = cycle["fault_on"]
    fallback = cycle["fallback"]
    fault_off = cycle["fault_off"]
    recovery = cycle["recovery"]

    start_time = parse_time(start["host_time"])
    fault_on_time = parse_time(fault_on["host_time"])
    fallback_time = parse_time(fallback["host_time"])
    fault_off_time = parse_time(fault_off["host_time"])
    recovery_time = parse_time(recovery["host_time"])

    sender_windows = [
        event
        for event in chunk
        if event.get("type") == "failover_window" and event.get("node_id") == sender
    ]
    baseline_windows = [
        event for event in sender_windows if start_time <= parse_time(event["host_time"]) < fault_on_time
    ]
    baseline_probes = sum(event.get("espnow_probes", 0) for event in baseline_windows)
    baseline_acks = sum(event.get("espnow_acks", 0) for event in baseline_windows)

    fallback_cutoff = fallback_time + timedelta(seconds=1)
    degradation_windows = [
        event
        for event in sender_windows
        if fault_on_time <= parse_time(event["host_time"]) <= fallback_cutoff
        and event.get("espnow_probes", 0) > 0
        and event.get("udp_probes", 0) == 0
    ]

    recovery_cutoff = recovery_time + timedelta(seconds=1)
    udp_windows = [
        event
        for event in sender_windows
        if fallback_time <= parse_time(event["host_time"]) <= recovery_cutoff
        and event.get("udp_probes", 0) > 0
    ]
    udp_probes = sum(event.get("udp_probes", 0) for event in udp_windows)
    udp_acks = sum(event.get("udp_acks", 0) for event in udp_windows)

    recovery_windows = [
        event
        for event in sender_windows
        if fault_off_time <= parse_time(event["host_time"]) <= recovery_cutoff
        and event.get("espnow_probes", 0) > 0
    ]
    final_good_windows = recovery_windows[-3:]
    final_good_probes = sum(event.get("espnow_probes", 0) for event in final_good_windows)
    final_good_acks = sum(event.get("espnow_acks", 0) for event in final_good_windows)

    config_status = first_event(
        chunk,
        lambda event: event.get("type") == "failover_status"
        and event.get("node_id") == sender
        and event.get("enabled") is True,
    )
    if not config_status:
        raise RuntimeError(f"No failover_status for repetition {repeat}")

    final_statuses = [
        event
        for event in chunk
        if event.get("type") == "failover_status"
        and event.get("node_id") == sender
        and parse_time(event["host_time"]) >= recovery_time
    ]
    final_status = final_statuses[-1] if final_statuses else None

    preparation_to_fault_ms = duration_ms(start, fault_on)
    required_wait_ms = 30000
    required_baseline_windows = 5
    protocol_checks = {
        "preparation_wait_at_least_30000_ms_with_timestamp_tolerance": (
            preparation_to_fault_ms >= required_wait_ms - preparation_tolerance_ms
        ),
        "at_least_5_complete_pre_fault_windows": len(baseline_windows) >= required_baseline_windows,
        "three_stabilization_windows_completed": len(baseline_windows) >= 3,
        "stabilization_windows_all_100_pct": all(
            event.get("espnow_success_pct") == 100 for event in baseline_windows[:3]
        ),
    }
    protocol_compliant = all(protocol_checks.values())

    degradation_public = [
        {
            "espnow_probes": event.get("espnow_probes", 0),
            "espnow_acks": event.get("espnow_acks", 0),
            "espnow_success_pct": event.get("espnow_success_pct", 0),
        }
        for event in degradation_windows[-2:]
    ]
    degradation_probes = sum(window["espnow_probes"] for window in degradation_public)
    degradation_acks = sum(window["espnow_acks"] for window in degradation_public)

    recovery_pct = [event.get("espnow_success_pct", 0) for event in recovery_windows]
    final_good_pct = [event.get("espnow_success_pct", 0) for event in final_good_windows]

    return {
        "schema": "wlf.standardized-experiment-run.v1",
        "test_id": f"{run_prefix}_{repeat:02d}_20261109",
        "date": "2026-11-09",
        "repeat": repeat,
        "transition_cycle_valid": True,
        "protocol_compliant": protocol_compliant,
        "classification": (
            "standardized_settings_protocol_compliant"
            if protocol_compliant
            else "standardized_settings_with_preparation_timing_deviation"
        ),
        "sender": sender,
        "fault_receiver": receiver,
        "distance_cm": 100,
        "configuration": {
            "probe_interval_ms": config_status["probe_interval_ms"],
            "window_ms": config_status["window_ms"],
            "fallback_loss_pct": config_status["fallback_loss_pct"],
            "recovery_success_pct": config_status["recovery_success_pct"],
            "bad_windows_required": config_status["bad_windows_required"],
            "good_windows_required": config_status["good_windows_required"],
            "recovery_probe_offset_ms": config_status["recovery_probe_offset_ms"],
            "recovery_probe_interval_ms": config_status["recovery_probe_interval_ms"],
            "recovery_probe_guard_ms": config_status["recovery_probe_guard_ms"],
            "espnow_stabilization_windows": config_status["espnow_stabilization_windows"],
            "wifi_power_save": False,
        },
        "protocol_adherence": {
            "preparation_to_fault_ms": preparation_to_fault_ms,
            "required_preparation_wait_ms": required_wait_ms,
            "host_timestamp_tolerance_ms": preparation_tolerance_ms,
            "complete_pre_fault_windows": len(baseline_windows),
            "required_pre_fault_windows": required_baseline_windows,
            "checks": protocol_checks,
        },
        "baseline": {
            "complete_windows": len(baseline_windows),
            "espnow_probes": baseline_probes,
            "espnow_acks": baseline_acks,
            "success_pct": percent(baseline_acks, baseline_probes),
            "window_success_pct": [event.get("espnow_success_pct", 0) for event in baseline_windows],
        },
        "controlled_fault": {
            "type": "espnow_ack_suppression",
            "enabled_at": fault_on["host_time"],
            "disabled_at": fault_off["host_time"],
            "duration_ms": duration_ms(fault_on, fault_off),
        },
        "fallback": {
            "transition_at": fallback["host_time"],
            "from": "esp-now",
            "to": "udp",
            "reason": fallback.get("reason"),
            "automatic": fallback.get("automatic"),
            "reaction_from_fault_ms": duration_ms(fault_on, fallback),
            "degradation_windows": degradation_public,
            "combined_espnow_success_pct": percent(degradation_acks, degradation_probes),
        },
        "udp_reserve": {
            "time_in_udp_ms": duration_ms(fallback, recovery),
            "observed_probes": udp_probes,
            "observed_acks": udp_acks,
            "success_pct": percent(udp_acks, udp_probes),
        },
        "recovery": {
            "transition_at": recovery["host_time"],
            "from": "udp",
            "to": "esp-now",
            "reason": recovery.get("reason"),
            "automatic": recovery.get("automatic"),
            "reaction_from_fault_removal_ms": duration_ms(fault_off, recovery),
            "all_window_success_pct": recovery_pct,
            "final_consecutive_good_windows": len(final_good_windows),
            "final_good_window_probes": final_good_probes,
            "final_good_window_acks": final_good_acks,
            "final_good_window_success_pct": percent(final_good_acks, final_good_probes),
            "final_good_window_success_pct_sequence": final_good_pct,
        },
        "final_state": {
            "active_transport": final_status.get("active_transport") if final_status else "esp-now",
            "automatic": final_status.get("automatic") if final_status else True,
            "switch_count": final_status.get("switch_count") if final_status else 2,
        },
        "raw_log": raw_relative,
        "raw_line_range": [start["_line"], recovery["_line"]],
        "interpretation": (
            "The automatic fallback and recovery cycle completed under the standardized radio and "
            "recovery settings. The controlled fault was injected after all three stabilization "
            "windows, but before the planned 30-second preparation interval had elapsed."
        ),
    }


def direction_summary(runs: list[dict[str, Any]], sender: str) -> dict[str, Any]:
    selected = [run for run in runs if run["sender"] == sender]
    if not selected:
        raise RuntimeError(f"No runs found for sender {sender}")
    probes = sum(run["baseline"]["espnow_probes"] for run in selected)
    acks = sum(run["baseline"]["espnow_acks"] for run in selected)
    udp_probes = sum(run["udp_reserve"]["observed_probes"] for run in selected)
    udp_acks = sum(run["udp_reserve"]["observed_acks"] for run in selected)
    return {
        "sender": sender,
        "receiver": selected[0]["fault_receiver"],
        "runs": len(selected),
        "baseline_espnow_probes": probes,
        "baseline_espnow_acks": acks,
        "baseline_espnow_success_pct": percent(acks, probes),
        "fallback_reaction_ms": describe([run["fallback"]["reaction_from_fault_ms"] for run in selected]),
        "recovery_reaction_ms": describe(
            [run["recovery"]["reaction_from_fault_removal_ms"] for run in selected]
        ),
        "udp_probes": udp_probes,
        "udp_acks": udp_acks,
        "udp_success_pct": percent(udp_acks, udp_probes),
    }


def main() -> None:
    events = read_events(RAW_LOG)
    cycles = find_complete_cycles(events, {"node8266", "node32s3"})
    if len(cycles) < 5:
        raise RuntimeError(f"Expected at least five complete cycles, found {len(cycles)}")
    selected_cycles = cycles[-5:]

    raw_relative = RAW_LOG.relative_to(ROOT).as_posix()
    runs = [
        build_run(cycle, index, raw_relative, RUN_PREFIX)
        for index, cycle in enumerate(selected_cycles, 1)
    ]
    for run in runs:
        output = RESULTS / f"{run['test_id']}.json"
        output.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    baseline_probes = sum(run["baseline"]["espnow_probes"] for run in runs)
    baseline_acks = sum(run["baseline"]["espnow_acks"] for run in runs)
    udp_probes = sum(run["udp_reserve"]["observed_probes"] for run in runs)
    udp_acks = sum(run["udp_reserve"]["observed_acks"] for run in runs)
    recovery_probes = sum(run["recovery"]["final_good_window_probes"] for run in runs)
    recovery_acks = sum(run["recovery"]["final_good_window_acks"] for run in runs)
    raw_hash = hashlib.sha256(RAW_LOG.read_bytes()).hexdigest()
    first_start = parse_time(selected_cycles[0]["start"]["host_time"])

    wifi_status = {
        node: latest_wifi_status(events, node, first_start)
        for node in ("node8266", "node32s3")
    }
    summary = {
        "schema": "wlf.standardized-experiment-summary.v1",
        "test_id": "failover_8266_s3_standardized_5x_20261109",
        "date": "2026-11-09",
        "classification": "complete_transition_series_with_preparation_timing_deviation",
        "complete_transition_cycles": 5,
        "protocol_compliant_cycles": sum(run["protocol_compliant"] for run in runs),
        "distance_cm": 100,
        "access_point": {
            "ssid": "Lab-2G",
            "band_ghz": 2.4,
            "channel": 6,
        },
        "wifi_status_before_series": wifi_status,
        "configuration": runs[0]["configuration"],
        "protocol_deviation": {
            "description": (
                f"ACK suppression was enabled {min(run['protocol_adherence']['preparation_to_fault_ms'] for run in runs) / 1000:.3f}-"
                f"{max(run['protocol_adherence']['preparation_to_fault_ms'] for run in runs) / 1000:.3f} seconds after preparation instead of "
                "waiting the planned 30 seconds. All three stabilization windows completed with "
                "100 percent ACK before every controlled fault, but zero to two additional baseline "
                "windows were available."
            ),
            "preparation_to_fault_ms": [
                run["protocol_adherence"]["preparation_to_fault_ms"] for run in runs
            ],
            "complete_pre_fault_windows": [
                run["protocol_adherence"]["complete_pre_fault_windows"] for run in runs
            ],
            "impact": (
                "The cycles remain suitable for algorithm transition and recovery timing analysis, "
                "but baseline stability totals and strict preregistered-protocol claims must be "
                "reported with this deviation."
            ),
        },
        "overall": {
            "successful_fallbacks": 5,
            "successful_recoveries": 5,
            "baseline_espnow_probes": baseline_probes,
            "baseline_espnow_acks": baseline_acks,
            "baseline_espnow_success_pct": percent(baseline_acks, baseline_probes),
            "fallback_reaction_ms": describe(
                [run["fallback"]["reaction_from_fault_ms"] for run in runs]
            ),
            "recovery_reaction_ms": describe(
                [run["recovery"]["reaction_from_fault_removal_ms"] for run in runs]
            ),
            "udp_reserve": {
                "observed_probes": udp_probes,
                "observed_acks": udp_acks,
                "success_pct": percent(udp_acks, udp_probes),
            },
            "final_recovery_windows": {
                "espnow_probes": recovery_probes,
                "espnow_acks": recovery_acks,
                "success_pct": percent(recovery_acks, recovery_probes),
            },
            "time_in_udp_ms": describe([run["udp_reserve"]["time_in_udp_ms"] for run in runs]),
        },
        "directions": [
            direction_summary(runs, "node32s3"),
            direction_summary(runs, "node8266"),
        ],
        "runs": [
            f"experiments/results/{run['test_id']}.json" for run in runs
        ],
        "raw_log": raw_relative,
        "raw_log_sha256": raw_hash,
        "integrity_status": "snapshot_complete",
        "interpretation": (
            "All five controlled faults caused automatic fallback and all five cycles returned "
            "automatically to ESP-NOW with the same 470/5000/30/80 settings and disabled Wi-Fi "
            "power saving used in the ESP32 series. Preparation was shorter than the documented "
            "30 seconds, so the deviation is retained in every run record and in the aggregate."
        ),
    }
    output_summary = RESULTS / SUMMARY_NAME
    output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for run in runs:
        print(
            run["repeat"],
            run["sender"],
            run["protocol_adherence"]["preparation_to_fault_ms"],
            run["fallback"]["reaction_from_fault_ms"],
            run["recovery"]["reaction_from_fault_removal_ms"],
            run["udp_reserve"]["success_pct"],
        )
    print(output_summary.relative_to(ROOT).as_posix())
    print(raw_hash)


if __name__ == "__main__":
    main()
