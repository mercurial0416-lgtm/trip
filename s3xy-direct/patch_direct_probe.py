from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

# Install the direct Commander BLE probe.
probe=Path('s3xy-direct/CommanderDirectProbe.java').read_text()
(root/'app/src/main/java/com/openai/s3xybridge/CommanderDirectProbe.java').write_text(probe)

# v0.7.0
p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 11','versionCode 12')
s=s.replace("versionName '0.6.5-pairing-compat'","versionName '0.7.0-commander-direct-lab'")
if 'versionCode 12' not in s or "versionName '0.7.0-commander-direct-lab'" not in s:
    raise SystemExit('0.7.0 version bump failed')
p.write_text(s)

p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()

s=s.replace(
'public class MainActivity extends Activity implements BridgeEngine.Listener {',
'public class MainActivity extends Activity implements BridgeEngine.Listener, CommanderDirectProbe.Listener {'
)
s=s.replace(
'private static final int REQ_PERMS=10, REQ_EXPORT=301, REQ_IMPORT=302;',
'private static final int REQ_PERMS=10, REQ_EXPORT=301, REQ_IMPORT=302, REQ_DIRECT_EXPORT=304;'
)
s=s.replace(
'''    private BridgeEngine engine;
    private UpdateManager updater;
''',
'''    private BridgeEngine engine;
    private UpdateManager updater;
    private CommanderDirectProbe directProbe;
'''
)
s=s.replace(
'''    private final Map<String,BluetoothDevice> found=new LinkedHashMap<>();
''',
'''    private final Map<String,BluetoothDevice> found=new LinkedHashMap<>();
    private final Map<String,BluetoothDevice> directFound=new LinkedHashMap<>();
'''
)
s=s.replace(
'''    private TextView realStatus,virtualStatus,commanderStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,vehicleTriggerStatus,log;
    private LinearLayout scanResults,chipRow;
    private Button scanButton,virtualButton;
''',
'''    private TextView realStatus,virtualStatus,commanderStatus,directStatus,bridgeStatus,lastEventValue,sessionPulseValue,totalHoldsValue,totalPulseValue,totalTimeValue,lastDeviceValue,vehicleTriggerStatus,log;
    private LinearLayout scanResults,directResults,chipRow;
    private Button scanButton,virtualButton,directScanButton;
'''
)
s=s.replace(
'''        engine=BridgeEngine.get(this);
        updater=new UpdateManager(this);
        setContentView(buildUi());
''',
'''        engine=BridgeEngine.get(this);
        updater=new UpdateManager(this);
        directProbe=new CommanderDirectProbe(this,this);
        setContentView(buildUi());
'''
)
s=s.replace(
'''    @Override protected void onDestroy(){stopScan();if(updater!=null)updater.close();engine.detach(this);super.onDestroy();}
''',
'''    @Override protected void onDestroy(){stopScan();if(directProbe!=null)directProbe.close();if(updater!=null)updater.close();engine.detach(this);super.onDestroy();}
'''
)

