from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# v0.6.3 resilience build: keep reconnecting without stale GATT callbacks
# poisoning a newer connection, and recover after Bluetooth is toggled off/on.
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 8','versionCode 9')
s=s.replace("versionName '0.6.2-no-bt-rename'","versionName '0.6.3-resilience'")
if "versionCode 9" not in s or "versionName '0.6.3-resilience'" not in s:
    raise SystemExit('version bump source not found')
p.write_text(s)

# Replace the real-button GATT client with a generation-safe implementation.
# The old client accepted callbacks from already-closed GATT objects; those stale
# callbacks could mark a newer connection as disconnected. It also had no setup
# timeout, so service discovery/bonding stalls could leave auto-reconnect stuck.
real = r'''package com.openai.s3xybridge;

import android.Manifest;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import java.util.Arrays;

/** Connects to a real ENH_BTN as the BLE central and exposes raw button notifications. */
public final class RealButtonClient {
    public interface Listener {
        void onRealStatus(String s);
        void onRealLog(String s);
        void onRealReady(boolean ready);
        void onRealEvent(S3xyProtocol.Event event, byte[] raw);
    }

    private static final long CONNECT_TIMEOUT_MS=30000L;

    private final Context context;
    private final Listener listener;
    private final Handler main = new Handler(Looper.getMainLooper());
    private BluetoothGatt gatt;
    private BluetoothDevice device;
    private BluetoothGattCharacteristic notifyChar;
    private BluetoothGattCharacteristic idChar;
    private boolean subscribed;
    private boolean ready;
    private boolean connecting;
    private boolean receiverRegistered;

    public RealButtonClient(Context c, Listener l) {
        context=c.getApplicationContext(); listener=l;
        IntentFilter f=new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        if(Build.VERSION.SDK_INT>=33)context.registerReceiver(bondReceiver,f,Context.RECEIVER_EXPORTED);
        else context.registerReceiver(bondReceiver,f);
        receiverRegistered=true;
    }

    public void connect(BluetoothDevice d) {
        if (!hasConnect()) { listener.onRealStatus("Bluetooth 연결 권한 필요"); return; }
        closeCurrent(false);
        device=d;
        connecting=true;
        listener.onRealStatus("실물 버튼 연결 중…");
        listener.onRealLog("connectGatt "+safeAddr(d)+" bond="+safeBond(d));
        try {
            gatt=d.connectGatt(context,false,callback,BluetoothDevice.TRANSPORT_LE);
            if(gatt==null){
                connecting=false;
                listener.onRealStatus("실물 버튼 연결 끊김 — GATT 생성 실패");
                return;
            }
            main.removeCallbacks(connectTimeout);
            main.postDelayed(connectTimeout,CONNECT_TIMEOUT_MS);
        } catch(Exception e) {
            connecting=false;
            gatt=null;
            listener.onRealLog("connectGatt error: "+e.getMessage());
            listener.onRealStatus("실물 버튼 연결 끊김 — 연결 시작 실패");
        }
    }

    public void disconnect() {
        closeCurrent(true);
        device=null;
    }

    public void close() {
        disconnect();
        if (receiverRegistered) { try { context.unregisterReceiver(bondReceiver); } catch(Exception ignored) {} receiverRegistered=false; }
    }

    public boolean isReady(){ return ready; }
    public boolean isConnecting(){ return connecting; }

    private void closeCurrent(boolean notifyReady) {
        main.removeCallbacks(connectTimeout);
        ready=false; connecting=false; subscribed=false; notifyChar=null; idChar=null;
        if(notifyReady)listener.onRealReady(false);
        BluetoothGatt old=gatt;
        gatt=null;
        if (hasConnect() && old!=null) {
            try { old.disconnect(); } catch(Exception ignored) {}
            try { old.close(); } catch(Exception ignored) {}
        }
    }

    private void failCurrent(BluetoothGatt source,String reason) {
        if(source!=null && source!=gatt){ closeStale(source); return; }
        listener.onRealLog("connection failed: "+reason);
        closeCurrent(true);
        listener.onRealStatus("실물 버튼 연결 끊김 — "+reason);
    }

    private void closeStale(BluetoothGatt stale) {
        if(stale==null)return;
        try{stale.close();}catch(Exception ignored){}
        listener.onRealLog("ignored stale GATT callback");
    }

    private boolean isCurrent(BluetoothGatt source) {
        if(source==gatt)return true;
        closeStale(source);
        return false;
    }

    private final Runnable connectTimeout=()->{
        if(!connecting||ready)return;
        BluetoothGatt local=gatt;
        if(local==null)return;
        failCurrent(local,"연결/초기화 시간 초과");
    };

    private final BroadcastReceiver bondReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            if (!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(i.getAction())) return;
            BluetoothDevice d = Build.VERSION.SDK_INT>=33 ? i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE,BluetoothDevice.class) : i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
            if (d==null || device==null || !safeAddr(d).equals(safeAddr(device))) return;
            int state=i.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE,BluetoothDevice.BOND_NONE);
            listener.onRealLog("bond state="+state);
            if (state==BluetoothDevice.BOND_BONDED) main.postDelayed(RealButtonClient.this::writeHandshake,250);
        }
    };

    private final BluetoothGattCallback callback = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt g,int status,int newState) {
            if(!isCurrent(g))return;
            if (newState==android.bluetooth.BluetoothProfile.STATE_CONNECTED && status==BluetoothGatt.GATT_SUCCESS) {
                connecting=true;
                listener.onRealStatus("실물 버튼 연결됨 — 서비스 확인 중");
                listener.onRealLog("real connected status="+status);
                if (hasConnect()) {
                    boolean started=false;
                    try{started=g.discoverServices();}catch(Exception ignored){}
                    if(!started)failCurrent(g,"서비스 검색 시작 실패");
                } else failCurrent(g,"Bluetooth 연결 권한 없음");
            } else if (newState==android.bluetooth.BluetoothProfile.STATE_DISCONNECTED) {
                failCurrent(g,"GATT 연결 종료 status="+status);
            } else if(status!=BluetoothGatt.GATT_SUCCESS) {
                failCurrent(g,"GATT 오류 status="+status+" state="+newState);
            }
        }

        @Override public void onServicesDiscovered(BluetoothGatt g,int status) {
            if(!isCurrent(g))return;
            if (status!=BluetoothGatt.GATT_SUCCESS) { failCurrent(g,"서비스 검색 실패="+status); return; }
            BluetoothGattService svc=g.getService(S3xyProtocol.BUTTON_SERVICE);
            if (svc==null) { failCurrent(g,"S3XY 서비스(3D46) 없음"); return; }
            notifyChar=svc.getCharacteristic(S3xyProtocol.BUTTON_NOTIFY);
            idChar=svc.getCharacteristic(S3xyProtocol.BUTTON_ID);
            if (notifyChar==null || idChar==null) { failCurrent(g,"S3XY characteristic 누락"); return; }
            listener.onRealLog("service ready notify=3D50 id=3D49");
            boolean notifyEnabled=false;
            try{notifyEnabled=hasConnect()&&g.setCharacteristicNotification(notifyChar,true);}catch(Exception ignored){}
            if (!notifyEnabled) { failCurrent(g,"Notify 활성화 실패"); return; }
            BluetoothGattDescriptor cccd=notifyChar.getDescriptor(S3xyProtocol.CCCD);
            if (cccd==null) { failCurrent(g,"CCCD 없음"); return; }
            try {
                if (Build.VERSION.SDK_INT>=33) {
                    int r=g.writeDescriptor(cccd,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    if(r!=0)failCurrent(g,"CCCD write 시작 실패="+r);
                } else {
                    cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    if(!g.writeDescriptor(cccd))failCurrent(g,"CCCD write 시작 실패");
                }
            } catch(Exception e){failCurrent(g,"CCCD write 오류");}
        }

        @Override public void onDescriptorWrite(BluetoothGatt g,BluetoothGattDescriptor d,int status) {
            if(!isCurrent(g))return;
            if (!S3xyProtocol.CCCD.equals(d.getUuid())) return;
            if (status!=BluetoothGatt.GATT_SUCCESS) { failCurrent(g,"Notify 구독 실패="+status); return; }
            subscribed=true; listener.onRealLog("real notify subscribed");
            if (device!=null && hasConnect() && safeBond(device)!=BluetoothDevice.BOND_BONDED) {
                listener.onRealStatus("실물 버튼 보안 페어링 중…");
                boolean started=false;
                try{started=device.createBond();}catch(Exception ignored){}
                listener.onRealLog("createBond="+started);
                if (!started) main.postDelayed(RealButtonClient.this::writeHandshake,250);
            } else writeHandshake();
        }

        @Override public void onCharacteristicWrite(BluetoothGatt g,BluetoothGattCharacteristic c,int status) {
            if(!isCurrent(g))return;
            if (S3xyProtocol.BUTTON_ID.equals(c.getUuid())) listener.onRealLog("B6 write status="+status);
            if (S3xyProtocol.BUTTON_ID.equals(c.getUuid()) && status!=BluetoothGatt.GATT_SUCCESS) {
                listener.onRealStatus("Handshake write 실패="+status+" — 페어링 재시도");
                if (device!=null && hasConnect()) try { device.createBond(); } catch(Exception ignored) {}
            }
        }

        @Override public void onCharacteristicChanged(BluetoothGatt g,BluetoothGattCharacteristic c) {
            if(!isCurrent(g))return;
            handleNotify(c.getValue());
        }
        @Override public void onCharacteristicChanged(BluetoothGatt g,BluetoothGattCharacteristic c,byte[] value) {
            if(!isCurrent(g))return;
            handleNotify(value);
        }
    };

    private void writeHandshake() {
        BluetoothGatt local=gatt;
        if (!hasConnect() || local==null || idChar==null || !subscribed) return;
        byte[] b=new byte[]{(byte)0xB6};
        listener.onRealLog("TX -> real button: B6");
        try {
            if (Build.VERSION.SDK_INT>=33) {
                int r=local.writeCharacteristic(idChar,b,BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
                if(r!=0)listener.onRealLog("B6 write start status="+r);
            } else {
                idChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);idChar.setValue(b);
                if(!local.writeCharacteristic(idChar))listener.onRealLog("B6 write start failed");
            }
        } catch(Exception e){listener.onRealLog("B6 write exception: "+e.getMessage());}
    }

    private void handleNotify(byte[] raw) {
        if (raw==null) return;
        byte[] copy=Arrays.copyOf(raw,raw.length);
        S3xyProtocol.Event e=S3xyProtocol.parseEvent(copy);
        listener.onRealLog("RX <- real button: "+S3xyProtocol.hex(copy)+"  "+e);
        if (e==S3xyProtocol.Event.HANDSHAKE_ACK) {
            ready=true; connecting=false; main.removeCallbacks(connectTimeout);
            listener.onRealReady(true); listener.onRealStatus("실물 S3XY Button 준비 완료");
        }
        listener.onRealEvent(e,copy);
    }

    private int safeBond(BluetoothDevice d){try{return hasConnect()?d.getBondState():BluetoothDevice.BOND_NONE;}catch(Exception e){return BluetoothDevice.BOND_NONE;}}
    private boolean hasConnect(){ return Build.VERSION.SDK_INT<31 || context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED; }
    private String safeAddr(BluetoothDevice d){ try{return hasConnect()?d.getAddress():"?";}catch(Exception e){return "?";} }
}
'''
(root/'app/src/main/java/com/openai/s3xybridge/RealButtonClient.java').write_text(real)

