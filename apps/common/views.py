import logging
from django.shortcuts import render
from django.http import JsonResponse

logger = logging.getLogger(__name__)

def csrf_failure(request, reason=""):
    """
    Custom CSRF failure handler.
    Instead of showing a raw 403 debug crash page, it gracefully handles
    expired/rotated tokens and renders a user-friendly page with auto-retry.
    """
    logger.warning(f"[CSRF Failure] Path: {request.path}, Method: {request.method}, Reason: {reason}")

    # For API or AJAX requests, return a clean JSON response
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return JsonResponse({
            "error": "csrf_failure",
            "message": "انتهت صلاحية رمز الأمان (CSRF). يرجى تحديث الصفحة والمحاولة مجدداً.",
            "reason": reason
        }, status=403)

    # For standard browser requests:
    retry_url = request.path or "/"
    
    return render(request, "site/v3/csrf_error.html", {
        "reason": reason,
        "retry_url": retry_url,
    }, status=403)
