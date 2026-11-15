package com.raqamiyat.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;

import androidx.core.app.NotificationCompat;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Scanner;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class AppNotificationSync {

    public static class AppNotifItem {
        public final String id;
        public final String category;
        public final String title;
        public final String body;
        public final String actionUrl;

        public AppNotifItem(String id, String category, String title, String body, String actionUrl) {
            this.id = id;
            this.category = category;
            this.title = title;
            this.body = body;
            this.actionUrl = actionUrl;
        }
    }

    public interface NotificationsCallback {
        void onNotificationsLoaded(List<AppNotifItem> items);
    }

    private static final String DOMAIN = "https://raqamiyatapp.com";
    private static final String NOTIF_API = DOMAIN + "/api/app/notifications/";
    private static final String PREFS_NAME = "raqamiyat_notif_prefs";
    private static final String KEY_SEEN_IDS = "seen_notif_ids";
    private static final String KEY_INITIAL_SEEDED = "initial_seeded_v2";
    private static final String CHANNEL_ID = "raqamiyat_notifications";

    private static ScheduledExecutorService bgPoller;

    private final Context context;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public AppNotificationSync(Context context) {
        this.context = context.getApplicationContext();
        ensureChannel();
    }

    public void startContinuousBackgroundSync() {
        AppNotificationJobService.scheduleBackgroundSync(context);
        synchronized (AppNotificationSync.class) {
            if (bgPoller == null || bgPoller.isShutdown()) {
                bgPoller = Executors.newSingleThreadScheduledExecutor();
                bgPoller.scheduleWithFixedDelay(() -> syncNow(null), 15, 22, TimeUnit.SECONDS);
            }
        }
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                NotificationManager mgr = context.getSystemService(NotificationManager.class);
                if (mgr != null && mgr.getNotificationChannel(CHANNEL_ID) == null) {
                    NotificationChannel channel = new NotificationChannel(
                            CHANNEL_ID,
                            "إشعارات وعروض رقميات",
                            NotificationManager.IMPORTANCE_HIGH
                    );
                    channel.setDescription("تنبيهات العروض والتحديثات والطلبات من منصة رقميات");
                    mgr.createNotificationChannel(channel);
                }
            } catch (Exception ignored) {
            }
        }
    }

    private boolean isSecurityNoise(String title, String actionUrl) {
        String t = (title != null ? title : "").toLowerCase();
        String u = (actionUrl != null ? actionUrl : "").toLowerCase();
        return t.contains("اختراق")
                || t.contains("هجوم")
                || t.contains("تم صد")
                || t.contains("تنبيه أمني")
                || t.contains("إنذار أمني")
                || t.contains("خطأ في الخادم")
                || t.contains("ماسح آلي")
                || u.contains("audit-logs");
    }

    public void syncNow(NotificationsCallback callback) {
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(NOTIF_API).openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(7000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.2 NotifSync");
                try {
                    String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                    if (cookies != null && !cookies.isEmpty()) {
                        conn.setRequestProperty("Cookie", cookies);
                    }
                } catch (Exception ignored) {
                }
                String appToken = new RaqamiyatLocalStore(context).getAppAuthToken();
                if (appToken != null && !appToken.isEmpty()) {
                    conn.setRequestProperty("X-App-Auth-Token", appToken);
                }
                conn.connect();

                if (conn.getResponseCode() == 200) {
                    Scanner sc = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String jsonStr = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();

                    JSONObject root = new JSONObject(jsonStr);
                    JSONArray arr = root.optJSONArray("notifications");
                    List<AppNotifItem> list = new ArrayList<>();
                    if (arr != null) {
                        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
                        Set<String> seen = new HashSet<>(prefs.getStringSet(KEY_SEEN_IDS, new HashSet<>()));
                        boolean isInitialSeeded = prefs.getBoolean(KEY_INITIAL_SEEDED, false);
                        boolean updated = false;

                        for (int i = 0; i < arr.length(); i++) {
                            JSONObject o = arr.getJSONObject(i);
                            String title = o.optString("title");
                            String actionUrl = o.optString("action_url", "");
                            if (isSecurityNoise(title, actionUrl)) {
                                continue;
                            }

                            AppNotifItem item = new AppNotifItem(
                                    o.optString("id"),
                                    o.optString("category", "promo"),
                                    title,
                                    o.optString("body"),
                                    actionUrl
                            );
                            list.add(item);

                            boolean shouldPush = o.optBoolean("should_push", true);
                            if (!item.id.isEmpty() && !seen.contains(item.id)) {
                                seen.add(item.id);
                                updated = true;
                                // Only fire push notification for genuinely new notifications (not old history on first open)
                                if (isInitialSeeded && shouldPush && i < 3) {
                                    fireSystemNotification(item);
                                }
                            }
                        }

                        if (!isInitialSeeded || updated) {
                            prefs.edit()
                                    .putStringSet(KEY_SEEN_IDS, seen)
                                    .putBoolean(KEY_INITIAL_SEEDED, true)
                                    .apply();
                        }
                    }
                    if (callback != null) {
                        mainHandler.post(() -> callback.onNotificationsLoaded(list));
                    }
                }
            } catch (Exception ignored) {
            }
        });
    }

    private void fireSystemNotification(AppNotifItem item) {
        try {
            String prefix;
            switch (item.category) {
                case "discount":
                    prefix = "🔥 تخفيضات | ";
                    break;
                case "update":
                    prefix = "⚡ تحديث | ";
                    break;
                case "promo":
                    prefix = "🎁 عرض خاص | ";
                    break;
                default:
                    prefix = "🔔 رقميات | ";
                    break;
            }

            Intent intent = new Intent(context, MainActivity.class);
            if (item.actionUrl != null && !item.actionUrl.isEmpty()) {
                String full = item.actionUrl.startsWith("http") ? item.actionUrl : DOMAIN + item.actionUrl;
                intent.setData(Uri.parse(full));
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);

            PendingIntent pi = PendingIntent.getActivity(
                    context,
                    item.id.hashCode(),
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );

            NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle(prefix + item.title)
                    .setContentText(item.body)
                    .setStyle(new NotificationCompat.BigTextStyle().bigText(item.body))
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .setAutoCancel(true)
                    .setContentIntent(pi);

            NotificationManager mgr = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (mgr != null) {
                mgr.notify(item.id.hashCode(), builder.build());
            }
        } catch (Exception ignored) {
        }
    }
}
