package com.raqamiyat.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.browser.customtabs.CustomTabsIntent;

import com.google.android.material.bottomsheet.BottomSheetDialog;

import org.json.JSONObject;

/**
 * Luxury Native Sign-In BottomSheet with rounded 28dp sheet, drag handle, and spring physics.
 */
public class NativeAuthHelper {

    public interface OnAuthSuccessListener {
        void onLoggedIn(JSONObject authData);
    }

    private static int dp(Activity ctx, int val) {
        return Math.round(val * ctx.getResources().getDisplayMetrics().density);
    }

    public static void showLoginSheet(
            Activity activity,
            CatalogRepository repo,
            RaqamiyatLocalStore localStore,
            String cachedGoogleUrl,
            OnAuthSuccessListener listener
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

        LinearLayout top = new LinearLayout(activity);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);

        ImageView icon = new ImageView(activity);
        icon.setImageResource(R.mipmap.ic_launcher);
        LinearLayout.LayoutParams icLp = new LinearLayout.LayoutParams(dp(activity, 46), dp(activity, 46));
        icLp.setMarginEnd(dp(activity, 14));
        icon.setLayoutParams(icLp);
        top.addView(icon);

        LinearLayout titleCol = new LinearLayout(activity);
        titleCol.setOrientation(LinearLayout.VERTICAL);
        TextView title = new TextView(activity);
        title.setText("تسجيل الدخول إلى رقميات");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(17.5f);
        title.setTypeface(title.getTypeface(), Typeface.BOLD);
        titleCol.addView(title);

        TextView sub = new TextView(activity);
        sub.setText("مزامنة فورية لمحفظتك وطلباتك بضمان مشفر");
        sub.setTextColor(0xFF94A3B8);
        sub.setTextSize(12f);
        titleCol.addView(sub);
        top.addView(titleCol);
        root.addView(top);

