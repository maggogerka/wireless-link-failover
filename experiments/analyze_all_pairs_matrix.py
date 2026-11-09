#!/usr/bin/env python3
"""Build the final three-pair failover matrix and article figure."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from analyze_failover_comparison import (
    FIGURES,
    RESULTS,
    ROOT,
    collect_series,
    describe,
    dot,
    line,
    text,
)


SERIES = (
    {
        "key": "esp8266_esp32",
        "label": "ESP8266↔ESP32",
        "short_label": "8266–32",
        "color": "#2563EB",
        "summary": RESULTS / "failover_8266_32_controlled_5x_20261108_summary.json",
        "protocol_note": "protocol compliant",
    },
    {
        "key": "esp8266_esp32s3",
        "label": "ESP8266↔ESP32-S3",
        "short_label": "8266–S3",
        "color": "#EA580C",
        "summary": RESULTS / "failover_8266_s3_standardized_5x_20261109_summary.json",
        "protocol_note": "settings standardized; preparation timing deviation documented",
    },
    {
        "key": "esp32_esp32s3",
        "label": "ESP32↔ESP32-S3",
        "short_label": "32–S3",
        "color": "#16A34A",
        "summary": RESULTS / "failover_32_s3_standardized_5x_20261109_summary.json",
        "protocol_note": "protocol compliant with 1 s host/device timestamp tolerance",
    },
)


def point_panel_multi(
    x: int,
    y: int,
    width: int,
    height: int,
    title_value: str,
    datasets: list[dict[str, Any]],
    value_key: str,
    y_max: float,
    tick_step: float,
) -> list[str]:
    items = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
        'fill="#F9FAFB" stroke="#E5E7EB"/>'
    ]
    items.append(text(x + 20, y + 34, title_value, 20, weight=700))
    left, right = x + 62, x + width - 20
    top, bottom = y + 58, y + height - 72
    tick = 0.0
    while tick <= y_max + 0.001:
        py = bottom - (tick / y_max) * (bottom - top)
        items.append(line(left, py, right, py, stroke="#D1D5DB", dash="4 5"))
        items.append(text(left - 10, py + 5, f"{tick:g}", 14, anchor="end", fill="#4B5563"))
        tick += tick_step
    items.append(text(left - 38, top - 8, "с", 14, anchor="middle", fill="#4B5563"))

    centres = [left + (right - left) * fraction for fraction in (0.18, 0.50, 0.82)]
    jitter = (-20, -10, 0, 10, 20)
    for centre, dataset in zip(centres, datasets):
        values = [value / 1000.0 for value in dataset[value_key]]
        for index, value in enumerate(values):
            py = bottom - (value / y_max) * (bottom - top)
            items.append(dot(centre + jitter[index], py, dataset["color"]))
        mean_value = statistics.mean(values)
        mean_y = bottom - (mean_value / y_max) * (bottom - top)
        items.append(line(centre - 28, mean_y, centre + 28, mean_y, stroke=dataset["color"], width=4))
        items.append(text(centre, bottom + 29, dataset["short_label"], 14, anchor="middle", weight=600))
        items.append(text(centre, bottom + 51, f"{mean_value:.2f} с", 13, anchor="middle", fill=dataset["color"]))
    return items


def delivery_panel_multi(
    x: int, y: int, width: int, height: int, datasets: list[dict[str, Any]]
) -> list[str]:
    items = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
        'fill="#F9FAFB" stroke="#E5E7EB"/>'
    ]
    items.append(text(x + 20, y + 34, "Доставка прикладных ACK", 20, weight=700))
    left, right = x + 62, x + width - 20
    top, bottom = y + 58, y + height - 72
    y_min, y_max = 60.0, 101.0
    for tick in (60, 70, 80, 90, 100):
        py = bottom - ((tick - y_min) / (y_max - y_min)) * (bottom - top)
        items.append(line(left, py, right, py, stroke="#D1D5DB", dash="4 5"))
        items.append(text(left - 10, py + 5, str(tick), 14, anchor="end", fill="#4B5563"))
    items.append(text(left - 38, top - 8, "%", 14, anchor="middle", fill="#4B5563"))

    centres = [left + (right - left) * fraction for fraction in (0.18, 0.50, 0.82)]
    for centre, dataset in zip(centres, datasets):
        baseline = dataset["baseline_espnow_success_pct"]
        udp = dataset["udp_success_pct"]
        baseline_y = bottom - ((baseline - y_min) / (y_max - y_min)) * (bottom - top)
        udp_y = bottom - ((udp - y_min) / (y_max - y_min)) * (bottom - top)
        items.append(line(centre, baseline_y, centre, udp_y, stroke=dataset["color"], width=2))
        items.append(dot(centre, baseline_y, dataset["color"]))
        items.append(dot(centre, udp_y, dataset["color"]))
        items.append(text(centre, baseline_y - 13, f"{baseline:.1f}", 13, anchor="middle", fill=dataset["color"], weight=600))
        items.append(text(centre, udp_y + 24, f"UDP {udp:.1f}", 13, anchor="middle", fill=dataset["color"], weight=600))
        items.append(text(centre, bottom + 29, dataset["short_label"], 14, anchor="middle", weight=600))
    items.append(text(x + width / 2, bottom + 54, "Верхняя точка — ESP-NOW до fault", 13, anchor="middle", fill="#6B7280"))
    return items


def write_figure(datasets: list[dict[str, Any]], output: Path) -> None:
    width, height = 1440, 800
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        text(40, 50, "Failover во всех трёх аппаратных парах", 30, weight=700),
        text(40, 80, "По 5 контролируемых циклов, настройки 470/5000/30/80, расстояние 1 м, Wi-Fi power save отключён", 17, fill="#4B5563"),
    ]
    for index, dataset in enumerate(datasets):
        lx = 760 + index * 210
        items.append(f'<rect x="{lx}" y="38" width="18" height="18" rx="3" fill="{dataset["color"]}"/>')
        items.append(text(lx + 27, 53, dataset["short_label"], 16, weight=600))

    items.extend(point_panel_multi(40, 115, 430, 520, "Переход ESP-NOW → UDP", datasets, "fallback_reaction_ms", 12, 2))
    items.extend(point_panel_multi(505, 115, 430, 520, "Возврат UDP → ESP-NOW", datasets, "recovery_reaction_ms", 22, 2))
    items.extend(delivery_panel_multi(970, 115, 430, 520, datasets))
    items.append(text(40, 680, "Во всех парах переход и возврат состоялись в 5 из 5 циклов; горизонтальная черта — среднее.", 16, fill="#166534", weight=600))
    items.append(text(40, 711, "Низкая UDP-доставка 32–S3 (68,5 %) не помешала восстановлению ESP-NOW, но требует отдельного исследования UDP.", 15, fill="#B45309", weight=600))
    items.append(text(40, 739, "Серия 8266–S3 имеет документированное отклонение времени подготовки; настройки и три стабилизационных окна совпадали.", 14, fill="#6B7280"))
    items.append(text(1398, 778, "Wireless Link Failover · 09.11.2026", 13, anchor="end", fill="#6B7280"))
    items.append("</svg>")
    output.write_text("\n".join(items) + "\n", encoding="utf-8")


def main() -> None:
    datasets = [collect_series(spec) for spec in SERIES]
    configs = [dataset["configuration"] for dataset in datasets]
    if any(config != configs[0] for config in configs[1:]):
        raise RuntimeError("All-pair matrix requires identical failover configurations")

    for dataset, spec in zip(datasets, SERIES):
        dataset["protocol_note"] = spec["protocol_note"]

    all_fallback = [value for dataset in datasets for value in dataset["fallback_reaction_ms"]]
    all_recovery = [value for dataset in datasets for value in dataset["recovery_reaction_ms"]]
    all_udp_time = [value for dataset in datasets for value in dataset["time_in_udp_ms"]]

    source_summaries = [json.loads(Path(spec["summary"]).read_text(encoding="utf-8")) for spec in SERIES]
    baseline_probes = sum(summary["overall"]["baseline_espnow_probes"] for summary in source_summaries)
    baseline_acks = sum(summary["overall"]["baseline_espnow_acks"] for summary in source_summaries)
    udp_probes = sum(summary["overall"]["udp_reserve"]["observed_probes"] for summary in source_summaries)
    udp_acks = sum(summary["overall"]["udp_reserve"]["observed_acks"] for summary in source_summaries)
    recovery_probes = sum(summary["overall"]["final_recovery_windows"]["espnow_probes"] for summary in source_summaries)
    recovery_acks = sum(summary["overall"]["final_recovery_windows"]["espnow_acks"] for summary in source_summaries)

    matrix = {
        "schema": "wlf.all-pairs-failover-matrix.v1",
        "matrix_id": "failover_all_pairs_standardized_20261109",
        "date": "2026-11-09",
        "classification": "all_pairwise_transition_matrix_with_documented_timing_deviation",
        "common_configuration": configs[0],
        "conditions": {
            "cycles_per_pair": 5,
            "distance_cm": 100,
            "ssid": "Lab-2G",
            "band_ghz": 2.4,
            "channel": 6,
        },
        "overall": {
            "hardware_pairs": 3,
            "complete_cycles": 15,
            "successful_fallbacks": 15,
            "successful_recoveries": 15,
            "baseline_espnow_probes": baseline_probes,
            "baseline_espnow_acks": baseline_acks,
            "baseline_espnow_success_pct": round(baseline_acks * 100.0 / baseline_probes, 3),
            "fallback_reaction_ms": describe(all_fallback),
            "recovery_reaction_ms": describe(all_recovery),
            "udp_reserve": {
                "observed_probes": udp_probes,
                "observed_acks": udp_acks,
                "success_pct": round(udp_acks * 100.0 / udp_probes, 3),
            },
            "final_recovery_windows": {
                "espnow_probes": recovery_probes,
                "espnow_acks": recovery_acks,
                "success_pct": round(recovery_acks * 100.0 / recovery_probes, 3),
            },
            "time_in_udp_ms": describe(all_udp_time),
        },
        "pairs": datasets,
        "supported_claims": [
            "automatic ESP-NOW to UDP fallback completed in all 15 controlled cycles",
            "automatic UDP to ESP-NOW recovery completed in all 15 controlled cycles",
            "the same firmware state machine and thresholds operated on all three hardware pairs",
        ],
        "unsupported_claims": [
            "simultaneous failover of three active senders",
            "guaranteed UDP packet delivery",
            "hardware-platform superiority",
            "physical-link or power-failure tolerance",
        ],
        "key_observation": (
            "ESP32/ESP32-S3 reserve UDP application-ACK delivery was 74/108 (68.519 percent), "
            "while the pair still recovered automatically and delivered 79/80 ACK in the final "
            "ESP-NOW recovery windows."
        ),
        "figure": "experiments/figures/failover_all_pairs_20261109.svg",
    }

    output_json = RESULTS / "failover_all_pairs_20261109.json"
    output_svg = FIGURES / "failover_all_pairs_20261109.svg"
    output_json.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_figure(datasets, output_svg)
    print(output_json.relative_to(ROOT).as_posix())
    print(output_svg.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
