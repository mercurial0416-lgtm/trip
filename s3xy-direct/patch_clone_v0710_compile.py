from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# Repair v0.7.10 diagnostics without changing vehicle-control behavior.
p=root/'app/src/main/java/com/openai/s3xybridge/RealButtonClient.java'
s=p.read_text()
s=s.replace('" start="+started+" bond="+safeBond(device)', '" start="+started+" bond="+safeBondLabel(device)')
s=s.replace('private String safeBond(BluetoothDevice d){', 'private String safeBondLabel(BluetoothDevice d){')
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
s=s.replace('        engine.log("CLONE stage=physical scan start");\n        startButtonScan(true);', '        startButtonScan(true);')
p.write_text(s)

print('v0.7.10 compile hotfix applied')
