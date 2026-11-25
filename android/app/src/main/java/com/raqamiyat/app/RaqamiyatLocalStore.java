package com.raqamiyat.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import com.raqamiyat.app.model.CartItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Local Data Layer, Global Currency Engine, Cart Persistence & Smart Offline Cache
 */
public class RaqamiyatLocalStore {

    private static final String TAG = "RaqamiyatLocalStore";
    private static final String CATALOG_CACHE_FILENAME = "raqamiyat_offline_catalog.json";
    private static final String WALLET_CACHE_FILENAME = "raqamiyat_wallet_gateways.json";
    private static final String IMAGE_CACHE_DIR = "product_images";
    private static final String PREFS_NAME = "raqamiyat_app_prefs";

    private static final String KEY_APP_AUTH_TOKEN = "app_auth_token";
    private static final String KEY_PREFERRED_CURRENCY = "preferred_currency";
    private static final String KEY_SYP_RATE = "syp_exchange_rate";
    private static final String KEY_CART_JSON = "native_cart_items";
    private static final String KEY_LAST_BALANCE_USD = "last_balance_usd";
    private static final String KEY_LAST_USER_NAME = "last_user_name";
    private static final String KEY_LAST_USER_EMAIL = "last_user_email";

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

    private SharedPreferences prefs() {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public void saveAppAuthToken(String token) {
        try {
            prefs().edit().putString(KEY_APP_AUTH_TOKEN, token != null ? token.trim() : "").apply();
        } catch (Exception ignored) {
        }
    }

    public String getAppAuthToken() {
        try {
            return prefs().getString(KEY_APP_AUTH_TOKEN, "");
        } catch (Exception e) {
            return "";
        }
    }

    public String getPreferredCurrency() {
        try {
            String c = prefs().getString(KEY_PREFERRED_CURRENCY, "USD");
            return "SYP".equalsIgnoreCase(c) ? "SYP" : "USD";
        } catch (Exception e) {
            return "USD";
        }
    }

    public void setPreferredCurrency(String currencyCode) {
        try {
            String clean = "SYP".equalsIgnoreCase(currencyCode) ? "SYP" : "USD";
            prefs().edit().putString(KEY_PREFERRED_CURRENCY, clean).apply();
        } catch (Exception ignored) {
        }
    }

    public String togglePreferredCurrency() {
        String next = "USD".equals(getPreferredCurrency()) ? "SYP" : "USD";
        setPreferredCurrency(next);
        return next;
    }

    public double getSypRate() {
        try {
            float r = prefs().getFloat(KEY_SYP_RATE, 15000f);
            return r > 1f ? (double) r : 15000.0;
        } catch (Exception e) {
            return 15000.0;
        }
    }

    public void setSypRate(double rate) {
        if (rate <= 1.0) return;
        try {
            prefs().edit().putFloat(KEY_SYP_RATE, (float) rate).apply();
        } catch (Exception ignored) {
        }
    }

    public void saveQuickAccountSnapshot(double balanceUsd, String fullName, String email) {
        try {
            SharedPreferences.Editor ed = prefs().edit();
            ed.putFloat(KEY_LAST_BALANCE_USD, (float) balanceUsd);
            if (fullName != null) ed.putString(KEY_LAST_USER_NAME, fullName);
            if (email != null) ed.putString(KEY_LAST_USER_EMAIL, email);
            ed.apply();
        } catch (Exception ignored) {
        }
    }

    public double getLastBalanceUsd() {
        try {
            return prefs().getFloat(KEY_LAST_BALANCE_USD, 0f);
        } catch (Exception e) {
            return 0.0;
        }
    }

    public String getLastUserName() {
        try {
            return prefs().getString(KEY_LAST_USER_NAME, "");
        } catch (Exception e) {
            return "";
        }
    }

    public String getLastUserEmail() {
        try {
            return prefs().getString(KEY_LAST_USER_EMAIL, "");
        } catch (Exception e) {
            return "";
        }
    }

    public String formatPrice(double usdAmount) {
        return formatPriceInCurrency(usdAmount, getPreferredCurrency(), getSypRate());
    }

    public String formatSecondaryPrice(double usdAmount) {
        String other = "USD".equals(getPreferredCurrency()) ? "SYP" : "USD";
        return "≈ " + formatPriceInCurrency(usdAmount, other, getSypRate());
    }

    public static String formatPriceInCurrency(double usdAmount, String currency, double sypRate) {
        if ("SYP".equalsIgnoreCase(currency)) {
            long syp = Math.round(usdAmount * (sypRate > 1.0 ? sypRate : 15000.0));
            return formatSypAmount(syp);
        }
        return String.format(Locale.US, "$%.2f", usdAmount);
    }

    public static String formatSypAmount(double sypVal) {
        long rounded = Math.round(sypVal);
        NumberFormat nf = NumberFormat.getIntegerInstance(Locale.US);
        return nf.format(rounded) + " ل.س";
    }

    // ── Native Shopping Cart Persistence ──
    public List<CartItem> getCartItems() {
        List<CartItem> list = new ArrayList<>();
        try {
            String raw = prefs().getString(KEY_CART_JSON, "[]");
            JSONArray arr = new JSONArray(raw);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.optJSONObject(i);
                if (o == null) continue;
                list.add(new CartItem(
                        o.optString("product_id"),
                        o.optString("variant_id"),
                        o.optString("product_name"),
                        o.optString("variant_name"),
                        o.optString("image_url"),
                        o.optDouble("unit_price_usd", 0.0),
                        o.optInt("quantity", 1),
                        o.optString("custom_input", "")
                ));
            }
        } catch (Exception ignored) {
        }
        return list;
    }

