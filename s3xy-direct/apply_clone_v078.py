from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

def rep(path, old, new, count=1):
    p=root/path
    s=p.read_text()
    if old not in s:
        raise SystemExit(f'marker missing in {path}: {old[:80]!r}')
    s=s.replace(old,new,count)
    p.write_text(s)

# Version.
rep('app/build.gradle',"versionCode 19","versionCode 20")
rep('app/build.gradle',"versionName '0.7.7-fast-highbeam-flash'","versionName '0.7.8-clone-id'")

# Real physical button: read encrypted 3D49 stable identity before B6.
p=root/'app/src/main/java/com/openai/s3xybridge/RealButtonClient.java'
s=p.read_text()
s=s.replace(
'''        void onRealReady(boolean ready);
        void onRealEvent(S3xyProtocol.Event event, byte[] raw);
''',
'''        void onRealReady(boolean ready);
        void onRealIdentity(byte[] id);
        void onRealEvent(S3xyProtocol.Event event, byte[] raw);
''',1)
s=s.replace(
'''            if (state==BluetoothDevice.BOND_BONDED) main.postDelayed(RealButtonClient.this::writeHandshake,250);
''',
'''            if (state==BluetoothDevice.BOND_BONDED) main.postDelayed(RealButtonClient.this::readIdentityThenHandshake,180);
''',1)
s=s.replace(
'''                if (!started) main.postDelayed(RealButtonClient.this::writeHandshake,250);
            } else writeHandshake();
''',
'''                if (!started) main.postDelayed(RealButtonClient.this::readIdentityThenHandshake,250);
            } else readIdentityThenHandshake();
''',1)
marker='''        @Override public void onCharacteristicWrite(BluetoothGatt g,BluetoothGattCharacteristic c,int status) {
'''
insert='''        @Override public void onCharacteristicRead(BluetoothGatt g,BluetoothGattCharacteristic c,int status) {
            if(!isCurrent(g))return;
            handleIdentityRead(c,status,c==null?null:c.getValue());
        }
        @Override public void onCharacteristicRead(BluetoothGatt g,BluetoothGattCharacteristic c,byte[] value,int status) {
            if(!isCurrent(g))return;
            handleIdentityRead(c,status,value);
        }

'''
if marker not in s: raise SystemExit('real read callback marker missing')
s=s.replace(marker,insert+marker,1)
marker='''    private void writeHandshake() {
'''
insert='''    private void readIdentityThenHandshake() {
        BluetoothGatt local=gatt;
        if(!hasConnect()||local==null||idChar==null||!subscribed){writeHandshake();return;}
        boolean started=false;
        try{started=local.readCharacteristic(idChar);}catch(Exception e){listener.onRealLog("3D49 read exception: "+e.getMessage());}
        listener.onRealLog("3D49 identity read start="+started);
        if(!started)main.postDelayed(this::writeHandshake,80);
    }

    private void handleIdentityRead(BluetoothGattCharacteristic c,int status,byte[] value) {
        if(c==null||!S3xyProtocol.BUTTON_ID.equals(c.getUuid()))return;
        if(status==BluetoothGatt.GATT_SUCCESS&&value!=null&&value.length>0&&value.length<=20){
            byte[] copy=Arrays.copyOf(value,value.length);
            listener.onRealLog("3D49 stable identity: "+S3xyProtocol.hex(copy));
            listener.onRealIdentity(copy);
        }else listener.onRealLog("3D49 identity read failed status="+status+" len="+(value==null?-1:value.length));
        main.postDelayed(this::writeHandshake,80);
    }

'''
if marker not in s: raise SystemExit('real handshake marker missing')
s=s.replace(marker,insert+marker,1)
p.write_text(s)

