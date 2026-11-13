package com.raqamiyat.app.model;

import java.io.Serializable;

public class VariantItem implements Serializable {
    public final String id;
    public final String name;
    public final String sku;
    public final double price;
    public final boolean isActive;

    public VariantItem(String id, String name, String sku, double price, boolean isActive) {
        this.id = id;
        this.name = name;
        this.sku = sku;
        this.price = price;
        this.isActive = isActive;
    }
}
