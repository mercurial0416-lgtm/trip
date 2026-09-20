from pathlib import Path
root=Path('/tmp/src/S3XYButtonBridgeAndroid')
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 7','versionCode 8')
s=s.replace("versionName '0.6.1-pairing-hotfix'","versionName '0.6.2-no-bt-rename'")
p.write_text(s)
