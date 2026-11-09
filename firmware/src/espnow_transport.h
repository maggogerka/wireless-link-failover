#pragma once

#include <Arduino.h>

namespace wlf_radio {

struct Metrics {
  bool active;
  bool testActive;
  uint32_t probeTx;
  uint32_t matchedAckRx;
  uint32_t lastMatchedAckMs;
};

bool begin();
void poll();
bool sendProbe();
void emitStatus();
bool restoreChannel();
bool setChannel(uint8_t channel);
bool startTest(uint32_t packetCount, uint32_t intervalMs);
void setAutoSend(bool enabled);
void setQuiet(bool enabled);
void setAckDelay(uint32_t delayMs);
void setAckResponsesEnabled(bool enabled);
void resetStats();
Metrics metrics();

}  // namespace wlf_radio
