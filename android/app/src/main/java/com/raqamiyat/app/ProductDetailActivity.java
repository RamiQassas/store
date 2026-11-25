package com.raqamiyat.app;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.android.material.bottomsheet.BottomSheetDialog;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.adapter.VariantAdapter;
import com.raqamiyat.app.model.CartItem;
import com.raqamiyat.app.model.FormFieldItem;
import com.raqamiyat.app.model.GatewayItem;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ProductDetailActivity extends AppCompatActivity {

    public static final String EXTRA_PRODUCT = "extra_product";
    public static final String EXTRA_OPEN_URL = "extra_open_url";
    public static final String EXTRA_OPEN_NATIVE_ORDERS = "extra_open_native_orders";
    private static final String ORDER_API_URL = CatalogRepository.DOMAIN + "/api/app/orders/create/";

    private ProductItem product;
    private VariantItem selectedVariant;
    private VariantAdapter variantAdapter;
    private ConnectivityHelper connectivityHelper;
    private RaqamiyatLocalStore localStore;
    private CatalogRepository repo;

    private TextView btnCurrencyToggle;
    private TextView priceView;
    private TextView priceSecondaryView;
    private TextView codeBadge;

    private boolean isAuthenticated = false;
    private double liveBalanceUsd = 0.0;
    private double liveBalanceSyp = 0.0;
    private String cachedGoogleLoginUrl = "";
    private final List<GatewayItem> checkoutGateways = new ArrayList<>();

    private static class PayOption {
        final String key;
        final String method;
        final String currency;
        final String title;
        final String subtitle;
        final String logoUrl;
        final boolean isWallet;
        final boolean isUnavailable;
        final String badge;
        final String unavailMsg;

        PayOption(String key, String method, String currency, String title, String subtitle,
                  String logoUrl, boolean isWallet, boolean isUnavailable, String badge, String unavailMsg) {
            this.key = key;
            this.method = method;
            this.currency = currency;
            this.title = title;
            this.subtitle = subtitle;
            this.logoUrl = logoUrl;
            this.isWallet = isWallet;
            this.isUnavailable = isUnavailable;
            this.badge = badge;
            this.unavailMsg = unavailMsg;
        }
    }

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
        repo = new CatalogRepository(localStore);

        product = (ProductItem) getIntent().getSerializableExtra(EXTRA_PRODUCT);
        if (product == null) {
            finish();
            return;
        }

        ImageButton btnBack = findViewById(R.id.btn_detail_back);
        btnBack.setOnClickListener(v -> finish());

        btnCurrencyToggle = findViewById(R.id.btn_detail_currency);
        codeBadge = findViewById(R.id.detail_code_badge);
        ImageView img = findViewById(R.id.detail_image);
        TextView category = findViewById(R.id.detail_category);
        TextView delivery = findViewById(R.id.detail_delivery);
        TextView name = findViewById(R.id.detail_name);
        priceView = findViewById(R.id.detail_price);
        priceSecondaryView = findViewById(R.id.detail_price_secondary);
        TextView description = findViewById(R.id.detail_description);
        TextView variantsLabel = findViewById(R.id.detail_variants_label);
        RecyclerView variantsRv = findViewById(R.id.detail_variants_rv);
        Button btnBuy = findViewById(R.id.btn_detail_buy);
        Button btnAddCart = findViewById(R.id.btn_detail_add_cart);

        if (product.imageUrl != null && !product.imageUrl.isEmpty()) {
            Glide.with(this)
                    .load(product.imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .into(img);
        } else {
            img.setImageResource(R.mipmap.ic_launcher);
        }

        codeBadge.setText(product.code != null && !product.code.isEmpty() ? "#" + product.code : "رقميات");
        category.setText(product.categoryName != null && !product.categoryName.isEmpty() ? product.categoryName : "المنتجات");
        delivery.setText(product.deliveryTimeDisplay != null && !product.deliveryTimeDisplay.isEmpty()
                ? ("⚡ " + product.deliveryTimeDisplay)
                : "⚡ تسليم فوري");

        name.setText(product.name);
        StringBuilder descText = new StringBuilder();
        if (product.description != null && !product.description.trim().isEmpty()) {
            descText.append(product.description.trim());
        } else {
            descText.append("منتج رقمي أصلي متوفر في متجر رقميات بتسليم فوري وضمان كامل.");
        }
        if (product.instructions != null && !product.instructions.trim().isEmpty()) {
            descText.append("\n\n📌 تعليمات الاستخدام:\n").append(product.instructions.trim());
        }
        description.setText(descText.toString());

        if (product.variants != null && !product.variants.isEmpty()) {
            selectedVariant = product.variants.get(0);
            if (selectedVariant.sku != null && !selectedVariant.sku.isEmpty()) {
                codeBadge.setText("#" + selectedVariant.sku);
            }
            variantsRv.setLayoutManager(new LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false));
            variantAdapter = new VariantAdapter(variant -> {
                selectedVariant = variant;
                if (variant.sku != null && !variant.sku.isEmpty()) {
                    codeBadge.setText("#" + variant.sku);
                }
                refreshDisplayedPrices();
            });
            variantAdapter.submitList(product.variants);
            variantsRv.setAdapter(variantAdapter);
        } else {
            variantsLabel.setVisibility(View.GONE);
            variantsRv.setVisibility(View.GONE);
        }

        btnCurrencyToggle.setOnClickListener(v -> {
            localStore.togglePreferredCurrency();
            refreshDisplayedPrices();
        });

        refreshDisplayedPrices();
        prefetchWalletAndGateways();

        if (product.isOutOfStock) {
            btnBuy.setText("نفدت الكمية حالياً");
            btnBuy.setEnabled(false);
            btnBuy.setAlpha(0.55f);
            btnAddCart.setVisibility(View.GONE);
        } else {
            btnAddCart.setOnClickListener(v -> {
                double uPrice = selectedVariant != null ? selectedVariant.price : product.price;
                String vId = selectedVariant != null ? selectedVariant.id : "default";
                String vName = selectedVariant != null ? selectedVariant.name : product.name;
                int count = localStore.addToCart(new CartItem(
                        product.id, vId, product.name, vName, product.imageUrl, uPrice, 1, ""
                ));
                Toast.makeText(this, "🛒 تمت الإضافة إلى السلة (" + count + ")", Toast.LENGTH_SHORT).show();
            });

            btnBuy.setOnClickListener(v -> {
                if (!connectivityHelper.isOnline()) {
                    new MaterialAlertDialogBuilder(this)
                            .setTitle("⚠️ لا يوجد اتصال بالإنترنت")
                            .setMessage("إتمام الطلب والشراء يتطلب اتصالاً فعالاً بالإنترنت لحماية حسابك وتأكيد العملية.")
                            .setPositiveButton("حسناً", (d, w) -> d.dismiss())
                            .show();
                    return;
                }
                openLuxuryCheckoutBottomSheet();
            });
        }
    }

    private int dp(int val) {
        return Math.round(val * getResources().getDisplayMetrics().density);
    }

    private void refreshDisplayedPrices() {
        String curr = localStore.getPreferredCurrency();
        double rate = localStore.getSypRate();
        btnCurrencyToggle.setText("USD".equals(curr) ? "USD $" : "ل.س SYP");

        double activePrice = selectedVariant != null ? selectedVariant.price : product.price;
        if (activePrice > 0) {
            priceView.setText(localStore.formatPrice(activePrice));
            priceSecondaryView.setText(localStore.formatSecondaryPrice(activePrice));
            priceSecondaryView.setVisibility(View.VISIBLE);
        } else {
            priceView.setText("حسب الباقة");
            priceSecondaryView.setVisibility(View.GONE);
        }

        if (variantAdapter != null) {
            variantAdapter.updateCurrencyConfig(curr, rate);
        }
    }

    private void prefetchWalletAndGateways() {
        repo.fetchWalletAndGateways((code, obj, err) -> {
            if (obj == null) return;
            isAuthenticated = obj.optBoolean("is_authenticated", false);
            cachedGoogleLoginUrl = obj.optString("google_login_url", "");
            if (isAuthenticated) {
                liveBalanceUsd = obj.optDouble("available_balance_usd", obj.optDouble("balance", 0.0));
                liveBalanceSyp = obj.optDouble("available_balance_syp", liveBalanceUsd * localStore.getSypRate());
            }
            List<GatewayItem> parsed = GatewayItem.parseList(obj.optJSONArray("gateways"));
            checkoutGateways.clear();
            for (GatewayItem g : parsed) {
                if (g.forCheckout && "gateway".equals(g.type)) {
                    checkoutGateways.add(g);
                }
            }
            refreshDisplayedPrices();
        });
    }

    private List<PayOption> buildCheckoutOptions(double totalUsd) {
        List<PayOption> opts = new ArrayList<>();
        String walletSub;
        if (isAuthenticated) {
            walletSub = String.format(Locale.US, "رصيدك المتاح: $%.2f  (≈ %s)",
                    liveBalanceUsd, RaqamiyatLocalStore.formatSypAmount(liveBalanceSyp > 0 ? liveBalanceSyp : liveBalanceUsd * localStore.getSypRate()));
        } else {
            walletSub = "خصم فوري واستلام الكود خلال ثوانٍ";
        }
        opts.add(new PayOption(
                "wallet", "wallet", localStore.getPreferredCurrency(),
                "محفظة رقميات الإلكترونية", walletSub,
                CatalogRepository.DOMAIN + "/logo-square.jpg",
                true, false, "فوري ⚡", ""
        ));

        if (!checkoutGateways.isEmpty()) {
            for (GatewayItem g : checkoutGateways) {
                if ("sham_cash".equals(g.code)) {
                    opts.add(new PayOption(
                            "sham_usd", "sham_cash", "USD",
                            g.name + " — دولار USD",
                            "تحويل تلقائي إلى تطبيق شام كاش ($ USD)",
                            g.logoUrl, false, g.isUnavailable, g.badgeLabel, g.unavailableMessage
                    ));
                    opts.add(new PayOption(
                            "sham_syp", "sham_cash", "SYP",
                            g.name + " — ليرة SYP",
                            "تحويل تلقائي إلى تطبيق شام كاش (ل.س SYP)",
                            g.logoUrl, false, g.isUnavailable, g.badgeLabel, g.unavailableMessage
                    ));
                } else if ("mtn_pay".equals(g.code)) {
                    double totalSyp = totalUsd * localStore.getSypRate();
                    boolean overCap = totalSyp > 50000.0;
                    opts.add(new PayOption(
                            "mtn_syp", "mtn_pay", "SYP",
                            g.name,
                            overCap ? "يتجاوز سقف كاش موبايل (50,000 ل.س)" : "دفع مباشر برقم الهاتف ورمز SMS من داخل التطبيق",
                            g.logoUrl, false, g.isUnavailable || overCap,
                            overCap ? "أعلى من 50,000" : g.badgeLabel,
                            overCap ? "الحد الأقصى للشراء عبر كاش موبايل هو 50,000 ل.س." : g.unavailableMessage
                    ));
                } else {
                    String defCurr = g.supportsCurrency("SYP") ? "SYP" : "USD";
                    opts.add(new PayOption(
                            g.code, g.provider, defCurr,
                            g.name, g.subtitle,
                            g.logoUrl, false, g.isUnavailable, g.badgeLabel, g.unavailableMessage
                    ));
                }
            }
        } else {
            // Instant fallback if gateways API hasn't returned yet
            opts.add(new PayOption("sham_usd", "sham_cash", "USD", "شام كاش (ShamCash) — USD",
                    "دفع فوري عبر تطبيق شام كاش", CatalogRepository.DOMAIN + "/api/app/gateway-logo/sham_cash/",
                    false, false, "فوري ⚡", ""));
            opts.add(new PayOption("sham_syp", "sham_cash", "SYP", "شام كاش (ShamCash) — SYP",
                    "دفع فوري بالليرة السورية", CatalogRepository.DOMAIN + "/api/app/gateway-logo/sham_cash/",
                    false, false, "فوري ⚡", ""));
            opts.add(new PayOption("mtn_syp", "mtn_pay", "SYP", "كاش موبايل (Cash Mobile)",
                    "دفع مباشر عبر هاتف MTN + رمز SMS", CatalogRepository.DOMAIN + "/api/app/gateway-logo/mtn_pay/",
                    false, false, "فوري ⚡", ""));
        }
        return opts;
    }

    private void openLuxuryCheckoutBottomSheet() {
        BottomSheetDialog sheet = new BottomSheetDialog(this);
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        outer.setBackgroundColor(0xFF0B1120);
        int pad = dp(16);
        outer.setPadding(pad, pad, pad, dp(22));

        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(root);
        outer.addView(scroll);

        final double unitPriceUsd = selectedVariant != null ? selectedVariant.price : product.price;
        final String variantLabel = selectedVariant != null ? selectedVariant.name : product.name;
        final int[] qty = {1};

        // Product Summary Header
        LinearLayout headerCard = new LinearLayout(this);
        headerCard.setOrientation(LinearLayout.HORIZONTAL);
        headerCard.setGravity(Gravity.CENTER_VERTICAL);
        headerCard.setBackgroundResource(R.drawable.bg_wallet_hero);
        headerCard.setPadding(dp(12), dp(12), dp(12), dp(12));

        ImageView thumb = new ImageView(this);
        LinearLayout.LayoutParams thLp = new LinearLayout.LayoutParams(dp(52), dp(52));
        thLp.setMarginEnd(dp(12));
        thumb.setLayoutParams(thLp);
        thumb.setBackgroundResource(R.drawable.bg_logo_box);
        thumb.setPadding(dp(4), dp(4), dp(4), dp(4));
        if (product.imageUrl != null && !product.imageUrl.isEmpty()) {
            Glide.with(this).load(product.imageUrl).placeholder(R.mipmap.ic_launcher).into(thumb);
        } else {
            thumb.setImageResource(R.mipmap.ic_launcher);
        }
        headerCard.addView(thumb);

        LinearLayout hCol = new LinearLayout(this);
        hCol.setOrientation(LinearLayout.VERTICAL);
        hCol.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        TextView hTitle = new TextView(this);
        hTitle.setText(product.name);
        hTitle.setTextColor(0xFFFFFFFF);
        hTitle.setTextSize(14f);
        hTitle.setTypeface(hTitle.getTypeface(), Typeface.BOLD);
        hCol.addView(hTitle);

        TextView hSub = new TextView(this);
        hSub.setText("الباقة: " + variantLabel);
        hSub.setTextColor(0xFF22D3EE);
        hSub.setTextSize(11.5f);
        hCol.addView(hSub);

        final TextView totalPriceTv = new TextView(this);
        totalPriceTv.setTextColor(0xFFFBBF24);
        totalPriceTv.setTextSize(15f);
        totalPriceTv.setTypeface(totalPriceTv.getTypeface(), Typeface.BOLD);
        hCol.addView(totalPriceTv);

        headerCard.addView(hCol);
        root.addView(headerCard);

        // Quantity Stepper Row
        LinearLayout qtyRow = new LinearLayout(this);
        qtyRow.setOrientation(LinearLayout.HORIZONTAL);
        qtyRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams qLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        qLp.topMargin = dp(14);
        qtyRow.setLayoutParams(qLp);

        TextView qtyLbl = new TextView(this);
        qtyLbl.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        qtyLbl.setText("الكمية المطلوبة:");
        qtyLbl.setTextColor(0xFFF8FAFC);
        qtyLbl.setTextSize(13.5f);
        qtyLbl.setTypeface(qtyLbl.getTypeface(), Typeface.BOLD);
        qtyRow.addView(qtyLbl);

        TextView btnMinus = new TextView(this);
        btnMinus.setText("−");
        btnMinus.setTextColor(0xFFFFFFFF);
        btnMinus.setTextSize(18f);
        btnMinus.setGravity(Gravity.CENTER);
        btnMinus.setBackgroundResource(R.drawable.bg_chip_unselected);
        btnMinus.setLayoutParams(new LinearLayout.LayoutParams(dp(38), dp(36)));
        qtyRow.addView(btnMinus);

        final TextView qtyValTv = new TextView(this);
        qtyValTv.setText("1");
        qtyValTv.setTextColor(0xFFFFFFFF);
        qtyValTv.setTextSize(15f);
        qtyValTv.setTypeface(qtyValTv.getTypeface(), Typeface.BOLD);
        qtyValTv.setPadding(dp(16), 0, dp(16), 0);
        qtyRow.addView(qtyValTv);

        TextView btnPlus = new TextView(this);
        btnPlus.setText("+");
        btnPlus.setTextColor(0xFF22D3EE);
        btnPlus.setTextSize(18f);
        btnPlus.setGravity(Gravity.CENTER);
        btnPlus.setBackgroundResource(R.drawable.bg_chip_unselected);
        btnPlus.setLayoutParams(new LinearLayout.LayoutParams(dp(38), dp(36)));
        qtyRow.addView(btnPlus);
        root.addView(qtyRow);

        // Dynamic Product Form Schema Inputs
        final Map<String, View> dynamicFieldViews = new HashMap<>();
        final EditText fallbackNoteInput;
        if (product.formFields != null && !product.formFields.isEmpty()) {
            fallbackNoteInput = null;
            for (FormFieldItem f : product.formFields) {
                TextView fLbl = new TextView(this);
                fLbl.setText(f.label + (f.required ? " *" : " (اختياري)"));
                fLbl.setTextColor(0xFFE2E8F0);
                fLbl.setTextSize(12.5f);
                fLbl.setTypeface(fLbl.getTypeface(), Typeface.BOLD);
                LinearLayout.LayoutParams flLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                flLp.topMargin = dp(12);
                fLbl.setLayoutParams(flLp);
                root.addView(fLbl);

                if ("select".equalsIgnoreCase(f.type) && !f.options.isEmpty()) {
                    Spinner sp = new Spinner(this);
                    sp.setBackgroundResource(R.drawable.bg_input_dark);
                    ArrayAdapter<String> ad = new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, f.options);
                    sp.setAdapter(ad);
                    LinearLayout.LayoutParams sLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46));
                    sLp.topMargin = dp(6);
                    sp.setLayoutParams(sLp);
                    root.addView(sp);
                    dynamicFieldViews.put(f.name, sp);
                } else {
                    EditText et = new EditText(this);
                    et.setBackgroundResource(R.drawable.bg_input_dark);
                    et.setHint(!f.placeholder.isEmpty() ? f.placeholder : ("أدخل " + f.label));
                    et.setHintTextColor(0xFF64748B);
                    et.setTextColor(0xFFFFFFFF);
                    if ("number".equalsIgnoreCase(f.type) || "tel".equalsIgnoreCase(f.type)) {
                        et.setInputType(InputType.TYPE_CLASS_PHONE);
                    } else {
                        et.setInputType(InputType.TYPE_CLASS_TEXT);
                    }
                    et.setSingleLine(true);
                    et.setPadding(dp(14), dp(10), dp(14), dp(10));
                    LinearLayout.LayoutParams eLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46));
                    eLp.topMargin = dp(6);
                    et.setLayoutParams(eLp);
                    root.addView(et);
                    dynamicFieldViews.put(f.name, et);
                }
            }
        } else {
            TextView nLbl = new TextView(this);
            nLbl.setText("معرف الحساب / رقم التواصل / ملاحظة (اختياري):");
            nLbl.setTextColor(0xFFE2E8F0);
            nLbl.setTextSize(12.5f);
            LinearLayout.LayoutParams nlLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            nlLp.topMargin = dp(12);
            nLbl.setLayoutParams(nlLp);
            root.addView(nLbl);

            fallbackNoteInput = new EditText(this);
            fallbackNoteInput.setBackgroundResource(R.drawable.bg_input_dark);
            fallbackNoteInput.setHint("أدخل المعرف أو رقم الهاتف إن وجد");
            fallbackNoteInput.setHintTextColor(0xFF64748B);
            fallbackNoteInput.setTextColor(0xFFFFFFFF);
            fallbackNoteInput.setSingleLine(true);
            fallbackNoteInput.setPadding(dp(14), dp(10), dp(14), dp(10));
            LinearLayout.LayoutParams fnLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46));
            fnLp.topMargin = dp(6);
            fallbackNoteInput.setLayoutParams(fnLp);
            root.addView(fallbackNoteInput);
        }

        // Payment Method Cards Section (with real logos via Glide!)
        TextView payHeader = new TextView(this);
        payHeader.setText("اختر وسيلة الدفع:");
        payHeader.setTextColor(0xFFF8FAFC);
        payHeader.setTextSize(13.5f);
        payHeader.setTypeface(payHeader.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams phLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        phLp.topMargin = dp(16);
        phLp.bottomMargin = dp(8);
        payHeader.setLayoutParams(phLp);
        root.addView(payHeader);

        final LinearLayout methodsBox = new LinearLayout(this);
        methodsBox.setOrientation(LinearLayout.VERTICAL);
        root.addView(methodsBox);

        final PayOption[] selectedOpt = {null};
        final Button confirmBtn = new Button(this);
        confirmBtn.setBackgroundResource(R.drawable.bg_button_gold);
        confirmBtn.setTextColor(0xFF030712);
        confirmBtn.setTextSize(14.5f);
        confirmBtn.setAllCaps(false);
        confirmBtn.setTypeface(confirmBtn.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams cbLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        cbLp.topMargin = dp(14);
        confirmBtn.setLayoutParams(cbLp);

        final Runnable[] renderMethods = new Runnable[1];
        renderMethods[0] = () -> {
            double totalUsd = unitPriceUsd * qty[0];
            totalPriceTv.setText("الإجمالي: " + localStore.formatPrice(totalUsd) + "  (" + localStore.formatSecondaryPrice(totalUsd) + ")");

            List<PayOption> options = buildCheckoutOptions(totalUsd);
            if (selectedOpt[0] == null || selectedOpt[0].isUnavailable) {
                for (PayOption o : options) {
                    if (!o.isUnavailable) {
                        selectedOpt[0] = o;
                        break;
                    }
                }
            } else {
                for (PayOption o : options) {
                    if (o.key.equals(selectedOpt[0].key)) {
                        selectedOpt[0] = o;
                        break;
                    }
                }
            }

            methodsBox.removeAllViews();
            for (final PayOption opt : options) {
                boolean isSel = selectedOpt[0] != null && opt.key.equals(selectedOpt[0].key) && !opt.isUnavailable;
                LinearLayout card = new LinearLayout(this);
                card.setOrientation(LinearLayout.HORIZONTAL);
                card.setGravity(Gravity.CENTER_VERTICAL);
                card.setPadding(dp(10), dp(10), dp(10), dp(10));
                if (opt.isUnavailable) {
                    card.setBackgroundResource(R.drawable.bg_gateway_disabled);
                    card.setAlpha(0.65f);
                } else if (isSel) {
                    card.setBackgroundResource(R.drawable.bg_gateway_selected);
                } else {
                    card.setBackgroundResource(R.drawable.bg_gateway_unselected);
                }
                LinearLayout.LayoutParams cLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                cLp.bottomMargin = dp(8);
                card.setLayoutParams(cLp);

                LinearLayout logoFrame = new LinearLayout(this);
                logoFrame.setBackgroundResource(R.drawable.bg_logo_box);
                logoFrame.setGravity(Gravity.CENTER);
                LinearLayout.LayoutParams lfLp = new LinearLayout.LayoutParams(dp(42), dp(42));
                lfLp.setMarginEnd(dp(10));
                logoFrame.setLayoutParams(lfLp);

                ImageView logoIv = new ImageView(this);
                logoIv.setLayoutParams(new LinearLayout.LayoutParams(dp(34), dp(34)));
                logoIv.setScaleType(ImageView.ScaleType.FIT_CENTER);
                Glide.with(this)
                        .load(opt.logoUrl)
                        .diskCacheStrategy(DiskCacheStrategy.ALL)
                        .placeholder(R.mipmap.ic_launcher)
                        .error(R.mipmap.ic_launcher)
                        .into(logoIv);
                logoFrame.addView(logoIv);
                card.addView(logoFrame);

                LinearLayout col = new LinearLayout(this);
                col.setOrientation(LinearLayout.VERTICAL);
                col.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

                TextView t1 = new TextView(this);
                t1.setText(opt.title);
                t1.setTextColor(0xFFFFFFFF);
                t1.setTextSize(13f);
                t1.setTypeface(t1.getTypeface(), Typeface.BOLD);
                col.addView(t1);

                TextView t2 = new TextView(this);
                t2.setText(opt.subtitle);
                t2.setTextColor(isSel ? 0xFFBAE6FD : 0xFF94A3B8);
                t2.setTextSize(10.5f);
                col.addView(t2);
                card.addView(col);

                TextView badge = new TextView(this);
                badge.setTextSize(10f);
                badge.setTypeface(badge.getTypeface(), Typeface.BOLD);
                badge.setPadding(dp(8), dp(3), dp(8), dp(3));
                if (opt.isUnavailable) {
                    badge.setText(opt.badge != null && !opt.badge.isEmpty() ? opt.badge : "غير متاح");
                    badge.setTextColor(0xFFFDE68A);
                    badge.setBackgroundResource(R.drawable.bg_badge_amber);
                } else if (isSel) {
                    badge.setText("✓ محدد");
                    badge.setTextColor(0xFF6EE7B7);
                    badge.setBackgroundResource(R.drawable.bg_badge_green);
                } else {
                    badge.setText(opt.badge);
                    badge.setTextColor(0xFF22D3EE);
                    badge.setBackgroundResource(R.drawable.bg_chip_unselected);
                }
                card.addView(badge);

                card.setOnClickListener(v -> {
                    if (opt.isUnavailable) {
                        Toast.makeText(this, !opt.unavailMsg.isEmpty() ? opt.unavailMsg : "هذه البوابة غير متاحة حالياً", Toast.LENGTH_LONG).show();
                        return;
                    }
                    selectedOpt[0] = opt;
                    renderMethods[0].run();
                });

                methodsBox.addView(card);
            }

            confirmBtn.setText("تأكيد وإتمام الشراء (" + localStore.formatPrice(totalUsd) + ") ⚡");
        };

        btnMinus.setOnClickListener(v -> {
            if (qty[0] > 1) {
                qty[0] -= 1;
                qtyValTv.setText(String.valueOf(qty[0]));
                renderMethods[0].run();
            }
        });
        btnPlus.setOnClickListener(v -> {
            qty[0] += 1;
            qtyValTv.setText(String.valueOf(qty[0]));
            renderMethods[0].run();
        });

        renderMethods[0].run();

        ProgressBar submitProgress = new ProgressBar(this);
        submitProgress.setVisibility(View.GONE);
        LinearLayout.LayoutParams spLp = new LinearLayout.LayoutParams(dp(28), dp(28));
        spLp.gravity = Gravity.CENTER_HORIZONTAL;
        spLp.topMargin = dp(8);
        submitProgress.setLayoutParams(spLp);
        root.addView(submitProgress);
        root.addView(confirmBtn);

        confirmBtn.setOnClickListener(v -> {
            if (selectedOpt[0] == null || selectedOpt[0].isUnavailable) {
                Toast.makeText(this, "يرجى اختيار وسيلة دفع متاحة", Toast.LENGTH_SHORT).show();
                return;
            }

            JSONObject customerInputs = new JSONObject();
            String firstInputVal = "";
            if (product.formFields != null && !product.formFields.isEmpty()) {
                for (FormFieldItem f : product.formFields) {
                    View fv = dynamicFieldViews.get(f.name);
                    String val = "";
                    if (fv instanceof EditText) {
                        CharSequence cs = ((EditText) fv).getText();
                        val = cs != null ? cs.toString().trim() : "";
                    } else if (fv instanceof Spinner) {
                        Object sel = ((Spinner) fv).getSelectedItem();
                        val = sel != null ? sel.toString().trim() : "";
                    }
                    if (f.required && val.isEmpty()) {
                        Toast.makeText(this, "يرجى تعبئة الحقل المطلوب: " + f.label, Toast.LENGTH_LONG).show();
                        return;
                    }
                    if (!val.isEmpty()) {
                        try {
                            customerInputs.put(f.name, val);
                        } catch (Exception ignored) {}
                        if (firstInputVal.isEmpty()) firstInputVal = val;
                    }
                }
            } else if (fallbackNoteInput != null && fallbackNoteInput.getText() != null) {
                firstInputVal = fallbackNoteInput.getText().toString().trim();
            }

            submitProgress.setVisibility(View.VISIBLE);
            confirmBtn.setEnabled(false);

            final PayOption chosen = selectedOpt[0];
            final String finalCustomVal = firstInputVal;
            submitNativeOrder(sheet, submitProgress, confirmBtn, chosen, qty[0], finalCustomVal, customerInputs);
        });

        sheet.setContentView(outer);
        sheet.show();
    }

    private void submitNativeOrder(
            BottomSheetDialog checkoutSheet,
            ProgressBar progress,
            Button confirmBtn,
            PayOption chosen,
            int quantity,
            String customInput,
            JSONObject customerInputs
    ) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("product_id", product.id);
            if (selectedVariant != null) {
                payload.put("variant_id", selectedVariant.id);
            }
            payload.put("quantity", quantity);
            payload.put("payment_method", chosen.method);
            payload.put("currency_code", chosen.currency);
            payload.put("custom_input", customInput);
            if (customerInputs != null && customerInputs.length() > 0) {
                payload.put("customer_inputs", customerInputs);
            }

            repo.postJson(ORDER_API_URL, payload, (code, json, err) -> {
                progress.setVisibility(View.GONE);
                confirmBtn.setEnabled(true);

                if (code == 401 || (json != null && json.optBoolean("requires_auth", false))) {
                    checkoutSheet.dismiss();
                    NativeAuthHelper.showLoginSheet(this, repo, localStore, cachedGoogleLoginUrl, authData -> {
                        prefetchWalletAndGateways();
                        openLuxuryCheckoutBottomSheet();
                    });
                    return;
                }

                if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                    checkoutSheet.dismiss();
                    String payMode = json.optString("payment_mode", "wallet");
                    String orderId = json.optString("order_id", "");
                    String orderNumber = json.optString("order_number", orderId);

                    if ("mtn_native".equals(payMode)) {
                        int invNum = json.optInt("mtn_invoice_number", 0);
                        double sypAmt = json.optDouble("syp_amount", 0.0);
                        String eq = json.optString("mtn_equation", "");
                        JSONArray phones = json.optJSONArray("saved_mtn_phones");
                        NativeMtnDialogHelper.show(
                                ProductDetailActivity.this,
                                repo,
                                invNum,
                                sypAmt,
                                eq,
                                phones,
                                chosen.logoUrl,
                                confirmJson -> showOrderCompletedDialog(
                                        confirmJson.optString("order_number", orderNumber),
                                        confirmJson.optJSONObject("fulfillment")
                                )
                        );
                        return;
                    }

                    String paymentUrl = json.optString("payment_url", "");
                    if (!paymentUrl.isEmpty()) {
                        if (MainActivity.tryLaunchNativeShamCashAppOnly(ProductDetailActivity.this, paymentUrl)) {
                            String statusPage = !orderId.isEmpty()
                                    ? (CatalogRepository.DOMAIN + "/payments/status/?type=order&id=" + Uri.encode(orderId))
                                    : (CatalogRepository.DOMAIN + "/dashboard/orders/");
                            openUrlInMainApp(statusPage);
                        } else {
                            openUrlInMainApp(paymentUrl);
                        }
                    } else {
                        prefetchWalletAndGateways();
                        showOrderCompletedDialog(orderNumber, json.optJSONObject("fulfillment"));
                    }
                    return;
                }

                boolean insufficient = json != null && json.optBoolean("insufficient_balance", false);
                String errMsg = json != null
                        ? json.optString("message", json.optString("error", "تعذر إتمام الطلب"))
                        : (err != null ? err : "تعذر الاتصال بالخادم");

                if (insufficient) {
                    new MaterialAlertDialogBuilder(this)
                            .setTitle("💳 رصيد المحفظة غير كافٍ")
                            .setMessage(errMsg)
                            .setPositiveButton("شحن المحفظة الآن ⚡", (d, w) -> {
                                checkoutSheet.dismiss();
                                startActivity(new Intent(this, NativePaymentActivity.class));
                            })
                            .setNegativeButton("اختيار بوابة مباشرة", (d, w) -> d.dismiss())
                            .show();
                } else {
                    new MaterialAlertDialogBuilder(this)
                            .setTitle("تنبيه حول الطلب")
                            .setMessage(errMsg)
                            .setPositiveButton("حسناً", (d, w) -> d.dismiss())
                            .show();
                }
            });
        } catch (Exception e) {
            progress.setVisibility(View.GONE);
            confirmBtn.setEnabled(true);
        }
    }

    private void showOrderCompletedDialog(String orderNumber, JSONObject fulfillment) {
        StringBuilder msg = new StringBuilder();
        msg.append("تم تأكيد وتنفيذ طلبك بنجاح!\nرقم الطلب: #").append(orderNumber);

        final List<String> codesToCopy = new ArrayList<>();
        if (fulfillment != null && fulfillment.length() > 0) {
            msg.append("\n\n🎁 بيانات التسليم الفوري:");
            Iterator<String> keys = fulfillment.keys();
            while (keys.hasNext()) {
                String k = keys.next();
                String v = fulfillment.optString(k, "");
                if (!v.isEmpty()) {
                    msg.append("\n• ").append(k).append(": ").append(v);
                    codesToCopy.add(v);
                }
            }
        }

        MaterialAlertDialogBuilder builder = new MaterialAlertDialogBuilder(this)
                .setTitle("✓ تم الشراء بنجاح ⚡")
                .setMessage(msg.toString())
                .setPositiveButton("عرض طلباتي 📦", (d, w) -> openNativeOrdersInMainApp())
                .setNegativeButton("إغلاق", (d, w) -> d.dismiss());

        if (!codesToCopy.isEmpty()) {
            builder.setNeutralButton("نسخ الكود 📋", (d, w) -> {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) {
                    cm.setPrimaryClip(ClipData.newPlainText("كود رقميات", android.text.TextUtils.join("\n", codesToCopy)));
                    Toast.makeText(this, "تم نسخ الكود بنجاح!", Toast.LENGTH_SHORT).show();
                }
            });
        }
        builder.show();
    }

    private void openNativeOrdersInMainApp() {
        Intent result = new Intent();
        result.putExtra(EXTRA_OPEN_NATIVE_ORDERS, true);
        setResult(RESULT_OK, result);
        finish();
    }

    private void openUrlInMainApp(String url) {
        Intent result = new Intent();
        result.putExtra(EXTRA_OPEN_URL, url);
        setResult(RESULT_OK, result);
        finish();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshDisplayedPrices();
        prefetchWalletAndGateways();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (connectivityHelper != null) {
            connectivityHelper.stopMonitoring();
        }
    }
}
