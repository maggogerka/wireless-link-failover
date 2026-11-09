#pragma once

#include <Arduino.h>

namespace wlf_failover {

enum class Transport : uint8_t { espnow, udp };

bool enable();
void disable();
void poll();
void emitStatus();
bool configure(uint32_t probeIntervalMs, uint32_t windowMs,
               uint8_t fallbackLossPct, uint8_t recoverySuccessPct);
bool force(Transport transport);
void useAutomaticSelection();
bool isEnabled();

}  // namespace wlf_failover
