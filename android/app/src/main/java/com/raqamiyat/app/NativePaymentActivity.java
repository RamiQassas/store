package com.raqamiyat.app;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.model.GatewayItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class NativePaymentActivity extends AppCompatActivity {

    private static final String DOMAIN = CatalogRepository.DOMAIN;
    private static final String DEPOSIT_API = DOMAIN + "/api/app/payments/deposit/";
    private static final String REDEEM_CARD_API = DOMAIN + "/api/app/wallet/redeem-card/";

    private TextView rateBadge;
    private LinearLayout loginBanner;
    private TextView userGreeting;
    private TextView walletBalanceText;
    private TextView walletSecondaryText;
    private TextView walletBreakdownText;
    private TextView optUsd, optSyp;
    private TextView gatewaysCountText;
    private LinearLayout gatewaysContainer;
    private LinearLayout manualBox;
    private TextView manualInstructions;
    private LinearLayout manualRowsContainer;
    private EditText manualRefInput;
    private TextView amountLabel;
    private TextView limitsHint;
    private EditText amountInput;
    private TextView conversionPreview;
    private Button btnAmt1, btnAmt2, btnAmt3, btnAmt4;
    private TextView statusText;
    private ProgressBar progressBar;
    private Button btnSubmit, btnVerify;
    private TextView recentHeader;
    private LinearLayout recentContainer;

    private final List<GatewayItem> gateways = new ArrayList<>();
    private GatewayItem selectedGateway = null;
    private String selectedCurrency = "USD";
    private boolean isAuthenticated = false;
    private double liveBalanceUsd = 0.0;
    private double liveBalanceSyp = 0.0;
    private double livePendingUsd = 0.0;
    private double liveHeldUsd = 0.0;
    private double sypRate = 15000.0;
    private String cachedGoogleLoginUrl = "";
    private String activeDepositId = "";
    private boolean waitingForGatewayReturn = false;

    private RaqamiyatLocalStore localStore;
    private CatalogRepository repo;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }
        setContentView(R.layout.activity_native_payment);

        localStore = new RaqamiyatLocalStore(this);
        repo = new CatalogRepository(localStore);
        selectedCurrency = localStore.getPreferredCurrency();
        sypRate = localStore.getSypRate();

        bindViews();
        setupActions();
        updateCurrencyUi();
        loadWalletAndGateways();
    }

    private int dp(int val) {
        return Math.round(val * getResources().getDisplayMetrics().density);
    }

    private void bindViews() {
        rateBadge = findViewById(R.id.pay_rate_badge);
        loginBanner = findViewById(R.id.pay_login_banner);
        userGreeting = findViewById(R.id.pay_user_greeting);
        walletBalanceText = findViewById(R.id.pay_wallet_balance);
        walletSecondaryText = findViewById(R.id.pay_wallet_secondary);
        walletBreakdownText = findViewById(R.id.pay_wallet_breakdown);
        optUsd = findViewById(R.id.opt_curr_usd);
        optSyp = findViewById(R.id.opt_curr_syp);
        gatewaysCountText = findViewById(R.id.pay_gateways_count);
        gatewaysContainer = findViewById(R.id.pay_gateways_container);
        manualBox = findViewById(R.id.pay_manual_box);
        manualInstructions = findViewById(R.id.pay_manual_instructions);
        manualRowsContainer = findViewById(R.id.pay_manual_rows);
        manualRefInput = findViewById(R.id.pay_manual_ref_input);
        amountLabel = findViewById(R.id.pay_amount_label);
        limitsHint = findViewById(R.id.pay_limits_hint);
        amountInput = findViewById(R.id.pay_amount_input);
        conversionPreview = findViewById(R.id.pay_conversion_preview);
        btnAmt1 = findViewById(R.id.btn_amt_5);
        btnAmt2 = findViewById(R.id.btn_amt_10);
        btnAmt3 = findViewById(R.id.btn_amt_25);
        btnAmt4 = findViewById(R.id.btn_amt_50);
        statusText = findViewById(R.id.pay_status_text);
        progressBar = findViewById(R.id.pay_progress);
        btnSubmit = findViewById(R.id.btn_pay_submit);
        btnVerify = findViewById(R.id.btn_pay_verify);
        recentHeader = findViewById(R.id.pay_recent_header);
        recentContainer = findViewById(R.id.pay_recent_container);
    }

    private void setupActions() {
        ImageButton btnBack = findViewById(R.id.btn_pay_back);
        btnBack.setOnClickListener(v -> finish());

        Button btnRefresh = findViewById(R.id.btn_pay_refresh);
        btnRefresh.setOnClickListener(v -> {
            Toast.makeText(this, "جاري مزامنة الرصيد والبوابات...", Toast.LENGTH_SHORT).show();
            loadWalletAndGateways();
        });

        Button btnLoginNow = findViewById(R.id.btn_pay_login_now);
        btnLoginNow.setOnClickListener(v -> openNativeLogin());

        Button btnRedeemCard = findViewById(R.id.btn_redeem_card);
        btnRedeemCard.setOnClickListener(v -> showRedeemRechargeCardDialog());

        optUsd.setOnClickListener(v -> selectCurrency("USD"));
        optSyp.setOnClickListener(v -> selectCurrency("SYP"));

        amountInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                updateConversionPreview();
            }

            @Override
            public void afterTextChanged(Editable s) {}
        });

        btnSubmit.setOnClickListener(v -> submitPayment());
        btnVerify.setOnClickListener(v -> verifyDepositStatus());
    }

    private void openNativeLogin() {
        NativeAuthHelper.showLoginSheet(this, repo, localStore, cachedGoogleLoginUrl, authData -> loadWalletAndGateways());
    }

    private void showRedeemRechargeCardDialog() {
        if (!isAuthenticated) {
            openNativeLogin();
            return;
        }
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(20), dp(12), dp(20), dp(8));

        EditText codeField = new EditText(this);
        codeField.setBackgroundResource(R.drawable.bg_input_dark);
        codeField.setHint("مثال: RC-XXXX-XXXX");
        codeField.setHintTextColor(0xFF64748B);
        codeField.setTextColor(0xFFFFFFFF);
        codeField.setSingleLine(true);
        codeField.setPadding(dp(14), dp(12), dp(14), dp(12));
        box.addView(codeField);

        new MaterialAlertDialogBuilder(this)
                .setTitle("🎟️ شحن بطاقة رصيد رقميات")
                .setMessage("أدخل كود بطاقة الشحن لإضافة قيمتها فوراً إلى رصيد محفظتك:")
                .setView(box)
                .setPositiveButton("شحن فوري ⚡", (d, w) -> {
                    String code = codeField.getText() != null ? codeField.getText().toString().trim() : "";
                    if (code.isEmpty()) return;
                    progressBar.setVisibility(View.VISIBLE);
                    try {
                        JSONObject payload = new JSONObject();
                        payload.put("code", code);
                        repo.postJson(REDEEM_CARD_API, payload, (st, json, err) -> {
                            progressBar.setVisibility(View.GONE);
                            if (st == 200 && json != null && "success".equals(json.optString("status"))) {
                                Toast.makeText(this, json.optString("message", "تم شحن البطاقة بنجاح!"), Toast.LENGTH_LONG).show();
                                loadWalletAndGateways();
                            } else {
                                Toast.makeText(this, json != null ? json.optString("message", "رمز غير صالح") : "تعذر الشحن", Toast.LENGTH_LONG).show();
                            }
                        });
                    } catch (Exception ignored) {
                        progressBar.setVisibility(View.GONE);
                    }
                })
                .setNegativeButton("إلغاء", (d, w) -> d.dismiss())
                .show();
    }

    private void selectCurrency(String curr) {
        selectedCurrency = "SYP".equalsIgnoreCase(curr) ? "SYP" : "USD";
        localStore.setPreferredCurrency(selectedCurrency);
        amountInput.setText("");
        updateCurrencyUi();
    }

    private void updateCurrencyUi() {
        boolean isUsd = "USD".equals(selectedCurrency);
        optUsd.setBackgroundResource(isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        optUsd.setTextColor(isUsd ? 0xFF030712 : 0xFFE2E8F0);
        optSyp.setBackgroundResource(!isUsd ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        optSyp.setTextColor(!isUsd ? 0xFF030712 : 0xFFE2E8F0);

        rateBadge.setText("سعر الصرف الحي: 1$ = " + RaqamiyatLocalStore.formatSypAmount(sypRate));

        if (!isAuthenticated) {
            walletBalanceText.setText(isUsd ? "$0.00" : "0 ل.س");
            walletSecondaryText.setText("سجّل الدخول لمزامنة رصيدك الحقيقي");
        } else {
            if (isUsd) {
                walletBalanceText.setText(String.format(Locale.US, "$%.2f", liveBalanceUsd));
                walletSecondaryText.setText("≈ " + RaqamiyatLocalStore.formatSypAmount(liveBalanceSyp > 0 ? liveBalanceSyp : (liveBalanceUsd * sypRate)));
            } else {
                double sypDisp = liveBalanceSyp > 0 ? liveBalanceSyp : (liveBalanceUsd * sypRate);
                walletBalanceText.setText(RaqamiyatLocalStore.formatSypAmount(sypDisp));
                walletSecondaryText.setText(String.format(Locale.US, "≈ $%.2f USD", liveBalanceUsd));
            }
        }

        amountLabel.setText(isUsd ? "المبلغ المطلوب شحنه ($ USD)" : "المبلغ المطلوب شحنه (ل.س SYP)");
        amountInput.setHint(isUsd ? "أدخل المبلغ بالدولار (مثال: 10)" : "أدخل المبلغ بالليرة السورية (مثال: 50000)");

        // Smart quick-amount buttons adapted to selected currency and gateway limits
        boolean isMtn = selectedGateway != null && "mtn_pay".equals(selectedGateway.code);
        final String[] vals;
        final String[] labels;
        if (isUsd) {
            if (isMtn) {
                vals = new String[]{"1", "2", "3", "3.3"};
                labels = new String[]{"$1", "$2", "$3", "الحد الأقصى"};
            } else {
                vals = new String[]{"5", "10", "25", "50"};
                labels = new String[]{"$5", "$10", "$25", "$50"};
            }
        } else {
            if (isMtn) {
                vals = new String[]{"5000", "10000", "25000", "50000"};
                labels = new String[]{"5,000", "10,000", "25,000", "50,000"};
            } else {
                vals = new String[]{"25000", "50000", "100000", "250000"};
                labels = new String[]{"25,000", "50,000", "100,000", "250,000"};
            }
        }

        Button[] btns = new Button[]{btnAmt1, btnAmt2, btnAmt3, btnAmt4};
        for (int i = 0; i < 4; i++) {
            final String vStr = vals[i];
            btns[i].setText(labels[i]);
            btns[i].setOnClickListener(v -> amountInput.setText(vStr));
        }

        updateGatewayLimitsHint();
        updateConversionPreview();
    }

    private void updateGatewayLimitsHint() {
        if (selectedGateway == null) {
            limitsHint.setText("");
            return;
        }
        if ("USD".equals(selectedCurrency)) {
            limitsHint.setText(String.format(Locale.US, "الحد الأدنى: $%.2f", selectedGateway.minUsd));
        } else {
            limitsHint.setText("الحد الأدنى: " + RaqamiyatLocalStore.formatSypAmount(selectedGateway.minSyp));
        }
    }

    private void updateConversionPreview() {
        String raw = amountInput.getText() != null ? amountInput.getText().toString().trim() : "";
        if (raw.isEmpty()) {
            conversionPreview.setVisibility(View.GONE);
            return;
        }
        try {
            double val = Double.parseDouble(raw);
            if (val <= 0) {
                conversionPreview.setVisibility(View.GONE);
                return;
            }
            if ("USD".equals(selectedCurrency)) {
                double sypEq = val * sypRate;
                conversionPreview.setText("💡 يعادل تقريباً: " + RaqamiyatLocalStore.formatSypAmount(sypEq));
            } else {
                double usdEq = val / Math.max(1.0, sypRate);
                conversionPreview.setText(String.format(Locale.US, "💡 سيضاف لمحفظتك ما يعادل: $%.2f USD", usdEq));
            }
            conversionPreview.setVisibility(View.VISIBLE);
        } catch (Exception e) {
            conversionPreview.setVisibility(View.GONE);
        }
    }

    private void loadWalletAndGateways() {
        repo.fetchWalletAndGateways((code, obj, err) -> {
            if (obj == null) return;

            double fetchedRate = obj.optDouble("syp_rate", 0.0);
            if (fetchedRate > 1.0) {
                sypRate = fetchedRate;
            }
            cachedGoogleLoginUrl = obj.optString("google_login_url", "");
            isAuthenticated = obj.optBoolean("is_authenticated", false);

            if (isAuthenticated) {
                loginBanner.setVisibility(View.GONE);
                liveBalanceUsd = obj.optDouble("available_balance_usd", obj.optDouble("balance", 0.0));
                liveBalanceSyp = obj.optDouble("available_balance_syp", liveBalanceUsd * sypRate);
                livePendingUsd = obj.optDouble("pending_balance_usd", 0.0);
                liveHeldUsd = obj.optDouble("held_balance_usd", 0.0);

                JSONObject uObj = obj.optJSONObject("user");
                String uName = uObj != null ? uObj.optString("full_name", "") : "";
                userGreeting.setText(!uName.isEmpty() ? ("محفظة " + uName + " ✓") : "رصيد محفظتك الحقيقي ✓");

                if (livePendingUsd > 0 || liveHeldUsd > 0) {
                    walletBreakdownText.setText(String.format(Locale.US, "معلق: $%.2f • محجوز: $%.2f", livePendingUsd, liveHeldUsd));
                } else {
                    walletBreakdownText.setText("متاح بالكامل للشراء الفوري 24/7 ⚡");
                }
            } else {
                loginBanner.setVisibility(View.VISIBLE);
                userGreeting.setText("رصيد محفظتك الحالي (غير مسجل الدخول)");
                walletBreakdownText.setText("سجّل دخولك بالأعلى لعرض رصيدك الفعلي");
            }

            List<GatewayItem> parsed = GatewayItem.parseList(obj.optJSONArray("gateways"));
            gateways.clear();
            for (GatewayItem g : parsed) {
                if (g.forDeposit) gateways.add(g);
            }

            // Preserve selected gateway or pick first available gateway
            if (selectedGateway != null) {
                GatewayItem match = null;
                for (GatewayItem g : gateways) {
                    if (g.code.equals(selectedGateway.code)) {
                        match = g;
                        break;
                    }
                }
                selectedGateway = match;
            }
            if (selectedGateway == null || selectedGateway.isUnavailable) {
                for (GatewayItem g : gateways) {
                    if (!g.isUnavailable) {
                        selectedGateway = g;
                        break;
                    }
                }
                if (selectedGateway == null && !gateways.isEmpty()) {
                    selectedGateway = gateways.get(0);
                }
            }

            renderGatewaysList();
            renderRecentTransactions(obj.optJSONArray("recent_transactions"));
            updateCurrencyUi();
        });
    }

    private void renderGatewaysList() {
        gatewaysContainer.removeAllViews();
        gatewaysCountText.setText(gateways.size() + " وسائل متاحة");

        for (final GatewayItem gw : gateways) {
            boolean isSelected = selectedGateway != null && gw.code.equals(selectedGateway.code);

            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.HORIZONTAL);
            card.setGravity(Gravity.CENTER_VERTICAL);
            if (gw.isUnavailable) {
                card.setBackgroundResource(R.drawable.bg_gateway_disabled);
                card.setAlpha(0.68f);
            } else if (isSelected) {
                card.setBackgroundResource(R.drawable.bg_gateway_selected);
            } else {
                card.setBackgroundResource(R.drawable.bg_gateway_unselected);
            }

            LinearLayout.LayoutParams cardLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            cardLp.bottomMargin = dp(10);
            card.setLayoutParams(cardLp);
            card.setPadding(dp(12), dp(12), dp(12), dp(12));

            // Crisp White Rounded Logo Frame
            LinearLayout logoFrame = new LinearLayout(this);
            logoFrame.setBackgroundResource(R.drawable.bg_logo_box);
            logoFrame.setGravity(Gravity.CENTER);
            LinearLayout.LayoutParams lfLp = new LinearLayout.LayoutParams(dp(48), dp(48));
            lfLp.setMarginEnd(dp(12));
            logoFrame.setLayoutParams(lfLp);

            ImageView logoImg = new ImageView(this);
            logoImg.setLayoutParams(new LinearLayout.LayoutParams(dp(40), dp(40)));
            logoImg.setScaleType(ImageView.ScaleType.FIT_CENTER);
            String logoToLoad = !gw.logoUrl.isEmpty()
                    ? gw.logoUrl
                    : (DOMAIN + "/api/app/gateway-logo/" + gw.provider + "/");
            Glide.with(this)
                    .load(logoToLoad)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .error(R.mipmap.ic_launcher)
                    .into(logoImg);
            logoFrame.addView(logoImg);
            card.addView(logoFrame);

            // Title + Subtitle + Currencies Column
            LinearLayout infoCol = new LinearLayout(this);
            infoCol.setOrientation(LinearLayout.VERTICAL);
            infoCol.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

            TextView titleTv = new TextView(this);
            titleTv.setText(gw.name);
            titleTv.setTextColor(0xFFFFFFFF);
            titleTv.setTextSize(14f);
            titleTv.setTypeface(titleTv.getTypeface(), Typeface.BOLD);
            infoCol.addView(titleTv);

            TextView subTv = new TextView(this);
            subTv.setText(gw.subtitle);
            subTv.setTextColor(isSelected ? 0xFFBAE6FD : 0xFF94A3B8);
            subTv.setTextSize(11f);
            subTv.setMaxLines(2);
            infoCol.addView(subTv);

            String currStr = android.text.TextUtils.join(" • ", gw.currencies);
            String feeStr = (gw.feePercent <= 0 && gw.feeFixed <= 0) ? "بدون عمولة إضافية" : ("عمولة " + gw.feePercent + "%");
            TextView metaTv = new TextView(this);
            metaTv.setText("العملات: " + currStr + "  |  " + feeStr);
            metaTv.setTextColor(0xFF64748B);
            metaTv.setTextSize(10f);
            infoCol.addView(metaTv);

            card.addView(infoCol);

            // Status / Selection Badge
            TextView badgeTv = new TextView(this);
            badgeTv.setTextSize(10.5f);
            badgeTv.setTypeface(badgeTv.getTypeface(), Typeface.BOLD);
            badgeTv.setPadding(dp(10), dp(4), dp(10), dp(4));
            if (gw.isMaintenanceMode) {
                badgeTv.setText("قيد الصيانة 🛠️");
                badgeTv.setTextColor(0xFFFCA5A5);
                badgeTv.setBackgroundResource(R.drawable.bg_badge_red);
            } else if (gw.isComingSoon) {
                badgeTv.setText("قريباً ⏳");
                badgeTv.setTextColor(0xFFFDE68A);
                badgeTv.setBackgroundResource(R.drawable.bg_badge_amber);
            } else if (isSelected) {
                badgeTv.setText("✓ محدد");
                badgeTv.setTextColor(0xFF6EE7B7);
                badgeTv.setBackgroundResource(R.drawable.bg_badge_green);
            } else {
                badgeTv.setText(gw.badgeLabel != null && !gw.badgeLabel.isEmpty() ? gw.badgeLabel : "متاح ⚡");
                badgeTv.setTextColor(0xFF22D3EE);
                badgeTv.setBackgroundResource(R.drawable.bg_chip_unselected);
            }
            card.addView(badgeTv);

            card.setOnClickListener(v -> {
                if (gw.isUnavailable) {
                    String msg = !gw.unavailableMessage.isEmpty()
                            ? gw.unavailableMessage
                            : ("بوابة " + gw.name + " غير متاحة حالياً (" + gw.badgeLabel + ").");
                    Toast.makeText(NativePaymentActivity.this, msg, Toast.LENGTH_LONG).show();
                    return;
                }
                selectedGateway = gw;
                if ("mtn_pay".equals(gw.code) && "USD".equals(selectedCurrency)) {
                    // Cash Mobile works seamlessly in SYP (and USD), default to SYP for clarity
                    selectedCurrency = "SYP";
                    localStore.setPreferredCurrency("SYP");
                }
                renderGatewaysList();
                renderManualMethodBox();
                updateCurrencyUi();
                btnSubmit.setText("متابعة الشحن عبر " + gw.name + " ⚡");
            });

            gatewaysContainer.addView(card);
        }

        renderManualMethodBox();
        if (selectedGateway != null && !selectedGateway.isUnavailable) {
            btnSubmit.setText("متابعة الشحن عبر " + selectedGateway.name + " ⚡");
            btnSubmit.setEnabled(true);
            btnSubmit.setAlpha(1.0f);
        } else {
            btnSubmit.setText("اختر بوابة دفع متاحة");
            btnSubmit.setEnabled(false);
            btnSubmit.setAlpha(0.55f);
        }
    }

    private void renderManualMethodBox() {
        if (selectedGateway == null || !"manual".equals(selectedGateway.type)) {
            manualBox.setVisibility(View.GONE);
            return;
        }
        manualBox.setVisibility(View.VISIBLE);
        manualInstructions.setText(!selectedGateway.instructions.isEmpty()
                ? selectedGateway.instructions
                : "حوّل المبلغ إلى الحساب أدناه ثم أدخل رقم عملية التحويل:");
        manualRowsContainer.removeAllViews();
        try {
            JSONArray rows = new JSONArray(selectedGateway.staticRowsJson);
            for (int i = 0; i < rows.length(); i++) {
                JSONObject r = rows.optJSONObject(i);
                if (r == null) continue;
                final String rTitle = r.optString("title", "بيان");
                final String rVal = r.optString("value", "");
                if (rVal.isEmpty()) continue;

                LinearLayout rowView = new LinearLayout(this);
                rowView.setOrientation(LinearLayout.HORIZONTAL);
                rowView.setGravity(Gravity.CENTER_VERTICAL);
                rowView.setBackgroundResource(R.drawable.bg_input_dark);
                rowView.setPadding(dp(10), dp(8), dp(10), dp(8));
                LinearLayout.LayoutParams rLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                rLp.topMargin = dp(6);
                rowView.setLayoutParams(rLp);

                TextView tv = new TextView(this);
                tv.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
                tv.setText(rTitle + ": " + rVal);
                tv.setTextColor(0xFFF8FAFC);
                tv.setTextSize(12f);
                rowView.addView(tv);

                TextView copyBtn = new TextView(this);
                copyBtn.setText("نسخ 📋");
                copyBtn.setTextColor(0xFF22D3EE);
                copyBtn.setTextSize(11f);
                copyBtn.setOnClickListener(v -> {
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) {
                        cm.setPrimaryClip(ClipData.newPlainText(rTitle, rVal));
                        Toast.makeText(this, "تم نسخ " + rTitle, Toast.LENGTH_SHORT).show();
                    }
                });
                rowView.addView(copyBtn);
                manualRowsContainer.addView(rowView);
            }
        } catch (Exception ignored) {
        }
    }

    private void renderRecentTransactions(JSONArray arr) {
        recentContainer.removeAllViews();
        if (arr == null || arr.length() == 0) {
            recentHeader.setVisibility(View.GONE);
            return;
        }
        recentHeader.setVisibility(View.VISIBLE);
        for (int i = 0; i < Math.min(8, arr.length()); i++) {
            JSONObject t = arr.optJSONObject(i);
            if (t == null) continue;

            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setBackgroundResource(R.drawable.bg_card_dark);
            row.setPadding(dp(12), dp(10), dp(12), dp(10));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.bottomMargin = dp(8);
            row.setLayoutParams(lp);

            LinearLayout left = new LinearLayout(this);
            left.setOrientation(LinearLayout.VERTICAL);
            left.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

            TextView title = new TextView(this);
            title.setText(t.optString("title", "عملية شحن"));
            title.setTextColor(0xFFF8FAFC);
            title.setTextSize(12.5f);
            title.setTypeface(title.getTypeface(), Typeface.BOLD);
            left.addView(title);

            TextView dateTv = new TextView(this);
            dateTv.setText(t.optString("created_at", "") + (t.optString("reference", "").isEmpty() ? "" : " • " + t.optString("reference")));
            dateTv.setTextColor(0xFF64748B);
            dateTv.setTextSize(10.5f);
            left.addView(dateTv);
            row.addView(left);

            LinearLayout right = new LinearLayout(this);
            right.setOrientation(LinearLayout.VERTICAL);
            right.setGravity(Gravity.END);

            double amt = t.optDouble("amount", 0.0);
            String cur = t.optString("currency", "USD");
            TextView amtTv = new TextView(this);
            amtTv.setText("SYP".equalsIgnoreCase(cur) ? RaqamiyatLocalStore.formatSypAmount(amt) : String.format(Locale.US, "$%.2f", amt));
            amtTv.setTextColor(0xFFFBBF24);
            amtTv.setTextSize(13f);
            amtTv.setTypeface(amtTv.getTypeface(), Typeface.BOLD);
            right.addView(amtTv);

            String st = t.optString("status", "");
            TextView stTv = new TextView(this);
            stTv.setText(t.optString("status_ar", st));
            stTv.setTextSize(10.5f);
            stTv.setTextColor("completed".equals(st) ? 0xFF10B981 : ("rejected".equals(st) ? 0xFFF87171 : 0xFFFBBF24));
            right.addView(stTv);

            row.addView(right);
            recentContainer.addView(row);
        }
    }

    private void submitPayment() {
        if (!isAuthenticated) {
            openNativeLogin();
            return;
        }
        if (selectedGateway == null || selectedGateway.isUnavailable) {
            Toast.makeText(this, "يرجى اختيار بوابة دفع متاحة أولاً", Toast.LENGTH_SHORT).show();
            return;
        }

        String amt = amountInput.getText() != null ? amountInput.getText().toString().trim() : "";
        if (amt.isEmpty()) {
            Toast.makeText(this, "يرجى إدخال المبلغ المطلوب شحنه", Toast.LENGTH_SHORT).show();
            return;
        }

        if ("manual".equals(selectedGateway.type)) {
            String ref = manualRefInput.getText() != null ? manualRefInput.getText().toString().trim() : "";
            if (ref.isEmpty()) {
                Toast.makeText(this, "يرجى إدخال رقم عملية التحويل أو اسم المرسل", Toast.LENGTH_SHORT).show();
                return;
            }
        }

        progressBar.setVisibility(View.VISIBLE);
        statusText.setVisibility(View.GONE);
        btnSubmit.setEnabled(false);

        try {
            JSONObject payload = new JSONObject();
            payload.put("provider", selectedGateway.provider);
            payload.put("payment_method_id", selectedGateway.paymentMethodId);
            payload.put("amount", amt);
            payload.put("currency_code", selectedCurrency);
            if ("manual".equals(selectedGateway.type) && manualRefInput.getText() != null) {
                payload.put("reference_number", manualRefInput.getText().toString().trim());
            }

            repo.postJson(DEPOSIT_API, payload, (code, json, err) -> {
                progressBar.setVisibility(View.GONE);
                btnSubmit.setEnabled(true);

                if (code == 401 || (json != null && json.optBoolean("requires_auth", false))) {
                    openNativeLogin();
                    return;
                }

                if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                    activeDepositId = json.optString("deposit_id", "");
                    String payMode = json.optString("payment_mode", "gateway");

                    if ("mtn_native".equals(payMode)) {
                        int invNum = json.optInt("mtn_invoice_number", 0);
                        double sypAmt = json.optDouble("syp_amount", 0.0);
                        String eq = json.optString("mtn_equation", "");
                        JSONArray phones = json.optJSONArray("saved_mtn_phones");
                        NativeMtnDialogHelper.show(
                                NativePaymentActivity.this,
                                repo,
                                invNum,
                                sypAmt,
                                eq,
                                phones,
                                selectedGateway.logoUrl,
                                confirmJson -> {
                                    statusText.setTextColor(0xFF10B981);
                                    statusText.setText("✓ تم تأكيد الدفع عبر كاش موبايل وإضافة الرصيد إلى محفظتك بنجاح!");
                                    statusText.setVisibility(View.VISIBLE);
                                    amountInput.setText("");
                                    Toast.makeText(NativePaymentActivity.this, "تم شحن محفظتك بنجاح ⚡", Toast.LENGTH_LONG).show();
                                    loadWalletAndGateways();
                                }
                        );
                        return;
                    }

                    if ("manual".equals(payMode)) {
                        statusText.setTextColor(0xFF10B981);
                        statusText.setText("✓ " + json.optString("message", "تم استلام طلب الإيداع بنجاح!"));
                        statusText.setVisibility(View.VISIBLE);
                        amountInput.setText("");
                        manualRefInput.setText("");
                        loadWalletAndGateways();
                        return;
                    }

                    String paymentUrl = json.optString("payment_url", "");
                    btnVerify.setVisibility(View.VISIBLE);
                    if (!paymentUrl.isEmpty()) {
                        waitingForGatewayReturn = true;
                        statusText.setTextColor(0xFF22D3EE);
                        statusText.setText("تم توجيهك لإتمام الدفع... عند العودة سيتم التحقق وتحديث رصيدك تلقائياً.");
                        statusText.setVisibility(View.VISIBLE);
                        openPaymentUrl(paymentUrl);
                    } else {
                        statusText.setText("تم إنشاء الطلب رقم: " + json.optString("bill_no"));
                        statusText.setVisibility(View.VISIBLE);
                    }
                    return;
                }

                String errMsg = json != null ? json.optString("message", "تعذر بدء عملية الدفع") : (err != null ? err : "خطأ في الاتصال");
                statusText.setTextColor(0xFFF87171);
                statusText.setText(errMsg);
                statusText.setVisibility(View.VISIBLE);
            });
        } catch (Exception e) {
            progressBar.setVisibility(View.GONE);
            btnSubmit.setEnabled(true);
        }
    }

    private void verifyDepositStatus() {
        if (activeDepositId.isEmpty()) return;
        progressBar.setVisibility(View.VISIBLE);
        String url = DOMAIN + "/api/app/payments/deposit/" + activeDepositId + "/status/";
        repo.getJson(url, (code, obj, err) -> {
            progressBar.setVisibility(View.GONE);
            if (code == 200 && obj != null) {
                boolean done = obj.optBoolean("is_completed", false);
                loadWalletAndGateways();
                if (done) {
                    statusText.setTextColor(0xFF10B981);
                    statusText.setText("✓ تم تأكيد الدفع وإضافة الرصيد إلى محفظتك بنجاح!");
                    statusText.setVisibility(View.VISIBLE);
                    btnVerify.setVisibility(View.GONE);
                    Toast.makeText(NativePaymentActivity.this, "تم شحن المحفظة بنجاح!", Toast.LENGTH_LONG).show();
                } else {
                    statusText.setTextColor(0xFFFBBF24);
                    statusText.setText("الحالة الحالية: قيد الانتظار — أتمم السداد في البوابة ثم اضغط تحقق.");
                    statusText.setVisibility(View.VISIBLE);
                }
            }
        });
    }

    private void openPaymentUrl(String url) {
        if (MainActivity.tryLaunchNativeShamCashAppOnly(this, url)) {
            return;
        }
        Intent intent = new Intent(this, MainActivity.class);
        intent.putExtra(ProductDetailActivity.EXTRA_OPEN_URL, url);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(intent);
        finish();
    }

    @Override
    protected void onResume() {
        super.onResume();
        selectedCurrency = localStore.getPreferredCurrency();
        loadWalletAndGateways();
        if (waitingForGatewayReturn && !activeDepositId.isEmpty()) {
            waitingForGatewayReturn = false;
            mainHandler.postDelayed(this::verifyDepositStatus, 800);
            mainHandler.postDelayed(this::verifyDepositStatus, 3200);
        }
    }
}
