#include "network_manager.h"

#include "espnow_transport.h"

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#elif defined(ESP32)
#include <WiFi.h>
#else
#error "Unsupported target"
#endif

namespace {

constexpr char kSchema[] = "wlf.telemetry.v1";
constexpr uint32_t kConnectTimeoutMs = 20000;

enum class NetworkState : uint8_t { idle, connecting, connected, failed };

NetworkState state = NetworkState::idle;
String configuredSsid;
uint32_t connectionStartedAtMs = 0;

const char* nodeId() {
#if defined(ESP8266)
  return "node8266";
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return "node32s3";
#else
  return "node32";
#endif
}

const char* stateName() {
  switch (state) {
    case NetworkState::connecting:
      return "connecting";
    case NetworkState::connected:
      return "connected";
    case NetworkState::failed:
      return "failed";
    default:
      return "idle";
  }
}

String jsonEscape(const String& source) {
  String escaped;
  escaped.reserve(source.length() + 8);
  for (size_t index = 0; index < source.length(); ++index) {
    const char ch = source.charAt(index);
    if (ch == '\\' || ch == '"') {
      escaped += '\\';
      escaped += ch;
    } else if (ch == '\n') {
      escaped += F("\\n");
    } else if (ch == '\r') {
      escaped += F("\\r");
    } else if (static_cast<uint8_t>(ch) >= 0x20) {
      escaped += ch;
    }
  }
  return escaped;
}

void emitEvent(const char* type, const char* reason = nullptr) {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\""));
  Serial.print(type);
  Serial.print(F("\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"ssid\":\""));
  Serial.print(jsonEscape(configuredSsid));
  Serial.print(F("\",\"state\":\""));
  Serial.print(stateName());
  Serial.print(F("\",\"connected\":"));
  Serial.print(WiFi.status() == WL_CONNECTED ? F("true") : F("false"));
  Serial.print(F(",\"wifi_power_save\":"));
  Serial.print(WiFi.getSleep() ? F("true") : F("false"));
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F(",\"channel\":"));
    Serial.print(WiFi.channel());
    Serial.print(F(",\"rssi_dbm\":"));
    Serial.print(WiFi.RSSI());
    Serial.print(F(",\"local_ip\":\""));
    Serial.print(WiFi.localIP().toString());
    Serial.print(F("\",\"gateway_ip\":\""));
    Serial.print(WiFi.gatewayIP().toString());
    Serial.print(F("\",\"subnet_mask\":\""));
    Serial.print(WiFi.subnetMask().toString());
    Serial.print(F("\""));
  }
  if (reason != nullptr) {
    Serial.print(F(",\"reason\":\""));
    Serial.print(reason);
    Serial.print(F("\""));
  }
  Serial.println(F("}"));
}

}  // namespace

namespace wlf_network {

bool connect(const String& ssid, const String& password) {
  if (ssid.isEmpty() || ssid.length() > 32 || password.length() > 63) {
    return false;
  }
  configuredSsid = ssid;
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  // Failover recovery depends on receiving unscheduled ESP-NOW frames while
  // the station is associated with an access point. Keep the shared radio
  // awake so DTIM/modem-sleep timing cannot hide recovery probes or ACKs.
  WiFi.setSleep(false);
  WiFi.disconnect();
  WiFi.begin(ssid.c_str(), password.c_str());
  state = NetworkState::connecting;
  connectionStartedAtMs = millis();
  emitEvent("wifi_connecting");
  return true;
}

void disconnect() {
  WiFi.disconnect();
  state = NetworkState::idle;
  emitEvent("wifi_disconnected", "command");
}

bool isConnected() {
  return state == NetworkState::connected && WiFi.status() == WL_CONNECTED;
}

void emitStatus() { emitEvent("wifi_status"); }

void poll() {
  const wl_status_t wifiStatus = WiFi.status();
  if (state == NetworkState::connecting) {
    if (wifiStatus == WL_CONNECTED) {
      const uint8_t channel = WiFi.channel();
      if (!wlf_radio::setChannel(channel)) {
        state = NetworkState::failed;
        emitEvent("wifi_failed", "espnow_channel_sync_failed");
        return;
      }
      state = NetworkState::connected;
      emitEvent("wifi_connected");
      return;
    }
    if (millis() - connectionStartedAtMs >= kConnectTimeoutMs) {
      state = NetworkState::failed;
      WiFi.disconnect();
      emitEvent("wifi_failed", "timeout");
    }
    return;
  }

  if (state == NetworkState::connected && wifiStatus != WL_CONNECTED) {
    state = NetworkState::connecting;
    connectionStartedAtMs = millis();
    WiFi.reconnect();
    emitEvent("wifi_reconnecting", "link_lost");
  }
}

}  // namespace wlf_network
