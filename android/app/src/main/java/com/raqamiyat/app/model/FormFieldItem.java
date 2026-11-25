package com.raqamiyat.app.model;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class FormFieldItem implements Serializable {
    public final String name;
    public final String label;
    public final String type;
    public final String placeholder;
    public final boolean required;
    public final List<String> options;

    public FormFieldItem(String name, String label, String type, String placeholder, boolean required, List<String> options) {
        this.name = name != null ? name : "note";
        this.label = label != null ? label : "البيانات المطلوبة";
        this.type = type != null ? type : "text";
        this.placeholder = placeholder != null ? placeholder : "";
        this.required = required;
        this.options = options != null ? options : new ArrayList<>();
    }
}
