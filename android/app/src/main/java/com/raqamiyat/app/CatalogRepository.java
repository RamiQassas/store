package com.raqamiyat.app;

import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;

import com.raqamiyat.app.model.CategoryItem;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CatalogRepository {

    public static final String DOMAIN = "https://raqamiyatapp.com";
    public static final String CATALOG_API_URL = DOMAIN + "/api/offline-catalog/";
    public static final String SESSION_API_URL = DOMAIN + "/api/app/session/";

    public static class CatalogData {
        public final List<CategoryItem> categories = new ArrayList<>();
        public final List<ProductItem> products = new ArrayList<>();
    }

    public interface CatalogCallback {
        void onLoaded(CatalogData data, boolean fromCache);
        void onError(String message);
    }

    public interface SessionCallback {
        void onSessionInfo(boolean isAuthenticated, boolean isAdmin, String displayName);
    }

    private final RaqamiyatLocalStore localStore;
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public CatalogRepository(RaqamiyatLocalStore localStore) {
        this.localStore = localStore;
    }

    public void loadCatalog(boolean forceNetwork, CatalogCallback callback) {
        executor.execute(() -> {
            // 1. Always emit cached data immediately if available for instant native rendering
            String cached = localStore.getCachedCatalogJson();
            if (cached != null && !cached.isEmpty()) {
                try {
                    CatalogData cachedData = parseCatalogJson(cached);
                    mainHandler.post(() -> callback.onLoaded(cachedData, true));
                    if (!forceNetwork) {
                        // Still refresh silently in background
                    }
                } catch (Exception ignored) {
                }
            }

            // 2. Fetch fresh data from server
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(CATALOG_API_URL).openConnection();
                conn.setConnectTimeout(7000);
                conn.setReadTimeout(10000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 Native");
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                }
                conn.connect();

                if (conn.getResponseCode() == 200) {
                    InputStream is = conn.getInputStream();
                    Scanner scanner = new Scanner(is, StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    if (!json.isEmpty()) {
                        localStore.saveCatalogJson(json);
                        CatalogData freshData = parseCatalogJson(json);
                        mainHandler.post(() -> callback.onLoaded(freshData, false));
                        return;
                    }
                }
                if (cached == null || cached.isEmpty()) {
                    mainHandler.post(() -> callback.onError("تعذر تحميل المنتجات حالياً"));
                }
            } catch (Exception e) {
                if (cached == null || cached.isEmpty()) {
                    mainHandler.post(() -> callback.onError("لا يوجد اتصال بالإنترنت ولا توجد بيانات محفوظة"));
                }
            }
        });
    }

    public void checkSession(SessionCallback callback) {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(SESSION_API_URL).openConnection();
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(5000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 Native");
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                }
                conn.connect();
                if (conn.getResponseCode() == 200) {
                    Scanner scanner = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    JSONObject obj = new JSONObject(json);
                    boolean isAuth = obj.optBoolean("is_authenticated", false);
                    boolean isAdmin = obj.optBoolean("can_manage_studio", false) || obj.optBoolean("is_admin", false);
                    String name = obj.optString("full_name", obj.optString("username", ""));
                    mainHandler.post(() -> callback.onSessionInfo(isAuth, isAdmin, name));
                    return;
                }
            } catch (Exception ignored) {
            }
            mainHandler.post(() -> callback.onSessionInfo(false, false, ""));
        });
    }

    public static String resolveUrl(String path) {
        if (path == null || path.trim().isEmpty() || "null".equals(path)) return "";
        if (path.startsWith("http://") || path.startsWith("https://")) return path;
        if (path.startsWith("/")) return DOMAIN + path;
        return DOMAIN + "/" + path;
    }

    private CatalogData parseCatalogJson(String json) throws Exception {
        CatalogData data = new CatalogData();
        JSONObject root = new JSONObject(json);

        JSONArray cats = root.optJSONArray("categories");
        if (cats != null) {
            for (int i = 0; i < cats.length(); i++) {
                JSONObject c = cats.getJSONObject(i);
                data.categories.add(new CategoryItem(
                        c.optString("id"),
                        c.optString("name"),
                        resolveUrl(c.optString("image")),
                        c.optString("product_type", "physical")
                ));
            }
        }

        JSONArray prods = root.optJSONArray("products");
        if (prods != null) {
            for (int i = 0; i < prods.length(); i++) {
                JSONObject p = prods.getJSONObject(i);
                List<VariantItem> variants = new ArrayList<>();
                JSONArray vArr = p.optJSONArray("variants");
                if (vArr != null) {
                    for (int j = 0; j < vArr.length(); j++) {
                        JSONObject v = vArr.getJSONObject(j);
                        variants.add(new VariantItem(
                                v.optString("id"),
                                v.optString("name"),
                                v.optString("sku", ""),
                                v.optDouble("price", 0.0),
                                v.optBoolean("is_active", true)
                        ));
                    }
                }
                double basePrice = p.optDouble("price", 0.0);
                if (basePrice <= 0 && !variants.isEmpty()) {
                    basePrice = variants.get(0).price;
                }
                data.products.add(new ProductItem(
                        p.optString("id"),
                        p.optString("name"),
                        p.optString("code", ""),
                        p.optString("description", ""),
                        p.optString("category_id", ""),
                        p.optString("category_name", ""),
                        resolveUrl(p.optString("image")),
                        basePrice,
                        p.optString("product_type", "physical"),
                        p.optBoolean("is_featured", false),
                        p.optBoolean("is_sale", false),
                        p.optBoolean("is_out_of_stock", false),
                        p.optString("delivery_time_display", ""),
                        variants
                ));
            }
        }
        return data;
    }
}
