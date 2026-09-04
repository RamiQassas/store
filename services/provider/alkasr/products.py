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
            active_val = item.get("is_active")
            if active_val is None:
                active_val = item.get("available", True)
                
            if isinstance(active_val, str):
                is_active = active_val.strip().lower() not in ("0", "false", "no", "null", "")
            else:
                is_active = bool(active_val)

            qty_values = item.get("qty_values")
            qty_min = None
            qty_max = None
            qty_list = []
            
            if qty_values is None:
                qty_min = 1
                qty_max = 1
            elif isinstance(qty_values, list):
                qty_list = [str(x) for x in qty_values]
            elif isinstance(qty_values, dict):
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
                if isinstance(cost_price, (int, float)):
                    cost_price = f"{Decimal(str(cost_price)):.8f}"
                else:
                    cp = str(cost_price).strip()
                    if not cp:
                        cp = "0.00"
                    cost_price = f"{Decimal(cp):.8f}"
            except Exception:
                cost_price = "0.00000000"

            params = item.get("params") or item.get("parameters") or item.get("fields") or []

            parsed_products.append({
                "remote_id": remote_id,
                "name": name,
                "cost_price": cost_price,
                "product_type": product_type,
                "is_active": is_active,
                "qty_min": int(qty_min) if qty_min is not None else None,
                "qty_max": int(qty_max) if qty_max is not None else None,
                "qty_list": qty_list if isinstance(qty_list, list) else [],
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
