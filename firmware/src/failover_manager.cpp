#include "failover_manager.h"

#include "espnow_transport.h"
#include "network_manager.h"
#include "udp_transport.h"

namespace {

constexpr char kSchema[] = "wlf.telemetry.v1";
constexpr uint8_t kBadWindowsRequired = 2;
constexpr uint8_t kGoodWindowsRequired = 3;
constexpr uint8_t kEspnowStabilizationWindows = 3;
constexpr uint32_t kUdpRestartIntervalMs = 2000;

struct Configuration {
  uint32_t probeIntervalMs = 470;
  uint32_t windowMs = 5000;
  uint8_t fallbackLossPct = 30;
  uint8_t recoverySuccessPct = 80;
};

struct WindowMetrics {
  uint32_t probes;
  uint32_t acks;
  uint8_t successPct;
};

Configuration config;
bool enabled = false;
bool automaticSelection = true;
wlf_failover::Transport activeTransport = wlf_failover::Transport::espnow;
uint32_t lastActiveProbeMs = 0;
uint32_t lastRecoveryProbeMs = 0;
uint32_t lastWindowMs = 0;
uint32_t lastUdpRestartAttemptMs = 0;
uint32_t degradationStartedMs = 0;
uint32_t lastSwitchMs = 0;
uint32_t switchCount = 0;
uint32_t espProbeBaseline = 0;
uint32_t espAckBaseline = 0;
uint32_t udpProbeBaseline = 0;
uint32_t udpAckBaseline = 0;
uint32_t espSendRejects = 0;
uint32_t udpSendRejects = 0;
uint8_t consecutiveBadWindows = 0;
uint8_t consecutiveGoodWindows = 0;
uint8_t espnowStabilizationWindowsRemaining = 0;
WindowMetrics lastEspWindow = {};
WindowMetrics lastUdpWindow = {};

const char* nodeId() {
#if defined(ESP8266)
  return "node8266";
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return "node32s3";
#else
  return "node32";
#endif
}

const char* transportName(wlf_failover::Transport transport) {
  return transport == wlf_failover::Transport::udp ? "udp" : "esp-now";
}

uint32_t recoveryProbeIntervalMs() {
  return config.probeIntervalMs * 2UL;
}

uint32_t recoveryProbeOffsetMs() {
  return config.probeIntervalMs / 2UL;
}

uint32_t recoveryProbeGuardMs() {
  return config.probeIntervalMs;
}

WindowMetrics windowMetrics(uint32_t probeNow, uint32_t ackNow,
                            uint32_t& probeBaseline,
                            uint32_t& ackBaseline) {
  WindowMetrics result = {};
  result.probes = probeNow - probeBaseline;
  const uint32_t rawAcks = ackNow - ackBaseline;
  result.acks = rawAcks > result.probes ? result.probes : rawAcks;
  result.successPct = result.probes > 0
                          ? static_cast<uint8_t>((result.acks * 100UL) /
                                                 result.probes)
                          : 0;
  probeBaseline = probeNow;
  ackBaseline = ackNow;
  return result;
}

void captureBaselines() {
  const wlf_radio::Metrics radio = wlf_radio::metrics();
  const wlf_udp::Metrics udp = wlf_udp::metrics();
  espProbeBaseline = radio.probeTx;
  espAckBaseline = radio.matchedAckRx;
  udpProbeBaseline = udp.probeTx;
  udpAckBaseline = udp.matchedAckRx;
}

void emitTransition(wlf_failover::Transport previous,
                    wlf_failover::Transport next, const char* reason,
                    uint32_t evidenceDurationMs) {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"failover_transition\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"from\":\""));
  Serial.print(transportName(previous));
  Serial.print(F("\",\"to\":\""));
  Serial.print(transportName(next));
  Serial.print(F("\",\"reason\":\""));
  Serial.print(reason);
  Serial.print(F("\",\"automatic\":"));
  Serial.print(automaticSelection ? F("true") : F("false"));
  Serial.print(F(",\"evidence_duration_ms\":"));
  Serial.print(evidenceDurationMs);
  Serial.print(F(",\"switch_count\":"));
  Serial.print(switchCount);
  Serial.print(F(",\"uptime_ms\":"));
  Serial.print(millis());
  Serial.println(F("}"));
}

