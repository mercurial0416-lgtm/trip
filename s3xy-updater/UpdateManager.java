package com.openai.s3xybridge;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

final class UpdateManager {
    static final int REQ_INSTALL_UNKNOWN=303;
    private static final String MANIFEST_URL="https://raw.githubusercontent.com/mercurial0416-lgtm/trip/s3xy-button-bridge-build/s3xy-update/latest.json";

    private final Activity activity;
    private final DownloadManager downloads;
    private TextView statusView;
    private long downloadId=-1;
    private UpdateInfo pending;
    private boolean receiverRegistered;

    UpdateManager(Activity activity){
        this.activity=activity;
        this.downloads=(DownloadManager)activity.getSystemService(Context.DOWNLOAD_SERVICE);
        registerReceiver();
    }

    void bindStatus(TextView v){statusView=v;refreshCurrentLabel();}

    void check(boolean userInitiated){
        setStatus("업데이트 확인 중…");
        new Thread(()->{
            HttpURLConnection c=null;
            try{
                c=(HttpURLConnection)new URL(MANIFEST_URL).openConnection();
                c.setConnectTimeout(7000);c.setReadTimeout(7000);c.setUseCaches(false);
                c.setRequestProperty("Accept","application/json");
                int code=c.getResponseCode();
                if(code<200||code>=300)throw new Exception("HTTP "+code);
                String text=readAll(c.getInputStream());
                JSONObject j=new JSONObject(text);
                UpdateInfo info=new UpdateInfo(j.getInt("versionCode"),j.optString("versionName",""),j.getString("apkUrl"),j.optString("sha256",""),j.optString("notes",""));
                long current=currentVersionCode();
                activity.runOnUiThread(()->{
                    if(info.versionCode>current){
                        pending=info;
                        setStatus("새 버전 "+info.versionName+" 사용 가능");
                        showUpdateDialog(info);
                    }else{
                        refreshCurrentLabel();
                        if(userInitiated)toast("현재 최신 버전입니다.");
                    }
                });
            }catch(Exception e){
                activity.runOnUiThread(()->{refreshCurrentLabel();if(userInitiated)toast("업데이트 확인 실패: "+e.getMessage());});
            }finally{if(c!=null)c.disconnect();}
        },"s3xy-update-check").start();
    }

    private void showUpdateDialog(UpdateInfo info){
        String msg="현재 "+currentVersionName()+"  →  새 버전 "+info.versionName;
        if(info.notes!=null&&!info.notes.trim().isEmpty())msg+="\n\n"+info.notes.trim();
        new AlertDialog.Builder(activity)
                .setTitle("S3XY Bridge 업데이트")
                .setMessage(msg)
                .setNegativeButton("나중에",null)
                .setPositiveButton("업데이트",(d,w)->beginUpdate(info))
                .show();
    }

