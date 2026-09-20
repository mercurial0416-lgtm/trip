package com.openai.s3xybridge;

import android.Manifest;
import android.app.UiModeManager;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothClass;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothProfile;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import java.util.List;
import java.util.Locale;

final class VehicleTriggerManager {
    interface Listener {
        void onVehicleTrigger(boolean active, String status);
        void onVehicleLog(String line);
    }

    private static final long DISCONNECT_GRACE_MS=15000L;
    private final Context context;
    private final SharedPreferences prefs;
    private final Listener listener;
    private final BluetoothAdapter adapter;
    private final Handler main=new Handler(Looper.getMainLooper());

    private boolean started;
    private boolean btConnected;
    private boolean carModeActive;
    private BluetoothProfile a2dp;
    private BluetoothProfile headset;

    VehicleTriggerManager(Context c, Listener l){
        context=c.getApplicationContext();
        prefs=context.getSharedPreferences("bridge_prefs",Context.MODE_PRIVATE);
        listener=l;
        adapter=BluetoothAdapter.getDefaultAdapter();
    }

    void start(){
        if(started)return;
        started=true;
        registerReceiver();
        carModeActive=isCarModeNow();
        requestProfiles();
        publish("차량 감지 대기");
    }

    void stop(){
        if(!started)return;
        started=false;
        main.removeCallbacks(disconnectGrace);
        try{context.unregisterReceiver(receiver);}catch(Exception ignored){}
        if(adapter!=null&&hasConnect()){
            try{if(a2dp!=null)adapter.closeProfileProxy(BluetoothProfile.A2DP,a2dp);}catch(Exception ignored){}
            try{if(headset!=null)adapter.closeProfileProxy(BluetoothProfile.HEADSET,headset);}catch(Exception ignored){}
        }
        a2dp=null;headset=null;
    }

    void refresh(){
        carModeActive=isCarModeNow();
        if(!prefs.getBoolean("vehicle_auto_enabled",true)){
            btConnected=false;
            publish("차량 자동 연결 꺼짐");
            return;
        }
        checkProfiles();
        publish("차량 설정 갱신");
    }

