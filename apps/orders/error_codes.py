"""
Provider Error Code Registry and Sanitization Utility.
Prevents leaking sensitive external provider messages (such as insufficient balance or internal credentials)
to customers, replacing them with standard polite error codes (e.g. ERR-100), while translating the true
reason for administrators and managers in the control panel.
"""

import re
from typing import Dict, Any, Tuple, Optional

# Master registry of provider error translations
PROVIDER_ERROR_REGISTRY = {
    100: {
        "code_tag": "ERR-100",
        "customer_message": "تعذر تنفيذ الطلب حالياً (رمز الخطأ: ERR-100)، يرجى مراجعة الدعم الفني أو المحاولة لاحقاً.",
        "admin_message": "الرصيد غير كافٍ في حساب المزود الخارجي (Insufficient Balance)",
        "admin_tip": "يرجى شحن وتغذية رصيد حسابك لدى المزود الخارجي لتتمكن من استئناف معالجة وتنفيذ الطلبات.",
        "keywords": [
            "insufficient balance", "الرصيد غير كاف", "رصيد المزود", "رصيدك غير كاف",
            "not enough balance", "low balance", "insufficient_balance", "balance error"
        ]
    },
    105: {
        "code_tag": "ERR-105",
        "customer_message": "الكمية المطلوبة غير متوفرة حالياً لدى مزود الخدمة (رمز الخطأ: ERR-105).",
        "admin_message": "الكمية غير متوفرة لدى المزود الخارجي (Quantity Not Available)",
        "admin_tip": "الكمية المطلوبة في الباقة غير متوفرة حالياً في مخزون المزود الخارجي.",
        "keywords": ["quantity not available", "الكمية غير متوفرة", "out of stock"]
    },
    106: {
        "code_tag": "ERR-106",
        "customer_message": "الكمية المحددة غير مسموح بها لهذا الطلب (رمز الخطأ: ERR-106).",
        "admin_message": "الكمية غير مسموح بها لدى المزود الخارجي (Quantity Not Allowed)",
        "admin_tip": "الكمية المحددة تخالف سياسات أو قيود المزود لهذا المنتج.",
        "keywords": ["quantity not allowed", "الكمية غير مسموح بها"]
    },
    107: {
        "code_tag": "ERR-107",
        "customer_message": "معرف الحساب المدخل غير صالح أو محظور لدى مزود الخدمة (رمز الخطأ: ERR-107).",
        "admin_message": "حساب اللاعب محظور أو مرفوض لدى المزود (Player Blocked)",
        "admin_tip": "حساب اللاعب المدخل من العميل محظور أو غير صالح لدى سيرفر اللعبة/المزود.",
        "keywords": ["player blocked", "حساب اللاعب محظور", "playerid محظور", "player_blocked"]
    },
    108: {
        "code_tag": "ERR-108",
        "customer_message": "يتطلب الطلب إجراءات تحقق أمنية إضافية (رمز الخطأ: ERR-108).",
        "admin_message": "المزود يتطلب تحقق ثنائي 2FA (Two-Factor Authentication Required)",
        "admin_tip": "حساب المتجر لدى المزود يتطلب إدخال رمز التحقق الثنائي (2FA) لتأكيد العمليات.",
        "keywords": ["2fa required", "المصادقة الثنائية", "تحقق 2fa", "two-factor"]
    },
    109: {
        "code_tag": "ERR-109",
        "customer_message": "المنتج المطلوب غير متاح حالياً (رمز الخطأ: ERR-109).",
        "admin_message": "المنتج محذوف أو غير موجود لدى المزود (Product Deleted)",
        "admin_tip": "تم حذف هذا المنتج من قائمة منتجات المزود أو تم تغيير معرفه.",
        "keywords": ["product deleted", "المنتج محذوف", "product not found"]
    },
    110: {
        "code_tag": "ERR-110",
        "customer_message": "الخدمة المطلوبة غير متوفرة مؤقتاً لدى مزود الخدمة (رمز الخطأ: ERR-110).",
        "admin_message": "المنتج غير متوفر حالياً لدى المزود (Product Unavailable)",
        "admin_tip": "المنتج معطل أو متوقف مؤقتاً من قبل المزود الخارجي.",
        "keywords": ["product unavailable", "المنتج غير متوفر حالياً", "service unavailable"]
    },
    111: {
        "code_tag": "ERR-111",
        "customer_message": "مزود الخدمة مشغول حالياً، يرجى المحاولة بعد قليل (رمز الخطأ: ERR-111).",
        "admin_message": "المزود يطلب إعادة المحاولة بعد دقيقة (Rate Limited / Retry After One Minute)",
        "admin_tip": "هناك ضغط طلبات كبير على المزود، يمكن إعادة إرسال الطلب بعد دقيقة.",
        "keywords": ["retry after one minute", "إعادة المحاولة بعد دقيقة", "حاول بعد دقيقة", "rate limited"]
    },
    112: {
        "code_tag": "ERR-112",
        "customer_message": "الكمية المدخلة أقل من الحد الأدنى المسموح به (رمز الخطأ: ERR-112).",
        "admin_message": "الكمية أقل من الحد الأدنى لدى المزود (Quantity Too Small)",
        "admin_tip": "الكمية المطلوبة في الطلب أقل من الحد الأدنى المقبول لدى المزود.",
        "keywords": ["quantity too small", "أقل من الحد الأدنى"]
    },
    113: {
        "code_tag": "ERR-113",
        "customer_message": "الكمية المدخلة تتجاوز الحد الأقصى المسموح به (رمز الخطأ: ERR-113).",
        "admin_message": "الكمية أكبر من الحد الأقصى لدى المزود (Quantity Too Large)",
        "admin_tip": "الكمية المطلوبة في الطلب تتجاوز الحد الأقصى المقبول لدى المزود.",
        "keywords": ["quantity too large", "أكبر من الحد الأقصى"]
    },
    120: {
        "code_tag": "ERR-120",
        "customer_message": "تعذر الاتصال بمزود الخدمة (رمز الخطأ: ERR-120).",
        "admin_message": "مفتاح الوصول للـ API مطلوب لدى المزود (API Token Required)",
        "admin_tip": "تأكد من إدخال API Token في إعدادات المزود في لوحة التحكم.",
        "keywords": ["api token required", "مفتاح الوصول مطلوب", "token required"]
    },
    121: {
        "code_tag": "ERR-121",
        "customer_message": "تعذر التحقق من مزود الخدمة (رمز الخطأ: ERR-121).",
        "admin_message": "مفتاح الوصول غير صالح أو منتهي (Invalid API Token)",
        "admin_tip": "قم بتحديث مفتاح API Token في إعدادات المزود في لوحة التحكم.",
        "keywords": ["invalid token", "token error", "مفتاح api غير صالح", "غير صحيح", "مفتاح الوصول غير صالح"]
    },
    122: {
        "code_tag": "ERR-122",
        "customer_message": "العملية غير مصرح بها حالياً (رمز الخطأ: ERR-122).",
        "admin_message": "العملية غير مصرح بها لدى المزود (Action Not Allowed)",
        "admin_tip": "الحساب لدى المزود لا يملك صلاحية تنفيذ هذا الإجراء.",
        "keywords": ["action not allowed", "غير مصرح بهذه العملية"]
    },
    123: {
        "code_tag": "ERR-123",
        "customer_message": "خطأ في تهيئة مزود الخدمة (رمز الخطأ: ERR-123).",
        "admin_message": "عنوان IP الخاص بالسيرفر غير مصرح له لدى المزود (IP Not Allowed)",
        "admin_tip": "أضف عنوان IP الخاص بسيرفر المتجر إلى القائمة البيضاء (IP Whitelist) لدى المزود.",
        "keywords": ["ip not allowed", "عنوان ip غير مصرح", "عنوان ip غير مسموح"]
    },
    130: {
        "code_tag": "ERR-130",
        "customer_message": "مزود الخدمة تحت الصيانة المجدولة حالياً (رمز الخطأ: ERR-130).",
        "admin_message": "سيرفر المزود في حالة صيانة مجدولة (Provider Under Maintenance)",
        "admin_tip": "المزود يقوم بأعمال صيانة دورية، سيتم استئناف الخدمة قريباً.",
        "keywords": ["provider under maintenance", "وضع الصيانة", "في حالة صيانة", "maintenance"]
    },
    500: {
        "code_tag": "ERR-500",
        "customer_message": "خطأ في معالجة الطلب لدى السيرفر (رمز الخطأ: ERR-500).",
        "admin_message": "خطأ داخلي في سيرفر المزود (Provider Internal Server Error)",
        "admin_tip": "فشل داخلي في سيرفر المزود الخارجي (HTTP 500)، يرجى مراجعة المزود.",
        "keywords": ["internal server error", "خطأ داخلي", "provider internal error", "500 internal"]
    }
}

