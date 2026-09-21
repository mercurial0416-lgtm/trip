package com.openai.s3xybridge;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattServer;
import android.bluetooth.BluetoothGattServerCallback;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.AdvertiseCallback;
import android.bluetooth.le.AdvertiseData;
import android.bluetooth.le.AdvertiseSettings;
import android.bluetooth.le.BluetoothLeAdvertiser;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;

import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;

public final class CommanderVirtualButtonServer {
    public interface Listener {
        void onCommanderStatus(String s);
        void onCommanderLog(String s);
        void onCommanderReady(boolean ready);
    }

    private static final long PAIRING_WINDOW_MS=30000L;
    private static final int EARLY_DISCONNECTS_FOR_COMPAT=2;

    private final Context context;
    private final Listener listener;
    private final BluetoothManager manager;
    private final BluetoothAdapter adapter;
    private final SharedPreferences prefs;
    private final Handler main=new Handler(Looper.getMainLooper());

    private BluetoothGattServer server;
    private BluetoothLeAdvertiser advertiser;
    private BluetoothGattCharacteristic notifyChar;
    private BluetoothDevice commander;
    private boolean subscribed;
    private boolean advertising;
    private boolean pairingWindow;
    private boolean bondReceiverRegistered;
    private boolean compatibilityMode;
    private int earlyDisconnects;
    private String savedAdapterName;
    private final byte[] id="BRIDGE0001".getBytes(StandardCharsets.US_ASCII);
    private final ArrayDeque<byte[]> pendingNotifications=new ArrayDeque<>();
    private final Runnable closePairingWindow;

    public CommanderVirtualButtonServer(Context c, Listener l) {
        context=c.getApplicationContext();
        listener=l;
        manager=(BluetoothManager)context.getSystemService(Context.BLUETOOTH_SERVICE);
        adapter=manager==null?null:manager.getAdapter();
        prefs=context.getSharedPreferences("bridge_prefs",Context.MODE_PRIVATE);
        compatibilityMode=prefs.getBoolean("commander_plain_gatt",false);
        closePairingWindow=this::closePairingWindowNow;
    }

    public boolean isReady(){return commander!=null&&subscribed;}
    public boolean isAdvertising(){return advertising;}

    public void start(){
        if(!hasConnect()||!hasAdvertise()){listener.onCommanderStatus("Bluetooth 권한 필요");return;}
        if(adapter==null||!adapter.isEnabled()||!adapter.isMultipleAdvertisementSupported()){
            listener.onCommanderStatus("BLE 광고 미지원 또는 Bluetooth 꺼짐");return;
        }
        closeServerOnly();
        registerBondReceiver();
        openServer();
    }

    public void beginPairingWindow(){
        pairingWindow=true;
        earlyDisconnects=0;
        pendingNotifications.clear();
        main.removeCallbacks(closePairingWindow);
        listener.onCommanderLog("PAIR pairing window opened (30s) compat="+compatibilityMode);
        enablePairingIdentity();

        if(server==null){
            start();
        }else{
            restartAdvertisingDelayed(300);
        }
        listener.onCommanderStatus("페어링 모드 — 공식 S3XY 앱의 버튼 추가 화면에서 대기");
        main.postDelayed(closePairingWindow,PAIRING_WINDOW_MS);
    }

