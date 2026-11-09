#include "espnow_transport.h"

#include <Arduino.h>
#include <cstring>

#if defined(ESP8266)
#include <ESP8266WiFi.h>
extern "C" {
#include <espnow.h>
#include <user_interface.h>
}
#elif defined(ESP32)
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#else
#error "Unsupported target"
#endif

namespace {

constexpr uint8_t kDefaultRadioChannel = 1;
constexpr uint32_t kPacketMagic = 0x31464C57UL;  // "WLF1" in little endian.
constexpr uint8_t kPacketVersion = 1;
constexpr uint8_t kProbeMessage = 1;
constexpr uint8_t kAckMessage = 2;
constexpr uint32_t kProbePeriodMs = 2000;
constexpr uint8_t kQueueSize = 8;
constexpr uint8_t kAckScheduleSize = 8;
constexpr uint8_t kProbeHistorySize = 32;
constexpr uint8_t kNodeCount = 3;
constexpr uint32_t kTestFinalizeDelayMs = 1500;
constexpr int16_t kRssiUnavailable = -32768;
constexpr char kSchema[] = "wlf.telemetry.v1";
constexpr uint8_t kBroadcastMac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

struct __attribute__((packed)) ExperimentPacket {
  uint32_t magic;
  uint8_t version;
  uint8_t messageType;
  uint8_t senderNode;
  uint8_t flags;
  uint32_t sequence;
  uint32_t senderUptimeMs;
  uint32_t crc32;
};

static_assert(sizeof(ExperimentPacket) == 20,
              "The over-the-air packet layout must stay stable");

struct RxEvent {
  uint8_t source[6];
  uint16_t receivedLength;
  int16_t rssiDbm;
  ExperimentPacket packet;
};

struct TxEvent {
  uint8_t destination[6];
  uint8_t status;
  uint8_t messageType;
  uint32_t sequence;
};

struct ProbeRecord {
  uint32_t sequence;
  uint32_t sentAtMs;
  bool active;
};

struct PendingAck {
  uint8_t targetNode;
  uint32_t sequence;
  uint32_t dueAtMs;
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
  bool previousQuiet;
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

RxEvent rxQueue[kQueueSize] = {};
TxEvent txQueue[kQueueSize] = {};
volatile uint8_t rxWriteIndex = 0;
volatile uint8_t rxReadIndex = 0;
volatile uint8_t txWriteIndex = 0;
volatile uint8_t txReadIndex = 0;
volatile uint32_t rxQueueDrops = 0;
volatile uint32_t txQueueDrops = 0;

bool radioActive = false;
uint8_t radioChannel = kDefaultRadioChannel;
uint32_t nextSequence = 0;
volatile uint32_t submittedSequence = 0;
volatile uint8_t submittedMessageType = 0;
uint32_t lastProbeMs = 0;
ProbeRecord probeHistory[kProbeHistorySize] = {};
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
SequenceState sequenceStates[kNodeCount + 1] = {};
TestSeries testSeries = {};
bool autoSendEnabled = true;
bool quietMode = false;
PendingAck ackSchedule[kAckScheduleSize] = {};
uint8_t ackScheduleWriteIndex = 0;
uint8_t ackScheduleReadIndex = 0;
uint32_t ackScheduleDrops = 0;
uint32_t ackDelayMs = 0;
bool ackResponsesEnabled = true;
uint32_t ackSuppressedCount = 0;

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
    return;
  }

  if (sequence == state.lastSequence) {
    ++state.duplicates;
    return;
  }
  if (sequence > state.lastSequence) {
    if (sequence > state.lastSequence + 1U) {
      state.missing += sequence - state.lastSequence - 1U;
    }
    state.lastSequence = sequence;
    return;
  }
  ++state.outOfOrder;
}

