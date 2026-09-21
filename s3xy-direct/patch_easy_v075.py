from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.7.5 Easy Connect: one-tap setup, auto-pick the physical button, then Commander.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 16','versionCode 17')
s=s.replace("versionName '0.7.4-direct-connect'","versionName '0.7.5-easy-connect'")
if 'versionCode 17' not in s or "versionName '0.7.5-easy-connect'" not in s:
    raise SystemExit('v0.7.5 version bump failed')
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()

s=s.replace(
'    private TextView realStatus,virtualStatus,commanderStatus,directStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,vehicleTriggerStatus,log;',
'    private TextView easyStatus,realStatus,virtualStatus,commanderStatus,directStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,vehicleTriggerStatus,log;'
)
s=s.replace(
'    private Button scanButton,virtualButton,directScanButton;',
'    private Button easyButton,scanButton,virtualButton,directScanButton;'
)
s=s.replace(
'    private boolean scanning, syncing;',
'    private boolean scanning, syncing, easyAutoConnect, easyRealReady, easyCommanderReady;'
)

# Auto-run Easy Connect after permissions are available.
old='''        main.postDelayed(()->{
            if(hasScan()&&hasConnect()){
                engine.stopCommander();
                if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();
            }
        },700);
'''
new='''        main.postDelayed(()->{
            if(hasScan()&&hasConnect())startEasyConnect();
        },900);
'''
if old not in s: raise SystemExit('onCreate direct marker not found')
s=s.replace(old,new,1)

# Add a single obvious card at the top.
old='''        ScrollView s=baseScroll();LinearLayout r=scrollRoot(s);r.addView(header("↗","Bridge Setup","버튼 연결·자동화·프로필을 여기서 관리합니다."));

        LinearLayout pc=deviceCard("▣","Physical Button","홀드용 실물 S3XY Button");
'''
new='''        ScrollView s=baseScroll();LinearLayout r=scrollRoot(s);r.addView(header("↗","간편 연결","공식 S3XY 앱은 종료하고, 아래 버튼 하나만 누르면 됩니다."));

        LinearLayout easy=card();easy.addView(section("⚡ 원터치 연결"));
        easyStatus=status("버튼 + Commander 자동 연결 대기",false);easy.addView(easyStatus,margins(-1,-2,0,8,0,10));
        TextView easyHelp=body("1) 공식 S3XY 앱 완전 종료  2) 원터치 연결 누르기  3) 둘 다 초록색이면 끝");
        easyHelp.setTextColor(Color.rgb(177,214,255));easy.addView(easyHelp,margins(-1,-2,0,0,0,10));
        easyButton=primary("원터치 연결 시작");easyButton.setOnClickListener(v->startEasyConnect());easy.addView(easyButton,margins(-1,dp(52),0,0,0,0));
        r.addView(easy,margins(-1,-2,0,0,0,14));

        LinearLayout pc=deviceCard("▣","Physical Button","고급/진단용 · 평소에는 위 원터치 연결만 사용");
'''
if old not in s: raise SystemExit('setup header marker not found')
s=s.replace(old,new,1)

# Reduce legacy confusion.
s=s.replace(
'        LinearLayout vc=deviceCard("</>","Legacy Virtual ENH_BTN","기존 가상 버튼 방식 · Commander 호환성 문제 때문에 Direct Lab을 우선 사용하세요.");',
'        LinearLayout vc=deviceCard("</>","Legacy Virtual ENH_BTN","사용하지 않는 이전 방식");vc.setVisibility(View.GONE);'
)
s=s.replace(
'        LinearLayout cc=deviceCard("◉","Commander","여기 상태는 공식 앱↔Commander가 아니라 \'가상 ENH_BTN↔Commander\' 연결 상태입니다.");',
'        LinearLayout cc=deviceCard("◉","Commander","Legacy 상태");cc.setVisibility(View.GONE);'
)

