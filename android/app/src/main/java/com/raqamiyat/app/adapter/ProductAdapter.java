package com.raqamiyat.app.adapter;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.bumptech.glide.load.resource.drawable.DrawableTransitionOptions;
import com.raqamiyat.app.R;
import com.raqamiyat.app.RaqamiyatLocalStore;
import com.raqamiyat.app.UiMotion;
import com.raqamiyat.app.model.ProductItem;

import java.util.ArrayList;
import java.util.List;

public class ProductAdapter extends RecyclerView.Adapter<ProductAdapter.VH> {

    public interface OnProductClickListener {
        void onProductClick(ProductItem product);
    }

    public interface OnAddToCartClickListener {
        void onAddToCart(ProductItem product);
    }

    private final List<ProductItem> items = new ArrayList<>();
    private final OnProductClickListener listener;
    private OnAddToCartClickListener cartListener;
    private String currency = "USD";
    private double sypRate = 15000.0;
    private int lastAnimatedPos = -1;

    public ProductAdapter(OnProductClickListener listener) {
        this.listener = listener;
    }

    public void setOnAddToCartClickListener(OnAddToCartClickListener cartListener) {
        this.cartListener = cartListener;
    }

    public void updateCurrencyConfig(String currencyCode, double sypExchangeRate) {
        this.currency = "SYP".equalsIgnoreCase(currencyCode) ? "SYP" : "USD";
        if (sypExchangeRate > 1.0) {
            this.sypRate = sypExchangeRate;
        }
        notifyDataSetChanged();
    }

    public void submitList(List<ProductItem> products) {
        items.clear();
        if (products != null) {
            items.addAll(products);
        }
        lastAnimatedPos = -1;
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_product_card, parent, false);
        UiMotion.attachPressScale(v);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        ProductItem item = items.get(position);
        holder.name.setText(item.name);
        holder.category.setText(item.categoryName != null && !item.categoryName.isEmpty() ? item.categoryName : "رقميات");

        if (item.price > 0) {
            String primary = RaqamiyatLocalStore.formatPriceInCurrency(item.price, currency, sypRate);
            String secondaryCurr = "USD".equalsIgnoreCase(currency) ? "SYP" : "USD";
            String secondary = "≈ " + RaqamiyatLocalStore.formatPriceInCurrency(item.price, secondaryCurr, sypRate);
            holder.price.setText(primary);
            holder.priceSub.setText(item.variants != null && item.variants.size() > 1 ? (secondary + " • باقات متعددة") : secondary);
            holder.priceSub.setVisibility(View.VISIBLE);
        } else {
            holder.price.setText("حسب الباقة");
            holder.priceSub.setVisibility(View.GONE);
        }

        holder.badgeStock.setVisibility(item.isOutOfStock ? View.VISIBLE : View.GONE);
        if (!item.isOutOfStock && (item.isFeatured || item.isSale)) {
            holder.badgeFeatured.setText(item.isSale ? "عرض خاص" : "الأكثر طلباً");
            holder.badgeFeatured.setVisibility(View.VISIBLE);
        } else {
            holder.badgeFeatured.setVisibility(View.GONE);
        }
        holder.badgeInstant.setVisibility(item.isOutOfStock ? View.GONE : View.VISIBLE);

        holder.btnBuy.setText(item.isOutOfStock ? "غير متوفر" : "شراء الآن");
        holder.btnBuy.setAlpha(item.isOutOfStock ? 0.5f : 1.0f);
        holder.btnCart.setVisibility(item.isOutOfStock ? View.GONE : View.VISIBLE);

        if (item.imageUrl != null && !item.imageUrl.isEmpty()) {
            Glide.with(holder.image.getContext())
                    .load(item.imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .transition(DrawableTransitionOptions.withCrossFade(220))
                    .placeholder(R.mipmap.ic_launcher)
                    .error(R.mipmap.ic_launcher)
                    .into(holder.image);
        } else {
            holder.image.setImageResource(R.mipmap.ic_launcher);
        }

        if (position > lastAnimatedPos) {
            UiMotion.animateCardEntrance(holder.itemView, position);
            lastAnimatedPos = position;
        }

        View.OnClickListener openDetail = v -> {
            UiMotion.hapticTap(v);
            if (listener != null) {
                listener.onProductClick(item);
            }
        };
        holder.itemView.setOnClickListener(openDetail);
        holder.btnBuy.setOnClickListener(openDetail);
        holder.btnCart.setOnClickListener(v -> {
            UiMotion.hapticTap(v);
            if (!item.isOutOfStock && cartListener != null) {
                cartListener.onAddToCart(item);
            } else if (listener != null) {
                listener.onProductClick(item);
            }
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        final ImageView image;
        final TextView category;
        final TextView name;
        final TextView price;
        final TextView priceSub;
        final TextView badgeStock;
        final TextView badgeFeatured;
        final View badgeInstant;
        final TextView btnBuy;
        final View btnCart;

        VH(@NonNull View itemView) {
            super(itemView);
            image = itemView.findViewById(R.id.product_image);
            category = itemView.findViewById(R.id.product_category);
            name = itemView.findViewById(R.id.product_name);
            price = itemView.findViewById(R.id.product_price);
            priceSub = itemView.findViewById(R.id.product_price_sub);
            badgeStock = itemView.findViewById(R.id.badge_stock);
            badgeFeatured = itemView.findViewById(R.id.badge_featured);
            badgeInstant = itemView.findViewById(R.id.badge_instant);
            btnBuy = itemView.findViewById(R.id.btn_card_buy);
            btnCart = itemView.findViewById(R.id.btn_card_cart);
        }
    }
}
