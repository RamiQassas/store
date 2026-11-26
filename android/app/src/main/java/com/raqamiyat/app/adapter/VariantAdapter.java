package com.raqamiyat.app.adapter;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.raqamiyat.app.R;
import com.raqamiyat.app.RaqamiyatLocalStore;
import com.raqamiyat.app.UiMotion;
import com.raqamiyat.app.model.VariantItem;

import java.util.ArrayList;
import java.util.List;

public class VariantAdapter extends RecyclerView.Adapter<VariantAdapter.VH> {

    public interface OnVariantSelectedListener {
        void onVariantSelected(VariantItem variant);
    }

    private final List<VariantItem> items = new ArrayList<>();
    private int selectedPos = 0;
    private String currency = "USD";
    private double sypRate = 15000.0;
    private final OnVariantSelectedListener listener;

    public VariantAdapter(OnVariantSelectedListener listener) {
        this.listener = listener;
    }

    public void updateCurrencyConfig(String currencyCode, double sypExchangeRate) {
        this.currency = "SYP".equalsIgnoreCase(currencyCode) ? "SYP" : "USD";
        if (sypExchangeRate > 1.0) {
            this.sypRate = sypExchangeRate;
        }
        notifyDataSetChanged();
    }

    public void submitList(List<VariantItem> variants) {
        items.clear();
        if (variants != null) {
            items.addAll(variants);
        }
        selectedPos = 0;
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_variant_chip, parent, false);
        UiMotion.attachPressScale(v);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        VariantItem item = items.get(position);
        boolean isSelected = position == selectedPos;
        holder.name.setText(item.name);
        holder.price.setText(RaqamiyatLocalStore.formatPriceInCurrency(item.price, currency, sypRate));
        holder.container.setBackgroundResource(isSelected ? R.drawable.bg_gateway_selected : R.drawable.bg_gateway_unselected);
        holder.name.setTextColor(0xFFFFFFFF);
        holder.price.setTextColor(isSelected ? 0xFF22D3EE : 0xFFFBBF24);

        holder.itemView.setOnClickListener(v -> {
            int pos = holder.getBindingAdapterPosition();
            if (pos != RecyclerView.NO_POSITION) {
                UiMotion.hapticTap(v);
                selectedPos = pos;
                notifyDataSetChanged();
                if (listener != null) {
                    listener.onVariantSelected(items.get(pos));
                }
            }
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        final LinearLayout container;
        final TextView name;
        final TextView price;

        VH(@NonNull View itemView) {
            super(itemView);
            container = itemView.findViewById(R.id.variant_container);
            name = itemView.findViewById(R.id.variant_name);
            price = itemView.findViewById(R.id.variant_price);
        }
    }
}
