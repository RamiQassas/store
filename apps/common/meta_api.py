import logging
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
BASE_GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class MetaAdsService:
    """
    Unified client for Meta Marketing & Graph API.
    Fetches real-time advertising performance, campaign statuses, spend, CPC, and ROAS.
    """

    def __init__(self, ad_account_id: str, access_token: str):
        raw_id = (ad_account_id or "").strip()
        if raw_id and not raw_id.startswith("act_"):
            self.ad_account_id = f"act_{raw_id}"
        else:
            self.ad_account_id = raw_id
        self.access_token = (access_token or "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.ad_account_id and self.access_token)

    def get_insights(self, date_preset: str = "last_30d", force_refresh: bool = False) -> dict:
        """
        Fetches high-level advertising insights for the account.
        Supported date_presets: today, yesterday, last_7d, last_30d, this_month, maximum
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "لم يتم إدخال معرف حساب الإعلانات (Ad Account ID) أو رمز وصول الـ API.",
                "data": None,
            }

        cache_key = f"meta_insights_{self.ad_account_id}_{date_preset}"
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return {"success": True, "error": None, "data": cached_data, "cached": True}

        url = f"{BASE_GRAPH_URL}/{self.ad_account_id}/insights"
        params = {
            "access_token": self.access_token,
            "date_preset": date_preset,
            "fields": (
                "spend,impressions,reach,clicks,cpc,cpm,ctr,actions,action_values,purchase_roas"
            ),
        }

        try:
            res = requests.get(url, params=params, timeout=12)
            json_res = res.json()

            if res.status_code != 200 or "error" in json_res:
                err_msg = json_res.get("error", {}).get("message", "حدث خطأ أثناء التواصل مع سيرفرات ميتا.")
                logger.warning("Meta Graph API error for %s: %s", self.ad_account_id, err_msg)
                return {"success": False, "error": err_msg, "data": None}

            items = json_res.get("data", [])
            if not items:
                # No ad spend or impressions yet in the given timeframe
                data = {
                    "spend": 0.0,
                    "impressions": 0,
                    "reach": 0,
                    "clicks": 0,
                    "cpc": 0.0,
                    "cpm": 0.0,
                    "ctr": 0.0,
                    "purchases_count": 0,
                    "purchases_value": 0.0,
                    "roas": 0.0,
                }
            else:
                row = items[0]
                actions = row.get("actions", [])
                action_values = row.get("action_values", [])
                roas_list = row.get("purchase_roas", [])

                purchases_count = 0
                for a in actions:
                    if a.get("action_type") in ("purchase", "omni_purchase"):
                        purchases_count += int(a.get("value", 0))

                purchases_value = 0.0
                for av in action_values:
                    if av.get("action_type") in ("purchase", "omni_purchase"):
                        purchases_value += float(av.get("value", 0.0))

                roas_val = 0.0
                if roas_list and isinstance(roas_list, list):
                    roas_val = float(roas_list[0].get("value", 0.0))
                elif purchases_value > 0 and float(row.get("spend", 0.0)) > 0:
                    roas_val = round(purchases_value / float(row.get("spend", 1.0)), 2)

                data = {
                    "spend": float(row.get("spend", 0.0)),
                    "impressions": int(row.get("impressions", 0)),
                    "reach": int(row.get("reach", 0)),
                    "clicks": int(row.get("clicks", 0)),
                    "cpc": float(row.get("cpc", 0.0)),
                    "cpm": float(row.get("cpm", 0.0)),
                    "ctr": float(row.get("ctr", 0.0)),
                    "purchases_count": purchases_count,
                    "purchases_value": purchases_value,
                    "roas": roas_val,
                }

            cache.set(cache_key, data, timeout=300)
            return {"success": True, "error": None, "data": data, "cached": False}

        except Exception as e:
            logger.exception("Meta Ads insights connection failed: %s", e)
            return {"success": False, "error": f"تعذر الاتصال بواجهة ميتا: {str(e)}", "data": None}

    def get_campaigns(self, force_refresh: bool = False) -> dict:
        """
        Fetches campaigns list with status, objective, daily budget, and spend.
        """
        if not self.is_configured:
            return {"success": False, "error": "إعدادات الربط غير مكتملة.", "campaigns": []}

        cache_key = f"meta_campaigns_{self.ad_account_id}"
        if not force_refresh:
            cached_campaigns = cache.get(cache_key)
            if cached_campaigns is not None:
                return {"success": True, "error": None, "campaigns": cached_campaigns, "cached": True}

        url = f"{BASE_GRAPH_URL}/{self.ad_account_id}/campaigns"
        params = {
            "access_token": self.access_token,
            "fields": (
                "id,name,status,effective_status,objective,daily_budget,lifetime_budget,start_time,updated_time"
            ),
            "limit": 25,
        }

        try:
            res = requests.get(url, params=params, timeout=12)
            json_res = res.json()

            if res.status_code != 200 or "error" in json_res:
                err_msg = json_res.get("error", {}).get("message", "تعذر جلب الحملات من فيسبوك.")
                return {"success": False, "error": err_msg, "campaigns": []}

            raw_campaigns = json_res.get("data", [])
            campaigns = []
            for c in raw_campaigns:
                budget_raw = c.get("daily_budget") or c.get("lifetime_budget") or 0
                budget_formatted = float(budget_raw) / 100.0 if budget_raw else 0.0

                campaigns.append({
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "effective_status": c.get("effective_status"),
                    "is_active": c.get("effective_status") == "ACTIVE",
                    "objective": c.get("objective"),
                    "budget": budget_formatted,
                    "budget_type": "يومي" if c.get("daily_budget") else "إجمالي",
                    "start_time": c.get("start_time", "")[:10] if c.get("start_time") else "",
                })

            cache.set(cache_key, campaigns, timeout=300)
            return {"success": True, "error": None, "campaigns": campaigns, "cached": False}

        except Exception as e:
            logger.exception("Meta campaigns request failed: %s", e)
            return {"success": False, "error": str(e), "campaigns": []}
