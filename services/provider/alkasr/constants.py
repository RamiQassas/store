"""
Alkasr VIP API Constants and Response Codes.
"""

DEFAULT_BASE_URL = "https://api.alkasr-vip.com/client/api/"
DEFAULT_TIMEOUT = 8  # seconds

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
    502: "Bad Gateway / بوابة المزود غير متوفرة حالياً",
    503: "Service Unavailable / خدمة المزود غير متاحة مؤقتاً",
    504: "Gateway Timeout / انتهت مهلة الاتصال بسيرفر المزود",
    520: "Web Server Returned Unknown Error / سيرفر المزود أرجع استجابة غير متوقعة",
    521: "سيرفر المزود (الكاسر VIP) متوقف مؤقتاً أو تحت الصيانة من طرفهم (Cloudflare 521: Web Server Is Down)",
    522: "Connection Timed Out / تعذر الوصول لسيرفر المزود (مهلة الاتصال انتهت)",
    524: "A Timeout Occurred / استغرق سيرفر المزود وقتاً أطول من المعتاد للاستجابة",
}

# Order Status Mapping (Provider status -> Internal System Status)
PROVIDER_STATUS_MAP = {
    "0": "pending",
    0: "pending",
    "pending": "pending",
    "waiting": "pending",
    "wait": "pending",
    "1": "processing",
    1: "processing",
    "processing": "processing",
    "in_progress": "processing",
    "2": "completed",
    2: "completed",
    "accept": "completed",
    "accepted": "completed",
    "completed": "completed",
    "done": "completed",
    "success": "completed",
    "successful": "completed",
    "approved": "completed",
    "3": "failed",
    3: "failed",
    "4": "failed",
    4: "failed",
    "reject": "failed",
    "rejected": "failed",
    "refuse": "failed",
    "refused": "failed",
    "declined": "failed",
    "decline": "failed",
    "canceled": "failed",
    "cancelled": "failed",
    "cancel": "failed",
    "failed": "failed",
    "fail": "failed",
    "failure": "failed",
    "error": "failed",
    "err": "failed",
    "refunded": "refunded",
    "refund": "refunded",
    "unsuccessful": "failed",
    "invalid": "failed",
    "-1": "failed",
    -1: "failed",
    "مرفوض": "failed",
    "ملغي": "failed",
    "ملغى": "failed",
    "فشل": "failed",
    "فاشل": "failed",
    "مكتمل": "completed",
    "تم التنفيذ": "completed",
    "تم الشحن": "completed",
}