# Honest hold-mode UI: direct vehicle write is not implemented yet.
old='''liveSwitch=addSwitch(mode,"실전 전송","가상 ENH_BTN 펄스를 Commander에 실제 전송",false,(b,on)->{if(syncing)return;syncing=true;testSwitch.setChecked(!on);syncing=false;applyHoldSettings();});'''
new='''liveSwitch=addSwitch(mode,"실전 전송 (아직 비활성)","Commander 직접 차량제어 명령부가 확인되기 전에는 차량 출력하지 않습니다.",false,(b,on)->{if(on){b.setChecked(false);toast("차량제어 명령부 확인 전이라 아직 비활성입니다.");}});liveSwitch.setEnabled(false);'''
if old not in s: raise SystemExit('live switch marker not found')
s=s.replace(old,new,1)

# Version in exported report.
s=s.replace('App: 0.7.4-direct-connect','App: 0.7.5-easy-connect')

# Easy connect implementation. Physical button first, then Commander.
insert='''    private void startEasyConnect(){
        if(!hasScan()||!hasConnect()){requestNeededPermissions();return;}
        if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}
        engine.beginManualSetupWindow();
        engine.stopCommander();
        easyAutoConnect=true;
        easyRealReady=false;easyCommanderReady=false;
        updateEasyStatus();
        if(easyButton!=null)easyButton.setText("자동 연결 중…");
        startButtonScan(true);
        main.postDelayed(()->{
            if(directProbe!=null&&!easyCommanderReady)directProbe.startAuto();
        },4500);
    }

    private void updateEasyStatus(){
        if(easyStatus==null)return;
        boolean ok=easyRealReady&&easyCommanderReady;
        String t=ok?"실물 버튼 + Commander 연결 완료":
                easyRealReady?"실물 버튼 연결됨 · Commander 연결 중…":
                easyCommanderReady?"Commander 연결됨 · 실물 버튼 연결 중…":
                "실물 버튼 찾는 중…";
        setStatus(easyStatus,t,ok);
        if(easyButton!=null)easyButton.setText(ok?"둘 다 연결됨 · 다시 연결":"원터치 연결 시작");
    }

'''
marker='''    private void startDirectScan(){
'''
if marker not in s: raise SystemExit('startDirectScan marker not found')
s=s.replace(marker,insert+marker,1)

# Direct status contributes to easy summary.
old='''    @Override public void onDirectStatus(String s,boolean connected){runOnUiThread(()->{
        setStatus(directStatus,s,connected);
        if(directScanButton!=null&&!s.contains("검색 중"))directScanButton.setText("Commander 자동 연결");
    });}
'''
new='''    @Override public void onDirectStatus(String s,boolean connected){runOnUiThread(()->{
        setStatus(directStatus,s,connected);
        easyCommanderReady=connected;updateEasyStatus();
        if(directScanButton!=null&&!s.contains("검색 중"))directScanButton.setText("Commander 자동 연결");
    });}
'''
if old not in s: raise SystemExit('direct status marker not found')
s=s.replace(old,new,1)

# Snapshot contributes physical-button status to easy summary.
old='''        setStatus(realStatus,s.realStatus,s.realReady);setStatus(virtualStatus,s.advertising?(s.commanderReady?"연결됨":"광고 중"):s.virtualStatus,s.advertising);setStatus(commanderStatus,s.commanderStatus,s.commanderReady);
'''
new='''        setStatus(realStatus,s.realStatus,s.realReady);easyRealReady=s.realReady;updateEasyStatus();setStatus(virtualStatus,s.advertising?(s.commanderReady?"연결됨":"광고 중"):s.virtualStatus,s.advertising);setStatus(commanderStatus,s.commanderStatus,s.commanderReady);
'''
if old not in s: raise SystemExit('snapshot marker not found')
s=s.replace(old,new,1)

# Replace physical scan with reusable auto/manual variant. Do not stop Commander scan here.
old='''    private void startScan(){if(!hasPermissions()){requestNeededPermissions();return;}if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}engine.beginManualSetupWindow();if(directProbe!=null)directProbe.stopScan();if(scanning)return;scanner=adapter.getBluetoothLeScanner();if(scanner==null){toast("BLE scanner 없음");return;}found.clear();scanResults.removeAllViews();scanning=true;scanButton.setText("검색 중…");scanner.startScan(scanCallback);main.postDelayed(this::stopScan,10000);}
'''
new='''    private void startScan(){startButtonScan(false);}
    private void startButtonScan(boolean autoConnect){
        if(!hasPermissions()){requestNeededPermissions();return;}
        if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}
        engine.beginManualSetupWindow();
        easyAutoConnect=autoConnect;
        if(scanning)stopScan();
        scanner=adapter.getBluetoothLeScanner();if(scanner==null){toast("BLE scanner 없음");return;}
        found.clear();if(scanResults!=null)scanResults.removeAllViews();scanning=true;
        if(scanButton!=null)scanButton.setText("검색 중…");
        try{scanner.startScan(scanCallback);}catch(Exception e){scanning=false;toast("검색 시작 실패");return;}
        main.postDelayed(this::stopScan,autoConnect?7000:10000);
    }
'''
if old not in s: raise SystemExit('startScan marker not found')
s=s.replace(old,new,1)

