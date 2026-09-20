from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# Add vehicle trigger manager.
src=Path('s3xy-vehicle/VehicleTriggerManager.java').read_text()
(root/'app/src/main/java/com/openai/s3xybridge/VehicleTriggerManager.java').write_text(src)

# v0.6.0
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 5','versionCode 6')
s=s.replace("versionName '0.5.0-pairing'","versionName '0.6.0-drive-auto'")
p.write_text(s)

# BridgeEngine: gate automatic BLE bridge by vehicle BT/car mode.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()

s=s.replace(
'''    private int sessionPulses;
    private Runnable reconnectRunnable;
    private long currentHoldStart;
''',
'''    private int sessionPulses;
    private Runnable reconnectRunnable;
    private long currentHoldStart;
    private boolean driveSessionActive;
    private String vehicleTriggerStatus="차량 감지 대기";
'''
)

s=s.replace(
'''    public void ensureRunning(){
        if(prefs.getBoolean("auto_virtual",true)) startCommander();
        if(isAutoReconnect()) scheduleReconnect(250);
    }
''',
'''    public void ensureRunning(){
        if(isVehicleAutoEnabled()){
            if(driveSessionActive) activateForDrive("ensureRunning");
            else suspendForNoDrive("차량 연결 대기");
        }else{
            if(prefs.getBoolean("auto_virtual",true)) startCommander();
            if(isAutoReconnect()) scheduleReconnect(250);
        }
    }
'''
)

insert_after='''    public boolean isBackgroundEnabled(){return prefs.getBoolean("background",true);}
    public void setBackgroundEnabled(boolean b){prefs.edit().putBoolean("background",b).apply();publish();}
'''
vehicle_methods='''    public boolean isVehicleAutoEnabled(){return prefs.getBoolean("vehicle_auto_enabled",true);}
    public boolean isCarModeTriggerEnabled(){return prefs.getBoolean("car_mode_trigger",true);}
    public boolean isDriveSessionActive(){return driveSessionActive;}
    public String getVehicleTriggerStatus(){return vehicleTriggerStatus;}
    public String getVehicleTargetName(){return prefs.getString("vehicle_bt_name","");}
    public String getVehicleTargetAddress(){return prefs.getString("vehicle_bt_address","");}
    public void setVehicleAutoEnabled(boolean b){
        prefs.edit().putBoolean("vehicle_auto_enabled",b).apply();
        if(b){
            if(driveSessionActive)activateForDrive("vehicle auto enabled");
            else suspendForNoDrive("차량 자동 연결 켜짐 · 차량 대기");
        }else{
            vehicleTriggerStatus="차량 자동 연결 꺼짐 · 항상 연결";
            manualDisconnect=false;
            if(prefs.getBoolean("auto_virtual",true))startCommander();
            if(isAutoReconnect())scheduleReconnect(100);
        }
        publish();
    }
    public void setCarModeTriggerEnabled(boolean b){prefs.edit().putBoolean("car_mode_trigger",b).apply();publish();}
    public void setVehicleTarget(String address,String name){
        if(address==null)address="";
        if(name==null)name="";
        prefs.edit().putString("vehicle_bt_address",address).putString("vehicle_bt_name",name).apply();
        log("TRIGGER vehicle target saved: "+name+" "+address);
        publish();
    }
    public void setDriveSessionActive(boolean active,String status){
        vehicleTriggerStatus=status==null?"":status;
        boolean changed=driveSessionActive!=active;
        driveSessionActive=active;
        if(isVehicleAutoEnabled()){
            if(active)activateForDrive(changed?"vehicle trigger ON":"vehicle trigger refresh");
            else suspendForNoDrive(changed?"vehicle trigger OFF":vehicleTriggerStatus);
        }
        publish();
    }
    private boolean shouldAutoRun(){return !isVehicleAutoEnabled()||driveSessionActive;}
    private void activateForDrive(String reason){
        manualDisconnect=false;
        log("TRIGGER bridge ON: "+reason);
        if(prefs.getBoolean("auto_virtual",true))startCommander();
        if(isAutoReconnect())scheduleReconnect(100);
    }
    private void suspendForNoDrive(String reason){
        main.removeCallbacks(reconnectRunnable);
        bridge.forceStop("차량 연결 종료");
        try{realClient.disconnect();}catch(Exception ignored){}
        realReady=false;
        realStatus="차량 대기";
        if(isCommanderRunning())stopCommander();
        bridgeStatus="차량 대기";
        log("TRIGGER bridge OFF: "+reason);
    }
'''
if vehicle_methods not in s:
    if insert_after not in s: raise SystemExit('BridgeEngine vehicle insertion point not found')
    s=s.replace(insert_after,insert_after+vehicle_methods)

