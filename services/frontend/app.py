from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, send_from_directory, session
from flask_sock import Sock
from websocket import create_connection
import requests
from datetime import datetime
import uuid
import os
import io
import base64
from pathlib import Path
import threading
import time
import logging
import urllib.parse
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

app = Flask(__name__)
sock = Sock(app)
# Configure session secret key (use environment variable or generate one)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
# Session cookie settings
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Feature flags configuration
FEATURE_FLAGS = {
    'browser_type': True,
    'headless': True,
    'viewport_width': True,
    'viewport_height': True,
    'wait_until': True,
    'wait_timeout': True,
    'user_agent': True,
    'full_page': True,
    'image_type': True,
    'quality': True,
    'wait_for_selector': True,
    'clip_fields': True,
    'record_duration': True,
    'scroll_enabled': True,
    'scroll_speed': True,
    'scroll_up_after': True,
    'scroll_timeout': True,
    'dismiss_popups': True,
}

# Backend API configuration (env-driven)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
# Optional public WS base URL for browsers (e.g., when behind TLS/proxy)
BACKEND_WS_PUBLIC_URL = os.getenv("BACKEND_WS_PUBLIC_URL", "")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "2"))
GLUETUN_API_URL = os.getenv("GLUETUN_API_URL", "http://localhost:8001")

# In-memory storage for tasks: {session_id: {task_id: task_data}}
# Each user session gets their own task dictionary
tasks = {}  # Structure: {session_id: {task_id: task_data}}
tasks_lock = threading.Lock()

# Create directory for storing media files (env-driven)
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
try:
    MEDIA_DIR.mkdir(exist_ok=True, parents=True)
    # Test write permissions
    test_file = MEDIA_DIR / ".write_test"
    test_file.touch()
    test_file.unlink()
    logger.info(f"Media directory initialized successfully at {MEDIA_DIR}")
except PermissionError as e:
    logger.error(f"Permission denied when creating or writing to media directory {MEDIA_DIR}: {e}")
    logger.error(f"Current user: {os.getuid() if hasattr(os, 'getuid') else 'unknown'}")
    logger.error(f"Directory permissions: {oct(MEDIA_DIR.stat().st_mode) if MEDIA_DIR.exists() else 'directory does not exist'}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize media directory {MEDIA_DIR}: {e}")
    raise

# HTTP session with retries
http = requests.Session()
retries = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=0.5,
    status_forcelist=[502, 503, 504],
    allowed_methods=["GET", "POST"],
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
http.mount("http://", adapter)
http.mount("https://", adapter)

# Constants
ALLOWED_TASK_TYPES = {"screenshot", "recording"}
MEDIA_CACHE_MAX_AGE = int(os.getenv("MEDIA_CACHE_MAX_AGE", "3600"))


def _get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr


def _is_valid_url(url_str):
    try:
        parsed = urllib.parse.urlparse(url_str)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _safe_media_path(filename):
    try:
        base = MEDIA_DIR.resolve()
        candidate = (MEDIA_DIR / filename).resolve()
        if os.path.commonpath([str(base), str(candidate)]) == str(base):
            return candidate
        return None
    except Exception:
        return None


def _gluetun_url(path: str) -> str:
    base = GLUETUN_API_URL.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _proxy_gluetun_json(path: str, description: str):
    url = _gluetun_url(path)
    try:
        response = http.get(url, timeout=(5, 30))
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if getattr(exc, "response", None) is not None else 502
        payload = None
        if getattr(exc, "response", None) is not None:
            try:
                payload = exc.response.json()
            except ValueError:
                payload = {"message": (exc.response.text or "")[:200]}
        logger.warning("Gluetun API responded with HTTP %s for %s", status_code, url)
        return jsonify({
            "error": f"{description} request failed",
            "status": status_code,
            "details": payload,
        }), status_code
    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to reach Gluetun API at %s: %s", url, exc)
        return jsonify({
            "error": f"Unable to reach Gluetun API for {description}",
            "details": str(exc),
        }), 502

    try:
        data = response.json()
    except ValueError:
        logger.warning("Gluetun API returned non-JSON payload for %s", url)
        return jsonify({"error": "Invalid JSON received from Gluetun API"}), 502

    return jsonify(data)