# Virtual button: clone/persist that same 3D49 identity.
p=root/'app/src/main/java/com/openai/s3xybridge/CommanderVirtualButtonServer.java'
s=p.read_text()
s=s.replace('import android.os.ParcelUuid;\n','import android.os.ParcelUuid;\nimport android.util.Base64;\n',1)
s=s.replace(
'''    private final byte[] id="BRIDGE0001".getBytes(StandardCharsets.US_ASCII);
''',
'''    private byte[] id="BRIDGE0001".getBytes(StandardCharsets.US_ASCII);
    private BluetoothGattCharacteristic idChar;
    private boolean cloneWindow;
''',1)
s=s.replace(
'''        compatibilityMode=prefs.getBoolean("commander_plain_gatt",false);
        closePairingWindow=this::closePairingWindowNow;
''',
'''        compatibilityMode=prefs.getBoolean("commander_plain_gatt",false);
        try{
            String saved=prefs.getString("cloned_button_id_b64","");
            if(!saved.isEmpty()){byte[] v=Base64.decode(saved,Base64.NO_WRAP);if(v.length>0&&v.length<=20)id=Arrays.copyOf(v,v.length);}
        }catch(Exception ignored){}
        closePairingWindow=this::closePairingWindowNow;
''',1)
s=s.replace(
'''    public boolean isReady(){return commander!=null&&subscribed;}
    public boolean isAdvertising(){return advertising;}
''',
'''    public boolean isReady(){return commander!=null&&subscribed;}
    public boolean isAdvertising(){return advertising;}
    public boolean hasClonedButtonId(){return prefs.contains("cloned_button_id_b64")&&id!=null&&id.length>0;}
    public byte[] getButtonId(){return id==null?new byte[0]:Arrays.copyOf(id,id.length);}
    public void setButtonId(byte[] value){
        if(value==null||value.length<1||value.length>20)return;
        id=Arrays.copyOf(value,value.length);
        prefs.edit().putString("cloned_button_id_b64",Base64.encodeToString(id,Base64.NO_WRAP)).apply();
        if(idChar!=null)try{idChar.setValue(Arrays.copyOf(id,id.length));}catch(Exception ignored){}
        listener.onCommanderLog("CLONE 3D49 identity loaded: "+S3xyProtocol.hex(id));
    }
''',1)
marker='''    private void openServer(){
'''
insert='''    public void beginCloneWindow(){
        cloneWindow=true;
        pairingWindow=true;
        earlyDisconnects=0;
        pendingNotifications.clear();
        main.removeCallbacks(closePairingWindow);
        listener.onCommanderLog("CLONE identity window opened id="+S3xyProtocol.hex(id));
        enablePairingIdentity();
        if(server==null)start();else restartAdvertisingDelayed(220);
        listener.onCommanderStatus("기존 버튼 ID 복제 광고 중 · Commander 자동 연결 대기");
        main.postDelayed(closePairingWindow,PAIRING_WINDOW_MS);
    }

'''
if marker not in s: raise SystemExit('server open marker missing')
s=s.replace(marker,insert+marker,1)
s=s.replace('BluetoothGattCharacteristic idChar=new BluetoothGattCharacteristic(','idChar=new BluetoothGattCharacteristic(',1)
s=s.replace(
'''        pairingWindow=false;
        restoreAdapterName();
        listener.onCommanderLog("PAIR pairing window closed");
''',
'''        pairingWindow=false;
        boolean wasClone=cloneWindow;cloneWindow=false;
        restoreAdapterName();
        listener.onCommanderLog((wasClone?"CLONE":"PAIR")+" identity window closed");
''',1)
s=s.replace(
'''        pairingWindow=false;
        closeServerOnly();
''',
'''        pairingWindow=false;
        cloneWindow=false;
        closeServerOnly();
''',1)
s=s.replace('''        server=null;
        notifyChar=null;
        advertiser=null;
''','''        server=null;
        notifyChar=null;
        idChar=null;
        advertiser=null;
''',1)
s=s.replace('''            listener.onCommanderStatus(pairingWindow
                    ?"페어링 모드 — ENH_BTN 광고 중"
                    :"S3XY 서비스 광고 중");
''','''            listener.onCommanderStatus(pairingWindow
                    ?(cloneWindow?"기존 버튼 ID 복제 광고 중 · Commander 대기":"페어링 모드 — ENH_BTN 광고 중")
                    :"S3XY 서비스 광고 중");
''',1)
s=s.replace('''                listener.onCommanderStatus(pairingWindow
                        ?"Commander 연결 끊김 — 자동 재광고 중"
                        :"Commander 연결 끊김 — 광고 유지");
''','''                listener.onCommanderStatus(pairingWindow
                        ?(cloneWindow?"복제 채널 연결 끊김 — 자동 재광고 중":"Commander 연결 끊김 — 자동 재광고 중")
                        :"Commander 연결 끊김 — 광고 유지");
''',1)
p.write_text(s)

