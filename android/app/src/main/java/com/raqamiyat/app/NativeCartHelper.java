package com.raqamiyat.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.bumptech.glide.Glide;
import com.google.android.material.bottomsheet.BottomSheetDialog;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.model.CartItem;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * 100% Native Shopping Cart BottomSheet with live USD/SYP pricing and instant Wallet Checkout.
 */
public class NativeCartHelper {

    public interface CartUpdateCallback {
        void onCartChanged();
        void onOrderCompleted(String orderNumber);
    }

    private static int dp(Activity ctx, int val) {
        return Math.round(val * ctx.getResources().getDisplayMetrics().density);
    }

    public static void showCartSheet(
            Activity activity,
            CatalogRepository repo,
            RaqamiyatLocalStore localStore,
            CartUpdateCallback callback
    ) {
        if (activity == null || activity.isFinishing()) return;

        BottomSheetDialog sheet = new BottomSheetDialog(activity);
        LinearLayout root = new LinearLayout(activity);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setBackgroundColor(0xFF0B1120);
        int pad = dp(activity, 18);
        root.setPadding(pad, pad, pad, dp(activity, 24));

        // Header
        LinearLayout header = new LinearLayout(activity);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = new TextView(activity);
        title.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        title.setText("🛒 سلة مشترياتك");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(17f);
        title.setTypeface(title.getTypeface(), Typeface.BOLD);
        header.addView(title);

        TextView clearBtn = new TextView(activity);
        clearBtn.setText("إفراغ السلة ✕");
        clearBtn.setTextColor(0xFFF87171);
        clearBtn.setTextSize(12f);
        clearBtn.setPadding(dp(activity, 8), dp(activity, 4), dp(activity, 8), dp(activity, 4));
        header.addView(clearBtn);
        root.addView(header);

        ScrollView scroll = new ScrollView(activity);
        LinearLayout.LayoutParams scLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        scLp.topMargin = dp(activity, 12);
        scroll.setLayoutParams(scLp);

        LinearLayout itemsContainer = new LinearLayout(activity);
        itemsContainer.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(itemsContainer);
        root.addView(scroll);

        TextView totalView = new TextView(activity);
        totalView.setTextColor(0xFFFBBF24);
        totalView.setTextSize(16f);
        totalView.setTypeface(totalView.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams totLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        totLp.topMargin = dp(activity, 14);
        totalView.setLayoutParams(totLp);
        root.addView(totalView);

        ProgressBar progress = new ProgressBar(activity);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams prLp = new LinearLayout.LayoutParams(dp(activity, 28), dp(activity, 28));
        prLp.gravity = Gravity.CENTER_HORIZONTAL;
        prLp.topMargin = dp(activity, 8);
        progress.setLayoutParams(prLp);
        root.addView(progress);

        Button checkoutBtn = new Button(activity);
        checkoutBtn.setBackgroundResource(R.drawable.bg_button_gold);
        checkoutBtn.setText("إتمام الشراء الفوري من المحفظة ⚡");
        checkoutBtn.setTextColor(0xFF030712);
        checkoutBtn.setTextSize(14.5f);
        checkoutBtn.setAllCaps(false);
        checkoutBtn.setTypeface(checkoutBtn.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams bLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        bLp.topMargin = dp(activity, 12);
        checkoutBtn.setLayoutParams(bLp);
        root.addView(checkoutBtn);

        final Runnable[] rebuildUi = new Runnable[1];
        rebuildUi[0] = () -> {
            itemsContainer.removeAllViews();
            List<CartItem> items = localStore.getCartItems();
            if (items.isEmpty()) {
                TextView empty = new TextView(activity);
                empty.setText("سلة المشتريات فارغة حالياً.\nتصفح المنتجات وأضف ما يعجبك بلمسة واحدة!");
                empty.setTextColor(0xFF94A3B8);
                empty.setTextSize(13f);
                empty.setGravity(Gravity.CENTER);
                empty.setPadding(0, dp(activity, 28), 0, dp(activity, 28));
                itemsContainer.addView(empty);
                totalView.setVisibility(View.GONE);
                checkoutBtn.setVisibility(View.GONE);
                clearBtn.setVisibility(View.GONE);
                return;
            }
            clearBtn.setVisibility(View.VISIBLE);
            totalView.setVisibility(View.VISIBLE);
            checkoutBtn.setVisibility(View.VISIBLE);

            double sumUsd = 0.0;
            for (int idx = 0; idx < items.size(); idx++) {
                final int pos = idx;
                final CartItem it = items.get(idx);
                sumUsd += it.unitPriceUsd * it.quantity;

                LinearLayout card = new LinearLayout(activity);
                card.setOrientation(LinearLayout.HORIZONTAL);
                card.setGravity(Gravity.CENTER_VERTICAL);
                card.setBackgroundResource(R.drawable.bg_card_dark);
                card.setPadding(dp(activity, 10), dp(activity, 10), dp(activity, 10), dp(activity, 10));
                LinearLayout.LayoutParams cLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                cLp.bottomMargin = dp(activity, 8);
                card.setLayoutParams(cLp);

                ImageView img = new ImageView(activity);
                LinearLayout.LayoutParams iLp = new LinearLayout.LayoutParams(dp(activity, 46), dp(activity, 46));
                iLp.setMarginEnd(dp(activity, 10));
                img.setLayoutParams(iLp);
                img.setBackgroundResource(R.drawable.bg_logo_box);
                img.setPadding(dp(activity, 3), dp(activity, 3), dp(activity, 3), dp(activity, 3));
                if (!it.imageUrl.isEmpty()) {
                    Glide.with(activity).load(it.imageUrl).placeholder(R.mipmap.ic_launcher).into(img);
                } else {
                    img.setImageResource(R.mipmap.ic_launcher);
                }
                card.addView(img);

                LinearLayout info = new LinearLayout(activity);
                info.setOrientation(LinearLayout.VERTICAL);
                info.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

                TextView pName = new TextView(activity);
                pName.setText(it.productName + (!it.variantName.isEmpty() && !it.variantName.equals(it.productName) ? " (" + it.variantName + ")" : ""));
                pName.setTextColor(0xFFFFFFFF);
                pName.setTextSize(12.5f);
                pName.setTypeface(pName.getTypeface(), Typeface.BOLD);
                pName.setMaxLines(2);
                info.addView(pName);

                TextView pPrice = new TextView(activity);
                pPrice.setText(localStore.formatPrice(it.unitPriceUsd * it.quantity));
                pPrice.setTextColor(0xFFFBBF24);
                pPrice.setTextSize(12f);
                pPrice.setTypeface(pPrice.getTypeface(), Typeface.BOLD);
                info.addView(pPrice);
                card.addView(info);

                // Qty controls
                LinearLayout qtyRow = new LinearLayout(activity);
                qtyRow.setOrientation(LinearLayout.HORIZONTAL);
                qtyRow.setGravity(Gravity.CENTER_VERTICAL);

                TextView minus = new TextView(activity);
                minus.setText("−");
                minus.setTextColor(0xFFFFFFFF);
                minus.setTextSize(15f);
                minus.setGravity(Gravity.CENTER);
                minus.setBackgroundResource(R.drawable.bg_chip_unselected);
                minus.setLayoutParams(new LinearLayout.LayoutParams(dp(activity, 28), dp(activity, 28)));
                minus.setOnClickListener(v -> {
                    List<CartItem> list = localStore.getCartItems();
                    if (pos < list.size()) {
                        if (list.get(pos).quantity > 1) {
                            list.get(pos).quantity -= 1;
                        } else {
                            list.remove(pos);
                        }
                        localStore.saveCartItems(list);
                        if (callback != null) callback.onCartChanged();
                        rebuildUi[0].run();
                    }
                });
                qtyRow.addView(minus);

                TextView qtyTv = new TextView(activity);
                qtyTv.setText(String.valueOf(it.quantity));
                qtyTv.setTextColor(0xFFFFFFFF);
                qtyTv.setTextSize(13f);
                qtyTv.setTypeface(qtyTv.getTypeface(), Typeface.BOLD);
                qtyTv.setPadding(dp(activity, 10), 0, dp(activity, 10), 0);
                qtyRow.addView(qtyTv);

                TextView plus = new TextView(activity);
                plus.setText("+");
                plus.setTextColor(0xFF22D3EE);
                plus.setTextSize(15f);
                plus.setGravity(Gravity.CENTER);
                plus.setBackgroundResource(R.drawable.bg_chip_unselected);
                plus.setLayoutParams(new LinearLayout.LayoutParams(dp(activity, 28), dp(activity, 28)));
                plus.setOnClickListener(v -> {
                    List<CartItem> list = localStore.getCartItems();
                    if (pos < list.size()) {
                        list.get(pos).quantity += 1;
                        localStore.saveCartItems(list);
                        if (callback != null) callback.onCartChanged();
                        rebuildUi[0].run();
                    }
                });
                qtyRow.addView(plus);
                card.addView(qtyRow);

                itemsContainer.addView(card);
            }

            totalView.setText("الإجمالي الكلي: " + localStore.formatPrice(sumUsd) + "  (" + localStore.formatSecondaryPrice(sumUsd) + ")");
        };

        clearBtn.setOnClickListener(v -> {
            localStore.clearCart();
            if (callback != null) callback.onCartChanged();
            rebuildUi[0].run();
        });

        checkoutBtn.setOnClickListener(v -> {
            List<CartItem> items = localStore.getCartItems();
            if (items.isEmpty()) return;
            progress.setVisibility(View.VISIBLE);
            checkoutBtn.setEnabled(false);
            try {
                JSONObject payload = new JSONObject();
                payload.put("payment_method", "wallet");
                payload.put("currency_code", localStore.getPreferredCurrency());
                JSONArray arr = new JSONArray();
                for (CartItem it : items) {
                    JSONObject o = new JSONObject();
                    o.put("product_id", it.productId);
                    o.put("variant_id", it.variantId);
                    o.put("quantity", it.quantity);
                    o.put("custom_input", it.customInput);
                    arr.put(o);
                }
                payload.put("cart_items", arr);

                repo.postJson(CatalogRepository.DOMAIN + "/api/app/orders/create/", payload, (code, json, err) -> {
                    progress.setVisibility(View.GONE);
                    checkoutBtn.setEnabled(true);
                    if (code == 401 || (json != null && json.optBoolean("requires_auth", false))) {
                        sheet.dismiss();
                        NativeAuthHelper.showLoginSheet(activity, repo, localStore, "", auth -> showCartSheet(activity, repo, localStore, callback));
                        return;
                    }
                    if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                        localStore.clearCart();
                        if (callback != null) {
                            callback.onCartChanged();
                            callback.onOrderCompleted(json.optString("order_number", ""));
                        }
                        sheet.dismiss();
                        Toast.makeText(activity, "✓ " + json.optString("message", "تم تأكيد طلبك بنجاح!"), Toast.LENGTH_LONG).show();
                        return;
                    }
                    boolean insuff = json != null && json.optBoolean("insufficient_balance", false);
                    String msg = json != null ? json.optString("message", "تعذر إتمام الطلب") : (err != null ? err : "خطأ في الاتصال");
                    if (insuff) {
                        new MaterialAlertDialogBuilder(activity)
                                .setTitle("💳 رصيد المحفظة غير كافٍ")
                                .setMessage(msg)
                                .setPositiveButton("شحن المحفظة الآن ⚡", (d, w) -> {
                                    sheet.dismiss();
                                    activity.startActivity(new Intent(activity, NativePaymentActivity.class));
                                })
                                .setNegativeButton("إلغاء", (d, w) -> d.dismiss())
                                .show();
                    } else {
                        Toast.makeText(activity, msg, Toast.LENGTH_LONG).show();
                    }
                });
            } catch (Exception ignored) {
                progress.setVisibility(View.GONE);
                checkoutBtn.setEnabled(true);
            }
        });

        rebuildUi[0].run();
        sheet.setContentView(root);
        sheet.show();
    }
}
