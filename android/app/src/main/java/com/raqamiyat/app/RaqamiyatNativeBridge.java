package com.raqamiyat.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;

/**
 * JavaScript Bridge exposed to WebView under `window.RaqamiyatNative`
 * Enforces Local-first reading + Server-authoritative transactions
 */
public class RaqamiyatNativeBridge {

    public interface BridgeActionCallback {
        void onOpenNativeStudio();
        void onTransactionSuccess(String orderId);
    }

    private final Activity activity;
    private final ConnectivityHelper connectivityHelper;
    private final RaqamiyatLocalStore localStore;
    private final BridgeActionCallback actionCallback;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public RaqamiyatNativeBridge(Activity activity, ConnectivityHelper connectivityHelper, RaqamiyatLocalStore localStore, BridgeActionCallback actionCallback) {
        this.activity = activity;
        this.connectivityHelper = connectivityHelper;
        this.localStore = localStore;
        this.actionCallback = actionCallback;
    }

    @JavascriptInterface
    public boolean isOnline() {
        return connectivityHelper != null && connectivityHelper.isOnline();
    }

    @JavascriptInterface
    public boolean canPerformFinancialOperation() {
        return isOnline();
    }

    /**
     * Shows a polished unified Native Dialog warning the user that financial transactions
     * (buying, deposits, withdrawals, transfers, balance updates) cannot be done offline.
     */
    @JavascriptInterface
    public void showOfflineTransactionAlert(final String operationName) {
        mainHandler.post(() -> {
            if (activity == null || activity.isFinishing()) return;

            String op = (operationName != null && !operationName.trim().isEmpty()) ? operationName.trim() : "هذه العملية المالية";

            new MaterialAlertDialogBuilder(activity)
                    .setTitle("⚠️ لا يوجد اتصال بالإنترنت")
                    .setMessage(op + " تحتاج إلى اتصال فعال بالإنترنت لحماية حسابك وتأكيد العملية وسحب الرصيد بأمان تام.\n\nيرجى التحقق من اتصالك بالإنترنت والمحاولة مجدداً.")
                    .setPositiveButton("حسناً، فهمت", (dialog, which) -> dialog.dismiss())
                    .setCancelable(true)
                    .show();
        });
    }

    @JavascriptInterface
    public void cacheCatalogData(final String jsonString) {
        if (localStore != null && jsonString != null) {
            localStore.saveCatalogJson(jsonString);
        }
    }

    @JavascriptInterface
    public String getCachedCatalogData() {
        if (localStore != null) {
            return localStore.getCachedCatalogJson();
        }
        return null;
    }

    @JavascriptInterface
    public void showToast(final String message) {
        if (message == null) return;
        mainHandler.post(() -> Toast.makeText(activity, message, Toast.LENGTH_SHORT).show());
    }

    @JavascriptInterface
    public void openNativeCameraStudio() {
        mainHandler.post(() -> {
            if (actionCallback != null) {
                actionCallback.onOpenNativeStudio();
            }
        });
    }

    @JavascriptInterface
    public void onTransactionSuccess(final String orderId) {
        mainHandler.post(() -> {
            if (actionCallback != null) {
                actionCallback.onTransactionSuccess(orderId);
            }
        });
    }

    @JavascriptInterface
    public String getAppVersion() {
        return "2.0.0";
    }
}
