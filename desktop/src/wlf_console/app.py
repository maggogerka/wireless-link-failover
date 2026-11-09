from __future__ import annotations

import json
import sys
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import serial
from serial.tools import list_ports


BAUD_RATE = 115200
POLL_INTERVAL_MS = 40
PORT_REFRESH_INTERVAL_MS = 2000
EXPECTED_SCHEMA = "wlf.telemetry.v1"
MIN_TRIAL_PREPARATION_SECONDS = 30.0


def project_root() -> Path:
    """Return the repository root for editable and source-tree execution."""
    return Path(__file__).resolve().parents[3]


def create_log_path() -> Path:
    raw_dir = project_root() / "experiments" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return raw_dir / f"serial_{timestamp}.jsonl"


@dataclass
class PortSession:
    port: str
    connection: serial.Serial
    buffer: bytearray = field(default_factory=bytearray)
    node_id: str = "—"
    platform: str = "—"
    station_mac: str = "—"
    wifi_connected: bool = False
    failover_transport: str = "unknown"

    def close(self) -> None:
        if self.connection.is_open:
            self.connection.close()


class MainWindow(tk.Tk):
    columns = ("port", "state", "node", "platform", "mac")

    def __init__(self) -> None:
        super().__init__()
        self.title("Wireless Link Failover Console")
        self.geometry("1160x900")
        self.minsize(850, 650)

        self.sessions: dict[str, PortSession] = {}
        self.available_ports: dict[str, Any] = {}
        self.log_path = create_log_path()
        self.trial_sender: str | None = None
        self.trial_sender_prepared_at: float | None = None

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        self.refresh_ports()
        self.after(POLL_INTERVAL_MS, self.poll_serial_ports)
        self.after(PORT_REFRESH_INTERVAL_MS, self.periodic_port_refresh)

    def _build_widgets(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Обновить порты", command=self.refresh_ports).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(
            toolbar, text="Подключить выбранные", command=self.connect_selected
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            toolbar, text="Отключить выбранные", command=self.disconnect_selected
        ).pack(side=tk.LEFT)

        ttk.Button(toolbar, text="SCAN", command=lambda: self.send_command("SCAN")).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(toolbar, text="PING", command=lambda: self.send_command("PING")).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(toolbar, text="INFO", command=lambda: self.send_command("INFO")).pack(
            side=tk.RIGHT
        )

        experiment_bar = ttk.LabelFrame(
            self, text="Статистическая серия ESP-NOW", padding=(8, 6)
        )
        experiment_bar.pack(fill=tk.X, padx=8, pady=(2, 4))

        self.test_count = tk.StringVar(value="1000")
        self.test_interval_ms = tk.StringVar(value="20")
        self.ack_delay_ms = tk.StringVar(value="0")
        ttk.Label(experiment_bar, text="Пакетов:").pack(side=tk.LEFT)
        ttk.Entry(
            experiment_bar, textvariable=self.test_count, width=8
        ).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(experiment_bar, text="Интервал, мс:").pack(side=tk.LEFT)
        ttk.Entry(
            experiment_bar, textvariable=self.test_interval_ms, width=7
        ).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(experiment_bar, text="ACK, мс:").pack(side=tk.LEFT)
        ttk.Entry(
            experiment_bar, textvariable=self.ack_delay_ms, width=5
        ).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Button(
            experiment_bar, text="1. Подготовить все", command=self.prepare_test
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            experiment_bar,
            text="2. TEST на выбранном",
            command=self.start_selected_test,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            experiment_bar, text="STATS всем", command=self.request_all_stats
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            experiment_bar, text="Вернуть AUTO", command=self.resume_auto_send
        ).pack(side=tk.LEFT)

        network_bar = ttk.LabelFrame(
            self, text="Wi-Fi / UDP (пароль не записывается в журнал)", padding=(8, 6)
        )
        network_bar.pack(fill=tk.X, padx=8, pady=(2, 4))
        self.wifi_ssid = tk.StringVar(value="")
        self.wifi_password = tk.StringVar(value="")
        ttk.Label(network_bar, text="SSID:").pack(side=tk.LEFT)
        ttk.Entry(network_bar, textvariable=self.wifi_ssid, width=22).pack(
            side=tk.LEFT, padx=(4, 10)
        )
        ttk.Label(network_bar, text="Пароль:").pack(side=tk.LEFT)
        ttk.Entry(
            network_bar,
            textvariable=self.wifi_password,
            width=24,
            show="•",
        ).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Button(
            network_bar, text="Подключить все", command=self.connect_wifi
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            network_bar, text="WIFI STATUS", command=lambda: self.send_to_all("WIFI STATUS")
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            network_bar,
            text="Отключить Wi-Fi",
            command=lambda: self.send_to_all("WIFI DISCONNECT"),
        ).pack(side=tk.LEFT)

        udp_bar = ttk.LabelFrame(self, text="UDP через точку доступа", padding=(8, 6))
        udp_bar.pack(fill=tk.X, padx=8, pady=(2, 4))
        ttk.Button(
            udp_bar, text="1. UDP START всем", command=self.prepare_udp_test
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            udp_bar, text="2. UDP TEST на выбранном", command=self.start_selected_udp_test
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            udp_bar, text="UDP STATUS всем", command=lambda: self.send_to_all("UDP STATUS")
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            udp_bar, text="UDP STOP всем", command=lambda: self.send_to_all("UDP STOP")
        ).pack(side=tk.LEFT)

        failover_bar = ttk.LabelFrame(
            self, text="Автомат ESP-NOW → UDP → ESP-NOW", padding=(8, 6)
        )
        failover_bar.pack(fill=tk.X, padx=8, pady=(2, 4))
        self.failover_probe_ms = tk.StringVar(value="470")
        self.failover_window_ms = tk.StringVar(value="5000")
        self.failover_loss_pct = tk.StringVar(value="30")
        self.failover_recovery_pct = tk.StringVar(value="80")
        ttk.Label(failover_bar, text="Probe, мс:").pack(side=tk.LEFT)
        ttk.Entry(
            failover_bar, textvariable=self.failover_probe_ms, width=6
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(failover_bar, text="Окно, мс:").pack(side=tk.LEFT)
        ttk.Entry(
            failover_bar, textvariable=self.failover_window_ms, width=7
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(failover_bar, text="Потери, %:").pack(side=tk.LEFT)
        ttk.Entry(
            failover_bar, textvariable=self.failover_loss_pct, width=4
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(failover_bar, text="Возврат, %:").pack(side=tk.LEFT)
        ttk.Entry(
            failover_bar, textvariable=self.failover_recovery_pct, width=4
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Button(
            failover_bar, text="Включить всем", command=self.enable_failover
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            failover_bar,
            text="STATUS",
            command=lambda: self.send_to_all("FAILOVER STATUS"),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            failover_bar,
            text="AUTO",
            command=lambda: self.send_to_all("FAILOVER AUTO"),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            failover_bar, text="FORCE UDP", command=lambda: self.force_failover("UDP")
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            failover_bar,
            text="FORCE ESP-NOW",
            command=lambda: self.force_failover("ESPNOW"),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            failover_bar,
            text="Выключить всем",
            command=lambda: self.send_to_all("FAILOVER OFF"),
        ).pack(side=tk.LEFT)

        fault_bar = ttk.LabelFrame(
            self, text="Контролируемое ухудшение ESP-NOW", padding=(8, 6)
        )
        fault_bar.pack(fill=tk.X, padx=8, pady=(2, 4))
        ttk.Label(
            fault_bar,
            text="Сначала отправитель, затем приёмник:",
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            fault_bar,
            text="1. Подготовить выбранного отправителя",
            command=self.enable_selected_failover,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            fault_bar,
            text="2. ACK ВЫКЛ. на приёмнике",
            command=lambda: self.set_selected_espnow_ack(False),
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            fault_bar,
            text="3. ACK ВКЛ. на приёмнике",
            command=lambda: self.set_selected_espnow_ack(True),
        ).pack(side=tk.LEFT)

        table_frame = ttk.Frame(self, padding=(8, 4))
        table_frame.pack(fill=tk.BOTH, expand=False)

        self.port_table = ttk.Treeview(
            table_frame,
            columns=self.columns,
            show="headings",
            selectmode="extended",
            height=6,
        )
        headings = {
            "port": "Порт",
            "state": "Состояние",
            "node": "Узел",
            "platform": "Платформа / устройство",
            "mac": "MAC",
        }
        widths = {"port": 80, "state": 110, "node": 120, "platform": 360, "mac": 170}
        for column in self.columns:
            self.port_table.heading(column, text=headings[column])
            self.port_table.column(column, width=widths[column], minwidth=70)

        table_scrollbar = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.port_table.yview
        )
        self.port_table.configure(yscrollcommand=table_scrollbar.set)
        self.port_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        table_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(
            self, text="JSON Lines и служебные сообщения", padding=(8, 6, 8, 2)
        ).pack(anchor=tk.W)

        log_frame = ttk.Frame(self, padding=(8, 0, 8, 4))
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_view = tk.Text(
            log_frame,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 9),
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#e5e7eb",
        )
        log_y_scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_view.yview
        )
        log_x_scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.HORIZONTAL, command=self.log_view.xview
        )
        self.log_view.configure(
            yscrollcommand=log_y_scrollbar.set, xscrollcommand=log_x_scrollbar.set
        )
        self.log_view.grid(row=0, column=0, sticky="nsew")
        log_y_scrollbar.grid(row=0, column=1, sticky="ns")
        log_x_scrollbar.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.status_text = tk.StringVar(value=f"Журнал: {self.log_path}")
        ttk.Label(self, textvariable=self.status_text, padding=(8, 2, 8, 8)).pack(
            fill=tk.X
        )

    def periodic_port_refresh(self) -> None:
        self.refresh_ports()
        self.after(PORT_REFRESH_INTERVAL_MS, self.periodic_port_refresh)

    def refresh_ports(self) -> None:
        ports = {item.device: item for item in list_ports.comports()}
        self.available_ports = ports
        selected = set(self.port_table.selection())
        all_names = sorted(set(ports) | set(self.sessions))

        existing = set(self.port_table.get_children())
        for stale in existing - set(all_names):
            self.port_table.delete(stale)

        for port_name in all_names:
            session = self.sessions.get(port_name)
            port_info = ports.get(port_name)
            state = "подключён" if session else "доступен"
            if port_info is None and session is None:
                state = "отключён"

            values = (
                port_name,
                state,
                session.node_id if session else "—",
                session.platform if session else self.port_description(port_info),
                session.station_mac if session else "—",
            )
            tags = ("connected",) if session else ()
            if self.port_table.exists(port_name):
                self.port_table.item(port_name, values=values, tags=tags)
            else:
                self.port_table.insert("", tk.END, iid=port_name, values=values, tags=tags)

        self.port_table.tag_configure("connected", background="#d9f7d9")
        for item_id in selected:
            if self.port_table.exists(item_id):
                self.port_table.selection_add(item_id)

    @staticmethod
    def port_description(port_info: Any) -> str:
        if port_info is None:
            return "—"
        return port_info.description or "неизвестное устройство"

    def selected_ports(self) -> set[str]:
        return set(self.port_table.selection())

    def connect_selected(self) -> None:
        selected = self.selected_ports()
        if not selected:
            messagebox.showinfo("Подключение", "Выберите хотя бы один порт")
            return

        for port_name in sorted(selected):
            if port_name in self.sessions:
                continue
            try:
                # Set control lines before opening the port. Opening a NodeMCU
                # with pyserial defaults can assert DTR/RTS long enough to keep
                # the board in reset instead of letting the firmware answer.
                connection = serial.Serial()
                connection.port = port_name
                connection.baudrate = BAUD_RATE
                connection.timeout = 0
                connection.write_timeout = 1
                connection.dsrdtr = False
                connection.rtscts = False
                connection.dtr = False
                connection.rts = False
                connection.open()
                self.sessions[port_name] = PortSession(port_name, connection)

                port_info = self.available_ports.get(port_name)
                is_cp210x = (
                    port_info is not None
                    and port_info.vid == 0x10C4
                    and port_info.pid == 0xEA60
                )
                if is_cp210x:
                    # This board's CP210x starts forwarding UART data reliably
                    # after a short DTR pulse. RTS remains inactive, so the
                    # pulse does not reset the ESP32 or select Download Mode.
                    connection.dtr = True
                    self.after(100, lambda name=port_name: self.release_dtr(name))

                self.append_service_message(port_name, "порт подключён")
                info_delay_ms = 600 if is_cp210x else 400
                self.after(
                    info_delay_ms,
                    lambda name=port_name: self.write_to_port(name, "INFO"),
                )
            except (OSError, serial.SerialException) as error:
                self.append_service_message(port_name, f"ошибка подключения: {error}")

        self.refresh_ports()

    def release_dtr(self, port_name: str) -> None:
        session = self.sessions.get(port_name)
        if session and session.connection.is_open:
            session.connection.dtr = False

    def disconnect_selected(self) -> None:
        for port_name in self.selected_ports():
            session = self.sessions.pop(port_name, None)
            if session:
                session.close()
                self.append_service_message(port_name, "порт отключён")
        self.refresh_ports()

    def command_targets(self) -> list[str]:
        selected = self.selected_ports()
        selected_connected = [name for name in selected if name in self.sessions]
        return selected_connected or sorted(self.sessions)

    def send_command(self, command: str) -> None:
        targets = self.command_targets()
        if not targets:
            messagebox.showinfo("Команда", "Нет подключённых узлов")
            return
        for port_name in targets:
            self.write_to_port(port_name, command)

    def connected_ports(self) -> list[str]:
        return sorted(self.sessions)

    def send_to_all(self, command: str) -> None:
        for port_name in self.connected_ports():
            self.write_to_port(port_name, command)

    def connect_wifi(self) -> None:
        if not self.sessions:
            messagebox.showinfo("Wi-Fi", "Нет подключённых узлов")
            return
        ssid = self.wifi_ssid.get().strip()
        password = self.wifi_password.get()
        if not ssid or len(ssid) > 32 or len(password) > 63 or "|" in ssid:
            messagebox.showerror(
                "Wi-Fi",
                "SSID обязателен, символ | в SSID запрещён; длина SSID/пароля — 32/63",
            )
            return
        command = f"WIFICONFIG {ssid}|{password}"
        for port_name in self.connected_ports():
            self.sessions[port_name].wifi_connected = False
            self.write_secret_to_port(port_name, command)
        self.wifi_password.set("")
        self.status_text.set(f"Подключение узлов к {ssid}; пароль удалён из формы")

    def prepare_test(self) -> None:
        if len(self.sessions) < 2:
            messagebox.showinfo(
                "Эксперимент", "Подключите минимум два исследуемых узла"
            )
            return
        try:
            ack_delay_ms = int(self.ack_delay_ms.get())
        except ValueError:
            messagebox.showerror("Эксперимент", "Задержка ACK должна быть числом")
            return
        if not 0 <= ack_delay_ms <= 100:
            messagebox.showerror("Эксперимент", "Задержка ACK: от 0 до 100 мс")
            return
        self.send_to_all("QUIET ON")
        self.send_to_all("AUTO OFF")
        self.send_to_all(f"ACKDELAY {ack_delay_ms}")
        self.send_to_all("RESETSTATS")
        self.status_text.set(
            f"Узлы подготовлены: ACK {ack_delay_ms} мс, QUIET ON, AUTO OFF"
        )

    def start_selected_test(self) -> None:
        selected = [name for name in self.selected_ports() if name in self.sessions]
        if len(selected) != 1:
            messagebox.showinfo(
                "Эксперимент", "Выберите ровно один подключённый узел-передатчик"
            )
            return
        try:
            count = int(self.test_count.get())
            interval_ms = int(self.test_interval_ms.get())
        except ValueError:
            messagebox.showerror("Эксперимент", "Количество и интервал должны быть числами")
            return
        if not 1 <= count <= 100000 or not 10 <= interval_ms <= 60000:
            messagebox.showerror(
                "Эксперимент",
                "Допустимо: 1–100000 пакетов и интервал 10–60000 мс",
            )
            return
        port_name = selected[0]
        self.write_to_port(port_name, f"TEST {count} {interval_ms}")
        self.status_text.set(
            f"Запущено: {port_name}, {count} пакетов, интервал {interval_ms} мс"
        )

    def prepare_udp_test(self) -> None:
        if len(self.sessions) < 2:
            messagebox.showinfo("UDP", "Подключите минимум два узла")
            return
        self.send_to_all("AUTO OFF")
        self.send_to_all("UDP START")
        self.send_to_all("UDP RESETSTATS")
        self.status_text.set("UDP запущен на всех узлах; статистика сброшена")

    def start_selected_udp_test(self) -> None:
        selected = [name for name in self.selected_ports() if name in self.sessions]
        if len(selected) != 1:
            messagebox.showinfo("UDP", "Выберите ровно один узел-передатчик")
            return
        try:
            count = int(self.test_count.get())
            interval_ms = int(self.test_interval_ms.get())
        except ValueError:
            messagebox.showerror("UDP", "Количество и интервал должны быть числами")
            return
        if not 1 <= count <= 100000 or not 10 <= interval_ms <= 60000:
            messagebox.showerror(
                "UDP", "Допустимо: 1–100000 пакетов и интервал 10–60000 мс"
            )
            return
        port_name = selected[0]
        self.write_to_port(port_name, f"UDP TEST {count} {interval_ms}")
        self.status_text.set(
            f"UDP TEST: {port_name}, {count} пакетов, интервал {interval_ms} мс"
        )

    def failover_config(self) -> tuple[int, int, int, int] | None:
        try:
            probe_ms = int(self.failover_probe_ms.get())
            window_ms = int(self.failover_window_ms.get())
            loss_pct = int(self.failover_loss_pct.get())
            recovery_pct = int(self.failover_recovery_pct.get())
        except ValueError:
            messagebox.showerror("Failover", "Все параметры должны быть числами")
            return None
        if not (
            100 <= probe_ms <= 10000
            and 1000 <= window_ms <= 60000
            and window_ms >= probe_ms * 3
            and 1 <= loss_pct <= 100
            and 1 <= recovery_pct <= 100
            and recovery_pct > 100 - loss_pct
        ):
            messagebox.showerror(
                "Failover",
                "Probe: 100–10000 мс; окно: 1000–60000 мс и минимум 3 probe; "
                "порог возврата должен быть выше границы перехода",
            )
            return None
        return probe_ms, window_ms, loss_pct, recovery_pct

    def enable_failover(self) -> None:
        if len(self.sessions) < 2:
            messagebox.showinfo("Failover", "Подключите минимум два узла")
            return
        config = self.failover_config()
        if config is None:
            return
        probe_ms, window_ms, loss_pct, recovery_pct = config
        self.send_to_all("ESPNOW ACK ON")
        self.send_to_all(
            f"FAILOVER CONFIG {probe_ms} {window_ms} {loss_pct} {recovery_pct}"
        )
        self.send_to_all("FAILOVER ON")
        self.status_text.set(
            f"Failover включён: probe {probe_ms} мс, окно {window_ms} мс, "
            f"переход при потерях {loss_pct} %, возврат при {recovery_pct} %"
        )

    def force_failover(self, transport: str) -> None:
        selected = [name for name in self.selected_ports() if name in self.sessions]
        if len(selected) != 1:
            messagebox.showinfo(
                "Failover", "Для FORCE выберите ровно один подключённый узел"
            )
            return
        port_name = selected[0]
        self.write_to_port(port_name, f"FAILOVER FORCE {transport}")
        self.status_text.set(f"{port_name}: принудительно выбран {transport}")

    def enable_selected_failover(self) -> None:
        selected = [name for name in self.selected_ports() if name in self.sessions]
        if len(selected) != 1:
            messagebox.showinfo(
                "Повторное испытание",
                "Выберите ровно одну подключённую плату-отправитель",
            )
            return
        config = self.failover_config()
        if config is None:
            return
        wifi_missing = [
            name for name, session in self.sessions.items() if not session.wifi_connected
        ]
        if wifi_missing:
            messagebox.showinfo(
                "Повторное испытание",
                "Обе платы должны подтвердить Wi-Fi. Нажмите WIFI STATUS и "
                f"дождитесь connected. Не готовы: {', '.join(sorted(wifi_missing))}",
            )
            self.send_to_all("WIFI STATUS")
            return
        sender = selected[0]
        probe_ms, window_ms, loss_pct, recovery_pct = config

        # Only one outgoing direction is evaluated in a repetition. The peer
        # remains a passive ESP-NOW/UDP responder, preventing synchronized
        # probe streams from biasing the ACK-loss windows.
        self.send_to_all("ESPNOW ACK ON")
        self.send_to_all("FAILOVER OFF")
        self.send_to_all("AUTO OFF")
        self.send_to_all("QUIET ON")
        self.send_to_all("RESETSTATS")
        self.send_to_all("UDP START")
        self.send_to_all("UDP RESETSTATS")
        self.write_to_port(
            sender,
            f"FAILOVER CONFIG {probe_ms} {window_ms} {loss_pct} {recovery_pct}",
        )
        self.write_to_port(sender, "FAILOVER ON")
        self.trial_sender = sender
        self.trial_sender_prepared_at = time.monotonic()
        self.sessions[sender].failover_transport = "esp-now"
        self.status_text.set(
            f"{sender}: подготовлен как единственный отправитель failover"
        )

    def set_selected_espnow_ack(self, enabled: bool) -> None:
        selected = [name for name in self.selected_ports() if name in self.sessions]
        if len(selected) != 1:
            messagebox.showinfo(
                "Контролируемое ухудшение",
                "Выберите ровно одну подключённую плату-приёмник",
            )
            return
        port_name = selected[0]
        if not enabled:
            if self.trial_sender is None or self.trial_sender not in self.sessions:
                messagebox.showinfo(
                    "Контролируемое ухудшение",
                    "Сначала подготовьте выбранного отправителя",
                )
                return
            if port_name == self.trial_sender:
                messagebox.showinfo(
                    "Контролируемое ухудшение",
                    "Выбрана плата-отправитель. Нужно выбрать вторую плату-приёмник",
                )
                return
            if self.trial_sender_prepared_at is None:
                messagebox.showinfo(
                    "Контролируемое ухудшение",
                    "Время подготовки отправителя не зафиксировано. Подготовьте повтор заново",
                )
                return
            elapsed = time.monotonic() - self.trial_sender_prepared_at
            if elapsed < MIN_TRIAL_PREPARATION_SECONDS:
                remaining = int(MIN_TRIAL_PREPARATION_SECONDS - elapsed + 0.999)
                messagebox.showinfo(
                    "Контролируемое ухудшение",
                    f"До включения отказа подождите ещё {remaining} с. "
                    "Методика требует 30 с после подготовки отправителя",
                )
                return
            sender_session = self.sessions[self.trial_sender]
            if sender_session.failover_transport != "esp-now":
                messagebox.showinfo(
                    "Контролируемое ухудшение",
                    "Отправитель уже не находится на ESP-NOW. Подготовьте повтор заново",
                )
                return
        command = "ESPNOW ACK ON" if enabled else "ESPNOW ACK OFF"
        self.write_to_port(port_name, command)
        state = "включены" if enabled else "отключены"
        self.status_text.set(f"{port_name}: ответы ESP-NOW ACK {state}")

    def request_all_stats(self) -> None:
        if not self.sessions:
            messagebox.showinfo("Эксперимент", "Нет подключённых узлов")
            return
        self.send_to_all("STATS")

    def resume_auto_send(self) -> None:
        if not self.sessions:
            return
        self.send_to_all("QUIET OFF")
        self.send_to_all("AUTO ON")
        self.status_text.set("Обычный автоматический режим восстановлен")

    def write_to_port(self, port_name: str, command: str) -> None:
        session = self.sessions.get(port_name)
        if not session:
            return
        try:
            session.connection.write((command + "\n").encode("utf-8"))
            self.append_service_message(port_name, f"> {command}")
        except (OSError, serial.SerialException) as error:
            self.handle_disconnected_port(port_name, error)

    def write_secret_to_port(self, port_name: str, command: str) -> None:
        session = self.sessions.get(port_name)
        if not session:
            return
        try:
            session.connection.write((command + "\n").encode("utf-8"))
            self.append_service_message(port_name, "> WIFICONFIG <redacted>")
        except (OSError, serial.SerialException) as error:
            self.handle_disconnected_port(port_name, error)

    def poll_serial_ports(self) -> None:
        for port_name, session in list(self.sessions.items()):
            try:
                waiting = session.connection.in_waiting
                if waiting:
                    session.buffer.extend(session.connection.read(waiting))
                    self.consume_lines(session)
            except (OSError, serial.SerialException) as error:
                self.handle_disconnected_port(port_name, error)
        self.after(POLL_INTERVAL_MS, self.poll_serial_ports)

    def consume_lines(self, session: PortSession) -> None:
        while b"\n" in session.buffer:
            raw_line, _, remainder = session.buffer.partition(b"\n")
            session.buffer = bytearray(remainder)
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                self.handle_line(session, line)

    def handle_line(self, session: PortSession, line: str) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            record: dict[str, Any] = {
                "host_time": timestamp,
                "serial_port": session.port,
                **payload,
            }
            if payload.get("schema") == EXPECTED_SCHEMA:
                self.update_session_identity(session, payload)
                event_type = payload.get("type")
                if event_type == "test_progress":
                    self.status_text.set(
                        f"{session.port}: {payload.get('accepted', 0)} / "
                        f"{payload.get('requested', 0)} пакетов"
                    )
                elif event_type == "test_complete":
                    self.status_text.set(
                        f"{session.port}: серия завершена; ACK "
                        f"{payload.get('ack_received', 0)} / "
                        f"{payload.get('accepted', 0)}"
                    )
                elif event_type == "wifi_connected":
                    session.wifi_connected = True
                    self.status_text.set(
                        f"{session.port}: Wi-Fi {payload.get('ssid', '')}, "
                        f"IP {payload.get('local_ip', '')}, канал {payload.get('channel', '')}"
                    )
                elif event_type == "wifi_failed":
                    session.wifi_connected = False
                    self.status_text.set(
                        f"{session.port}: ошибка Wi-Fi — {payload.get('reason', '')}"
                    )
                elif event_type in {"wifi_status", "wifi_disconnected"}:
                    session.wifi_connected = bool(payload.get("connected"))
                elif event_type == "udp_test_progress":
                    self.status_text.set(
                        f"UDP {session.port}: {payload.get('accepted', 0)} / "
                        f"{payload.get('requested', 0)} пакетов"
                    )
                elif event_type == "udp_test_complete":
                    self.status_text.set(
                        f"UDP {session.port}: ACK {payload.get('ack_received', 0)} / "
                        f"{payload.get('accepted', 0)}"
                    )
                elif event_type == "failover_transition":
                    session.failover_transport = str(payload.get("to", "unknown"))
                    self.status_text.set(
                        f"{session.port}: {payload.get('from', '')} → "
                        f"{payload.get('to', '')}; {payload.get('reason', '')}; "
                        f"наблюдение {payload.get('evidence_duration_ms', 0)} мс"
                    )
                elif event_type == "failover_window":
                    self.status_text.set(
                        f"{session.port}: {payload.get('active_transport', '')}; "
                        f"ESP-NOW {payload.get('espnow_success_pct', 0)} %, "
                        f"UDP {payload.get('udp_success_pct', 0)} %"
                    )
                elif event_type == "failover_status":
                    session.failover_transport = str(
                        payload.get("active_transport", "unknown")
                    )
                    self.status_text.set(
                        f"{session.port}: failover "
                        f"{'ON' if payload.get('enabled') else 'OFF'}, "
                        f"транспорт {payload.get('active_transport', '')}"
                    )
                elif event_type == "fault_control":
                    self.status_text.set(
                        f"{session.port}: подавление ESP-NOW ACK "
                        f"{'включено' if payload.get('active') else 'выключено'}"
                    )
        except (json.JSONDecodeError, ValueError):
            record = {
                "host_time": timestamp,
                "serial_port": session.port,
                "type": "serial_text",
                "text": line,
            }

        self.append_log_line(f"[{session.port}] {line}")
        with self.log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            log_file.write("\n")

    def update_session_identity(self, session: PortSession, payload: dict[str, Any]) -> None:
        if payload.get("node_id"):
            session.node_id = str(payload["node_id"])
        if payload.get("platform"):
            session.platform = str(payload["platform"])
        if payload.get("station_mac"):
            session.station_mac = str(payload["station_mac"])
        self.refresh_ports()

    def append_service_message(self, port_name: str, message: str) -> None:
        self.append_log_line(f"[{port_name}] {message}")

    def append_log_line(self, line: str) -> None:
        self.log_view.configure(state=tk.NORMAL)
        self.log_view.insert(tk.END, line + "\n")
        self.log_view.see(tk.END)
        self.log_view.configure(state=tk.DISABLED)

    def handle_disconnected_port(self, port_name: str, error: Exception) -> None:
        session = self.sessions.pop(port_name, None)
        if session:
            session.close()
        self.append_service_message(port_name, f"соединение потеряно: {error}")
        self.refresh_ports()

    def close_application(self) -> None:
        for session in self.sessions.values():
            session.close()
        self.sessions.clear()
        self.destroy()


def main() -> int:
    try:
        window = MainWindow()
        window.mainloop()
        return 0
    except tk.TclError as error:
        print(f"Unable to start GUI: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