bool sequenceBelongsToTest(uint32_t sequence) {
  if ((!testSeries.sending && !testSeries.finalizing) ||
      testSeries.accepted == 0) {
    return false;
  }
  return sequence >= testSeries.firstSequence &&
         sequence <= testSeries.lastSequence;
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

void formatMac(const uint8_t* mac, char* output, size_t outputSize) {
  snprintf(output, outputSize, "%02X:%02X:%02X:%02X:%02X:%02X", mac[0],
           mac[1], mac[2], mac[3], mac[4], mac[5]);
}

int transmitPacket(const ExperimentPacket& packet) {
  submittedSequence = packet.sequence;
  submittedMessageType = packet.messageType;
#if defined(ESP8266)
  uint8_t destination[6] = {};
  memcpy(destination, kBroadcastMac, sizeof(destination));
  return esp_now_send(destination,
                      const_cast<uint8_t*>(
                          reinterpret_cast<const uint8_t*>(&packet)),
                      static_cast<uint8_t>(sizeof(packet)));
#else
  return static_cast<int>(esp_now_send(
      kBroadcastMac, reinterpret_cast<const uint8_t*>(&packet), sizeof(packet)));
#endif
}

bool addBroadcastPeer() {
#if defined(ESP8266)
  uint8_t destination[6] = {};
  memcpy(destination, kBroadcastMac, sizeof(destination));
  return esp_now_add_peer(destination, ESP_NOW_ROLE_COMBO, radioChannel,
                          nullptr, 0) == 0;
#else
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, kBroadcastMac, sizeof(peer.peer_addr));
  peer.channel = radioChannel;
  peer.ifidx = WIFI_IF_STA;
  peer.encrypt = false;
  return esp_now_add_peer(&peer) == ESP_OK;
#endif
}

void removeBroadcastPeer() {
#if defined(ESP8266)
  uint8_t destination[6] = {};
  memcpy(destination, kBroadcastMac, sizeof(destination));
  esp_now_del_peer(destination);
#else
  esp_now_del_peer(kBroadcastMac);
#endif
}

bool sendAck(uint8_t targetNode, uint32_t acknowledgedSequence) {
  if (!radioActive) {
    return false;
  }

  ExperimentPacket packet = {};
  packet.magic = kPacketMagic;
  packet.version = kPacketVersion;
  packet.messageType = kAckMessage;
  packet.senderNode = nodeNumber();
  packet.flags = targetNode;
  packet.sequence = acknowledgedSequence;
  packet.senderUptimeMs = millis();
  packet.crc32 = calculateCrc32(reinterpret_cast<const uint8_t*>(&packet),
                                offsetof(ExperimentPacket, crc32));
  const int result = transmitPacket(packet);
  if (result == 0) {
    ++ackTxCount;
  }

  if (!quietMode) {
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"espnow_ack_tx\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.print(F("\",\"target_node\":"));
    Serial.print(targetNode);
    Serial.print(F(",\"acknowledged_sequence\":"));
    Serial.print(acknowledgedSequence);
    Serial.print(F(",\"accepted\":"));
    Serial.print(result == 0 ? F("true") : F("false"));
    Serial.print(F(",\"result_code\":"));
    Serial.print(result);
    Serial.println(F("}"));
  }
  return result == 0;
}

bool scheduleAck(uint8_t targetNode, uint32_t acknowledgedSequence) {
  const uint8_t nextIndex =
      (ackScheduleWriteIndex + 1U) % kAckScheduleSize;
  if (nextIndex == ackScheduleReadIndex) {
    ++ackScheduleDrops;
    return false;
  }
  PendingAck& pending = ackSchedule[ackScheduleWriteIndex];
  pending.targetNode = targetNode;
  pending.sequence = acknowledgedSequence;
  pending.dueAtMs = millis() + ackDelayMs;
  ackScheduleWriteIndex = nextIndex;
  return true;
}

void processPendingAcks() {
  while (ackScheduleReadIndex != ackScheduleWriteIndex) {
    const PendingAck& pending = ackSchedule[ackScheduleReadIndex];
    if (static_cast<int32_t>(millis() - pending.dueAtMs) < 0) {
      return;
    }
    sendAck(pending.targetNode, pending.sequence);
    ackScheduleReadIndex =
        (ackScheduleReadIndex + 1U) % kAckScheduleSize;
  }
}

void enqueueRx(const uint8_t* source, const uint8_t* data, size_t length,
               int16_t rssiDbm) {
  const uint8_t writeIndex = rxWriteIndex;
  const uint8_t nextIndex = (writeIndex + 1U) % kQueueSize;
  if (nextIndex == rxReadIndex) {
    rxQueueDrops = rxQueueDrops + 1U;
    return;
  }

  RxEvent event = {};
  memcpy(event.source, source, sizeof(event.source));
  event.receivedLength = static_cast<uint16_t>(length);
  event.rssiDbm = rssiDbm;
  const size_t copyLength =
      length < sizeof(event.packet) ? length : sizeof(event.packet);
  memcpy(&event.packet, data, copyLength);
  rxQueue[writeIndex] = event;
  __sync_synchronize();
  rxWriteIndex = nextIndex;
}

