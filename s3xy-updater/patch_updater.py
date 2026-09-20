from pathlib import Path

root=Path('/tmp/src/S3XYButtonBridgeAndroid')

p=root/'app/build.gradle'
s=p.read_text()
s=s.replace('versionCode 3','versionCode 4').replace("versionName '0.3.0-full'","versionName '0.4.0-updater'")
p.write_text(s)

p=root/'app/src/main/AndroidManifest.xml'
s=p.read_text()
needle='    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />'
repl=needle+'\n    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />'
if 'android.permission.INTERNET' not in s:
    s=s.replace(needle,repl)
p.write_text(s)

src=Path('s3xy-updater/UpdateManager.java').read_text()
(root/'app/src/main/java/com/openai/s3xybridge/UpdateManager.java').write_text(src)

p=root/'app/src/main/java/com/openai/s3xybridge/MainActivity.java'
s=p.read_text()
if 'private UpdateManager updater;' not in s:
    s=s.replace('    private BridgeEngine engine;\n','    private BridgeEngine engine;\n    private UpdateManager updater;\n')
    s=s.replace('        engine=BridgeEngine.get(this);\n        setContentView(buildUi());','        engine=BridgeEngine.get(this);\n        updater=new UpdateManager(this);\n        setContentView(buildUi());')
    s=s.replace('        refreshProfiles();\n    }','        refreshProfiles();\n        main.postDelayed(()->updater.check(false),1200);\n    }',1)
    s=s.replace('@Override protected void onDestroy(){stopScan();engine.detach(this);super.onDestroy();}','@Override protected void onDestroy(){stopScan();if(updater!=null)updater.close();engine.detach(this);super.onDestroy();}')

needle='''        LinearLayout cfg=card();cfg.addView(section("⇄ 설정 백업"));
        Button export=primary("설정 내보내기 (.json)");export.setOnClickListener(v->exportConfig());cfg.addView(export,margins(-1,dp(46),0,0,0,8));
        Button imp=secondary("설정 불러오기");imp.setOnClickListener(v->importConfig());cfg.addView(imp,margins(-1,dp(44),0,0,0,0));r.addView(cfg,margins(-1,-2,0,0,0,12));
'''
if '⬆ 앱 업데이트' not in s:
    repl=needle+'''
        LinearLayout upd=card();upd.addView(section("⬆ 앱 업데이트"));
        TextView updateStatus=body("현재 버전 확인 중…");upd.addView(updateStatus,margins(-1,-2,0,7,0,10));updater.bindStatus(updateStatus);
        Button checkUpdate=primary("업데이트 확인");checkUpdate.setOnClickListener(v->updater.check(true));upd.addView(checkUpdate,margins(-1,dp(46),0,0,0,0));
        TextView updateInfo=body("새 버전이 있으면 앱 안에서 다운로드하고 설치 화면까지 바로 연결합니다.");upd.addView(updateInfo,margins(-1,-2,0,9,0,0));r.addView(upd,margins(-1,-2,0,0,0,12));
'''
    if needle not in s: raise SystemExit('backup block not found')
    s=s.replace(needle,repl)

old='''    @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();try{if(req==REQ_EXPORT){OutputStream o=getContentResolver().openOutputStream(u);if(o!=null){o.write(engine.exportJson().getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();toast("설정 내보냄");}}else if(req==REQ_IMPORT){InputStream in=getContentResolver().openInputStream(u);if(in!=null){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=in.read(buf))>0)b.write(buf,0,n);in.close();boolean ok=engine.importJson(b.toString("UTF-8"));refreshProfiles();toast(ok?"설정 불러옴":"설정 파일 오류");}}}catch(Exception e){toast("파일 처리 실패: "+e.getMessage());}}
'''
new='''    @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(req==UpdateManager.REQ_INSTALL_UNKNOWN){if(updater!=null)updater.onActivityResult(req);return;}if(result!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();try{if(req==REQ_EXPORT){OutputStream o=getContentResolver().openOutputStream(u);if(o!=null){o.write(engine.exportJson().getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();toast("설정 내보냄");}}else if(req==REQ_IMPORT){InputStream in=getContentResolver().openInputStream(u);if(in!=null){ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=in.read(buf))>0)b.write(buf,0,n);in.close();boolean ok=engine.importJson(b.toString("UTF-8"));refreshProfiles();toast(ok?"설정 불러옴":"설정 파일 오류");}}}catch(Exception e){toast("파일 처리 실패: "+e.getMessage());}}
'''
if 'UpdateManager.REQ_INSTALL_UNKNOWN' not in s:
    if old not in s: raise SystemExit('activity result block not found')
    s=s.replace(old,new)

p.write_text(s)
