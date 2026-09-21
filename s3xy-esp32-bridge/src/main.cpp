#include <Arduino.h>
#include <BLE2902.h>
#include <BLEClient.h>
#include <BLEDevice.h>
#include <BLESecurity.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <esp_gap_ble_api.h>

// S3XY BLE UUIDs confirmed by the public virtual-button implementation.
static const char* SERVICE_UUID     = "00003d46-87d2-479e-7e45-8551415a6de1";
static const char* CHAR_NOTIFY_UUID = "00003d50-87d2-479e-7e45-8551415a6de1";
static const char* CHAR_ID_UUID     = "00003d49-87d2-479e-7e45-8551415a6de1";

static constexpr uint32_t REPEAT_INTERVAL_MS = 120;
static constexpr uint32_t MAX_HOLD_MS = 5000;
static constexpr uint32_t FIRST_SCAN_DELAY_MS = 60000;
static constexpr uint32_t RESCAN_MS = 7000;
static constexpr uint32_t HANDSHAKE_RETRY_MS = 1000;
static constexpr int BOOT_BUTTON = 0;
static constexpr int STATUS_LED = 2;

static BLEServer* gServer = nullptr;
static BLECharacteristic* gCommanderNotify = nullptr;
static BLECharacteristic* gCommanderId = nullptr;
static bool gCommanderConnected = false;
static bool gCommanderSubscribed = false;
static bool gPendingCommanderInitReply = false;

static BLEClient* gRealClient = nullptr;
static BLERemoteCharacteristic* gRealNotify = nullptr;
static BLERemoteCharacteristic* gRealId = nullptr;
static BLEAdvertisedDevice* gFoundReal = nullptr;
static bool gRealConnected = false;
static bool gRealReady = false;
static bool gScanning = false;
static uint32_t gNextScanAt = 0;
static uint32_t gLastHandshakeAt = 0;

static bool gHoldDown = false;
static uint32_t gHoldStartedAt = 0;
static uint32_t gNextPulseAt = 0;

static uint8_t gVirtualId[10] = {'S','A','B','R','I','N','A','S','N','S'};

static void startCommanderAdvertising();
static void connectFoundRealButton();
static void sendCommanderSingle();
static void stopHold(const char* why);
static void tryRealHandshake();

static bool bytesEqual(const uint8_t* data, size_t len, std::initializer_list<uint8_t> expected) {
  if (len != expected.size()) return false;
  size_t i = 0;
  for (uint8_t v : expected) {
    if (data[i++] != v) return false;
  }
  return true;
}

static String hexBytes(const uint8_t* data, size_t len) {
  String out;
  for (size_t i = 0; i < len; ++i) {
    if (i) out += ' ';
    char b[4];
    snprintf(b, sizeof(b), "%02X", data[i]);
    out += b;
  }
  return out;
}

static bool commanderReady() {
  return gCommanderConnected && gCommanderSubscribed && gCommanderNotify;
}

static void commanderNotify(const uint8_t* data, size_t len) {
  if (!commanderReady()) return;
  gCommanderNotify->setValue((uint8_t*)data, len);
  gCommanderNotify->notify();
}

static void flushCommanderInitReply() {
  if (!gPendingCommanderInitReply || !commanderReady()) return;
  const uint8_t reply[] = {0xC7, 0x00, 0x01};
  commanderNotify(reply, sizeof(reply));
  gPendingCommanderInitReply = false;
  Serial.println("[CMD] queued B6 reply sent: C7 00 01");
}

class SecurityCallbacks final : public BLESecurityCallbacks {
 public:
  uint32_t onPassKeyRequest() override { return 0; }
  void onPassKeyNotify(uint32_t) override {}
  bool onSecurityRequest() override {
    Serial.println("[SEC] security request accepted");
    return true;
  }
  bool onConfirmPIN(uint32_t) override { return true; }
  void onAuthenticationComplete(esp_ble_auth_cmpl_t cmpl) override {
    char addr[18];
    snprintf(addr, sizeof(addr), "%02X:%02X:%02X:%02X:%02X:%02X",
             cmpl.bd_addr[0], cmpl.bd_addr[1], cmpl.bd_addr[2],
             cmpl.bd_addr[3], cmpl.bd_addr[4], cmpl.bd_addr[5]);
    Serial.printf("[SEC] %s peer=%s addrType=%d\n", cmpl.success ? "bonded" : "bond failed", addr, cmpl.addr_type);
    if (cmpl.success && gRealConnected) {
      gLastHandshakeAt = 0;
    }
  }
};

