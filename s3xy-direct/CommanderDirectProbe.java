package com.openai.s3xybridge;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanRecord;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.content.pm.PackageManager;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.UUID;

/**
 * Read-only/notify-oriented probe for the real S3XY Commander BLE surface.
 *
 * This intentionally does not send vendor control payloads. It discovers the
 * actual GATT surface, reads readable characteristics and subscribes to
 * notify/indicate characteristics so the real Commander wire surface can be
 * identified without guessing.
 */
public final class CommanderDirectProbe {
    public interface Listener {
        void onDirectStatus(String status, boolean connected);
        void onDirectLog(String line);
        void onDirectDevice(BluetoothDevice device, String label, int rssi, String advertised);
    }

    private static final long SCAN_MS=12000L;
    private static final UUID CCCD=UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final UUID COMMANDER_SERVICE=UUID.fromString("5857a678-87c6-11eb-8dcd-0242ac130003");

    private static CommanderDirectProbe INSTANCE;
    public static synchronized CommanderDirectProbe get(Context c){
        if(INSTANCE==null)INSTANCE=new CommanderDirectProbe(c.getApplicationContext());
        return INSTANCE;
    }

    private final Context context;
    private final CopyOnWriteArrayList<Listener> listeners=new CopyOnWriteArrayList<>();
    private final SharedPreferences prefs;
    private final BluetoothAdapter adapter;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final StringBuilder report=new StringBuilder();
    private final Set<String> seen=new HashSet<>();
    private final ArrayDeque<Op> ops=new ArrayDeque<>();

    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothDevice device;
    private boolean scanning;
    private boolean connected;
    private boolean opBusy;
    private boolean autoConnecting;
    private boolean wanted;

    private static final class Op {
        static final int READ=1, SUBSCRIBE=2;
        final int type;
        final BluetoothGattCharacteristic characteristic;
        Op(int type,BluetoothGattCharacteristic c){this.type=type;this.characteristic=c;}
    }

    private CommanderDirectProbe(Context c){
        context=c.getApplicationContext();
        prefs=context.getSharedPreferences("s3xy_bridge",Context.MODE_PRIVATE);
        BluetoothManager manager=(BluetoothManager)context.getSystemService(Context.BLUETOOTH_SERVICE);
        adapter=manager==null?null:manager.getAdapter();
        log("DIRECT probe created");
    }

    public void attach(Listener l){if(l!=null&&!listeners.contains(l))listeners.add(l);}
    public void detach(Listener l){if(l!=null)listeners.remove(l);}
    public boolean isWanted(){return wanted;}

    public void startAuto(){
        wanted=true;
        if(connected||autoConnecting||scanning)return;
        startScan();
    }

    public boolean isConnected(){return connected;}
    public boolean isScanning(){return scanning;}
    public String report(){synchronized(report){return report.toString();}}

    public void startScan(){
        wanted=true;
        main.removeCallbacks(scanRetryRunnable);
        if(!hasScan()||!hasConnect()){status("Bluetooth 권한 필요",false);return;}
        if(adapter==null||!adapter.isEnabled()){status("Bluetooth를 켜세요",false);return;}
        stopScan();
        scanner=adapter.getBluetoothLeScanner();
        if(scanner==null){status("BLE scanner 없음",false);return;}
        seen.clear();
        autoConnecting=false;
        scanning=true;
        status("Commander 검색 중…",false);
        log("DIRECT scan start 12s");
        try{
            scanner.startScan(scanCallback);
            main.postDelayed(stopScanRunnable,SCAN_MS);
        }catch(Exception e){
            scanning=false;
            log("DIRECT scan error: "+e);
            status("Commander 검색 실패",false);
        }
    }

    public void stopScan(){
        main.removeCallbacks(stopScanRunnable);
        if(!scanning)return;
        scanning=false;
        if(scanner!=null&&hasScan()){
            try{scanner.stopScan(scanCallback);}catch(Exception ignored){}
        }
        log("DIRECT scan stop");
        if(!connected){
            status(wanted?"Commander 재검색 대기":"Commander 직접 연결 대기",false);
            if(wanted&&!autoConnecting){main.removeCallbacks(scanRetryRunnable);main.postDelayed(scanRetryRunnable,2500);}
        }
    }

    private final Runnable stopScanRunnable=this::stopScan;
    private final Runnable scanRetryRunnable=()->{if(wanted&&!connected&&!autoConnecting)startScan();};

    public void connect(BluetoothDevice d){
        wanted=true;
        connectInternal(d);
    }