# BridgeEngine reconnect coordinator hardening.
p=root/'app/src/main/java/com/openai/s3xybridge/BridgeEngine.java'
s=p.read_text()

s=s.replace(
'''    private boolean manualDisconnect;
    private int reconnectAttempt;
''',
'''    private boolean manualDisconnect;
    private boolean disconnectAlerted;
    private int reconnectAttempt;
''')

s=s.replace(
'''        applyMappedProfile(a);
        realClient.connect(d);
        publish();
''',
'''        applyMappedProfile(a);
        main.removeCallbacks(reconnectRunnable);
        realClient.connect(d);
        publish();
''')

old='''    public void setAutoReconnect(boolean b){prefs.edit().putBoolean("auto_reconnect",b).apply(); if(b)scheduleReconnect(100);else main.removeCallbacks(reconnectRunnable);publish();}
'''
new='''    public void setAutoReconnect(boolean b){prefs.edit().putBoolean("auto_reconnect",b).apply();if(b){manualDisconnect=false;scheduleReconnect(100);}else main.removeCallbacks(reconnectRunnable);publish();}
'''
if old not in s: raise SystemExit('setAutoReconnect block not found')
s=s.replace(old,new)

old='''        if(s.contains("연결 끊김")&&!manualDisconnect){bridge.forceStop("연결 끊김");if(isDisconnectAlert()&&shouldAutoRun()){vibrate(new long[]{0,100,80,180});log("ALERT 실물 버튼 연결 끊김");}if(isAutoReconnect()&&shouldAutoRun())scheduleReconnect(nextBackoff());}
'''
new='''        if(s.contains("연결 끊김")&&!manualDisconnect){
            bridge.forceStop("연결 끊김");
            if(isDisconnectAlert()&&shouldAutoRun()&&!disconnectAlerted){disconnectAlerted=true;vibrate(new long[]{0,100,80,180});log("ALERT 실물 버튼 연결 끊김");}
            if(isAutoReconnect()&&shouldAutoRun())scheduleReconnect(nextBackoff());
        }
'''
if old not in s: raise SystemExit('onRealStatus reconnect block not found')
s=s.replace(old,new)

