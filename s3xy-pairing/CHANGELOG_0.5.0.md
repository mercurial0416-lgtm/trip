# S3XY Bridge 0.5.0-pairing

- Virtual ENH_BTN 20s pairing mode added.
- BLE advertising restarts for pairing.
- Commander LE bonding is proactively requested with createBond().
- Bond state changes are logged.
- B6 -> C7 00 01 initialization handshake retained.
- CCCD subscription state is logged.
- UI now has "가상 버튼 페어링 시작 (20초)".
- Commander status text now means Virtual ENH_BTN <-> Commander, not official app <-> Commander.
- Protocol self-test: 8/8 PASS.
- Release build: PASS.
- APK signature verification: v2=true, v3=true.
- Signing key backed up privately in ChatGPT Library under /S3XY Bridge/Signing.
