#pragma once

#include <Arduino.h>

namespace wlf_udp {

struct Metrics {
  bool active;
  bool testActive;
  uint32_t probeTx;
  uint32_t matchedAckRx;
  uint32_t lastMatchedAckMs;
};

bool begin();
void stop();
void poll();
bool sendProbe();
bool startTest(uint32_t packetCount, uint32_t intervalMs);
void resetStats();
void emitStatus();
bool isActive();
Metrics metrics();

}  // namespace wlf_udp
