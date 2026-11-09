#include "udp_transport.h"

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#elif defined(ESP32)
#include <WiFi.h>
#include <WiFiUdp.h>
#else
#error "Unsupported target"
#endif

#include <cstring>

namespace {

constexpr char kSchema[] = "wlf.telemetry.v1";
constexpr uint32_t kPacketMagic = 0x31464C57UL;
constexpr uint8_t kPacketVersion = 1;
constexpr uint8_t kUdpProbeMessage = 3;
constexpr uint8_t kUdpAckMessage = 4;
constexpr uint16_t kUdpPort = 42100;
constexpr uint8_t kProbeHistorySize = 64;
constexpr uint8_t kNodeCount = 3;
constexpr uint32_t kTestFinalizeDelayMs = 1500;

struct __attribute__((packed)) UdpPacket {
  uint32_t magic;
  uint8_t version;
  uint8_t messageType;
  uint8_t senderNode;
  uint8_t targetNode;
  uint32_t sequence;
  uint32_t senderUptimeMs;
  uint32_t crc32;
};

static_assert(sizeof(UdpPacket) == 20,
              "UDP and ESP-NOW packet sizes must remain comparable");

struct ProbeRecord {
  uint32_t sequence;
  uint32_t sentAtMs;
  bool active;
};

struct SequenceState {
  bool initialized;
  uint32_t lastSequence;
  uint32_t received;
  uint32_t missing;
  uint32_t duplicates;
  uint32_t outOfOrder;
};

struct TestSeries {
  bool sending;
  bool finalizing;
  uint32_t requested;
  uint32_t accepted;
  uint32_t rejected;
  uint32_t intervalMs;
  uint32_t startedAtMs;
  uint32_t lastSendAtMs;
  uint32_t finishedSendingAtMs;
  uint32_t finalizeAtMs;
  uint32_t firstSequence;
  uint32_t lastSequence;
  uint32_t lastProgressReported;
  uint32_t ackReceived;
  uint32_t rttSamples;
  uint32_t rttMinMs;
  uint32_t rttMaxMs;
  uint64_t rttSumMs;
};

WiFiUDP udp;
bool active = false;
uint32_t nextSequence = 0;
ProbeRecord probeHistory[kProbeHistorySize] = {};
SequenceState sequenceStates[kNodeCount + 1] = {};
TestSeries testSeries = {};
uint32_t probeTxCount = 0;
uint32_t probeRxCount = 0;
uint32_t ackTxCount = 0;
uint32_t ackRxCount = 0;
uint32_t invalidPacketCount = 0;
uint32_t unmatchedAckCount = 0;
uint32_t rttSampleCount = 0;
uint32_t rttMinMs = 0;
uint32_t rttMaxMs = 0;
uint64_t rttSumMs = 0;
uint32_t lastMatchedAckMs = 0;

const char* nodeId() {
#if defined(ESP8266)
  return "node8266";
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return "node32s3";
#else
  return "node32";
#endif
}

uint8_t nodeNumber() {
#if defined(ESP8266)
  return 1;
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  return 3;
#else
  return 2;
#endif
}

uint32_t calculateCrc32(const uint8_t* data, size_t length) {
  uint32_t crc = 0xFFFFFFFFUL;
  for (size_t index = 0; index < length; ++index) {
    crc ^= data[index];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = -(crc & 1UL);
      crc = (crc >> 1U) ^ (0xEDB88320UL & mask);
    }
  }
  return ~crc;
}

IPAddress broadcastAddress() {
  const IPAddress local = WiFi.localIP();
  const IPAddress mask = WiFi.subnetMask();
  return IPAddress((local[0] & mask[0]) | static_cast<uint8_t>(~mask[0]),
                   (local[1] & mask[1]) | static_cast<uint8_t>(~mask[1]),
                   (local[2] & mask[2]) | static_cast<uint8_t>(~mask[2]),
                   (local[3] & mask[3]) | static_cast<uint8_t>(~mask[3]));
}

void rememberProbe(uint32_t sequence, uint32_t sentAtMs) {
  ProbeRecord& record = probeHistory[sequence % kProbeHistorySize];
  record.sequence = sequence;
  record.sentAtMs = sentAtMs;
  record.active = true;
}

