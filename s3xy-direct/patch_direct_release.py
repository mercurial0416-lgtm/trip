from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# Version bump after the existing 0.7.0 Direct Lab patch.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 12','versionCode 15')
s=s.replace("versionName '0.7.0-commander-direct-lab'","versionName '0.7.3-direct-connect'")
if 'versionCode 14' not in s or "versionName '0.7.2-direct-connect'" not in s:
    raise SystemExit('0.7.3 version bump failed')
p.write_text(s)

# MainActivity: shared Direct manager, automatic Commander selection, no BLE device clutter.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
s=s.replace('directProbe=new CommanderDirectProbe(this,this);',
            'directProbe=CommanderDirectProbe.get(this);directProbe.attach(this);')
s=s.replace('if(directProbe!=null)directProbe.close();',
            'if(directProbe!=null)directProbe.detach(this);')
s=s.replace('directScanButton=primary("Commander BLE 검색 (12초)")',
            'directScanButton=primary("Commander 자동 연결")')
s=s.replace('directScanButton.setText("Commander BLE 검색 (12초)")',
            'directScanButton.setText("Commander 자동 연결")')
s=s.replace('if(directScanButton!=null)directScanButton.setText("Commander 검색 중…");\n        directProbe.startScan();',
            'engine.stopCommander();\n        if(directScanButton!=null)directScanButton.setText("Commander 자동 연결 중…");\n        directProbe.startAuto();')
s=s.replace('b.append("App: 0.7.0-commander-direct-lab\\n\\n");',
            'b.append("App: 0.7.3-direct-connect\\n\\n");')
needle='''        engine.ensureRunning();
        refreshProfiles();
'''
repl='''        engine.ensureRunning();
        refreshProfiles();
        main.postDelayed(()->{
            if(hasScan()&&hasConnect()){
                engine.stopCommander();
                if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();
            }
        },700);
'''
if needle in s:
    s=s.replace(needle,repl,1)
s=s.replace('if(r==REQ_PERMS){engine.ensureRunning();}',
            'if(r==REQ_PERMS){engine.ensureRunning();if(hasScan()&&hasConnect()){engine.stopCommander();if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();}}')
p.write_text(s)

# BridgeEngine: Direct mode is default; do not auto-start the legacy virtual ENH_BTN.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()
s=s.replace('if(prefs.getBoolean("auto_virtual",true)) startCommander();',
            'if(!prefs.getBoolean("direct_commander_mode",true) && prefs.getBoolean("auto_virtual",true)) startCommander();')
s=s.replace('if(prefs.getBoolean("auto_virtual",true))startCommander();',
            'if(!prefs.getBoolean("direct_commander_mode",true) && prefs.getBoolean("auto_virtual",true))startCommander();')
p.write_text(s)

# Foreground service owns the Direct manager too, so the Commander link is not tied to the Activity.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeForegroundService.java'
s=p.read_text()
if 'private CommanderDirectProbe directProbe;' not in s:
    s=s.replace('    private BridgeEngine engine;',
                '    private BridgeEngine engine;\n    private CommanderDirectProbe directProbe;')
if 'directProbe=CommanderDirectProbe.get(this);' not in s:
    s=s.replace('        engine=BridgeEngine.get(this);\n        engine.attach(this);',
                '        engine=BridgeEngine.get(this);\n        directProbe=CommanderDirectProbe.get(this);\n        engine.attach(this);')
if 'syncDirect();' not in s:
    s=s.replace('        engine.ensureRunning();\n    }',
                '        engine.ensureRunning();\n        syncDirect();\n    }',1)
    s=s.replace('        engine.ensureRunning();\n        return START_STICKY;',
                '        engine.ensureRunning();\n        syncDirect();\n        return START_STICKY;')
    s=s.replace('    @Override public void onVehicleTrigger(boolean active,String status){engine.setDriveSessionActive(active,status);}',
                '    @Override public void onVehicleTrigger(boolean active,String status){engine.setDriveSessionActive(active,status);syncDirect();}')
    insert='''    private void syncDirect(){
        if(directProbe==null)directProbe=CommanderDirectProbe.get(this);
        engine.stopCommander();
        if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();
        else directProbe.disconnect();
    }

'''
    s=s.replace('    @Override public void onSnapshot(BridgeEngine.Snapshot s){',
                insert+'    @Override public void onSnapshot(BridgeEngine.Snapshot s){')
p.write_text(s)

# Ensure service re-syncs Direct mode on every start command, including refresh intents.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeForegroundService.java'
s=p.read_text()
s=s.replace('''        if(intent!=null&&ACTION_REFRESH_TRIGGER.equals(intent.getAction()))vehicleTrigger.refresh();
        else engine.ensureRunning();
        return START_STICKY;
''','''        if(intent!=null&&ACTION_REFRESH_TRIGGER.equals(intent.getAction()))vehicleTrigger.refresh();
        else engine.ensureRunning();
        syncDirect();
        return START_STICKY;
''')
p.write_text(s)

print('v0.7.3 Direct Connect release patch applied')
