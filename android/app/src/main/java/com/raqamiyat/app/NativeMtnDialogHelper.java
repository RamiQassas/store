package com.raqamiyat.app;

import android.app.Activity;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import com.bumptech.glide.Glide;
import com.google.android.material.bottomsheet.BottomSheetDialog;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * 100% Native Cash Mobile (MTN Syria) Phone + SMS OTP Payment BottomSheet.
 * Works seamlessly for both Wallet Deposits and Direct Product Purchases without WebView!
 */
public class NativeMtnDialogHelper {

    public interface OnMtnCompletedListener {
        void onSuccess(JSONObject confirmResponse);
    }

    private static int dp(Activity ctx, int val) {
        return Math.round(val * ctx.getResources().getDisplayMetrics().density);
    }

    public static void show(
            Activity activity,
            CatalogRepository repo,
            int invoiceNumber,
            double sypAmount,
            String mtnEquation,
            JSONArray savedPhones,
            String logoUrl,
            OnMtnCompletedListener listener
    ) {
        if (activity == null || activity.isFinishing()) return;

        BottomSheetDialog sheet = new BottomSheetDialog(activity);
        LinearLayout root = new LinearLayout(activity);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setBackgroundColor(0xFF0B1120);
        int pad = dp(activity, 18);
        root.setPadding(pad, pad, pad, dp(activity, 24));

        // Header Row with Cash Mobile Logo
        LinearLayout header = new LinearLayout(activity);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout logoBox = new LinearLayout(activity);
        logoBox.setBackgroundResource(R.drawable.bg_logo_box);
        logoBox.setGravity(Gravity.CENTER);
        int boxSz = dp(activity, 48);
        LinearLayout.LayoutParams boxLp = new LinearLayout.LayoutParams(boxSz, boxSz);
        boxLp.setMarginEnd(dp(activity, 12));
        logoBox.setLayoutParams(boxLp);

        ImageView logoImg = new ImageView(activity);
        logoImg.setLayoutParams(new LinearLayout.LayoutParams(dp(activity, 40), dp(activity, 40)));
        logoImg.setScaleType(ImageView.ScaleType.FIT_CENTER);
        String resolvedLogo = (logoUrl != null && !logoUrl.isEmpty())
                ? logoUrl
                : (CatalogRepository.DOMAIN + "/api/app/gateway-logo/mtn_pay/");
        Glide.with(activity).load(resolvedLogo).placeholder(R.mipmap.ic_launcher).into(logoImg);
        logoBox.addView(logoImg);
        header.addView(logoBox);

        LinearLayout titleCol = new LinearLayout(activity);
        titleCol.setOrientation(LinearLayout.VERTICAL);
        titleCol.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        TextView title = new TextView(activity);
        title.setText("الدفع المباشر عبر كاش موبايل (MTN)");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(16f);
        title.setTypeface(title.getTypeface(), android.graphics.Typeface.BOLD);
        titleCol.addView(title);

        TextView invBadge = new TextView(activity);
        invBadge.setText("فاتورة رقم #" + invoiceNumber + " • صالحة لمدة 10 دقائق");
        invBadge.setTextColor(0xFF94A3B8);
        invBadge.setTextSize(11f);
        titleCol.addView(invBadge);
        header.addView(titleCol);
        root.addView(header);

        // Summary Card
        LinearLayout summaryCard = new LinearLayout(activity);
        summaryCard.setOrientation(LinearLayout.VERTICAL);
        summaryCard.setBackgroundResource(R.drawable.bg_card_dark);
        LinearLayout.LayoutParams sumLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        sumLp.topMargin = dp(activity, 14);
        summaryCard.setLayoutParams(sumLp);
        summaryCard.setPadding(dp(activity, 14), dp(activity, 12), dp(activity, 14), dp(activity, 12));

        TextView amtTxt = new TextView(activity);
        amtTxt.setText("المبلغ المطلوب: " + RaqamiyatLocalStore.formatSypAmount(sypAmount));
        amtTxt.setTextColor(0xFFFBBF24);
        amtTxt.setTextSize(16f);
        amtTxt.setTypeface(amtTxt.getTypeface(), android.graphics.Typeface.BOLD);
        summaryCard.addView(amtTxt);

        if (mtnEquation != null && !mtnEquation.isEmpty()) {
            TextView eqTxt = new TextView(activity);
            eqTxt.setText("إجمالي الخصم مع عمولة الشبكة: " + mtnEquation);
            eqTxt.setTextColor(0xFFCBD5E1);
            eqTxt.setTextSize(11f);
            summaryCard.addView(eqTxt);
        }
        root.addView(summaryCard);

        // Step 1: Phone Input Container
        LinearLayout stepPhone = new LinearLayout(activity);
        stepPhone.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams spLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        spLp.topMargin = dp(activity, 14);
        stepPhone.setLayoutParams(spLp);

        TextView phoneLabel = new TextView(activity);
        phoneLabel.setText("رقم هاتف كاش موبايل MTN (10 أرقام يبدأ بـ 094 أو 095):");
        phoneLabel.setTextColor(0xFFE2E8F0);
        phoneLabel.setTextSize(12f);
        stepPhone.addView(phoneLabel);

        EditText phoneInput = new EditText(activity);
        phoneInput.setBackgroundResource(R.drawable.bg_input_dark);
        phoneInput.setHint("094XXXXXXX");
        phoneInput.setHintTextColor(0xFF64748B);
        phoneInput.setTextColor(0xFFFFFFFF);
        phoneInput.setInputType(InputType.TYPE_CLASS_PHONE);
        phoneInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(10)});
        phoneInput.setPadding(dp(activity, 14), dp(activity, 12), dp(activity, 14), dp(activity, 12));
        LinearLayout.LayoutParams inLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 48));
        inLp.topMargin = dp(activity, 6);
        phoneInput.setLayoutParams(inLp);
        stepPhone.addView(phoneInput);

        if (savedPhones != null && savedPhones.length() > 0) {
            LinearLayout savedRow = new LinearLayout(activity);
            savedRow.setOrientation(LinearLayout.HORIZONTAL);
            LinearLayout.LayoutParams srLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            srLp.topMargin = dp(activity, 8);
            savedRow.setLayoutParams(srLp);
            for (int i = 0; i < Math.min(3, savedPhones.length()); i++) {
                final String pNum = savedPhones.optString(i, "");
                if (pNum.isEmpty()) continue;
                TextView chip = new TextView(activity);
                chip.setText("📱 " + pNum);
                chip.setTextColor(0xFF22D3EE);
                chip.setTextSize(11f);
                chip.setBackgroundResource(R.drawable.bg_chip_unselected);
                chip.setPadding(dp(activity, 10), dp(activity, 5), dp(activity, 10), dp(activity, 5));
                LinearLayout.LayoutParams cLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                cLp.setMarginEnd(dp(activity, 6));
                chip.setLayoutParams(cLp);
                chip.setOnClickListener(v -> phoneInput.setText(pNum));
                savedRow.addView(chip);
                if (i == 0 && phoneInput.getText().length() == 0) {
                    phoneInput.setText(pNum);
                }
            }
            stepPhone.addView(savedRow);
        }
        root.addView(stepPhone);

        // Step 2: SMS OTP Input Container (Hidden initially)
        LinearLayout stepOtp = new LinearLayout(activity);
        stepOtp.setOrientation(LinearLayout.VERTICAL);
        stepOtp.setVisibility(View.GONE);
        LinearLayout.LayoutParams soLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        soLp.topMargin = dp(activity, 14);
        stepOtp.setLayoutParams(soLp);

        TextView otpLabel = new TextView(activity);
        otpLabel.setText("أدخل رمز التأكيد (SMS OTP) المرسل إلى هاتفك:");
        otpLabel.setTextColor(0xFF10B981);
        otpLabel.setTextSize(13f);
        otpLabel.setTypeface(otpLabel.getTypeface(), android.graphics.Typeface.BOLD);
        stepOtp.addView(otpLabel);

        EditText otpInput = new EditText(activity);
        otpInput.setBackgroundResource(R.drawable.bg_input_dark);
        otpInput.setHint("أدخل الرمز السري من الرسالة النصية");
        otpInput.setHintTextColor(0xFF64748B);
        otpInput.setTextColor(0xFFFFFFFF);
        otpInput.setGravity(Gravity.CENTER);
        otpInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        otpInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        otpInput.setPadding(dp(activity, 14), dp(activity, 12), dp(activity, 14), dp(activity, 12));
        otpInput.setLayoutParams(inLp);
        stepOtp.addView(otpInput);
        root.addView(stepOtp);

        // Status & Progress
        TextView statusView = new TextView(activity);
        statusView.setTextSize(12f);
        statusView.setTextColor(0xFFF87171);
        statusView.setVisibility(View.GONE);
        LinearLayout.LayoutParams stLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        stLp.topMargin = dp(activity, 10);
        statusView.setLayoutParams(stLp);
        root.addView(statusView);

        ProgressBar progress = new ProgressBar(activity);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams prLp = new LinearLayout.LayoutParams(dp(activity, 28), dp(activity, 28));
        prLp.gravity = Gravity.CENTER_HORIZONTAL;
        prLp.topMargin = dp(activity, 8);
        progress.setLayoutParams(prLp);
        root.addView(progress);

        // Primary Action Button
        Button btnAction = new Button(activity);
        btnAction.setBackgroundResource(R.drawable.bg_button_gold);
        btnAction.setText("إرسال رمز التحقق SMS ⚡");
        btnAction.setTextColor(0xFF030712);
        btnAction.setTextSize(14f);
        btnAction.setTypeface(btnAction.getTypeface(), android.graphics.Typeface.BOLD);
        LinearLayout.LayoutParams btnLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        btnLp.topMargin = dp(activity, 16);
        btnAction.setLayoutParams(btnLp);
        root.addView(btnAction);

        final boolean[] isOtpStage = {false};

        btnAction.setOnClickListener(v -> {
            statusView.setVisibility(View.GONE);
            if (!isOtpStage[0]) {
                String phone = phoneInput.getText() != null ? phoneInput.getText().toString().trim() : "";
                if (phone.length() < 9) {
                    statusView.setTextColor(0xFFF87171);
                    statusView.setText("يرجى إدخال رقم هاتف MTN صحيح مكون من 10 أرقام (مثال: 094XXXXXXX).");
                    statusView.setVisibility(View.VISIBLE);
                    return;
                }
                progress.setVisibility(View.VISIBLE);
                btnAction.setEnabled(false);
                try {
                    JSONObject body = new JSONObject();
                    body.put("invoice_number", invoiceNumber);
                    body.put("phone", phone);
                    repo.postJson(CatalogRepository.DOMAIN + "/api/app/payments/mtn/initiate/", body, (code, json, err) -> {
                        progress.setVisibility(View.GONE);
                        btnAction.setEnabled(true);
                        if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                            isOtpStage[0] = true;
                            phoneInput.setEnabled(false);
                            stepOtp.setVisibility(View.VISIBLE);
                            otpInput.requestFocus();
                            btnAction.setText("تأكيد الرمز وإتمام الدفع الآن ✓");
                            statusView.setTextColor(0xFF10B981);
                            statusView.setText(json.optString("message", "تم إرسال رمز التحقق بنجاح."));
                            statusView.setVisibility(View.VISIBLE);
                        } else {
                            statusView.setTextColor(0xFFF87171);
                            statusView.setText(json != null ? json.optString("message", "تعذر إرسال رمز التحقق") : (err != null ? err : "خطأ في الاتصال"));
                            statusView.setVisibility(View.VISIBLE);
                        }
                    });
                } catch (Exception ignored) {
                    progress.setVisibility(View.GONE);
                    btnAction.setEnabled(true);
                }
            } else {
                String otp = otpInput.getText() != null ? otpInput.getText().toString().trim() : "";
                if (otp.length() < 4) {
                    statusView.setTextColor(0xFFF87171);
                    statusView.setText("يرجى إدخال رمز التأكيد المرسل في الرسالة النصية.");
                    statusView.setVisibility(View.VISIBLE);
                    return;
                }
                progress.setVisibility(View.VISIBLE);
                btnAction.setEnabled(false);
                try {
                    JSONObject body = new JSONObject();
                    body.put("invoice_number", invoiceNumber);
                    body.put("code", otp);
                    repo.postJson(CatalogRepository.DOMAIN + "/api/app/payments/mtn/confirm/", body, (code, json, err) -> {
                        progress.setVisibility(View.GONE);
                        btnAction.setEnabled(true);
                        if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                            sheet.dismiss();
                            if (listener != null) {
                                listener.onSuccess(json);
                            }
                        } else {
                            statusView.setTextColor(0xFFF87171);
                            statusView.setText(json != null ? json.optString("message", "رمز التحقق غير صحيح") : (err != null ? err : "فشل التحقق"));
                            statusView.setVisibility(View.VISIBLE);
                        }
                    });
                } catch (Exception ignored) {
                    progress.setVisibility(View.GONE);
                    btnAction.setEnabled(true);
                }
            }
        });

        sheet.setContentView(root);
        sheet.show();
    }
}