    private void connectInternal(BluetoothDevice d){
        if(d==null||!hasConnect()){status("Commander 연결 권한 필요",false);return;}
        autoConnecting=true;
        stopScan();
        closeGatt();
        device=d;
        String label=safeName(d)+" "+safeAddr(d);
        log("DIRECT connect -> "+label);
        status("Commander 직접 연결 중…",false);
        try{
            if(Build.VERSION.SDK_INT>=23)gatt=d.connectGatt(context,false,gattCallback,BluetoothDevice.TRANSPORT_LE);
            else gatt=d.connectGatt(context,false,gattCallback);
            if(gatt==null)status("Commander GATT 생성 실패",false);
        }catch(Exception e){
            log("DIRECT connectGatt exception: "+e);
            status("Commander 직접 연결 실패",false);
        }
    }

    public void rediscover(){
        if(gatt==null||!connected){status("먼저 Commander에 연결하세요",false);return;}
        ops.clear();opBusy=false;
        log("DIRECT rediscoverServices requested");
        try{gatt.discoverServices();}catch(Exception e){log("DIRECT discover exception: "+e);}
    }

    public void disconnect(){
        wanted=false;
        main.removeCallbacks(scanRetryRunnable);
        stopScan();
        closeGatt();
        device=null;
        status("Commander 직접 연결 대기",false);
    }

    private void closeGatt(){
        ops.clear();opBusy=false;connected=false;autoConnecting=false;
        BluetoothGatt old=gatt;gatt=null;
        if(old!=null&&hasConnect()){
            try{old.disconnect();}catch(Exception ignored){}
            try{old.close();}catch(Exception ignored){}
        }
    }

    public void close(){
        wanted=false;
        main.removeCallbacks(scanRetryRunnable);
        main.removeCallbacks(stopScanRunnable);
        stopScan();
        closeGatt();
        device=null;
    }

    private final ScanCallback scanCallback=new ScanCallback(){
        @Override public void onScanResult(int callbackType, ScanResult result){handleScan(result);}
        @Override public void onBatchScanResults(List<ScanResult> results){if(results!=null)for(ScanResult r:results)handleScan(r);}
        @Override public void onScanFailed(int errorCode){
            scanning=false;
            log("DIRECT scan failed code="+errorCode);
            status("Commander 검색 실패 code="+errorCode,false);
        }
    };

    private void handleScan(ScanResult r){
        if(r==null||r.getDevice()==null)return;
        BluetoothDevice d=r.getDevice();
        String addr=safeAddr(d);
        if(addr.isEmpty()||seen.contains(addr))return;
        seen.add(addr);

        ScanRecord record=r.getScanRecord();
        String recordName=null;
        try{recordName=record==null?null:record.getDeviceName();}catch(Exception ignored){}
        String name=recordName;
        if(name==null||name.isEmpty())name=safeName(d);
        if(name==null||name.isEmpty())name="이름 없는 BLE";

        StringBuilder adv=new StringBuilder();
        try{
            if(record!=null&&record.getServiceUuids()!=null){
                for(android.os.ParcelUuid u:record.getServiceUuids()){
                    if(adv.length()>0)adv.append(',');
                    adv.append(u.getUuid());
                }
            }
            if(record!=null&&record.getManufacturerSpecificData()!=null&&record.getManufacturerSpecificData().size()>0){
                if(adv.length()>0)adv.append(" · ");
                adv.append("MFG=");
                for(int i=0;i<record.getManufacturerSpecificData().size();i++){
                    int key=record.getManufacturerSpecificData().keyAt(i);
                    byte[] value=record.getManufacturerSpecificData().valueAt(i);
                    if(i>0)adv.append(';');
                    adv.append(String.format(Locale.US,"%04X:",key)).append(hex(value,24));
                }
            }
        }catch(Exception ignored){}

        String lower=name.toLowerCase(Locale.ROOT);
        boolean likely=lower.contains("commander")||lower.contains("s3xy")||lower.contains("enhance")||lower.contains("enhauto")||lower.contains("enh_");
        boolean commanderUuid=adv.toString().toLowerCase(Locale.ROOT).contains(COMMANDER_SERVICE.toString());
        if(!(likely||commanderUuid))return;
        log("DIRECT scan LIKELY name="+name+" addr="+addr+" rssi="+r.getRssi()+" adv="+adv);
        emitDevice(d,name,r.getRssi(),adv.toString());
        if(!connected&&!autoConnecting&&r.getRssi()>-82){
            autoConnecting=true;
            log("DIRECT auto-select Commander -> "+name+" "+addr);
            main.post(()->connectInternal(d));
        }
    }

