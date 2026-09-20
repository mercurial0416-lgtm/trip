from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.6.1 hotfix
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 6','versionCode 7')
s=s.replace("versionName '0.6.0-drive-auto'","versionName '0.6.1-pairing-hotfix'")
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()

s=s.replace(
'''    private boolean driveSessionActive;
    private String vehicleTriggerStatus="차량 감지 대기";
''',
'''    private boolean driveSessionActive;
    private boolean pairingOverrideActive;
    private String vehicleTriggerStatus="차량 감지 대기";
'''
)

old_pair='''    public void startVirtualPairing(){
        commanderRunning=true;
        virtualStatus="페어링 모드 시작 중…";
        commanderStatus="Commander 페어링 대기";
        log("PAIR  virtual pairing requested");
        publish();
        commanderServer.beginPairingWindow();
    }
'''
new_pair='''    public void startVirtualPairing(){
        pairingOverrideActive=true;
        main.removeCallbacks(clearPairingOverride);
        main.postDelayed(clearPairingOverride,25000);
        commanderRunning=true;
        virtualStatus="페어링 모드 시작 중…";
        commanderStatus="Commander 페어링 대기";
        log("PAIR  virtual pairing requested · vehicle gate bypass 25s");
        publish();
        commanderServer.beginPairingWindow();
    }

    private final Runnable clearPairingOverride=()->{
        pairingOverrideActive=false;
        log("PAIR  vehicle gate bypass ended");
        if(isVehicleAutoEnabled()&&!driveSessionActive)suspendForNoDrive("페어링 종료 · 차량 연결 대기");
        publish();
    };
'''
if old_pair not in s:
    raise SystemExit('startVirtualPairing block not found')
s=s.replace(old_pair,new_pair)

old_should='''    private boolean shouldAutoRun(){return !isVehicleAutoEnabled()||driveSessionActive;}
'''
new_should='''    private boolean shouldAutoRun(){return pairingOverrideActive||!isVehicleAutoEnabled()||driveSessionActive;}
'''
if old_should not in s:
    raise SystemExit('shouldAutoRun block not found')
s=s.replace(old_should,new_should)

old_gate='''        if(isVehicleAutoEnabled()){
            if(active)activateForDrive(changed?"vehicle trigger ON":"vehicle trigger refresh");
            else suspendForNoDrive(changed?"vehicle trigger OFF":vehicleTriggerStatus);
        }
'''
new_gate='''        if(isVehicleAutoEnabled()){
            if(active)activateForDrive(changed?"vehicle trigger ON":"vehicle trigger refresh");
            else if(pairingOverrideActive){
                log("TRIGGER vehicle OFF ignored during pairing override");
            }else suspendForNoDrive(changed?"vehicle trigger OFF":vehicleTriggerStatus);
        }
'''
if old_gate not in s:
    raise SystemExit('vehicle gate block not found')
s=s.replace(old_gate,new_gate)

p.write_text(s)