void enqueueTx(const uint8_t* destination, uint8_t status) {
  const uint8_t writeIndex = txWriteIndex;
  const uint8_t nextIndex = (writeIndex + 1U) % kQueueSize;
  if (nextIndex == txReadIndex) {
    txQueueDrops = txQueueDrops + 1U;
    return;
  }

  TxEvent event = {};
  memcpy(event.destination, destination, sizeof(event.destination));
  event.status = status;
  event.sequence = submittedSequence;
  event.messageType = submittedMessageType;
  txQueue[writeIndex] = event;
  __sync_synchronize();
  txWriteIndex = nextIndex;
}

#if defined(ESP8266)
void onReceive(uint8_t* source, uint8_t* data, uint8_t length) {
  enqueueRx(source, data, length, kRssiUnavailable);
}

void onSend(uint8_t* destination, uint8_t status) {
  enqueueTx(destination, status);
}
#else
void onReceive(const esp_now_recv_info_t* info, const uint8_t* data,
               int length) {
  if (info == nullptr || info->src_addr == nullptr || data == nullptr ||
      length < 0) {
    return;
  }
  const int16_t rssi =
      info->rx_ctrl == nullptr ? kRssiUnavailable : info->rx_ctrl->rssi;
  enqueueRx(info->src_addr, data, static_cast<size_t>(length), rssi);
}

void onSend(const esp_now_send_info_t* info, esp_now_send_status_t status) {
  const uint8_t* destination = kBroadcastMac;
  if (info != nullptr && info->des_addr != nullptr) {
    destination = info->des_addr;
  }
  enqueueTx(destination, static_cast<uint8_t>(status));
}
#endif

bool popRx(RxEvent& event) {
  const uint8_t readIndex = rxReadIndex;
  if (readIndex == rxWriteIndex) {
    return false;
  }
  __sync_synchronize();
  event = rxQueue[readIndex];
  rxReadIndex = (readIndex + 1U) % kQueueSize;
  return true;
}

bool popTx(TxEvent& event) {
  const uint8_t readIndex = txReadIndex;
  if (readIndex == txWriteIndex) {
    return false;
  }
  __sync_synchronize();
  event = txQueue[readIndex];
  txReadIndex = (readIndex + 1U) % kQueueSize;
  return true;
}

void emitRx(const RxEvent& event) {
  char source[18] = {};
  formatMac(event.source, source, sizeof(source));

  const bool lengthValid = event.receivedLength == sizeof(ExperimentPacket);
  const bool headerValid = lengthValid && event.packet.magic == kPacketMagic &&
                           event.packet.version == kPacketVersion;
  const uint32_t expectedCrc =
      calculateCrc32(reinterpret_cast<const uint8_t*>(&event.packet),
                     offsetof(ExperimentPacket, crc32));
  const bool crcValid = headerValid && expectedCrc == event.packet.crc32;

  if (!quietMode) {
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"espnow_rx\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.print(F("\",\"source_mac\":\""));
    Serial.print(source);
    Serial.print(F("\",\"length\":"));
    Serial.print(event.receivedLength);
    Serial.print(F(",\"valid\":"));
    Serial.print(crcValid ? F("true") : F("false"));
    if (headerValid) {
      Serial.print(F(",\"sender_node\":"));
      Serial.print(event.packet.senderNode);
      Serial.print(F(",\"message_type\":"));
      Serial.print(event.packet.messageType);
      Serial.print(F(",\"target_node\":"));
      Serial.print(event.packet.flags);
      Serial.print(F(",\"sequence\":"));
      Serial.print(event.packet.sequence);
      Serial.print(F(",\"sender_uptime_ms\":"));
      Serial.print(event.packet.senderUptimeMs);
      Serial.print(F(",\"crc_valid\":"));
      Serial.print(crcValid ? F("true") : F("false"));
    }
    Serial.print(F(",\"rssi_dbm\":"));
    if (event.rssiDbm == kRssiUnavailable) {
      Serial.print(F("null"));
    } else {
      Serial.print(event.rssiDbm);
    }
    Serial.println(F("}"));
  }

  if (!crcValid) {
    ++invalidPacketCount;
    return;
  }

  if (event.packet.messageType == kProbeMessage) {
    ++probeRxCount;
    trackSequence(event.packet.senderNode, event.packet.sequence);
    if (ackResponsesEnabled) {
      scheduleAck(event.packet.senderNode, event.packet.sequence);
    } else {
      ++ackSuppressedCount;
    }
    return;
  }

  if (event.packet.messageType == kAckMessage &&
      event.packet.flags == nodeNumber()) {
    ++ackRxCount;
    uint32_t rttMs = 0;
    const bool matched = resolveProbe(event.packet.sequence, rttMs);
    if (matched) {
      lastMatchedAckMs = millis();
      ++rttSampleCount;
      rttSumMs += rttMs;
      if (rttSampleCount == 1 || rttMs < rttMinMs) {
        rttMinMs = rttMs;
      }
      if (rttMs > rttMaxMs) {
        rttMaxMs = rttMs;
      }
      if (sequenceBelongsToTest(event.packet.sequence)) {
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
    } else {
      ++unmatchedAckCount;
    }

    if (!quietMode) {
      Serial.print(F("{\"schema\":\""));
      Serial.print(kSchema);
      Serial.print(F("\",\"type\":\"espnow_ack_rx\",\"node_id\":\""));
      Serial.print(nodeId());
      Serial.print(F("\",\"source_mac\":\""));
      Serial.print(source);
      Serial.print(F("\",\"acknowledged_sequence\":"));
      Serial.print(event.packet.sequence);
      Serial.print(F(",\"matched\":"));
      Serial.print(matched ? F("true") : F("false"));
      Serial.print(F(",\"rtt_ms\":"));
      if (matched) {
        Serial.print(rttMs);
      } else {
        Serial.print(F("null"));
      }
      Serial.println(F("}"));
    }
  }
}