class CommanderServerCallbacks final : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    gCommanderConnected = true;
    Serial.println("[CMD] Commander connected");
  }

  void onDisconnect(BLEServer*) override {
    gCommanderConnected = false;
    gCommanderSubscribed = false;
    gPendingCommanderInitReply = false;
    stopHold("Commander disconnected");
    Serial.println("[CMD] Commander disconnected; advertising restarted");
    delay(80);
    startCommanderAdvertising();
  }
};

class CommanderCccdCallbacks final : public BLEDescriptorCallbacks {
  void onWrite(BLEDescriptor* d) override {
    uint8_t* value = d->getValue();
    size_t len = d->getLength();
    gCommanderSubscribed = len >= 1 && (value[0] & 0x01);
    Serial.printf("[CMD] notifications %s\n", gCommanderSubscribed ? "enabled" : "disabled");
    if (gCommanderSubscribed) {
      flushCommanderInitReply();
      const uint8_t poke = 0x00;
      commanderNotify(&poke, 1);
      // Once Commander is ready, immediately begin looking for the physical button.
      gNextScanAt = 0;
    } else {
      stopHold("Commander notifications disabled");
    }
  }
};

class CommanderIdCallbacks final : public BLECharacteristicCallbacks {
  void onRead(BLECharacteristic*) override {
    Serial.println("[CMD] ID read");
  }

  void onWrite(BLECharacteristic* c) override {
    uint8_t* data = c->getData();
    size_t len = c->getLength();
    Serial.printf("[CMD] ID write: %s\n", hexBytes(data, len).c_str());

    if (bytesEqual(data, len, {0xB6})) {
      const uint8_t reply[] = {0xC7, 0x00, 0x01};
      if (commanderReady()) {
        commanderNotify(reply, sizeof(reply));
        Serial.println("[CMD] B6 -> C7 00 01");
      } else {
        gPendingCommanderInitReply = true;
        Serial.println("[CMD] B6 reply queued until CCCD subscribe");
      }
    } else if (bytesEqual(data, len, {0xA1})) {
      Serial.println("[CMD] Commander requested disconnect");
      if (gServer) gServer->disconnect(0);
    } else if (len == 4 && data[0] == 0xA4) {
      const uint8_t reply[] = {0xA4, 0x00, data[1], data[2]};
      if (commanderReady()) commanderNotify(reply, sizeof(reply));
      Serial.println("[CMD] rename request acknowledged");
    }
  }
};

class RealClientCallbacks final : public BLEClientCallbacks {
  void onConnect(BLEClient*) override {
    gRealConnected = true;
    gRealReady = false;
    Serial.println("[BTN] physical S3XY Button connected");
  }

  void onDisconnect(BLEClient*) override {
    gRealConnected = false;
    gRealReady = false;
    gRealNotify = nullptr;
    gRealId = nullptr;
    stopHold("physical button disconnected");
    gNextScanAt = millis() + RESCAN_MS;
    Serial.println("[BTN] physical S3XY Button disconnected");
  }
};

static void realNotifyCallback(BLERemoteCharacteristic*, uint8_t* data, size_t len, bool) {
  Serial.printf("[BTN] RX %s\n", hexBytes(data, len).c_str());

  if (bytesEqual(data, len, {0xC7, 0x00, 0x01})) {
    gRealReady = true;
    Serial.println("[BTN] physical button handshake ready");
    return;
  }

  if (bytesEqual(data, len, {0x01})) {
    if (!gHoldDown) {
      gHoldDown = true;
      gHoldStartedAt = millis();
      gNextPulseAt = 0;
      Serial.println("[BRIDGE] HOLD START");
    }
    return;
  }

  if (bytesEqual(data, len, {0x00})) {
    if (gHoldDown) stopHold("button released");
    return;
  }
}

class RealScanCallbacks final : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertised) override {
    if (!advertised.haveServiceUUID() ||
        !advertised.isAdvertisingService(BLEUUID(SERVICE_UUID))) return;

    // Our own local advertising is not reported to the local scanner. Any peer
    // advertising the S3XY service is therefore a candidate real button.
    String name = advertised.haveName() ? advertised.getName().c_str() : "";
    Serial.printf("[SCAN] S3XY candidate %s name=%s\n",
                  advertised.getAddress().toString().c_str(), name.c_str());

    if (gFoundReal) {
      delete gFoundReal;
      gFoundReal = nullptr;
    }
    gFoundReal = new BLEAdvertisedDevice(advertised);
    BLEDevice::getScan()->stop();
  }
};

