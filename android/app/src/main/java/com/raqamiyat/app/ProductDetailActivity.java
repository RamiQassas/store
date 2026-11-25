package com.raqamiyat.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.adapter.VariantAdapter;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ProductDetailActivity extends AppCompatActivity {

    public static final String EXTRA_PRODUCT = "extra_product";
    public static final String EXTRA_OPEN_URL = "extra_open_url";
    private static final String ORDER_API_URL = CatalogRepository.DOMAIN + "/api/app/orders/create/";

    private ProductItem product;
    private VariantItem selectedVariant;
    private ConnectivityHelper connectivityHelper;
    private RaqamiyatLocalStore localStore;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }
        setContentView(R.layout.activity_product_detail);

        connectivityHelper = new ConnectivityHelper(this);
        connectivityHelper.startMonitoring();
        localStore = new RaqamiyatLocalStore(this);
        product = (ProductItem) getIntent().getSerializableExtra(EXTRA_PRODUCT);
        if (product == null) {
            finish();
            return;
        }

        ImageButton btnBack = findViewById(R.id.btn_detail_back);
        btnBack.setOnClickListener(v -> finish());

        ImageView img = findViewById(R.id.detail_image);
        TextView codeBadge = findViewById(R.id.detail_code_badge);
        TextView category = findViewById(R.id.detail_category);
        TextView delivery = findViewById(R.id.detail_delivery);
        TextView name = findViewById(R.id.detail_name);
        TextView price = findViewById(R.id.detail_price);
        TextView description = findViewById(R.id.detail_description);
        TextView variantsLabel = findViewById(R.id.detail_variants_label);
        RecyclerView variantsRv = findViewById(R.id.detail_variants_rv);
        Button btnBuy = findViewById(R.id.btn_detail_buy);

        if (product.imageUrl != null && !product.imageUrl.isEmpty()) {
            Glide.with(this)
                    .load(product.imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .into(img);
        } else {
            img.setImageResource(R.mipmap.ic_launcher);
        }

        codeBadge.setText(product.code != null && !product.code.isEmpty() ? "كود: " + product.code : "رقميات");
        category.setText(product.categoryName != null && !product.categoryName.isEmpty() ? product.categoryName : "المنتجات");
        if (product.deliveryTimeDisplay != null && !product.deliveryTimeDisplay.isEmpty()) {
            delivery.setText("⚡ التسليم: " + product.deliveryTimeDisplay);
            delivery.setVisibility(View.VISIBLE);
        } else {
            delivery.setVisibility(View.GONE);
        }

        name.setText(product.name);
        price.setText(product.price > 0 ? String.format(Locale.US, "$%.2f", product.price) : "حسب الباقة");
        description.setText(product.description != null && !product.description.trim().isEmpty()
                ? product.description.trim()
                : "منتج متوفر في متجر رقميات بأعلى جودة وضمان.");

        if (product.variants != null && !product.variants.isEmpty()) {
            selectedVariant = product.variants.get(0);
            price.setText(String.format(Locale.US, "$%.2f", selectedVariant.price));
            if (selectedVariant.sku != null && !selectedVariant.sku.isEmpty()) {
                codeBadge.setText("كود: " + selectedVariant.sku);
            }

            variantsRv.setLayoutManager(new LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false));
            VariantAdapter adapter = new VariantAdapter(variant -> {
                selectedVariant = variant;
                price.setText(String.format(Locale.US, "$%.2f", variant.price));
                if (variant.sku != null && !variant.sku.isEmpty()) {
                    codeBadge.setText("كود: " + variant.sku);
                }
            });
            adapter.submitList(product.variants);
            variantsRv.setAdapter(adapter);
        } else {
            variantsLabel.setVisibility(View.GONE);
            variantsRv.setVisibility(View.GONE);
        }

        if (product.isOutOfStock) {
            btnBuy.setText("غير متوفر حالياً");
            btnBuy.setEnabled(false);
            btnBuy.setAlpha(0.55f);
        } else {
            btnBuy.setOnClickListener(v -> {
                if (!connectivityHelper.isOnline()) {
                    new MaterialAlertDialogBuilder(this)
                            .setTitle("⚠️ لا يوجد اتصال بالإنترنت")
                            .setMessage("إتمام الطلب والشراء يتطلب اتصالاً فعالاً بالإنترنت لحماية حسابك وتأكيد العملية.")
                            .setPositiveButton("حسناً", (d, w) -> d.dismiss())
                            .show();
                    return;
                }
                openNativePurchaseDialog();
            });
        }
    }

    private void openNativePurchaseDialog() {
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (18 * getResources().getDisplayMetrics().density);
        container.setPadding(pad, pad / 2, pad, pad / 2);

        TextView summary = new TextView(this);
        String varName = selectedVariant != null ? selectedVariant.name : product.name;
        double unitPrice = selectedVariant != null ? selectedVariant.price : product.price;
        summary.setText(String.format(Locale.US, "%s — $%.2f", varName, unitPrice));
        summary.setTextSize(15f);
        summary.setPadding(0, 0, 0, pad / 2);
        container.addView(summary);

        TextView qtyLabel = new TextView(this);
        qtyLabel.setText("الكمية:");
        container.addView(qtyLabel);

        EditText qtyInput = new EditText(this);
        qtyInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        qtyInput.setText("1");
        container.addView(qtyInput);

        TextView noteLabel = new TextView(this);
        noteLabel.setText("معرف اللاعب / رقم الهاتف / ملاحظة (اختياري):");
        noteLabel.setPadding(0, pad / 3, 0, 0);
        container.addView(noteLabel);

        EditText noteInput = new EditText(this);
        noteInput.setHint("أدخل المعرف أو رقم التواصل إن وجد");
        container.addView(noteInput);

        TextView payLabel = new TextView(this);
        payLabel.setText("اختر وسيلة الدفع:");
        payLabel.setPadding(0, pad / 2, 0, 4);
        container.addView(payLabel);

        RadioGroup methodGroup = new RadioGroup(this);
        RadioButton rbWallet = new RadioButton(this);
        rbWallet.setId(View.generateViewId());
        rbWallet.setText("محفظة رقميات (شراء فوري ⚡)");
        methodGroup.addView(rbWallet);

        RadioButton rbShamUsd = new RadioButton(this);
        rbShamUsd.setId(View.generateViewId());
        rbShamUsd.setText("شام كاش — ShamCash (USD)");
        methodGroup.addView(rbShamUsd);

        RadioButton rbShamSyp = new RadioButton(this);
        rbShamSyp.setId(View.generateViewId());
        rbShamSyp.setText("شام كاش — ShamCash (SYP)");
        methodGroup.addView(rbShamSyp);

        RadioButton rbPaymera = new RadioButton(this);
        rbPaymera.setId(View.generateViewId());
        rbPaymera.setText("بيميرا — Paymera");
        methodGroup.addView(rbPaymera);

        methodGroup.check(rbWallet.getId());
        container.addView(methodGroup);

        new MaterialAlertDialogBuilder(this)
                .setTitle("إتمام شراء المنتج ⚡")
                .setView(container)
                .setPositiveButton("تأكيد وإتمام الشراء", (dialog, which) -> {
                    int checkedId = methodGroup.getCheckedRadioButtonId();
                    String method = "wallet";
                    String currency = "USD";
                    if (checkedId == rbShamUsd.getId()) {
                        method = "sham_cash";
                        currency = "USD";
                    } else if (checkedId == rbShamSyp.getId()) {
                        method = "sham_cash";
                        currency = "SYP";
                    } else if (checkedId == rbPaymera.getId()) {
                        method = "paymera";
                        currency = "SYP";
                    }

                    int qty = 1;
                    try {
                        qty = Math.max(1, Integer.parseInt(qtyInput.getText().toString().trim()));
                    } catch (Exception ignored) {
                    }
                    String customVal = noteInput.getText() != null ? noteInput.getText().toString().trim() : "";
                    submitNativeOrder(method, currency, qty, customVal);
                })
                .setNeutralButton("صفحة المنتج المتقدمة", (d, w) -> openUrlInMainApp(CatalogRepository.DOMAIN + "/catalog/" + product.id + "/"))
                .setNegativeButton("إلغاء", (d, w) -> d.dismiss())
                .show();
    }

    private void submitNativeOrder(String paymentMethod, String currencyCode, int quantity, String customInput) {
        AlertDialog loading = new MaterialAlertDialogBuilder(this)
                .setTitle("جاري تنفيذ الطلب...")
                .setMessage("يرجى الانتظار لحظات لتأكيد الطلب بأمان مع الخادم.")
                .setCancelable(false)
                .create();
        loading.show();

        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(ORDER_API_URL).openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(25000);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 NativeApp");

                String cookies = CookieManager.getInstance().getCookie(CatalogRepository.DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                    String csrf = extractCookie(cookies, "csrftoken");
                    if (!csrf.isEmpty()) conn.setRequestProperty("X-CSRFToken", csrf);
                }
                String appToken = localStore.getAppAuthToken();
                if (appToken != null && !appToken.isEmpty()) {
                    conn.setRequestProperty("X-App-Auth-Token", appToken);
                }

                JSONObject payload = new JSONObject();
                payload.put("product_id", product.id);
                if (selectedVariant != null) {
                    payload.put("variant_id", selectedVariant.id);
                }
                payload.put("quantity", quantity);
                payload.put("payment_method", paymentMethod);
                payload.put("currency_code", currencyCode);
                payload.put("custom_input", customInput);

                OutputStream os = conn.getOutputStream();
                os.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                os.flush();
                os.close();

                int code = conn.getResponseCode();
                InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                String resp = "";
                if (is != null) {
                    Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                    resp = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                }

                if (code == 404) {
                    submitFallbackFormOrder(loading, paymentMethod, currencyCode, quantity, customInput);
                    return;
                }

                String trimmed = resp.trim();
                if (!trimmed.startsWith("{")) {
                    final int statusCode = code;
                    mainHandler.post(() -> {
                        loading.dismiss();
                        if (statusCode == 401 || statusCode == 403) {
                            promptLoginRequired("يرجى تسجيل الدخول بحسابك أولاً لإتمام الشراء.");
                        } else {
                            showOrderErrorDialog("تعذر معالجة استجابة الخادم (" + statusCode + ")، يمكنك إتمام الطلب عبر صفحة المنتج داخل التطبيق.");
                        }
                    });
                    return;
                }

                JSONObject json = new JSONObject(trimmed);
                if (code == 200 && "success".equals(json.optString("status"))) {
                    String paymentUrl = json.optString("payment_url", "");
                    String orderId = json.optString("order_id", "");
                    String orderNumber = json.optString("order_number", orderId);
                    mainHandler.post(() -> {
                        loading.dismiss();
                        if (!paymentUrl.isEmpty()) {
                            if (MainActivity.isShamCashExternalUrl(paymentUrl) || "shamcash".equalsIgnoreCase(paymentMethod)) {
                                String statusPage = !orderId.isEmpty()
                                        ? (CatalogRepository.DOMAIN + "/payments/status/?type=order&id=" + Uri.encode(orderId))
                                        : (CatalogRepository.DOMAIN + "/dashboard/orders/");
                                openUrlInMainApp(statusPage);
                                MainActivity.launchExternalShamCashUrl(ProductDetailActivity.this, paymentUrl);
                            } else {
                                openUrlInMainApp(paymentUrl);
                            }
                        } else {
                            new MaterialAlertDialogBuilder(ProductDetailActivity.this)
                                    .setTitle("✓ تم تأكيد طلبك بنجاح ⚡")
                                    .setMessage("تم استلام طلبك بنجاح" + (!orderNumber.isEmpty() ? "\nرقم الطلب: #" + orderNumber : ""))
                                    .setPositiveButton("عرض طلباتي", (d, w) -> openUrlInMainApp(CatalogRepository.DOMAIN + "/dashboard/orders/"))
                                    .setNegativeButton("تم", (d, w) -> d.dismiss())
                                    .show();
                        }
                    });
                    return;
                }

                boolean requiresAuth = (code == 401) || json.optBoolean("requires_auth", false);
                String errMsg = json.optString("message", json.optString("error", "تعذر إتمام الطلب"));
                mainHandler.post(() -> {
                    loading.dismiss();
                    if (requiresAuth) {
                        promptLoginRequired(errMsg);
                    } else {
                        showOrderErrorDialog(errMsg);
                    }
                });
            } catch (Exception e) {
                mainHandler.post(() -> {
                    loading.dismiss();
                    showOrderErrorDialog("تعذر الاتصال بالخادم حالياً: " + e.getMessage());
                });
            }
        });
    }

    private void submitFallbackFormOrder(AlertDialog loading, String paymentMethod, String currencyCode, int quantity, String customInput) {
        try {
            String urlStr = CatalogRepository.DOMAIN + "/catalog/" + product.id + "/";
            HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(12000);
            conn.setReadTimeout(15000);
            conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8");
            conn.setRequestProperty("X-Requested-With", "XMLHttpRequest");

            String cookies = CookieManager.getInstance().getCookie(CatalogRepository.DOMAIN);
            if (cookies != null && !cookies.isEmpty()) {
                conn.setRequestProperty("Cookie", cookies);
                String csrf = extractCookie(cookies, "csrftoken");
                if (!csrf.isEmpty()) conn.setRequestProperty("X-CSRFToken", csrf);
            }

            StringBuilder form = new StringBuilder();
            form.append("ajax=1");
            form.append("&quantity=").append(quantity);
            form.append("&payment_method=").append(URLEncoder.encode(paymentMethod, "UTF-8"));
            form.append("&gateway_currency=").append(URLEncoder.encode(currencyCode, "UTF-8"));
            if (selectedVariant != null) {
                form.append("&variant_id=").append(URLEncoder.encode(selectedVariant.id, "UTF-8"));
            }
            if (!customInput.isEmpty()) {
                form.append("&custom_note=").append(URLEncoder.encode(customInput, "UTF-8"));
            }

            OutputStream os = conn.getOutputStream();
            os.write(form.toString().getBytes(StandardCharsets.UTF_8));
            os.flush();
            os.close();

            int code = conn.getResponseCode();
            InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String resp = "";
            if (is != null) {
                Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                resp = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                sc.close();
            }

            if (resp.trim().startsWith("{")) {
                JSONObject json = new JSONObject(resp);
                if (json.optBoolean("success", false)) {
                    String redirectUrl = json.optString("redirect_url", "");
                    String orderNumber = json.optString("order_number", "");
                    mainHandler.post(() -> {
                        loading.dismiss();
                        if (!redirectUrl.isEmpty()) {
                            if (MainActivity.isShamCashExternalUrl(redirectUrl)) {
                                openUrlInMainApp(CatalogRepository.DOMAIN + "/dashboard/orders/");
                                MainActivity.launchExternalShamCashUrl(ProductDetailActivity.this, redirectUrl);
                            } else {
                                openUrlInMainApp(redirectUrl);
                            }
                        } else {
                            new MaterialAlertDialogBuilder(ProductDetailActivity.this)
                                    .setTitle("✓ تم تأكيد طلبك بنجاح ⚡")
                                    .setMessage("رقم الطلب: #" + orderNumber)
                                    .setPositiveButton("عرض طلباتي", (d, w) -> openUrlInMainApp(CatalogRepository.DOMAIN + "/dashboard/orders/"))
                                    .setNegativeButton("تم", (d, w) -> d.dismiss())
                                    .show();
                        }
                    });
                    return;
                }
                String err = json.optString("error", "تعذر إتمام الطلب");
                mainHandler.post(() -> {
                    loading.dismiss();
                    showOrderErrorDialog(err);
                });
                return;
            }
            mainHandler.post(() -> {
                loading.dismiss();
                openUrlInMainApp(urlStr);
            });
        } catch (Exception e) {
            mainHandler.post(() -> {
                loading.dismiss();
                openUrlInMainApp(CatalogRepository.DOMAIN + "/catalog/" + product.id + "/");
            });
        }
    }

    private void promptLoginRequired(String message) {
        String nextCatalog = "/catalog/" + product.id + "/";
        new MaterialAlertDialogBuilder(this)
                .setTitle("تسجيل الدخول مطلوب")
                .setMessage(message)
                .setPositiveButton("تسجيل الدخول عبر Google ⚡", (d, w) -> {
                    String url = CatalogRepository.DOMAIN + "/accounts/google/login/?process=login&next=" + Uri.encode(nextCatalog);
                    openUrlInMainApp(url);
                })
                .setNeutralButton("دخول بالبريد / الهاتف", (d, w) -> {
                    String url = CatalogRepository.DOMAIN + "/auth/login/?next=" + Uri.encode(nextCatalog);
                    openUrlInMainApp(url);
                })
                .setNegativeButton("إلغاء", (d, w) -> d.dismiss())
                .show();
    }

    private void showOrderErrorDialog(String message) {
        new MaterialAlertDialogBuilder(this)
                .setTitle("تنبيه حول الطلب")
                .setMessage(message)
                .setPositiveButton("فتح صفحة المنتج", (d, w) -> openUrlInMainApp(CatalogRepository.DOMAIN + "/catalog/" + product.id + "/"))
                .setNegativeButton("حسناً", (d, w) -> d.dismiss())
                .show();
    }

    private void openUrlInMainApp(String url) {
        Intent result = new Intent();
        result.putExtra(EXTRA_OPEN_URL, url);
        setResult(RESULT_OK, result);
        finish();
    }

    private String extractCookie(String cookieHeader, String key) {
        for (String part : cookieHeader.split(";")) {
            String t = part.trim();
            if (t.startsWith(key + "=")) return t.substring(key.length() + 1);
        }
        return "";
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (connectivityHelper != null) {
            connectivityHelper.stopMonitoring();
        }
    }
}
