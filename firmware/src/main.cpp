#include <Arduino.h>

#include "espnow_transport.h"
#include "failover_manager.h"
#include "network_manager.h"
#include "udp_transport.h"

#if defined(ESP8266)
#include <ESP8266WiFi.h>
extern "C" {
#include <user_interface.h>
}
#elif defined(ESP32)
#include <WiFi.h>
#include <esp_arduino_version.h>
#include <esp_system.h>
#include <esp_wifi.h>
#else
#error "Unsupported target"
#endif

namespace {

constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kHeartbeatPeriodMs = 10000;
constexpr const char* kSchema = "wlf.telemetry.v1";

String commandBuffer;
uint32_t lastHeartbeatMs = 0;

const char* nodeId() {
#if defined(ESP8266)
  return "node8266";
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return "node32s3";
#else
  return "node32";
#endif
}

const char* platformName() {
#if defined(ESP8266)
  return "ESP8266";
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return "ESP32-S3";
#else
  return "ESP32";
#endif
}

String jsonEscape(const String& source) {
  String escaped;
  escaped.reserve(source.length() + 8);

  for (size_t i = 0; i < source.length(); ++i) {
    const char ch = source.charAt(i);
    switch (ch) {
      case '\\':
        escaped += F("\\\\");
        break;
      case '"':
        escaped += F("\\\"");
        break;
      case '\n':
        escaped += F("\\n");
        break;
      case '\r':
        escaped += F("\\r");
        break;
      case '\t':
        escaped += F("\\t");
        break;
      default:
        if (static_cast<uint8_t>(ch) >= 0x20) {
          escaped += ch;
        }
        break;
    }
  }

  return escaped;
}

uint8_t currentWiFiChannel() {
#if defined(ESP8266)
  return wifi_get_channel();
#else
  uint8_t primary = 0;
  wifi_second_chan_t secondary = WIFI_SECOND_CHAN_NONE;
  if (esp_wifi_get_channel(&primary, &secondary) != ESP_OK) {
    return 0;
  }
  return primary;
#endif
}

uint32_t flashSizeBytes() {
  return ESP.getFlashChipSize();
}

uint32_t realFlashSizeBytes() {
#if defined(ESP8266)
  return ESP.getFlashChipRealSize();
#else
  return ESP.getFlashChipSize();
#endif
}

uint32_t psramSizeBytes() {
#if defined(ESP8266)
  return 0;
#else
  return ESP.getPsramSize();
#endif
}

String chipModel() {
#if defined(ESP8266)
  return F("ESP8266EX");
#else
  return String(ESP.getChipModel());
#endif
}

uint32_t chipRevision() {
#if defined(ESP8266)
  return 0;
#else
  return ESP.getChipRevision();
#endif
}

uint32_t chipCores() {
#if defined(ESP8266)
  return 1;
#else
  return ESP.getChipCores();
#endif
}

String chipIdentifier() {
#if defined(ESP8266)
  char value[9] = {};
  snprintf(value, sizeof(value), "%08X", ESP.getChipId());
  return String(value);
#else
  const uint64_t efuseMac = ESP.getEfuseMac();
  char value[17] = {};
  snprintf(value, sizeof(value), "%08lX%08lX",
           static_cast<unsigned long>(efuseMac >> 32),
           static_cast<unsigned long>(efuseMac & 0xFFFFFFFFULL));
  return String(value);
#endif
}

String resetReason() {
#if defined(ESP8266)
  return ESP.getResetReason();
#else
  return String(static_cast<int>(esp_reset_reason()));
#endif
}

const char* arduinoCoreVersion() {
#if defined(ESP_ARDUINO_VERSION_STR)
  return ESP_ARDUINO_VERSION_STR;
#else
  return "not-reported";
#endif
}

void emitError(const String& code, const String& message) {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"error\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"code\":\""));
  Serial.print(jsonEscape(code));
  Serial.print(F("\",\"message\":\""));
  Serial.print(jsonEscape(message));
  Serial.println(F("\"}"));
}

