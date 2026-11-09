# Оборудование

## Исследуемые узлы

| Узел | Плата и модуль | Среда PlatformIO | Состояние |
|---|---|---|---|
| `node8266` | NodeMCU 1.0, ESP-12E / ESP8266MOD | `node8266`, `nodemcuv2` | подтверждено на устройстве |
| `node32` | 38-pin ESP32 DevKit, модуль ESP-32 | `node32`, `esp32dev` | подтверждено на устройстве |
| `node32s3` | ESP32-S3 DevKitC-1-совместимая, N16R8 | `node32s3`, `esp32-s3-devkitc-1` | подтверждено на устройстве |

## Компьютер и инструменты

- операционная система: Windows;
- VS Code и PlatformIO;
- PlatformIO Core 6.1.19;
- Espressif 8266 Platform 4.2.1, Arduino Core 3.1.2;
- Espressif 32 Platform 8.0.0, Arduino Core 3.3.12, ESP-IDF 5.5.5;
- Python 3.11.15;
- Git;
- два USB-A–USB-C кабеля с линиями данных.

## Маршрутизатор

- Huawei WiFi AX1, модель WS5203;
- сеть 2,4 ГГц;
- точный канал и параметры сети будут записаны после команды `SCAN`.

## Последовательные порты на первом осмотре

| Порт | USB-UART | Состояние Windows |
|---|---|---|
| `COM3` | Silicon Labs CP210x, VID `10C4`, PID `EA60` | ESP32, работает; требуется ручной вход в Download Mode |
| `COM6` | WCH CH340, VID `1A86`, PID `7523` | `node8266`, работает |
| `COM7` | ESP32-S3 USB Serial/JTAG, VID `303A`, PID `1001` | `node32s3`, native USB работает |

## Подтверждённые характеристики ESP8266

| Параметр | Значение |
|---|---|
| Микроконтроллер | ESP8266EX, 1 ядро, 80 МГц |
| Chip ID | `006C868D` |
| Station MAC | `24:4C:AB:6C:86:8D` |
| Flash | 4 194 304 байт, 40 МГц |
| Свободная RAM после запуска | 51 648 байт |
| SDK | `2.2.2-dev(38a443e)` |
| Канал без подключения к точке доступа | 1 |

Исходная запись сохранена в
`experiments/metadata/hardware_inventory.jsonl`.

### Особенность загрузки ESP32

Автоматическая последовательность DTR/RTS оставляет плату в режиме `0x13`,
поэтому в профиле `node32` задано `board_upload.before_reset = no-reset`.
Перед записью пользователь вручную включает ROM Download Mode кнопками
`BOOT` и `RST`.

## Подтверждённые характеристики ESP32

| Параметр | Значение |
|---|---|
| Микроконтроллер | ESP32-D0WD-V3, revision 3.1, 2 ядра, 240 МГц |
| Chip ID / eFuse MAC | `000024CBA2077000` |
| Station MAC | `00:70:07:A2:CB:24` |
| Flash | 4 194 304 байт, 40 МГц |
| PSRAM | отсутствует |
| Свободная RAM после запуска | 235 916 байт |
| SDK / ESP-IDF | `v5.5.5` |
| Arduino Core | `3.3.12` |
| Канал без подключения к точке доступа | 1 |

Исходная запись добавлена в
`experiments/metadata/hardware_inventory.jsonl`.

### Особенность загрузки ESP32-S3

После записи через native USB программный reset может оставить S3 в ROM
Download Mode. Для запуска приложения нужно отпустить `BOOT` и коротко нажать
`RST`. Эквивалентная последовательность по COM7: DTR=false, импульс RTS=true,
затем RTS=false. В профиль сборки добавлен `ARDUINO_USB_CDC_ON_BOOT=1`, поэтому
после запуска тот же native USB остаётся последовательным портом диагностики.

Перед первой записью прочитано состояние eFuse: `SECURE_BOOT_EN = False`,
`SPI_BOOT_CRYPT_CNT = Disable`, `DIS_DOWNLOAD_MODE = False`, блокировки USB и
JTAG не установлены. Производственные ключевые блоки пусты. Никакие eFuse при
диагностике и прошивке не изменялись.

## Подтверждённые характеристики ESP32-S3

| Параметр | Значение |
|---|---|
| Микроконтроллер | ESP32-S3 QFN56, revision 0.2, 2 ядра, 240 МГц |
| Chip ID / eFuse MAC | `000094E6D290A994` |
| Station MAC | `94:A9:90:D2:E6:94` |
| Flash | 16 777 216 байт, 80 МГц |
| PSRAM | 8 388 608 байт, Octal PSRAM |
| Свободная RAM после запуска | 271 212 байт |
| SDK / ESP-IDF | `v5.5.5` |
| Arduino Core | `3.3.12` |
| Канал без подключения к точке доступа | 1 |

Исходная запись добавлена в
`experiments/metadata/hardware_inventory.jsonl`.

