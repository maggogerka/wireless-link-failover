#!/usr/bin/env python3
"""Compare ESP32 and ESP32-S3 under the same failover configuration."""

from __future__ import annotations

import json

from analyze_failover_comparison import (
    FIGURES,
    RESULTS,
    ROOT,
    collect_series,
    configuration_differences,
    write_svg,
)


SERIES = (
    {
        "key": "esp32",
        "label": "ESP8266↔ESP32",
        "short_label": "ESP32",
        "color": "#2563EB",
        "summary": RESULTS / "failover_8266_32_controlled_5x_20261108_summary.json",
    },
    {
        "key": "esp32_s3",
        "label": "ESP8266↔ESP32-S3",
        "short_label": "ESP32-S3",
        "color": "#EA580C",
        "summary": RESULTS / "failover_8266_s3_standardized_5x_20261109_summary.json",
    },
)


def main() -> None:
    datasets = [collect_series(spec) for spec in SERIES]
    esp32, esp32_s3 = datasets
    differences = configuration_differences(esp32, esp32_s3)
    if differences:
        raise RuntimeError(f"Standardized configurations differ: {differences}")

    comparison = {
        "schema": "wlf.failover-comparison.v1",
        "comparison_id": "failover_esp32_vs_esp32s3_standardized_20261109",
        "date": "2026-11-09",
        "classification": "standardized_settings_with_documented_preparation_timing_deviation",
        "common_conditions": {
            "complete_transition_cycles_per_series": 5,
            "distance_cm": 100,
            "ssid": "Lab-2G",
            "band_ghz": 2.4,
            "channel": 6,
            "probe_interval_ms": 470,
            "window_ms": 5000,
            "fallback_loss_pct": 30,
            "recovery_success_pct": 80,
            "bad_windows_required": 2,
            "good_windows_required": 3,
            "recovery_probe_interval_ms": 940,
            "recovery_probe_guard_ms": 470,
            "espnow_stabilization_windows": 3,
            "wifi_power_save": False,
            "fault_type": "controlled_espnow_application_ack_suppression",
        },
        "configuration_differences": differences,
        "series": datasets,
        "observed_differences": {
            "fallback_average_ms_esp32s3_minus_esp32": round(
                esp32_s3["fallback_reaction_ms_descriptive"]["average"]
                - esp32["fallback_reaction_ms_descriptive"]["average"],
                3,
            ),
            "recovery_average_ms_esp32s3_minus_esp32": round(
                esp32_s3["recovery_reaction_ms_descriptive"]["average"]
                - esp32["recovery_reaction_ms_descriptive"]["average"],
                3,
            ),
            "baseline_success_percentage_points_esp32s3_minus_esp32": round(
                esp32_s3["baseline_espnow_success_pct"] - esp32["baseline_espnow_success_pct"], 3
            ),
            "udp_success_percentage_points_esp32s3_minus_esp32": round(
                esp32_s3["udp_success_pct"] - esp32["udp_success_pct"], 3
            ),
        },
        "protocol_deviation": {
            "affected_series": "esp32_s3",
            "description": (
                "The S3 controlled fault began 16.284-26.429 seconds after preparation rather "
                "than after the planned 30 seconds. All three stabilization windows completed "
                "with 100 percent ACK before every fault."
            ),
            "analysis_scope": (
                "Fallback and post-fault recovery timing remain comparable under identical state-machine "
                "settings; baseline exposure duration must not be compared as if it were identical."
            ),
        },
        "conclusion": (
            "Both pairs completed fallback and recovery in all five cycles. With identical settings "
            "and Wi-Fi power saving disabled, average recovery differed by only 15 ms: 15.214 s for "
            "ESP32 and 15.229 s for ESP32-S3. The earlier long S3 recovery tail was therefore not "
            "reproduced under the standardized algorithm configuration."
        ),
        "scope_limitation": (
            "Five cycles per pair and an unbalanced 3/2 direction split are sufficient for an "
            "engineering demonstration but not for a directional hardware-effect claim."
        ),
        "figure": "experiments/figures/failover_comparison_standardized_20261109.svg",
    }

    output_json = RESULTS / "failover_comparison_standardized_20261109.json"
    output_svg = FIGURES / "failover_comparison_standardized_20261109.svg"
    output_json.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_svg(
        datasets,
        output_svg,
        title_value="Сравнение при одинаковых настройках автомата",
        footer_lines=(
            "Настройки 470/5000/30/80 и энергосбережение Wi-Fi отключены в обеих сериях.",
            "В серии S3 fault включался раньше 30 с, но после трёх стабильных окон со 100 % ACK.",
        ),
    )
    print(output_json.relative_to(ROOT).as_posix())
    print(output_svg.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