def _get_session_id():
    """
    Get or create a session ID for the current user.
    Session ID is stored in Flask session (cookie-based).
    """
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        logger.debug(f"Created new session ID: {session['session_id']}")
    return session['session_id']


def _get_user_tasks(session_id):
    """
    Get the task dictionary for a specific session.
    Creates an empty dictionary if it doesn't exist.
    """
    with tasks_lock:
        if session_id not in tasks:
            tasks[session_id] = {}
        return tasks[session_id]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/submit')
def submit():
    return render_template(
        'submit.html',
        flags=FEATURE_FLAGS,
        gluetun_locations_url=url_for('proxy_gluetun_locations'),
        gluetun_servers_url=url_for('proxy_gluetun_servers'),
    )


@app.route('/tasks')
def tasks_view():
    session_id = _get_session_id()
    user_tasks = _get_user_tasks(session_id)
    sorted_tasks = sorted(user_tasks.values(), key=lambda x: x['timestamp'], reverse=True)
    return render_template('tasks.html', tasks=sorted_tasks, backend_ws_public_url=BACKEND_WS_PUBLIC_URL)


@app.route('/task/<task_id>')
def task_detail(task_id):
    session_id = _get_session_id()
    user_tasks = _get_user_tasks(session_id)
    task = user_tasks.get(task_id)
    if not task:
        return "Task not found", 404
    return render_template('task_detail.html', task=task, backend_ws_public_url=BACKEND_WS_PUBLIC_URL)


@app.route('/api/submit', methods=['POST'])
def api_submit():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON body'}), 400

    url = data.get('url')
    if not url or not _is_valid_url(url):
        return jsonify({'error': 'A valid http(s) url is required'}), 400

    raw_task_types = data.get('task_types', [])
    if not isinstance(raw_task_types, list) or not raw_task_types:
        return jsonify({'error': 'task_types must be a non-empty list'}), 400
    task_types = [t for t in raw_task_types if t in ALLOWED_TASK_TYPES]
    if not task_types:
        return jsonify({'error': 'No valid task_types provided'}), 400
    
    # Client metadata (not shown to user)
    client_metadata = {
        'user_agent': request.headers.get('User-Agent'),
        'ip_address': _get_client_ip(),
    }
    
    results = {}
    
    # Build request payload for backend
    payload = {k: v for k, v in data.items() if k != 'task_types' and v is not None and v != ''}
    # Normalize image_type and quality to satisfy backend validation
    img_type = payload.get('image_type')
    if img_type == 'jpg':
        payload['image_type'] = 'jpeg'
    if payload.get('image_type') == 'png':
        payload.pop('quality', None)
    
    # Get user's session ID
    session_id = _get_session_id()
    user_tasks = _get_user_tasks(session_id)
    
    # Process screenshot tasks via queue
    if 'screenshot' in task_types:
        try:
            headers = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}
            enqueue_resp = http.post(
                f"{BACKEND_URL}/queue/screenshot",
                json=payload,
                headers=headers,
                timeout=(5, 15)
            )
            enqueue_resp.raise_for_status()
            enqueue_data = enqueue_resp.json()
            backend_task_id = enqueue_data.get('task_id')
            task = {
                'id': backend_task_id,
                'type': 'screenshot',
                'url': payload.get('url'),
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'status': 'queued',
                'request_params': payload.copy(),
                'metadata': client_metadata
            }
            with tasks_lock:
                user_tasks[backend_task_id] = task
            results['screenshot'] = {'task_id': backend_task_id, 'status': 'queued'}
        except Exception as e:
            logger.exception("Failed to enqueue screenshot task")
            results['screenshot'] = {'status': 'error', 'message': str(e)}
    
    # Process recording tasks via queue
    if 'recording' in task_types:
        try:
            headers = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}
            enqueue_resp = http.post(
                f"{BACKEND_URL}/queue/record",
                json=payload,
                headers=headers,
                timeout=(5, 15)
            )
            enqueue_resp.raise_for_status()
            enqueue_data = enqueue_resp.json()
            backend_task_id = enqueue_data.get('task_id')
            task = {
                'id': backend_task_id,
                'type': 'recording',
                'url': payload.get('url'),
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'status': 'queued',
                'request_params': payload.copy(),
                'metadata': client_metadata
            }
            with tasks_lock:
                user_tasks[backend_task_id] = task
            results['recording'] = {'task_id': backend_task_id, 'status': 'queued'}
        except Exception as e:
            logger.exception("Failed to enqueue recording task")
            results['recording'] = {'status': 'error', 'message': str(e)}
    
    return jsonify(results)


