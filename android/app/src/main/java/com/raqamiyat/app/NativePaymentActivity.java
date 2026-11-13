package com.raqamiyat.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.browser.customtabs.CustomTabsIntent;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class NativePaymentActivity extends AppCompatActivity {

    private static final String DOMAIN = "https://raqamiyatapp.com";
    private static final String WALLET_API = DOMAIN + "/api/app/wallet/";
    private static final String DEPOSIT_API = DOMAIN + "/api/app/payments/deposit/";

    private TextView walletBalanceText;
    private LinearLayout cardShamcash;
    private LinearLayout cardPaymera;
    private TextView txtShamTitle, txtShamSub, txtPayTitle, txtPaySub;
    private TextView optUsd, optSyp;
    private EditText amountInput;
    private TextView statusText;
    private ProgressBar progressBar;
    private Button btnSubmit, btnVerify;

    private String selectedProvider = "shamcash";
    private String selectedCurrency = "USD";
    private String activeDepositId = "";
    private boolean waitingForGatewayReturn = false;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }
        setContentView(R.layout.activity_native_payment);

        bindViews();
        setupActions();
        loadWalletInfo();
    }

    private void bindViews() {
        walletBalanceText = findViewById(R.id.pay_wallet_balance);
        cardShamcash = findViewById(R.id.card_provider_shamcash);
        cardPaymera = findViewById(R.id.card_provider_paymera);
        txtShamTitle = findViewById(R.id.txt_shamcash_title);
        txtShamSub = findViewById(R.id.txt_shamcash_sub);
        txtPayTitle = findViewById(R.id.txt_paymera_title);
        txtPaySub = findViewById(R.id.txt_paymera_sub);
        optUsd = findViewById(R.id.opt_curr_usd);
        optSyp = findViewById(R.id.opt_curr_syp);
        amountInput = findViewById(R.id.pay_amount_input);
        statusText = findViewById(R.id.pay_status_text);
        progressBar = findViewById(R.id.pay_progress);
        btnSubmit = findViewById(R.id.btn_pay_submit);
        btnVerify = findViewById(R.id.btn_pay_verify);
    }

    private void setupActions() {
        ImageButton btnBack = findViewById(R.id.btn_pay_back);
        btnBack.setOnClickListener(v -> finish());

        cardShamcash.setOnClickListener(v -> selectProvider("shamcash"));
        cardPaymera.setOnClickListener(v -> selectProvider("paymera"));

        optUsd.setOnClickListener(v -> selectCurrency("USD"));
        optSyp.setOnClickListener(v -> selectCurrency("SYP"));

        findViewById(R.id.btn_amt_5).setOnClickListener(v -> amountInput.setText("5"));
        findViewById(R.id.btn_amt_10).setOnClickListener(v -> amountInput.setText("10"));
        findViewById(R.id.btn_amt_25).setOnClickListener(v -> amountInput.setText("25"));
        findViewById(R.id.btn_amt_50).setOnClickListener(v -> amountInput.setText("50"));

        btnSubmit.setOnClickListener(v -> submitPayment());
        btnVerify.setOnClickListener(v -> verifyDepositStatus());
    }

    private void selectProvider(String provider) {
        selectedProvider = provider;
        boolean isSham = "shamcash".equals(provider);
        cardShamcash.setBackgroundResource(isSham ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        txtShamTitle.setTextColor(isSham ? 0xFF030712 : 0xFFF8FAFC);
        txtShamSub.setTextColor(isSham ? 0xFF0F172A : 0xFF94A3B8);

        cardPaymera.setBackgroundResource(!isSham ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        txtPayTitle.setTextColor(!isSham ? 0xFF030712 : 0xFFF8FAFC);
        txtPaySub.setTextColor(!isSham ? 0xFF0F172A : 0xFF94A3B8);
    }

    private void selectCurrency(String curr) {
        selectedCurrency = curr;
        boolean isUsd = "USD".equals(curr);
        optUsd.setBackgroundResource(isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        optUsd.setTextColor(isUsd ? 0xFF030712 : 0xFFE2E8F0);
        optSyp.setBackgroundResource(!isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        optSyp.setTextColor(!isUsd ? 0xFF030712 : 0xFFE2E8F0);
    }

    private void loadWalletInfo() {
        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(WALLET_API).openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null) conn.setRequestProperty("Cookie", cookies);
                conn.connect();
                if (conn.getResponseCode() == 200) {
                    Scanner sc = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                    JSONObject obj = new JSONObject(body);
                    if (obj.optBoolean("is_authenticated", false)) {
                        double bal = obj.optDouble("balance", 0.0);
                        String cur = obj.optString("currency", "USD");
                        mainHandler.post(() -> walletBalanceText.setText(String.format(Locale.US, "%.2f %s", bal, cur)));
                    } else {
                        mainHandler.post(() -> {
                            walletBalanceText.setText("يرجى تسجيل الدخول");
                            statusText.setText("سجل دخولك من تبويب (حسابي) لإتمام الدفع عبر بيميرا وشام كاش.");
                            statusText.setVisibility(View.VISIBLE);
                        });
                    }
                }
            } catch (Exception ignored) {
            }
        });
    }

    private void submitPayment() {
        String amt = amountInput.getText() != null ? amountInput.getText().toString().trim() : "";
        if (amt.isEmpty()) {
            Toast.makeText(this, "يرجى إدخال المبلغ", Toast.LENGTH_SHORT).show();
            return;
        }
        progressBar.setVisibility(View.VISIBLE);
        statusText.setVisibility(View.GONE);
        btnSubmit.setEnabled(false);

        executor.execute(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(DEPOSIT_API).openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(15000);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                    String csrf = extractCookie(cookies, "csrftoken");
                    if (!csrf.isEmpty()) conn.setRequestProperty("X-CSRFToken", csrf);
                }

                JSONObject payload = new JSONObject();
                payload.put("provider", selectedProvider);
                payload.put("amount", amt);
                payload.put("currency_code", selectedCurrency);

                OutputStream os = conn.getOutputStream();
                os.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                os.flush();
                os.close();

                int code = conn.getResponseCode();
                InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                String resp = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                sc.close();

                JSONObject json = new JSONObject(resp);
                if (code == 200 && "success".equals(json.optString("status"))) {
                    String paymentUrl = json.optString("payment_url", "");
                    activeDepositId = json.optString("deposit_id", "");
                    mainHandler.post(() -> {
                        progressBar.setVisibility(View.GONE);
                        btnSubmit.setEnabled(true);
                        btnVerify.setVisibility(View.VISIBLE);
                        if (!paymentUrl.isEmpty()) {
                            waitingForGatewayReturn = true;
                            statusText.setText("تم فتح بوابة الدفع... عند الانتهاء سيتم التحقق تلقائياً.");
                            statusText.setVisibility(View.VISIBLE);
                            openPaymentUrl(paymentUrl);
                        } else {
                            statusText.setText("تم إنشاء الطلب رقم: " + json.optString("bill_no"));
                            statusText.setVisibility(View.VISIBLE);
                        }
                    });
                    return;
                }

                String err = json.optString("message", "تعذر بدء عملية الدفع");
                mainHandler.post(() -> {
                    progressBar.setVisibility(View.GONE);
                    btnSubmit.setEnabled(true);
                    statusText.setText(err);
                    statusText.setVisibility(View.VISIBLE);
                });
            } catch (Exception e) {
                mainHandler.post(() -> {
                    progressBar.setVisibility(View.GONE);
                    btnSubmit.setEnabled(true);
                    statusText.setText("خطأ في الاتصال بالخادم");
                    statusText.setVisibility(View.VISIBLE);
                });
            }
        });
    }

    private void verifyDepositStatus() {
        if (activeDepositId.isEmpty()) return;
        progressBar.setVisibility(View.VISIBLE);
        executor.execute(() -> {
            try {
                String url = DOMAIN + "/api/app/payments/deposit/" + activeDepositId + "/status/";
                HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null) conn.setRequestProperty("Cookie", cookies);
                conn.connect();
                if (conn.getResponseCode() == 200) {
                    Scanner sc = new Scanner(conn.getInputStream(), StandardCharsets.UTF_8.name());
                    String body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                    sc.close();
                    JSONObject obj = new JSONObject(body);
                    boolean done = obj.optBoolean("is_completed", false);
                    double bal = obj.optDouble("wallet_balance", 0.0);
                    String cur = obj.optString("currency", "USD");
                    mainHandler.post(() -> {
                        progressBar.setVisibility(View.GONE);
                        walletBalanceText.setText(String.format(Locale.US, "%.2f %s", bal, cur));
                        if (done) {
                            statusText.setText("✓ تم تأكيد الدفع وإضافة الرصيد إلى محفظتك بنجاح!");
                            statusText.setVisibility(View.VISIBLE);
                            Toast.makeText(NativePaymentActivity.this, "تم شحن المحفظة بنجاح!", Toast.LENGTH_LONG).show();
                        } else {
                            statusText.setText("الحالة الحالية: قيد الانتظار — أتمم الدفع في البوابة ثم اضغط تحقق.");
                            statusText.setVisibility(View.VISIBLE);
                        }
                    });
                }
            } catch (Exception e) {
                mainHandler.post(() -> progressBar.setVisibility(View.GONE));
            }
        });
    }

    private void openPaymentUrl(String url) {
        try {
            CustomTabsIntent customTabsIntent = new CustomTabsIntent.Builder()
                    .setToolbarColor(0xFF030712)
                    .build();
            customTabsIntent.launchUrl(this, Uri.parse(url));
        } catch (Exception e) {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (waitingForGatewayReturn && !activeDepositId.isEmpty()) {
            waitingForGatewayReturn = false;
            mainHandler.postDelayed(this::verifyDepositStatus, 1000);
        }
    }

    private String extractCookie(String cookieHeader, String key) {
        for (String part : cookieHeader.split(";")) {
            String t = part.trim();
            if (t.startsWith(key + "=")) return t.substring(key.length() + 1);
        }
        return "";
    }
}