# Engine: clone state, safe arm gate, and auto-start cloned peripheral after ID capture.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()
s=s.replace(
'''    public boolean isFastHighBeamMode(){return prefs.getBoolean("fast_highbeam_mode",false);}
    public boolean isFastHighBeamArmed(){return prefs.getBoolean("fast_highbeam_armed",false);}
''',
'''    public boolean isFastHighBeamMode(){return prefs.getBoolean("fast_highbeam_mode",false);}
    public boolean isFastHighBeamArmed(){return prefs.getBoolean("fast_highbeam_armed",false);}
    public boolean isCloneMode(){return prefs.getBoolean("fast_highbeam_clone_mode",false);}
    public boolean hasClonedButtonIdentity(){return commanderServer.hasClonedButtonId();}
    public void prepareFastHighBeamClone(){
        prefs.edit().putBoolean("fast_highbeam_mode",true)
                .putBoolean("fast_highbeam_clone_mode",true)
                .putBoolean("fast_highbeam_armed",false)
                .putBoolean("direct_commander_mode",false)
                .putBoolean("auto_virtual",true)
                .putBoolean("commander_plain_gatt",false)
                .putBoolean("test_mode",true)
                .putLong("interval",80)
                .putLong("max_ms",5000).apply();
        bridge.updateSettings(true,80,5000);
        stopCommander();
        manualDisconnect=false;
        beginManualSetupWindow();
        log("CLONE waiting for physical 3D49 identity · no vehicle output");
        publish();
    }
''',1)
s=s.replace(
'''        prefs.edit().putBoolean("fast_highbeam_mode",true)
                .putBoolean("fast_highbeam_armed",false)
''',
'''        prefs.edit().putBoolean("fast_highbeam_mode",true)
                .putBoolean("fast_highbeam_clone_mode",false)
                .putBoolean("fast_highbeam_armed",false)
''',1)
s=s.replace('''    public void armFastHighBeam(){
        prefs.edit().putBoolean("fast_highbeam_mode",true)
''','''    public boolean armFastHighBeam(){
        if(isCloneMode()&&!hasClonedButtonIdentity()){log("FASTHB arm blocked: cloned 3D49 identity missing");publish();return false;}
        prefs.edit().putBoolean("fast_highbeam_mode",true)
''',1)
s=s.replace('''        log("FASTHB ARMED: physical DOWN/UP -> repeated virtual SINGLE, 80ms");
        publish();
    }
''','''        log("FASTHB ARMED: physical DOWN/UP -> repeated virtual SINGLE, 80ms");
        publish();
        return true;
    }
''',1)
marker='''    @Override public void onRealEvent(S3xyProtocol.Event e,byte[] raw){
'''
insert='''    @Override public void onRealIdentity(byte[] id){
        if(id==null||id.length<1||id.length>20)return;
        commanderServer.setButtonId(id);
        log("CLONE physical button identity captured: "+S3xyProtocol.hex(id));
        if(isCloneMode()){
            commanderRunning=true;
            virtualStatus="기존 버튼 ID 복제 광고 준비 중";
            commanderStatus="Commander 자동 연결 대기";
            commanderServer.beginCloneWindow();
        }
        publish();
    }

'''
if marker not in s: raise SystemExit('engine real event marker missing')
s=s.replace(marker,insert+marker,1)
p.write_text(s)

