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
import com.raqamiyat.app.R;
import com.raqamiyat.app.model.ProductItem;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ProductAdapter extends RecyclerView.Adapter<ProductAdapter.VH> {

    public interface OnProductClickListener {
        void onProductClick(ProductItem product);
    }

    private final List<ProductItem> items = new ArrayList<>();
    private final OnProductClickListener listener;

    public ProductAdapter(OnProductClickListener listener) {
        this.listener = listener;
    }

    public void submitList(List<ProductItem> products) {
        items.clear();
        if (products != null) {
            items.addAll(products);
        }
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_product_card, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        ProductItem item = items.get(position);
        holder.name.setText(item.name);
        holder.category.setText(item.categoryName != null && !item.categoryName.isEmpty() ? item.categoryName : "رقميات");
        holder.price.setText(item.price > 0
                ? String.format(Locale.US, "$%.2f", item.price)
                : "حسب الباقة");

        holder.badgeStock.setVisibility(item.isOutOfStock ? View.VISIBLE : View.GONE);
        holder.badgeFeatured.setVisibility(item.isFeatured && !item.isOutOfStock ? View.VISIBLE : View.GONE);

        if (item.imageUrl != null && !item.imageUrl.isEmpty()) {
            Glide.with(holder.image.getContext())
                    .load(item.imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher)
                    .error(R.mipmap.ic_launcher)
                    .into(holder.image);
        } else {
            holder.image.setImageResource(R.mipmap.ic_launcher);
        }

        holder.itemView.setOnClickListener(v -> {
            if (listener != null) {
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
        final TextView badgeStock;
        final TextView badgeFeatured;

        VH(@NonNull View itemView) {
            super(itemView);
            image = itemView.findViewById(R.id.product_image);
            category = itemView.findViewById(R.id.product_category);
            name = itemView.findViewById(R.id.product_name);
            price = itemView.findViewById(R.id.product_price);
            badgeStock = itemView.findViewById(R.id.badge_stock);
            badgeFeatured = itemView.findViewById(R.id.badge_featured);
        }
    }
}