    private void openServer(){
        if(manager==null){listener.onCommanderStatus("Bluetooth manager 없음");return;}
        server=manager.openGattServer(context,callback);
        if(server==null){listener.onCommanderStatus("GATT 서버 생성 실패");return;}

        BluetoothGattService svc=new BluetoothGattService(S3xyProtocol.BUTTON_SERVICE,BluetoothGattService.SERVICE_TYPE_PRIMARY);
        notifyChar=new BluetoothGattCharacteristic(
                S3xyProtocol.BUTTON_NOTIFY,
                BluetoothGattCharacteristic.PROPERTY_READ|BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ);
        notifyChar.setValue(new byte[]{0x00});
        notifyChar.addDescriptor(new BluetoothGattDescriptor(
                S3xyProtocol.CCCD,
                BluetoothGattDescriptor.PERMISSION_READ|BluetoothGattDescriptor.PERMISSION_WRITE));

        int idPerm=compatibilityMode
                ? BluetoothGattCharacteristic.PERMISSION_READ|BluetoothGattCharacteristic.PERMISSION_WRITE
                : BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED|BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED;
        BluetoothGattCharacteristic idChar=new BluetoothGattCharacteristic(
                S3xyProtocol.BUTTON_ID,
                BluetoothGattCharacteristic.PROPERTY_READ|BluetoothGattCharacteristic.PROPERTY_WRITE,
                idPerm);
        idChar.setValue(Arrays.copyOf(id,id.length));
        svc.addCharacteristic(notifyChar);
        svc.addCharacteristic(idChar);

        if(!server.addService(svc)){
            listener.onCommanderStatus("GATT 서비스 등록 실패");
            closeServerOnly();
        }else{
            listener.onCommanderStatus(compatibilityMode
                    ?"Commander용 가상 버튼 준비 중 · 호환 모드"
                    :"Commander용 가상 버튼 준비 중…");
        }
    }

    private void closePairingWindowNow(){
        main.removeCallbacks(closePairingWindow);
        pairingWindow=false;
        restoreAdapterName();
        listener.onCommanderLog("PAIR pairing window closed");
        if(isReady())listener.onCommanderStatus("Commander 준비 완료");
        else{
            restartAdvertisingDelayed(250);
            listener.onCommanderStatus("S3XY 서비스 광고 중");
        }
    }

    public void stop(){
        main.removeCallbacks(closePairingWindow);
        pairingWindow=false;
        closeServerOnly();
        restoreAdapterName();
        unregisterBondReceiver();
        listener.onCommanderReady(false);
    }

    private void closeServerOnly(){
        if(hasAdvertise()&&advertiser!=null&&advertising){
            try{advertiser.stopAdvertising(adCallback);}catch(Exception ignored){}
        }
        advertising=false;
        subscribed=false;
        commander=null;
        pendingNotifications.clear();
        if(hasConnect()&&server!=null){
            try{server.close();}catch(Exception ignored){}
        }
        server=null;
        notifyChar=null;
        advertiser=null;
        listener.onCommanderReady(false);
    }

    public boolean sendSingle(){
        if(!isReady())return false;
        for(byte[] p:S3xyProtocol.singleClickSequence()){notifyBytes(p);sleep(5);}
        return true;
    }
    public boolean sendDouble(){if(!isReady())return false;notifyBytes(S3xyProtocol.doubleClick());return true;}
    public boolean sendLong(){if(!isReady())return false;notifyBytes(S3xyProtocol.longPress());return true;}

    private void advertise(){
        if(!hasAdvertise()||adapter==null||advertising||server==null)return;
        advertiser=adapter.getBluetoothLeAdvertiser();
        if(advertiser==null){listener.onCommanderStatus("BLE advertiser 없음");return;}

        AdvertiseSettings st=new AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                .setConnectable(true)
                .setTimeout(0)
                .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
                .build();

        final AdvertiseData data;
        final AdvertiseData scan;
        if(pairingWindow){
            data=new AdvertiseData.Builder()
                    .setIncludeDeviceName(true)
                    .setIncludeTxPowerLevel(false)
                    .build();
            scan=new AdvertiseData.Builder()
                    .addServiceUuid(new ParcelUuid(S3xyProtocol.BUTTON_SERVICE))
                    .setIncludeDeviceName(false)
                    .build();
        }else{
            data=new AdvertiseData.Builder()
                    .addServiceUuid(new ParcelUuid(S3xyProtocol.BUTTON_SERVICE))
                    .setIncludeDeviceName(false)
                    .setIncludeTxPowerLevel(false)
                    .build();
            scan=new AdvertiseData.Builder().setIncludeDeviceName(false).build();
        }
        try{advertiser.startAdvertising(st,data,scan,adCallback);}
        catch(Exception e){listener.onCommanderLog("PAIR advertise exception: "+e.getMessage());}
    }

