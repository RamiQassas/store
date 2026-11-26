package com.raqamiyat.app.adapter;

import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.raqamiyat.app.CatalogRepository;
import com.raqamiyat.app.R;
import com.raqamiyat.app.UiMotion;
import com.raqamiyat.app.model.GatewayItem;

import java.util.ArrayList;
import java.util.List;

public class HeroBannerAdapter extends RecyclerView.Adapter<HeroBannerAdapter.VH> {

    public static class Slide {
        public final int backgroundRes;
        public final String tag;
        public final String title;
        public final String subtitle;
        public final String ctaText;
        public final int actionCode; // 0=Wallet/Login, 1=Catalog/Featured, 2=Gateways

        public Slide(int backgroundRes, String tag, String title, String subtitle, String ctaText, int actionCode) {
            this.backgroundRes = backgroundRes;
            this.tag = tag;
            this.title = title;
            this.subtitle = subtitle;
            this.ctaText = ctaText;
            this.actionCode = actionCode;
        }
    }

    public interface OnSlideActionListener {
        void onSlideAction(int actionCode);
    }

    private final List<Slide> slides = new ArrayList<>();
    private final List<GatewayItem> gateways = new ArrayList<>();
    private final OnSlideActionListener listener;

    public HeroBannerAdapter(OnSlideActionListener listener) {
        this.listener = listener;
    }

    public void submitData(List<Slide> newSlides, List<GatewayItem> newGateways) {
        slides.clear();
        if (newSlides != null) slides.addAll(newSlides);
        gateways.clear();
        if (newGateways != null) gateways.addAll(newGateways);
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_hero_banner, parent, false);
        UiMotion.attachPressScale(v);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        Slide s = slides.get(position);
        holder.root.setBackgroundResource(s.backgroundRes);
        holder.tag.setText(s.tag);
        holder.title.setText(s.title);
        holder.subtitle.setText(s.subtitle);
        holder.cta.setText(s.ctaText);

        holder.logosContainer.removeAllViews();
        if (position == 0 || position == 2) {
            int shown = 0;
            int boxSz = UiMotion.dp(holder.root, 28);
            int imgSz = UiMotion.dp(holder.root, 22);
            for (GatewayItem g : gateways) {
                if (!"gateway".equals(g.type) || shown >= 3) continue;
                shown++;
                LinearLayout box = new LinearLayout(holder.root.getContext());
                box.setBackgroundResource(R.drawable.bg_logo_box);
                box.setGravity(Gravity.CENTER);
                LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(boxSz, boxSz);
                lp.setMarginStart(UiMotion.dp(holder.root, 5));
                box.setLayoutParams(lp);

                ImageView iv = new ImageView(holder.root.getContext());
                iv.setLayoutParams(new LinearLayout.LayoutParams(imgSz, imgSz));
                iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
                String logo = !g.logoUrl.isEmpty() ? g.logoUrl : (CatalogRepository.DOMAIN + "/api/app/gateway-logo/" + g.provider + "/");
                Glide.with(holder.root.getContext())
                        .load(logo)
                        .diskCacheStrategy(DiskCacheStrategy.ALL)
                        .placeholder(R.mipmap.ic_launcher)
                        .into(iv);
                box.addView(iv);
                holder.logosContainer.addView(box);
            }
        }

        View.OnClickListener click = v -> {
            UiMotion.hapticTap(v);
            if (listener != null) listener.onSlideAction(s.actionCode);
        };
        holder.root.setOnClickListener(click);
        holder.cta.setOnClickListener(click);
    }

    @Override
    public int getItemCount() {
        return slides.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        final LinearLayout root;
        final TextView tag;
        final TextView title;
        final TextView subtitle;
        final TextView cta;
        final LinearLayout logosContainer;

        VH(@NonNull View itemView) {
            super(itemView);
            root = itemView.findViewById(R.id.hero_slide_root);
            tag = itemView.findViewById(R.id.hero_slide_tag);
            title = itemView.findViewById(R.id.hero_slide_title);
            subtitle = itemView.findViewById(R.id.hero_slide_subtitle);
            cta = itemView.findViewById(R.id.hero_slide_cta);
            logosContainer = itemView.findViewById(R.id.hero_slide_logos);
        }
    }
}
