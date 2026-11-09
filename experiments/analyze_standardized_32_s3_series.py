#!/usr/bin/env python3
"""Extract the five protocol-compliant ESP32/ESP32-S3 failover cycles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from analyze_standardized_s3_series import (
    ROOT,
    build_run,
    describe,
    direction_summary,
    find_complete_cycles,
    latest_wifi_status,
    parse_time,
    percent,
    read_events,
)


RAW_LOG = ROOT / "experiments" / "raw" / "serial_20261109_032220_32_s3_snapshot.jsonl"
RESULTS = ROOT / "experiments" / "results"
RUN_PREFIX = "failover_32_s3_standardized_repeat"
SUMMARY_NAME = "failover_32_s3_standardized_5x_20261109_summary.json"


def main() -> None:
    events = read_events(RAW_LOG)
    cycles = find_complete_cycles(events, {"node32", "node32s3"})
    if len(cycles) < 5:
        raise RuntimeError(f"Expected at least five complete cycles, found {len(cycles)}")
    selected_cycles = cycles[-5:]

    raw_relative = RAW_LOG.relative_to(ROOT).as_posix()
    runs = [
        build_run(
            cycle,
            index,
            raw_relative,
            RUN_PREFIX,
            preparation_tolerance_ms=1000,
        )
        for index, cycle in enumerate(selected_cycles, 1)
    ]
    noncompliant = [run["repeat"] for run in runs if not run["protocol_compliant"]]
    if noncompliant:
        raise RuntimeError(f"Preparation protocol failed in repetitions: {noncompliant}")

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
        for node in ("node32", "node32s3")
    }

    summary = {
        "schema": "wlf.standardized-experiment-summary.v1",
        "test_id": "failover_32_s3_standardized_5x_20261109",
        "date": "2026-11-09",
        "classification": "protocol_compliant_standardized_series",
        "complete_transition_cycles": 5,
        "protocol_compliant_cycles": 5,
        "distance_cm": 100,
        "access_point": {
            "ssid": "Lab-2G",
            "band_ghz": 2.4,
            "channel": 6,
        },
        "wifi_status_before_series": wifi_status,
        "configuration": runs[0]["configuration"],
        "protocol_adherence": {
            "minimum_preparation_wait_ms": 30000,
            "host_timestamp_tolerance_ms": 1000,
            "preparation_to_fault_ms": [
                run["protocol_adherence"]["preparation_to_fault_ms"] for run in runs
            ],
            "complete_pre_fault_windows": [
                run["protocol_adherence"]["complete_pre_fault_windows"] for run in runs
            ],
            "all_cycles_compliant": True,
            "tolerance_rationale": (
                "The GUI timer starts after sending FAILOVER ON, while failover_enabled is logged "
                "after serial processing. Up to 1 second is allowed for this host/device timestamp skew; "
                "every cycle also completed at least five full pre-fault windows."
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
            direction_summary(runs, "node32"),
            direction_summary(runs, "node32s3"),
        ],
        "runs": [f"experiments/results/{run['test_id']}.json" for run in runs],
        "raw_log": raw_relative,
        "raw_log_sha256": raw_hash,
        "integrity_status": "snapshot_complete",
        "interpretation": (
            "All five controlled faults followed the 30-second preparation guard, caused automatic "
            "fallback to UDP, and returned automatically to ESP-NOW. Both nodes used the same "
            "470/5000/30/80 configuration with Wi-Fi power saving disabled."
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