    private void restartAdvertisingDelayed(long delay){
        main.postDelayed(()->{
            if(server==null||adapter==null||!adapter.isEnabled())return;
            try{
                if(advertiser!=null&&advertising)advertiser.stopAdvertising(adCallback);
            }catch(Exception ignored){}
            advertising=false;
            advertise();
        },delay);
    }

    private void enablePairingIdentity(){
        if(adapter==null||!hasConnect())return;
        try{
            if(savedAdapterName==null)savedAdapterName=adapter.getName();
            boolean ok=adapter.setName("ENH_BTN");
            listener.onCommanderLog("PAIR temporary local name ENH_BTN set="+ok);
        }catch(Exception e){listener.onCommanderLog("PAIR temporary name error: "+e.getMessage());}
    }

    private void restoreAdapterName(){
        if(adapter==null||!hasConnect()||savedAdapterName==null)return;
        try{
            boolean ok=adapter.setName(savedAdapterName);
            listener.onCommanderLog("PAIR local name restored set="+ok);
        }catch(Exception e){listener.onCommanderLog("PAIR restore name error: "+e.getMessage());}
        savedAdapterName=null;
    }

    private void enterCompatibilityMode(){
        if(compatibilityMode||!pairingWindow)return;
        compatibilityMode=true;
        prefs.edit().putBoolean("commander_plain_gatt",true).apply();
        listener.onCommanderLog("PAIR switching to plain-GATT compatibility mode after early disconnects");
        listener.onCommanderStatus("Commander 호환 모드로 자동 재시도…");
        main.postDelayed(()->{
            if(!pairingWindow)return;
            closeServerOnly();
            openServer();
        },500);
    }

    private final AdvertiseCallback adCallback=new AdvertiseCallback(){
        @Override public void onStartSuccess(AdvertiseSettings s){
            advertising=true;
            listener.onCommanderLog("PAIR advertising started name="+(pairingWindow?"ENH_BTN":"hidden")+" compat="+compatibilityMode);
            listener.onCommanderStatus(pairingWindow
                    ?"페어링 모드 — ENH_BTN 광고 중"
                    :"S3XY 서비스 광고 중");
        }
        @Override public void onStartFailure(int e){
            advertising=false;
            listener.onCommanderLog("PAIR advertising failure code="+e);
            listener.onCommanderStatus("광고 실패 code="+e);
        }
    };

    private final BluetoothGattServerCallback callback=new BluetoothGattServerCallback(){
        @Override public void onServiceAdded(int status,BluetoothGattService service){
            if(status==BluetoothGatt.GATT_SUCCESS){
                if(pairingWindow)main.postDelayed(CommanderVirtualButtonServer.this::advertise,250);
                else advertise();
            }else listener.onCommanderStatus("서비스 등록 오류="+status);
        }

        @Override public void onConnectionStateChange(BluetoothDevice d,int status,int state){
            if(state==android.bluetooth.BluetoothProfile.STATE_CONNECTED&&status==BluetoothGatt.GATT_SUCCESS){
                commander=d;
                pendingNotifications.clear();
                int bond=safeBond(d);
                listener.onCommanderLog("PAIR Commander connected "+safeAddr(d)+" status="+status+" bond="+bondState(bond)+" compat="+compatibilityMode);
                if(bond==BluetoothDevice.BOND_BONDED)listener.onCommanderStatus("Commander 연결됨 · 알림 구독 대기");
                else if(bond==BluetoothDevice.BOND_BONDING)listener.onCommanderStatus("Commander 연결됨 · 본딩 진행 중");
                else listener.onCommanderStatus("Commander 연결됨 · 보안 핸드셰이크 대기");
            }else if(state==android.bluetooth.BluetoothProfile.STATE_DISCONNECTED){
                boolean wasReady=subscribed;
                listener.onCommanderLog("PAIR Commander disconnected "+safeAddr(d)+" status="+status+" ready="+wasReady);
                commander=null;
                subscribed=false;
                pendingNotifications.clear();
                listener.onCommanderReady(false);
                if(pairingWindow&&!wasReady){
                    earlyDisconnects++;
                    listener.onCommanderLog("PAIR early disconnect count="+earlyDisconnects);
                    if(earlyDisconnects>=EARLY_DISCONNECTS_FOR_COMPAT&&!compatibilityMode){
                        enterCompatibilityMode();
                        return;
                    }
                }
                listener.onCommanderStatus(pairingWindow
                        ?"Commander 연결 끊김 — 자동 재광고 중"
                        :"Commander 연결 끊김 — 광고 유지");
                restartAdvertisingDelayed(350);
            }else if(status!=BluetoothGatt.GATT_SUCCESS){
                listener.onCommanderLog("PAIR connection state error status="+status+" state="+state);
            }
        }

        @Override public void onCharacteristicReadRequest(BluetoothDevice d,int req,int off,BluetoothGattCharacteristic c){
            if(server==null)return;
            byte[] v=S3xyProtocol.BUTTON_ID.equals(c.getUuid())?Arrays.copyOf(id,id.length):new byte[]{0x00};
            listener.onCommanderLog("PAIR read "+c.getUuid()+" off="+off+" bond="+bondState(safeBond(d)));
            if(off>v.length){server.sendResponse(d,req,BluetoothGatt.GATT_INVALID_OFFSET,off,null);return;}
            server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,Arrays.copyOfRange(v,off,v.length));
        }