old='''        realReady=r;if(r){reconnectAttempt=0;realStatus="연결됨";prefs.edit().putLong("last_connected_at",System.currentTimeMillis()).apply();vibrate(35);}publish();
'''
new='''        realReady=r;if(r){reconnectAttempt=0;disconnectAlerted=false;main.removeCallbacks(reconnectRunnable);realStatus="연결됨";prefs.edit().putLong("last_connected_at",System.currentTimeMillis()).apply();vibrate(35);}publish();
'''
if old not in s: raise SystemExit('onRealReady block not found')
s=s.replace(old,new)

old='''    private void doReconnect(){
        if(!isAutoReconnect()||manualDisconnect||realReady||!shouldAutoRun())return;
        String addr=prefs.getString("last_device","");
        if(addr.isEmpty()||adapter==null||!adapter.isEnabled()||!hasConnect())return;
        try{log("AUTO reconnect -> "+addr);realClient.connect(adapter.getRemoteDevice(addr));}
        catch(Exception e){log("AUTO reconnect failed: "+e.getMessage());scheduleReconnect(nextBackoff());}
    }
'''
new='''    private void doReconnect(){
        if(!isAutoReconnect()||manualDisconnect||realReady||!shouldAutoRun())return;
        String addr=prefs.getString("last_device","");
        if(addr.isEmpty())return;
        if(adapter==null||!hasConnect()){
            log("AUTO reconnect 대기 — Bluetooth 권한/어댑터 확인");
            scheduleReconnect(15000);
            return;
        }
        if(!adapter.isEnabled()){
            log("AUTO reconnect 대기 — Bluetooth OFF");
            scheduleReconnect(15000);
            return;
        }
        if(realClient.isConnecting()){
            scheduleReconnect(5000);
            return;
        }
        try{
            log("AUTO reconnect #"+(reconnectAttempt+1)+" -> "+addr);
            realClient.connect(adapter.getRemoteDevice(addr));
        }catch(Exception e){
            log("AUTO reconnect failed: "+e.getMessage());
            scheduleReconnect(nextBackoff());
        }
    }
'''
if old not in s: raise SystemExit('doReconnect block not found')
s=s.replace(old,new)

