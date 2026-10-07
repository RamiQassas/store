package com.raqamiyat.app;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Handler;
import android.os.Looper;

import androidx.annotation.NonNull;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Robust Centralized Connectivity Manager
 * Distinguishes between physical network transport (Wi-Fi / Cellular)
 * and true internet reachability (DNS / HTTP validation).
 */
public class ConnectivityHelper {

    public interface OnConnectivityChangeListener {
        void onConnectivityChanged(boolean isOnline);
    }

    private static final String PING_URL = "https://raqamiyatapp.com/api/offline-catalog/";
    private static final String FALLBACK_PING_URL = "https://www.google.com/generate_204";
    private static final int TIMEOUT_MS = 2500;

    private final Context context;
    private final ConnectivityManager connectivityManager;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private OnConnectivityChangeListener listener;

    private volatile boolean isOnline = false;
    private ConnectivityManager.NetworkCallback networkCallback;

    public ConnectivityHelper(Context context) {
        this.context = context.getApplicationContext();
        this.connectivityManager = (ConnectivityManager) this.context.getSystemService(Context.CONNECTIVITY_SERVICE);
    }

    public void setListener(OnConnectivityChangeListener listener) {
        this.listener = listener;
    }

    public boolean isOnline() {
        return isOnline;
    }

    public void startMonitoring() {
        if (connectivityManager == null) return;

        NetworkRequest request = new NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build();

        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(@NonNull Network network) {
                checkActualInternet(network);
            }

            @Override
            public void onLost(@NonNull Network network) {
                setOnlineState(false);
            }

            @Override
            public void onCapabilitiesChanged(@NonNull Network network, @NonNull NetworkCapabilities capabilities) {
                boolean hasInternet = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                        && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
                if (hasInternet) {
                    setOnlineState(true);
                } else {
                    checkActualInternet(network);
                }
            }
        };

        try {
            connectivityManager.registerNetworkCallback(request, networkCallback);
        } catch (Exception e) {
            // Fallback: check initial state
            checkActualInternet(connectivityManager.getActiveNetwork());
        }
        
        // Initial check
        checkActualInternet(connectivityManager.getActiveNetwork());
    }

    public void stopMonitoring() {
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {
            }
        }
    }

    public void checkActualInternet(final Network network) {
        if (network == null) {
            setOnlineState(false);
            return;
        }

        executor.execute(() -> {
            boolean reachable = pingUrl(PING_URL);
            if (!reachable) {
                reachable = pingUrl(FALLBACK_PING_URL);
            }
            setOnlineState(reachable);
        });
    }

    private boolean pingUrl(String targetUrl) {
        try {
            HttpURLConnection connection = (HttpURLConnection) new URL(targetUrl).openConnection();
            connection.setRequestProperty("User-Agent", "RaqamiyatAndroid/2.0 ConnectivityPing");
            connection.setConnectTimeout(TIMEOUT_MS);
            connection.setReadTimeout(TIMEOUT_MS);
            connection.setRequestMethod("GET");
            connection.setInstanceFollowRedirects(true);
            int code = connection.getResponseCode();
            return (code >= 200 && code < 400);
        } catch (IOException e) {
            return false;
        }
    }

    private void setOnlineState(final boolean online) {
        if (this.isOnline != online) {
            this.isOnline = online;
            mainHandler.post(() -> {
                if (listener != null) {
                    listener.onConnectivityChanged(online);
                }
            });
        }
    }
}
