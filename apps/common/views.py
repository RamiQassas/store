import logging
from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404
from django.utils.cache import patch_cache_control
from django.shortcuts import render
from django.http import JsonResponse
from django.views.static import serve

logger = logging.getLogger(__name__)

_PRIVATE_MEDIA_PREFIXES = ("kyc/", "deposit-proofs/", "withdrawal-proofs/", "chats/files/")


def protected_media(request, path):
    """Serve public media normally and restrict financial/KYC evidence by owner."""
    normalized_path = str(PurePosixPath(path)).lstrip("/")
    if normalized_path in {"", "."} or ".." in PurePosixPath(normalized_path).parts:
        raise Http404

    if normalized_path.startswith(_PRIVATE_MEDIA_PREFIXES):
        if not request.user.is_authenticated:
            raise Http404
        if not request.user.is_staff:
            if not _user_owns_private_media(request.user, normalized_path):
                raise Http404

    response = serve(request, normalized_path, document_root=settings.MEDIA_ROOT)
    if normalized_path.startswith(_PRIVATE_MEDIA_PREFIXES):
        patch_cache_control(response, private=True, no_cache=True, no_store=True)
    return response


def _user_owns_private_media(user, path):
    from apps.accounts.models import KYCRequest
    from apps.payments.models import DepositRequest, WithdrawalRequest
    from apps.support.models import ChatMessage

    if path.startswith("kyc/"):
        return KYCRequest.objects.filter(user=user).filter(
            identity_front=path
        ).exists() or KYCRequest.objects.filter(user=user).filter(
            identity_back=path
        ).exists() or KYCRequest.objects.filter(user=user).filter(
            selfie_verification=path
        ).exists()

    if path.startswith("deposit-proofs/"):
        for deposit in DepositRequest.all_objects.filter(user=user).only("proof_image", "metadata"):
            if deposit.proof_image and deposit.proof_image.name == path:
                return True
            if isinstance(deposit.metadata, dict) and _metadata_contains_media_path(deposit.metadata, path):
                return True
        return False

    if path.startswith("withdrawal-proofs/"):
        return WithdrawalRequest.all_objects.filter(user=user).filter(
            proof_image=path
        ).exists() or WithdrawalRequest.all_objects.filter(user=user).filter(
            proof_file=path
        ).exists()

    if path.startswith("chats/files/"):
        return ChatMessage.objects.filter(room__user=user, file=path).exists()

    return False


def _metadata_contains_media_path(value, path):
    if isinstance(value, dict):
        return any(_metadata_contains_media_path(item, path) for item in value.values())
    if isinstance(value, list):
        return any(_metadata_contains_media_path(item, path) for item in value)
    return str(value).removeprefix(settings.MEDIA_URL) == path

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