# UI: no new virtual-button registration. Clone the user's existing button identity.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
old='''        LinearLayout easy=card();easy.addView(section("⚡ 빠른 하이빔 연결"));
        easyStatus=status("최초 1회 설정 필요",false);easy.addView(easyStatus,margins(-1,-2,0,8,0,10));
        TextView easyHelp=body("처음 한 번만 공식 S3XY 앱에서 새 ENH_BTN을 추가하고 SINGLE 동작을 반드시 High Beam으로 지정하세요. 그 뒤에는 공식 앱을 종료하고 이 앱만 쓰면 됩니다.");
        easyHelp.setTextColor(Color.rgb(177,214,255));easy.addView(easyHelp,margins(-1,-2,0,0,0,10));
        highBeamPairButton=primary("1회 설정 · 공식 S3XY 앱에서 버튼 추가");highBeamPairButton.setOnClickListener(v->startHighBeamPairing());easy.addView(highBeamPairButton,margins(-1,dp(50),0,0,0,8));
        highBeamArmButton=secondary("SINGLE = High Beam Flash 지정 완료");highBeamArmButton.setOnClickListener(v->{engine.armFastHighBeam();toast("빠른 하이빔 모드 활성화");startEasyConnect();});easy.addView(highBeamArmButton,margins(-1,dp(48),0,0,0,8));
        easyButton=primary("원터치 연결 시작");easyButton.setOnClickListener(v->startEasyConnect());easy.addView(easyButton,margins(-1,dp(52),0,0,0,0));
'''
new='''        LinearLayout easy=card();easy.addView(section("⚡ 기존 S3XY 버튼 복제"));
        easyStatus=status("복제 설정 필요",false);easy.addView(easyStatus,margins(-1,-2,0,8,0,10));
        TextView easyHelp=body("새 ENH_BTN을 추가하지 않습니다. 공식 앱에서는 기존 실물 버튼의 SINGLE만 High Beam Flash로 지정하세요. 그 다음 이 앱이 실물 버튼의 3D49 고유 ID를 읽어 같은 버튼으로 광고합니다.");
        easyHelp.setTextColor(Color.rgb(177,214,255));easy.addView(easyHelp,margins(-1,-2,0,0,0,10));
        highBeamPairButton=primary("1. 기존 버튼 ID 복제 시작");highBeamPairButton.setOnClickListener(v->startCloneSetup());easy.addView(highBeamPairButton,margins(-1,dp(50),0,0,0,8));
        highBeamArmButton=secondary("2. 기존 버튼 SINGLE = High Beam Flash 확인");highBeamArmButton.setOnClickListener(v->{if(engine.armFastHighBeam()){toast("빠른 하이빔 모드 활성화");startEasyConnect();}else toast("먼저 기존 버튼 ID 복제를 완료하세요.");});easy.addView(highBeamArmButton,margins(-1,dp(48),0,0,0,8));
        easyButton=primary("재연결 / 원터치 시작");easyButton.setOnClickListener(v->startEasyConnect());easy.addView(easyButton,margins(-1,dp(52),0,0,0,0));
'''
if old not in s: raise SystemExit('main easy card marker missing')
s=s.replace(old,new,1)
s=s.replace("초기 등록 뒤에는 Commander가 이 가상 버튼에 직접 연결합니다. 실물 버튼 DOWN/UP은 폰이 받고, 누르는 동안 SINGLE을 빠르게 반복합니다.","복제 성공 뒤에는 Commander가 같은 3D49 ID를 가진 가상 버튼으로 인식하는지 자동 확인합니다. 실물 버튼 DOWN/UP은 폰이 받고 누르는 동안 SINGLE을 빠르게 반복합니다.",1)
s=s.replace("ⓘ 최초 1회 가상 ENH_BTN의 SINGLE을 High Beam Flash로 등록하면 이후에는 실물 버튼을 누르고 있는 동안 빠른 펄스를 자동 전송합니다. 버튼을 떼면 즉시 반복을 중단합니다.","ⓘ 새 가상 버튼 등록 대신 기존 실물 버튼의 3D49 안정 ID를 복제합니다. 기존 버튼 SINGLE은 High Beam Flash여야 합니다. 버튼을 떼면 반복을 즉시 중단합니다.",1)
s=s.replace("먼저 SINGLE을 High Beam Flash로 지정하고 설정 완료를 누르세요.","먼저 기존 버튼 ID 복제와 High Beam Flash 확인을 완료하세요.",1)
marker='''    private void startHighBeamPairing(){
'''
insert='''    private void startCloneSetup(){
        if(!hasScan()||!hasConnect()||!hasAdvertise()){requestNeededPermissions();return;}
        if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}
        if(directProbe!=null){directProbe.stopScan();directProbe.disconnect();}
        engine.prepareFastHighBeamClone();
        easyAutoConnect=true;easyRealReady=false;easyCommanderReady=false;
        updateEasyStatus();
        if(easyButton!=null)easyButton.setText("실물 버튼 찾는 중…");
        startButtonScan(true);
    }

'''
if marker not in s: raise SystemExit('main pair method marker missing')
s=s.replace(marker,insert+marker,1)
s=s.replace('''        if(!engine.isFastHighBeamMode()){toast("먼저 1회 하이빔 버튼 등록을 해주세요.");return;}
        engine.beginManualSetupWindow();
        if(directProbe!=null){directProbe.stopScan();directProbe.disconnect();}
        engine.startCommander();
''','''        if(!engine.isFastHighBeamMode()){toast("먼저 기존 버튼 ID 복제를 시작하세요.");return;}
        engine.beginManualSetupWindow();
        if(directProbe!=null){directProbe.stopScan();directProbe.disconnect();}
        if(engine.hasClonedButtonIdentity())engine.startCommander();
''',1)
s=s.replace('''        String t=!engine.isFastHighBeamMode()?"최초 1회 설정 필요":
                !armed?"공식 S3XY 앱에서 SINGLE = High Beam Flash 지정 후 '지정 완료'를 누르세요":
                ok?"빠른 하이빔 준비 완료 · 누르는 동안 반복":
                easyRealReady?"실물 버튼 연결됨 · Commander 채널 연결 중…":
                easyCommanderReady?"Commander 채널 연결됨 · 실물 버튼 연결 중…":
                "실물 버튼 + Commander 자동 연결 중…";
''','''        boolean cloned=engine!=null&&engine.hasClonedButtonIdentity();
        String t=!engine.isFastHighBeamMode()?"복제 설정 필요":
                !cloned?"실물 버튼 연결 후 3D49 ID 읽는 중…":
                !armed?"ID 복제 완료 · 기존 버튼 SINGLE = High Beam Flash 확인 필요":
                ok?"빠른 하이빔 준비 완료 · 누르는 동안 반복":
                easyRealReady?"실물 버튼 연결됨 · 복제 ID로 Commander 연결 대기…":
                easyCommanderReady?"Commander 복제 채널 연결됨 · 실물 버튼 연결 중…":
                "복제 ID 저장됨 · 실물 버튼 + Commander 자동 연결 중…";
''',1)
s=s.replace("App: 0.7.7-fast-highbeam-flash","App: 0.7.8-clone-id")
p.write_text(s)

print('v0.7.8 clone-id patch applied')
