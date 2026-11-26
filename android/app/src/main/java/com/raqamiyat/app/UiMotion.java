package com.raqamiyat.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.view.animation.OvershootInterpolator;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * World-Class Tactile Motion, Spring Physics, Staggered Cascades & Micro-Interactions Engine.
 */
public final class UiMotion {

    private static final OvershootInterpolator SPRING = new OvershootInterpolator(1.85f);
    private static final DecelerateInterpolator SMOOTH_OUT = new DecelerateInterpolator(1.6f);

    private UiMotion() {}

    public static int dp(View v, int val) {
        return Math.round(val * v.getResources().getDisplayMetrics().density);
    }

    @SuppressLint("ClickableViewAccessibility")
    public static void attachPressScale(final View view) {
        if (view == null) return;
        view.setOnTouchListener((v, event) -> {
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN) {
                v.animate().cancel();
                v.animate()
                        .scaleX(0.955f)
                        .scaleY(0.955f)
                        .setDuration(95)
                        .setInterpolator(SMOOTH_OUT)
                        .start();
            } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                v.animate().cancel();
                v.animate()
                        .scaleX(1.0f)
                        .scaleY(1.0f)
                        .setDuration(230)
                        .setInterpolator(SPRING)
                        .start();
            }
            return false;
        });
    }

    public static void hapticTap(View v) {
        if (v != null) {
            try {
                v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
            } catch (Exception ignored) {
            }
        }
    }

    public static void animateCardEntrance(final View view, int position) {
        if (view == null) return;
        float offsetPx = dp(view, 24);
        view.setAlpha(0f);
        view.setTranslationY(offsetPx);
        view.setScaleX(0.97f);
        view.setScaleY(0.97f);
        long delay = Math.min((position % 8) * 38L, 220L);
        view.animate()
                .alpha(1f)
                .translationY(0f)
                .scaleX(1f)
                .scaleY(1f)
                .setStartDelay(delay)
                .setDuration(300)
                .setInterpolator(SMOOTH_OUT)
                .start();
    }

    public static void revealContainer(final View target, View... toHide) {
        if (toHide != null) {
            for (View h : toHide) {
                if (h != null && h != target) {
                    h.setVisibility(View.GONE);
                }
            }
        }
        if (target == null) return;
        if (target.getVisibility() == View.VISIBLE && target.getAlpha() == 1f) {
            return;
        }
        target.setAlpha(0f);
        target.setTranslationY(dp(target, 12));
        target.setVisibility(View.VISIBLE);
        target.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(220)
                .setInterpolator(SMOOTH_OUT)
                .start();
    }

    public static void pulseTextChange(final TextView tv, final String newText) {
        if (tv == null) return;
        tv.animate()
                .scaleX(0.92f)
                .scaleY(0.92f)
                .alpha(0.6f)
                .setDuration(85)
                .withEndAction(() -> {
                    tv.setText(newText);
                    tv.animate()
                            .scaleX(1f)
                            .scaleY(1f)
                            .alpha(1f)
                            .setDuration(190)
                            .setInterpolator(SPRING)
                            .start();
                })
                .start();
    }

    public static View createDragHandle(Activity ctx) {
        View handle = new View(ctx);
        handle.setBackgroundResource(R.drawable.bg_drag_handle);
        int w = Math.round(42 * ctx.getResources().getDisplayMetrics().density);
        int h = Math.round(4 * ctx.getResources().getDisplayMetrics().density);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(w, h);
        lp.gravity = Gravity.CENTER_HORIZONTAL;
        lp.bottomMargin = Math.round(16 * ctx.getResources().getDisplayMetrics().density);
        handle.setLayoutParams(lp);
        return handle;
    }

    public static void applySlideTransition(Activity activity) {
        if (activity != null) {
            activity.overridePendingTransition(R.anim.slide_in_enter, R.anim.slide_out_exit);
        }
    }
}
