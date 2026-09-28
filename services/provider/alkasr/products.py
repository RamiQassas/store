"""
Alkasr Products Parser and Retrieval Service.
Parses, filters, and standardizes product payloads returned by the provider API.
"""

from typing import List, Dict, Any


class AlkasrProductService:
    """Service to process raw products data from Alkasr API."""

    def __init__(self, client):
        self.client = client

    def fetch_all_products(self) -> List[Dict[str, Any]]:
        """Fetches and parses products list from API client."""
        raw_data = self.client.get_products()
        return self.parse_products_response(raw_data)

    @classmethod
    def extract_item_availability(cls, item: dict) -> bool:
        """
        Determines item availability status with 100% precision:
        Defaults to True unless the provider explicitly marks the item as disabled, inactive, or out of stock.
        Never treats None/missing fields or parameter names ('qty') as out-of-stock.
        """
        if not isinstance(item, dict):
            return False

        # 1. Check explicit availability keys
        for k in ("available", "isAvailable", "is_available"):
            if k in item:
                val = item.get(k)
                if val is False or val == 0 or val == "0":
                    return False
                if isinstance(val, str) and val.strip().lower() in (
                    "0", "false", "no", "off", "unavailable", "out_of_stock", "disabled", "inactive"
                ):
                    return False

        # 2. Check active / enabled keys
        for k in ("is_active", "isActive", "active", "enabled", "is_enabled", "isEnabled"):
            if k in item:
                val = item.get(k)
                if val is False or val == 0 or val == "0":
                    return False
                if isinstance(val, str) and val.strip().lower() in (
                    "0", "false", "no", "off", "disabled", "inactive"
                ):
                    return False

        # 3. Check status string values
        for k in ("status", "state", "product_status", "item_status"):
            if k in item and item.get(k) is not None:
                st = str(item.get(k)).strip().lower()
                if st in (
                    "0", "false", "no", "inactive", "disabled", "off",
                    "out_of_stock", "out of stock", "out-of-stock", "oos",
                    "unavailable", "not_available", "not available",
                    "closed", "stop", "stopped", "paused", "maintenance",
                    "sold_out", "sold out", "soldout", "hidden", "deleted"
                ):
                    return False

        # 4. Check explicit in_stock boolean / string
        for k in ("in_stock", "inStock"):
            if k in item and item.get(k) is not None:
                val = item.get(k)
                if val is False or val == 0 or val == "0":
                    return False
                if isinstance(val, str) and val.strip().lower() in ("0", "false", "no", "out_of_stock", "out of stock"):
                    return False

        # 5. Check category status if provided as a dict
        cat_info = item.get("category")
        if isinstance(cat_info, dict):
            cat_st = str(cat_info.get("status") or cat_info.get("available") or cat_info.get("isAvailable") or "").strip().lower()
            if cat_st in ("0", "false", "no", "inactive", "disabled", "unavailable", "out_of_stock", "closed"):
                return False

        return True

    @classmethod
    def parse_products_response(cls, response_data: dict) -> List[Dict[str, Any]]:
        """
        Parses raw API JSON response into standardized Product DTO dicts.
        """
        raw_list = []
        if isinstance(response_data, list):
            raw_list = response_data
        elif isinstance(response_data, dict):
            d = response_data.get("data")
            p = response_data.get("products")
            if isinstance(d, list):
                raw_list = d
            elif isinstance(d, dict) and isinstance(d.get("products"), list):
                raw_list = d["products"]
            elif isinstance(p, list):
                raw_list = p
            else:
                raw_list = d or p or []

        if not isinstance(raw_list, list):
            raw_list = []

        parsed_products = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue

            remote_id = str(item.get("id") or item.get("product_id") or "")
            if not remote_id:
                continue

            name = str(item.get("name") or item.get("title") or f"Product #{remote_id}")[:255]
            cost_price = item.get("price") or item.get("cost") or item.get("base_price") or "0.00"
            product_type = str(item.get("product_type") or item.get("type") or "package")[:50]
            
            is_active = cls.extract_item_availability(item)

            qty_values = item.get("qty_values")
            qty_min = None
            qty_max = None
            qty_list = []
            
            if qty_values is None:
                qty_min = 1
                qty_max = 1
                product_type = "package"
            elif isinstance(qty_values, list):
                product_type = "fixed_quantities"
                qty_list = [str(x).strip() for x in qty_values if x is not None and str(x).strip().lower() not in ("none", "null", "")]
            elif isinstance(qty_values, dict):
                product_type = "amount"
                try:
                    qmin = qty_values.get("min")
                    qty_min = int(qmin) if qmin not in (None, "") else None
                except (ValueError, TypeError):
                    qty_min = None
                    
                try:
                    qmax = qty_values.get("max")
                    qty_max = int(qmax) if qmax not in (None, "") else None
                except (ValueError, TypeError):
                    qty_max = None

            raw_parent_id = item.get("parent_id") or item.get("parent")
            parent_name = str(item.get("parent_name") or item.get("app_name") or "").strip()[:100]
            raw_category_name = str(item.get("category_name") or item.get("category") or "").strip()[:100]
            raw_cat_id = item.get("category_id") or item.get("cat_id")
            
            # If category_name is empty, fallback to parent_name or General
            category_name = raw_category_name or parent_name or "عام"
            
            # Keep raw category_id as the subcategory ID, fallback to parent_id if missing
            if raw_cat_id and str(raw_cat_id) not in ("0", ""):
                category_id = str(raw_cat_id)[:100]
            elif raw_parent_id and str(raw_parent_id) not in ("0", ""):
                category_id = str(raw_parent_id)[:100]
            else:
                import hashlib
                category_id = hashlib.md5(category_name.encode('utf-8')).hexdigest()[:15]

            parent_id_val = str(raw_parent_id)[:100] if raw_parent_id and str(raw_parent_id) not in ("0", "") else None
            parent_name_val = parent_name if parent_name else None
            
            try:
                from decimal import Decimal
                dec_cost = Decimal(str(cost_price if cost_price not in (None, "") else "0.00").strip())
                
                # SMM / Per-Mille (Rate per 1,000 units in Alkasr API)
                remote_id_str = str(remote_id).strip()
                cat_lower = str(category_name or "").lower()
                name_lower = name.lower()
                is_smm = (
                    remote_id_str in ("9364", "7346", "7350", "7354", "7359", "7370", "7373", "7377")
                    or (product_type == "amount" and (qty_min or 0) >= 1000 and dec_cost >= Decimal("0.50"))
                    or (any(k in cat_lower for k in ("likee", "x", "twitter", "instagram", "tiktok")) and any(k in name_lower for k in ("متابعين", "followers", "likes", "views", "مشاهدات", "لايكات")))
                )
                if is_smm and dec_cost >= Decimal("0.50"):
                    dec_cost = dec_cost / Decimal("1000")

                if dec_cost > Decimal("10000") or remote_id_str == "9486":
                    is_active = False

                cost_price = f"{dec_cost:.8f}"
            except Exception:
                cost_price = "0.00000000"

            base_price = item.get("base_price") or cost_price
            category_img = str(item.get("category_img") or item.get("category_image") or item.get("img") or item.get("image") or "").strip()
            if category_img and category_img.lower() not in ("null", "none", ""):
                if not category_img.startswith("http"):
                    category_img = f"https://api.alkasr-vip.com/{category_img.lstrip('/')}"
            else:
                category_img = ""

            params = item.get("params") or item.get("parameters") or item.get("fields") or []

            parsed_products.append({
                "remote_id": remote_id,
                "name": name,
                "cost_price": str(cost_price),
                "base_price": str(base_price),
                "category_img": category_img,
                "product_type": product_type,
                "is_active": is_active,
                "qty_min": int(qty_min) if qty_min is not None else None,
                "qty_max": int(qty_max) if qty_max is not None else None,
                "qty_list": qty_list if isinstance(qty_list, list) else [],
                "raw_qty_values": qty_values,
                "category_id": str(category_id),
                "category_name": str(category_name),
                "parent_id": parent_id_val,
                "parent_name": parent_name_val,
                "parameters": params if isinstance(params, list) else [],
                "raw_data": item,
            })

        return parsed_products

    def filter_products(self, category_id: str = None, search: str = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """Filters catalog by category, search query, or availability."""
        products = self.fetch_all_products()
        filtered = []
        for p in products:
            if active_only and not p["is_active"]:
                continue
            if category_id and p["category_id"] != str(category_id):
                continue
            if search and search.lower() not in p["name"].lower():
                continue
            filtered.append(p)
        return filtered