        @Override public void onCharacteristicWriteRequest(BluetoothDevice d,int req,BluetoothGattCharacteristic c,boolean prep,boolean response,int off,byte[] v){
            if(response&&server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,v);
            if(!S3xyProtocol.BUTTON_ID.equals(c.getUuid())||v==null)return;
            listener.onCommanderLog("PAIR ID write "+S3xyProtocol.hex(v)+" subscribed="+subscribed+" bond="+bondState(safeBond(d)));
            if(S3xyProtocol.equals(v,0xB6)){
                queueOrNotify(S3xyProtocol.initReply());
                listener.onCommanderLog(subscribed?"PAIR handshake B6 -> C7 00 01":"PAIR handshake B6 queued until CCCD subscribe");
            }else if(S3xyProtocol.equals(v,0xA1)&&server!=null){
                listener.onCommanderLog("PAIR Commander requested disconnect A1");
                server.cancelConnection(d);
            }else if(v.length==4&&(v[0]&0xFF)==0xA4){
                queueOrNotify(new byte[]{(byte)0xA4,0x00,v[1],v[2]});
            }
        }

        @Override public void onDescriptorWriteRequest(BluetoothDevice d,int req,BluetoothGattDescriptor desc,boolean prep,boolean response,int off,byte[] v){
            if(S3xyProtocol.CCCD.equals(desc.getUuid())){
                subscribed=Arrays.equals(v,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                int queued=pendingNotifications.size();
                listener.onCommanderLog("PAIR CCCD "+(subscribed?"enabled":"disabled")+" pending="+queued);
                listener.onCommanderReady(isReady());
                listener.onCommanderStatus(subscribed?"Commander 준비 완료":"Commander 알림 해제됨");
                if(subscribed){
                    if(queued>0)flushPendingNotifications();
                    else notifyBytes(new byte[]{0x00});
                    if(pairingWindow)main.postDelayed(CommanderVirtualButtonServer.this::closePairingWindowNow,800);
                }
            }
            if(response&&server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,v);
        }

        @Override public void onDescriptorReadRequest(BluetoothDevice d,int req,int off,BluetoothGattDescriptor desc){
            if(server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,
                    subscribed?BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE:BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE);
        }

        @Override public void onMtuChanged(BluetoothDevice d,int mtu){
            listener.onCommanderLog("PAIR MTU="+mtu);
        }

        @Override public void onNotificationSent(BluetoothDevice d,int status){
            listener.onCommanderLog("PAIR notification sent status="+status);
        }
    };