physical='''        scanResults=new LinearLayout(this);scanResults.setOrientation(LinearLayout.VERTICAL);pc.addView(scanResults,margins(-1,-2,0,10,0,0));r.addView(pc,margins(-1,-2,0,0,0,12));

'''
direct='''        scanResults=new LinearLayout(this);scanResults.setOrientation(LinearLayout.VERTICAL);pc.addView(scanResults,margins(-1,-2,0,10,0,0));r.addView(pc,margins(-1,-2,0,0,0,12));

        LinearLayout dc=deviceCard("⌁","Commander Direct Lab","보드 없이 폰이 Commander에 직접 BLE 연결합니다. 현재 버전은 안전하게 GATT 구조·읽기값·알림만 자동 수집합니다.");
        directStatus=status("Commander 직접 연결 대기",false);dc.addView(directStatus,margins(-2,-2,0,8,0,8));
        TextView directHelp=body("공식 S3XY 앱을 완전히 종료한 뒤 검색하세요. 검색 결과에서 Commander로 보이는 기기를 누르면 서비스/특성 UUID와 notify를 자동 기록합니다. 임의 차량 제어 명령은 보내지 않습니다.");
        directHelp.setTextColor(Color.rgb(177,214,255));dc.addView(directHelp,margins(-1,-2,0,2,0,10));
        directScanButton=primary("Commander BLE 검색 (12초)");directScanButton.setOnClickListener(v->startDirectScan());dc.addView(directScanButton,margins(-1,dp(48),0,0,0,8));
        LinearLayout dbtns=new LinearLayout(this);dbtns.setOrientation(LinearLayout.HORIZONTAL);
        Button directDrop=secondary("직접 연결 끊기");directDrop.setOnClickListener(v->{if(directProbe!=null)directProbe.disconnect();});dbtns.addView(directDrop,new LinearLayout.LayoutParams(0,dp(44),1f));
        Button directDump=secondary("GATT 다시 읽기");directDump.setOnClickListener(v->{if(directProbe!=null)directProbe.rediscover();});LinearLayout.LayoutParams ddp=new LinearLayout.LayoutParams(0,dp(44),1f);ddp.setMargins(dp(8),0,0,0);dbtns.addView(directDump,ddp);dc.addView(dbtns);
        Button directExport=secondary("Commander 진단 리포트 저장");directExport.setOnClickListener(v->exportDirectReport());dc.addView(directExport,margins(-1,dp(44),0,8,0,8));
        directResults=new LinearLayout(this);directResults.setOrientation(LinearLayout.VERTICAL);dc.addView(directResults,margins(-1,-2,0,2,0,0));
        r.addView(dc,margins(-1,-2,0,0,0,12));

'''
if physical not in s: raise SystemExit('physical card insertion point missing')
s=s.replace(physical,direct,1)

s=s.replace(
'''        LinearLayout vc=deviceCard("</>","Virtual ENH_BTN","Commander가 인식하는 가상 버튼");
''',
'''        LinearLayout vc=deviceCard("</>","Legacy Virtual ENH_BTN","기존 가상 버튼 방식 · Commander 호환성 문제 때문에 Direct Lab을 우선 사용하세요.");
'''
)

# Direct callbacks/methods are inserted before the existing physical scan section.
anchor='''    // BLE scan is UI-only. Engine owns the actual connection after selection.
'''
methods=r'''    private void startDirectScan(){
        if(!hasScan()||!hasConnect()){requestNeededPermissions();return;}
        stopScan();
        if(directProbe==null)return;
        directFound.clear();
        if(directResults!=null)directResults.removeAllViews();
        if(directScanButton!=null)directScanButton.setText("Commander 검색 중…");
        directProbe.startScan();
        main.postDelayed(()->{if(directScanButton!=null)directScanButton.setText("Commander BLE 검색 (12초)");},12500);
    }

    private void exportDirectReport(){
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        i.setType("text/plain");
        i.putExtra(Intent.EXTRA_TITLE,"s3xy-commander-direct-report.txt");
        startActivityForResult(i,REQ_DIRECT_EXPORT);
    }

    @Override public void onDirectStatus(String s,boolean connected){runOnUiThread(()->{
        setStatus(directStatus,s,connected);
        if(directScanButton!=null&&!s.contains("검색 중"))directScanButton.setText("Commander BLE 검색 (12초)");
    });}

    @Override public void onDirectLog(String line){runOnUiThread(()->{
        if(log!=null)log.append(line+"\n");
    });}

    @Override public void onDirectDevice(BluetoothDevice d,String label,int rssi,String advertised){runOnUiThread(()->{
        if(directResults==null||d==null)return;
        String addr=safeAddr(d);
        if(addr.isEmpty()||directFound.containsKey(addr)||directFound.size()>=30)return;
        directFound.put(addr,d);
        String lower=(label==null?"":label).toLowerCase(Locale.ROOT);
        boolean likely=lower.contains("commander")||lower.contains("s3xy")||lower.contains("enhance")||lower.contains("enhauto");
        String title=(likely?"★ ":"")+(label==null||label.isEmpty()?"이름 없는 BLE":label)+"  ·  "+addr+"  ·  "+rssi+" dBm";
        Button b=secondary(title);
        b.setTextSize(11);
        b.setOnClickListener(v->{
            engine.stopCommander();
            directProbe.stopScan();
            directProbe.connect(d);
            if(directResults!=null)directResults.removeAllViews();
        });
        directResults.addView(b,margins(-1,dp(46),0,4,0,0));
        if(advertised!=null&&!advertised.isEmpty()){
            TextView a=body("ADV: "+advertised);
            a.setTextIsSelectable(true);
            directResults.addView(a,margins(-1,-2,0,1,0,3));
        }
    });}

'''
if anchor not in s: raise SystemExit('scan anchor missing')
s=s.replace(anchor,methods+anchor,1)

