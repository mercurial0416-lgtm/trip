package com.openai.s3xybridge;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.UriMatcher;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.Environment;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

public class UpdateFileProvider extends ContentProvider {
    @Override public boolean onCreate(){return true;}

    private File resolve(Uri uri) throws FileNotFoundException{
        String name=uri.getLastPathSegment();
        if(name==null||!name.equals("S3XYButtonBridge-update.apk"))throw new FileNotFoundException();
        File dir=getContext().getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if(dir==null)throw new FileNotFoundException();
        File f=new File(dir,name);
        if(!f.isFile())throw new FileNotFoundException();
        return f;
    }

    @Override public String getType(Uri uri){return "application/vnd.android.package-archive";}

    @Override public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException{
        if(!"r".equals(mode))throw new FileNotFoundException();
        return ParcelFileDescriptor.open(resolve(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] selectionArgs,String sortOrder){
        try{
            File f=resolve(uri);
            MatrixCursor c=new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE});
            c.addRow(new Object[]{f.getName(),f.length()});
            return c;
        }catch(Exception e){return null;}
    }

    @Override public int delete(Uri uri,String selection,String[] selectionArgs){return 0;}
    @Override public int update(Uri uri,ContentValues values,String selection,String[] selectionArgs){return 0;}
    @Override public Uri insert(Uri uri,ContentValues values){return null;}
}