void switchTransport(wlf_failover::Transport next, const char* reason) {
  if (activeTransport == next) {
    return;
  }
  const uint32_t now = millis();
  const wlf_failover::Transport previous = activeTransport;
  const uint32_t evidenceDurationMs =
      degradationStartedMs == 0 ? 0 : now - degradationStartedMs;
  activeTransport = next;
  espnowStabilizationWindowsRemaining =
      next == wlf_failover::Transport::espnow
          ? kEspnowStabilizationWindows
          : 0;
  ++switchCount;
  lastSwitchMs = now;
  if (next == wlf_failover::Transport::udp) {
    // UDP and ESP-NOW share one 2.4 GHz radio. Schedule the first recovery
    // probe between active UDP probes instead of submitting both together.
    lastRecoveryProbeMs =
        now - recoveryProbeIntervalMs() + recoveryProbeOffsetMs();
  }
  degradationStartedMs = 0;
  consecutiveBadWindows = 0;
  consecutiveGoodWindows = 0;
  captureBaselines();
  emitTransition(previous, next, reason, evidenceDurationMs);
}

void emitWindow() {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"failover_window\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"active_transport\":\""));
  Serial.print(transportName(activeTransport));
  Serial.print(F("\",\"automatic\":"));
  Serial.print(automaticSelection ? F("true") : F("false"));
  Serial.print(F(",\"espnow_probes\":"));
  Serial.print(lastEspWindow.probes);
  Serial.print(F(",\"espnow_acks\":"));
  Serial.print(lastEspWindow.acks);
  Serial.print(F(",\"espnow_success_pct\":"));
  Serial.print(lastEspWindow.successPct);
  Serial.print(F(",\"udp_probes\":"));
  Serial.print(lastUdpWindow.probes);
  Serial.print(F(",\"udp_acks\":"));
  Serial.print(lastUdpWindow.acks);
  Serial.print(F(",\"udp_success_pct\":"));
  Serial.print(lastUdpWindow.successPct);
  Serial.print(F(",\"bad_windows\":"));
  Serial.print(consecutiveBadWindows);
  Serial.print(F(",\"good_windows\":"));
  Serial.print(consecutiveGoodWindows);
  Serial.print(F(",\"espnow_stabilization_windows_remaining\":"));
  Serial.print(espnowStabilizationWindowsRemaining);
  Serial.println(F("}"));
}

uint32_t minimumSamples(uint32_t intervalMs) {
  const uint32_t expected = config.windowMs / intervalMs;
  if (expected < 3) {
    return 3;
  }
  return expected > 10 ? 10 : expected;
}

void evaluateWindow() {
  const wlf_radio::Metrics radio = wlf_radio::metrics();
  const wlf_udp::Metrics udp = wlf_udp::metrics();
  lastEspWindow = windowMetrics(radio.probeTx, radio.matchedAckRx,
                                espProbeBaseline, espAckBaseline);
  lastUdpWindow = windowMetrics(udp.probeTx, udp.matchedAckRx,
                                udpProbeBaseline, udpAckBaseline);

  if (automaticSelection) {
    if (activeTransport == wlf_failover::Transport::espnow) {
      if (espnowStabilizationWindowsRemaining > 0) {
        --espnowStabilizationWindowsRemaining;
        consecutiveBadWindows = 0;
        consecutiveGoodWindows = 0;
        degradationStartedMs = 0;
      } else {
        const uint32_t minSamples = minimumSamples(config.probeIntervalMs);
        if (lastEspWindow.probes >= minSamples) {
          const uint8_t lossPct = 100U - lastEspWindow.successPct;
          if (lossPct >= config.fallbackLossPct) {
            if (consecutiveBadWindows == 0) {
              degradationStartedMs = millis();
            }
            ++consecutiveBadWindows;
          } else {
            consecutiveBadWindows = 0;
            degradationStartedMs = 0;
          }
        }
        consecutiveGoodWindows = 0;
        if (consecutiveBadWindows >= kBadWindowsRequired &&
            wlf_network::isConnected() && wlf_udp::isActive()) {
          switchTransport(wlf_failover::Transport::udp,
                          "espnow_ack_loss_threshold");
        }
      }
    } else {
      const uint32_t minSamples = minimumSamples(recoveryProbeIntervalMs());
      if (lastEspWindow.probes >= minSamples &&
          lastEspWindow.successPct >= config.recoverySuccessPct) {
        ++consecutiveGoodWindows;
      } else {
        consecutiveGoodWindows = 0;
      }
      consecutiveBadWindows = 0;
      if (consecutiveGoodWindows >= kGoodWindowsRequired) {
        switchTransport(wlf_failover::Transport::espnow,
                        "espnow_recovery_threshold");
      }
    }
  }
  emitWindow();
}

}  // namespace

