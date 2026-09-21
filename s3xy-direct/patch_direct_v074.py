from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.7.4: real-device identity repair + manual setup bypass for the vehicle gate.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 15','versionCode 16')
s=s.replace("versionName '0.7.3-direct-connect'","versionName '0.7.4-direct-connect'")
if 'versionCode 16' not in s or "versionName '0.7.4-direct-connect'" not in s:
    raise SystemExit('v0.7.4 version bump failed')
p.write_text(s)

# Commander identity: clear any legacy wrong cached address once, exclude the known physical button,
# prefer the user's known Commander identity, and validate the Commander service after connection.
p=root/'app/src/main/java/com/openai/s3xybridge/CommanderDirectProbe.java'
s=p.read_text()
s=s.replace(
'    private static final UUID COMMANDER_SERVICE=UUID.fromString("5857a678-87c6-11eb-8dcd-0242ac130003");',
'''    private static final UUID COMMANDER_SERVICE=UUID.fromString("5857a678-87c6-11eb-8dcd-0242ac130003");
    private static final String KNOWN_COMMANDER_ADDR="C0:CD:D6:5F:40:66";
    private static final String KNOWN_BUTTON_ADDR="E1:5D:0C:C1:D7:5A";'''
)
s=s.replace(
'        adapter=manager==null?null:manager.getAdapter();\n        log("DIRECT probe created");',
'''        adapter=manager==null?null:manager.getAdapter();
        if(!prefs.getBoolean("direct_identity_fix_v074",false)){
            prefs.edit().remove("direct_commander_addr").putBoolean("direct_identity_fix_v074",true).apply();
            log("DIRECT cleared legacy cached Commander identity");
        }
        log("DIRECT probe created");'''
)
old='''        String saved=prefs.getString("direct_commander_addr","");
        boolean savedMatch=!saved.isEmpty()&&saved.equalsIgnoreCase(addr);
        boolean looksButton=lower.contains("enh_btn")||lower.contains("button")||lower.contains("s3xy btn");
        boolean mayAuto=savedMatch||(saved.isEmpty()&&!looksButton);
        if(!connected&&!autoConnecting&&r.getRssi()>-82&&mayAuto){
            autoConnecting=true;
            log("DIRECT auto-select Commander -> "+name+" "+addr+(savedMatch?" [saved]":" [first-use]"));
            main.post(()->connectInternal(d));
        }else if(looksButton){
            log("DIRECT skip physical-button candidate -> "+name+" "+addr);
        }else if(!saved.isEmpty()&&!savedMatch){
            log("DIRECT skip non-saved candidate -> "+name+" "+addr);
        }
'''
new='''        String saved=prefs.getString("direct_commander_addr","");
        boolean knownCommander=KNOWN_COMMANDER_ADDR.equalsIgnoreCase(addr);
        boolean knownButton=KNOWN_BUTTON_ADDR.equalsIgnoreCase(addr);
        boolean savedMatch=!saved.isEmpty()&&saved.equalsIgnoreCase(addr);
        boolean looksButton=knownButton||lower.contains("enh_btn")||lower.contains("button")||lower.contains("s3xy btn");
        if(savedMatch&&looksButton){
            prefs.edit().remove("direct_commander_addr").apply();
            saved="";savedMatch=false;
            log("DIRECT removed stale physical-button address from Commander cache");
        }
        boolean commanderIdentity=knownCommander||commanderUuid||(!looksButton&&lower.startsWith("enh_"));
        boolean mayAuto=!looksButton&&commanderIdentity&&(knownCommander||commanderUuid||savedMatch||saved.isEmpty());
        if(!connected&&!autoConnecting&&r.getRssi()>-100&&mayAuto){
            autoConnecting=true;
            log("DIRECT auto-select Commander -> "+name+" "+addr+(knownCommander?" [known]":savedMatch?" [saved]":" [verified]"));
            main.post(()->connectInternal(d));
        }else if(looksButton){
            log("DIRECT skip physical-button candidate -> "+name+" "+addr);
        }else if(!saved.isEmpty()&&!savedMatch){
            log("DIRECT skip non-saved candidate -> "+name+" "+addr);
        }
'''
if old not in s: raise SystemExit('Commander identity block not found')
s=s.replace(old,new,1)