static SecurityCallbacks gSecurityCallbacks;
static CommanderServerCallbacks gCommanderServerCallbacks;
static CommanderCccdCallbacks gCommanderCccdCallbacks;
static CommanderIdCallbacks gCommanderIdCallbacks;
static RealClientCallbacks gRealClientCallbacks;
static RealScanCallbacks gRealScanCallbacks;

static void setupSecurity() {
  BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
  BLEDevice::setSecurityCallbacks(&gSecurityCallbacks);

  auto* security = new BLESecurity();
  security->setCapability(ESP_IO_CAP_NONE);
  security->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
  security->setKeySize(16);
  security->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  security->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
}

static void setupCommanderServer() {
  gServer = BLEDevice::createServer();
  gServer->setCallbacks(&gCommanderServerCallbacks);

  BLEService* service = gServer->createService(SERVICE_UUID);

  gCommanderNotify = service->createCharacteristic(
      CHAR_NOTIFY_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  auto* cccd = new BLE2902();
  cccd->setNotifications(false);
  cccd->setCallbacks(&gCommanderCccdCallbacks);
  gCommanderNotify->addDescriptor(cccd);
  gCommanderNotify->setValue((uint8_t*)"\x00", 1);

  gCommanderId = service->createCharacteristic(
      CHAR_ID_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE);
  gCommanderId->setAccessPermissions(
      ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED);
  gCommanderId->setValue(gVirtualId, sizeof(gVirtualId));
  gCommanderId->setCallbacks(&gCommanderIdCallbacks);

  service->start();
  startCommanderAdvertising();
}

static void startCommanderAdvertising() {
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  BLEAdvertisementData advData;
  BLEAdvertisementData scanResp;

  advData.setAppearance(0x0000);
  advData.setFlags(0x06);
  advData.setName("ENH_BTN");
  scanResp.setCompleteServices(BLEUUID(SERVICE_UUID));

  adv->setAdvertisementData(advData);
  adv->setScanResponseData(scanResp);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("[CMD] advertising as ENH_BTN");
}

static void setupRealClient() {
  gRealClient = BLEDevice::createClient();
  gRealClient->setClientCallbacks(&gRealClientCallbacks);

  BLEScan* scan = BLEDevice::getScan();
  scan->setAdvertisedDeviceCallbacks(&gRealScanCallbacks, true);
  scan->setActiveScan(true);
  scan->setInterval(120);
  scan->setWindow(80);
}

static void tryRealHandshake() {
  if (!gRealConnected || gRealReady || !gRealId) return;
  uint32_t now = millis();
  if (gLastHandshakeAt && now - gLastHandshakeAt < HANDSHAKE_RETRY_MS) return;
  gLastHandshakeAt = now;
  uint8_t b6 = 0xB6;
  Serial.println("[BTN] TX B6 handshake");
  gRealId->writeValue(&b6, 1, true);
}

static bool prepareRealButtonConnection() {
  if (!gRealClient || !gFoundReal) return false;

  BLEAdvertisedDevice* target = gFoundReal;
  gFoundReal = nullptr;

  Serial.printf("[BTN] connecting to %s\n", target->getAddress().toString().c_str());
  bool ok = gRealClient->connect(target);
  BLEAddress addr = target->getAddress();
  delete target;

  if (!ok) {
    Serial.println("[BTN] connect failed");
    return false;
  }

  BLERemoteService* service = gRealClient->getService(BLEUUID(SERVICE_UUID));
  if (!service) {
    Serial.println("[BTN] service 3D46 missing");
    gRealClient->disconnect();
    return false;
  }

  gRealNotify = service->getCharacteristic(BLEUUID(CHAR_NOTIFY_UUID));
  gRealId = service->getCharacteristic(BLEUUID(CHAR_ID_UUID));
  if (!gRealNotify || !gRealId) {
    Serial.println("[BTN] required characteristics missing");
    gRealClient->disconnect();
    return false;
  }

  if (gRealNotify->canNotify()) {
    if (!gRealNotify->registerForNotify(realNotifyCallback)) {
      Serial.println("[BTN] notify subscription failed");
      gRealClient->disconnect();
      return false;
    }
  } else {
    Serial.println("[BTN] notify characteristic is not notifiable");
    gRealClient->disconnect();
    return false;
  }

  // Force Secure Connections/Bonding with the physical button. The encrypted
  // 3D49 write below is retried until the C7 handshake acknowledgement arrives.
  esp_ble_set_encryption(addr.getNative(), ESP_BLE_SEC_ENCRYPT_NO_MITM);
  gLastHandshakeAt = 0;
  delay(300);
  tryRealHandshake();
  return true;
}

static void scanForRealButton() {
  if (gScanning || gRealConnected || gFoundReal) return;
  gScanning = true;
  Serial.println("[SCAN] looking for physical S3XY Button for 5s; hold/wake the button now");
  BLEScan* scan = BLEDevice::getScan();
  scan->clearResults();
  scan->start(5, false);
  gScanning = false;

  if (gFoundReal) {
    prepareRealButtonConnection();
  } else {
    Serial.println("[SCAN] no physical button found");
  }
}

static void sendCommanderSingle() {
  if (!commanderReady()) {
    Serial.println("[BRIDGE] DROP pulse: Commander not ready");
    return;
  }

  const uint8_t p1[] = {0x01};
  const uint8_t p0[] = {0x00};
  const uint8_t pC1[] = {0xC1, 0x01};

  commanderNotify(p1, sizeof(p1));
  delay(5);
  commanderNotify(p0, sizeof(p0));
  delay(5);
  commanderNotify(pC1, sizeof(pC1));
  delay(5);
  commanderNotify(p0, sizeof(p0));
  delay(5);
  Serial.println("[BRIDGE] TX single pulse");
}

static void stopHold(const char* why) {
  if (!gHoldDown) return;
  gHoldDown = false;
  Serial.printf("[BRIDGE] HOLD STOP: %s\n", why);
}

static void processHold() {
  if (!gHoldDown) return;
  uint32_t now = millis();

  if (now - gHoldStartedAt >= MAX_HOLD_MS) {
    stopHold("5s safety limit");
    return;
  }

  if (gNextPulseAt == 0 || (int32_t)(now - gNextPulseAt) >= 0) {
    sendCommanderSingle();
    gNextPulseAt = millis() + REPEAT_INTERVAL_MS;
  }
}

static void processSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "status") {
    Serial.printf("[STATUS] Commander=%s notify=%s Real=%s ready=%s Hold=%s\n",
                  gCommanderConnected ? "connected" : "off",
                  gCommanderSubscribed ? "on" : "off",
                  gRealConnected ? "connected" : "off",
                  gRealReady ? "yes" : "no",
                  gHoldDown ? "down" : "up");
  } else if (cmd == "scan") {
    gNextScanAt = 0;
    Serial.println("[CLI] scan requested");
  } else if (cmd == "reset") {
    Serial.println("[CLI] deleting all BLE bonds and rebooting");
    BLEDevice::deleteAllBonds();
    delay(300);
    ESP.restart();
  }
}

