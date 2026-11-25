package com.raqamiyat.app.model;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class GatewayItem implements Serializable {
    public final String id;
    public final String paymentMethodId;
    public final String code;
    public final String provider;
    public final String type;
    public final String name;
    public final String subtitle;
    public final String logoUrl;
    public final List<String> currencies;
    public final boolean forDeposit;
    public final boolean forCheckout;
    public final double minUsd;
    public final double maxUsd;
    public final double minSyp;
    public final double maxSyp;
    public final double feePercent;
    public final double feeFixed;
    public final boolean isComingSoon;
    public final boolean isMaintenanceMode;
    public final boolean isUnavailable;
    public final String badgeLabel;
    public final String unavailableMessage;
    public final String instructions;
    public final String staticRowsJson;
    public final String formFieldsJson;
    public final String qrUrl;

    public GatewayItem(
            String id,
            String paymentMethodId,
            String code,
            String provider,
            String type,
            String name,
            String subtitle,
            String logoUrl,
            List<String> currencies,
            boolean forDeposit,
            boolean forCheckout,
            double minUsd,
            double maxUsd,
            double minSyp,
            double maxSyp,
            double feePercent,
            double feeFixed,
            boolean isComingSoon,
            boolean isMaintenanceMode,
            boolean isUnavailable,
            String badgeLabel,
            String unavailableMessage,
            String instructions,
            String staticRowsJson,
            String formFieldsJson,
            String qrUrl
    ) {
        this.id = id;
        this.paymentMethodId = paymentMethodId;
        this.code = code;
        this.provider = provider;
        this.type = type;
        this.name = name;
        this.subtitle = subtitle;
        this.logoUrl = logoUrl;
        this.currencies = currencies != null ? currencies : new ArrayList<>();
        this.forDeposit = forDeposit;
        this.forCheckout = forCheckout;
        this.minUsd = minUsd;
        this.maxUsd = maxUsd;
        this.minSyp = minSyp;
        this.maxSyp = maxSyp;
        this.feePercent = feePercent;
        this.feeFixed = feeFixed;
        this.isComingSoon = isComingSoon;
        this.isMaintenanceMode = isMaintenanceMode;
        this.isUnavailable = isUnavailable;
        this.badgeLabel = badgeLabel;
        this.unavailableMessage = unavailableMessage;
        this.instructions = instructions;
        this.staticRowsJson = staticRowsJson;
        this.formFieldsJson = formFieldsJson;
        this.qrUrl = qrUrl;
    }

    public boolean supportsCurrency(String curr) {
        if (currencies == null || currencies.isEmpty()) return true;
        for (String c : currencies) {
            if (c != null && c.equalsIgnoreCase(curr)) return true;
        }
        return false;
    }

    public static List<GatewayItem> parseList(JSONArray arr) {
        List<GatewayItem> out = new ArrayList<>();
        if (arr == null) return out;
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.optJSONObject(i);
            if (o == null) continue;
            List<String> currs = new ArrayList<>();
            JSONArray cArr = o.optJSONArray("currencies");
            if (cArr != null) {
                for (int k = 0; k < cArr.length(); k++) {
                    String c = cArr.optString(k, "").trim().toUpperCase();
                    if (!c.isEmpty()) currs.add(c);
                }
            }
            if (currs.isEmpty()) {
                currs.add("USD");
                currs.add("SYP");
            }
            JSONArray sRows = o.optJSONArray("static_rows");
            JSONArray fFields = o.optJSONArray("form_fields");
            out.add(new GatewayItem(
                    o.optString("id", ""),
                    o.optString("payment_method_id", ""),
                    o.optString("code", ""),
                    o.optString("provider", ""),
                    o.optString("type", "gateway"),
                    o.optString("name", "بوابة دفع"),
                    o.optString("subtitle", ""),
                    o.optString("logo_url", ""),
                    currs,
                    o.optBoolean("for_deposit", true),
                    o.optBoolean("for_checkout", true),
                    o.optDouble("min_usd", 1.0),
                    o.optDouble("max_usd", 10000.0),
                    o.optDouble("min_syp", 15000.0),
                    o.optDouble("max_syp", 50000000.0),
                    o.optDouble("fee_percent", 0.0),
                    o.optDouble("fee_fixed", 0.0),
                    o.optBoolean("is_coming_soon", false),
                    o.optBoolean("is_maintenance_mode", false),
                    o.optBoolean("is_unavailable", false),
                    o.optString("badge_label", "فوري ⚡"),
                    o.optString("unavailable_message", ""),
                    o.optString("instructions", ""),
                    sRows != null ? sRows.toString() : "[]",
                    fFields != null ? fFields.toString() : "[]",
                    o.optString("qr_url", "")
            ));
        }
        return out;
    }
}