    private final BroadcastReceiver bondReceiver=new BroadcastReceiver(){
        @Override public void onReceive(Context c,Intent i){
            if(!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(i.getAction()))return;
            BluetoothDevice d;
            if(Build.VERSION.SDK_INT>=33)d=i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE,BluetoothDevice.class);
            else d=i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
            if(d==null||commander==null||!safeAddr(d).equals(safeAddr(commander)))return;
            int state=i.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE,BluetoothDevice.ERROR);
            int prev=i.getIntExtra(BluetoothDevice.EXTRA_PREVIOUS_BOND_STATE,BluetoothDevice.ERROR);
            listener.onCommanderLog("PAIR bond "+bondState(prev)+" -> "+bondState(state));
            if(state==BluetoothDevice.BOND_BONDED)listener.onCommanderStatus("Commander 본딩 완료 · 초기화 대기");
            else if(state==BluetoothDevice.BOND_BONDING)listener.onCommanderStatus("Commander 본딩 진행 중…");
            else if(state==BluetoothDevice.BOND_NONE&&prev==BluetoothDevice.BOND_BONDING)
                listener.onCommanderStatus("Commander 본딩 해제/실패 · 자동 재광고 대기");
        }
    };

    private void registerBondReceiver(){
        if(bondReceiverRegistered)return;
        try{
            IntentFilter f=new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
            if(Build.VERSION.SDK_INT>=33)context.registerReceiver(bondReceiver,f,Context.RECEIVER_EXPORTED);
            else context.registerReceiver(bondReceiver,f);
            bondReceiverRegistered=true;
        }catch(Exception e){listener.onCommanderLog("PAIR bond receiver error: "+e.getMessage());}
    }

    private void unregisterBondReceiver(){
        if(!bondReceiverRegistered)return;
        try{context.unregisterReceiver(bondReceiver);}catch(Exception ignored){}
        bondReceiverRegistered=false;
    }

    private void queueOrNotify(byte[] v){
        if(v==null)return;
        if(isReady()){
            notifyBytes(v);
            return;
        }
        if(pendingNotifications.size()>=8)pendingNotifications.removeFirst();
        pendingNotifications.addLast(Arrays.copyOf(v,v.length));
    }

    private void flushPendingNotifications(){
        while(isReady()&&!pendingNotifications.isEmpty()){
            notifyBytes(pendingNotifications.removeFirst());
            sleep(8);
        }
    }

    private void notifyBytes(byte[] v){
        if(!hasConnect()||server==null||commander==null||notifyChar==null||!subscribed)return;
        listener.onCommanderLog("TX -> Commander: "+S3xyProtocol.hex(v));
        if(Build.VERSION.SDK_INT>=33){
            int r=server.notifyCharacteristicChanged(commander,notifyChar,false,v);
            if(r!=0)listener.onCommanderLog("PAIR notify start status="+r);
        }else{
            notifyChar.setValue(v);
            boolean ok=server.notifyCharacteristicChanged(commander,notifyChar,false);
            if(!ok)listener.onCommanderLog("PAIR notify start failed");
        }
    }

    private int safeBond(BluetoothDevice d){
        try{return hasConnect()?d.getBondState():BluetoothDevice.BOND_NONE;}catch(Exception e){return BluetoothDevice.BOND_NONE;}
    }
    private static String bondState(int s){
        if(s==BluetoothDevice.BOND_BONDED)return "BONDED";
        if(s==BluetoothDevice.BOND_BONDING)return "BONDING";
        if(s==BluetoothDevice.BOND_NONE)return "NONE";
        return "UNKNOWN("+s+")";
    }
    private boolean hasConnect(){return Build.VERSION.SDK_INT<31||context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED;}
    private boolean hasAdvertise(){return Build.VERSION.SDK_INT<31||context.checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE)==PackageManager.PERMISSION_GRANTED;}
    private String safeAddr(BluetoothDevice d){try{return hasConnect()?d.getAddress():"?";}catch(Exception e){return"?";}}
    private static void sleep(long ms){try{Thread.sleep(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}}
}