void emitDeviceInfo() {
  const String mac = WiFi.macAddress();
  const String model = chipModel();
  const String chipId = chipIdentifier();
  const String reason = resetReason();

  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"device_info\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"platform\":\""));
  Serial.print(platformName());
  Serial.print(F("\",\"chip_model\":\""));
  Serial.print(jsonEscape(model));
  Serial.print(F("\",\"chip_revision\":"));
  Serial.print(chipRevision());
  Serial.print(F(",\"chip_cores\":"));
  Serial.print(chipCores());
  Serial.print(F(",\"chip_id\":\""));
  Serial.print(chipId);
  Serial.print(F("\",\"station_mac\":\""));
  Serial.print(mac);
  Serial.print(F("\",\"flash_configured_bytes\":"));
  Serial.print(flashSizeBytes());
  Serial.print(F(",\"flash_detected_bytes\":"));
  Serial.print(realFlashSizeBytes());
  Serial.print(F(",\"psram_bytes\":"));
  Serial.print(psramSizeBytes());
  Serial.print(F(",\"free_heap_bytes\":"));
  Serial.print(ESP.getFreeHeap());
  Serial.print(F(",\"cpu_mhz\":"));
  Serial.print(ESP.getCpuFreqMHz());
  Serial.print(F(",\"flash_hz\":"));
  Serial.print(ESP.getFlashChipSpeed());
  Serial.print(F(",\"wifi_channel\":"));
  Serial.print(currentWiFiChannel());
  Serial.print(F(",\"sdk_version\":\""));
  Serial.print(jsonEscape(String(ESP.getSdkVersion())));
  Serial.print(F("\",\"arduino_core\":\""));
  Serial.print(arduinoCoreVersion());
  Serial.print(F("\",\"reset_reason\":\""));
  Serial.print(jsonEscape(reason));
  Serial.print(F("\",\"uptime_ms\":"));
  Serial.print(millis());
  Serial.println(F("}"));
}

void emitHeartbeat() {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"heartbeat\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"uptime_ms\":"));
  Serial.print(millis());
  Serial.print(F(",\"free_heap_bytes\":"));
  Serial.print(ESP.getFreeHeap());
  Serial.print(F(",\"wifi_channel\":"));
  Serial.print(currentWiFiChannel());
  Serial.println(F("}"));
}

void scanNetworks() {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"scan_started\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\"}"));

  const int count = WiFi.scanNetworks(false, true);
  if (count < 0) {
    emitError(F("scan_failed"), String(count));
    return;
  }

  for (int i = 0; i < count; ++i) {
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"network\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.print(F("\",\"ssid\":\""));
    Serial.print(jsonEscape(WiFi.SSID(i)));
    Serial.print(F("\",\"rssi_dbm\":"));
    Serial.print(WiFi.RSSI(i));
    Serial.print(F(",\"channel\":"));
    Serial.print(WiFi.channel(i));
    Serial.print(F(",\"encryption\":"));
    Serial.print(static_cast<int>(WiFi.encryptionType(i)));
    Serial.println(F("}"));
  }

  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"scan_complete\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"network_count\":"));
  Serial.print(count);
  Serial.println(F("}"));

  WiFi.scanDelete();
  wlf_radio::restoreChannel();
}

void emitHelp() {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"help\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\",\"commands\":[\"INFO\",\"SCAN\",\"PING\",\"RADIO\",\"STATS\",\"SEND\",\"AUTO ON|OFF\",\"QUIET ON|OFF\",\"ACKDELAY <0..100 ms>\",\"ESPNOW ACK ON|OFF\",\"RESETSTATS\",\"TEST <count> <interval_ms>\",\"WIFICONFIG <ssid>|<password>\",\"WIFI STATUS\",\"WIFI DISCONNECT\",\"UDP START|STOP|SEND|STATUS|RESETSTATS\",\"UDP TEST <count> <interval_ms>\",\"FAILOVER ON|OFF|STATUS|AUTO\",\"FAILOVER FORCE ESPNOW|UDP\",\"FAILOVER CONFIG <probe_ms> <window_ms> <fallback_loss_pct> <recovery_success_pct>\",\"HELP\"]}"));
}