namespace wlf_failover {

bool configure(uint32_t probeIntervalMs, uint32_t windowMs,
               uint8_t fallbackLossPct, uint8_t recoverySuccessPct) {
  if (probeIntervalMs < 100 || probeIntervalMs > 10000 || windowMs < 1000 ||
      windowMs > 60000 || windowMs < probeIntervalMs * 3UL ||
      fallbackLossPct == 0 || fallbackLossPct > 100 ||
      recoverySuccessPct == 0 || recoverySuccessPct > 100 ||
      recoverySuccessPct <= 100U - fallbackLossPct) {
    return false;
  }
  config.probeIntervalMs = probeIntervalMs;
  config.windowMs = windowMs;
  config.fallbackLossPct = fallbackLossPct;
  config.recoverySuccessPct = recoverySuccessPct;
  captureBaselines();
  lastWindowMs = millis();
  emitStatus();
  return true;
}

bool enable() {
  if (!wlf_network::isConnected() || !wlf_radio::metrics().active ||
      !wlf_udp::begin()) {
    return false;
  }
  wlf_radio::setAutoSend(false);
  wlf_radio::setQuiet(true);
  wlf_radio::resetStats();
  wlf_udp::resetStats();
  enabled = true;
  automaticSelection = true;
  activeTransport = Transport::espnow;
  switchCount = 0;
  espSendRejects = 0;
  udpSendRejects = 0;
  consecutiveBadWindows = 0;
  consecutiveGoodWindows = 0;
  espnowStabilizationWindowsRemaining = kEspnowStabilizationWindows;
  degradationStartedMs = 0;
  lastSwitchMs = 0;
  const uint32_t now = millis();
  lastActiveProbeMs = now - config.probeIntervalMs;
  lastRecoveryProbeMs = now - recoveryProbeIntervalMs();
  lastWindowMs = now;
  lastUdpRestartAttemptMs = now;
  captureBaselines();
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"failover_enabled\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\",\"active_transport\":\"esp-now\"}"));
  emitStatus();
  return true;
}

void disable() {
  enabled = false;
  automaticSelection = true;
  wlf_radio::setQuiet(false);
  wlf_radio::setAutoSend(true);
  wlf_udp::stop();
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"failover_disabled\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\"}"));
}

bool force(Transport transport) {
  if (!enabled) {
    return false;
  }
  if (transport == Transport::udp &&
      (!wlf_network::isConnected() || !wlf_udp::isActive())) {
    return false;
  }
  automaticSelection = false;
  switchTransport(transport, "manual_force");
  emitStatus();
  return true;
}

void useAutomaticSelection() {
  automaticSelection = true;
  consecutiveBadWindows = 0;
  consecutiveGoodWindows = 0;
  espnowStabilizationWindowsRemaining =
      activeTransport == Transport::espnow ? kEspnowStabilizationWindows : 0;
  degradationStartedMs = 0;
  captureBaselines();
  lastWindowMs = millis();
  emitStatus();
}