# Auto-select the physical button in easy mode.
old='''    private void handleScan(ScanResult r){if(r==null||r.getDevice()==null)return;String name="";try{name=r.getScanRecord()==null?null:r.getScanRecord().getDeviceName();}catch(Exception ignored){}boolean svc=false;try{svc=r.getScanRecord()!=null&&r.getScanRecord().getServiceUuids()!=null&&r.getScanRecord().getServiceUuids().contains(new ParcelUuid(S3xyProtocol.BUTTON_SERVICE));}catch(Exception ignored){}if(!("ENH_BTN".equals(name)||svc))return;String addr=safeAddr(r.getDevice());if(found.containsKey(addr))return;found.put(addr,r.getDevice());String fn=name==null||name.isEmpty()?"ENH_BTN":name;runOnUiThread(()->{TextView item=text(fn+"  RSSI "+r.getRssi()+"\n"+addr+"  · 탭해서 연결",13,true,TEXT);item.setPadding(dp(12),dp(12),dp(12),dp(12));item.setBackground(rounded(Color.rgb(11,25,38),BLUE,12,1));item.setOnClickListener(v->{stopScan();engine.connectReal(r.getDevice());});scanResults.addView(item,margins(-1,-2,0,0,0,7));});}
'''
new='''    private void handleScan(ScanResult r){if(r==null||r.getDevice()==null)return;String name="";try{name=r.getScanRecord()==null?null:r.getScanRecord().getDeviceName();}catch(Exception ignored){}boolean svc=false;try{svc=r.getScanRecord()!=null&&r.getScanRecord().getServiceUuids()!=null&&r.getScanRecord().getServiceUuids().contains(new ParcelUuid(S3xyProtocol.BUTTON_SERVICE));}catch(Exception ignored){}if(!("ENH_BTN".equals(name)||svc))return;String addr=safeAddr(r.getDevice());if(found.containsKey(addr))return;found.put(addr,r.getDevice());if(easyAutoConnect){runOnUiThread(()->{easyAutoConnect=false;stopScan();engine.connectReal(r.getDevice());if(directProbe!=null)main.postDelayed(()->directProbe.startAuto(),700);});return;}String fn=name==null||name.isEmpty()?"ENH_BTN":name;runOnUiThread(()->{TextView item=text(fn+"  RSSI "+r.getRssi()+"\n"+addr+"  · 탭해서 연결",13,true,TEXT);item.setPadding(dp(12),dp(12),dp(12),dp(12));item.setBackground(rounded(Color.rgb(11,25,38),BLUE,12,1));item.setOnClickListener(v->{stopScan();engine.connectReal(r.getDevice());});scanResults.addView(item,margins(-1,-2,0,0,0,7));});}
'''
if old not in s: raise SystemExit('handleScan marker not found')
s=s.replace(old,new,1)

# Permission completion also uses Easy Connect.
old='''    @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){super.onRequestPermissionsResult(r,p,g);if(r==REQ_PERMS){engine.ensureRunning();if(hasScan()&&hasConnect()){engine.stopCommander();if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive())directProbe.startAuto();}}}
'''
new='''    @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){super.onRequestPermissionsResult(r,p,g);if(r==REQ_PERMS){engine.ensureRunning();if(hasScan()&&hasConnect())main.postDelayed(this::startEasyConnect,400);}}
'''
if old not in s: raise SystemExit('permission marker not found')
s=s.replace(old,new,1)

p.write_text(s)
print('v0.7.5 Easy Connect patch applied')
