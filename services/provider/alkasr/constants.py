"""
Alkasr VIP API Constants and Response Codes.
"""

DEFAULT_BASE_URL = "https://api.alkasr-vip.com/client/api"
DEFAULT_TIMEOUT = 30  # seconds

# Endpoint paths relative to Base URL
ENDPOINT_PROFILE = "/profile"
ENDPOINT_PRODUCTS = "/products"
ENDPOINT_NEW_ORDER = "/newOrder"
ENDPOINT_CHECK_ORDER = "/check"

# Error Codes Mapping
ERROR_CODES = {
    100: "Insufficient Balance / الرصيد غير كافٍ في المزود",
    105: "Quantity Not Available / الكمية غير متوفرة",
    106: "Quantity Not Allowed / الكمية غير مسموح بها",
    107: "Player Blocked / حسـاب اللاعب محظور",
    108: "2FA Required / تتطلب المصادقة الثنائية",
    109: "Product Deleted / المنتج محذوف لدى المزود",
    110: "Product Unavailable / المنتج غير متوفر حالياً",
    111: "Retry After One Minute / يرجى إعادة المحاولة بعد دقيقة",
    112: "Quantity Too Small / الكمية أقل من الحد الأدنى",
    113: "Quantity Too Large / الكمية أكبر من الحد الأقصى",
    114: "Unknown Provider Error / خطأ غير معروف من المزود",
    120: "API Token Required / مفتاح الوصول مطلوب",
    121: "Invalid Token / مفتاح الوصول غير صحيح",
    122: "Action Not Allowed / غير مصرح بهذه العملية",
    123: "IP Not Allowed / عنوان IP غير مصرح له",
    130: "Provider Under Maintenance / المزود في حالة صيانة",
    500: "Provider Internal Error / خطأ داخلي في سيرفر المزود",
}

# Order Status Mapping (Provider status -> Internal System Status)
PROVIDER_STATUS_MAP = {
    "pending": "pending",
    "waiting": "processing",
    "wait": "processing",
    "processing": "processing",
    "accept": "completed",
    "accepted": "completed",
    "completed": "completed",
    "done": "completed",
    "reject": "rejected",
    "rejected": "rejected",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "failed": "failed",
    "refunded": "refunded",
}
