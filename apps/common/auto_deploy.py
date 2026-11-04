import os
import sys
import json
import hashlib
import hmac
import logging
import threading
import time
import subprocess
from pathlib import Path
import requests
from django.conf import settings
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_auto_deploy_thread_started = False
STATE_FILE = Path(settings.BASE_DIR) / ".auto_deploy_state.json"


def is_auto_deploy_enabled():
    """
    Returns True if auto deploy (automatic instant sync with Master) is enabled.
    Checks cache first, then persistent file state. Defaults to True.
    """
    from django.core.cache import cache
    cached = cache.get("auto_deploy_is_enabled")
    if cached is not None:
        return bool(cached)

    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                enabled = bool(data.get("enabled", True))
                cache.set("auto_deploy_is_enabled", enabled, 300)
                cache.set("auto_deploy_paused", not enabled, 300)
                return enabled
        except Exception as e:
            logger.debug(f"Error reading auto deploy state file: {e}")

    # Fallback to legacy cache key
    if cache.get("auto_deploy_paused"):
        return False
    return True


def set_auto_deploy_enabled(enabled: bool):
    """
    Persistently sets whether auto-deploy is enabled or disabled (paused).
    """
    from django.core.cache import cache
    enabled = bool(enabled)
    cache.set("auto_deploy_is_enabled", enabled, 300)
    if not enabled:
        cache.set("auto_deploy_paused", True, 300)
    else:
        cache.delete("auto_deploy_paused")

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled, "updated_at": time.time()}, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist auto deploy state: {e}")

    if enabled:
        start_auto_deploy_background_thread()