@app.route('/api/task/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    session_id = _get_session_id()
    user_tasks = _get_user_tasks(session_id)
    
    with tasks_lock:
        task = user_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    # Delete associated file (safely)
    result_file = task.get('result_file', '')
    safe_path = _safe_media_path(result_file)
    if result_file and safe_path and safe_path.exists():
        try:
            os.remove(safe_path)
        except Exception:
            logger.warning("Failed to delete media file %s", safe_path)
    
    # Remove from memory
    with tasks_lock:
        if task_id in user_tasks:
            del user_tasks[task_id]
    
    return jsonify({'status': 'deleted'})


@app.route('/api/task/<task_id>', methods=['GET'])
def get_task(task_id):
    session_id = _get_session_id()
    user_tasks = _get_user_tasks(session_id)
    
    with tasks_lock:
        task = user_tasks.get(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        # Return a shallow copy safe for JSON
        safe_task = {
            'id': task.get('id'),
            'type': task.get('type'),
            'url': task.get('url'),
            'timestamp': task.get('timestamp'),
            'status': task.get('status'),
            'result_file': task.get('result_file'),
            'result_format': task.get('result_format'),
            'error': task.get('error'),
        }
    return jsonify({'task': safe_task})


@app.route('/media/<path:filename>')
def serve_media(filename):
    safe_path = _safe_media_path(filename)
    if not safe_path or not safe_path.exists():
        return "File not found", 404
    return send_from_directory(str(MEDIA_DIR), filename, conditional=True, max_age=MEDIA_CACHE_MAX_AGE)


@app.route('/api/gluetun/servers', methods=['GET'])
def proxy_gluetun_servers():
    """Expose the Gluetun server list through the frontend."""
    return _proxy_gluetun_json("/servers", "Server list")


@app.route('/api/gluetun/locations', methods=['GET'])
def proxy_gluetun_locations():
    """Expose Gluetun location metadata through the frontend."""
    return _proxy_gluetun_json("/locations", "Location list")


@sock.route('/ws/tasks/<task_id>')
def proxy_task_ws(ws, task_id):
    logger.info(f"WS: Client connected for task {task_id}")
    # Derive backend WS URL from BACKEND_URL
    backend_ws_url = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://')
    target_url = f"{backend_ws_url}/ws/tasks/{task_id}"
    
    try:
        # Connect to backend
        logger.info(f"WS: Connecting to backend {target_url}")
        backend_ws = create_connection(target_url, timeout=5)
        logger.info(f"WS: Connected to backend for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to connect to backend WS {target_url}: {e}")
        try:
            ws.close()
        except:
            pass
        return

    # Bridge threads
    def forward_backend_to_client():
        logger.info(f"WS: Starting backend->client forwarder for {task_id}")
        try:
            while True:
                data = backend_ws.recv()
                if not data:
                    logger.info(f"WS: Backend closed connection for {task_id}")
                    break
                try:
                    ws.send(data)
                except Exception as e:
                    logger.warning(f"WS: Failed to send to client: {e}")
                    break
        except Exception as e:
            logger.warning(f"WS: Error reading from backend: {e}")
            pass
        finally:
            try:
                ws.close()
            except:
                pass
            logger.info(f"WS: Backend->client forwarder ended for {task_id}")

    t = threading.Thread(target=forward_backend_to_client, daemon=True)
    t.start()

    try:
        while True:
            data = ws.receive()
            if not data:
                logger.info(f"WS: Client disconnected for {task_id}")
                break
            try:
                backend_ws.send(data)
            except Exception:
                break
    except Exception as e:
        logger.warning(f"WS: Client loop error: {e}")
        pass
    finally:
        try:
            backend_ws.close()
        except:
            pass
        logger.info(f"WS: Connection handler ended for {task_id}")



if __name__ == '__main__':
    debug = os.getenv("DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=debug, port=port, use_reloader=False)

# --- Background polling of backend queue ---
_poller_thread = None
_stop_event = threading.Event()

def _poll_backend_queue():
    while not _stop_event.is_set():
        try:
            # Collect all pending tasks from all sessions
            pending = []
            with tasks_lock:
                for session_id, user_tasks in tasks.items():
                    for tid, task in user_tasks.items():
                        if task.get('status') in ('queued', 'running'):
                            task_copy = task.copy()
                            task_copy['_session_id'] = session_id  # Track which session it belongs to
                            pending.append(task_copy)
        except Exception:
            pending = []

        for t in pending:
            tid = t['id']
            ttype = t['type']
            session_id = t.get('_session_id')
            if not session_id:
                continue
                
            try:
                status_resp = http.get(f"{BACKEND_URL}/queue/{tid}", timeout=(5, 10))
                if status_resp.status_code == 404:
                    continue
                status_data = status_resp.json()
                new_status = status_data.get('status')

                with tasks_lock:
                    user_tasks = tasks.get(session_id, {})
                    if tid not in user_tasks:
                        continue  # Task was deleted or session doesn't exist

                if new_status in ('queued', 'running'):
                    with tasks_lock:
                        user_tasks = tasks.get(session_id, {})
                        if tid in user_tasks:
                            user_tasks[tid]['status'] = new_status
                    continue

                if new_status == 'failed':
                    with tasks_lock:
                        user_tasks = tasks.get(session_id, {})
                        if tid in user_tasks:
                            user_tasks[tid]['status'] = 'failed'
                            user_tasks[tid]['error'] = status_data.get('error')
                    continue

                if new_status == 'completed':
                    # Fetch result binary (streaming)
                    result_resp = http.get(f"{BACKEND_URL}/queue/{tid}/result", stream=True, timeout=(5, 180))
                    result_resp.raise_for_status()
                    content_type = result_resp.headers.get('Content-Type', '')
                    content_type_base = content_type.split(';', 1)[0].strip().lower()
                    if ttype == 'screenshot':
                        if content_type_base == 'image/png':
                            ext = 'png'
                        elif content_type_base in ('image/jpeg', 'image/jpg'):
                            ext = 'jpg'
                        else:
                            ext = 'png'
                        filename = f"{tid}.{ext}"
                    else:
                        if content_type_base == 'video/mp4':
                            ext = 'mp4'
                        else:
                            ext = 'webm'
                        filename = f"{tid}.{ext}"
                    filepath = MEDIA_DIR / filename
                    total_bytes = 0
                    with open(filepath, 'wb') as f:
                        for chunk in result_resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                try:
                                    total_bytes += len(chunk)
                                except Exception:
                                    pass
                    with tasks_lock:
                        user_tasks = tasks.get(session_id, {})
                        if tid in user_tasks:
                            user_tasks[tid]['status'] = 'completed'
                            user_tasks[tid]['result_file'] = filename
                            user_tasks[tid]['result_format'] = filename.split('.')[-1]
                            try:
                                if total_bytes == 0:
                                    total_bytes = os.path.getsize(filepath)
                            except Exception:
                                total_bytes = None
                            user_tasks[tid]['result_size'] = total_bytes
            except Exception as exc:
                logger.warning("Polling error for task %s (%s): %s", tid, ttype, exc, exc_info=True)
                continue

        # Allow graceful shutdown while sleeping
        _stop_event.wait(POLL_INTERVAL_SECONDS)

def _start_poller_impl():
    global _poller_thread
    if _poller_thread is None or not _poller_thread.is_alive():
        _stop_event.clear()
        _poller_thread = threading.Thread(target=_poll_backend_queue, daemon=True)
        _poller_thread.start()

# Prefer modern hook if available (Flask 2.2+)
if hasattr(app, 'before_serving'):
    @app.before_serving
    def _start_poller():
        _start_poller_impl()
else:
    # Fallback: start on first incoming request (idempotent)
    @app.before_request
    def _start_poller_before_request():
        _start_poller_impl()


@app.teardown_appcontext
def _stop_poller(exception):
    try:
        _stop_event.set()
        if _poller_thread and _poller_thread.is_alive():
            _poller_thread.join(timeout=0.5)
    except Exception:
        pass
