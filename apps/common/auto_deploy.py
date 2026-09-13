import os
import sys
import logging
import threading
import time
import subprocess
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

_auto_deploy_thread_started = False

def get_local_commit_sha():
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True, timeout=3)
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None

def get_remote_commit_sha():
    try:
        headers = {"User-Agent": "Raqamiyat-AutoDeploy/1.0"}
        res = requests.get("https://api.github.com/repos/RamiQassas/store/commits/master", headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data.get("sha")
    except Exception as e:
        logger.debug(f"GitHub SHA fetch error: {e}")
    return None

def restart_process_soon():
    def _exit():
        time.sleep(1)
        logger.info("🔄 [AUTO-DEPLOY] Restarting ASGI container for clean code reload...")
        try:
            subprocess.run(["sh", "-c", "kill -9 1"], timeout=2)
        except Exception:
            pass
        import os
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()

def apply_git_update():
    logger.info("🚀 [AUTO-DEPLOY] New commit detected on GitHub master. Applying updates...")
    success = False
    output = ""
    try:
        cmd = "git config --global --add safe.directory '*' && git fetch origin master && git reset --hard origin/master && python manage.py migrate --noinput"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        logger.info(f"🚀 [AUTO-DEPLOY] Output: {proc.stdout[:300]}")
        if proc.stderr:
            logger.warning(f"🚀 [AUTO-DEPLOY] Stderr: {proc.stderr[:300]}")
        success = (proc.returncode == 0)
        output = proc.stdout
    except Exception as e:
        logger.error(f"❌ [AUTO-DEPLOY] Failed to apply update: {e}")
        output = str(e)
    
    if success:
        restart_process_soon()
    return success, output

def auto_deploy_poller():
    logger.info("🔄 [AUTO-DEPLOY] Background GitHub polling thread started.")
    time.sleep(15)
    
    while True:
        try:
            from django.core.cache import cache
            if cache.get("auto_deploy_paused"):
                time.sleep(30)
                continue

            local_sha = get_local_commit_sha()
            remote_sha = get_remote_commit_sha()
            
            if remote_sha and local_sha and remote_sha != local_sha:
                logger.info(f"🔄 [AUTO-DEPLOY] Remote SHA ({remote_sha[:7]}) differs from Local SHA ({local_sha[:7]}). Updating...")
                apply_git_update()
        except Exception as e:
            logger.debug(f"Auto deploy loop exception: {e}")
            
        time.sleep(45)

def start_auto_deploy_background_thread():
    global _auto_deploy_thread_started
    if _auto_deploy_thread_started:
        return
    _auto_deploy_thread_started = True
    t = threading.Thread(target=auto_deploy_poller, daemon=True)
    t.start()

@csrf_exempt
def github_auto_deploy_view(request):
    """Webhook endpoint for instant GitHub deployment."""
    success, output = apply_git_update()
    if success:
        return JsonResponse({"status": "success", "message": "Deployed successfully", "output": output[:300]})
    return JsonResponse({"status": "error", "message": output}, status=500)


@csrf_exempt
def paymera_diagnostics_view(request):
    import requests, base64
    from django.conf import settings
    from apps.payments.models import PaymentGatewayIntegration
    from apps.payments.paymera import PaymeraClient

    outbound_ip = "unknown"
    try:
        outbound_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
    except Exception as e:
        outbound_ip = f"Error: {e}"

    gw = PaymentGatewayIntegration.all_objects.filter(provider="paymera", is_active=True).first()
    gw_info = {
        "exists": bool(gw),
        "terminal_id": getattr(gw, "terminal_id", None),
        "api_key_len": len(getattr(gw, "api_key", "") or ""),
        "is_active": getattr(gw, "is_active", None),
        "mode": getattr(gw, "mode", None),
        "base_url": getattr(gw, "base_url", None),
    }

    client = PaymeraClient.from_integration(gw)
    test_result = {}
    try:
        res = client.create_payment(
            amount=1000,
            callback_url="https://raqamiyatapp.com/payments/paymera/callback/",
            trigger_url="https://raqamiyatapp.com/payments/paymera/trigger/",
            notes="Diagnostics Test",
        )
        test_result = {"success": True, "data": res}
    except Exception as e:
        test_result = {"success": False, "error": str(e)}

    raw_res = {}
    try:
        auth_bytes = f"{client.api_key}:".encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 PaymeraClient/4.0",
        }
        payload = {
            "amount": 1000,
            "terminalId": client.terminal_id,
            "callbackURL": "https://raqamiyatapp.com/payments/paymera/callback/",
            "triggerURL": "https://raqamiyatapp.com/payments/paymera/trigger/",
            "lang": "ar",
            "notes": "Diagnostics Raw Test",
        }
        resp = requests.post(f"{client.base_url}/api/create-payment", json=payload, headers=headers, timeout=15)
        raw_res = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp.text[:1000],
        }
    except Exception as e:
        raw_res = {"error": str(e)}

    return JsonResponse({
        "outbound_ip": outbound_ip,
        "gw_info": gw_info,
        "test_result": test_result,
        "raw_res": raw_res,
    })

