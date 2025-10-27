from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, send_from_directory
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
}

# Backend API configuration (env-driven)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
# Optional public WS base URL for browsers (e.g., when behind TLS/proxy)
BACKEND_WS_PUBLIC_URL = os.getenv("BACKEND_WS_PUBLIC_URL", "")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "2"))

# In-memory storage for tasks
tasks = {}
tasks_lock = threading.Lock()

# Create directory for storing media files (env-driven)
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
MEDIA_DIR.mkdir(exist_ok=True)

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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/submit')
def submit():
    return render_template('submit.html', flags=FEATURE_FLAGS)


@app.route('/tasks')
def tasks_view():
    with tasks_lock:
        sorted_tasks = sorted(tasks.values(), key=lambda x: x['timestamp'], reverse=True)
    return render_template('tasks.html', tasks=sorted_tasks, backend_ws_public_url=BACKEND_WS_PUBLIC_URL)


@app.route('/task/<task_id>')
def task_detail(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
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
    
    # Process screenshot tasks via queue
    if 'screenshot' in task_types:
        try:
            enqueue_resp = http.post(
                f"{BACKEND_URL}/queue/screenshot",
                json=payload,
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
                tasks[backend_task_id] = task
            results['screenshot'] = {'task_id': backend_task_id, 'status': 'queued'}
        except Exception as e:
            logger.exception("Failed to enqueue screenshot task")
            results['screenshot'] = {'status': 'error', 'message': str(e)}
    
    # Process recording tasks via queue
    if 'recording' in task_types:
        try:
            enqueue_resp = http.post(
                f"{BACKEND_URL}/queue/record",
                json=payload,
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
                tasks[backend_task_id] = task
            results['recording'] = {'task_id': backend_task_id, 'status': 'queued'}
        except Exception as e:
            logger.exception("Failed to enqueue recording task")
            results['recording'] = {'status': 'error', 'message': str(e)}
    
    return jsonify(results)


@app.route('/api/task/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
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
        if task_id in tasks:
            del tasks[task_id]
    
    return jsonify({'status': 'deleted'})


@app.route('/api/task/<task_id>', methods=['GET'])
def get_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
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
            with tasks_lock:
                pending = [t.copy() for t in tasks.values() if t.get('status') in ('queued', 'running')]
        except Exception:
            pending = []

        for t in pending:
            tid = t['id']
            ttype = t['type']
            try:
                status_resp = http.get(f"{BACKEND_URL}/queue/{tid}", timeout=(5, 10))
                if status_resp.status_code == 404:
                    continue
                status_data = status_resp.json()
                new_status = status_data.get('status')

                if new_status in ('queued', 'running'):
                    with tasks_lock:
                        if tid in tasks:
                            tasks[tid]['status'] = new_status
                    continue

                if new_status == 'failed':
                    with tasks_lock:
                        if tid in tasks:
                            tasks[tid]['status'] = 'failed'
                            tasks[tid]['error'] = status_data.get('error')
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
                    with open(filepath, 'wb') as f:
                        for chunk in result_resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    with tasks_lock:
                        if tid in tasks:
                            tasks[tid]['status'] = 'completed'
                            tasks[tid]['result_file'] = filename
                            tasks[tid]['result_format'] = filename.split('.')[-1]
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
