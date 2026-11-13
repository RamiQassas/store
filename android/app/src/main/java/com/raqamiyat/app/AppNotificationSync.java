package com.raqamiyat.app;

import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

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
    private static final String CHANNEL_ID = "raqamiyat_notifications";

    private final Context context;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public AppNotificationSync(Context context) {
        this.context = context.getApplicationContext();
    }

    public void syncNow(NotificationsCallback callback) {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(NOTIF_API).openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(7000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 NotifSync");
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
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
                        boolean updated = false;

                        for (int i = 0; i < arr.length(); i++) {
                            JSONObject o = arr.getJSONObject(i);
                            AppNotifItem item = new AppNotifItem(
                                    o.optString("id"),
                                    o.optString("category", "promo"),
                                    o.optString("title"),
                                    o.optString("body"),
                                    o.optString("action_url", "")
                            );
                            list.add(item);

                            if (!item.id.isEmpty() && !seen.contains(item.id)) {
                                seen.add(item.id);
                                updated = true;
                                // Fire native Android system notification for the newest unseen item(s)
                                if (i < 3) {
                                    fireSystemNotification(item);
                                }
                            }
                        }

                        if (updated) {
                            prefs.edit().putStringSet(KEY_SEEN_IDS, seen).apply();
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
