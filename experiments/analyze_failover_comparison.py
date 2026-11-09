#!/usr/bin/env python3
"""Build a descriptive comparison of the two controlled failover series.

The two source series were collected with different recovery settings, so the
generated artefacts explicitly mark the result as descriptive rather than a
causal comparison of ESP32 and ESP32-S3 hardware.
"""

from __future__ import annotations

import json
import statistics
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
FIGURES = ROOT / "experiments" / "figures"

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
        "summary": RESULTS / "failover_8266_s3_controlled_5x_20261107_summary.json",
    },
)

CONFIG_KEYS = (
    "probe_interval_ms",
    "window_ms",
    "fallback_loss_pct",
    "recovery_success_pct",
    "bad_windows_required",
    "good_windows_required",
    "recovery_probe_offset_ms",
    "recovery_probe_interval_ms",
    "recovery_probe_guard_ms",
    "espnow_stabilization_windows",
    "wifi_power_save",
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def describe(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "average": round(statistics.mean(values), 3),
        "median": statistics.median(values),
        "maximum": max(values),
        "sample_standard_deviation": round(
            statistics.stdev(values) if len(values) > 1 else 0.0, 3
        ),
    }


def collect_series(spec: dict[str, Any]) -> dict[str, Any]:
    summary = read_json(spec["summary"])
    runs = [read_json(ROOT / relative) for relative in summary["runs"]]
    fallback_ms = [run["fallback"]["reaction_from_fault_ms"] for run in runs]
    recovery_ms = [run["recovery"]["reaction_from_fault_removal_ms"] for run in runs]
    udp_time_ms = [run["udp_reserve"]["time_in_udp_ms"] for run in runs]

    return {
        "key": spec["key"],
        "label": spec["label"],
        "short_label": spec["short_label"],
        "color": spec["color"],
        "source_summary": spec["summary"].relative_to(ROOT).as_posix(),
        "configuration": summary["configuration"],
        "valid_runs": summary.get("valid_runs", summary.get("complete_transition_cycles")),
        "successful_fallbacks": summary["overall"]["successful_fallbacks"],
        "successful_recoveries": summary["overall"]["successful_recoveries"],
        "baseline_espnow_success_pct": summary["overall"]["baseline_espnow_success_pct"],
        "udp_success_pct": summary["overall"]["udp_reserve"]["success_pct"],
        "fallback_reaction_ms": fallback_ms,
        "fallback_reaction_ms_descriptive": describe(fallback_ms),
        "recovery_reaction_ms": recovery_ms,
        "recovery_reaction_ms_descriptive": describe(recovery_ms),
        "time_in_udp_ms": udp_time_ms,
        "time_in_udp_ms_descriptive": describe(udp_time_ms),
        "runs": [path for path in summary["runs"]],
    }


def configuration_differences(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    differences = []
    for key in CONFIG_KEYS:
        left_value = left["configuration"].get(key, "not_recorded")
        right_value = right["configuration"].get(key, "not_recorded")
        if left_value != right_value:
            differences.append(
                {
                    "parameter": key,
                    left["key"]: left_value,
                    right["key"]: right_value,
                }
            )
    return differences


def text(x: float, y: float, value: str, size: int = 18, *, anchor: str = "start", weight: int = 400, fill: str = "#111827") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="DejaVu Sans, Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}">{escape(value)}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, *, stroke: str = "#9CA3AF", width: float = 1.0, dash: str | None = None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'


def dot(x: float, y: float, color: str) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" fill-opacity="0.78" stroke="#FFFFFF" stroke-width="1.5"/>'


def point_panel(
    x: int,
    y: int,
    width: int,
    height: int,
    title_value: str,
    unit: str,
    datasets: list[dict[str, Any]],
    value_key: str,
    y_max: float,
    tick_step: float,
) -> list[str]:
    items = [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#F9FAFB" stroke="#E5E7EB"/>']
    items.append(text(x + 20, y + 34, title_value, 20, weight=700))
    left, right = x + 62, x + width - 20
    top, bottom = y + 58, y + height - 66

    tick = 0.0
    while tick <= y_max + 0.001:
        py = bottom - (tick / y_max) * (bottom - top)
        items.append(line(left, py, right, py, stroke="#D1D5DB", dash="4 5"))
        items.append(text(left - 10, py + 5, f"{tick:g}", 14, anchor="end", fill="#4B5563"))
        tick += tick_step
    items.append(text(left - 38, top - 8, unit, 14, anchor="middle", fill="#4B5563"))

    centres = [left + (right - left) * 0.30, left + (right - left) * 0.72]
    jitter = (-24, -12, 0, 12, 24)
    for centre, dataset in zip(centres, datasets):
        values = [value / 1000.0 for value in dataset[value_key]]
        for index, value in enumerate(values):
            py = bottom - (value / y_max) * (bottom - top)
            items.append(dot(centre + jitter[index], py, dataset["color"]))
        mean_value = statistics.mean(values)
        mean_y = bottom - (mean_value / y_max) * (bottom - top)
        items.append(line(centre - 34, mean_y, centre + 34, mean_y, stroke=dataset["color"], width=4))
        items.append(text(centre, bottom + 28, dataset["short_label"], 15, anchor="middle", weight=600))
        items.append(text(centre, bottom + 50, f"ср. {mean_value:.2f} с", 14, anchor="middle", fill=dataset["color"]))
    return items


def delivery_panel(x: int, y: int, width: int, height: int, datasets: list[dict[str, Any]]) -> list[str]:
    items = [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#F9FAFB" stroke="#E5E7EB"/>']
    items.append(text(x + 20, y + 34, "Доставка прикладных ACK", 20, weight=700))
    left, right = x + 62, x + width - 20
    top, bottom = y + 58, y + height - 66
    y_min, y_max = 85.0, 101.0
    for tick in (85, 90, 95, 100):
        py = bottom - ((tick - y_min) / (y_max - y_min)) * (bottom - top)
        items.append(line(left, py, right, py, stroke="#D1D5DB", dash="4 5"))
        items.append(text(left - 10, py + 5, str(tick), 14, anchor="end", fill="#4B5563"))
    items.append(text(left - 38, top - 8, "%", 14, anchor="middle", fill="#4B5563"))

    groups = (("ESP-NOW до отказа", "baseline_espnow_success_pct"), ("UDP в резерве", "udp_success_pct"))
    group_centres = [left + (right - left) * 0.30, left + (right - left) * 0.72]
    offsets = (-22, 22)
    for centre, (label, key) in zip(group_centres, groups):
        for offset, dataset in zip(offsets, datasets):
            value = dataset[key]
            py = bottom - ((value - y_min) / (y_max - y_min)) * (bottom - top)
            items.append(dot(centre + offset, py, dataset["color"]))
            items.append(text(centre + offset, py - 13, f"{value:.1f}", 13, anchor="middle", fill=dataset["color"], weight=600))
        items.append(text(centre, bottom + 30, label, 14, anchor="middle", weight=600))
    items.append(text(x + width / 2, bottom + 52, "Шкала 85–101 %", 13, anchor="middle", fill="#6B7280"))
    return items


def write_svg(
    datasets: list[dict[str, Any]],
    output: Path,
    *,
    title_value: str = "Описательное сравнение контролируемых переходов",
    subtitle: str = "Пять повторов в каждой серии, расстояние 1 м, точка доступа Lab-2G, канал 6",
    footer_lines: tuple[str, str] = (
        "Серии различались порогом восстановления, интервалами probe и режимом энергосбережения Wi-Fi.",
        "Поэтому график показывает наблюдавшиеся результаты алгоритма, но не доказывает преимущество одного микроконтроллера.",
    ),
) -> None:
    width, height = 1320, 760
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        text(40, 50, title_value, 30, weight=700),
        text(40, 80, subtitle, 17, fill="#4B5563"),
    ]
    for index, dataset in enumerate(datasets):
        lx = 905 + index * 190
        items.append(f'<rect x="{lx}" y="38" width="18" height="18" rx="3" fill="{dataset["color"]}"/>')
        items.append(text(lx + 27, 53, dataset["short_label"], 16, weight=600))

    items.extend(point_panel(40, 115, 395, 500, "Переход ESP-NOW → UDP", "с", datasets, "fallback_reaction_ms", 12, 2))
    items.extend(point_panel(462, 115, 395, 500, "Возврат UDP → ESP-NOW", "с", datasets, "recovery_reaction_ms", 60, 10))
    items.extend(delivery_panel(884, 115, 395, 500, datasets))
    items.append(text(40, 658, "Горизонтальная черта на точечных графиках — среднее значение.", 15, fill="#4B5563"))
    items.append(text(40, 686, footer_lines[0], 15, fill="#B45309", weight=600))
    items.append(text(40, 711, footer_lines[1], 15, fill="#B45309", weight=600))
    items.append(text(1279, 739, "Wireless Link Failover · 09.11.2026", 13, anchor="end", fill="#6B7280"))
    items.append("</svg>")
    output.write_text("\n".join(items) + "\n", encoding="utf-8")


def main() -> None:
    datasets = [collect_series(spec) for spec in SERIES]
    left, right = datasets
    differences = configuration_differences(left, right)

    comparison = {
        "schema": "wlf.failover-comparison.v1",
        "comparison_id": "failover_esp32_vs_esp32s3_descriptive_20261109",
        "date": "2026-11-09",
        "classification": "descriptive_only",
        "reason": (
            "Source series used non-identical recovery settings, and Wi-Fi power saving "
            "was explicitly disabled only in the ESP32 series."
        ),
        "common_conditions": {
            "valid_runs_per_series": 5,
            "distance_cm": 100,
            "ssid": "Lab-2G",
            "band_ghz": 2.4,
            "channel": 6,
            "fault_type": "controlled_espnow_application_ack_suppression",
        },
        "configuration_differences": differences,
        "series": datasets,
        "observed_differences": {
            "fallback_average_ms_esp32_minus_esp32s3": round(
                left["fallback_reaction_ms_descriptive"]["average"]
                - right["fallback_reaction_ms_descriptive"]["average"],
                3,
            ),
            "recovery_average_ms_esp32_minus_esp32s3": round(
                left["recovery_reaction_ms_descriptive"]["average"]
                - right["recovery_reaction_ms_descriptive"]["average"],
                3,
            ),
            "baseline_success_percentage_points_esp32_minus_esp32s3": round(
                left["baseline_espnow_success_pct"] - right["baseline_espnow_success_pct"], 3
            ),
            "udp_success_percentage_points_esp32_minus_esp32s3": round(
                left["udp_success_pct"] - right["udp_success_pct"], 3
            ),
        },
        "conclusion": (
            "Both implementations completed automatic fallback and recovery in all five runs. "
            "The ESP32 series had less variable recovery after Wi-Fi power saving was disabled, "
            "but the hardware effect cannot be isolated from the changed recovery threshold and scheduler."
        ),
        "required_standardized_follow_up": {
            "same_firmware_revision": True,
            "wifi_power_save": False,
            "probe_interval_ms": 470,
            "window_ms": 5000,
            "fallback_loss_pct": 30,
            "recovery_success_pct": 80,
            "bad_windows_required": 2,
            "good_windows_required": 3,
            "recovery_probe_interval_ms": 940,
            "recovery_probe_guard_ms": 470,
            "espnow_stabilization_windows": 3,
            "recommended_runs_per_direction_per_pair": 5,
            "randomize_direction_order": True,
        },
        "figure": "experiments/figures/failover_comparison_20261109.svg",
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    output_json = RESULTS / "failover_comparison_20261109.json"
    output_svg = FIGURES / "failover_comparison_20261109.svg"
    output_json.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_svg(datasets, output_svg)
    print(output_json.relative_to(ROOT).as_posix())
    print(output_svg.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
