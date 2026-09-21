package com.openai.s3xybridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

public class BridgeForegroundService extends Service implements BridgeEngine.Listener, VehicleTriggerManager.Listener {
    private static final String CHANNEL="s3xy_bridge";
    private static final int ID=2301;
    public static final String ACTION_REFRESH_TRIGGER="com.openai.s3xybridge.REFRESH_VEHICLE_TRIGGER";
    private BridgeEngine engine;
    private CommanderDirectProbe directProbe;
    private VehicleTriggerManager vehicleTrigger;

    @Override public void onCreate(){
        super.onCreate();
        createChannel();
        engine=BridgeEngine.get(this);
        directProbe=CommanderDirectProbe.get(this);
        engine.attach(this);
        startForeground(ID,notification("차량 감지 시작"));
        vehicleTrigger=new VehicleTriggerManager(this,this);
        vehicleTrigger.start();
        engine.ensureRunning();
        syncDirect();
    }

    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(engine==null)engine=BridgeEngine.get(this);
        if(vehicleTrigger==null){vehicleTrigger=new VehicleTriggerManager(this,this);vehicleTrigger.start();}
        if(intent!=null&&ACTION_REFRESH_TRIGGER.equals(intent.getAction()))vehicleTrigger.refresh();
        else engine.ensureRunning();
        syncDirect();
        return START_STICKY;
    }

    @Override public void onDestroy(){if(vehicleTrigger!=null)vehicleTrigger.stop();if(engine!=null)engine.detach(this);super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}

    private void syncDirect(){
        if(directProbe==null)directProbe=CommanderDirectProbe.get(this);
        if(engine.isFastHighBeamMode()){
            directProbe.stopScan();
            directProbe.disconnect();
            engine.ensureRunning();
            return;
        }
        engine.stopCommander();
        if(!engine.isVehicleAutoEnabled()||engine.isDriveSessionActive()||engine.isManualSetupOverrideActive())directProbe.startAuto();
        else directProbe.disconnect();
    }

    @Override public void onSnapshot(BridgeEngine.Snapshot s){
        String text=(engine.isVehicleAutoEnabled()?(engine.isDriveSessionActive()?"차량 ✓":"차량 대기"):"항상 연결")+" · "+(s.realReady?"버튼 ✓":"버튼 대기")+" · "+(s.commanderReady?"Commander ✓":"Commander 대기");
        NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        if(nm!=null)nm.notify(ID,notification(text));
    }
    @Override public void onLogLine(String line){}
    @Override public void onVehicleTrigger(boolean active,String status){engine.setDriveSessionActive(active,status);syncDirect();}
    @Override public void onVehicleLog(String line){}

    private Notification notification(String text){
        Intent i=new Intent(this,MainActivity.class);i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi=PendingIntent.getActivity(this,0,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,CHANNEL):new Notification.Builder(this);
        return b.setContentTitle("S3XY Button Bridge 실행 중").setContentText(text).setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
                .setContentIntent(pi).setOngoing(true).setOnlyAlertOnce(true).build();
    }

    private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(nm!=null){NotificationChannel c=new NotificationChannel(CHANNEL,"S3XY Bridge",NotificationManager.IMPORTANCE_LOW);c.setDescription("S3XY 버튼 브리지를 백그라운드에서 유지합니다.");nm.createNotificationChannel(c);}}}
}
