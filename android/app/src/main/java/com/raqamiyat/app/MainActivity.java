package com.raqamiyat.app;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.view.View;
import android.view.animation.AlphaAnimation;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity implements ConnectivityHelper.OnConnectivityChangeListener, RaqamiyatNativeBridge.BridgeActionCallback {

    private static final String BASE_URL = "https://raqamiyatapp.com/";
    private static final String CATALOG_URL = "https://raqamiyatapp.com/catalog/";
    private static final String OFFLINE_API_URL = "https://raqamiyatapp.com/api/offline-catalog/";
    private static final String CHANNEL_ID = "raqamiyat_notifications";
    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;
    private static final int PERMISSIONS_REQUEST_CODE = 2001;

    private WebView webView;
    private SwipeRefreshLayout swipeRefresh;
    private ProgressBar progressBar;
    private LinearLayout connectivityBanner;
    private TextView bannerText;
    private RelativeLayout splashOverlay;
    private LinearLayout nativeErrorView;
    private Button btnRetry;
    private Button btnBrowseCached;

    private ConnectivityHelper connectivityHelper;
    private RaqamiyatLocalStore localStore;
    private RaqamiyatNativeBridge nativeBridge;

    private ValueCallback<Uri[]> mFilePathCallback;
    private String mCameraPhotoPath;
    private boolean isInitialPageLoaded = false;
    private long backPressedTime = 0;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Initialize Native Views
        webView = findViewById(R.id.main_webview);
        swipeRefresh = findViewById(R.id.swipe_refresh);
        progressBar = findViewById(R.id.page_progress);
        connectivityBanner = findViewById(R.id.connectivity_banner);
        bannerText = findViewById(R.id.banner_text);
        splashOverlay = findViewById(R.id.splash_overlay);
        nativeErrorView = findViewById(R.id.native_error_view);
        btnRetry = findViewById(R.id.btn_retry_connection);
        btnBrowseCached = findViewById(R.id.btn_browse_cached);

        // Core Native Systems
        localStore = new RaqamiyatLocalStore(this);
        connectivityHelper = new ConnectivityHelper(this);
        connectivityHelper.setListener(this);
        nativeBridge = new RaqamiyatNativeBridge(this, connectivityHelper, localStore, this);

        createNotificationChannel();
        setupWebView();
        setupErrorView();
        setupSwipeRefresh();
        checkAndRequestPermissions();

        connectivityHelper.startMonitoring();

        // Handle Deep Linking or Default URL
        Intent intent = getIntent();
        if (intent != null && intent.getData() != null) {
            webView.loadUrl(intent.getData().toString());
        } else {
            webView.loadUrl(BASE_URL);
        }

        // Background catalog sync if online
        syncCatalogCacheInBackground();
    }

    private void setupWebView() {
        WebSettings settings = webView.getSettings();

        // JavaScript & DOM Storage
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        // Responsive Viewport Configuration (strictly 1:1, prevent horizontal blowout)
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(false);
        settings.setTextZoom(100); // Prevents system font size from breaking layouts
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        // Mixed Content Security
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        // Hardware Acceleration & Custom Native User-Agent
        settings.setUserAgentString(settings.getUserAgentString() + " RaqamiyatAndroid/2.0 NativeApp");

        // Cookies & Sessions
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        // Set initial cache mode based on connectivity
        if (connectivityHelper.isOnline()) {
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        } else {
            settings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
        }

        // Register Native JavaScript Bridge
        webView.addJavascriptInterface(nativeBridge, "RaqamiyatNative");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                progressBar.setVisibility(View.VISIBLE);
                super.onPageStarted(view, url, favicon);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
                swipeRefresh.setRefreshing(false);
                nativeErrorView.setVisibility(View.GONE);

                // Dismiss splash screen smoothly after first load
                if (!isInitialPageLoaded) {
                    isInitialPageLoaded = true;
                    dismissSplashOverlay();
                }

                super.onPageFinished(view, url);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    progressBar.setVisibility(View.GONE);
                    swipeRefresh.setRefreshing(false);

                    if (!connectivityHelper.isOnline()) {
                        // Show offline banner and try to fallback to cached catalog
                        showConnectivityBanner(false);
                        String cachedJson = localStore.getCachedCatalogJson();
                        if (cachedJson == null) {
                            nativeErrorView.setVisibility(View.VISIBLE);
                            dismissSplashOverlay();
                        }
                    } else {
                        nativeErrorView.setVisibility(View.VISIBLE);
                        dismissSplashOverlay();
                    }
                }
                super.onReceivedError(view, request, error);
            }

            @Nullable
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                // If offline and request is an image, check local image disk cache
                String url = request.getUrl().toString();
                if (!connectivityHelper.isOnline() && (url.contains("/media/") || url.endsWith(".png") || url.endsWith(".jpg") || url.endsWith(".jpeg"))) {
                    File cachedImg = localStore.getCachedImageFile(url);
                    if (cachedImg != null && cachedImg.exists()) {
                        try {
                            FileInputStream fis = new FileInputStream(cachedImg);
                            String mime = url.endsWith(".png") ? "image/png" : "image/jpeg";
                            return new WebResourceResponse(mime, "UTF-8", fis);
                        } catch (Exception ignored) {
                        }
                    }
                }
                return super.shouldInterceptRequest(view, request);
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
            }

            // WebRTC Camera & Microphone permission for Camera Studio
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> {
                    String[] resources = request.getResources();
                    request.grant(resources);
                });
            }

            // Native Camera & File Chooser (Supports both single and multiple selection)
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (mFilePathCallback != null) {
                    mFilePathCallback.onReceiveValue(null);
                }
                mFilePathCallback = filePathCallback;

                boolean allowsMultiple = (fileChooserParams.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);

                Intent takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                if (takePictureIntent.resolveActivity(getPackageManager()) != null) {
                    File photoFile = null;
                    try {
                        photoFile = createImageFile();
                        takePictureIntent.putExtra("PhotoPath", mCameraPhotoPath);
                    } catch (IOException ignored) {
                    }

                    if (photoFile != null) {
                        mCameraPhotoPath = "file:" + photoFile.getAbsolutePath();
                        Uri photoURI = FileProvider.getUriForFile(MainActivity.this,
                                getPackageName() + ".fileprovider",
                                photoFile);
                        takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoURI);
                    } else {
                        takePictureIntent = null;
                    }
                }

                Intent contentSelectionIntent = new Intent(Intent.ACTION_GET_CONTENT);
                contentSelectionIntent.addCategory(Intent.CATEGORY_OPENABLE);
                contentSelectionIntent.setType("image/*");
                if (allowsMultiple) {
                    contentSelectionIntent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                }

                Intent[] intentArray = (takePictureIntent != null) ? new Intent[]{takePictureIntent} : new Intent[0];

                Intent chooserIntent = new Intent(Intent.ACTION_CHOOSER);
                chooserIntent.putExtra(Intent.EXTRA_INTENT, contentSelectionIntent);
                chooserIntent.putExtra(Intent.EXTRA_TITLE, "التقاط صورة المنتج أو اختيار من المعرض");
                chooserIntent.putExtra(Intent.EXTRA_INITIAL_INTENTS, intentArray);

                startActivityForResult(chooserIntent, FILE_CHOOSER_REQUEST_CODE);
                return true;
            }
        });
    }

    private void setupSwipeRefresh() {
        swipeRefresh.setOnRefreshListener(() -> {
            if (connectivityHelper.isOnline()) {
                webView.reload();
                syncCatalogCacheInBackground();
            } else {
                swipeRefresh.setRefreshing(false);
                Toast.makeText(this, "وضع عدم الاتصال: يتم عرض البيانات المحفوظة", Toast.LENGTH_SHORT).show();
            }
        });
        swipeRefresh.setColorSchemeColors(0xFF06B6D4, 0xFFD4A853);
    }

    private void setupErrorView() {
        btnRetry.setOnClickListener(v -> {
            nativeErrorView.setVisibility(View.GONE);
            progressBar.setVisibility(View.VISIBLE);
            webView.reload();
        });

        btnBrowseCached.setOnClickListener(v -> {
            nativeErrorView.setVisibility(View.GONE);
            webView.loadUrl(CATALOG_URL);
        });
    }

    private void dismissSplashOverlay() {
        if (splashOverlay != null && splashOverlay.getVisibility() == View.VISIBLE) {
            AlphaAnimation fadeOut = new AlphaAnimation(1.0f, 0.0f);
            fadeOut.setDuration(400);
            fadeOut.setFillAfter(true);
            splashOverlay.startAnimation(fadeOut);
            mainHandler.postDelayed(() -> splashOverlay.setVisibility(View.GONE), 400);
        }
    }

    @Override
    public void onConnectivityChanged(boolean isOnline) {
        runOnUiThread(() -> {
            showConnectivityBanner(isOnline);
            if (isOnline) {
                webView.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
                syncCatalogCacheInBackground();
            } else {
                webView.getSettings().setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
            }
        });
    }

    private void showConnectivityBanner(boolean isOnline) {
        if (!isOnline) {
            connectivityBanner.setBackgroundColor(Color.parseColor("#b45309")); // Amber
            bannerText.setText("⚠️ أنت تتصفح بدون إنترنت • يتم عرض البيانات المخزنة محلياً");
            connectivityBanner.setVisibility(View.VISIBLE);
        } else {
            connectivityBanner.setBackgroundColor(Color.parseColor("#059669")); // Emerald
            bannerText.setText("⚡ تم استعادة الاتصال بالإنترنت • البيانات محدثة");
            connectivityBanner.setVisibility(View.VISIBLE);
            // Hide banner after 3.5 seconds
            mainHandler.postDelayed(() -> {
                if (connectivityHelper.isOnline()) {
                    connectivityBanner.setVisibility(View.GONE);
                }
            }, 3500);
        }
    }

    private void syncCatalogCacheInBackground() {
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(OFFLINE_API_URL).openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(8000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/2.0 CacheSync");
                conn.connect();

                if (conn.getResponseCode() == 200) {
                    Scanner scanner = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    if (!json.isEmpty()) {
                        localStore.saveCatalogJson(json);
                    }
                }
            } catch (Exception ignored) {
            }
        });
    }

    private File createImageFile() throws IOException {
        String timeStamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(new Date());
        String imageFileName = "PRODUCT_STUDIO_" + timeStamp + "_";
        File storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
        return File.createTempFile(imageFileName, ".jpg", storageDir);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (mFilePathCallback == null) {
                super.onActivityResult(requestCode, resultCode, data);
                return;
            }

            Uri[] results = null;
            if (resultCode == RESULT_OK) {
                if (data != null && data.getClipData() != null) {
                    // Multiple files selected
                    ClipData clipData = data.getClipData();
                    int count = clipData.getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = clipData.getItemAt(i).getUri();
                    }
                } else if (data != null && data.getData() != null) {
                    // Single file selected from gallery
                    results = new Uri[]{data.getData()};
                } else if (mCameraPhotoPath != null) {
                    // Camera photo capture
                    results = new Uri[]{Uri.parse(mCameraPhotoPath)};
                }
            }

            mFilePathCallback.onReceiveValue(results);
            mFilePathCallback = null;
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

    @Override
    public void onBackPressed() {
        if (nativeErrorView.getVisibility() == View.VISIBLE) {
            nativeErrorView.setVisibility(View.GONE);
            webView.loadUrl(BASE_URL);
            return;
        }

        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            // Double back to exit
            if (backPressedTime + 2000 > System.currentTimeMillis()) {
                super.onBackPressed();
            } else {
                Toast.makeText(this, "اضغط مرة أخرى للخروج من التطبيق", Toast.LENGTH_SHORT).show();
                backPressedTime = System.currentTimeMillis();
            }
        }
    }

    @Override
    public void onOpenNativeStudio() {
        webView.loadUrl("https://raqamiyatapp.com/control/camera-studio/");
    }

    @Override
    public void onTransactionSuccess(String orderId) {
        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("رقميات | تم تأكيد طلبك بنجاح ⚡")
                .setContentText("طلبك رقم #" + orderId + " قيد المعالجة السريعة الآن.")
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true);

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify((int) System.currentTimeMillis(), builder.build());
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            CharSequence name = "إشعارات رقميات";
            String description = "إشعارات الطلبات والعمليات الهامة";
            int importance = NotificationManager.IMPORTANCE_HIGH;
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, name, importance);
            channel.setDescription(description);
            channel.enableVibration(true);

            NotificationManager notificationManager = getSystemService(NotificationManager.class);
            if (notificationManager != null) {
                notificationManager.createNotificationChannel(channel);
            }
        }
    }

    private void checkAndRequestPermissions() {
        List<String> permissions = new ArrayList<>();
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(Manifest.permission.CAMERA);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.POST_NOTIFICATIONS);
            }
        }
        if (!permissions.isEmpty()) {
            ActivityCompat.requestPermissions(this, permissions.toArray(new String[0]), PERMISSIONS_REQUEST_CODE);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (connectivityHelper != null) {
            connectivityHelper.stopMonitoring();
        }
    }
}