bool resolveProbe(uint32_t sequence, uint32_t& rttMs) {
  ProbeRecord& record = probeHistory[sequence % kProbeHistorySize];
  if (!record.active || record.sequence != sequence) {
    return false;
  }
  rttMs = millis() - record.sentAtMs;
  record.active = false;
  return true;
}

void trackSequence(uint8_t senderNode, uint32_t sequence) {
  if (senderNode == 0 || senderNode > kNodeCount) {
    return;
  }
  SequenceState& state = sequenceStates[senderNode];
  ++state.received;
  if (!state.initialized) {
    state.initialized = true;
    state.lastSequence = sequence;
  } else if (sequence == state.lastSequence) {
    ++state.duplicates;
  } else if (sequence > state.lastSequence) {
    if (sequence > state.lastSequence + 1U) {
      state.missing += sequence - state.lastSequence - 1U;
    }
    state.lastSequence = sequence;
  } else {
    ++state.outOfOrder;
  }
}

bool sequenceBelongsToTest(uint32_t sequence) {
  return (testSeries.sending || testSeries.finalizing) &&
         testSeries.accepted > 0 && sequence >= testSeries.firstSequence &&
         sequence <= testSeries.lastSequence;
}

bool sendPacket(const UdpPacket& packet, const IPAddress& destination) {
  if (!active || WiFi.status() != WL_CONNECTED ||
      udp.beginPacket(destination, kUdpPort) != 1) {
    return false;
  }
  const size_t written =
      udp.write(reinterpret_cast<const uint8_t*>(&packet), sizeof(packet));
  return written == sizeof(packet) && udp.endPacket() == 1;
}

bool sendAck(const IPAddress& destination, uint8_t targetNode,
             uint32_t sequence) {
  UdpPacket packet = {};
  packet.magic = kPacketMagic;
  packet.version = kPacketVersion;
  packet.messageType = kUdpAckMessage;
  packet.senderNode = nodeNumber();
  packet.targetNode = targetNode;
  packet.sequence = sequence;
  packet.senderUptimeMs = millis();
  packet.crc32 = calculateCrc32(reinterpret_cast<const uint8_t*>(&packet),
                                offsetof(UdpPacket, crc32));
  const bool sent = sendPacket(packet, destination);
  if (sent) {
    ++ackTxCount;
  }
  return sent;
}

void processPacket(const UdpPacket& packet, const IPAddress& source) {
  const bool valid = packet.magic == kPacketMagic &&
                     packet.version == kPacketVersion &&
                     packet.crc32 == calculateCrc32(
                                         reinterpret_cast<const uint8_t*>(&packet),
                                         offsetof(UdpPacket, crc32));
  if (!valid) {
    ++invalidPacketCount;
    return;
  }
  if (packet.senderNode == nodeNumber()) {
    return;
  }
  if (packet.messageType == kUdpProbeMessage) {
    ++probeRxCount;
    trackSequence(packet.senderNode, packet.sequence);
    sendAck(source, packet.senderNode, packet.sequence);
    return;
  }
  if (packet.messageType != kUdpAckMessage ||
      packet.targetNode != nodeNumber()) {
    return;
  }
  ++ackRxCount;
  uint32_t rttMs = 0;
  if (!resolveProbe(packet.sequence, rttMs)) {
    ++unmatchedAckCount;
    return;
  }
  ++rttSampleCount;
  lastMatchedAckMs = millis();
  rttSumMs += rttMs;
  if (rttSampleCount == 1 || rttMs < rttMinMs) {
    rttMinMs = rttMs;
  }
  if (rttMs > rttMaxMs) {
    rttMaxMs = rttMs;
  }
  if (sequenceBelongsToTest(packet.sequence)) {
    ++testSeries.ackReceived;
    ++testSeries.rttSamples;
    testSeries.rttSumMs += rttMs;
    if (testSeries.rttSamples == 1 || rttMs < testSeries.rttMinMs) {
      testSeries.rttMinMs = rttMs;
    }
    if (rttMs > testSeries.rttMaxMs) {
      testSeries.rttMaxMs = rttMs;
    }
  }
}

void emitNullableRtt(uint32_t samples, uint32_t value) {
  if (samples > 0) {
    Serial.print(value);
  } else {
    Serial.print(F("null"));
  }
}

}  // namespace

namespace wlf_udp {

bool begin() {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }
  if (active) {
    udp.stop();
  }
  active = udp.begin(kUdpPort) == 1;
  emitStatus();
  return active;
}

