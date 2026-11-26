package com.raqamiyat.app;

import android.app.Activity;
import android.graphics.Typeface;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
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
 * Fintech-Grade Cash Mobile (MTN Syria) Phone + SMS OTP BottomSheet with rounded glass surface & spring physics.
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
        root.setBackgroundResource(R.drawable.bg_bottom_sheet);
        int pad = dp(activity, 20);
        root.setPadding(pad, dp(activity, 12), pad, dp(activity, 28));

        root.addView(UiMotion.createDragHandle(activity));

        // Header Row with Cash Mobile Logo
        LinearLayout header = new LinearLayout(activity);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout logoBox = new LinearLayout(activity);
        logoBox.setBackgroundResource(R.drawable.bg_logo_box);
        logoBox.setGravity(Gravity.CENTER);
        int boxSz = dp(activity, 50);
        LinearLayout.LayoutParams boxLp = new LinearLayout.LayoutParams(boxSz, boxSz);
        boxLp.setMarginEnd(dp(activity, 14));
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
        title.setText("الدفع المباشر — كاش موبايل MTN");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(16.5f);
        title.setTypeface(title.getTypeface(), Typeface.BOLD);
        titleCol.addView(title);

        TextView invBadge = new TextView(activity);
        invBadge.setText("فاتورة #" + invoiceNumber + " • صالحة لمدة 10 دقائق");
        invBadge.setTextColor(0xFF94A3B8);
        invBadge.setTextSize(11.5f);
        titleCol.addView(invBadge);
        header.addView(titleCol);
        root.addView(header);

        // Summary Card
        LinearLayout summaryCard = new LinearLayout(activity);
        summaryCard.setOrientation(LinearLayout.VERTICAL);
        summaryCard.setBackgroundResource(R.drawable.bg_wallet_hero);
        LinearLayout.LayoutParams sumLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        sumLp.topMargin = dp(activity, 16);
        summaryCard.setLayoutParams(sumLp);
        summaryCard.setPadding(dp(activity, 16), dp(activity, 14), dp(activity, 16), dp(activity, 14));

        TextView amtTxt = new TextView(activity);
        amtTxt.setText("المبلغ المطلوب: " + RaqamiyatLocalStore.formatSypAmount(sypAmount));
        amtTxt.setTextColor(0xFFFDE047);
        amtTxt.setTextSize(17f);
        amtTxt.setTypeface(amtTxt.getTypeface(), Typeface.BOLD);
        summaryCard.addView(amtTxt);

        if (mtnEquation != null && !mtnEquation.isEmpty()) {
            TextView eqTxt = new TextView(activity);
            eqTxt.setText("إجمالي الخصم مع عمولة الشبكة: " + mtnEquation);
            eqTxt.setTextColor(0xFFCBD5E1);
            eqTxt.setTextSize(11.5f);
            eqTxt.setPadding(0, dp(activity, 3), 0, 0);
            summaryCard.addView(eqTxt);
        }
        root.addView(summaryCard);

        // Step 1: Phone Input
        LinearLayout stepPhone = new LinearLayout(activity);
        stepPhone.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams spLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        spLp.topMargin = dp(activity, 16);
        stepPhone.setLayoutParams(spLp);

        TextView phoneLabel = new TextView(activity);
        phoneLabel.setText("رقم هاتف كاش موبايل MTN (10 أرقام):");
        phoneLabel.setTextColor(0xFFE2E8F0);
        phoneLabel.setTextSize(12.5f);
        phoneLabel.setTypeface(phoneLabel.getTypeface(), Typeface.BOLD);
        stepPhone.addView(phoneLabel);

        EditText phoneInput = new EditText(activity);
        phoneInput.setBackgroundResource(R.drawable.bg_input_dark);
        phoneInput.setHint("094XXXXXXX");
        phoneInput.setHintTextColor(0xFF64748B);
        phoneInput.setTextColor(0xFFFFFFFF);
        phoneInput.setInputType(InputType.TYPE_CLASS_PHONE);
        phoneInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(10)});
        phoneInput.setPadding(dp(activity, 16), dp(activity, 12), dp(activity, 16), dp(activity, 12));
        LinearLayout.LayoutParams inLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        inLp.topMargin = dp(activity, 8);
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
                chip.setText(pNum);
                chip.setTextColor(0xFF22D3EE);
                chip.setTextSize(11.5f);
                chip.setTypeface(chip.getTypeface(), Typeface.BOLD);
                chip.setBackgroundResource(R.drawable.bg_chip_unselected);
                chip.setPadding(dp(activity, 12), dp(activity, 6), dp(activity, 12), dp(activity, 6));
                LinearLayout.LayoutParams cLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                cLp.setMarginEnd(dp(activity, 6));
                chip.setLayoutParams(cLp);
                UiMotion.attachPressScale(chip);
                chip.setOnClickListener(v -> phoneInput.setText(pNum));
                savedRow.addView(chip);
                if (i == 0 && phoneInput.getText().length() == 0) {
                    phoneInput.setText(pNum);
                }
            }
            stepPhone.addView(savedRow);
        }
        root.addView(stepPhone);

        // Step 2: SMS OTP Input
        LinearLayout stepOtp = new LinearLayout(activity);
        stepOtp.setOrientation(LinearLayout.VERTICAL);
        stepOtp.setVisibility(View.GONE);
        LinearLayout.LayoutParams soLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        soLp.topMargin = dp(activity, 16);
        stepOtp.setLayoutParams(soLp);

        TextView otpLabel = new TextView(activity);
        otpLabel.setText("رمز التحقق المرسل عبر الرسالة النصية (SMS):");
        otpLabel.setTextColor(0xFF10B981);
        otpLabel.setTextSize(13f);
        otpLabel.setTypeface(otpLabel.getTypeface(), Typeface.BOLD);
        stepOtp.addView(otpLabel);

        EditText otpInput = new EditText(activity);
        otpInput.setBackgroundResource(R.drawable.bg_input_dark);
        otpInput.setHint("أدخل الرمز السري");
        otpInput.setHintTextColor(0xFF64748B);
        otpInput.setTextColor(0xFFFFFFFF);
        otpInput.setGravity(Gravity.CENTER);
        otpInput.setTextSize(18f);
        otpInput.setTypeface(otpInput.getTypeface(), Typeface.BOLD);
        otpInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        otpInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        otpInput.setPadding(dp(activity, 16), dp(activity, 12), dp(activity, 16), dp(activity, 12));
        otpInput.setLayoutParams(inLp);
        stepOtp.addView(otpInput);
        root.addView(stepOtp);

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

        // True Liquid Gold Action Button (TextView so MaterialComponents never tints it flat cyan!)
        TextView btnAction = new TextView(activity);
        btnAction.setBackgroundResource(R.drawable.bg_button_gold);
        btnAction.setGravity(Gravity.CENTER);
        btnAction.setClickable(true);
        btnAction.setFocusable(true);
        btnAction.setText("إرسال رمز التحقق SMS");
        btnAction.setTextColor(0xFF050811);
        btnAction.setTextSize(15f);
        btnAction.setTypeface(btnAction.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams btnLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 52));
        btnLp.topMargin = dp(activity, 18);
        btnAction.setLayoutParams(btnLp);
        UiMotion.attachPressScale(btnAction);
        root.addView(btnAction);

        final boolean[] isOtpStage = {false};

        btnAction.setOnClickListener(v -> {
            UiMotion.hapticTap(v);
            statusView.setVisibility(View.GONE);
            if (!isOtpStage[0]) {
                String phone = phoneInput.getText() != null ? phoneInput.getText().toString().trim() : "";
                if (phone.length() < 9) {
                    statusView.setTextColor(0xFFF87171);
                    statusView.setText("يرجى إدخال رقم هاتف MTN صحيح مكون من 10 أرقام (094XXXXXXX).");
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
                            UiMotion.revealContainer(stepOtp);
                            otpInput.requestFocus();
                            btnAction.setText("تأكيد الرمز وإتمام الدفع الآن");
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