    private void registerReceiver(){
        IntentFilter f=new IntentFilter();
        f.addAction(BluetoothDevice.ACTION_ACL_CONNECTED);
        f.addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED);
        f.addAction(UiModeManager.ACTION_ENTER_CAR_MODE);
        f.addAction(UiModeManager.ACTION_EXIT_CAR_MODE);
        try{
            if(Build.VERSION.SDK_INT>=33)context.registerReceiver(receiver,f,Context.RECEIVER_EXPORTED);
            else context.registerReceiver(receiver,f);
        }catch(Exception e){listener.onVehicleLog("TRIGGER receiver error: "+e.getMessage());}
    }

    private final BroadcastReceiver receiver=new BroadcastReceiver(){
        @Override public void onReceive(Context c,Intent i){
            String action=i.getAction();
            if(UiModeManager.ACTION_ENTER_CAR_MODE.equals(action)){
                carModeActive=true;
                publish("운전모드 시작");
                return;
            }
            if(UiModeManager.ACTION_EXIT_CAR_MODE.equals(action)){
                carModeActive=false;
                publish("운전모드 종료");
                return;
            }
            BluetoothDevice d;
            if(Build.VERSION.SDK_INT>=33)d=i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE,BluetoothDevice.class);
            else d=i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
            if(d==null)return;

            if(BluetoothDevice.ACTION_ACL_CONNECTED.equals(action)){
                if(matchesVehicle(d)){
                    main.removeCallbacks(disconnectGrace);
                    btConnected=true;
                    maybeAutoSelect(d);
                    publish("차량 Bluetooth 연결: "+safeName(d));
                }
            }else if(BluetoothDevice.ACTION_ACL_DISCONNECTED.equals(action)){
                if(matchesVehicle(d)){
                    main.removeCallbacks(disconnectGrace);
                    main.postDelayed(disconnectGrace,DISCONNECT_GRACE_MS);
                    listener.onVehicleLog("TRIGGER vehicle BT disconnected, grace 15s");
                }
            }
        }
    };

    private final Runnable disconnectGrace=()->{
        btConnected=false;
        publish("차량 Bluetooth 연결 끊김");
    };

    private void requestProfiles(){
        if(adapter==null||!hasConnect())return;
        BluetoothProfile.ServiceListener sl=new BluetoothProfile.ServiceListener(){
            @Override public void onServiceConnected(int profile,BluetoothProfile proxy){
                if(profile==BluetoothProfile.A2DP)a2dp=proxy;
                if(profile==BluetoothProfile.HEADSET)headset=proxy;
                checkProfiles();
            }
            @Override public void onServiceDisconnected(int profile){
                if(profile==BluetoothProfile.A2DP)a2dp=null;
                if(profile==BluetoothProfile.HEADSET)headset=null;
            }
        };
        try{adapter.getProfileProxy(context,sl,BluetoothProfile.A2DP);}catch(Exception ignored){}
        try{adapter.getProfileProxy(context,sl,BluetoothProfile.HEADSET);}catch(Exception ignored){}
    }

    private void checkProfiles(){
        if(!prefs.getBoolean("vehicle_auto_enabled",true)||!hasConnect())return;
        BluetoothDevice found=findMatching(a2dp);
        if(found==null)found=findMatching(headset);
        boolean now=found!=null;
        if(now){
            main.removeCallbacks(disconnectGrace);
            maybeAutoSelect(found);
        }
        if(btConnected!=now){
            btConnected=now;
            publish(now?"차량 Bluetooth 이미 연결됨: "+safeName(found):"차량 Bluetooth 대기");
        }
    }

    private BluetoothDevice findMatching(BluetoothProfile p){
        if(p==null)return null;
        try{
            List<BluetoothDevice> ds=p.getConnectedDevices();
            if(ds!=null)for(BluetoothDevice d:ds)if(matchesVehicle(d))return d;
        }catch(Exception ignored){}
        return null;
    }

    private boolean matchesVehicle(BluetoothDevice d){
        if(d==null||!hasConnect())return false;
        String saved=prefs.getString("vehicle_bt_address","");
        String addr=safeAddr(d);
        if(!saved.isEmpty())return saved.equalsIgnoreCase(addr);
        return looksLikeVehicle(d);
    }

    private boolean looksLikeVehicle(BluetoothDevice d){
        String n=safeName(d).toLowerCase(Locale.ROOT);
        if(n.contains("tesla")||n.contains("model 3")||n.contains("model3")||n.contains("model y")||n.contains("model s")||n.contains("model x"))return true;
        try{
            BluetoothClass bc=d.getBluetoothClass();
            return bc!=null&&bc.getDeviceClass()==BluetoothClass.Device.AUDIO_VIDEO_CAR_AUDIO;
        }catch(Exception ignored){return false;}
    }

    private void maybeAutoSelect(BluetoothDevice d){
        if(!prefs.getString("vehicle_bt_address","").isEmpty()||d==null)return;
        prefs.edit().putString("vehicle_bt_address",safeAddr(d)).putString("vehicle_bt_name",safeName(d)).apply();
        listener.onVehicleLog("TRIGGER auto-selected vehicle "+safeName(d)+" "+safeAddr(d));
    }

    private void publish(String why){
        boolean enabled=prefs.getBoolean("vehicle_auto_enabled",true);
        boolean carEnabled=prefs.getBoolean("car_mode_trigger",true);
        boolean active=enabled&&(btConnected||(carEnabled&&carModeActive));
        String name=prefs.getString("vehicle_bt_name","");
        String status=(active?"활성":"대기")+" · "+(btConnected?"차량 BT 연결":"차량 BT 미연결")+
                (carEnabled?(carModeActive?" · 운전모드 ON":" · 운전모드 OFF"):"")+
                (name.isEmpty()?"":" · "+name);
        listener.onVehicleLog("TRIGGER "+why+" -> "+status);
        listener.onVehicleTrigger(active,status);
    }

    private boolean isCarModeNow(){
        if(!prefs.getBoolean("car_mode_trigger",true))return false;
        try{
            UiModeManager u=(UiModeManager)context.getSystemService(Context.UI_MODE_SERVICE);
            return u!=null&&u.getCurrentModeType()==Configuration.UI_MODE_TYPE_CAR;
        }catch(Exception e){return false;}
    }

    private boolean hasConnect(){return Build.VERSION.SDK_INT<31||context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED;}
    private String safeName(BluetoothDevice d){try{String n=d.getName();return n==null?"차량":n;}catch(Exception e){return"차량";}}
    private String safeAddr(BluetoothDevice d){try{return d.getAddress();}catch(Exception e){return"";}}
}