static void updateLed() {
  static uint32_t last = 0;
  static bool state = false;
  uint32_t now = millis();

  if (commanderReady() && gRealReady) {
    digitalWrite(STATUS_LED, HIGH);
    return;
  }

  uint32_t interval = gCommanderConnected ? 250 : 700;
  if (now - last >= interval) {
    last = now;
    state = !state;
    digitalWrite(STATUS_LED, state ? HIGH : LOW);
  }
}

void setup() {
  pinMode(BOOT_BUTTON, INPUT_PULLUP);
  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  Serial.begin(115200);
  delay(400);
  Serial.println();
  Serial.println("S3XY ESP32 Hardware Bridge v1.0");

  BLEDevice::init("ENH_BTN");
  setupSecurity();

  if (digitalRead(BOOT_BUTTON) == LOW) {
    Serial.println("[BOOT] BOOT held: clearing all BLE bonds");
    BLEDevice::deleteAllBonds();
    delay(500);
  }

  setupCommanderServer();
  setupRealClient();

  gNextScanAt = millis() + FIRST_SCAN_DELAY_MS;
  Serial.println("[SETUP] 1) Add this ENH_BTN to Commander first.");
  Serial.println("[SETUP] 2) Then wake/hold the physical S3XY Button; it will be scanned automatically.");
  Serial.println("[SETUP] Hold BOOT while powering on to erase bonds.");
}

void loop() {
  processSerial();
  processHold();
  tryRealHandshake();
  updateLed();

  uint32_t now = millis();

  // Prefer pairing Commander first. As soon as Commander subscribes, scan now.
  // If Commander is not paired, scanning starts after 60s anyway.
  bool scanAllowed = commanderReady() || now >= FIRST_SCAN_DELAY_MS;
  if (scanAllowed && !gRealConnected && !gScanning &&
      (gNextScanAt == 0 || (int32_t)(now - gNextScanAt) >= 0)) {
    gNextScanAt = now + RESCAN_MS;
    scanForRealButton();
  }

  delay(5);
}
