package com.raqamiyat.app.adapter;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.raqamiyat.app.R;
import com.raqamiyat.app.model.CategoryItem;

import java.util.ArrayList;
import java.util.List;

public class CategoryAdapter extends RecyclerView.Adapter<CategoryAdapter.VH> {

    public interface OnCategoryClickListener {
        void onCategorySelected(String categoryId);
    }

    private final List<CategoryItem> items = new ArrayList<>();
    private String selectedCategoryId = "";
    private final OnCategoryClickListener listener;

    public CategoryAdapter(OnCategoryClickListener listener) {
        this.listener = listener;
    }

    public void submitList(List<CategoryItem> categories) {
        items.clear();
        items.add(new CategoryItem("", "الكل", "", "all"));
        if (categories != null) {
            items.addAll(categories);
        }
        notifyDataSetChanged();
    }

    public void setSelectedCategoryId(String categoryId) {
        this.selectedCategoryId = categoryId != null ? categoryId : "";
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_category_chip, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        CategoryItem item = items.get(position);
        boolean isSelected = item.id.equals(selectedCategoryId);
        holder.title.setText(item.name);
        holder.title.setBackgroundResource(isSelected ? R.drawable.bg_chip_selected : R.drawable.bg_chip_unselected);
        holder.title.setTextColor(isSelected ? 0xFF030712 : 0xFFE2E8F0);
        holder.itemView.setOnClickListener(v -> {
            selectedCategoryId = item.id;
            notifyDataSetChanged();
            if (listener != null) {
                listener.onCategorySelected(item.id);
            }
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        final TextView title;
        VH(@NonNull View itemView) {
            super(itemView);
            title = itemView.findViewById(R.id.chip_title);
        }
    }
}