void handleCommand(String command) {
  command.trim();
  if (command.isEmpty()) {
    return;
  }

  String normalized = command;
  normalized.toUpperCase();
  if (normalized.startsWith(F("WIFICONFIG "))) {
    const String payload = command.substring(11);
    const int separator = payload.indexOf('|');
    if (separator <= 0 ||
        !wlf_network::connect(payload.substring(0, separator),
                              payload.substring(separator + 1))) {
      emitError(F("invalid_wifi_config"),
                F("SSID is required; max SSID/password length is 32/63"));
    }
    return;
  }
  command = normalized;

  if (command == F("INFO")) {
    emitDeviceInfo();
  } else if (command == F("SCAN")) {
    scanNetworks();
  } else if (command == F("PING")) {
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"pong\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.println(F("\"}"));
  } else if (command == F("RADIO") || command == F("STATS")) {
    wlf_radio::emitStatus();
  } else if (command == F("AUTO ON")) {
    wlf_radio::setAutoSend(true);
  } else if (command == F("AUTO OFF")) {
    wlf_radio::setAutoSend(false);
  } else if (command == F("QUIET ON")) {
    wlf_radio::setQuiet(true);
  } else if (command == F("QUIET OFF")) {
    wlf_radio::setQuiet(false);
  } else if (command == F("ESPNOW ACK ON")) {
    wlf_radio::setAckResponsesEnabled(true);
  } else if (command == F("ESPNOW ACK OFF")) {
    wlf_radio::setAckResponsesEnabled(false);
  } else if (command == F("WIFI STATUS")) {
    wlf_network::emitStatus();
  } else if (command == F("WIFI DISCONNECT")) {
    wlf_network::disconnect();
  } else if (command == F("FAILOVER ON")) {
    if (!wlf_failover::enable()) {
      emitError(F("failover_enable_failed"),
                F("Connect Wi-Fi and verify ESP-NOW before FAILOVER ON"));
    }
  } else if (command == F("FAILOVER OFF")) {
    wlf_failover::disable();
  } else if (command == F("FAILOVER STATUS")) {
    wlf_failover::emitStatus();
  } else if (command == F("FAILOVER AUTO")) {
    if (!wlf_failover::isEnabled()) {
      emitError(F("failover_not_enabled"), F("Use FAILOVER ON first"));
    } else {
      wlf_failover::useAutomaticSelection();
    }
  } else if (command == F("FAILOVER FORCE ESPNOW")) {
    if (!wlf_failover::force(wlf_failover::Transport::espnow)) {
      emitError(F("failover_force_failed"), F("Use FAILOVER ON first"));
    }
  } else if (command == F("FAILOVER FORCE UDP")) {
    if (!wlf_failover::force(wlf_failover::Transport::udp)) {
      emitError(F("failover_force_failed"),
                F("FAILOVER must be enabled with Wi-Fi and UDP active"));
    }
  } else if (command.startsWith(F("FAILOVER CONFIG "))) {
    unsigned long probeMs = 0;
    unsigned long windowMs = 0;
    unsigned long fallbackLossPct = 0;
    unsigned long recoverySuccessPct = 0;
    if (sscanf(command.c_str(), "FAILOVER CONFIG %lu %lu %lu %lu", &probeMs,
               &windowMs, &fallbackLossPct, &recoverySuccessPct) != 4 ||
        fallbackLossPct > 100 || recoverySuccessPct > 100 ||
        !wlf_failover::configure(
            static_cast<uint32_t>(probeMs), static_cast<uint32_t>(windowMs),
            static_cast<uint8_t>(fallbackLossPct),
            static_cast<uint8_t>(recoverySuccessPct))) {
      emitError(F("invalid_failover_config"),
                F("Use probe 100..10000 ms, window 1000..60000 ms, "
                  "window >= 3 probes, and recovery above fallback boundary"));
    }
  } else if (command == F("UDP START")) {
    if (!wlf_udp::begin()) {
      emitError(F("udp_start_failed"), F("Connect Wi-Fi before UDP START"));
    }
  } else if (command == F("UDP STOP")) {
    wlf_udp::stop();
  } else if (command == F("UDP SEND")) {
    if (!wlf_udp::sendProbe()) {
      emitError(F("udp_send_failed"), F("UDP is not active"));
    }
  } else if (command == F("UDP STATUS")) {
    wlf_udp::emitStatus();
  } else if (command == F("UDP RESETSTATS")) {
    wlf_udp::resetStats();
  } else if (command.startsWith(F("UDP TEST "))) {
    unsigned long packetCount = 0;
    unsigned long intervalMs = 0;
    if (wlf_failover::isEnabled() ||
        sscanf(command.c_str(), "UDP TEST %lu %lu", &packetCount,
               &intervalMs) != 2 ||
        !wlf_udp::startTest(static_cast<uint32_t>(packetCount),
                            static_cast<uint32_t>(intervalMs))) {
      emitError(F("invalid_udp_test"),
                F("Use UDP TEST <1..100000> <10..60000 ms> while active"));
    }
  } else if (command.startsWith(F("ACKDELAY "))) {
    unsigned long delayMs = 0;
    if (sscanf(command.c_str(), "ACKDELAY %lu", &delayMs) != 1 ||
        delayMs > 100) {
      emitError(F("invalid_ack_delay"), F("Use ACKDELAY <0..100 ms>"));
    } else {
      wlf_radio::setAckDelay(static_cast<uint32_t>(delayMs));
    }
  } else if (command == F("RESETSTATS")) {
    wlf_radio::resetStats();
  } else if (command.startsWith(F("TEST "))) {
    unsigned long packetCount = 0;
    unsigned long intervalMs = 0;
    if (wlf_failover::isEnabled() ||
        sscanf(command.c_str(), "TEST %lu %lu", &packetCount, &intervalMs) !=
            2 ||
        !wlf_radio::startTest(static_cast<uint32_t>(packetCount),
                              static_cast<uint32_t>(intervalMs))) {
      emitError(F("invalid_test"),
                F("Use TEST <1..100000> <10..60000 ms> while idle"));
    }
  } else if (command == F("SEND")) {
    if (!wlf_radio::sendProbe()) {
      emitError(F("espnow_send_failed"), F("ESP-NOW did not accept the packet"));
    }
  } else if (command == F("HELP")) {
    emitHelp();
  } else {
    emitError(F("unknown_command"), command);
  }
}

