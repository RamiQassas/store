package com.raqamiyat.app;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
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
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.adapter.CategoryAdapter;
import com.raqamiyat.app.adapter.ProductAdapter;
import com.raqamiyat.app.model.CartItem;
import com.raqamiyat.app.model.GatewayItem;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Iterator;
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
    private static final int PRODUCT_DETAIL_REQUEST_CODE = 4001;
    private static final int NATIVE_STUDIO_REQUEST_CODE = 4002;

    private static final int TAB_HOME = 0;
    private static final int TAB_CATALOG = 1;
    private static final int TAB_WALLET = 2;
    private static final int TAB_ORDERS = 3;
    private static final int TAB_ACCOUNT = 4;

    // Storefront Views
    private LinearLayout nativeStoreContainer;
    private SwipeRefreshLayout nativeCatalogSwipe;
    private RecyclerView nativeCategoriesRv;
    private RecyclerView nativeProductsRv;
    private EditText nativeSearchInput;
    private TextView nativeEmptyState;
    private Button btnAdminQuickStudio;
    private TextView btnNativeCurrency;
    private Button btnNativePay;
    private Button btnNativeNotif;
    private Button btnNativeCart;
    private LinearLayout heroWalletBanner;
    private TextView heroWalletLabel;
    private TextView heroWalletValue;
    private LinearLayout heroGatewaysStrip;

    // Native Orders Views
    private LinearLayout nativeOrdersContainer;
    private SwipeRefreshLayout nativeOrdersSwipe;
    private LinearLayout nativeOrdersList;
    private Button btnOrdersRefresh;

    // Native Account Views
    private LinearLayout nativeAccountContainer;
    private LinearLayout nativeAccountBody;

    // Data & State
    private CatalogRepository catalogRepository;
    private AppNotificationSync notificationSync;
    private final List<AppNotificationSync.AppNotifItem> latestNotifications = new ArrayList<>();
    private CategoryAdapter categoryAdapter;
    private ProductAdapter productAdapter;
    private final List<ProductItem> allProducts = new ArrayList<>();
    private final List<GatewayItem> liveGateways = new ArrayList<>();
    private String activeCategoryId = "";
    private String activeSearchQuery = "";
    private int activeNativeTab = TAB_HOME;
    private boolean isNativeMode = true;

    // Live User & Wallet Snapshot
    private boolean isAuthenticated = false;
    private boolean isAdminUser = false;
    private String userFullName = "";
    private String userEmail = "";
    private String userNameHandle = "";
    private boolean userIsVerified = false;
    private double liveBalanceUsd = 0.0;
    private double liveBalanceSyp = 0.0;
    private String cachedGoogleLoginUrl = "";

    // WebView Portal Views (Fallback for external payment gateways / admin studio pages)
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
    private boolean isWaitingForGoogleAuth = false;
    private boolean isWaitingForExternalPayment = false;
    private long backPressedTime = 0;
    private String cleanChromeUserAgent = "";
    private String appWebViewUserAgent = "";
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }

        setContentView(R.layout.activity_main);

        // Bind Storefront Views
        nativeStoreContainer = findViewById(R.id.native_store_container);
        nativeCatalogSwipe = findViewById(R.id.native_catalog_swipe);
        nativeCategoriesRv = findViewById(R.id.native_categories_rv);
        nativeProductsRv = findViewById(R.id.native_products_rv);
        nativeSearchInput = findViewById(R.id.native_search_input);
        nativeEmptyState = findViewById(R.id.native_empty_state);
        btnAdminQuickStudio = findViewById(R.id.btn_admin_quick_studio);
        btnNativeCurrency = findViewById(R.id.btn_native_currency);
        btnNativePay = findViewById(R.id.btn_native_pay);
        btnNativeNotif = findViewById(R.id.btn_native_notif);
        btnNativeCart = findViewById(R.id.btn_native_cart);
        heroWalletBanner = findViewById(R.id.hero_wallet_banner);
        heroWalletLabel = findViewById(R.id.hero_wallet_label);
        heroWalletValue = findViewById(R.id.hero_wallet_value);
        heroGatewaysStrip = findViewById(R.id.hero_gateways_strip);

        // Bind Native Orders & Account Views
        nativeOrdersContainer = findViewById(R.id.native_orders_container);
        nativeOrdersSwipe = findViewById(R.id.native_orders_swipe);
        nativeOrdersList = findViewById(R.id.native_orders_list);
        btnOrdersRefresh = findViewById(R.id.btn_orders_refresh);
        nativeAccountContainer = findViewById(R.id.native_account_container);
        nativeAccountBody = findViewById(R.id.native_account_body);

        // Bind WebView Views
        webView = findViewById(R.id.main_webview);
        swipeRefresh = findViewById(R.id.swipe_refresh);
        progressBar = findViewById(R.id.page_progress);
        connectivityBanner = findViewById(R.id.connectivity_banner);
        bannerText = findViewById(R.id.banner_text);
        splashOverlay = findViewById(R.id.splash_overlay);
        nativeErrorView = findViewById(R.id.native_error_view);
        btnRetry = findViewById(R.id.btn_retry_connection);
        btnBrowseCached = findViewById(R.id.btn_browse_cached);

        // Core Systems
        localStore = new RaqamiyatLocalStore(this);
        catalogRepository = new CatalogRepository(localStore);
        notificationSync = new AppNotificationSync(this);
        connectivityHelper = new ConnectivityHelper(this);
        connectivityHelper.setListener(this);
        nativeBridge = new RaqamiyatNativeBridge(this, connectivityHelper, localStore, this);

        createNotificationChannel();
        connectivityHelper.startMonitoring();
        setupNativeStorefront();
        setupNativeOrdersView();
        setupWebView();
        setupErrorView();
        setupSwipeRefresh();
        setupBottomNavigation();
        checkAndRequestPermissions();

        updateHeaderBadges();
        renderAccountTab();

        Intent intent = getIntent();
        String openUrlExtra = intent != null ? intent.getStringExtra(ProductDetailActivity.EXTRA_OPEN_URL) : null;
        if (openUrlExtra != null && !openUrlExtra.isEmpty()) {
            showWebMode(openUrlExtra);
        } else if (intent != null && intent.getData() != null) {
            handleIncomingDeepLink(intent.getData());
        } else {
            switchToNativeTab(TAB_HOME);
        }

        loadNativeCatalog(false);
        syncLiveWalletAndSession();
        notificationSync.startContinuousBackgroundSync();
        syncAppNotifications();
        checkForAppUpdatesInBackground();
    }

    private int dp(int val) {
        return Math.round(val * getResources().getDisplayMetrics().density);
    }

    private void setupNativeStorefront() {
        nativeCategoriesRv.setLayoutManager(new LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false));
        categoryAdapter = new CategoryAdapter(categoryId -> {
            activeCategoryId = categoryId;
            applyProductFilters();
        });
        nativeCategoriesRv.setAdapter(categoryAdapter);

        nativeProductsRv.setLayoutManager(new GridLayoutManager(this, 2));
        productAdapter = new ProductAdapter(product -> {
            Intent detailIntent = new Intent(MainActivity.this, ProductDetailActivity.class);
            detailIntent.putExtra(ProductDetailActivity.EXTRA_PRODUCT, product);
            startActivityForResult(detailIntent, PRODUCT_DETAIL_REQUEST_CODE);
        });
        productAdapter.setOnAddToCartClickListener(product -> {
            VariantItem v = (product.variants != null && !product.variants.isEmpty()) ? product.variants.get(0) : null;
            double uPrice = v != null ? v.price : product.price;
            String vId = v != null ? v.id : "default";
            String vName = v != null ? v.name : product.name;
            int cnt = localStore.addToCart(new CartItem(product.id, vId, product.name, vName, product.imageUrl, uPrice, 1, ""));
            updateHeaderBadges();
            Toast.makeText(MainActivity.this, "🛒 تمت الإضافة إلى السلة (" + cnt + ")", Toast.LENGTH_SHORT).show();
        });
        productAdapter.updateCurrencyConfig(localStore.getPreferredCurrency(), localStore.getSypRate());
        nativeProductsRv.setAdapter(productAdapter);

        nativeCatalogSwipe.setColorSchemeColors(0xFF06B6D4, 0xFFD4A853);
        nativeCatalogSwipe.setOnRefreshListener(() -> {
            loadNativeCatalog(true);
            syncLiveWalletAndSession();
        });

        nativeSearchInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                activeSearchQuery = s != null ? s.toString().trim().toLowerCase(Locale.ROOT) : "";
                applyProductFilters();
            }

            @Override
            public void afterTextChanged(Editable s) {}
        });

        btnAdminQuickStudio.setOnClickListener(v -> launchNativeStudio());

        btnNativeCurrency.setOnClickListener(v -> {
            String next = localStore.togglePreferredCurrency();
            onGlobalCurrencyChanged();
            Toast.makeText(this, "تم التبديل إلى " + ("USD".equals(next) ? "الدولار الأمريكي ($)" : "الليرة السورية (ل.س)"), Toast.LENGTH_SHORT).show();
        });

        View.OnClickListener openWalletAction = v -> {
            if (!connectivityHelper.isOnline()) {
                nativeBridge.showOfflineTransactionAlert("المحفظة وبوابات الدفع");
                return;
            }
            startActivity(new Intent(MainActivity.this, NativePaymentActivity.class));
        };
        btnNativePay.setOnClickListener(openWalletAction);
        heroWalletBanner.setOnClickListener(v -> {
            if (!isAuthenticated) {
                openNativeLoginSheet();
            } else {
                openWalletAction.onClick(v);
            }
        });

        btnNativeNotif.setOnClickListener(v -> showNotificationsInboxDialog());
        btnNativeCart.setOnClickListener(v -> NativeCartHelper.showCartSheet(
                MainActivity.this,
                catalogRepository,
                localStore,
                new NativeCartHelper.CartUpdateCallback() {
                    @Override
                    public void onCartChanged() {
                        updateHeaderBadges();
                    }

                    @Override
                    public void onOrderCompleted(String orderNumber) {
                        updateHeaderBadges();
                        syncLiveWalletAndSession();
                        switchToNativeTab(TAB_ORDERS);
                    }
                }
        ));
    }

    private void setupNativeOrdersView() {
        nativeOrdersSwipe.setColorSchemeColors(0xFF06B6D4, 0xFFD4A853);
        nativeOrdersSwipe.setOnRefreshListener(this::loadNativeOrders);
        btnOrdersRefresh.setOnClickListener(v -> loadNativeOrders());
    }

    private void onGlobalCurrencyChanged() {
        String curr = localStore.getPreferredCurrency();
        double rate = localStore.getSypRate();
        updateHeaderBadges();
        productAdapter.updateCurrencyConfig(curr, rate);
        updateHeroWalletBanner();
        if (activeNativeTab == TAB_ORDERS) {
            loadNativeOrders();
        } else if (activeNativeTab == TAB_ACCOUNT) {
            renderAccountTab();
        }
    }

    private void updateHeaderBadges() {
        String curr = localStore.getPreferredCurrency();
        btnNativeCurrency.setText("USD".equals(curr) ? "USD $" : "ل.س SYP");
        int cartCnt = localStore.getCartCount();
        btnNativeCart.setText("🛒 " + cartCnt);
    }

    private void updateHeroWalletBanner() {
        if (!isAuthenticated) {
            heroWalletLabel.setText("مرحباً بك في تطبيق رقميات ⚡");
            heroWalletValue.setText("اضغط هنا لتسجيل الدخول ومزامنة رصيدك ←");
        } else {
            String curr = localStore.getPreferredCurrency();
            heroWalletLabel.setText(!userFullName.isEmpty() ? ("رصيد محفظة " + userFullName) : "رصيد محفظتك الحقيقي");
            if ("USD".equals(curr)) {
                double sypEq = liveBalanceSyp > 0 ? liveBalanceSyp : (liveBalanceUsd * localStore.getSypRate());
                heroWalletValue.setText(String.format(Locale.US, "$%.2f  •  %s", liveBalanceUsd, RaqamiyatLocalStore.formatSypAmount(sypEq)));
            } else {
                double sypDisp = liveBalanceSyp > 0 ? liveBalanceSyp : (liveBalanceUsd * localStore.getSypRate());
                heroWalletValue.setText(String.format(Locale.US, "%s  •  $%.2f", RaqamiyatLocalStore.formatSypAmount(sypDisp), liveBalanceUsd));
            }
        }

        // Render Official Gateways Logos Strip via Glide
        heroGatewaysStrip.removeAllViews();
        int shown = 0;
        for (GatewayItem g : liveGateways) {
            if (!"gateway".equals(g.type)) continue;
            if (shown >= 3) break;
            shown++;

            LinearLayout box = new LinearLayout(this);
            box.setBackgroundResource(R.drawable.bg_logo_box);
            box.setGravity(Gravity.CENTER);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(34), dp(34));
            lp.setMarginStart(dp(5));
            box.setLayoutParams(lp);
            if (g.isUnavailable) box.setAlpha(0.5f);

            ImageView iv = new ImageView(this);
            iv.setLayoutParams(new LinearLayout.LayoutParams(dp(26), dp(26)));
            iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
            String logoUrl = !g.logoUrl.isEmpty() ? g.logoUrl : (CatalogRepository.DOMAIN + "/api/app/gateway-logo/" + g.provider + "/");
            Glide.with(this)
                    .load(logoUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .into(iv);
            box.addView(iv);
            heroGatewaysStrip.addView(box);
        }
    }

    private void syncLiveWalletAndSession() {
        catalogRepository.fetchWalletAndGateways((code, obj, err) -> {
            if (obj == null) return;
            isAuthenticated = obj.optBoolean("is_authenticated", false);
            cachedGoogleLoginUrl = obj.optString("google_login_url", "");

            List<GatewayItem> gws = GatewayItem.parseList(obj.optJSONArray("gateways"));
            if (!gws.isEmpty()) {
                liveGateways.clear();
                liveGateways.addAll(gws);
            }

            if (isAuthenticated) {
                liveBalanceUsd = obj.optDouble("available_balance_usd", obj.optDouble("balance", 0.0));
                liveBalanceSyp = obj.optDouble("available_balance_syp", liveBalanceUsd * localStore.getSypRate());
                JSONObject u = obj.optJSONObject("user");
                if (u != null) {
                    userFullName = u.optString("full_name", "");
                    userEmail = u.optString("email", "");
                    userNameHandle = u.optString("username", "");
                    userIsVerified = u.optBoolean("is_verified", false);
                    isAdminUser = u.optBoolean("is_admin", false);
                }
            } else {
                isAdminUser = false;
                liveBalanceUsd = 0.0;
                liveBalanceSyp = 0.0;
            }

            btnAdminQuickStudio.setVisibility(isAdminUser ? View.VISIBLE : View.GONE);
            productAdapter.updateCurrencyConfig(localStore.getPreferredCurrency(), localStore.getSypRate());
            updateHeroWalletBanner();
            if (activeNativeTab == TAB_ACCOUNT) {
                renderAccountTab();
            }
        });
    }

    private void openNativeLoginSheet() {
        NativeAuthHelper.showLoginSheet(this, catalogRepository, localStore, cachedGoogleLoginUrl, authData -> {
            syncLiveWalletAndSession();
            if (activeNativeTab == TAB_ORDERS) {
                loadNativeOrders();
            } else if (activeNativeTab == TAB_ACCOUNT) {
                renderAccountTab();
            }
        });
    }

    private void loadNativeOrders() {
        nativeOrdersSwipe.setRefreshing(true);
        catalogRepository.getJson(CatalogRepository.ORDERS_API_URL, (code, obj, err) -> {
            nativeOrdersSwipe.setRefreshing(false);
            nativeOrdersList.removeAllViews();

            if (obj == null) {
                addOrdersEmptyCard("تعذر جلب الطلبات حالياً، اسحب للأسفل لإعادة المحاولة.", false);
                return;
            }
            if (!obj.optBoolean("is_authenticated", false)) {
                addOrdersEmptyCard("سجّل دخولك لعرض سجل طلباتك وأكواد الشحن الفورية.", true);
                return;
            }

            JSONArray arr = obj.optJSONArray("orders");
            if (arr == null || arr.length() == 0) {
                addOrdersEmptyCard("لا توجد طلبات سابقة في حسابك حتى الآن.\nابدأ بتصفح المنتجات واستمتع بالتسليم الفوري ⚡", false);
                return;
            }

            String prefCurr = localStore.getPreferredCurrency();
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.optJSONObject(i);
                if (o == null) continue;

                final String orderId = o.optString("id", "");
                final String orderNumber = o.optString("number", "");
                String title = o.optString("title", "طلب رقميات");
                String imgUrl = o.optString("image_url", "");
                double totalUsd = o.optDouble("total_usd", 0.0);
                double totalSyp = o.optDouble("total_syp", totalUsd * localStore.getSypRate());
                String st = o.optString("status", "");
                String stAr = o.optString("status_ar", st);
                String payAr = o.optString("payment_method_ar", "محفظة رقميات");
                String createdAt = o.optString("created_at", "");
                boolean canCancel = o.optBoolean("can_cancel", false);

                LinearLayout card = new LinearLayout(this);
                card.setOrientation(LinearLayout.VERTICAL);
                card.setBackgroundResource(R.drawable.bg_card_dark);
                card.setPadding(dp(14), dp(14), dp(14), dp(14));
                LinearLayout.LayoutParams cLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                cLp.bottomMargin = dp(10);
                card.setLayoutParams(cLp);

                // Top Row: Image + Title + Status Badge
                LinearLayout topRow = new LinearLayout(this);
                topRow.setOrientation(LinearLayout.HORIZONTAL);
                topRow.setGravity(Gravity.CENTER_VERTICAL);

                ImageView iv = new ImageView(this);
                LinearLayout.LayoutParams ivLp = new LinearLayout.LayoutParams(dp(46), dp(46));
                ivLp.setMarginEnd(dp(10));
                iv.setLayoutParams(ivLp);
                iv.setBackgroundResource(R.drawable.bg_logo_box);
                iv.setPadding(dp(3), dp(3), dp(3), dp(3));
                if (!imgUrl.isEmpty()) {
                    Glide.with(this).load(imgUrl).placeholder(R.mipmap.ic_launcher).into(iv);
                } else {
                    iv.setImageResource(R.mipmap.ic_launcher);
                }
                topRow.addView(iv);

                LinearLayout infoCol = new LinearLayout(this);
                infoCol.setOrientation(LinearLayout.VERTICAL);
                infoCol.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

                TextView tTv = new TextView(this);
                tTv.setText(title);
                tTv.setTextColor(0xFFFFFFFF);
                tTv.setTextSize(13.5f);
                tTv.setTypeface(tTv.getTypeface(), Typeface.BOLD);
                infoCol.addView(tTv);

                TextView subTv = new TextView(this);
                subTv.setText("#" + orderNumber + " • " + payAr + " • " + createdAt);
                subTv.setTextColor(0xFF94A3B8);
                subTv.setTextSize(10.5f);
                infoCol.addView(subTv);
                topRow.addView(infoCol);

                TextView badge = new TextView(this);
                badge.setText(stAr);
                badge.setTextSize(10.5f);
                badge.setTypeface(badge.getTypeface(), Typeface.BOLD);
                badge.setPadding(dp(10), dp(4), dp(10), dp(4));
                if ("completed".equals(st) || "delivered".equals(st)) {
                    badge.setTextColor(0xFF6EE7B7);
                    badge.setBackgroundResource(R.drawable.bg_badge_green);
                } else if ("cancelled".equals(st) || "refunded".equals(st)) {
                    badge.setTextColor(0xFFFCA5A5);
                    badge.setBackgroundResource(R.drawable.bg_badge_red);
                } else {
                    badge.setTextColor(0xFFFDE68A);
                    badge.setBackgroundResource(R.drawable.bg_badge_amber);
                }
                topRow.addView(badge);
                card.addView(topRow);

                // Price Row
                TextView priceTv = new TextView(this);
                String pDisp = "SYP".equals(prefCurr)
                        ? (RaqamiyatLocalStore.formatSypAmount(totalSyp) + String.format(Locale.US, " (≈ $%.2f)", totalUsd))
                        : (String.format(Locale.US, "$%.2f", totalUsd) + " (≈ " + RaqamiyatLocalStore.formatSypAmount(totalSyp) + ")");
                priceTv.setText("الإجمالي: " + pDisp);
                priceTv.setTextColor(0xFFFBBF24);
                priceTv.setTextSize(13f);
                priceTv.setTypeface(priceTv.getTypeface(), Typeface.BOLD);
                priceTv.setPadding(0, dp(8), 0, 0);
                card.addView(priceTv);

                // Deliverable Digital Codes / PINs Box
                JSONObject ff = o.optJSONObject("fulfillment");
                if (ff != null && ff.length() > 0) {
                    LinearLayout codeBox = new LinearLayout(this);
                    codeBox.setOrientation(LinearLayout.VERTICAL);
                    codeBox.setBackgroundResource(R.drawable.bg_gateway_selected);
                    codeBox.setPadding(dp(12), dp(10), dp(12), dp(10));
                    LinearLayout.LayoutParams cbLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                    cbLp.topMargin = dp(10);
                    codeBox.setLayoutParams(cbLp);

                    Iterator<String> keys = ff.keys();
                    while (keys.hasNext()) {
                        final String k = keys.next();
                        final String v = ff.optString(k, "");
                        if (v.isEmpty()) continue;

                        LinearLayout kRow = new LinearLayout(this);
                        kRow.setOrientation(LinearLayout.HORIZONTAL);
                        kRow.setGravity(Gravity.CENTER_VERTICAL);

                        TextView kvTv = new TextView(this);
                        kvTv.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
                        kvTv.setText("🎁 " + k + ": " + v);
                        kvTv.setTextColor(0xFFFFFFFF);
                        kvTv.setTextSize(12.5f);
                        kvTv.setTypeface(kvTv.getTypeface(), Typeface.BOLD);
                        kRow.addView(kvTv);

                        TextView copyBtn = new TextView(this);
                        copyBtn.setText("نسخ 📋");
                        copyBtn.setTextColor(0xFF22D3EE);
                        copyBtn.setTextSize(11.5f);
                        copyBtn.setTypeface(copyBtn.getTypeface(), Typeface.BOLD);
                        copyBtn.setPadding(dp(8), dp(4), dp(8), dp(4));
                        copyBtn.setOnClickListener(view -> {
                            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                            if (cm != null) {
                                cm.setPrimaryClip(ClipData.newPlainText(k, v));
                                Toast.makeText(MainActivity.this, "تم نسخ الكود بنجاح!", Toast.LENGTH_SHORT).show();
                            }
                        });
                        kRow.addView(copyBtn);
                        codeBox.addView(kRow);
                    }
                    card.addView(codeBox);
                }

                // Action Buttons Row
                LinearLayout actionsRow = new LinearLayout(this);
                actionsRow.setOrientation(LinearLayout.HORIZONTAL);
                LinearLayout.LayoutParams arLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                arLp.topMargin = dp(10);
                actionsRow.setLayoutParams(arLp);

                Button detailsBtn = new Button(this);
                detailsBtn.setLayoutParams(new LinearLayout.LayoutParams(0, dp(34), 1f));
                detailsBtn.setBackgroundResource(R.drawable.bg_chip_unselected);
                detailsBtn.setText("📄 الفاتورة والتفاصيل");
                detailsBtn.setAllCaps(false);
                detailsBtn.setTextColor(0xFFE2E8F0);
                detailsBtn.setTextSize(11f);
                detailsBtn.setOnClickListener(v -> showWebMode(BASE_URL + "dashboard/orders/" + orderId + "/"));
                actionsRow.addView(detailsBtn);

                if ("processing".equals(st) || "pending".equals(st)) {
                    Button syncBtn = new Button(this);
                    LinearLayout.LayoutParams sLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(34));
                    sLp.setMarginStart(dp(6));
                    syncBtn.setLayoutParams(sLp);
                    syncBtn.setBackgroundResource(R.drawable.bg_chip_unselected);
                    syncBtn.setPadding(dp(10), 0, dp(10), 0);
                    syncBtn.setText("🔄 تحديث الحالة");
                    syncBtn.setAllCaps(false);
                    syncBtn.setTextColor(0xFF22D3EE);
                    syncBtn.setTextSize(11f);
                    syncBtn.setOnClickListener(v -> performOrderAction(orderId, "sync"));
                    actionsRow.addView(syncBtn);
                }

                if (canCancel) {
                    Button cancelBtn = new Button(this);
                    LinearLayout.LayoutParams xLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(34));
                    xLp.setMarginStart(dp(6));
                    cancelBtn.setLayoutParams(xLp);
                    cancelBtn.setBackgroundResource(R.drawable.bg_badge_red);
                    cancelBtn.setPadding(dp(10), 0, dp(10), 0);
                    cancelBtn.setText("✕ إلغاء");
                    cancelBtn.setAllCaps(false);
                    cancelBtn.setTextColor(0xFFFCA5A5);
                    cancelBtn.setTextSize(11f);
                    cancelBtn.setOnClickListener(v -> performOrderAction(orderId, "cancel"));
                    actionsRow.addView(cancelBtn);
                }

                card.addView(actionsRow);
                nativeOrdersList.addView(card);
            }
        });
    }

    private void performOrderAction(String orderId, String action) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("action", action);
            catalogRepository.postJson(BASE_URL + "api/app/orders/" + orderId + "/action/", payload, (code, json, err) -> {
                if (json != null) {
                    Toast.makeText(this, json.optString("message", "تم التحديث"), Toast.LENGTH_SHORT).show();
                }
                loadNativeOrders();
            });
        } catch (Exception ignored) {
        }
    }

    private void addOrdersEmptyCard(String text, boolean showLoginBtn) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.CENTER);
        card.setBackgroundResource(R.drawable.bg_card_dark);
        card.setPadding(dp(24), dp(32), dp(24), dp(32));

        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextColor(0xFFCBD5E1);
        tv.setTextSize(13.5f);
        tv.setGravity(Gravity.CENTER);
        card.addView(tv);

        if (showLoginBtn) {
            Button btn = new Button(this);
            btn.setBackgroundResource(R.drawable.bg_button_gold);
            btn.setText("تسجيل الدخول الآن ⚡");
            btn.setAllCaps(false);
            btn.setTextColor(0xFF030712);
            btn.setTypeface(btn.getTypeface(), Typeface.BOLD);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(44));
            lp.topMargin = dp(16);
            btn.setLayoutParams(lp);
            btn.setPadding(dp(24), 0, dp(24), 0);
            btn.setOnClickListener(v -> openNativeLoginSheet());
            card.addView(btn);
        }
        nativeOrdersList.addView(card);
    }

    private void renderAccountTab() {
        nativeAccountBody.removeAllViews();

        // 1. Profile / Login Hero Card
        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setBackgroundResource(R.drawable.bg_wallet_hero);
        hero.setPadding(dp(18), dp(18), dp(18), dp(18));

        if (!isAuthenticated) {
            TextView t1 = new TextView(this);
            t1.setText("مرحباً بك في رقميات | Raqamiyat");
            t1.setTextColor(0xFFFFFFFF);
            t1.setTextSize(17f);
            t1.setTypeface(t1.getTypeface(), Typeface.BOLD);
            hero.addView(t1);

            TextView t2 = new TextView(this);
            t2.setText("سجّل دخولك لمزامنة محفظتك، عرض الرصيد بالدولار والليرة السورية، ومتابعة طلباتك الفورية.");
            t2.setTextColor(0xFFCBD5E1);
            t2.setTextSize(12f);
            t2.setPadding(0, dp(6), 0, dp(14));
            hero.addView(t2);

            Button loginBtn = new Button(this);
            loginBtn.setBackgroundResource(R.drawable.bg_button_gold);
            loginBtn.setText("🔐 تسجيل الدخول السريع");
            loginBtn.setAllCaps(false);
            loginBtn.setTextColor(0xFF030712);
            loginBtn.setTextSize(14f);
            loginBtn.setTypeface(loginBtn.getTypeface(), Typeface.BOLD);
            loginBtn.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)));
            loginBtn.setOnClickListener(v -> openNativeLoginSheet());
            hero.addView(loginBtn);
        } else {
            TextView nameTv = new TextView(this);
            nameTv.setText((!userFullName.isEmpty() ? userFullName : userNameHandle) + (userIsVerified ? "  ✓ موثق" : ""));
            nameTv.setTextColor(0xFFFFFFFF);
            nameTv.setTextSize(18f);
            nameTv.setTypeface(nameTv.getTypeface(), Typeface.BOLD);
            hero.addView(nameTv);

            if (!userEmail.isEmpty()) {
                TextView emailTv = new TextView(this);
                emailTv.setText(userEmail);
                emailTv.setTextColor(0xFF94A3B8);
                emailTv.setTextSize(12f);
                hero.addView(emailTv);
            }

            TextView balTv = new TextView(this);
            balTv.setText("رصيد المحفظة: " + localStore.formatPrice(liveBalanceUsd) + "  (" + localStore.formatSecondaryPrice(liveBalanceUsd) + ")");
            balTv.setTextColor(0xFFFBBF24);
            balTv.setTextSize(15f);
            balTv.setTypeface(balTv.getTypeface(), Typeface.BOLD);
            balTv.setPadding(0, dp(10), 0, dp(12));
            hero.addView(balTv);

            Button topupBtn = new Button(this);
            topupBtn.setBackgroundResource(R.drawable.bg_button_gold);
            topupBtn.setText("💳 شحن المحفظة وبوابات الدفع ⚡");
            topupBtn.setAllCaps(false);
            topupBtn.setTextColor(0xFF030712);
            topupBtn.setTextSize(13.5f);
            topupBtn.setTypeface(topupBtn.getTypeface(), Typeface.BOLD);
            topupBtn.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)));
            topupBtn.setOnClickListener(v -> startActivity(new Intent(MainActivity.this, NativePaymentActivity.class)));
            hero.addView(topupBtn);
        }
        nativeAccountBody.addView(hero);

        // 2. Global Currency Selector Card
        LinearLayout currCard = new LinearLayout(this);
        currCard.setOrientation(LinearLayout.VERTICAL);
        currCard.setBackgroundResource(R.drawable.bg_card_dark);
        currCard.setPadding(dp(16), dp(14), dp(16), dp(14));
        LinearLayout.LayoutParams ccLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ccLp.topMargin = dp(14);
        currCard.setLayoutParams(ccLp);

        TextView cTitle = new TextView(this);
        cTitle.setText("💱 عملة العرض والشراء في التطبيق");
        cTitle.setTextColor(0xFFFFFFFF);
        cTitle.setTextSize(14f);
        cTitle.setTypeface(cTitle.getTypeface(), Typeface.BOLD);
        currCard.addView(cTitle);

        TextView cSub = new TextView(this);
        cSub.setText("سعر الصرف المباشر: 1$ = " + RaqamiyatLocalStore.formatSypAmount(localStore.getSypRate()));
        cSub.setTextColor(0xFF94A3B8);
        cSub.setTextSize(11.5f);
        cSub.setPadding(0, dp(2), 0, dp(10));
        currCard.addView(cSub);

        LinearLayout cBtns = new LinearLayout(this);
        cBtns.setOrientation(LinearLayout.HORIZONTAL);
        boolean isUsd = "USD".equals(localStore.getPreferredCurrency());

        Button bUsd = new Button(this);
        LinearLayout.LayoutParams b1Lp = new LinearLayout.LayoutParams(0, dp(40), 1f);
        b1Lp.setMarginEnd(dp(8));
        bUsd.setLayoutParams(b1Lp);
        bUsd.setBackgroundResource(isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        bUsd.setText("الدولار ($ USD)");
        bUsd.setAllCaps(false);
        bUsd.setTextColor(isUsd ? 0xFF030712 : 0xFFE2E8F0);
        bUsd.setTypeface(bUsd.getTypeface(), Typeface.BOLD);
        bUsd.setOnClickListener(v -> {
            localStore.setPreferredCurrency("USD");
            onGlobalCurrencyChanged();
        });
        cBtns.addView(bUsd);

        Button bSyp = new Button(this);
        bSyp.setLayoutParams(new LinearLayout.LayoutParams(0, dp(40), 1f));
        bSyp.setBackgroundResource(!isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        bSyp.setText("الليرة السورية (ل.س)");
        bSyp.setAllCaps(false);
        bSyp.setTextColor(!isUsd ? 0xFF030712 : 0xFFE2E8F0);
        bSyp.setTypeface(bSyp.getTypeface(), Typeface.BOLD);
        bSyp.setOnClickListener(v -> {
            localStore.setPreferredCurrency("SYP");
            onGlobalCurrencyChanged();
        });
        cBtns.addView(bSyp);
        currCard.addView(cBtns);
        nativeAccountBody.addView(currCard);

        // 3. Quick Actions Menu
        addAccountActionRow("💳 المحفظة وبوابات الدفع وسجل الإيداعات", "شام كاش، كاش موبايل، بيميرا وكروت الشحن",
                () -> startActivity(new Intent(this, NativePaymentActivity.class)));
        addAccountActionRow("📦 سجل طلباتي وأكواد البطاقات", "استعراض جميع مشترياتك ونسخ الأكواد بلمسة واحدة",
                () -> switchToNativeTab(TAB_ORDERS));
        addAccountActionRow("🔔 مركز الإشعارات والعروض الحصرية", "أحدث التخفيضات والتنبيهات في رقميات",
                this::showNotificationsInboxDialog);

        if (isAuthenticated) {
            addAccountActionRow("🛡️ الأمان وتوثيق الهوية (KYC & 2FA)", "إدارة كلمة المرور، التحقق بخطوتين وتوثيق الحساب",
                    () -> showWebMode(BASE_URL + "dashboard/"));
        }

        if (isAdminUser) {
            addAccountActionRow("🎛️ لوحة تحكم الإدارة الشاملة", "إدارة الطلبات، المنتجات، شام كاش والبوابات",
                    () -> showWebMode(BASE_URL + "control/"));
            addAccountActionRow("📷 استوديو تصوير المنتجات بالذكاء الاصطناعي", "عزل الخلفية وتحديث صور المنتجات بالكاميرا",
                    this::launchNativeStudio);
        }

        addAccountActionRow("💬 الدعم الفني والتواصل معنا", "فريق دعم رقميات في خدمتك على مدار الساعة",
                () -> showWebMode(BASE_URL + "contact/"));

        if (isAuthenticated) {
            Button logoutBtn = new Button(this);
            LinearLayout.LayoutParams loLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46));
            loLp.topMargin = dp(16);
            logoutBtn.setLayoutParams(loLp);
            logoutBtn.setBackgroundResource(R.drawable.bg_badge_red);
            logoutBtn.setText("🚪 تسجيل الخروج من الحساب");
            logoutBtn.setAllCaps(false);
            logoutBtn.setTextColor(0xFFFCA5A5);
            logoutBtn.setTypeface(logoutBtn.getTypeface(), Typeface.BOLD);
            logoutBtn.setOnClickListener(v -> {
                catalogRepository.postJson(CatalogRepository.LOGOUT_API_URL, new JSONObject(), (c, j, e) -> {
                    localStore.saveAppAuthToken("");
                    localStore.saveQuickAccountSnapshot(0.0, "", "");
                    CookieManager.getInstance().removeAllCookies(null);
                    CookieManager.getInstance().flush();
                    isAuthenticated = false;
                    isAdminUser = false;
                    liveBalanceUsd = 0.0;
                    liveBalanceSyp = 0.0;
                    btnAdminQuickStudio.setVisibility(View.GONE);
                    updateHeroWalletBanner();
                    renderAccountTab();
                    Toast.makeText(this, "تم تسجيل الخروج بنجاح", Toast.LENGTH_SHORT).show();
                });
            });
            nativeAccountBody.addView(logoutBtn);
        }
    }

    private void addAccountActionRow(String titleText, String subtitleText, Runnable onClick) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackgroundResource(R.drawable.bg_card_dark);
        row.setPadding(dp(14), dp(13), dp(14), dp(13));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(10);
        row.setLayoutParams(lp);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        TextView t1 = new TextView(this);
        t1.setText(titleText);
        t1.setTextColor(0xFFF8FAFC);
        t1.setTextSize(13.5f);
        t1.setTypeface(t1.getTypeface(), Typeface.BOLD);
        col.addView(t1);

        TextView t2 = new TextView(this);
        t2.setText(subtitleText);
        t2.setTextColor(0xFF94A3B8);
        t2.setTextSize(11f);
        col.addView(t2);

        row.addView(col);

        TextView arrow = new TextView(this);
        arrow.setText("←");
        arrow.setTextColor(0xFF22D3EE);
        arrow.setTextSize(15f);
        arrow.setTypeface(arrow.getTypeface(), Typeface.BOLD);
        row.addView(arrow);

        row.setOnClickListener(v -> {
            if (onClick != null) onClick.run();
        });
        nativeAccountBody.addView(row);
    }

    private void syncAppNotifications() {
        if (notificationSync == null || !connectivityHelper.isOnline()) return;
        notificationSync.syncNow(items -> {
            latestNotifications.clear();
            latestNotifications.addAll(items);
        });
    }

    private void showNotificationsInboxDialog() {
        syncAppNotifications();
        if (latestNotifications.isEmpty()) {
            new MaterialAlertDialogBuilder(this)
                    .setTitle("🔔 إشعارات وعروض رقميات")
                    .setMessage("لا توجد إشعارات أو عروض جديدة حالياً.")
                    .setPositiveButton("حسناً", (d, w) -> d.dismiss())
                    .show();
            return;
        }
        CharSequence[] titles = new CharSequence[latestNotifications.size()];
        for (int i = 0; i < latestNotifications.size(); i++) {
            AppNotificationSync.AppNotifItem item = latestNotifications.get(i);
            String icon = "discount".equals(item.category) ? "🔥 " : ("update".equals(item.category) ? "⚡ " : ("promo".equals(item.category) ? "🎁 " : "💬 "));
            titles[i] = icon + item.title + "\n" + item.body;
        }
        new MaterialAlertDialogBuilder(this)
                .setTitle("🔔 أحدث الإشعارات والعروض")
                .setItems(titles, (dialog, which) -> {
                    AppNotificationSync.AppNotifItem picked = latestNotifications.get(which);
                    if (picked.actionUrl != null && !picked.actionUrl.isEmpty()) {
                        String fullUrl = picked.actionUrl.startsWith("http") ? picked.actionUrl : BASE_URL + (picked.actionUrl.startsWith("/") ? picked.actionUrl.substring(1) : picked.actionUrl);
                        showWebMode(fullUrl);
                    }
                })
                .setNegativeButton("إغلاق", (d, w) -> d.dismiss())
                .show();
    }

    private void loadNativeCatalog(boolean forceNetwork) {
        catalogRepository.loadCatalog(forceNetwork, new CatalogRepository.CatalogCallback() {
            @Override
            public void onLoaded(CatalogRepository.CatalogData data, boolean fromCache) {
                nativeCatalogSwipe.setRefreshing(false);
                categoryAdapter.submitList(data.categories);
                allProducts.clear();
                allProducts.addAll(data.products);
                if (!data.gateways.isEmpty() && liveGateways.isEmpty()) {
                    liveGateways.addAll(data.gateways);
                    updateHeroWalletBanner();
                }
                productAdapter.updateCurrencyConfig(localStore.getPreferredCurrency(), localStore.getSypRate());
                applyProductFilters();
                if (!isInitialPageLoaded) {
                    isInitialPageLoaded = true;
                    dismissSplashOverlay();
                }
            }

            @Override
            public void onError(String message) {
                nativeCatalogSwipe.setRefreshing(false);
                if (!isInitialPageLoaded) {
                    isInitialPageLoaded = true;
                    dismissSplashOverlay();
                }
                if (allProducts.isEmpty()) {
                    nativeEmptyState.setText(message);
                    nativeEmptyState.setVisibility(View.VISIBLE);
                }
            }
        });
    }

    private void applyProductFilters() {
        List<ProductItem> filtered = new ArrayList<>();
        for (ProductItem p : allProducts) {
            boolean matchesCat = activeCategoryId.isEmpty() || activeCategoryId.equals(p.categoryId);
            boolean matchesQuery = activeSearchQuery.isEmpty()
                    || (p.name != null && p.name.toLowerCase(Locale.ROOT).contains(activeSearchQuery))
                    || (p.categoryName != null && p.categoryName.toLowerCase(Locale.ROOT).contains(activeSearchQuery))
                    || (p.code != null && p.code.toLowerCase(Locale.ROOT).contains(activeSearchQuery));
            if (matchesCat && matchesQuery) {
                filtered.add(p);
            }
        }
        productAdapter.submitList(filtered);
        nativeEmptyState.setVisibility(filtered.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private void switchToNativeTab(int tab) {
        isNativeMode = true;
        activeNativeTab = tab;
        swipeRefresh.setVisibility(View.GONE);
        nativeErrorView.setVisibility(View.GONE);

        nativeStoreContainer.setVisibility((tab == TAB_HOME || tab == TAB_CATALOG) ? View.VISIBLE : View.GONE);
        nativeOrdersContainer.setVisibility(tab == TAB_ORDERS ? View.VISIBLE : View.GONE);
        nativeAccountContainer.setVisibility(tab == TAB_ACCOUNT ? View.VISIBLE : View.GONE);

        setActiveBottomTabHighlight(tab);

        if (tab == TAB_CATALOG) {
            nativeSearchInput.requestFocus();
        } else if (tab == TAB_ORDERS) {
            loadNativeOrders();
        } else if (tab == TAB_ACCOUNT) {
            renderAccountTab();
            syncLiveWalletAndSession();
        }
    }

    public static boolean isShamCashExternalUrl(String url) {
        if (url == null || url.isEmpty()) return false;
        String lower = url.trim().toLowerCase(Locale.ROOT);
        if (lower.startsWith("shamcash:") || lower.startsWith("shamcash://")) {
            return true;
        }
        try {
            Uri parsed = Uri.parse(url);
            String host = parsed.getHost() != null ? parsed.getHost().toLowerCase(Locale.ROOT) : "";
            return host.equals("shamcash.sy")
                    || host.endsWith(".shamcash.sy")
                    || host.equals("shamcash.com")
                    || host.endsWith(".shamcash.com")
                    || host.equals("shamlogix.tech")
                    || host.endsWith(".shamlogix.tech");
        } catch (Exception ignored) {
            return false;
        }
    }

    public static void launchExternalShamCashUrl(Context context, String url) {
        if (context == null || url == null || url.isEmpty()) return;
        try {
            Intent viewIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            viewIntent.addCategory(Intent.CATEGORY_BROWSABLE);
            viewIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(viewIntent);
        } catch (Exception e) {
            Toast.makeText(context, "تعذر فتح رابط الدفع الخارجي لشام كاش", Toast.LENGTH_SHORT).show();
        }
    }

    public static boolean tryLaunchNativeShamCashAppOnly(Context context, String url) {
        if (context == null || url == null || url.isEmpty()) return false;
        String lower = url.trim().toLowerCase(Locale.ROOT);
        if (lower.startsWith("shamcash:") || lower.startsWith("shamcash://")) {
            launchExternalShamCashUrl(context, url);
            return true;
        }
        try {
            PackageManager pm = context.getPackageManager();
            Intent probe = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            probe.addCategory(Intent.CATEGORY_BROWSABLE);
            List<android.content.pm.ResolveInfo> handlers = pm.queryIntentActivities(probe, 0);
            if (handlers != null) {
                for (android.content.pm.ResolveInfo ri : handlers) {
                    if (ri.activityInfo == null || ri.activityInfo.packageName == null) continue;
                    String pkg = ri.activityInfo.packageName.toLowerCase(Locale.ROOT);
                    if (pkg.contains("shamcash") || pkg.contains("shamlogix")) {
                        Intent appIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        appIntent.setPackage(ri.activityInfo.packageName);
                        appIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        context.startActivity(appIntent);
                        return true;
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    private void showWebMode(String url) {
        if (isShamCashExternalUrl(url) && tryLaunchNativeShamCashAppOnly(this, url)) {
            isWaitingForExternalPayment = true;
            return;
        }
        isNativeMode = false;
        nativeStoreContainer.setVisibility(View.GONE);
        nativeOrdersContainer.setVisibility(View.GONE);
        nativeAccountContainer.setVisibility(View.GONE);
        nativeErrorView.setVisibility(View.GONE);
        swipeRefresh.setVisibility(View.VISIBLE);
        if (connectivityHelper != null && connectivityHelper.isOnline() && webView != null) {
            webView.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        }
        webView.loadUrl(url);
        updateBottomNavigationActiveTabFromUrl(url);
    }

    private void launchNativeStudio() {
        Intent studioIntent = new Intent(this, NativeCameraStudioActivity.class);
        startActivityForResult(studioIntent, NATIVE_STUDIO_REQUEST_CODE);
    }

    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(false);
        settings.setTextZoom(100);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);

        String rawUa = settings.getUserAgentString();
        String cleanedUa = rawUa != null
                ? rawUa.replace("; wv", "").replaceAll("Version/\\d+(?:\\.\\d+)?\\s*", "").replaceAll("\\s+", " ").trim()
                : "";
        if (!cleanedUa.contains("Chrome/")) {
            cleanedUa = "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36";
        }
        cleanChromeUserAgent = cleanedUa;
        appWebViewUserAgent = cleanedUa + " RaqamiyatAndroid/3.2.3 NativeApp";
        settings.setUserAgentString(appWebViewUserAgent);

        webView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            if (url != null && (url.contains("/download/app") || url.contains("/download/apk") || url.endsWith(".apk"))) {
                downloadAndInstallApkInApp(url);
            } else if (url != null) {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                } catch (Exception ignored) {}
            }
        });

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        if (connectivityHelper.isOnline()) {
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        } else {
            settings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
        }

        webView.setOnLongClickListener(v -> true);
        webView.setHapticFeedbackEnabled(true);
        webView.addJavascriptInterface(nativeBridge, "RaqamiyatNative");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrlNavigation(request.getUrl().toString());
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrlNavigation(url);
            }

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
                CookieManager.getInstance().flush();

                if (!isInitialPageLoaded) {
                    isInitialPageLoaded = true;
                    dismissSplashOverlay();
                }

                syncLiveWalletAndSession();
                if (webView != null) {
                    webView.evaluateJavascript(
                            "(function(){document.querySelectorAll('.rq-bottom-nav,.rq-mobile-bottom-nav,#rq-web-bottom-nav').forEach(function(e){e.style.display='none';});})();",
                            null
                    );
                }

                super.onPageFinished(view, url);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame() && !isNativeMode) {
                    String reqUrl = request.getUrl() != null ? request.getUrl().toString() : "";
                    int errCode = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && error != null)
                            ? error.getErrorCode()
                            : WebViewClient.ERROR_UNKNOWN;
                    boolean isHttp = reqUrl.startsWith("http://") || reqUrl.startsWith("https://");
                    boolean isNetworkError = !connectivityHelper.isOnline()
                            || errCode == WebViewClient.ERROR_HOST_LOOKUP
                            || errCode == WebViewClient.ERROR_CONNECT
                            || errCode == WebViewClient.ERROR_TIMEOUT
                            || errCode == WebViewClient.ERROR_IO;

                    if (isHttp && isNetworkError) {
                        progressBar.setVisibility(View.GONE);
                        swipeRefresh.setRefreshing(false);
                        if (!connectivityHelper.isOnline()) {
                            showConnectivityBanner(false);
                        }
                        nativeErrorView.setVisibility(View.VISIBLE);
                        dismissSplashOverlay();
                    }
                }
                super.onReceivedError(view, request, error);
            }

            @Nullable
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
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

            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> request.grant(request.getResources()));
            }

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
                                getPackageName() + ".fileprovider", photoFile);
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
            switchToNativeTab(TAB_HOME);
        });
    }

    private void setupBottomNavigation() {
        View navHome = findViewById(R.id.nav_item_home);
        View navCatalog = findViewById(R.id.nav_item_catalog);
        View navWallet = findViewById(R.id.nav_item_wallet);
        View navOrders = findViewById(R.id.nav_item_orders);
        View navAccount = findViewById(R.id.nav_item_account);

        if (navHome != null) {
            navHome.setOnClickListener(v -> switchToNativeTab(TAB_HOME));
        }
        if (navCatalog != null) {
            navCatalog.setOnClickListener(v -> switchToNativeTab(TAB_CATALOG));
        }
        if (navWallet != null) {
            navWallet.setOnClickListener(v -> startActivity(new Intent(MainActivity.this, NativePaymentActivity.class)));
        }
        if (navOrders != null) {
            navOrders.setOnClickListener(v -> switchToNativeTab(TAB_ORDERS));
        }
        if (navAccount != null) {
            navAccount.setOnClickListener(v -> switchToNativeTab(TAB_ACCOUNT));
        }
    }

    private void setActiveBottomTabHighlight(int tab) {
        TextView textHome = findViewById(R.id.nav_text_home);
        TextView textCatalog = findViewById(R.id.nav_text_catalog);
        TextView textWallet = findViewById(R.id.nav_text_wallet);
        TextView textOrders = findViewById(R.id.nav_text_orders);
        TextView textAccount = findViewById(R.id.nav_text_account);

        int colorInactive = 0xFF94A3B8;
        int colorActiveGold = 0xFFD4A853;
        int colorActiveCyan = 0xFF22D3EE;

        if (textHome != null) textHome.setTextColor(tab == TAB_HOME ? colorActiveGold : colorInactive);
        if (textCatalog != null) textCatalog.setTextColor(tab == TAB_CATALOG ? colorActiveGold : colorInactive);
        if (textWallet != null) textWallet.setTextColor(tab == TAB_WALLET ? colorActiveCyan : colorInactive);
        if (textOrders != null) textOrders.setTextColor(tab == TAB_ORDERS ? colorActiveGold : colorInactive);
        if (textAccount != null) textAccount.setTextColor(tab == TAB_ACCOUNT ? colorActiveGold : colorInactive);
    }

    private void updateBottomNavigationActiveTabFromUrl(String url) {
        if (url == null) return;
        if (url.contains("/dashboard/wallet/")) {
            setActiveBottomTabHighlight(TAB_WALLET);
        } else if (url.contains("/catalog/")) {
            setActiveBottomTabHighlight(TAB_CATALOG);
        } else if (url.contains("/dashboard/orders/")) {
            setActiveBottomTabHighlight(TAB_ORDERS);
        } else if (url.contains("/dashboard/") || url.contains("/accounts/") || url.contains("/control/")) {
            setActiveBottomTabHighlight(TAB_ACCOUNT);
        } else {
            setActiveBottomTabHighlight(TAB_HOME);
        }
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
                syncLiveWalletAndSession();
            } else {
                webView.getSettings().setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
            }
        });
    }

    private void showConnectivityBanner(boolean isOnline) {
        if (!isOnline) {
            connectivityBanner.setBackgroundColor(Color.parseColor("#b45309"));
            bannerText.setText("⚠️ أنت تتصفح بدون إنترنت • يتم عرض البيانات المخزنة محلياً");
            connectivityBanner.setVisibility(View.VISIBLE);
        } else {
            connectivityBanner.setBackgroundColor(Color.parseColor("#059669"));
            bannerText.setText("⚡ تم استعادة الاتصال بالإنترنت • البيانات محدثة");
            connectivityBanner.setVisibility(View.VISIBLE);
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
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.2.3 CacheSync");
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
        if (requestCode == PRODUCT_DETAIL_REQUEST_CODE) {
            updateHeaderBadges();
            syncLiveWalletAndSession();
            if (resultCode == RESULT_OK && data != null) {
                if (data.getBooleanExtra(ProductDetailActivity.EXTRA_OPEN_NATIVE_ORDERS, false)) {
                    switchToNativeTab(TAB_ORDERS);
                    return;
                }
                String openUrl = data.getStringExtra(ProductDetailActivity.EXTRA_OPEN_URL);
                if (openUrl != null && !openUrl.isEmpty()) {
                    showWebMode(openUrl);
                }
            }
            return;
        }
        if (requestCode == NATIVE_STUDIO_REQUEST_CODE) {
            if (resultCode == RESULT_OK) {
                loadNativeCatalog(true);
            }
            return;
        }
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (mFilePathCallback == null) {
                super.onActivityResult(requestCode, resultCode, data);
                return;
            }
            Uri[] results = null;
            if (resultCode == RESULT_OK) {
                if (data != null && data.getClipData() != null) {
                    ClipData clipData = data.getClipData();
                    int count = clipData.getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = clipData.getItemAt(i).getUri();
                    }
                } else if (data != null && data.getData() != null) {
                    results = new Uri[]{data.getData()};
                } else if (mCameraPhotoPath != null) {
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
            switchToNativeTab(TAB_HOME);
            return;
        }
        if (!isNativeMode && webView.canGoBack()) {
            webView.goBack();
        } else if (!isNativeMode || activeNativeTab != TAB_HOME) {
            switchToNativeTab(TAB_HOME);
        } else {
            if (backPressedTime + 2000 > System.currentTimeMillis()) {
                super.onBackPressed();
            } else {
                Toast.makeText(this, "اضغط مرة أخرى للخروج من التطبيق", Toast.LENGTH_SHORT).show();
                backPressedTime = System.currentTimeMillis();
            }
        }
    }

    private boolean hasPromptedAppUpdate = false;

    private boolean isPackageInstalled(String packageName) {
        try {
            getPackageManager().getPackageInfo(packageName, 0);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private void launchGoogleCustomTab(String url) {
        NativeAuthHelper.launchGoogleAuthTab(this, url);
    }

    private void downloadAndInstallApkInApp(final String apkUrl) {
        Toast.makeText(this, "⏳ جاري تحميل وتثبيت التحديث التلقائي داخل التطبيق...", Toast.LENGTH_LONG).show();
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(apkUrl).openConnection();
                conn.setInstanceFollowRedirects(true);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(30000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.2.3 AutoUpdater");
                conn.connect();
                if (conn.getResponseCode() == 200) {
                    File outFile = new File(getCacheDir(), "Raqamiyat-Update.apk");
                    java.io.InputStream is = conn.getInputStream();
                    java.io.FileOutputStream fos = new java.io.FileOutputStream(outFile);
                    byte[] buffer = new byte[32768];
                    int len;
                    while ((len = is.read(buffer)) != -1) {
                        fos.write(buffer, 0, len);
                    }
                    fos.flush();
                    fos.close();
                    is.close();
                    if (outFile.exists() && outFile.length() > 100000) {
                        mainHandler.post(() -> {
                            try {
                                Uri apkUri = FileProvider.getUriForFile(
                                        MainActivity.this,
                                        getPackageName() + ".fileprovider",
                                        outFile
                                );
                                Intent installIntent = new Intent(Intent.ACTION_VIEW);
                                installIntent.setDataAndType(apkUri, "application/vnd.android.package-archive");
                                installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                                startActivity(installIntent);
                            } catch (Exception e) {
                                launchGoogleCustomTab(apkUrl);
                            }
                        });
                        return;
                    }
                }
            } catch (Exception ignored) {
            }
            mainHandler.post(() -> launchGoogleCustomTab(apkUrl));
        });
    }

    private void checkForAppUpdatesInBackground() {
        if (hasPromptedAppUpdate || !connectivityHelper.isOnline()) return;
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(BASE_URL + "api/app/version/").openConnection();
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(6000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.2.3 UpdateCheck");
                conn.connect();
                if (conn.getResponseCode() == 200) {
                    Scanner scanner = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String json = scanner.useDelimiter("\\A").hasNext() ? scanner.next() : "";
                    scanner.close();
                    if (!json.isEmpty()) {
                        JSONObject obj = new JSONObject(json);
                        int serverCode = obj.optInt("version_code", 0);
                        String serverName = obj.optString("version_name", "");
                        String apkUrl = obj.optString("local_apk_url", obj.optString("apk_url", BASE_URL + "download/app/?direct=1"));
                        String notes = obj.optString("release_notes", "تتوفر نسخة محدثة من تطبيق رقميات.");
                        long localCode = 0;
                        try {
                            android.content.pm.PackageInfo pInfo = getPackageManager().getPackageInfo(getPackageName(), 0);
                            localCode = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P ? pInfo.getLongVersionCode() : pInfo.versionCode;
                        } catch (Exception ignored) {}
                        if (serverCode > localCode) {
                            hasPromptedAppUpdate = true;
                            mainHandler.post(() -> {
                                if (!isFinishing()) {
                                    new MaterialAlertDialogBuilder(MainActivity.this)
                                            .setTitle("⚡ يتوفر تحديث جديد لتطبيق رقميات (" + serverName + ")")
                                            .setMessage(notes + "\n\nاضغط تحديث ليتم تحميل وتثبيت النسخة الجديدة تلقائياً.")
                                            .setPositiveButton("تحديث تلقائي الآن", (d, w) -> downloadAndInstallApkInApp(apkUrl))
                                            .setNegativeButton("لاحقاً", (d, w) -> d.dismiss())
                                            .show();
                                }
                            });
                        }
                    }
                }
            } catch (Exception ignored) {
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        CookieManager.getInstance().flush();
        updateHeaderBadges();
        productAdapter.updateCurrencyConfig(localStore.getPreferredCurrency(), localStore.getSypRate());
        loadNativeCatalog(false);
        syncLiveWalletAndSession();
        syncAppNotifications();

        if (isWaitingForExternalPayment) {
            isWaitingForExternalPayment = false;
            if (!isNativeMode && webView != null && connectivityHelper != null && connectivityHelper.isOnline()) {
                mainHandler.postDelayed(() -> {
                    if (webView != null) {
                        String curr = webView.getUrl();
                        if (curr != null && (curr.contains("/dashboard/") || curr.contains("/payments/status/") || curr.contains("/cart/"))) {
                            webView.reload();
                        }
                    }
                }, 600);
            }
        }
        if (isWaitingForGoogleAuth) {
            isWaitingForGoogleAuth = false;
            Runnable checkSso = this::syncLiveWalletAndSession;
            mainHandler.postDelayed(checkSso, 200);
            mainHandler.postDelayed(checkSso, 900);
            mainHandler.postDelayed(checkSso, 2000);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (intent != null) {
            String openUrlExtra = intent.getStringExtra(ProductDetailActivity.EXTRA_OPEN_URL);
            if (openUrlExtra != null && !openUrlExtra.isEmpty()) {
                showWebMode(openUrlExtra);
                return;
            }
            if (intent.getData() != null) {
                handleIncomingDeepLink(intent.getData());
            }
        }
    }

    private void handleIncomingDeepLink(Uri uri) {
        if (uri == null) return;
        String deepUrl = uri.toString();
        if ("raqamiyat".equals(uri.getScheme()) && "open".equals(uri.getHost())) {
            String target = uri.getQueryParameter("url");
            if (target != null && !target.isEmpty() && target.startsWith("https://raqamiyatapp.com")) {
                isWaitingForExternalPayment = false;
                if (target.contains("/dashboard/orders")) {
                    switchToNativeTab(TAB_ORDERS);
                } else if (target.contains("/dashboard/wallet")) {
                    startActivity(new Intent(this, NativePaymentActivity.class));
                } else {
                    showWebMode(target);
                }
            }
            return;
        }
        if ("raqamiyat".equals(uri.getScheme()) && "auth".equals(uri.getHost())) {
            String token = uri.getQueryParameter("token");
            if (token != null && !token.isEmpty()) {
                isWaitingForGoogleAuth = false;
                String exchangeJsonUrl = BASE_URL + "auth/app-sso-exchange/?format=json&token=" + Uri.encode(token);
                catalogRepository.getJson(exchangeJsonUrl, (code, json, err) -> {
                    if (code == 200 && json != null && json.optBoolean("is_authenticated", false)) {
                        String appTok = json.optString("app_auth_token", "");
                        if (!appTok.isEmpty()) localStore.saveAppAuthToken(appTok);
                        Toast.makeText(this, "✓ تم تسجيل الدخول بنجاح في تطبيق رقميات!", Toast.LENGTH_SHORT).show();
                        syncLiveWalletAndSession();
                        switchToNativeTab(TAB_HOME);
                    } else {
                        showWebMode(BASE_URL + "auth/app-sso-exchange/?token=" + Uri.encode(token));
                    }
                });
            }
            return;
        }
        if (deepUrl.contains("/control/camera-studio")) {
            launchNativeStudio();
        } else if (deepUrl.contains("/payments/")) {
            showWebMode(deepUrl);
        } else if (deepUrl.contains("/dashboard/orders")) {
            switchToNativeTab(TAB_ORDERS);
        } else if (deepUrl.contains("/dashboard/wallet")) {
            startActivity(new Intent(this, NativePaymentActivity.class));
        } else if (deepUrl.contains("/auth/app-sso-exchange")
                || deepUrl.contains("/accounts/")
                || deepUrl.contains("/auth/")
                || deepUrl.contains("/control/")
                || deepUrl.contains("/catalog/")
                || deepUrl.contains("/cart/")) {
            showWebMode(deepUrl);
        } else if (deepUrl.contains("raqamiyatapp.com")) {
            switchToNativeTab(TAB_HOME);
        }
    }

    private boolean handleUrlNavigation(String url) {
        if (url == null) return false;

        if (url.startsWith("raqamiyat://")) {
            handleIncomingDeepLink(Uri.parse(url));
            return true;
        }

        if (isShamCashExternalUrl(url) && tryLaunchNativeShamCashAppOnly(this, url)) {
            isWaitingForExternalPayment = true;
            return true;
        }

        if (url.startsWith("intent:")) {
            try {
                Intent intent = Intent.parseUri(url, Intent.URI_INTENT_SCHEME);
                if (intent != null) {
                    startActivity(intent);
                }
                return true;
            } catch (Exception ignored) {
                return true;
            }
        }

        if (url.startsWith("whatsapp:") || url.startsWith("tel:") || url.startsWith("mailto:") || url.startsWith("tg:")) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                return true;
            } catch (Exception ignored) {
                return true;
            }
        }

        if (url.contains("accounts.google.com") || url.contains("/accounts/google/login")) {
            isWaitingForGoogleAuth = true;
            launchGoogleCustomTab(url);
            return true;
        }

        if (url.contains("/control/camera-studio")) {
            launchNativeStudio();
            return true;
        }

        if (url.startsWith("http://") || url.startsWith("https://")) {
            if (isNativeMode) {
                isNativeMode = false;
                nativeStoreContainer.setVisibility(View.GONE);
                nativeOrdersContainer.setVisibility(View.GONE);
                nativeAccountContainer.setVisibility(View.GONE);
                nativeErrorView.setVisibility(View.GONE);
                swipeRefresh.setVisibility(View.VISIBLE);
            }
            return false;
        }

        return false;
    }

    @Override
    public void onOpenNativeStudio() {
        launchNativeStudio();
    }

    @Override
    public void onOpenGoogleLogin() {
        openNativeLoginSheet();
    }

    @Override
    public void onTransactionSuccess(String orderId) {
        syncLiveWalletAndSession();
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