old='''    private long nextBackoff(){long[] v={1000,2000,5000,10000,15000};return v[Math.min(reconnectAttempt++,v.length-1)];}
'''
new='''    private long nextBackoff(){long[] v={1000,2000,5000,10000,20000,30000,60000};return v[Math.min(reconnectAttempt++,v.length-1)];}
'''
if old not in s: raise SystemExit('backoff block not found')
s=s.replace(old,new)

# Reset outage state when a drive session is deliberately suspended.
old='''        realReady=false;
        realStatus="차량 대기";
'''
new='''        realReady=false;
        reconnectAttempt=0;
        disconnectAlerted=false;
        realStatus="차량 대기";
'''
if old not in s: raise SystemExit('suspend state block not found')
s=s.replace(old,new,1)

p.write_text(s)

# Vehicle trigger recovery after phone Bluetooth is toggled.
p=root/'app/src/main/java/com/openai/s3xybridge/VehicleTriggerManager.java'
s=p.read_text()
s=s.replace(
'''        f.addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED);
        f.addAction(UiModeManager.ACTION_ENTER_CAR_MODE);
''',
'''        f.addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED);
        f.addAction(BluetoothAdapter.ACTION_STATE_CHANGED);
        f.addAction(UiModeManager.ACTION_ENTER_CAR_MODE);
''')

old='''        checkProfiles();
        publish("차량 설정 갱신");
'''
new='''        if(a2dp==null&&headset==null)requestProfiles();
        checkProfiles();
        publish("차량 설정 갱신");
'''
if old not in s: raise SystemExit('vehicle refresh block not found')
s=s.replace(old,new,1)

needle='''            String action=i.getAction();
            if(UiModeManager.ACTION_ENTER_CAR_MODE.equals(action)){
'''
repl='''            String action=i.getAction();
            if(BluetoothAdapter.ACTION_STATE_CHANGED.equals(action)){
                int state=i.getIntExtra(BluetoothAdapter.EXTRA_STATE,BluetoothAdapter.ERROR);
                if(state==BluetoothAdapter.STATE_OFF||state==BluetoothAdapter.STATE_TURNING_OFF){
                    main.removeCallbacks(disconnectGrace);
                    btConnected=false;a2dp=null;headset=null;
                    publish("폰 Bluetooth 꺼짐");
                }else if(state==BluetoothAdapter.STATE_ON){
                    main.postDelayed(()->{if(!started)return;requestProfiles();checkProfiles();publish("폰 Bluetooth 다시 켜짐");},800);
                }
                return;
            }
            if(UiModeManager.ACTION_ENTER_CAR_MODE.equals(action)){
'''
if needle not in s: raise SystemExit('vehicle receiver insertion point not found')
s=s.replace(needle,repl,1)
p.write_text(s)

print('v0.6.3 resilience patch applied')