s=s.replace(
'''if(s.contains("연결 끊김")&&!manualDisconnect){bridge.forceStop("연결 끊김");if(isDisconnectAlert()){vibrate(new long[]{0,100,80,180});log("ALERT 실물 버튼 연결 끊김");}if(isAutoReconnect())scheduleReconnect(nextBackoff());}''',
'''if(s.contains("연결 끊김")&&!manualDisconnect){bridge.forceStop("연결 끊김");if(isDisconnectAlert()&&shouldAutoRun()){vibrate(new long[]{0,100,80,180});log("ALERT 실물 버튼 연결 끊김");}if(isAutoReconnect()&&shouldAutoRun())scheduleReconnect(nextBackoff());}'''
)

s=s.replace(
'''    private void doReconnect(){
        if(!isAutoReconnect()||manualDisconnect||realReady)return;
''',
'''    private void doReconnect(){
        if(!isAutoReconnect()||manualDisconnect||realReady||!shouldAutoRun())return;
'''
)

# Include trigger prefs in backup/restore.
s=s.replace(
'''root.put("auto_reconnect",isAutoReconnect());root.put("vibration",isVibration());root.put("disconnect_alert",isDisconnectAlert());root.put("background",isBackgroundEnabled());''',
'''root.put("auto_reconnect",isAutoReconnect());root.put("vibration",isVibration());root.put("disconnect_alert",isDisconnectAlert());root.put("background",isBackgroundEnabled());
            root.put("vehicle_auto_enabled",isVehicleAutoEnabled());root.put("car_mode_trigger",isCarModeTriggerEnabled());root.put("vehicle_bt_address",getVehicleTargetAddress());root.put("vehicle_bt_name",getVehicleTargetName());'''
)
s=s.replace(
'''                    .putBoolean("background",root.optBoolean("background",true)).apply();''',
'''                    .putBoolean("background",root.optBoolean("background",true))
                    .putBoolean("vehicle_auto_enabled",root.optBoolean("vehicle_auto_enabled",true))
                    .putBoolean("car_mode_trigger",root.optBoolean("car_mode_trigger",true))
                    .putString("vehicle_bt_address",root.optString("vehicle_bt_address",""))
                    .putString("vehicle_bt_name",root.optString("vehicle_bt_name","")).apply();'''
)
p.write_text(s)

# Foreground service owns the trigger receiver.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeForegroundService.java'
s=p.read_text()
s=s.replace(
'''public class BridgeForegroundService extends Service implements BridgeEngine.Listener {''',
'''public class BridgeForegroundService extends Service implements BridgeEngine.Listener, VehicleTriggerManager.Listener {'''
)
s=s.replace(
'''    private BridgeEngine engine;
''',
'''    public static final String ACTION_REFRESH_TRIGGER="com.openai.s3xybridge.REFRESH_VEHICLE_TRIGGER";
    private BridgeEngine engine;
    private VehicleTriggerManager vehicleTrigger;
'''
)
s=s.replace(
'''        engine.attach(this);
        startForeground(ID,notification("브리지 시작 중"));
        engine.ensureRunning();
''',
'''        engine.attach(this);
        startForeground(ID,notification("차량 감지 시작"));
        vehicleTrigger=new VehicleTriggerManager(this,this);
        vehicleTrigger.start();
        engine.ensureRunning();
'''
)
s=s.replace(
'''    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(engine==null)engine=BridgeEngine.get(this);
        engine.ensureRunning();
        return START_STICKY;
    }

    @Override public void onDestroy(){if(engine!=null)engine.detach(this);super.onDestroy();}
''',
'''    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(engine==null)engine=BridgeEngine.get(this);
        if(vehicleTrigger==null){vehicleTrigger=new VehicleTriggerManager(this,this);vehicleTrigger.start();}
        if(intent!=null&&ACTION_REFRESH_TRIGGER.equals(intent.getAction()))vehicleTrigger.refresh();
        else engine.ensureRunning();
        return START_STICKY;
    }

    @Override public void onDestroy(){if(vehicleTrigger!=null)vehicleTrigger.stop();if(engine!=null)engine.detach(this);super.onDestroy();}
'''
)
s=s.replace(
'''        String text=(s.realReady?"버튼 ✓":"버튼 대기")+" · "+(s.commanderReady?"Commander ✓":"Commander 대기")+" · "+s.intervalMs+"ms";
''',
'''        String text=(engine.isVehicleAutoEnabled()?(engine.isDriveSessionActive()?"차량 ✓":"차량 대기"):"항상 연결")+" · "+(s.realReady?"버튼 ✓":"버튼 대기")+" · "+(s.commanderReady?"Commander ✓":"Commander 대기");
'''
)
marker='''    @Override public void onLogLine(String line){}

    private Notification notification(String text){
'''
replacement='''    @Override public void onLogLine(String line){}
    @Override public void onVehicleTrigger(boolean active,String status){engine.setDriveSessionActive(active,status);}
    @Override public void onVehicleLog(String line){}

    private Notification notification(String text){
'''
if marker not in s: raise SystemExit('Service listener insertion point not found')
s=s.replace(marker,replacement)
p.write_text(s)

