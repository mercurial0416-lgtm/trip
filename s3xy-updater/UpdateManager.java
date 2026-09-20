package com.openai.s3xybridge;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import android.util.Base64;
import android.util.Base64InputStream;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;
import org.json.JSONArray;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

final class UpdateManager {
    static final int REQ_INSTALL_UNKNOWN=303;
    private static final String MANIFEST_URL="https://raw.githubusercontent.com/mercurial0416-lgtm/trip/s3xy-button-bridge-build/s3xy-update/latest.json";

    private final Activity activity;
    private TextView statusView;
    private UpdateInfo pending;

    UpdateManager(Activity activity){this.activity=activity;}

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
                JSONObject j=new JSONObject(readAll(c.getInputStream()));
                java.util.ArrayList<String> urls=new java.util.ArrayList<>();
                JSONArray arr=j.optJSONArray("apkB64Urls");
                if(arr!=null){for(int i=0;i<arr.length();i++)urls.add(arr.getString(i));}
                else urls.add(j.getString("apkB64Url"));
                UpdateInfo info=new UpdateInfo(
                        j.getInt("versionCode"),
                        j.optString("versionName",""),
                        urls.toArray(new String[0]),
                        j.optString("sha256",""),
                        j.optString("notes",""));
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
                activity.runOnUiThread(()->{
                    refreshCurrentLabel();
                    if(userInitiated)toast("업데이트 확인 실패: "+e.getMessage());
                });
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
        downloadDecodeAndInstall(info);
    }

    void onActivityResult(int requestCode){
        if(requestCode==REQ_INSTALL_UNKNOWN&&pending!=null){
            if(Build.VERSION.SDK_INT<26||activity.getPackageManager().canRequestPackageInstalls())downloadDecodeAndInstall(pending);
            else toast("업데이트 설치 허용이 필요합니다.");
        }
    }

    private void downloadDecodeAndInstall(UpdateInfo info){
        setStatus("새 버전 다운로드 중…");
        new Thread(()->{
            HttpURLConnection c=null;
            try{
                File dir=activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                if(dir==null)throw new Exception("다운로드 폴더 없음");
                File dst=new File(dir,"S3XYButtonBridge-update.apk");
                if(dst.exists()&&!dst.delete())throw new Exception("이전 업데이트 파일 삭제 실패");

                try(FileOutputStream out=new FileOutputStream(dst)){
                    byte[] buf=new byte[32768];
                    for(String partUrl:info.apkB64Urls){
                        c=(HttpURLConnection)new URL(partUrl).openConnection();
                        c.setConnectTimeout(10000);c.setReadTimeout(30000);c.setUseCaches(false);
                        int code=c.getResponseCode();
                        if(code<200||code>=300)throw new Exception("APK HTTP "+code);
                        try(InputStream raw=c.getInputStream();
                            Base64InputStream decoded=new Base64InputStream(raw,Base64.DEFAULT)){
                            int n;while((n=decoded.read(buf))>0)out.write(buf,0,n);
                        }finally{c.disconnect();c=null;}
                    }
                    out.getFD().sync();
                }

                if(info.sha256!=null&&!info.sha256.trim().isEmpty()){
                    String actual=sha256(dst);
                    if(!actual.equalsIgnoreCase(info.sha256.trim())){
                        dst.delete();
                        throw new SecurityException("SHA-256 불일치");
                    }
                }

                activity.runOnUiThread(()->openInstaller(dst));
            }catch(Exception e){
                activity.runOnUiThread(()->{
                    refreshCurrentLabel();
                    toast("업데이트 실패: "+e.getMessage());
                });
            }finally{if(c!=null)c.disconnect();}
        },"s3xy-update-download").start();
    }

    private void openInstaller(File apk){
        try{
            setStatus("설치 준비됨");
            Uri uri=Uri.parse("content://"+activity.getPackageName()+".updates/"+Uri.encode(apk.getName()));
            Intent i=new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(uri,"application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivity(i);
        }catch(Exception e){toast("설치 화면 열기 실패: "+e.getMessage());}
    }

    private String sha256(File file)throws Exception{
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        try(InputStream in=new FileInputStream(file)){
            byte[] b=new byte[32768];int n;while((n=in.read(b))>0)md.update(b,0,n);
        }
        StringBuilder s=new StringBuilder();
        for(byte b:md.digest())s.append(String.format(Locale.US,"%02x",b&0xff));
        return s.toString();
    }

    private long currentVersionCode(){
        try{
            PackageInfo p=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0);
            return Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode;
        }catch(Exception e){return 0;}
    }

    private String currentVersionName(){
        try{return activity.getPackageManager().getPackageInfo(activity.getPackageName(),0).versionName;}
        catch(Exception e){return "?";}
    }

    private void refreshCurrentLabel(){setStatus("현재 버전 "+currentVersionName()+" · 자동 업데이트 확인 켜짐");}
    private void setStatus(String s){activity.runOnUiThread(()->{if(statusView!=null)statusView.setText(s);});}
    private void toast(String s){Toast.makeText(activity,s,Toast.LENGTH_SHORT).show();}
    private static String readAll(InputStream in)throws Exception{
        try(InputStream x=in){
            byte[] b=new byte[8192];
            java.io.ByteArrayOutputStream o=new java.io.ByteArrayOutputStream();
            int n;while((n=x.read(b))>0)o.write(b,0,n);
            return o.toString("UTF-8");
        }
    }
    void close(){}

    private static final class UpdateInfo{
        final int versionCode;final String versionName,sha256,notes;final String[] apkB64Urls;
        UpdateInfo(int c,String n,String[] u,String h,String notes){
            versionCode=c;versionName=n;apkB64Urls=u;sha256=h;this.notes=notes;
        }
    }
}
