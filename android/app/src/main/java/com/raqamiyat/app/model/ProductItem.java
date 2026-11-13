package com.raqamiyat.app.model;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class ProductItem implements Serializable {
    public final String id;
    public final String name;
    public final String code;
    public final String description;
    public final String categoryId;
    public final String categoryName;
    public final String imageUrl;
    public final double price;
    public final String productType;
    public final boolean isFeatured;
    public final boolean isSale;
    public final boolean isOutOfStock;
    public final String deliveryTimeDisplay;
    public final List<VariantItem> variants;

    public ProductItem(
            String id,
            String name,
            String code,
            String description,
            String categoryId,
            String categoryName,
            String imageUrl,
            double price,
            String productType,
            boolean isFeatured,
            boolean isSale,
            boolean isOutOfStock,
            String deliveryTimeDisplay,
            List<VariantItem> variants
    ) {
        this.id = id;
        this.name = name;
        this.code = code;
        this.description = description;
        this.categoryId = categoryId;
        this.categoryName = categoryName;
        this.imageUrl = imageUrl;
        this.price = price;
        this.productType = productType;
        this.isFeatured = isFeatured;
        this.isSale = isSale;
        this.isOutOfStock = isOutOfStock;
        this.deliveryTimeDisplay = deliveryTimeDisplay;
        this.variants = variants != null ? variants : new ArrayList<>();
    }
}