# MainActivity UI and one-time paired vehicle selector.
p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
s=s.replace(
'''    private TextView realStatus,virtualStatus,commanderStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,log;
''',
'''    private TextView realStatus,virtualStatus,commanderStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,vehicleTriggerStatus,log;
'''
)
s=s.replace(
'''    private Spinner maxSpinner,profileSpinner;
    private Switch testSwitch,liveSwitch,autoReconnectSwitch,backgroundSwitch,vibrationSwitch,disconnectAlertSwitch;
''',
'''    private Spinner maxSpinner,profileSpinner,vehicleSpinner;
    private final java.util.ArrayList<BluetoothDevice> vehicleDevices=new java.util.ArrayList<>();
    private Switch testSwitch,liveSwitch,autoReconnectSwitch,backgroundSwitch,vibrationSwitch,disconnectAlertSwitch,vehicleAutoSwitch,carModeSwitch;
'''
)
s=s.replace(
'''        engine.ensureRunning();
        refreshProfiles();
''',
'''        engine.ensureRunning();
        refreshProfiles();
        refreshVehicleDevices();
'''
)
s=s.replace(
'''    @Override protected void onResume(){super.onResume();if(engine!=null){engine.attach(this);refreshProfiles();}}
''',
'''    @Override protected void onResume(){super.onResume();if(engine!=null){engine.attach(this);refreshProfiles();refreshVehicleDevices();refreshVehicleTrigger();}}
'''
)

auto_marker='''        LinearLayout auto=card();auto.addView(section("⚡ 자동화 / 백그라운드"));
'''
vehicle_card='''        LinearLayout drive=card();drive.addView(section("🚗 차량 자동 연결"));
        vehicleTriggerStatus=status("차량 감지 대기",false);drive.addView(vehicleTriggerStatus,margins(-1,-2,0,8,0,10));
        vehicleAutoSwitch=addSwitch(drive,"차량 Bluetooth 연결 때만 브리지 ON","평소에는 실물 버튼·가상 ENH_BTN 연결을 끊어 배터리 사용을 줄입니다.",true,(b,on)->{if(syncing)return;engine.setVehicleAutoEnabled(on);refreshVehicleTrigger();});
        carModeSwitch=addSwitch(drive,"운전모드도 시작 조건으로 사용","Android가 Car Mode를 알리면 차량 Bluetooth와 별개로 브리지를 시작합니다.",true,(b,on)->{if(syncing)return;engine.setCarModeTriggerEnabled(on);refreshVehicleTrigger();});
        vehicleSpinner=spinner(new String[]{"페어링된 차량 검색 중…"},0);drive.addView(vehicleSpinner,margins(-1,dp(50),0,4,0,8));
        Button saveVehicle=primary("이 Bluetooth 기기를 차량으로 저장");saveVehicle.setOnClickListener(v->saveSelectedVehicle());drive.addView(saveVehicle,margins(-1,dp(46),0,0,0,8));
        TextView driveInfo=body("차량 Bluetooth가 끊기면 15초 대기 후 S3XY 브리지를 자동 종료합니다. 아직 차량을 저장하지 않았다면 Tesla/차량 오디오 기기를 자동 인식할 수도 있습니다.");drive.addView(driveInfo);r.addView(drive,margins(-1,-2,0,0,0,12));

'''
if vehicle_card not in s:
    if auto_marker not in s: raise SystemExit('MainActivity auto card marker not found')
    s=s.replace(auto_marker,vehicle_card+auto_marker)