void emitTx(const TxEvent& event) {
  if (quietMode) {
    return;
  }
  char destination[18] = {};
  formatMac(event.destination, destination, sizeof(destination));
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"espnow_tx_result\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"destination_mac\":\""));
  Serial.print(destination);
  Serial.print(F("\",\"sequence\":"));
  Serial.print(event.sequence);
  Serial.print(F(",\"message_type\":"));
  Serial.print(event.messageType);
  Serial.print(F(",\"success\":"));
  Serial.print(event.status == 0 ? F("true") : F("false"));
  Serial.print(F(",\"status_code\":"));
  Serial.print(event.status);
  Serial.println(F("}"));
}

}  // namespace

namespace wlf_radio {

bool restoreChannel() {
  if (WiFi.status() == WL_CONNECTED) {
    return WiFi.channel() == radioChannel;
  }
#if defined(ESP8266)
  return wifi_set_channel(radioChannel);
#else
  return esp_wifi_set_channel(radioChannel, WIFI_SECOND_CHAN_NONE) == ESP_OK;
#endif
}

bool setChannel(uint8_t channel) {
  if (channel < 1 || channel > 13) {
    return false;
  }
  radioChannel = channel;
  if (!restoreChannel()) {
    return false;
  }
  if (radioActive) {
    removeBroadcastPeer();
    if (!addBroadcastPeer()) {
      radioActive = false;
      return false;
    }
  }
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"radio_control\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"channel\":"));
  Serial.print(radioChannel);
  Serial.println(F("}"));
  return true;
}

bool begin() {
  restoreChannel();

#if defined(ESP8266)
  if (esp_now_init() != 0) {
    return false;
  }
  esp_now_set_self_role(ESP_NOW_ROLE_COMBO);
  esp_now_register_recv_cb(onReceive);
  esp_now_register_send_cb(onSend);
  if (!addBroadcastPeer()) {
    return false;
  }
#else
  if (esp_now_init() != ESP_OK) {
    return false;
  }
  esp_now_register_recv_cb(onReceive);
  esp_now_register_send_cb(onSend);
  if (!addBroadcastPeer()) {
    return false;
  }
#endif

  radioActive = true;
  lastProbeMs = millis();
  return true;
}

