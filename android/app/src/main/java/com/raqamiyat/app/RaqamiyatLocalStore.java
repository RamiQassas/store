package com.raqamiyat.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Local Data Layer & Smart Offline Cache:
 * - Local-first catalog JSON storage
 * - Product image cache with LRU eviction and 50MB bound
 */
public class RaqamiyatLocalStore {

    private static final String TAG = "RaqamiyatLocalStore";
    private static final String CATALOG_CACHE_FILENAME = "raqamiyat_offline_catalog.json";
    private static final String IMAGE_CACHE_DIR = "product_images";
    private static final long MAX_IMAGE_CACHE_BYTES = 50 * 1024 * 1024; // 50 MB max

    private final Context context;
    private final File imageCacheDir;
    private final ExecutorService executor = Executors.newFixedThreadPool(2);

    public RaqamiyatLocalStore(Context context) {
        this.context = context.getApplicationContext();
        this.imageCacheDir = new File(this.context.getCacheDir(), IMAGE_CACHE_DIR);
        if (!imageCacheDir.exists()) {
            imageCacheDir.mkdirs();
        }
    }

    /**
     * Saves catalog JSON string to local storage
     */
    public synchronized void saveCatalogJson(String json) {
        if (json == null || json.isEmpty()) return;
        try {
            File file = new File(context.getFilesDir(), CATALOG_CACHE_FILENAME);
            FileOutputStream fos = new FileOutputStream(file);
            fos.write(json.getBytes(StandardCharsets.UTF_8));
            fos.flush();
            fos.close();
            Log.d(TAG, "Saved offline catalog JSON (" + json.length() + " chars)");
        } catch (Exception e) {
            Log.e(TAG, "Error saving catalog JSON: " + e.getMessage());
        }
    }

    /**
     * Reads saved catalog JSON from local storage
     */
    public synchronized String getCachedCatalogJson() {
        try {
            File file = new File(context.getFilesDir(), CATALOG_CACHE_FILENAME);
            if (!file.exists()) return null;

            FileInputStream fis = new FileInputStream(file);
            byte[] data = new byte[(int) file.length()];
            fis.read(data);
            fis.close();
            return new String(data, StandardCharsets.UTF_8);
        } catch (Exception e) {
            Log.e(TAG, "Error reading cached catalog JSON: " + e.getMessage());
            return null;
        }
    }

    /**
     * Async image caching with disk eviction
     */
    public void cacheProductImageAsync(final String imageUrl) {
        if (imageUrl == null || !imageUrl.startsWith("http")) return;

        executor.execute(() -> {
            try {
                String key = md5(imageUrl);
                File cachedFile = new File(imageCacheDir, key);
                if (cachedFile.exists()) return;

                HttpURLConnection conn = (HttpURLConnection) new URL(imageUrl).openConnection();
                conn.setConnectTimeout(4000);
                conn.setReadTimeout(4000);
                conn.connect();

                if (conn.getResponseCode() == 200) {
                    InputStream in = conn.getInputStream();
                    FileOutputStream out = new FileOutputStream(cachedFile);
                    byte[] buffer = new byte[4096];
                    int bytesRead;
                    while ((bytesRead = in.read(buffer)) != -1) {
                        out.write(buffer, 0, bytesRead);
                    }
                    out.flush();
                    out.close();
                    in.close();

                    trimCacheIfNeeded();
                }
            } catch (Exception ignored) {
            }
        });
    }

    /**
     * Returns cached product image file or null
     */
    public File getCachedImageFile(String imageUrl) {
        if (imageUrl == null) return null;
        String key = md5(imageUrl);
        File file = new File(imageCacheDir, key);
        return file.exists() ? file : null;
    }

    private void trimCacheIfNeeded() {
        File[] files = imageCacheDir.listFiles();
        if (files == null) return;

        long totalSize = 0;
        for (File f : files) {
            totalSize += f.length();
        }

        if (totalSize > MAX_IMAGE_CACHE_BYTES) {
            // Sort by oldest modified
            Arrays.sort(files, Comparator.comparingLong(File::lastModified));
            for (File f : files) {
                if (totalSize <= (MAX_IMAGE_CACHE_BYTES * 0.75)) break;
                long len = f.length();
                if (f.delete()) {
                    totalSize -= len;
                }
            }
        }
    }

    private static String md5(String s) {
        try {
            MessageDigest digest = MessageDigest.getInstance("MD5");
            digest.update(s.getBytes(StandardCharsets.UTF_8));
            byte[] messageDigest = digest.digest();
            StringBuilder hexString = new StringBuilder();
            for (byte b : messageDigest) {
                String hex = Integer.toHexString(0xFF & b);
                while (hex.length() < 2) hex = "0" + hex;
                hexString.append(hex);
            }
            return hexString.toString();
        } catch (Exception e) {
            return String.valueOf(s.hashCode());
        }
    }
}
