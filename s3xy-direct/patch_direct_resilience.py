from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')
p=root/'app/src/main/java/com/openai/s3xybridge/CommanderDirectProbe.java'
s=p.read_text()

# A connectGatt() attempt can occasionally never deliver a terminal callback.
# Without a watchdog autoConnecting stays true forever and startAuto() can no-op forever.
s=s.replace(
'    private static final long SCAN_MS=12000L;\n',
'    private static final long SCAN_MS=12000L;\n    private static final long CONNECT_TIMEOUT_MS=15000L;\n'
)

s=s.replace(
'    private final Runnable scanRetryRunnable=()->{if(wanted&&!connected&&!autoConnecting)startScan();};\n',
'''    private final Runnable scanRetryRunnable=()->{if(wanted&&!connected&&!autoConnecting)startScan();};
    private final Runnable connectTimeoutRunnable=()->{
        if(!connected&&autoConnecting){
            log("DIRECT connect timeout; reset GATT and rescan");
            closeGatt();
            status("Commander 연결 시간 초과 · 재검색",false);
            if(wanted)main.postDelayed(scanRetryRunnable,700);
        }
    };
'''
)

s=s.replace(
'''            if(Build.VERSION.SDK_INT>=23)gatt=d.connectGatt(context,false,gattCallback,BluetoothDevice.TRANSPORT_LE);
            else gatt=d.connectGatt(context,false,gattCallback);
            if(gatt==null){
''',
'''            if(Build.VERSION.SDK_INT>=23)gatt=d.connectGatt(context,false,gattCallback,BluetoothDevice.TRANSPORT_LE);
            else gatt=d.connectGatt(context,false,gattCallback);
            main.removeCallbacks(connectTimeoutRunnable);
            if(gatt!=null)main.postDelayed(connectTimeoutRunnable,CONNECT_TIMEOUT_MS);
            if(gatt==null){
'''
)

s=s.replace(
'''    private void closeGatt(){
        ops.clear();opBusy=false;connected=false;autoConnecting=false;
''',
'''    private void closeGatt(){
        main.removeCallbacks(connectTimeoutRunnable);
        ops.clear();opBusy=false;connected=false;autoConnecting=false;
'''
)

s=s.replace(
'''            if(newState==BluetoothProfile.STATE_CONNECTED&&statusCode==BluetoothGatt.GATT_SUCCESS){
                connected=true;
''',
'''            if(newState==BluetoothProfile.STATE_CONNECTED&&statusCode==BluetoothGatt.GATT_SUCCESS){
                main.removeCallbacks(connectTimeoutRunnable);
                connected=true;
'''
)

s=s.replace(
'''            }else if(newState==BluetoothProfile.STATE_DISCONNECTED){
                connected=false;autoConnecting=false;ops.clear();opBusy=false;
''',
'''            }else if(newState==BluetoothProfile.STATE_DISCONNECTED){
                main.removeCallbacks(connectTimeoutRunnable);
                connected=false;autoConnecting=false;ops.clear();opBusy=false;
'''
)

# Once a Commander has connected successfully its address is persisted. Prefer that exact
# device on later scans so a nearby S3XY Button/other ENH_* device cannot win the race.
old='''        if(!connected&&!autoConnecting&&r.getRssi()>-82){
            autoConnecting=true;
            log("DIRECT auto-select Commander -> "+name+" "+addr);
            main.post(()->connectInternal(d));
        }
'''
new='''        String saved=prefs.getString("direct_commander_addr","");
        boolean savedMatch=!saved.isEmpty()&&saved.equalsIgnoreCase(addr);
        boolean mayAuto=saved.isEmpty()||savedMatch;
        if(!connected&&!autoConnecting&&r.getRssi()>-82&&mayAuto){
            autoConnecting=true;
            log("DIRECT auto-select Commander -> "+name+" "+addr+(savedMatch?" [saved]":" [first-use]"));
            main.post(()->connectInternal(d));
        }else if(!saved.isEmpty()&&!savedMatch){
            log("DIRECT skip non-saved candidate -> "+name+" "+addr);
        }
'''
if old not in s:
    raise SystemExit('auto-select block missing')
s=s.replace(old,new,1)

required=['CONNECT_TIMEOUT_MS=15000L','connect timeout; reset GATT and rescan','skip non-saved candidate']
for token in required:
    if token not in s: raise SystemExit('resilience patch failed: '+token)

p.write_text(s)
print('Commander Direct resilience patch applied')
