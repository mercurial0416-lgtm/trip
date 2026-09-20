from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# Replace the virtual-button GATT server with the bonding-aware implementation.
src=Path('s3xy-pairing/CommanderVirtualButtonServer.java').read_text()
(root/'app/src/main/java/com/openai/s3xybridge/CommanderVirtualButtonServer.java').write_text(src)

# Version bump.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 4','versionCode 5')
s=s.replace("versionName '0.4.0-updater'","versionName '0.5.0-pairing'")
p.write_text(s)

# BridgeEngine: expose a dedicated pairing-window action.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()
needle='''    public void stopCommander(){ commanderRunning=false; commanderServer.stop(); virtualStatus="중지됨"; commanderStatus="연결 대기"; commanderReady=false; publish(); }
    public boolean isCommanderRunning(){return commanderRunning||commanderServer.isAdvertising();}
'''
repl='''    public void stopCommander(){ commanderRunning=false; commanderServer.stop(); virtualStatus="중지됨"; commanderStatus="연결 대기"; commanderReady=false; publish(); }
    public boolean isCommanderRunning(){return commanderRunning||commanderServer.isAdvertising();}
    public void startVirtualPairing(){
        commanderRunning=true;
        virtualStatus="페어링 모드 시작 중…";
        commanderStatus="Commander 페어링 대기";
        log("PAIR  virtual pairing requested");
        publish();
        commanderServer.beginPairingWindow();
    }
'''
if 'startVirtualPairing()' not in s:
    if needle not in s: raise SystemExit('BridgeEngine insertion point not found')
    s=s.replace(needle,repl)
p.write_text(s)

# MainActivity: add an explicit pairing action with clear instructions.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
old='''        LinearLayout vc=deviceCard("</>","Virtual ENH_BTN","Commander가 인식하는 가상 버튼");
        virtualStatus=status("중지됨",false);vc.addView(virtualStatus,margins(-2,-2,0,8,0,8));
        virtualButton=primary("가상 ENH_BTN 시작");virtualButton.setOnClickListener(v->{if(engine.isCommanderRunning())engine.stopCommander();else engine.startCommander();});vc.addView(virtualButton,margins(-1,dp(46),0,12,0,0));r.addView(vc,margins(-1,-2,0,0,0,12));
'''
new='''        LinearLayout vc=deviceCard("</>","Virtual ENH_BTN","Commander가 인식하는 가상 버튼");
        virtualStatus=status("중지됨",false);vc.addView(virtualStatus,margins(-2,-2,0,8,0,8));
        TextView pairHelp=body("공식 S3XY 앱 → Buttons → S3XY Button 추가 → '버튼을 꾹 누르세요' 화면에서 아래 페어링 버튼을 누르세요.");pairHelp.setTextColor(Color.rgb(177,214,255));vc.addView(pairHelp,margins(-1,-2,0,2,0,10));
        Button pair=primary("가상 버튼 페어링 시작 (20초)");pair.setOnClickListener(v->{engine.startVirtualPairing();toast("공식 S3XY 앱의 버튼 추가 화면에서 잠시 기다리세요.");});vc.addView(pair,margins(-1,dp(48),0,0,0,8));
        virtualButton=secondary("가상 ENH_BTN 시작 / 중지");virtualButton.setOnClickListener(v->{if(engine.isCommanderRunning())engine.stopCommander();else engine.startCommander();});vc.addView(virtualButton,margins(-1,dp(44),0,0,0,0));r.addView(vc,margins(-1,-2,0,0,0,12));
'''
if '가상 버튼 페어링 시작 (20초)' not in s:
    if old not in s: raise SystemExit('Virtual card block not found')
    s=s.replace(old,new)

old2='''        LinearLayout cc=deviceCard("◉","Commander","공식 S3XY 앱 연결은 그대로 유지");commanderStatus=status("연결 대기",false);cc.addView(commanderStatus,margins(-2,-2,0,8,0,0));r.addView(cc,margins(-1,-2,0,0,0,12));
'''
new2='''        LinearLayout cc=deviceCard("◉","Commander","여기 상태는 공식 앱↔Commander가 아니라 '가상 ENH_BTN↔Commander' 연결 상태입니다.");commanderStatus=status("연결 대기",false);cc.addView(commanderStatus,margins(-2,-2,0,8,0,0));r.addView(cc,margins(-1,-2,0,0,0,12));
'''
if old2 in s:s=s.replace(old2,new2)

p.write_text(s)