void stop() {
  udp.stop();
  active = false;
  emitStatus();
}

bool sendProbe() {
  if (!active) {
    return false;
  }
  UdpPacket packet = {};
  packet.magic = kPacketMagic;
  packet.version = kPacketVersion;
  packet.messageType = kUdpProbeMessage;
  packet.senderNode = nodeNumber();
  packet.sequence = ++nextSequence;
  packet.senderUptimeMs = millis();
  packet.crc32 = calculateCrc32(reinterpret_cast<const uint8_t*>(&packet),
                                offsetof(UdpPacket, crc32));
  const bool sent = sendPacket(packet, broadcastAddress());
  if (sent) {
    ++probeTxCount;
    rememberProbe(packet.sequence, packet.senderUptimeMs);
  } else {
    --nextSequence;
  }
  return sent;
}

bool startTest(uint32_t packetCount, uint32_t intervalMs) {
  if (!active || testSeries.sending || testSeries.finalizing ||
      packetCount == 0 || packetCount > 100000 || intervalMs < 10 ||
      intervalMs > 60000) {
    return false;
  }
  testSeries = {};
  testSeries.sending = true;
  testSeries.requested = packetCount;
  testSeries.intervalMs = intervalMs;
  testSeries.startedAtMs = millis();
  testSeries.lastSendAtMs = testSeries.startedAtMs - intervalMs;
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"udp_test_started\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"requested\":"));
  Serial.print(packetCount);
  Serial.print(F(",\"interval_ms\":"));
  Serial.print(intervalMs);
  Serial.println(F("}"));
  return true;
}

void resetStats() {
  probeTxCount = 0;
  probeRxCount = 0;
  ackTxCount = 0;
  ackRxCount = 0;
  invalidPacketCount = 0;
  unmatchedAckCount = 0;
  rttSampleCount = 0;
  rttMinMs = 0;
  rttMaxMs = 0;
  rttSumMs = 0;
  lastMatchedAckMs = 0;
  memset(probeHistory, 0, sizeof(probeHistory));
  memset(sequenceStates, 0, sizeof(sequenceStates));
  testSeries = {};
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"udp_stats_reset\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\"}"));
}

void emitStatus() {
  uint32_t missing = 0;
  uint32_t duplicates = 0;
  uint32_t outOfOrder = 0;
  for (uint8_t node = 1; node <= kNodeCount; ++node) {
    missing += sequenceStates[node].missing;
    duplicates += sequenceStates[node].duplicates;
    outOfOrder += sequenceStates[node].outOfOrder;
  }
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"udp_info\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"active\":"));
  Serial.print(active ? F("true") : F("false"));
  Serial.print(F(",\"wifi_connected\":"));
  Serial.print(WiFi.status() == WL_CONNECTED ? F("true") : F("false"));
  Serial.print(F(",\"port\":"));
  Serial.print(kUdpPort);
  Serial.print(F(",\"local_ip\":\""));
  Serial.print(WiFi.localIP().toString());
  Serial.print(F("\",\"broadcast_ip\":\""));
  Serial.print(broadcastAddress().toString());
  Serial.print(F("\",\"probe_tx\":"));
  Serial.print(probeTxCount);
  Serial.print(F(",\"probe_rx\":"));
  Serial.print(probeRxCount);
  Serial.print(F(",\"ack_tx\":"));
  Serial.print(ackTxCount);
  Serial.print(F(",\"ack_rx\":"));
  Serial.print(ackRxCount);
  Serial.print(F(",\"invalid_packets\":"));
  Serial.print(invalidPacketCount);
  Serial.print(F(",\"unmatched_acks\":"));
  Serial.print(unmatchedAckCount);
  Serial.print(F(",\"sequence_missing\":"));
  Serial.print(missing);
  Serial.print(F(",\"sequence_duplicates\":"));
  Serial.print(duplicates);
  Serial.print(F(",\"sequence_out_of_order\":"));
  Serial.print(outOfOrder);
  Serial.print(F(",\"rtt_samples\":"));
  Serial.print(rttSampleCount);
  Serial.print(F(",\"rtt_min_ms\":"));
  emitNullableRtt(rttSampleCount, rttMinMs);
  Serial.print(F(",\"rtt_avg_ms\":"));
  emitNullableRtt(rttSampleCount,
                  rttSampleCount > 0
                      ? static_cast<uint32_t>(rttSumMs / rttSampleCount)
                      : 0);
  Serial.print(F(",\"rtt_max_ms\":"));
  emitNullableRtt(rttSampleCount, rttMaxMs);
  Serial.println(F("}"));
}