bool sendProbe() {
  if (!radioActive) {
    return false;
  }

  ExperimentPacket packet = {};
  packet.magic = kPacketMagic;
  packet.version = kPacketVersion;
  packet.messageType = kProbeMessage;
  packet.senderNode = nodeNumber();
  packet.sequence = ++nextSequence;
  packet.senderUptimeMs = millis();
  packet.crc32 = calculateCrc32(reinterpret_cast<const uint8_t*>(&packet),
                                offsetof(ExperimentPacket, crc32));
  const int result = transmitPacket(packet);
  if (result == 0) {
    ++probeTxCount;
    rememberProbe(packet.sequence, packet.senderUptimeMs);
  } else {
    // A rejected local submission was never placed on air. Reuse the sequence
    // number so receivers do not count a driver-busy condition as RF loss.
    --nextSequence;
  }

  if (!quietMode) {
    Serial.print(F("{\"schema\":\""));
    Serial.print(kSchema);
    Serial.print(F("\",\"type\":\"espnow_tx_queued\",\"node_id\":\""));
    Serial.print(nodeId());
    Serial.print(F("\",\"sequence\":"));
    Serial.print(packet.sequence);
    Serial.print(F(",\"channel\":"));
    Serial.print(radioChannel);
    Serial.print(F(",\"accepted\":"));
    Serial.print(result == 0 ? F("true") : F("false"));
    Serial.print(F(",\"result_code\":"));
    Serial.print(static_cast<int>(result));
    Serial.println(F("}"));
  }
  return result == 0;
}

void setAutoSend(bool enabled) {
  autoSendEnabled = enabled;
  lastProbeMs = millis();
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"radio_control\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"auto_send\":"));
  Serial.print(autoSendEnabled ? F("true") : F("false"));
  Serial.println(F("}"));
}

void setQuiet(bool enabled) {
  quietMode = enabled;
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"radio_control\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"quiet\":"));
  Serial.print(quietMode ? F("true") : F("false"));
  Serial.println(F("}"));
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
  rxQueueDrops = 0;
  txQueueDrops = 0;
  ackScheduleDrops = 0;
  ackSuppressedCount = 0;
  ackScheduleWriteIndex = 0;
  ackScheduleReadIndex = 0;
  memset(probeHistory, 0, sizeof(probeHistory));
  memset(sequenceStates, 0, sizeof(sequenceStates));
  testSeries = {};

  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"stats_reset\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.println(F("\"}"));
}

void setAckDelay(uint32_t delayMs) {
  ackDelayMs = delayMs;
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"radio_control\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"ack_delay_ms\":"));
  Serial.print(ackDelayMs);
  Serial.println(F("}"));
}

void setAckResponsesEnabled(bool enabled) {
  ackResponsesEnabled = enabled;
  if (!enabled) {
    ackScheduleReadIndex = ackScheduleWriteIndex;
  }
  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"fault_control\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"fault\":\"espnow_ack_suppression\",\"active\":"));
  Serial.print(enabled ? F("false") : F("true"));
  Serial.print(F(",\"ack_responses_enabled\":"));
  Serial.print(enabled ? F("true") : F("false"));
  Serial.println(F("}"));
}

bool startTest(uint32_t packetCount, uint32_t intervalMs) {
  if (!radioActive || testSeries.sending || testSeries.finalizing ||
      packetCount == 0 || packetCount > 100000 || intervalMs < 10 ||
      intervalMs > 60000) {
    return false;
  }

  testSeries = {};
  testSeries.sending = true;
  testSeries.previousQuiet = quietMode;
  testSeries.requested = packetCount;
  testSeries.intervalMs = intervalMs;
  testSeries.startedAtMs = millis();
  testSeries.lastSendAtMs = testSeries.startedAtMs - intervalMs;
  autoSendEnabled = false;
  quietMode = true;

  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"test_started\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"requested\":"));
  Serial.print(packetCount);
  Serial.print(F(",\"interval_ms\":"));
  Serial.print(intervalMs);
  Serial.println(F("}"));
  return true;
}

