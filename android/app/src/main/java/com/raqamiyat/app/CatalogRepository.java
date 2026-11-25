package com.raqamiyat.app;

import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;

import com.raqamiyat.app.model.CategoryItem;
import com.raqamiyat.app.model.FormFieldItem;
import com.raqamiyat.app.model.GatewayItem;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CatalogRepository {

    public static final String DOMAIN = "https://raqamiyatapp.com";
    public static final String CATALOG_API_URL = DOMAIN + "/api/offline-catalog/";
    public static final String SESSION_API_URL = DOMAIN + "/api/app/session/";
    public static final String WALLET_API_URL = DOMAIN + "/api/app/wallet/";
    public static final String ORDERS_API_URL = DOMAIN + "/api/app/orders/";
    public static final String LOGIN_API_URL = DOMAIN + "/api/app/auth/login/";
    public static final String LOGOUT_API_URL = DOMAIN + "/api/app/auth/logout/";

    public static class CatalogData {
        public final List<CategoryItem> categories = new ArrayList<>();
        public final List<ProductItem> products = new ArrayList<>();
        public final List<GatewayItem> gateways = new ArrayList<>();
        public double sypRate = 15000.0;
    }

    public interface CatalogCallback {
        void onLoaded(CatalogData data, boolean fromCache);
        void onError(String message);
    }

    public interface SessionCallback {
        void onSessionInfo(boolean isAuthenticated, boolean isAdmin, String displayName);
    }

    public interface JsonCallback {
        void onResult(int statusCode, JSONObject json, String error);
    }

    private final RaqamiyatLocalStore localStore;
    private final ExecutorService executor = Executors.newFixedThreadPool(3);
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public CatalogRepository(RaqamiyatLocalStore localStore) {
        this.localStore = localStore;
    }

    public static void attachAuthHeaders(HttpURLConnection conn, RaqamiyatLocalStore store) {
        conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.2.3 NativeApp");
        String cookies = CookieManager.getInstance().getCookie(DOMAIN);
        if (cookies != null && !cookies.isEmpty()) {
            conn.setRequestProperty("Cookie", cookies);
            for (String part : cookies.split(";")) {
                String t = part.trim();
                if (t.startsWith("csrftoken=")) {
                    conn.setRequestProperty("X-CSRFToken", t.substring("csrftoken=".length()));
                    break;
                }
            }
        }
        if (store != null) {
            String storedToken = store.getAppAuthToken();
            if (storedToken != null && !storedToken.isEmpty()) {
                conn.setRequestProperty("X-App-Auth-Token", storedToken);
            }
        }
    }

    public static void captureResponseCookies(HttpURLConnection conn) {
        try {
            Map<String, List<String>> headers = conn.getHeaderFields();
            if (headers == null) return;
            List<String> setCookies = headers.get("Set-Cookie");
            if (setCookies == null) setCookies = headers.get("set-cookie");
            if (setCookies != null) {
                CookieManager cm = CookieManager.getInstance();
                for (String cookie : setCookies) {
                    if (cookie != null && !cookie.isEmpty()) {
                        cm.setCookie(DOMAIN, cookie);
                    }
                }
                cm.flush();
            }
        } catch (Exception ignored) {
        }
    }

    public void loadCatalog(boolean forceNetwork, CatalogCallback callback) {
        executor.execute(() -> {
            String cached = localStore.getCachedCatalogJson();
            if (cached != null && !cached.isEmpty()) {
                try {
                    CatalogData cachedData = parseCatalogJson(cached);
                    mainHandler.post(() -> callback.onLoaded(cachedData, true));
                } catch (Exception ignored) {
                }
            }

            try {
                String urlStr = forceNetwork ? (CATALOG_API_URL + "?nocache=1") : CATALOG_API_URL;
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setConnectTimeout(7000);
                conn.setReadTimeout(10000);
                attachAuthHeaders(conn, localStore);
                conn.connect();

                if (conn.getResponseCode() == 200) {
                    InputStream is = conn.getInputStream();
                    Scanner scanner = new Scanner(is, StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    if (!json.isEmpty()) {
                        localStore.saveCatalogJson(json);
                        CatalogData freshData = parseCatalogJson(json);
                        if (freshData.sypRate > 1.0) {
                            localStore.setSypRate(freshData.sypRate);
                        }
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

    public void fetchWalletAndGateways(JsonCallback callback) {
        executor.execute(() -> {
            String cached = localStore.getCachedWalletJson();
            if (cached != null && !cached.isEmpty()) {
                try {
                    JSONObject cachedObj = new JSONObject(cached);
                    mainHandler.post(() -> callback.onResult(200, cachedObj, null));
                } catch (Exception ignored) {
                }
            }
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(WALLET_API_URL).openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(8000);
                attachAuthHeaders(conn, localStore);
                conn.connect();
                captureResponseCookies(conn);

                int code = conn.getResponseCode();
                InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                String body = "";
                if (is != null) {
                    Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                    body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                }
                if (code == 200 && body.trim().startsWith("{")) {
                    localStore.saveWalletJson(body);
                    JSONObject obj = new JSONObject(body);
                    double rate = obj.optDouble("syp_rate", 0.0);
                    if (rate > 1.0) localStore.setSypRate(rate);
                    if (obj.optBoolean("is_authenticated", false)) {
                        String tok = obj.optString("app_auth_token", "");
                        if (!tok.isEmpty()) localStore.saveAppAuthToken(tok);
                        JSONObject u = obj.optJSONObject("user");
                        localStore.saveQuickAccountSnapshot(
                                obj.optDouble("available_balance_usd", obj.optDouble("balance", 0.0)),
                                u != null ? u.optString("full_name", "") : "",
                                u != null ? u.optString("email", "") : ""
                        );
                    }
                    mainHandler.post(() -> callback.onResult(200, obj, null));
                    return;
                }
                if (cached == null || cached.isEmpty()) {
                    mainHandler.post(() -> callback.onResult(code, null, "تعذر جلب بيانات المحفظة"));
                }
            } catch (Exception e) {
                if (cached == null || cached.isEmpty()) {
                    mainHandler.post(() -> callback.onResult(0, null, "تحقق من اتصالك بالإنترنت"));
                }
            }
        });
    }

    public void getJson(String urlStr, JsonCallback callback) {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setConnectTimeout(7000);
                conn.setReadTimeout(10000);
                attachAuthHeaders(conn, localStore);
                conn.connect();
                captureResponseCookies(conn);
                int code = conn.getResponseCode();
                InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                String body = "";
                if (is != null) {
                    Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                    body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                }
                if (body.trim().startsWith("{")) {
                    JSONObject obj = new JSONObject(body.trim());
                    mainHandler.post(() -> callback.onResult(code, obj, null));
                } else {
                    mainHandler.post(() -> callback.onResult(code, null, "استجابة غير متوقعة من الخادم"));
                }
            } catch (Exception e) {
                mainHandler.post(() -> callback.onResult(0, null, "تعذر الاتصال بالخادم"));
            }
        });
    }

    public void postJson(String urlStr, JSONObject payload, JsonCallback callback) {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(25000);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                attachAuthHeaders(conn, localStore);

                OutputStream os = conn.getOutputStream();
                os.write((payload != null ? payload.toString() : "{}").getBytes(StandardCharsets.UTF_8));
                os.flush();
                os.close();

                captureResponseCookies(conn);
                int code = conn.getResponseCode();
                InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                String body = "";
                if (is != null) {
                    Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                    body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                }
                if (body.trim().startsWith("{")) {
                    JSONObject obj = new JSONObject(body.trim());
                    mainHandler.post(() -> callback.onResult(code, obj, null));
                } else {
                    mainHandler.post(() -> callback.onResult(code, null, "تعذر معالجة استجابة الخادم"));
                }
            } catch (Exception e) {
                mainHandler.post(() -> callback.onResult(0, null, "تعذر الاتصال بالخادم، تحقق من الإنترنت"));
            }
        });
    }

    public void checkSession(SessionCallback callback) {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(SESSION_API_URL).openConnection();
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(5000);
                attachAuthHeaders(conn, localStore);
                conn.connect();
                captureResponseCookies(conn);
                if (conn.getResponseCode() == 200) {
                    Scanner scanner = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    JSONObject obj = new JSONObject(json);
                    boolean isAuth = obj.optBoolean("is_authenticated", false);
                    String token = obj.optString("app_auth_token", "");
                    if (isAuth && !token.isEmpty()) {
                        localStore.saveAppAuthToken(token);
                    } else if (!isAuth) {
                        localStore.saveAppAuthToken("");
                    }
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

        double sypR = root.optDouble("syp_rate", 0.0);
        if (sypR > 1.0) {
            data.sypRate = sypR;
        } else {
            data.sypRate = localStore.getSypRate();
        }

        JSONArray gws = root.optJSONArray("gateways");
        if (gws != null) {
            data.gateways.addAll(GatewayItem.parseList(gws));
        }

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

                List<FormFieldItem> formFields = new ArrayList<>();
                JSONArray fArr = p.optJSONArray("form_fields");
                if (fArr != null) {
                    for (int f = 0; f < fArr.length(); f++) {
                        JSONObject fo = fArr.optJSONObject(f);
                        if (fo == null) continue;
                        List<String> opts = new ArrayList<>();
                        JSONArray oArr = fo.optJSONArray("options");
                        if (oArr != null) {
                            for (int k = 0; k < oArr.length(); k++) {
                                String optVal = oArr.optString(k, "").trim();
                                if (!optVal.isEmpty()) opts.add(optVal);
                            }
                        }
                        formFields.add(new FormFieldItem(
                                fo.optString("name", "note"),
                                fo.optString("label", "البيانات المطلوبة"),
                                fo.optString("type", "text"),
                                fo.optString("placeholder", ""),
                                fo.optBoolean("required", false),
                                opts
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
                        p.optString("instructions", ""),
                        p.optString("category_id", ""),
                        p.optString("category_name", ""),
                        resolveUrl(p.optString("image")),
                        basePrice,
                        p.optString("product_type", "physical"),
                        p.optBoolean("is_featured", false),
                        p.optBoolean("is_sale", false),
                        p.optBoolean("is_out_of_stock", false),
                        p.optString("delivery_time_display", "تسليم فوري ⚡"),
                        variants,
                        formFields
                ));
            }
        }
        return data;
    }
}
