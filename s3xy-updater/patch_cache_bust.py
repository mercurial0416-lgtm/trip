from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.6.4: make update checks immune to stale raw.githubusercontent.com CDN entries.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 9','versionCode 10')
s=s.replace("versionName '0.6.3-resilience'","versionName '0.6.4-cache-bust'")
if 'versionCode 10' not in s or "versionName '0.6.4-cache-bust'" not in s:
    raise SystemExit('0.6.4 version bump source not found')
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/UpdateManager.java'
s=p.read_text()
old='c=(HttpURLConnection)new URL(MANIFEST_URL).openConnection();'
new='c=(HttpURLConnection)new URL(MANIFEST_URL+"?cb="+System.currentTimeMillis()).openConnection();'
if old not in s:
    raise SystemExit('manifest connection source not found')
s=s.replace(old,new,1)

old='c.setConnectTimeout(7000);c.setReadTimeout(7000);c.setUseCaches(false);'
new='c.setConnectTimeout(7000);c.setReadTimeout(7000);c.setUseCaches(false);c.setRequestProperty("Cache-Control","no-cache, no-store");c.setRequestProperty("Pragma","no-cache");'
if old not in s:
    raise SystemExit('manifest cache header source not found')
s=s.replace(old,new,1)
p.write_text(s)

print('v0.6.4 updater cache-bust patch applied')