void emitStatus() {
  uint32_t sequenceMissing = 0;
  uint32_t sequenceDuplicates = 0;
  uint32_t sequenceOutOfOrder = 0;
  for (uint8_t node = 1; node <= kNodeCount; ++node) {
    sequenceMissing += sequenceStates[node].missing;
    sequenceDuplicates += sequenceStates[node].duplicates;
    sequenceOutOfOrder += sequenceStates[node].outOfOrder;
  }

  Serial.print(F("{\"schema\":\""));
  Serial.print(kSchema);
  Serial.print(F("\",\"type\":\"radio_info\",\"node_id\":\""));
  Serial.print(nodeId());
  Serial.print(F("\",\"transport\":\"esp-now\",\"active\":"));
  Serial.print(radioActive ? F("true") : F("false"));
  Serial.print(F(",\"channel\":"));
  Serial.print(radioChannel);
  Serial.print(F(",\"packet_version\":"));
  Serial.print(kPacketVersion);
  Serial.print(F(",\"packet_size\":"));
  Serial.print(sizeof(ExperimentPacket));
  Serial.print(F(",\"broadcast\":true,\"rx_queue_drops\":"));
  Serial.print(rxQueueDrops);
  Serial.print(F(",\"tx_queue_drops\":"));
  Serial.print(txQueueDrops);
  Serial.print(F(",\"ack_schedule_drops\":"));
  Serial.print(ackScheduleDrops);
  Serial.print(F(",\"ack_delay_ms\":"));
  Serial.print(ackDelayMs);
  Serial.print(F(",\"ack_responses_enabled\":"));
  Serial.print(ackResponsesEnabled ? F("true") : F("false"));
  Serial.print(F(",\"ack_suppressed\":"));
  Serial.print(ackSuppressedCount);
  Serial.print(F(",\"probe_tx\":"));
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
  Serial.print(sequenceMissing);
  Serial.print(F(",\"sequence_duplicates\":"));
  Serial.print(sequenceDuplicates);
  Serial.print(F(",\"sequence_out_of_order\":"));
  Serial.print(sequenceOutOfOrder);
  Serial.print(F(",\"auto_send\":"));
  Serial.print(autoSendEnabled ? F("true") : F("false"));
  Serial.print(F(",\"quiet\":"));
  Serial.print(quietMode ? F("true") : F("false"));
  Serial.print(F(",\"test_active\":"));
  Serial.print((testSeries.sending || testSeries.finalizing) ? F("true")
                                                            : F("false"));
  Serial.print(F(",\"rtt_samples\":"));
  Serial.print(rttSampleCount);
  Serial.print(F(",\"rtt_min_ms\":"));
  if (rttSampleCount > 0) {
    Serial.print(rttMinMs);
  } else {
    Serial.print(F("null"));
  }
  Serial.print(F(",\"rtt_avg_ms\":"));
  if (rttSampleCount > 0) {
    Serial.print(static_cast<uint32_t>(rttSumMs / rttSampleCount));
  } else {
    Serial.print(F("null"));
  }
  Serial.print(F(",\"rtt_max_ms\":"));
  if (rttSampleCount > 0) {
    Serial.print(rttMaxMs);
  } else {
    Serial.print(F("null"));
  }
  Serial.println(F("}"));
}

Metrics metrics() {
  Metrics snapshot = {};
  snapshot.active = radioActive;
  snapshot.testActive = testSeries.sending || testSeries.finalizing;
  snapshot.probeTx = probeTxCount;
  snapshot.matchedAckRx = rttSampleCount;
  snapshot.lastMatchedAckMs = lastMatchedAckMs;
  return snapshot;
}

void poll() {
  RxEvent rxEvent = {};
  while (popRx(rxEvent)) {
    emitRx(rxEvent);
  }

  processPendingAcks();

  TxEvent txEvent = {};
  while (popTx(txEvent)) {
    emitTx(txEvent);
  }

  const uint32_t now = millis();
  if (testSeries.sending &&
      now - testSeries.lastSendAtMs >= testSeries.intervalMs) {
    testSeries.lastSendAtMs = now;
    const bool accepted = sendProbe();
    if (accepted) {
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
      Serial.print(F("\",\"type\":\"test_progress\",\"node_id\":\""));
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
    Serial.print(F("\",\"type\":\"test_complete\",\"node_id\":\""));
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
    if (testSeries.rttSamples > 0) {
      Serial.print(testSeries.rttMinMs);
    } else {
      Serial.print(F("null"));
    }
    Serial.print(F(",\"rtt_avg_ms\":"));
    if (testSeries.rttSamples > 0) {
      Serial.print(static_cast<uint32_t>(testSeries.rttSumMs /
                                         testSeries.rttSamples));
    } else {
      Serial.print(F("null"));
    }
    Serial.print(F(",\"rtt_max_ms\":"));
    if (testSeries.rttSamples > 0) {
      Serial.print(testSeries.rttMaxMs);
    } else {
      Serial.print(F("null"));
    }
    Serial.println(F("}"));
    quietMode = testSeries.previousQuiet;
  }

  if (radioActive && autoSendEnabled && !testSeries.sending &&
      !testSeries.finalizing && now - lastProbeMs >= kProbePeriodMs) {
    lastProbeMs = now;
    sendProbe();
  }
}

}  // namespace wlf_radio
