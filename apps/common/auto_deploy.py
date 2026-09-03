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

def apply_git_update():
    logger.info("🚀 [AUTO-DEPLOY] New commit detected on GitHub master. Applying updates...")
    try:
        cmd = "git fetch origin master && git reset --hard origin/master && python manage.py migrate --noinput && python manage.py collectstatic --noinput && (pkill -f daphne || pkill -f gunicorn || true)"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        logger.info(f"🚀 [AUTO-DEPLOY] Output: {proc.stdout[:300]}")
        if proc.stderr:
            logger.warning(f"🚀 [AUTO-DEPLOY] Stderr: {proc.stderr[:300]}")
        return True, proc.stdout
    except Exception as e:
        logger.error(f"❌ [AUTO-DEPLOY] Failed to apply update: {e}")
        return False, str(e)

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