void pollSerial() {
  while (Serial.available() > 0) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n' || ch == '\r') {
      if (!commandBuffer.isEmpty()) {
        handleCommand(commandBuffer);
        commandBuffer = "";
      }
      continue;
    }

    if (commandBuffer.length() < 127) {
      commandBuffer += ch;
    } else {
      commandBuffer = "";
      emitError(F("command_too_long"), F("Maximum command length is 127 bytes"));
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(kSerialBaud);
  delay(1000);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  // This experiment measures transport availability, not energy saving.
  // Disable modem sleep before ESP-NOW is initialized so both transmitters
  // can receive direct frames continuously while connected to an AP.
  WiFi.setSleep(false);
  delay(100);

  const bool radioReady = wlf_radio::begin();

  Serial.println();
  Serial.println(F("Wireless Link Failover - hardware diagnostic"));
  emitDeviceInfo();
  wlf_radio::emitStatus();
  wlf_network::emitStatus();
  wlf_failover::emitStatus();
  if (!radioReady) {
    emitError(F("espnow_init_failed"), F("ESP-NOW initialization failed"));
  }
  emitHelp();
  lastHeartbeatMs = millis();
}

void loop() {
  pollSerial();
  wlf_network::poll();
  wlf_radio::poll();
  wlf_udp::poll();
  wlf_failover::poll();

  const uint32_t now = millis();
  if (now - lastHeartbeatMs >= kHeartbeatPeriodMs) {
    lastHeartbeatMs = now;
    emitHeartbeat();
  }

  delay(1);
}