    public void saveCartItems(List<CartItem> items) {
        try {
            JSONArray arr = new JSONArray();
            if (items != null) {
                for (CartItem it : items) {
                    JSONObject o = new JSONObject();
                    o.put("product_id", it.productId);
                    o.put("variant_id", it.variantId);
                    o.put("product_name", it.productName);
                    o.put("variant_name", it.variantName);
                    o.put("image_url", it.imageUrl);
                    o.put("unit_price_usd", it.unitPriceUsd);
                    o.put("quantity", it.quantity);
                    o.put("custom_input", it.customInput);
                    arr.put(o);
                }
            }
            prefs().edit().putString(KEY_CART_JSON, arr.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    public int addToCart(CartItem newItem) {
        List<CartItem> current = getCartItems();
        boolean merged = false;
        for (CartItem existing : current) {
            if (existing.getKey().equals(newItem.getKey())) {
                existing.quantity += newItem.quantity;
                if (newItem.customInput != null && !newItem.customInput.isEmpty()) {
                    existing.customInput = newItem.customInput;
                }
                merged = true;
                break;
            }
        }
        if (!merged) {
            current.add(newItem);
        }
        saveCartItems(current);
        return getCartCount();
    }

    public void clearCart() {
        prefs().edit().putString(KEY_CART_JSON, "[]").apply();
    }

    public int getCartCount() {
        int total = 0;
        for (CartItem it : getCartItems()) {
            total += it.quantity;
        }
        return total;
    }

    public synchronized void saveWalletJson(String json) {
        if (json == null || json.isEmpty()) return;
        try {
            File file = new File(context.getFilesDir(), WALLET_CACHE_FILENAME);
            FileOutputStream fos = new FileOutputStream(file);
            fos.write(json.getBytes(StandardCharsets.UTF_8));
            fos.flush();
            fos.close();
        } catch (Exception ignored) {
        }
    }

    public synchronized String getCachedWalletJson() {
        try {
            File file = new File(context.getFilesDir(), WALLET_CACHE_FILENAME);
            if (!file.exists()) return null;
            FileInputStream fis = new FileInputStream(file);
            byte[] data = new byte[(int) file.length()];
            fis.read(data);
            fis.close();
            return new String(data, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

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
