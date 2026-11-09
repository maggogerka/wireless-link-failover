#pragma once

#include <Arduino.h>

namespace wlf_network {

bool connect(const String& ssid, const String& password);
void disconnect();
void poll();
void emitStatus();
bool isConnected();

}  // namespace wlf_network
