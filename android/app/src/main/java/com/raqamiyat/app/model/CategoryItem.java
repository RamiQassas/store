package com.raqamiyat.app.model;

public class CategoryItem {
    public final String id;
    public final String name;
    public final String imageUrl;
    public final String productType;

    public CategoryItem(String id, String name, String imageUrl, String productType) {
        this.id = id;
        this.name = name;
        this.imageUrl = imageUrl;
        this.productType = productType;
    }
}