needle='''            List<BluetoothGattService> services=source.getServices();
            log("DIRECT SERVICES count="+(services==null?0:services.size()));
'''
repl='''            List<BluetoothGattService> services=source.getServices();
            log("DIRECT SERVICES count="+(services==null?0:services.size()));
            if(source.getService(COMMANDER_SERVICE)==null){
                String bad=device==null?"":safeAddr(device);
                log("DIRECT connected device is not Commander; reject "+bad);
                if(!bad.isEmpty()&&bad.equalsIgnoreCase(prefs.getString("direct_commander_addr","")))
                    prefs.edit().remove("direct_commander_addr").apply();
                closeGatt();
                status("Commander 아님 · 다시 검색",false);
                if(wanted)main.postDelayed(scanRetryRunnable,500);
                return;
            }
'''
if needle not in s: raise SystemExit('services marker not found')
s=s.replace(needle,repl,1)
p.write_text(s)

# Vehicle gate: a manual connect/search should get a temporary setup window instead of the
# background vehicle trigger immediately tearing both BLE links back down.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()
s=s.replace('    private boolean pairingOverrideActive;\n',
'''    private boolean pairingOverrideActive;
    private boolean manualSetupOverrideActive;
''')
s=s.replace(
'''        if(isVehicleAutoEnabled()){
            if(driveSessionActive) activateForDrive("ensureRunning");
            else suspendForNoDrive("차량 연결 대기");
''',
'''        if(isVehicleAutoEnabled()){
            if(driveSessionActive||manualSetupOverrideActive) activateForDrive("ensureRunning");
            else suspendForNoDrive("차량 연결 대기");
''')
s=s.replace(
'''    public boolean isDriveSessionActive(){return driveSessionActive;}
''',
'''    public boolean isDriveSessionActive(){return driveSessionActive;}
    public boolean isManualSetupOverrideActive(){return manualSetupOverrideActive;}
    public void beginManualSetupWindow(){
        manualSetupOverrideActive=true;
        main.removeCallbacks(clearManualSetupOverride);
        main.postDelayed(clearManualSetupOverride,120000);
        manualDisconnect=false;
        log("SETUP manual BLE window ON for 120s");
        if(isAutoReconnect())scheduleReconnect(100);
        publish();
    }
    private final Runnable clearManualSetupOverride=()->{
        manualSetupOverrideActive=false;
        log("SETUP manual BLE window ended");
        if(isVehicleAutoEnabled()&&!driveSessionActive)suspendForNoDrive("설정 창 종료 · 차량 연결 대기");
        publish();
    };
''')
s=s.replace(
'''            else if(pairingOverrideActive){
                log("TRIGGER vehicle OFF ignored during pairing override");
            }else suspendForNoDrive(changed?"vehicle trigger OFF":vehicleTriggerStatus);
''',
'''            else if(pairingOverrideActive||manualSetupOverrideActive){
                log("TRIGGER vehicle OFF ignored during setup/pairing override");
            }else suspendForNoDrive(changed?"vehicle trigger OFF":vehicleTriggerStatus);
''')
s=s.replace(
'    private boolean shouldAutoRun(){return pairingOverrideActive||!isVehicleAutoEnabled()||driveSessionActive;}',
'    private boolean shouldAutoRun(){return pairingOverrideActive||manualSetupOverrideActive||!isVehicleAutoEnabled()||driveSessionActive;}'
)
p.write_text(s)

# UI manual actions open the setup window before either scan.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
s=s.replace(
'''        engine.stopCommander();
        if(directScanButton!=null)directScanButton.setText("Commander 자동 연결 중…");
''',
'''        engine.beginManualSetupWindow();
        engine.stopCommander();
        if(directScanButton!=null)directScanButton.setText("Commander 자동 연결 중…");
''',1)
s=s.replace(
'''    private void startScan(){if(!hasPermissions()){requestNeededPermissions();return;}if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}''',
'''    private void startScan(){if(!hasPermissions()){requestNeededPermissions();return;}if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}engine.beginManualSetupWindow();''',1)
s=s.replace('b.append("App: 0.7.3-direct-connect\\n\\n");','b.append("App: 0.7.4-direct-connect\\n\\n");')
p.write_text(s)

# Service must honor the same temporary manual setup window.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeForegroundService.java'
s=p.read_text()
s=s.replace(
'        if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();',
'        if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive()||engine.isManualSetupOverrideActive())directProbe.startAuto();'
)
p.write_text(s)

print('v0.7.4 Commander identity + manual setup gate fix applied')
