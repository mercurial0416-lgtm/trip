from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 18','versionCode 19')
s=s.replace("versionName '0.7.6-fast-highbeam'","versionName '0.7.7-fast-highbeam-flash'")
if 'versionCode 19' not in s or "versionName '0.7.7-fast-highbeam-flash'" not in s:
    raise SystemExit('v0.7.7 version bump failed')
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
repls={
    'SINGLE = High Beam 지정 완료':'SINGLE = High Beam Flash 지정 완료',
    'SINGLE = High Beam 지정 후':'SINGLE = High Beam Flash 지정 후',
    'SINGLE을 반드시 High Beam으로 지정하세요.':'SINGLE을 반드시 High Beam Flash로 지정하세요. High Beam은 선택하지 마세요.',
    'SINGLE을 High Beam으로 등록하면':'SINGLE을 High Beam Flash로 등록하면',
    'Commander에 등록한 가상 버튼의 SINGLE을 반복 전송':'Commander에 High Beam Flash로 등록한 가상 버튼 SINGLE을 반복 전송',
    '먼저 SINGLE을 High Beam으로 지정하고 설정 완료를 누르세요.':'먼저 SINGLE을 High Beam Flash로 지정하고 설정 완료를 누르세요.',
    'Buttons → 새 버튼 추가 → SINGLE을 High Beam으로 지정하세요.':'Buttons → 새 버튼 추가 → SINGLE을 High Beam Flash로 지정하세요.',
    'App: 0.7.6-fast-highbeam':'App: 0.7.7-fast-highbeam-flash',
}
for a,b in repls.items():
    s=s.replace(a,b)
p.write_text(s)

print('v0.7.7 high-beam action corrected to High Beam Flash')
