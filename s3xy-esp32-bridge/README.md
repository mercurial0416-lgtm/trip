# S3XY ESP32 Hardware Bridge

This firmware removes Android from the BLE data path:

```
Physical S3XY Button  <--BLE central-->  ESP32  <--BLE peripheral-->  Commander
```

The Commander-facing implementation follows the public MIT-licensed
`Beat-YT/s3xy-virtual-button` BLE layout and security settings:
Secure Connections + bonding, 16-byte key, ENC/Identity key exchange,
ENH_BTN advertising, service 3D46, notify 3D50 and encrypted ID 3D49.

The ESP32 also connects to a physical S3XY Button, subscribes to 3D50,
bonds/encrypts the link and sends B6 on 3D49 until C7 00 01 is received.

Default bridge behavior mirrors the existing Android bridge:
- physical DOWN: start immediately
- every 120 ms while held: emit a virtual single click to Commander
- physical UP: stop immediately
- hard stop at 5 seconds if UP is missed

## Hardware target

Use an ESP32-WROOM-32 / ESP32 DevKit V1 compatible board.
The first build intentionally targets classic ESP32 because the reference
virtual-button implementation is verified on `esp32dev`.

## First pairing

1. Flash `S3XY-ESP32-Bridge-merged.bin` at address `0x0`.
2. Power the ESP32 in the car.
3. In the official S3XY app, add a new S3XY Button to Commander. The ESP32
   advertises as `ENH_BTN`.
4. After Commander has connected/subscribed, wake or hold the physical S3XY
   Button. The ESP32 scans automatically and bonds to it.
5. Assign the newly added virtual button's Single action in the official app
   to the action you want (the current bridge emits repeated Single while held).

For the cleanest setup, remove the physical button from Commander first so
Commander cannot grab it directly while the ESP32 is trying to bond to it.

## Status LED

- solid: Commander and physical button are both ready
- fast blink: Commander connected but bridge not fully ready
- slow blink: waiting for Commander

## Recovery

Hold the board's BOOT button while powering it on to clear all BLE bonds.

Serial console at 115200 supports:
- `status`
- `scan`
- `reset`

## Attribution

Commander-facing BLE behavior is derived from the MIT-licensed project:
https://github.com/Beat-YT/s3xy-virtual-button

See `THIRD_PARTY_NOTICES.md`.
