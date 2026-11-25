package com.raqamiyat.app.model;

import java.io.Serializable;

public class CartItem implements Serializable {
    public final String productId;
    public final String variantId;
    public final String productName;
    public final String variantName;
    public final String imageUrl;
    public final double unitPriceUsd;
    public int quantity;
    public String customInput;

    public CartItem(String productId, String variantId, String productName, String variantName, String imageUrl, double unitPriceUsd, int quantity, String customInput) {
        this.productId = productId != null ? productId : "";
        this.variantId = variantId != null ? variantId : "";
        this.productName = productName != null ? productName : "";
        this.variantName = variantName != null ? variantName : "";
        this.imageUrl = imageUrl != null ? imageUrl : "";
        this.unitPriceUsd = unitPriceUsd;
        this.quantity = Math.max(1, quantity);
        this.customInput = customInput != null ? customInput : "";
    }

    public String getKey() {
        return productId + "::" + variantId;
    }
}