    private final BluetoothGattCallback gattCallback=new BluetoothGattCallback(){
        @Override public void onConnectionStateChange(BluetoothGatt source,int statusCode,int newState){
            if(source!=gatt){try{source.close();}catch(Exception ignored){}return;}
            log("DIRECT state status="+statusCode+" newState="+newState+" bond="+safeBond(device));
            if(newState==BluetoothProfile.STATE_CONNECTED&&statusCode==BluetoothGatt.GATT_SUCCESS){
                connected=true;
                autoConnecting=false;
                if(device!=null&&hasConnect())prefs.edit().putString("direct_commander_addr",safeAddr(device)).apply();
                status("Commander 연결됨 · GATT 확인 중",true);
                try{source.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH);}catch(Exception ignored){}
                try{source.requestMtu(517);}catch(Exception ignored){}
                main.postDelayed(()->{
                    BluetoothGatt x=gatt;
                    if(x!=null&&connected)try{x.discoverServices();}catch(Exception e){log("DIRECT discover error: "+e);}
                },250);
            }else if(newState==BluetoothProfile.STATE_DISCONNECTED){
                connected=false;autoConnecting=false;ops.clear();opBusy=false;
                status("Commander 직접 연결 끊김 · status="+statusCode,false);
                if(wanted){main.removeCallbacks(scanRetryRunnable);main.postDelayed(scanRetryRunnable,1200);}
            }else if(statusCode!=BluetoothGatt.GATT_SUCCESS){
                status("Commander GATT 오류="+statusCode,false);
            }
        }

        @Override public void onMtuChanged(BluetoothGatt source,int mtu,int statusCode){
            if(source!=gatt)return;
            log("DIRECT MTU="+mtu+" status="+statusCode);
        }

        @Override public void onServicesDiscovered(BluetoothGatt source,int statusCode){
            if(source!=gatt)return;
            if(statusCode!=BluetoothGatt.GATT_SUCCESS){
                log("DIRECT services failed="+statusCode);
                status("GATT 서비스 검색 실패="+statusCode,false);
                return;
            }
            List<BluetoothGattService> services=source.getServices();
            log("DIRECT SERVICES BEGIN count="+(services==null?0:services.size()));
            ops.clear();opBusy=false;
            if(services!=null){
                for(BluetoothGattService svc:services){
                    log("DIRECT SVC "+svc.getUuid()+" type="+svc.getType());
                    for(BluetoothGattCharacteristic c:svc.getCharacteristics()){
                        int p=c.getProperties();
                        log("DIRECT   CHR "+c.getUuid()+" props="+properties(p)+" perms=0x"+Integer.toHexString(c.getPermissions()));
                        for(BluetoothGattDescriptor d:c.getDescriptors())log("DIRECT     DSC "+d.getUuid()+" perms=0x"+Integer.toHexString(d.getPermissions()));
                        if((p&BluetoothGattCharacteristic.PROPERTY_READ)!=0)ops.addLast(new Op(Op.READ,c));
                        if((p&(BluetoothGattCharacteristic.PROPERTY_NOTIFY|BluetoothGattCharacteristic.PROPERTY_INDICATE))!=0)ops.addLast(new Op(Op.SUBSCRIBE,c));
                    }
                }
            }
            log("DIRECT SERVICES END queuedOps="+ops.size());
            status("Commander GATT 발견 · "+(services==null?0:services.size())+" services",true);
            main.postDelayed(CommanderDirectProbe.this::runNextOp,120);
        }

        @Override public void onCharacteristicRead(BluetoothGatt source,BluetoothGattCharacteristic c,int statusCode){
            if(source!=gatt)return;
            byte[] value=c.getValue();
            log("DIRECT READ "+c.getUuid()+" status="+statusCode+" value="+hex(value,256));
            finishOp();
        }

        @Override public void onCharacteristicRead(BluetoothGatt source,BluetoothGattCharacteristic c,byte[] value,int statusCode){
            if(source!=gatt)return;
            log("DIRECT READ33 "+c.getUuid()+" status="+statusCode+" value="+hex(value,256));
            finishOp();
        }