    private void beginUpdate(UpdateInfo info){
        pending=info;
        if(Build.VERSION.SDK_INT>=26&&!activity.getPackageManager().canRequestPackageInstalls()){
            toast("처음 한 번만 '이 출처 허용'을 켜주세요.");
            Intent i=new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName()));
            activity.startActivityForResult(i,REQ_INSTALL_UNKNOWN);
            return;
        }
        download(info);
    }

    void onActivityResult(int requestCode){
        if(requestCode==REQ_INSTALL_UNKNOWN&&pending!=null){
            if(Build.VERSION.SDK_INT<26||activity.getPackageManager().canRequestPackageInstalls())download(pending);
            else toast("설치 허용이 필요합니다.");
        }
    }

    private void download(UpdateInfo info){
        try{
            File dir=activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
            if(dir==null)throw new Exception("다운로드 폴더 없음");
            File dst=new File(dir,"S3XYButtonBridge-update.apk");
            if(dst.exists())dst.delete();
            DownloadManager.Request req=new DownloadManager.Request(Uri.parse(info.apkUrl));
            req.setTitle("S3XY Button Bridge "+info.versionName);
            req.setDescription("업데이트 다운로드 중");
            req.setMimeType("application/vnd.android.package-archive");
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalFilesDir(activity,Environment.DIRECTORY_DOWNLOADS,dst.getName());
            downloadId=downloads.enqueue(req);
            setStatus("새 버전 다운로드 중…");
            toast("업데이트 다운로드를 시작했습니다.");
        }catch(Exception e){toast("다운로드 시작 실패: "+e.getMessage());}
    }

    private void registerReceiver(){
        IntentFilter f=new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if(Build.VERSION.SDK_INT>=33)activity.registerReceiver(receiver,f,Context.RECEIVER_NOT_EXPORTED);
        else activity.registerReceiver(receiver,f);
        receiverRegistered=true;
    }

    private final BroadcastReceiver receiver=new BroadcastReceiver(){@Override public void onReceive(Context context,Intent intent){
        long id=intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID,-1);
        if(id!=downloadId||pending==null)return;
        Uri uri=downloads.getUriForDownloadedFile(id);
        if(uri==null){toast("업데이트 다운로드에 실패했습니다.");refreshCurrentLabel();return;}
        verifyAndInstall(uri,pending);
    }};

    private void verifyAndInstall(Uri uri,UpdateInfo info){
        setStatus("업데이트 파일 확인 중…");
        new Thread(()->{
            try{
                if(info.sha256!=null&&!info.sha256.trim().isEmpty()){
                    String actual=sha256(uri);
                    if(!actual.equalsIgnoreCase(info.sha256.trim()))throw new SecurityException("SHA-256 불일치");
                }
                activity.runOnUiThread(()->openInstaller(uri));
            }catch(Exception e){activity.runOnUiThread(()->{refreshCurrentLabel();toast("업데이트 파일 검증 실패: "+e.getMessage());});}
        },"s3xy-update-verify").start();
    }

    private void openInstaller(Uri uri){
        try{
            setStatus("설치 준비됨");
            Intent i=new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(uri,"application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(i);
        }catch(Exception e){toast("설치 화면 열기 실패: "+e.getMessage());}
    }

    private String sha256(Uri uri)throws Exception{
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        try(InputStream in=activity.getContentResolver().openInputStream(uri)){
            if(in==null)throw new Exception("파일 열기 실패");
            byte[] b=new byte[32768];int n;while((n=in.read(b))>0)md.update(b,0,n);
        }
        StringBuilder s=new StringBuilder();for(byte b:md.digest())s.append(String.format(Locale.US,"%02x",b&0xff));return s.toString();
    }

    private long currentVersionCode(){
        try{PackageInfo p=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0);return Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode;}catch(Exception e){return 0;}
    }
    private String currentVersionName(){try{return activity.getPackageManager().getPackageInfo(activity.getPackageName(),0).versionName;}catch(Exception e){return "?";}}
    private void refreshCurrentLabel(){setStatus("현재 버전 "+currentVersionName()+" · 자동 업데이트 확인 켜짐");}
    private void setStatus(String s){activity.runOnUiThread(()->{if(statusView!=null)statusView.setText(s);});}
    private void toast(String s){Toast.makeText(activity,s,Toast.LENGTH_SHORT).show();}
    private static String readAll(InputStream in)throws Exception{try(InputStream x=in){byte[] b=new byte[8192];java.io.ByteArrayOutputStream o=new java.io.ByteArrayOutputStream();int n;while((n=x.read(b))>0)o.write(b,0,n);return o.toString("UTF-8");}}

    void close(){if(receiverRegistered){try{activity.unregisterReceiver(receiver);}catch(Exception ignored){}receiverRegistered=false;}}

    private static final class UpdateInfo{
        final int versionCode;final String versionName,apkUrl,sha256,notes;
        UpdateInfo(int c,String n,String u,String h,String notes){versionCode=c;versionName=n;apkUrl=u;sha256=h;this.notes=notes;}
    }
}