# Prevent direct and physical scanners from fighting.
s=s.replace(
'''    private void startScan(){if(!hasPermissions()){requestNeededPermissions();return;}if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}if(scanning)return;scanner=adapter.getBluetoothLeScanner();''',
'''    private void startScan(){if(!hasPermissions()){requestNeededPermissions();return;}if(adapter==null||!adapter.isEnabled()){toast("Bluetooth를 켜세요");return;}if(directProbe!=null)directProbe.stopScan();if(scanning)return;scanner=adapter.getBluetoothLeScanner();'''
)

old_result='''    @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(req==UpdateManager.REQ_INSTALL_UNKNOWN){if(updater!=null)updater.onActivityResult(req);return;}if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();try{if(req==REQ_EXPORT){OutputStream o=getContentResolver().openOutputStream(u);if(o!=null){o.write(engine.exportJson().getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();toast("설정 내보냄");}}else if(req==REQ_IMPORT){InputStream in=getContentResolver().openInputStream(u);if(in!=null){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=in.read(buf))>0)b.write(buf,0,n);in.close();boolean ok=engine.importJson(b.toString("UTF-8"));refreshProfiles();toast(ok?"설정 불러옴":"설정 파일 오류");}}}catch(Exception e){toast("파일 처리 실패: "+e.getMessage());}}
'''
new_result='''    @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(req==UpdateManager.REQ_INSTALL_UNKNOWN){if(updater!=null)updater.onActivityResult(req);return;}if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();try{if(req==REQ_EXPORT){OutputStream o=getContentResolver().openOutputStream(u);if(o!=null){o.write(engine.exportJson().getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();toast("설정 내보냄");}}else if(req==REQ_DIRECT_EXPORT){OutputStream o=getContentResolver().openOutputStream(u);if(o!=null){StringBuilder b=new StringBuilder();b.append("S3XY Commander Direct Lab\\n");b.append("App: 0.7.0-commander-direct-lab\\n\\n");if(directProbe!=null)b.append(directProbe.report());b.append("\\n--- Combined UI log ---\\n");if(log!=null)b.append(log.getText());o.write(b.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();toast("Commander 진단 리포트 저장됨");}}else if(req==REQ_IMPORT){InputStream in=getContentResolver().openInputStream(u);if(in!=null){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=in.read(buf))>0)b.write(buf,0,n);in.close();boolean ok=engine.importJson(b.toString("UTF-8"));refreshProfiles();toast(ok?"설정 불러옴":"설정 파일 오류");}}}catch(Exception e){toast("파일 처리 실패: "+e.getMessage());}}
'''
if old_result not in s: raise SystemExit('onActivityResult block missing')
s=s.replace(old_result,new_result,1)

p.write_text(s)
print('v0.7.0 Commander Direct Lab patch applied')