bool isActive() { return active; }

Metrics metrics() {
  Metrics snapshot = {};
  snapshot.active = active;
  snapshot.testActive = testSeries.sending || testSeries.finalizing;
  snapshot.probeTx = probeTxCount;
  snapshot.matchedAckRx = rttSampleCount;
  snapshot.lastMatchedAckMs = lastMatchedAckMs;
  return snapshot;
}

void poll() {
  if (active && WiFi.status() == WL_CONNECTED) {
    int packetLength = 0;
    while ((packetLength = udp.parsePacket()) > 0) {
      const IPAddress source = udp.remoteIP();
      if (packetLength != static_cast<int>(sizeof(UdpPacket))) {
        while (udp.available() > 0) {
          udp.read();
        }
        ++invalidPacketCount;
        continue;
      }
      UdpPacket packet = {};
      const int received = udp.read(reinterpret_cast<uint8_t*>(&packet),
                                    sizeof(packet));
      if (received == static_cast<int>(sizeof(packet))) {
        processPacket(packet, source);
      } else {
        ++invalidPacketCount;
      }
    }
  }

  const uint32_t now = millis();
  if (testSeries.sending &&
      now - testSeries.lastSendAtMs >= testSeries.intervalMs) {
    testSeries.lastSendAtMs = now;
    if (sendProbe()) {
      ++testSeries.accepted;
      if (testSeries.accepted == 1) {
        testSeries.firstSequence = nextSequence;
      }
      testSeries.lastSequence = nextSequence;
    } else {
      ++testSeries.rejected;
    }
    if (testSeries.accepted >= testSeries.requested) {
      testSeries.sending = false;
      testSeries.finalizing = true;
      testSeries.finishedSendingAtMs = now;
      testSeries.finalizeAtMs = now + kTestFinalizeDelayMs;
    } else if (testSeries.accepted > 0 &&
               testSeries.accepted % 100U == 0 &&
               testSeries.accepted != testSeries.lastProgressReported) {
      testSeries.lastProgressReported = testSeries.accepted;
      Serial.print(F("{\"schema\":\""));
      Serial.print(kSchema);
      Serial.print(F("\",\"type\":\"udp_test_progress\",\"node_id\":\""));
      Serial.print(nodeId());
      Serial.print(F("\",\"accepted\":"));
      Serial.print(testSeries.accepted);
      Serial.print(F(",\"requested\":"));
      Serial.print(testSeries.requested);
      Serial.println(F("}"));
    }
  }

  if (testSeries.finalizing &&
      static_cast<int32_t>(now - testSeries.finalizeAtMs) >= 0) {
    testSeries.finalizing = false;
    const uint32_t lost = testSeries.accepted > testSeries.ackReceived
                              ? testSeries.accepted - testSeries.ackReceived
                              : 0;
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"udp_test_complete\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.print(F("\",\"requested\":"));
    Serial.print(testSeries.requested);
    Serial.print(F(",\"accepted\":"));
    Serial.print(testSeries.accepted);
    Serial.print(F(",\"rejected\":"));
    Serial.print(testSeries.rejected);
    Serial.print(F(",\"ack_received\":"));
    Serial.print(testSeries.ackReceived);
    Serial.print(F(",\"ack_lost\":"));
    Serial.print(lost);
    Serial.print(F(",\"send_duration_ms\":"));
    Serial.print(testSeries.finishedSendingAtMs - testSeries.startedAtMs);
    Serial.print(F(",\"rtt_samples\":"));
    Serial.print(testSeries.rttSamples);
    Serial.print(F(",\"rtt_min_ms\":"));
    emitNullableRtt(testSeries.rttSamples, testSeries.rttMinMs);
    Serial.print(F(",\"rtt_avg_ms\":"));
    emitNullableRtt(
        testSeries.rttSamples,
        testSeries.rttSamples > 0
            ? static_cast<uint32_t>(testSeries.rttSumMs / testSeries.rttSamples)
            : 0);
    Serial.print(F(",\"rtt_max_ms\":"));
    emitNullableRtt(testSeries.rttSamples, testSeries.rttMaxMs);
    Serial.println(F("}"));
  }
}

}  // namespace wlf_udp
