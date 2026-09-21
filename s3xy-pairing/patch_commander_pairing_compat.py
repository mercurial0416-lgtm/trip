from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.6.5: Commander pairing compatibility / handshake hardening.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 10','versionCode 11')
s=s.replace("versionName '0.6.4-cache-bust'","versionName '0.6.5-pairing-compat'")
if 'versionCode 11' not in s or "versionName '0.6.5-pairing-compat'" not in s:
    raise SystemExit('0.6.5 version bump source not found')
p.write_text(s)

# Keep vehicle gating out of the way for the full 30s pairing window plus margin.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()
s=s.replace('main.postDelayed(clearPairingOverride,25000);','main.postDelayed(clearPairingOverride,40000);')
s=s.replace('vehicle gate bypass 25s','vehicle gate bypass 40s')
if 'clearPairingOverride,40000' not in s:
    raise SystemExit('pairing override patch not applied')
p.write_text(s)

# UI now reflects the 30 second Commander pairing window.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
s=s.replace('가상 버튼 페어링 시작 (20초)','가상 버튼 페어링 시작 (30초)')
p.write_text(s)

print('v0.6.5 Commander pairing compatibility patch applied')