# Sensitive balance phrases that MUST NEVER leak to customers under any circumstances
SENSITIVE_BALANCE_PATTERNS = [
    r"insufficient\s+balance",
    r"الرصيد\s+غير\s+كاف",
    r"رصيد\s+المزود",
    r"رصيدك\s+غير\s+كاف",
    r"not\s+enough\s+balance",
    r"low\s+balance",
    r"balance\s+error",
    r"insufficient_balance",
    r"insufficientbalance",
]


def detect_error_code(raw_data: Any, explicit_code: Optional[Any] = None) -> Optional[int]:
    """
    Extracts numerical error code from raw response, string, or explicit code.
    """
    if explicit_code is not None:
        try:
            c = int(explicit_code)
            if c != 0 and c != 200:
                return c
        except (ValueError, TypeError):
            pass

    if isinstance(raw_data, dict):
        for key in ("code", "error_code", "status_code", "err_code"):
            val = raw_data.get(key)
            if val is not None:
                try:
                    c = int(val)
                    if c != 0 and c != 200:
                        return c
                except (ValueError, TypeError):
                    pass

    # Search in text for ERR-XXX or (code: XXX) or similar
    text = str(raw_data or "")
    m = re.search(r"ERR-(\d+)", text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except (ValueError, TypeError):
            pass

    m2 = re.search(r"(?:code|خطأ|كود)\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    if m2:
        try:
            c = int(m2.group(1))
            if c != 200 and c != 0:
                return c
        except (ValueError, TypeError):
            pass

    # Keyword check: If text indicates insufficient balance, map directly to 100
    text_lower = text.lower()
    for pat in SENSITIVE_BALANCE_PATTERNS:
        if re.search(pat, text_lower):
            return 100

    # Keyword check across registry
    for code, info in PROVIDER_ERROR_REGISTRY.items():
        for kw in info["keywords"]:
            if kw in text_lower:
                return code

    return None


def sanitize_provider_error(raw_data: Any, error_code: Optional[Any] = None) -> Dict[str, Any]:
    """
    Main sanitizer function.
    Given any provider response, string, or error code, returns a dictionary containing:
    - is_error: bool
    - code_tag: str (e.g. 'ERR-100')
    - error_code: int or None
    - customer_message: Safe, polite message for customer
    - admin_message: Real translated reason for manager
    - admin_tip: Actionable recommendation for manager
    - raw_detail: Original technical text/data
    """
    raw_str = str(raw_data or "").strip()
    code = detect_error_code(raw_data, explicit_code=error_code)

    if code and code in PROVIDER_ERROR_REGISTRY:
        reg = PROVIDER_ERROR_REGISTRY[code]
        return {
            "is_error": True,
            "error_code": code,
            "code_tag": reg["code_tag"],
            "customer_message": reg["customer_message"],
            "admin_message": reg["admin_message"],
            "admin_tip": reg["admin_tip"],
            "raw_detail": raw_str,
        }

    # If code was numeric but not in our explicit dictionary
    if code:
        code_tag = f"ERR-{code}"
        return {
            "is_error": True,
            "error_code": code,
            "code_tag": code_tag,
            "customer_message": f"تعذر تنفيذ الطلب حالياً لدى مزود الخدمة (رمز الخطأ: {code_tag})، يرجى التواصل مع الدعم الفني.",
            "admin_message": f"خطأ من المزود الخارجي (رمز: {code_tag}): {raw_str[:120]}",
            "admin_tip": "يرجى مراجعة تفاصيل الاستجابة لدى المزود الخارجي للتحقق من سبب الرفض.",
            "raw_detail": raw_str,
        }

    # If no numerical code found, check if it's a known cancellation or error text
    if any(re.search(pat, raw_str.lower()) for pat in SENSITIVE_BALANCE_PATTERNS):
        reg = PROVIDER_ERROR_REGISTRY[100]
        return {
            "is_error": True,
            "error_code": 100,
            "code_tag": reg["code_tag"],
            "customer_message": reg["customer_message"],
            "admin_message": reg["admin_message"],
            "admin_tip": reg["admin_tip"],
            "raw_detail": raw_str,
        }

    # Generic error without known code
    return {
        "is_error": bool(raw_str),
        "error_code": None,
        "code_tag": "ERR-PROVIDER",
        "customer_message": "تعذر تنفيذ الطلب حالياً لدى مزود الخدمة، يرجى المحاولة لاحقاً أو مراجعة الدعم الفني.",
        "admin_message": f"استجابة غير معتادة من المزود: {raw_str[:150]}" if raw_str else "تعذر تنفيذ الطلب من قبل المزود الخارجي",
        "admin_tip": "راجع استجابة المزود الأخيرة في تفاصيل الطلب لمعرفة السبب.",
        "raw_detail": raw_str,
    }


def sanitize_text_for_customer(text: Optional[str]) -> str:
    """
    Sanitizes any arbitrary text destined for a customer.
    Replaces sensitive phrases like 'الرصيد غير كاف في المزود' or 'insufficient balance'
    with 'تعذر تنفيذ الطلب (رمز الخطأ: ERR-100)'.
    """
    if not text:
        return ""

    s = str(text).strip()
    s_lower = s.lower()

    # If contains balance sensitivity
    for pat in SENSITIVE_BALANCE_PATTERNS:
        if re.search(pat, s_lower):
            return "تعذر تنفيذ الطلب حالياً (رمز الخطأ: ERR-100)، يرجى مراجعة الدعم الفني."

    # If contains raw token or API key leaks
    if "token" in s_lower or "api_token" in s_lower or "unauthorized" in s_lower or "forbidden" in s_lower:
        return "تعذر التحقق من مزود الخدمة (رمز الخطأ: ERR-121)."

    return s