bool isEnabled() { return enabled; }

void emitStatus() {
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"failover_status\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"enabled\":"));
  Serial.print(enabled ? F("true") : F("false"));
  Serial.print(F(",\"automatic\":"));
  Serial.print(automaticSelection ? F("true") : F("false"));
  Serial.print(F(",\"active_transport\":\""));
  Serial.print(transportName(activeTransport));
  Serial.print(F("\",\"probe_interval_ms\":"));
  Serial.print(config.probeIntervalMs);
  Serial.print(F(",\"window_ms\":"));
  Serial.print(config.windowMs);
  Serial.print(F(",\"fallback_loss_pct\":"));
  Serial.print(config.fallbackLossPct);
  Serial.print(F(",\"recovery_success_pct\":"));
  Serial.print(config.recoverySuccessPct);
  Serial.print(F(",\"bad_windows_required\":"));
  Serial.print(kBadWindowsRequired);
  Serial.print(F(",\"good_windows_required\":"));
  Serial.print(kGoodWindowsRequired);
  Serial.print(F(",\"espnow_stabilization_windows\":"));
  Serial.print(kEspnowStabilizationWindows);
  Serial.print(F(",\"espnow_stabilization_windows_remaining\":"));
  Serial.print(espnowStabilizationWindowsRemaining);
  Serial.print(F(",\"recovery_probe_offset_ms\":"));
  Serial.print(recoveryProbeOffsetMs());
  Serial.print(F(",\"recovery_probe_interval_ms\":"));
  Serial.print(recoveryProbeIntervalMs());
  Serial.print(F(",\"recovery_probe_guard_ms\":"));
  Serial.print(recoveryProbeGuardMs());
  Serial.print(F(",\"switch_count\":"));
  Serial.print(switchCount);
  Serial.print(F(",\"last_switch_ms\":"));
  Serial.print(lastSwitchMs);
  Serial.print(F(",\"espnow_send_rejects\":"));
  Serial.print(espSendRejects);
  Serial.print(F(",\"udp_send_rejects\":"));
  Serial.print(udpSendRejects);
  Serial.println(F("}"));
}

void poll() {
  if (!enabled) {
    return;
  }
  const uint32_t now = millis();

  if (!wlf_network::isConnected()) {
    if (activeTransport == Transport::udp) {
      switchTransport(Transport::espnow, "wifi_unavailable");
    }
  } else if (!wlf_udp::isActive() &&
             now - lastUdpRestartAttemptMs >= kUdpRestartIntervalMs) {
    lastUdpRestartAttemptMs = now;
    wlf_udp::begin();
  }

  const bool recoveryDue =
      activeTransport == Transport::udp &&
      now - lastRecoveryProbeMs >= recoveryProbeIntervalMs();
  if (recoveryDue) {
    // ESP-NOW and UDP share one radio. Once a recovery probe is due, hold the
    // UDP schedule until a quiet guard interval has elapsed, then reserve the
    // following active interval as well. This prevents the two transmissions
    // (and their application ACKs) from being queued almost simultaneously as
    // their otherwise independent periodic schedules drift through phase.
    if (now - lastActiveProbeMs >= recoveryProbeGuardMs()) {
      lastRecoveryProbeMs = now;
      lastActiveProbeMs = now;
      if (!wlf_radio::sendProbe()) {
        ++espSendRejects;
      }
    }
  } else if (now - lastActiveProbeMs >= config.probeIntervalMs) {
    lastActiveProbeMs = now;
    const bool sent = activeTransport == Transport::espnow
                          ? wlf_radio::sendProbe()
                          : wlf_udp::sendProbe();
    if (!sent) {
      if (activeTransport == Transport::espnow) {
        ++espSendRejects;
      } else {
        ++udpSendRejects;
      }
    }
  }

  if (now - lastWindowMs >= config.windowMs) {
    lastWindowMs = now;
    evaluateWindow();
  }
}

}  // namespace wlf_failover