        @Override public void onDescriptorWrite(BluetoothGatt source,BluetoothGattDescriptor d,int statusCode){
            if(source!=gatt)return;
            log("DIRECT CCCD "+d.getCharacteristic().getUuid()+" status="+statusCode);
            finishOp();
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source,BluetoothGattCharacteristic c){
            if(source!=gatt)return;
            log("DIRECT RX "+c.getUuid()+" value="+hex(c.getValue(),512));
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source,BluetoothGattCharacteristic c,byte[] value){
            if(source!=gatt)return;
            log("DIRECT RX33 "+c.getUuid()+" value="+hex(value,512));
        }
    };

    private void runNextOp(){
        BluetoothGatt x=gatt;
        if(x==null||!connected||opBusy)return;
        Op op=ops.pollFirst();
        if(op==null){
            log("DIRECT GATT probe complete · notifications armed");
            status("Commander 직접 연결됨 · 알림 수집 중",true);
            return;
        }
        opBusy=true;
        boolean started=false;
        try{
            if(op.type==Op.READ){
                log("DIRECT -> READ "+op.characteristic.getUuid());
                started=x.readCharacteristic(op.characteristic);
            }else{
                BluetoothGattCharacteristic c=op.characteristic;
                boolean enable=x.setCharacteristicNotification(c,true);
                BluetoothGattDescriptor d=c.getDescriptor(CCCD);
                log("DIRECT -> SUB "+c.getUuid()+" local="+enable+" cccd="+(d!=null));
                if(enable&&d!=null){
                    byte[] value=(c.getProperties()&BluetoothGattCharacteristic.PROPERTY_INDICATE)!=0
                            ?BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
                            :BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE;
                    if(Build.VERSION.SDK_INT>=33){
                        started=x.writeDescriptor(d,value)==0;
                    }else{
                        d.setValue(value);
                        started=x.writeDescriptor(d);
                    }
                }
            }
        }catch(Exception e){log("DIRECT op exception: "+e);}
        if(!started){
            opBusy=false;
            main.postDelayed(this::runNextOp,80);
        }else{
            main.postDelayed(()->{
                if(opBusy){
                    log("DIRECT op timeout; continue");
                    opBusy=false;
                    runNextOp();
                }
            },3500);
        }
    }

    private void finishOp(){
        if(!opBusy)return;
        opBusy=false;
        main.postDelayed(this::runNextOp,90);
    }

    private void status(String s,boolean ok){
        for(Listener l:listeners)try{l.onDirectStatus(s,ok);}catch(Exception ignored){}
        log("DIRECT STATUS "+s);
    }

    private void log(String s){
        String line=new SimpleDateFormat("HH:mm:ss.SSS",Locale.KOREA).format(new Date())+"   "+s;
        synchronized(report){
            report.append(line).append('\n');
            if(report.length()>180000)report.delete(0,40000);
        }
        for(Listener l:listeners)try{l.onDirectLog(line);}catch(Exception ignored){}
    }

    private void emitDevice(BluetoothDevice d,String label,int rssi,String adv){
        for(Listener l:listeners)try{l.onDirectDevice(d,label,rssi,adv);}catch(Exception ignored){}
    }

    private boolean hasScan(){return Build.VERSION.SDK_INT<31||context.checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN)==PackageManager.PERMISSION_GRANTED;}
    private boolean hasConnect(){return Build.VERSION.SDK_INT<31||context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED;}

    private String safeName(BluetoothDevice d){
        try{
            if(d==null||!hasConnect())return "";
            String n=d.getName();
            return n==null?"":n;
        }catch(Exception e){return "";}
    }
    private String safeAddr(BluetoothDevice d){
        try{return d!=null&&hasConnect()?d.getAddress():"";}catch(Exception e){return "";}
    }
    private int safeBond(BluetoothDevice d){
        try{return d!=null&&hasConnect()?d.getBondState():BluetoothDevice.BOND_NONE;}catch(Exception e){return BluetoothDevice.BOND_NONE;}
    }

    private static String properties(int p){
        StringBuilder s=new StringBuilder();
        if((p&BluetoothGattCharacteristic.PROPERTY_READ)!=0)s.append("R");
        if((p&BluetoothGattCharacteristic.PROPERTY_WRITE)!=0)s.append(" W");
        if((p&BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)!=0)s.append(" WNR");
        if((p&BluetoothGattCharacteristic.PROPERTY_NOTIFY)!=0)s.append(" N");
        if((p&BluetoothGattCharacteristic.PROPERTY_INDICATE)!=0)s.append(" I");
        if((p&BluetoothGattCharacteristic.PROPERTY_SIGNED_WRITE)!=0)s.append(" SW");
        return s.length()==0?"0x"+Integer.toHexString(p):s.toString().trim();
    }

    private static String hex(byte[] value,int max){
        if(value==null)return "null";
        int n=Math.min(value.length,max);
        StringBuilder b=new StringBuilder();
        for(int i=0;i<n;i++){
            if(i>0)b.append(' ');
            b.append(String.format(Locale.US,"%02X",value[i]&0xff));
        }
        if(value.length>n)b.append(" …(").append(value.length).append(" bytes)");
        return b.toString();
    }
}
