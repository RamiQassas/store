package com.raqamiyat.app;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.raqamiyat.app.adapter.VariantAdapter;
import com.raqamiyat.app.model.ProductItem;
import com.raqamiyat.app.model.VariantItem;

import java.util.Locale;

public class ProductDetailActivity extends AppCompatActivity {

    public static final String EXTRA_PRODUCT = "extra_product";
    public static final String EXTRA_OPEN_URL = "extra_open_url";

    private ProductItem product;
    private VariantItem selectedVariant;
    private ConnectivityHelper connectivityHelper;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }
        setContentView(R.layout.activity_product_detail);

        connectivityHelper = new ConnectivityHelper(this);
        product = (ProductItem) getIntent().getSerializableExtra(EXTRA_PRODUCT);
        if (product == null) {
            finish();
            return;
        }

        ImageButton btnBack = findViewById(R.id.btn_detail_back);
        btnBack.setOnClickListener(v -> finish());

        ImageView img = findViewById(R.id.detail_image);
        TextView codeBadge = findViewById(R.id.detail_code_badge);
        TextView category = findViewById(R.id.detail_category);
        TextView delivery = findViewById(R.id.detail_delivery);
        TextView name = findViewById(R.id.detail_name);
        TextView price = findViewById(R.id.detail_price);
        TextView description = findViewById(R.id.detail_description);
        TextView variantsLabel = findViewById(R.id.detail_variants_label);
        RecyclerView variantsRv = findViewById(R.id.detail_variants_rv);
        Button btnBuy = findViewById(R.id.btn_detail_buy);

        if (product.imageUrl != null && !product.imageUrl.isEmpty()) {
            Glide.with(this)
                    .load(product.imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .into(img);
        } else {
            img.setImageResource(R.mipmap.ic_launcher);
        }

        codeBadge.setText(product.code != null && !product.code.isEmpty() ? "كود: " + product.code : "رقميات");
        category.setText(product.categoryName != null && !product.categoryName.isEmpty() ? product.categoryName : "المنتجات");
        if (product.deliveryTimeDisplay != null && !product.deliveryTimeDisplay.isEmpty()) {
            delivery.setText("⚡ التسليم: " + product.deliveryTimeDisplay);
            delivery.setVisibility(View.VISIBLE);
        } else {
            delivery.setVisibility(View.GONE);
        }

        name.setText(product.name);
        price.setText(product.price > 0 ? String.format(Locale.US, "$%.2f", product.price) : "حسب الباقة");
        description.setText(product.description != null && !product.description.trim().isEmpty()
                ? product.description.trim()
                : "منتج متوفر في متجر رقميات بأعلى جودة وضمان.");

        if (product.variants != null && !product.variants.isEmpty()) {
            selectedVariant = product.variants.get(0);
            price.setText(String.format(Locale.US, "$%.2f", selectedVariant.price));
            if (selectedVariant.sku != null && !selectedVariant.sku.isEmpty()) {
                codeBadge.setText("كود: " + selectedVariant.sku);
            }

            variantsRv.setLayoutManager(new LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false));
            VariantAdapter adapter = new VariantAdapter(variant -> {
                selectedVariant = variant;
                price.setText(String.format(Locale.US, "$%.2f", variant.price));
                if (variant.sku != null && !variant.sku.isEmpty()) {
                    codeBadge.setText("كود: " + variant.sku);
                }
            });
            adapter.submitList(product.variants);
            variantsRv.setAdapter(adapter);
        } else {
            variantsLabel.setVisibility(View.GONE);
            variantsRv.setVisibility(View.GONE);
        }

        if (product.isOutOfStock) {
            btnBuy.setText("غير متوفر حالياً");
            btnBuy.setEnabled(false);
            btnBuy.setAlpha(0.55f);
        } else {
            btnBuy.setOnClickListener(v -> {
                if (!connectivityHelper.isOnline()) {
                    new MaterialAlertDialogBuilder(this)
                            .setTitle("⚠️ لا يوجد اتصال بالإنترنت")
                            .setMessage("إتمام الطلب والشراء يتطلب اتصالاً فعالاً بالإنترنت لحماية حسابك وتأكيد العملية.")
                            .setPositiveButton("حسناً", (d, w) -> d.dismiss())
                            .show();
                    return;
                }
                Intent result = new Intent();
                result.putExtra(EXTRA_OPEN_URL, CatalogRepository.DOMAIN + "/catalog/" + product.id + "/");
                setResult(RESULT_OK, result);
                finish();
            });
        }
    }
}