        // Google Fast Sign-In CTA
        TextView btnGoogle = new TextView(activity);
        btnGoogle.setBackgroundResource(R.drawable.bg_button_cyan);
        btnGoogle.setGravity(Gravity.CENTER);
        btnGoogle.setClickable(true);
        btnGoogle.setFocusable(true);
        btnGoogle.setText("المتابعة السريعة عبر حساب Google");
        btnGoogle.setTextColor(0xFF050811);
        btnGoogle.setTextSize(14f);
        btnGoogle.setTypeface(btnGoogle.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams gLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        gLp.topMargin = dp(activity, 18);
        btnGoogle.setLayoutParams(gLp);
        UiMotion.attachPressScale(btnGoogle);
        btnGoogle.setOnClickListener(v -> {
            UiMotion.hapticTap(v);
            sheet.dismiss();
            if (cachedGoogleUrl != null && !cachedGoogleUrl.isEmpty()) {
                launchGoogleAuthTab(activity, cachedGoogleUrl);
            } else {
                repo.getJson(CatalogRepository.SESSION_API_URL + "?from_app=1", (code, json, err) -> {
                    String gUrl = json != null ? json.optString("google_login_url", "") : "";
                    if (gUrl.isEmpty()) {
                        gUrl = CatalogRepository.DOMAIN + "/accounts/google/login/?process=login&from_app=1";
                    }
                    launchGoogleAuthTab(activity, gUrl);
                });
            }
        });
        root.addView(btnGoogle);

        TextView divider = new TextView(activity);
        divider.setText("أو عبر البريد الإلكتروني / اسم المستخدم");
        divider.setTextColor(0xFF64748B);
        divider.setTextSize(11.5f);
        divider.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams dLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        dLp.topMargin = dp(activity, 16);
        dLp.bottomMargin = dp(activity, 12);
        divider.setLayoutParams(dLp);
        root.addView(divider);

        EditText idInput = new EditText(activity);
        idInput.setBackgroundResource(R.drawable.bg_input_dark);
        idInput.setHint("البريد الإلكتروني أو اسم المستخدم");
        idInput.setHintTextColor(0xFF64748B);
        idInput.setTextColor(0xFFFFFFFF);
        idInput.setSingleLine(true);
        idInput.setPadding(dp(activity, 16), dp(activity, 12), dp(activity, 16), dp(activity, 12));
        LinearLayout.LayoutParams inLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        idInput.setLayoutParams(inLp);
        root.addView(idInput);

        EditText passInput = new EditText(activity);
        passInput.setBackgroundResource(R.drawable.bg_input_dark);
        passInput.setHint("كلمة المرور");
        passInput.setHintTextColor(0xFF64748B);
        passInput.setTextColor(0xFFFFFFFF);
        passInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        passInput.setSingleLine(true);
        passInput.setPadding(dp(activity, 16), dp(activity, 12), dp(activity, 16), dp(activity, 12));
        LinearLayout.LayoutParams pwLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 50));
        pwLp.topMargin = dp(activity, 10);
        passInput.setLayoutParams(pwLp);
        root.addView(passInput);

        TextView errText = new TextView(activity);
        errText.setTextColor(0xFFF87171);
        errText.setTextSize(12f);
        errText.setVisibility(View.GONE);
        LinearLayout.LayoutParams eLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        eLp.topMargin = dp(activity, 8);
        errText.setLayoutParams(eLp);
        root.addView(errText);

        ProgressBar progress = new ProgressBar(activity);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams pLp = new LinearLayout.LayoutParams(dp(activity, 28), dp(activity, 28));
        pLp.gravity = Gravity.CENTER_HORIZONTAL;
        pLp.topMargin = dp(activity, 8);
        progress.setLayoutParams(pLp);
        root.addView(progress);

        TextView btnLogin = new TextView(activity);
        btnLogin.setBackgroundResource(R.drawable.bg_button_gold);
        btnLogin.setGravity(Gravity.CENTER);
        btnLogin.setClickable(true);
        btnLogin.setFocusable(true);
        btnLogin.setText("تسجيل الدخول الآن");
        btnLogin.setTextColor(0xFF050811);
        btnLogin.setTextSize(15f);
        btnLogin.setTypeface(btnLogin.getTypeface(), Typeface.BOLD);
        LinearLayout.LayoutParams lLp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 52));
        lLp.topMargin = dp(activity, 16);
        btnLogin.setLayoutParams(lLp);
        UiMotion.attachPressScale(btnLogin);

        btnLogin.setOnClickListener(v -> {
            UiMotion.hapticTap(v);
            String ident = idInput.getText() != null ? idInput.getText().toString().trim() : "";
            String pwd = passInput.getText() != null ? passInput.getText().toString() : "";
            if (ident.isEmpty() || pwd.isEmpty()) {
                errText.setText("يرجى إدخال البريد/اسم المستخدم وكلمة المرور.");
                errText.setVisibility(View.VISIBLE);
                return;
            }
            errText.setVisibility(View.GONE);
            progress.setVisibility(View.VISIBLE);
            btnLogin.setEnabled(false);
            try {
                JSONObject payload = new JSONObject();
                payload.put("identifier", ident);
                payload.put("password", pwd);
                repo.postJson(CatalogRepository.LOGIN_API_URL, payload, (code, json, err) -> {
                    progress.setVisibility(View.GONE);
                    btnLogin.setEnabled(true);
                    if (code == 200 && json != null && "success".equals(json.optString("status"))) {
                        String tok = json.optString("app_auth_token", "");
                        if (!tok.isEmpty()) localStore.saveAppAuthToken(tok);
                        localStore.saveQuickAccountSnapshot(
                                json.optDouble("available_balance_usd", 0.0),
                                json.optString("full_name", ""),
                                json.optString("email", "")
                        );
                        Toast.makeText(activity, "تم تسجيل الدخول بنجاح", Toast.LENGTH_SHORT).show();
                        sheet.dismiss();
                        if (listener != null) listener.onLoggedIn(json);
                    } else {
                        errText.setText(json != null ? json.optString("message", "بيانات الدخول غير صحيحة") : (err != null ? err : "تعذر الاتصال"));
                        errText.setVisibility(View.VISIBLE);
                    }
                });
            } catch (Exception ignored) {
                progress.setVisibility(View.GONE);
                btnLogin.setEnabled(true);
            }
        });
        root.addView(btnLogin);

        TextView registerLink = new TextView(activity);
        registerLink.setText("ليس لديك حساب؟ إنشاء حساب جديد في رقميات");
        registerLink.setTextColor(0xFF22D3EE);
        registerLink.setTextSize(12.5f);
        registerLink.setTypeface(registerLink.getTypeface(), Typeface.BOLD);
        registerLink.setGravity(Gravity.CENTER);
        registerLink.setPadding(0, dp(activity, 16), 0, dp(activity, 4));
        registerLink.setOnClickListener(v -> {
            sheet.dismiss();
            Intent i = new Intent(activity, MainActivity.class);
            i.putExtra(ProductDetailActivity.EXTRA_OPEN_URL, CatalogRepository.DOMAIN + "/auth/register/");
            i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            activity.startActivity(i);
        });
        root.addView(registerLink);

        sheet.setContentView(root);
        sheet.show();
    }

    public static void launchGoogleAuthTab(Activity activity, String url) {
        try {
            CustomTabsIntent customTabsIntent = new CustomTabsIntent.Builder()
                    .setShowTitle(true)
                    .setToolbarColor(0xFF050811)
                    .build();
            try {
                activity.getPackageManager().getPackageInfo("com.android.chrome", 0);
                customTabsIntent.intent.setPackage("com.android.chrome");
            } catch (Exception ignored) {
            }
            customTabsIntent.launchUrl(activity, Uri.parse(url));
        } catch (Exception e) {
            try {
                activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            } catch (Exception ignored) {
            }
        }
    }
}