def get_local_commit_sha():
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(settings.BASE_DIR), capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def get_remote_commit_sha(bypass_cache=False):
    from django.core.cache import cache
    cache_key = "github_remote_master_sha"
    if not bypass_cache:
        cached_sha = cache.get(cache_key)
        if cached_sha:
            return cached_sha

    # 1. Primary method: git ls-remote (fast, highly reliable, immune to GitHub REST API 60 req/hr rate limits)
    try:
        res = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/master"],
            cwd=str(settings.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=8
        )
        if res.returncode == 0 and res.stdout.strip():
            sha = res.stdout.strip().split()[0]
            if len(sha) == 40:
                cache.set(cache_key, sha, 60)
                return sha
    except Exception as e:
        logger.debug(f"Git ls-remote error: {e}")

    # 2. Fallback method: GitHub REST API
    try:
        headers = {
            "User-Agent": "Raqamiyat-AutoDeploy/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        token = os.environ.get("GITHUB_TOKEN") or getattr(settings, "GITHUB_TOKEN", None)
        if token:
            headers["Authorization"] = f"token {token}"
        res = requests.get("https://api.github.com/repos/RamiQassas/store/commits/master", headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            sha = data.get("sha")
            if sha:
                cache.set(cache_key, sha, 60)
                return sha
        else:
            logger.warning(f"GitHub API commit fetch status {res.status_code}: {res.text[:150]}")
    except Exception as e:
        logger.debug(f"GitHub SHA fetch error: {e}")

    return None


def check_update_status(bypass_cache=False):
    """
    Returns a unified dict summarizing update status between local and remote master.
    """
    from django.core.cache import cache
    cache_key = "system_update_status_summary"
    if not bypass_cache:
        cached = cache.get(cache_key)
        if cached:
            cached["auto_deploy_enabled"] = is_auto_deploy_enabled()
            cached["is_paused"] = not cached["auto_deploy_enabled"]
            return cached

    local_sha = get_local_commit_sha() or ""
    remote_sha = get_remote_commit_sha(bypass_cache=bypass_cache) or ""

    has_update = bool(remote_sha and local_sha and remote_sha.strip().lower() != local_sha.strip().lower())
    is_up_to_date = bool(remote_sha and local_sha and remote_sha.strip().lower() == local_sha.strip().lower())
    auto_enabled = is_auto_deploy_enabled()

    result = {
        "local_sha": local_sha,
        "short_local_sha": local_sha[:7] if local_sha else "",
        "remote_sha": remote_sha,
        "short_remote_sha": remote_sha[:7] if remote_sha else "",
        "has_update": has_update,
        "is_up_to_date": is_up_to_date,
        "auto_deploy_enabled": auto_enabled,
        "is_paused": not auto_enabled,
    }
    cache.set(cache_key, result, 60)
    return result


def restart_process_soon():
    def _exit():
        time.sleep(1.5)
        logger.info("🔄 [AUTO-DEPLOY] Gracefully reloading server workers...")

        # 1. Touch wsgi.py and asgi.py
        try:
            for f in ["wsgi.py", "asgi.py"]:
                target_path = os.path.join(str(settings.BASE_DIR), "config", f)
                if os.path.exists(target_path):
                    os.utime(target_path, None)
        except Exception as e:
            logger.debug(f"Touch wsgi/asgi error: {e}")

        # 2. Send SIGHUP to Gunicorn parent master process (os.getppid())
        try:
            import signal
            ppid = os.getppid()
            if ppid > 1:
                os.kill(ppid, signal.SIGHUP)
                logger.info(f"🔄 [AUTO-DEPLOY] Sent SIGHUP to Gunicorn master (PPID: {ppid})")
        except Exception as e_hup:
            logger.debug(f"Signal SIGHUP error: {e_hup}")

        # 3. Try pkill / systemctl reload
        try:
            subprocess.run(["pkill", "-HUP", "-f", "gunicorn"], timeout=3)
        except Exception:
            pass
        try:
            subprocess.run(["systemctl", "reload", "gunicorn"], timeout=3)
        except Exception:
            pass

        # 4. Gracefully exit THIS worker if not PID 1
        # Gunicorn master will immediately fork a brand new worker with fresh code from disk!
        current_pid = os.getpid()
        if current_pid > 1:
            logger.info(f"🔄 [AUTO-DEPLOY] Worker {current_pid} recycling itself to reload code...")
            time.sleep(1)
            os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()


def apply_git_update():
    """
    Immediately fetches and applies latest changes from origin/master,
    runs migrations, collects static files, seeds essential data, and reloads server.
    Uses distributed lock to prevent multiple workers from running git reset concurrently.
    """
    from django.core.cache import cache
    lock_acquired = cache.add("auto_deploy_exec_lock", "locked", timeout=180)
    if not lock_acquired:
        logger.info("🚀 [AUTO-DEPLOY] Update already being applied by another worker.")
        return False, "Update already in progress"

    logger.info("🚀 [AUTO-DEPLOY] Applying updates from origin/master...")
    cache.delete("github_remote_master_sha")
    cache.delete("system_update_status_summary")

    success = False
    output = ""
    py_bin = sys.executable or "python"
    try:
        cmd = f"git config --global --add safe.directory '*' && git fetch origin master && git reset --hard origin/master && \"{py_bin}\" manage.py migrate --noinput && \"{py_bin}\" manage.py collectstatic --noinput && \"{py_bin}\" manage.py setup_flagship_storefront"
        proc = subprocess.run(cmd, shell=True, cwd=str(settings.BASE_DIR), capture_output=True, text=True, timeout=240)
        logger.info(f"🚀 [AUTO-DEPLOY] Output: {proc.stdout[:300]}")
        if proc.stderr:
            logger.warning(f"🚀 [AUTO-DEPLOY] Stderr: {proc.stderr[:300]}")
        success = (proc.returncode == 0)
        output = (proc.stdout or "") + "\n[STDERR]\n" + (proc.stderr or "")
    except Exception as e:
        logger.error(f"❌ [AUTO-DEPLOY] Failed to apply update: {e}")
        output = str(e)

    cache.delete("auto_deploy_exec_lock")
    if success:
        restart_process_soon()
    return success, output


def auto_deploy_poller():
    logger.info("🔄 [AUTO-DEPLOY] Background GitHub polling thread started (15s instant check).")
    time.sleep(10)

    last_synced_sha = None
    last_sync_time = 0

    while True:
        try:
            if not is_auto_deploy_enabled():
                time.sleep(15)
                continue

            local_sha = get_local_commit_sha()
            remote_sha = get_remote_commit_sha(bypass_cache=True)

            now_ts = time.time()
            if remote_sha and local_sha and remote_sha.strip().lower() != local_sha.strip().lower():
                if remote_sha == last_synced_sha and (now_ts - last_sync_time) < 300:
                    time.sleep(15)
                    continue

                last_synced_sha = remote_sha
                last_sync_time = now_ts
                logger.info(f"🚀 [AUTO-DEPLOY] New commit detected on Master ({remote_sha[:7]}). Applying update immediately to server...")
                apply_git_update()
        except Exception as e:
            logger.debug(f"Auto deploy loop exception: {e}")

        time.sleep(15)


def start_auto_deploy_background_thread():
    global _auto_deploy_thread_started
    if _auto_deploy_thread_started:
        return
    _auto_deploy_thread_started = True
    t = threading.Thread(target=auto_deploy_poller, daemon=True)
    t.start()


@require_POST
@csrf_exempt
def github_auto_deploy_view(request):
    """GitHub webhook and deployment endpoint, active when AUTO_DEPLOY_ENABLED."""
    if not getattr(settings, "AUTO_DEPLOY_ENABLED", True) or not getattr(settings, "GITHUB_WEBHOOK_SECRET", ""):
        return HttpResponseNotFound()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        return HttpResponseForbidden("Missing webhook signature")

    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return HttpResponseForbidden("Invalid webhook signature")

    success, output = apply_git_update()
    if success:
        return JsonResponse({"status": "success", "message": "Deployed successfully", "output": output[:300]})
    return JsonResponse({"status": "error", "message": output}, status=500)