snap_old='''        syncing=true;if(autoReconnectSwitch!=null)autoReconnectSwitch.setChecked(s.autoReconnect);if(backgroundSwitch!=null)backgroundSwitch.setChecked(engine.isBackgroundEnabled());if(vibrationSwitch!=null)vibrationSwitch.setChecked(s.vibration);if(disconnectAlertSwitch!=null)disconnectAlertSwitch.setChecked(s.disconnectAlert);if(testSwitch!=null)testSwitch.setChecked(s.testMode);if(liveSwitch!=null)liveSwitch.setChecked(!s.testMode);syncing=false;
'''
snap_new='''        syncing=true;if(autoReconnectSwitch!=null)autoReconnectSwitch.setChecked(s.autoReconnect);if(backgroundSwitch!=null)backgroundSwitch.setChecked(engine.isBackgroundEnabled());if(vibrationSwitch!=null)vibrationSwitch.setChecked(s.vibration);if(disconnectAlertSwitch!=null)disconnectAlertSwitch.setChecked(s.disconnectAlert);if(vehicleAutoSwitch!=null)vehicleAutoSwitch.setChecked(engine.isVehicleAutoEnabled());if(carModeSwitch!=null)carModeSwitch.setChecked(engine.isCarModeTriggerEnabled());if(testSwitch!=null)testSwitch.setChecked(s.testMode);if(liveSwitch!=null)liveSwitch.setChecked(!s.testMode);syncing=false;
        if(vehicleTriggerStatus!=null)setStatus(vehicleTriggerStatus,engine.getVehicleTriggerStatus(),engine.isDriveSessionActive());
'''
if snap_old not in s: raise SystemExit('Snapshot switch block not found')
s=s.replace(snap_old,snap_new)

service_marker='''    private void startBridgeService(){Intent i=new Intent(this,BridgeForegroundService.class);try{if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}catch(Exception e){toast("백그라운드 서비스 시작 실패: "+e.getMessage());}}
'''
service_new=service_marker+'''    private void refreshVehicleTrigger(){Intent i=new Intent(this,BridgeForegroundService.class);i.setAction(BridgeForegroundService.ACTION_REFRESH_TRIGGER);try{if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}catch(Exception e){}}
    private void refreshVehicleDevices(){
        if(vehicleSpinner==null||adapter==null||!hasConnect())return;
        vehicleDevices.clear();java.util.ArrayList<String> labels=new java.util.ArrayList<>();int selected=0;String saved=engine.getVehicleTargetAddress();
        try{
            for(BluetoothDevice d:adapter.getBondedDevices()){
                String a=safeAddr(d);String n;try{n=d.getName();}catch(Exception e){n=null;}if(n==null||n.isEmpty())n="Bluetooth 기기";
                vehicleDevices.add(d);labels.add(n+"  ·  "+a);if(a.equalsIgnoreCase(saved))selected=vehicleDevices.size()-1;
            }
        }catch(Exception ignored){}
        if(labels.isEmpty())labels.add("페어링된 Bluetooth 기기 없음");
        vehicleSpinner.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,labels));
        if(!vehicleDevices.isEmpty())vehicleSpinner.setSelection(Math.min(selected,vehicleDevices.size()-1));
    }
    private void saveSelectedVehicle(){
        if(vehicleSpinner==null||vehicleDevices.isEmpty()){toast("먼저 폰 설정에서 차량 Bluetooth를 페어링하세요.");return;}
        int i=vehicleSpinner.getSelectedItemPosition();if(i<0||i>=vehicleDevices.size())return;BluetoothDevice d=vehicleDevices.get(i);
        String n;try{n=d.getName();}catch(Exception e){n="차량";}if(n==null)n="차량";
        engine.setVehicleTarget(safeAddr(d),n);refreshVehicleTrigger();toast("차량 저장됨: "+n);
    }
'''
if service_marker not in s: raise SystemExit('service marker not found')
s=s.replace(service_marker,service_new)

p.write_text(s)
