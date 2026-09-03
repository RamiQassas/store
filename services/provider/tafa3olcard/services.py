import re
import logging
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from .client import Tafa3olCardClient, Tafa3olCardAPIException

logger = logging.getLogger("provider.tafa3olcard.service")


class Tafa3olCardProviderService:
    """
    Main Service entry point for Tafa3ol Card (تفاعل كارد) Provider integration.
    Fully isolated and self-contained; guarantees other providers are never affected.
    """

    def __init__(self, api_token: str, base_url: str = None, profile_model=None):
        self.profile = profile_model
        if profile_model and not api_token:
            api_token = profile_model.api_token
            base_url = profile_model.base_url

        self.client = Tafa3olCardClient(
            api_token=api_token,
            base_url=base_url,
            profile=profile_model
        )

    def fetch_balance(self) -> dict:
        """
        Fetches current balance from Tafa3ol Card API.
        GET /balance
        Response format:
        { "success": true, "message": "Balance retrieved", "data": { "balance": 152.75, "openCredit": 0, "currency": "USD" } }
        """
        data = self.client.get_balance()
        inner = data.get("data") or {}

        raw_balance = inner.get("balance", 0)
        raw_currency = inner.get("currency") or "USD"

        balance_val = Decimal(str(raw_balance or "0.00"))
        currency_val = str(raw_currency or "USD")

        if self.profile:
            self.profile.balance = balance_val
            self.profile.currency = currency_val
            self.profile.save(update_fields=["balance", "currency", "updated_at"])

        return {
            "balance": balance_val,
            "currency": currency_val,
            "raw_response": data,
        }

    def fetch_products(self) -> list:
        """
        Fetches all available products from Tafa3ol Card with pagination.
        """
        all_products = []
        page = 1
        limit = 50

        while True:
            try:
                res = self.client.get_products(page=page, limit=limit)
                if isinstance(res, dict):
                    data = res.get("data") or []
                    meta = res.get("meta") or {}
                elif isinstance(res, list):
                    data = res
                    meta = {}
                else:
                    data = []
                    meta = {}

                if not data or not isinstance(data, list):
                    break

                for p in data:
                    if isinstance(p, dict):
                        all_products.append(p)

                total = meta.get("total", 0) if isinstance(meta, dict) else 0
                if len(all_products) >= total or len(data) < limit:
                    break
                page += 1
                if page > 50:  # safety bound
                    break
            except Exception as e:
                logger.error(f"Error fetching page {page} from Tafa3ol Card: {e}")
                if page == 1:
                    raise e
                break

        return all_products

    def sync_catalog(self, selected_group_names=None, progress_callback=None) -> dict:
        """
        Synchronizes Tafa3ol Card products and categories into ProviderProduct/ProviderCategory,
        and reports live progress to cache and callback.
        """
        from django.core.cache import cache
        from apps.providers.models import ProviderCategory, ProviderProduct, ProviderPrice
        from apps.catalog.models import Category, Product, ProductVariant

        progress_key = f"sync_progress_{self.profile.id}" if self.profile else None
        def _safe_cache(k, v, to=600):
            try:
                cache.set(k, v, timeout=to)
            except Exception:
                pass

        if progress_key:
            _safe_cache(progress_key, {
                "status": "running",
                "total": 0,
                "current": 0,
                "percent": 5,
                "product_name": "جاري الاتصال بخادم تفاعل كارد وجلب قائمة المنتجات...",
                "created": 0,
                "updated": 0
            }, 600)

        raw_products = self.fetch_products()
        total_items = len(raw_products)
        created_count = 0
        updated_count = 0

        # Also fetch categories from provider
        cat_map = {}
        # 1. Fetch categories
        try:
            cats_res = self.client.get_categories()
            raw_cats = cats_res.get("data") if isinstance(cats_res, dict) else (cats_res if isinstance(cats_res, list) else [])
            for c in raw_cats:
                if isinstance(c, dict):
                    c_id = str(c.get("_id") or c.get("id") or "")
                    c_name = c.get("name")
                    if isinstance(c_name, dict):
                        c_name = c_name.get("ar") or c_name.get("en") or str(c_name)
                    if c_id:
                        cat_map[c_id] = str(c_name or "عام")
                elif isinstance(c, str):
                    cat_map[c] = c
        except Exception as e:
            logger.warning(f"Could not fetch Tafa3ol Card categories: {e}")

        # 2. Fetch services
        try:
            srv_res = self.client.get_services()
            raw_srv = srv_res.get("data") if isinstance(srv_res, dict) else (srv_res if isinstance(srv_res, list) else [])
            for s in raw_srv:
                if isinstance(s, dict):
                    s_id = str(s.get("_id") or s.get("id") or "")
                    s_name = s.get("name")
                    if isinstance(s_name, dict):
                        s_name = s_name.get("ar") or s_name.get("en") or str(s_name)
                    if s_id and s_id not in cat_map:
                        cat_map[s_id] = str(s_name or "عام")
                elif isinstance(s, str):
                    cat_map[s] = s
        except Exception as e:
            logger.warning(f"Could not fetch Tafa3ol Card services: {e}")

        store = self.profile.store if self.profile else None
        known_requirements = {}

        for idx, item in enumerate(raw_products, start=1):
            if not isinstance(item, dict):
                continue
            remote_id = str(item.get("_id") or item.get("id") or "")
            if not remote_id:
                continue

            raw_name = item.get("name")
            if isinstance(raw_name, dict):
                p_name = raw_name.get("ar") or raw_name.get("en") or str(raw_name)
            else:
                p_name = str(raw_name or "منتج تفاعل كارد")
            p_name = p_name.strip()

            # Skip decorative / separator dot items like "..........................................."
            if re.match(r'^[\.\s\-_=~*#]+$', p_name) or len(p_name) < 2:
                continue

            # Accurate Pricing calculation from Tafa3ol Card pricing object
            pricing_obj = item.get("pricing") or {}
            qty_mode = str(item.get("quantityMode") or "FIXED").upper()
            min_qty = item.get("minQuantity", 1)
            max_qty = item.get("maxQuantity", 10)

            final_total = pricing_obj.get("finalTotalPrice") if isinstance(pricing_obj, dict) else None
            final_unit = pricing_obj.get("finalUnitPrice") if isinstance(pricing_obj, dict) else None
            display_qty = (pricing_obj.get("displayQuantity") if isinstance(pricing_obj, dict) else None) or 1

            if qty_mode in ("COUNTER", "QUANTITY", "RANGE"):
                if final_unit is not None and float(final_unit) > 0:
                    cost_price = Decimal(str(round(float(final_unit), 6)))
                elif final_total is not None and float(final_total) > 0:
                    cost_price = Decimal(str(round(float(final_total) / max(int(display_qty), 1), 6)))
                else:
                    cost_price = Decimal(str(item.get("costPrice") or item.get("price") or "0.00"))
            else:
                if final_total is not None and float(final_total) > 0:
                    cost_price = Decimal(str(round(float(final_total), 4)))
                elif final_unit is not None and float(final_unit) > 0:
                    cost_price = Decimal(str(round(float(final_unit), 4)))
                else:
                    cost_price = Decimal(str(item.get("costPrice") or item.get("price") or "0.00"))

            # Handle Category & Service exactly from Tafa3ol Card hierarchy
            srv_field = item.get("serviceId") or item.get("service") or {}
            cat_field = item.get("categoryId") or item.get("category") or {}

            # Service (Parent category in Tafa3ol Card)
            if isinstance(srv_field, dict):
                srv_id = str(srv_field.get("_id") or srv_field.get("id") or "")
                s_name = srv_field.get("name")
                srv_name = (s_name.get("ar") or s_name.get("en") if isinstance(s_name, dict) else str(s_name or "")).strip()
            else:
                srv_id = str(srv_field or "")
                srv_name = cat_map.get(srv_id, "")

            # Category (Child game/app/service in Tafa3ol Card)
            if isinstance(cat_field, dict):
                cat_id = str(cat_field.get("_id") or cat_field.get("id") or "")
                c_name = cat_field.get("name")
                cat_name = (c_name.get("ar") or c_name.get("en") if isinstance(c_name, dict) else str(c_name or "")).strip()
                cat_img = (cat_field.get("image") or {}).get("secureUrl") if isinstance(cat_field.get("image"), dict) else ""
            else:
                cat_id = str(cat_field or "")
                cat_name = cat_map.get(cat_id, "")
                cat_img = ""

            item_img_obj = item.get("image")
            item_img = ""
            if isinstance(item_img_obj, dict):
                item_img = item_img_obj.get("secureUrl") or item_img_obj.get("url") or ""
            elif isinstance(item_img_obj, str):
                item_img = item_img_obj

            final_img = cat_img or item_img

            if not srv_name:
                srv_name = "خدمات رقمية"
            if not cat_name:
                cat_name = p_name

            # Update or create ProviderCategory
            p_cat = None
            if self.profile:
                parent_cat = None
                if srv_id or srv_name:
                    parent_cat, _ = ProviderCategory.objects.get_or_create(
                        profile=self.profile,
                        remote_id=srv_id or f"srv_{srv_name}",
                        defaults={"name": srv_name}
                    )
                    if parent_cat.name != srv_name:
                        parent_cat.name = srv_name
                        parent_cat.save(update_fields=["name"])

                p_cat, _ = ProviderCategory.objects.get_or_create(
                    profile=self.profile,
                    remote_id=cat_id or f"cat_{cat_name}",
                    defaults={"name": cat_name, "parent": parent_cat}
                )
                if parent_cat and p_cat.parent != parent_cat:
                    p_cat.parent = parent_cat
                    p_cat.save(update_fields=["parent"])
                if cat_name and p_cat.name != cat_name:
                    p_cat.name = cat_name
                    p_cat.save(update_fields=["name"])

                extra_data = {
                    "image_url": final_img,
                    "service_name": srv_name,
                    "category_name": cat_name,
                    "quantity_mode": qty_mode,
                    "display_quantity": display_qty,
                }

                pp, created = ProviderProduct.objects.update_or_create(
                    profile=self.profile,
                    remote_id=remote_id,
                    defaults={
                        "name": p_name,
                        "category": p_cat,
                        "cost_price": cost_price,
                        "is_active": True,
                        "local_is_active": True,
                        "product_type": "package" if qty_mode == "FIXED" else "recharge",
                        "qty_min": min_qty,
                        "qty_max": max_qty,
                        "data": extra_data,
                    }
                )

                # Store product parameters / requirements safely
                requirements = item.get("requirements") or []
                if isinstance(requirements, list) and requirements:
                    pp.parameters.all().delete()
                    for r_idx, r in enumerate(requirements):
                        if isinstance(r, dict):
                            r_name = str(r.get("paramsName") or r.get("key") or r.get("name") or f"param_{r_idx}")[:100]
                            r_msg = r.get("message")
                            if isinstance(r_msg, dict):
                                r_label = r_msg.get("ar") or r_msg.get("en") or r_name
                            else:
                                r_label = str(r_msg or r_name)[:100]
                            r_required = bool(r.get("isRequired", True))
                            if r.get("_id"):
                                known_requirements[str(r["_id"])] = r
                        elif isinstance(r, str) and r.strip():
                            r_id = r.strip()
                            if r_id in known_requirements:
                                req_obj = known_requirements[r_id]
                                r_name = str(req_obj.get("paramsName") or "playerId")[:100]
                                r_msg = req_obj.get("message")
                                if isinstance(r_msg, dict):
                                    r_label = r_msg.get("ar") or r_msg.get("en") or r_name
                                else:
                                    r_label = str(r_msg or r_name)[:100]
                                r_required = bool(req_obj.get("isRequired", True))
                            else:
                                # Fetch detail for the first product to populate requirement definitions
                                resolved = False
                                try:
                                    prod_detail = self.client.get_product(remote_id)
                                    p_data = prod_detail.get("data") if isinstance(prod_detail, dict) else {}
                                    p_reqs = p_data.get("requirements") or []
                                    if isinstance(p_reqs, list):
                                        for pr in p_reqs:
                                            if isinstance(pr, dict) and pr.get("_id"):
                                                known_requirements[str(pr["_id"])] = pr
                                    if r_id in known_requirements:
                                        req_obj = known_requirements[r_id]
                                        r_name = str(req_obj.get("paramsName") or "playerId")[:100]
                                        r_msg = req_obj.get("message")
                                        if isinstance(r_msg, dict):
                                            r_label = r_msg.get("ar") or r_msg.get("en") or r_name
                                        else:
                                            r_label = str(r_msg or r_name)[:100]
                                        r_required = bool(req_obj.get("isRequired", True))
                                        resolved = True
                                except Exception:
                                    pass

                                if not resolved:
                                    r_name = "playerId"
                                    r_label = "معرف اللاعب / الحساب (Player ID)"
                                    r_required = True
                        else:
                            continue

                        pp.parameters.create(
                            name=r_name,
                            label=r_label,
                            required=r_required,
                            parameter_type="text"
                        )

                # Ensure default pricing entry exists
                ProviderPrice.objects.get_or_create(
                    product=pp,
                    defaults={
                        "margin_type": "percentage",
                        "margin_value": Decimal("5.00"),
                        "retail_margin_value": Decimal("5.00"),
                        "dealer_margin_value": Decimal("2.00"),
                        "vip_margin_value": Decimal("1.00"),
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            pct = int((idx / max(total_items, 1)) * 100) if total_items > 0 else 100
            if progress_key:
                _safe_cache(progress_key, {
                    "status": "running",
                    "total": total_items,
                    "current": idx,
                    "percent": min(pct, 99),
                    "product_name": p_name,
                    "created": created_count,
                    "updated": updated_count
                }, 600)

            if progress_callback:
                progress_callback(idx, total_items, p_name, created_count, updated_count)

        if self.profile:
            self.profile.last_sync_at = timezone.now()
            self.profile.save(update_fields=["last_sync_at"])

            # Automatically map ProviderProducts to store catalog Product & ProductVariant
            try:
                from apps.providers.alkasr.mapper import AlkasrMapperService
                AlkasrMapperService(self.profile).map_all_to_catalog(selected_group_names=selected_group_names)
            except Exception as map_err:
                logger.error(f"Auto-map catalog failed after Tafa3ol sync: {map_err}")

        if progress_key:
            _safe_cache(progress_key, {
                "status": "completed",
                "total": total_items,
                "current": total_items,
                "percent": 100,
                "product_name": f"تمت المزامنة وربط الخدمات بنجاح! تم استيراد وتحديث {created_count + updated_count} منتج.",
                "created": created_count,
                "updated": updated_count
            }, 600)

        return {
            "status": "completed",
            "total": total_items,
            "created": created_count,
            "updated": updated_count
        }

    def place_order(
        self,
        local_order,
        provider_product,
        quantity: int = 1,
        player_params: Dict[str, Any] = None,
        order_uuid: str = None
    ) -> dict:
        """
        Submits an order to Tafa3ol Card API.
        POST /orders
        Payload: { "productId": "...", "quantity": 1, "requirements": { ... } }
        """
        product_id = provider_product.remote_id
        
        # Build formatted requirements matching Tafa3ol Card parameters
        formatted_reqs = {}
        expected_params = list(provider_product.parameters.all())
        
        normalized_input = {}
        for k, v in (player_params or {}).items():
            if v is not None and str(v).strip():
                clean_k = re.sub(r'[^a-zA-Z0-9]', '', str(k).lower())
                normalized_input[clean_k] = str(v).strip()
                normalized_input[str(k)] = str(v).strip()

        if expected_params:
            for p in expected_params:
                p_name = p.name
                clean_p = re.sub(r'[^a-zA-Z0-9]', '', p_name.lower())
                val = (player_params or {}).get(p_name) or normalized_input.get(clean_p)
                
                if not val:
                    if any(x in clean_p for x in ("player", "user", "id", "account")):
                        for alias in ("playerid", "player_id", "userid", "user_id", "id", "account", "accountid"):
                            if alias in normalized_input:
                                val = normalized_input[alias]
                                break
                    elif any(x in clean_p for x in ("link", "url", "target")):
                        for alias in ("link", "url", "target"):
                            if alias in normalized_input:
                                val = normalized_input[alias]
                                break
                    elif any(x in clean_p for x in ("phone", "mobile", "number")):
                        for alias in ("phone", "mobile", "number"):
                            if alias in normalized_input:
                                val = normalized_input[alias]
                                break
                
                # If still empty and user gave single value, use it
                if not val and len(player_params or {}) == 1:
                    val = list((player_params or {}).values())[0]

                if val:
                    formatted_reqs[p_name] = str(val).strip()
        else:
            formatted_reqs = dict(player_params or {})

        res = self.client.create_order(
            product_id=product_id,
            quantity=quantity,
            requirements=formatted_reqs
        )

        data = res.get("data") or {}
        remote_order_id = str(data.get("_id") or data.get("orderNumber") or "")
        status = str(data.get("status") or "PROCESSING").upper()

        return {
            "status": status,
            "remote_order_id": remote_order_id,
            "raw_response": res
        }

    def check_orders(self, order_identifiers: List[str], is_uuid: bool = True) -> list:
        """
        Checks order statuses with Tafa3ol Card.
        GET /orders/:id
        """
        results = []
        for oid in order_identifiers:
            try:
                res = self.client.get_order(str(oid))
                data = res.get("data") or {}
                raw_status = str(data.get("status") or "").upper()

                # Map statuses
                if raw_status == "COMPLETED":
                    mapped = "completed"
                elif raw_status in ("PENDING_MANUAL", "PROCESSING"):
                    mapped = "pending"
                elif raw_status in ("FAILED", "CANCELLED"):
                    mapped = "failed"
                else:
                    mapped = "pending"

                results.append({
                    "remote_order_id": str(oid),
                    "status": mapped,
                    "raw_status": raw_status,
                    "data": data
                })
            except Exception as e:
                logger.error(f"Error checking order {oid} on Tafa3ol Card: {e}")
                results.append({
                    "remote_order_id": str(oid),
                    "status": "pending",
                    "error": str(e)
                })

        return results
