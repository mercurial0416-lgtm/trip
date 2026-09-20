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
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CommanderVirtualButtonServer {
    public interface Listener {
        void onCommanderStatus(String s);
        void onCommanderLog(String s);
        void onCommanderReady(boolean ready);
    }

    private final Context context;
    private final Listener listener;
    private final BluetoothManager manager;
    private final BluetoothAdapter adapter;
    private final Handler main=new Handler(Looper.getMainLooper());

    private BluetoothGattServer server;
    private BluetoothLeAdvertiser advertiser;
    private BluetoothGattCharacteristic notifyChar;
    private BluetoothDevice commander;
    private boolean subscribed;
    private boolean advertising;
    private boolean pairingWindow;
    private boolean bondReceiverRegistered;
    private String oldName;
    private final byte[] id="BRIDGE0001".getBytes(StandardCharsets.US_ASCII);
    private final Runnable closePairingWindow;

    public CommanderVirtualButtonServer(Context c, Listener l) {
        context=c.getApplicationContext();
        listener=l;
        manager=(BluetoothManager)context.getSystemService(Context.BLUETOOTH_SERVICE);
        adapter=manager==null?null:manager.getAdapter();
        closePairingWindow=this::closePairingWindowNow;
    }

    public boolean isReady(){return commander!=null&&subscribed;}
    public boolean isAdvertising(){return advertising;}

    public void start(){
        if(!hasConnect()||!hasAdvertise()){listener.onCommanderStatus("Bluetooth 권한 필요");return;}
        if(adapter==null||!adapter.isEnabled()||!adapter.isMultipleAdvertisementSupported()){
            listener.onCommanderStatus("BLE 광고 미지원 또는 Bluetooth 꺼짐");return;
        }
        stop();
        registerBondReceiver();
        oldName=adapter.getName();
        try{adapter.setName("ENH_BTN");}catch(Exception ignored){}
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

        BluetoothGattCharacteristic idChar=new BluetoothGattCharacteristic(
                S3xyProtocol.BUTTON_ID,
                BluetoothGattCharacteristic.PROPERTY_READ|BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED|BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED);
        idChar.setValue(Arrays.copyOf(id,id.length));
        svc.addCharacteristic(notifyChar);
        svc.addCharacteristic(idChar);

        if(!server.addService(svc)){
            listener.onCommanderStatus("GATT 서비스 등록 실패");
            stop();
        }else{
            listener.onCommanderStatus("Commander용 가상 버튼 준비 중…");
        }
    }

    /**
     * Real S3XY buttons are put into discoverable/pairable state by holding them.
     * The virtual implementation is already connectable, so this restarts the
     * advertisement and proactively requests LE bonding as soon as Commander connects.
     */
    public void beginPairingWindow(){
        pairingWindow=true;
        listener.onCommanderLog("PAIR pairing window opened (20s)");
        if(server==null){
            start();
        }else if(commander!=null){
            listener.onCommanderStatus("페어링 모드 — Commander 본딩 요청 중");
            requestBond(commander);
        }else{
            restartAdvertising();
            listener.onCommanderStatus("페어링 모드 — 공식 앱에서 버튼 추가를 진행하세요");
        }
        main.removeCallbacks(closePairingWindow);
        main.postDelayed(closePairingWindow,20000);
    }

    private void closePairingWindowNow(){
        pairingWindow=false;
        listener.onCommanderLog("PAIR pairing window closed");
        if(isReady())listener.onCommanderStatus("Commander 준비 완료");
        else if(advertising)listener.onCommanderStatus("ENH_BTN 광고 중 — Commander에서 버튼 추가");
    }

    public void stop(){
        main.removeCallbacks(closePairingWindow);
        pairingWindow=false;
        if(hasAdvertise()&&advertiser!=null&&advertising){
            try{advertiser.stopAdvertising(adCallback);}catch(Exception ignored){}
        }
        advertising=false;
        subscribed=false;
        commander=null;
        if(hasConnect()&&server!=null){
            try{server.close();}catch(Exception ignored){}
        }
        server=null;
        notifyChar=null;
        advertiser=null;
        listener.onCommanderReady(false);
        unregisterBondReceiver();
        if(hasConnect()&&adapter!=null&&oldName!=null){
            try{adapter.setName(oldName);}catch(Exception ignored){}
        }
        oldName=null;
    }

    public boolean sendSingle(){
        if(!isReady())return false;
        for(byte[] p:S3xyProtocol.singleClickSequence()){notifyBytes(p);sleep(5);}
        return true;
    }
    public boolean sendDouble(){if(!isReady())return false;notifyBytes(S3xyProtocol.doubleClick());return true;}
    public boolean sendLong(){if(!isReady())return false;notifyBytes(S3xyProtocol.longPress());return true;}

    private void advertise(){
        if(!hasAdvertise()||adapter==null||advertising)return;
        advertiser=adapter.getBluetoothLeAdvertiser();
        if(advertiser==null){listener.onCommanderStatus("BLE advertiser 없음");return;}

        AdvertiseSettings st=new AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                .setConnectable(true)
                .setTimeout(0)
                .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
                .build();

        // Mirrors the tested virtual-button layout as closely as Android exposes:
        // device name in ADV, complete service UUID in scan response.
        AdvertiseData data=new AdvertiseData.Builder()
                .setIncludeDeviceName(true)
                .setIncludeTxPowerLevel(false)
                .build();
        AdvertiseData scan=new AdvertiseData.Builder()
                .addServiceUuid(new ParcelUuid(S3xyProtocol.BUTTON_SERVICE))
                .build();

        advertiser.startAdvertising(st,data,scan,adCallback);
    }

    private void restartAdvertising(){
        if(!hasAdvertise()||adapter==null)return;
        try{
            if(advertiser!=null&&advertising)advertiser.stopAdvertising(adCallback);
        }catch(Exception ignored){}
        advertising=false;
        advertise();
    }

    private void requestBond(BluetoothDevice d){
        if(d==null||!hasConnect())return;
        try{
            int state=d.getBondState();
            listener.onCommanderLog("PAIR bond state="+bondState(state)+" "+safeAddr(d));
            if(state==BluetoothDevice.BOND_BONDED){
                listener.onCommanderStatus("Commander 본딩 완료 — 알림 구독 대기");
                return;
            }
            if(state==BluetoothDevice.BOND_BONDING){
                listener.onCommanderStatus("Commander 본딩 진행 중…");
                return;
            }
            boolean started=d.createBond();
            listener.onCommanderLog("PAIR createBond()="+started);
            listener.onCommanderStatus(started?"Commander 본딩 시작…":"Commander 본딩 요청 실패 — 다시 시도");
        }catch(Exception e){
            listener.onCommanderLog("PAIR createBond error: "+e.getMessage());
            listener.onCommanderStatus("Commander 본딩 오류");
        }
    }

    private final AdvertiseCallback adCallback=new AdvertiseCallback(){
        @Override public void onStartSuccess(AdvertiseSettings s){
            advertising=true;
            listener.onCommanderStatus(pairingWindow
                    ?"페어링 모드 — 공식 앱의 '꾹 누르세요' 화면에서 대기"
                    :"ENH_BTN 광고 중 — Commander에서 버튼 추가");
        }
        @Override public void onStartFailure(int e){
            advertising=false;
            listener.onCommanderStatus("광고 실패 code="+e);
        }
    };

    private final BluetoothGattServerCallback callback=new BluetoothGattServerCallback(){
        @Override public void onServiceAdded(int status,BluetoothGattService service){
            if(status==BluetoothGatt.GATT_SUCCESS)advertise();
            else listener.onCommanderStatus("서비스 등록 오류="+status);
        }

        @Override public void onConnectionStateChange(BluetoothDevice d,int status,int state){
            if(state==android.bluetooth.BluetoothProfile.STATE_CONNECTED){
                commander=d;
                listener.onCommanderLog("Commander connected "+safeAddr(d)+" status="+status+" bond="+bondState(safeBond(d)));
                listener.onCommanderStatus("Commander 연결 — 보안 본딩 확인 중");
                // Android's encrypted ID characteristic will also trigger security on access,
                // but proactively starting bonding makes the pairing flow deterministic.
                if(pairingWindow||safeBond(d)!=BluetoothDevice.BOND_BONDED)requestBond(d);
                else listener.onCommanderStatus("Commander 본딩됨 — 알림 구독 대기");
            }else if(state==android.bluetooth.BluetoothProfile.STATE_DISCONNECTED){
                listener.onCommanderLog("Commander disconnected "+safeAddr(d)+" status="+status);
                commander=null;
                subscribed=false;
                listener.onCommanderReady(false);
                listener.onCommanderStatus(pairingWindow
                        ?"Commander 연결 끊김 — 페어링 광고 유지"
                        :"Commander 연결 끊김 — 광고 유지");
                if(!advertising)restartAdvertising();
            }
        }

        @Override public void onCharacteristicReadRequest(BluetoothDevice d,int req,int off,BluetoothGattCharacteristic c){
            if(server==null)return;
            byte[] v=S3xyProtocol.BUTTON_ID.equals(c.getUuid())?Arrays.copyOf(id,id.length):new byte[]{0x00};
            if(off>v.length){server.sendResponse(d,req,BluetoothGatt.GATT_INVALID_OFFSET,off,null);return;}
            server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,Arrays.copyOfRange(v,off,v.length));
        }

        @Override public void onCharacteristicWriteRequest(BluetoothDevice d,int req,BluetoothGattCharacteristic c,boolean prep,boolean response,int off,byte[] v){
            if(response&&server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,v);
            if(!S3xyProtocol.BUTTON_ID.equals(c.getUuid())||v==null)return;
            listener.onCommanderLog("ID write "+S3xyProtocol.hex(v));
            if(S3xyProtocol.equals(v,0xB6)){
                notifyBytes(S3xyProtocol.initReply());
                listener.onCommanderLog("PAIR handshake B6 -> C7 00 01");
            }else if(S3xyProtocol.equals(v,0xA1)&&server!=null){
                server.cancelConnection(d);
            }else if(v.length==4&&(v[0]&0xFF)==0xA4){
                notifyBytes(new byte[]{(byte)0xA4,0x00,v[1],v[2]});
            }
        }

        @Override public void onDescriptorWriteRequest(BluetoothDevice d,int req,BluetoothGattDescriptor desc,boolean prep,boolean response,int off,byte[] v){
            if(S3xyProtocol.CCCD.equals(desc.getUuid())){
                subscribed=Arrays.equals(v,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                listener.onCommanderLog("PAIR CCCD "+(subscribed?"enabled":"disabled"));
                listener.onCommanderReady(isReady());
                listener.onCommanderStatus(subscribed?"Commander 준비 완료":"Commander 알림 해제됨");
                if(subscribed)notifyBytes(new byte[]{0x00});
            }
            if(response&&server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,v);
        }

        @Override public void onDescriptorReadRequest(BluetoothDevice d,int req,int off,BluetoothGattDescriptor desc){
            if(server!=null)server.sendResponse(d,req,BluetoothGatt.GATT_SUCCESS,off,
                    subscribed?BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE:BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE);
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
            if(state==BluetoothDevice.BOND_BONDED){
                listener.onCommanderStatus("Commander 본딩 완료 — 초기화 대기");
            }else if(state==BluetoothDevice.BOND_NONE&&prev==BluetoothDevice.BOND_BONDING){
                listener.onCommanderStatus("Commander 본딩 실패 — 페어링 다시 시도");
                if(pairingWindow)main.postDelayed(()->requestBond(commander),800);
            }else if(state==BluetoothDevice.BOND_BONDING){
                listener.onCommanderStatus("Commander 본딩 진행 중…");
            }
        }
    };

    private void registerBondReceiver(){
        if(bondReceiverRegistered)return;
        try{
            IntentFilter f=new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
            if(Build.VERSION.SDK_INT>=33)context.registerReceiver(bondReceiver,f,Context.RECEIVER_EXPORTED);
            else context.registerReceiver(bondReceiver,f);
            bondReceiverRegistered=true;
        }catch(Exception e){
            listener.onCommanderLog("PAIR bond receiver error: "+e.getMessage());
        }
    }

    private void unregisterBondReceiver(){
        if(!bondReceiverRegistered)return;
        try{context.unregisterReceiver(bondReceiver);}catch(Exception ignored){}
        bondReceiverRegistered=false;
    }

    private void notifyBytes(byte[] v){
        if(!hasConnect()||server==null||commander==null||notifyChar==null||!subscribed)return;
        listener.onCommanderLog("TX -> Commander: "+S3xyProtocol.hex(v));
        if(Build.VERSION.SDK_INT>=33){
            int r=server.notifyCharacteristicChanged(commander,notifyChar,false,v);
            if(r!=0)listener.onCommanderLog("notify status="+r);
        }else{
            notifyChar.setValue(v);
            server.notifyCharacteristicChanged(commander,notifyChar,false);
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
