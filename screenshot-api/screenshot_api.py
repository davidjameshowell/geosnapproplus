from fastapi import FastAPI, HTTPException, Query, APIRouter, Body, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, Dict, Callable, Awaitable, Any
import asyncio
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError
from camoufox.async_api import AsyncCamoufox
import base64
import logging
from datetime import datetime
import os
import tempfile
from pathlib import Path
import time
from pyvirtualdisplay import Display
import uuid
import re
import json
import socket
import ipaddress
from urllib.parse import urlparse, urlunparse
from collections import defaultdict
import aiohttp

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Ensure our logs surface under Uvicorn/Hypercorn by reusing their error logger handlers
try:
    candidate_error_loggers = [
        logging.getLogger("uvicorn.error"),
        logging.getLogger("hypercorn.error"),
    ]
    selected = next((lg for lg in candidate_error_loggers if lg and lg.handlers), None)
    if selected is not None:
        logger.handlers = selected.handlers
        logger.setLevel(selected.level or logging.INFO)
        logger.propagate = False
    else:
        import sys
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(_handler)
        logger.setLevel(logging.INFO)
except Exception:
    pass

def log_info(message: str) -> None:
    logger.info(message)

def log_warning(message: str) -> None:
    logger.warning(message)

def log_error(message: str) -> None:
    logger.error(message)

# Default settings for API parameters
DEFAULT_SETTINGS = {
    "viewport_width": 1920,
    "viewport_height": 1080,
    "full_page": False,
    "image_type": "png",
    "quality": None,
    "wait_until": "domcontentloaded",
    "wait_timeout": 60000,
    "browser_type": "chromium",
    "record_duration": 10,
    "scroll_enabled": False,
    "scroll_speed": 100,
    "scroll_up_after": False,
    "scroll_timeout": 10,
    "headless": True,
    "post_wait_ms": 1500,
    "pre_record_wait_ms": 1000, 
    "pause_before_scroll_ms": 0,
    "post_scroll_pause_ms": 0,
    "dismiss_popups": True
}

POPUP_CLOSE_TEXT_PATTERNS = (
    re.compile(r"\\bclose\\b", re.I),
    re.compile(r"\\bdismiss\\b", re.I),
    re.compile(r"\\bno,? thanks\\b", re.I),
    re.compile(r"\\bno thanks\\b", re.I),
    re.compile(r"\\bgot it\\b", re.I),
    re.compile(r"\\baccept\\b", re.I),
    re.compile(r"\\bi agree\\b", re.I),
    re.compile(r"\\bcontinue\\b", re.I),
    re.compile(r"\\ballow\\b", re.I),
    re.compile(r"\\bok\\b", re.I),
)

POPUP_CLICKABLE_SELECTORS = (
    '[aria-label*="close" i]',
    '[aria-label*="dismiss" i]',
    '[aria-label*="no thanks" i]',
    '[data-testid*="close" i]',
    '[data-testid*="dismiss" i]',
    '[data-test*="close" i]',
    '[data-test*="dismiss" i]',
    '[class*="close-button" i]',
    '[class*="close-icon" i]',
    '[class*="close-btn" i]',
    '[class*="modal-close" i]',
    '[class*="popup-close" i]',
    '[class*="paywall-close" i]',
    '[id*="close" i]',
    '[id*="dismiss" i]',
    '[role="button"][id*="close" i]',
    '[role="button"][class*="close" i]',
    'button:has-text("×")',
    'button:has-text("✕")',
    'button:has-text("✖")',
    'button:has-text("Skip")',
)

POPUP_OVERLAY_KEYWORDS = (
    "ad blocker",
    "subscribe",
    "subscription",
    "sign up",
    "sign in",
    "log in",
    "cookie",
    "privacy",
    "consent",
    "gdpr",
    "newsletter",
    "we value your",
    "support us",
    "keep reading",
    "continue reading",
    "disable your ad blocker",
)

POPUP_REMOVAL_JS = """
(selList, keywords) => {
  const normalizedKeywords = (keywords || []).map(k => (k || '').toLowerCase());
  const matchesKeyword = (el) => {
    const text = (el.innerText || '').toLowerCase();
    if (!text) return false;
    return normalizedKeywords.some((keyword) => keyword && text.includes(keyword));
  };
  const matchesSelectorList = (el) => {
    if (!selList || !selList.length) return false;
    return selList.some((sel) => {
      try {
        return el.matches(sel);
      } catch (error) {
        return false;
      }
    });
  };
  const asString = (value) => {
    if (!value) return '';
    if (typeof value === 'string') return value;
    if (typeof value.baseVal === 'string') return value.baseVal;
    return String(value);
  };
  const viewW = window.innerWidth || document.documentElement.clientWidth || 1920;
  const viewH = window.innerHeight || document.documentElement.clientHeight || 1080;
  let removed = 0;

  const shouldRemove = (el) => {
    if (!el || el === document.body) return false;
    const style = window.getComputedStyle(el);
    if (!style) return false;
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const position = style.position;
    const zIndex = parseFloat(style.zIndex || '0');
    if (!['fixed', 'sticky'].includes(position) && zIndex < 30 && !matchesSelectorList(el)) return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width < 1 || rect.height < 1) return false;
    const className = asString(el.className).toLowerCase();
    const id = asString(el.id).toLowerCase();
    const label = `${className} ${id}`;
    const coversMajority = rect.width >= viewW * 0.6 || rect.height >= viewH * 0.4;
    const isLargeBar = rect.width >= viewW * 0.6 && rect.height >= viewH * 0.15;
    const keywordHit = matchesKeyword(el);
    const labelHit = /modal|overlay|popup|interstitial|newsletter|subscribe|paywall|cookie|gdpr|consent|adblock/i.test(label);
    if (keywordHit || labelHit) return true;
    if (matchesSelectorList(el) && (coversMajority || keywordHit)) return true;
    if (coversMajority && (['fixed', 'sticky'].includes(position) || zIndex >= 10)) return true;
    if (isLargeBar) return true;
    return false;
  };

  const candidates = Array.from(document.body.querySelectorAll('*')).filter((el) => shouldRemove(el));
  const capped = candidates.slice(0, 20);
  capped.forEach((el) => {
    try {
      el.dataset.__geosnap_removed_popup = 'true';
      el.style.setProperty('display', 'none', 'important');
      el.style.setProperty('visibility', 'hidden', 'important');
      el.style.setProperty('pointer-events', 'none', 'important');
      removed += 1;
    } catch (error) {
      // ignore
    }
  });
  return removed;
}
"""

# Gluetun API configuration
GLUETUN_API_URL = os.getenv("GLUETUN_API_URL", "http://gluetun-api:8001")

def _parse_positive_int(value: str | None, default: int) -> int:
    try:
        if value is None:
            return default
        return max(0, int(value))
    except Exception:
        return default

VPN_SHARED_PROXY_IDLE_TTL_SECONDS = _parse_positive_int(os.getenv("VPN_SHARED_PROXY_IDLE_TTL_SECONDS"), 20)

# --- Shared Proxy Manager ---
# Tracks gluetun proxies by VPN location to allow sharing between screenshot and recording tasks
# Value schema: {
#   'container_id': str,
#   'proxy_url': str,
#   'ref_count': int,
#   'destroy_task': Optional[asyncio.Task]
# }
_shared_proxy_manager: Dict[str, Dict] = {}
_proxy_manager_lock = asyncio.Lock()

_group_states: Dict[str, Dict[str, Any]] = {}
_group_lock = asyncio.Lock()

FINAL_TASK_STATUSES = {"completed", "failed"}

async def _release_shared_proxy(location_key: str):
    """Release a reference to a shared proxy. Decrements ref count and destroys if needed."""
    async with _proxy_manager_lock:
        if location_key not in _shared_proxy_manager:
            log_warning(f"[VPN] Attempted to release proxy for {location_key} but it doesn't exist")
            return
        
        proxy_info = _shared_proxy_manager[location_key]
        proxy_info['ref_count'] -= 1
        log_info(f"[VPN] Released shared proxy for {location_key} (ref_count={proxy_info['ref_count']})")
        
        # If ref count reaches 0, destroy the proxy
        if proxy_info['ref_count'] <= 0:
            container_id = proxy_info['container_id']
            if VPN_SHARED_PROXY_IDLE_TTL_SECONDS <= 0:
                log_info(f"[VPN] Reference count reached 0 for {location_key}, destroying proxy container {container_id} immediately")
                del _shared_proxy_manager[location_key]
                asyncio.create_task(_destroy_gluetun_proxy(container_id))
            else:
                if proxy_info.get('destroy_task') is not None:
                    # Should not normally happen, but cancel any existing teardown task before scheduling a new one
                    try:
                        proxy_info['destroy_task'].cancel()
                    except Exception:
                        pass
                log_info(f"[VPN] Reference count reached 0 for {location_key}, scheduling destroy in {VPN_SHARED_PROXY_IDLE_TTL_SECONDS}s (container {container_id})")
                destroy_task = asyncio.create_task(_schedule_proxy_teardown(location_key, container_id))
                proxy_info['destroy_task'] = destroy_task

async def _schedule_proxy_teardown(location_key: str, container_id: str) -> None:
    try:
        if VPN_SHARED_PROXY_IDLE_TTL_SECONDS > 0:
            await asyncio.sleep(VPN_SHARED_PROXY_IDLE_TTL_SECONDS)
    except asyncio.CancelledError:
        log_info(f"[VPN] Cancelled idle destroy timer for {location_key}")
        return

    try:
        async with _proxy_manager_lock:
            proxy_info = _shared_proxy_manager.get(location_key)
            if not proxy_info:
                return
            if proxy_info.get('ref_count', 0) > 0:
                proxy_info['destroy_task'] = None
                return
            current_task = proxy_info.get('destroy_task')
            if current_task is not asyncio.current_task():
                # Another task took over; leave cleanup to that task
                return
            proxy_info['destroy_task'] = None
            _shared_proxy_manager.pop(location_key, None)
        log_info(f"[VPN] Destroying idle shared proxy for {location_key} (container {container_id})")
        await _destroy_gluetun_proxy(container_id)
    except asyncio.CancelledError:
        log_info(f"[VPN] Cancelled idle destroy timer for {location_key}")
    except Exception as e:
        log_warning(f"[VPN] Error during proxy teardown for {location_key}: {e}")


def _group_location_key(country: Optional[str], city: Optional[str]) -> Optional[str]:
    if not country:
        return None
    if not city:
        return f"{country}/_random_"
    return f"{country}/{city}"


def _group_has_pending_tasks(group_id: str) -> bool:
    for record in _task_store.values():
        if record.get("group_id") == group_id and record.get("status") not in FINAL_TASK_STATUSES:
            return True
    return False


async def _acquire_group_proxy(group_id: str, country: str, city: Optional[str], *, task_id: Optional[str] = None) -> tuple[str, str]:
    location_key = _group_location_key(country, city)
    if location_key is None:
        raise ValueError("Group proxy acquisition requires country")

    async with _group_lock:
        state = _group_states.get(group_id)
        if state:
            if state.get("location_key") != location_key:
                raise ValueError(
                    f"Group '{group_id}' is already bound to location {state.get('location_key')} but request asked for {location_key}"
                )
            state["active"] = state.get("active", 0) + 1
            if task_id:
                state.setdefault("tasks", set()).add(task_id)
            log_info(f"[VPN-GROUP] Reusing proxy for group {group_id} at {location_key} (active={state['active']})")
            return state["proxy_url"], state["container_id"]

    proxy_url, container_id = await _create_gluetun_proxy(country, city or "")
    if not proxy_url or not container_id:
        raise Exception(f"Failed to create gluetun proxy for group {group_id} ({country}/{city or 'random'})")

    async with _group_lock:
        # Another coroutine might have populated state while we awaited proxy creation.
        state = _group_states.get(group_id)
        if state:
            # We no longer need the newly created container; destroy it and use existing.
            log_warning(f"[VPN-GROUP] Proxy already existed for group {group_id}; destroying extra container {container_id}")
            try:
                await _destroy_gluetun_proxy(container_id)
            except Exception as destroy_error:
                log_warning(f"[VPN-GROUP] Error destroying redundant container {container_id}: {destroy_error}")
            state["active"] = state.get("active", 0) + 1
            if task_id:
                state.setdefault("tasks", set()).add(task_id)
            return state["proxy_url"], state["container_id"]

        _group_states[group_id] = {
            "location_key": location_key,
            "proxy_url": proxy_url,
            "container_id": container_id,
            "active": 1,
            "tasks": {task_id} if task_id else set(),
        }
        log_info(f"[VPN-GROUP] Created new proxy for group {group_id} at {location_key} (container {container_id})")

    return proxy_url, container_id


async def _release_group_proxy(group_id: str) -> None:
    async with _group_lock:
        state = _group_states.get(group_id)
        if not state:
            return
        state["active"] = max(0, state.get("active", 0) - 1)
        current_active = state["active"]
    log_info(f"[VPN-GROUP] Released proxy for group {group_id} (active={current_active})")
    await _maybe_destroy_group_proxy(group_id)


async def _maybe_destroy_group_proxy(group_id: str) -> None:
    async with _group_lock:
        state = _group_states.get(group_id)
        if not state:
            return
        if state.get("active", 0) > 0:
            return
        container_id = state.get("container_id")
        location_key = state.get("location_key")

    if _group_has_pending_tasks(group_id):
        return

    async with _group_lock:
        state = _group_states.pop(group_id, None)

    if not state:
        return

    container_id = state.get("container_id")
    if container_id:
        log_info(f"[VPN-GROUP] Destroying proxy for group {group_id} (container {container_id}, location {location_key})")
        try:
            await _destroy_gluetun_proxy(container_id)
        except Exception as destroy_error:
            log_warning(f"[VPN-GROUP] Error destroying group proxy {container_id}: {destroy_error}")

async def _on_group_task_finalized(record: Dict) -> None:
    group_id = record.get("group_id")
    if not group_id:
        return
    await _maybe_destroy_group_proxy(group_id)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Playwright Screenshot & Recorder API",
    description="API service for taking screenshots and recording videos using Playwright",
    version="2.3.3"
)
# --- Simple API Key & Rate Limiting ---
API_KEY = os.getenv("API_KEY", "")
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60"))
_rate_buckets: dict[str, list[int]] = defaultdict(list)

def _client_identifier(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if xf:
        return xf
    return request.client.host if request.client else "unknown"

async def require_api_key(request: Request):
    if not API_KEY:
        return  # auth disabled
    provided = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if provided != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

async def rate_limit(request: Request):
    if RATE_LIMIT_MAX_REQUESTS <= 0:
        return  # disabled
    now = int(time.time())
    ident = _client_identifier(request)
    bucket = _rate_buckets[ident]
    # drop old
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    i = 0
    for ts in bucket:
        if ts >= window_start:
            break
        i += 1
    if i:
        del bucket[:i]
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)

# --- URL/SSRF Validation Helpers ---
def _is_ip_disallowed(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except Exception:
        return True

def _resolve_host_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
        ips: list[str] = []
        for family, _type, _proto, _canonname, sockaddr in infos:
            try:
                if family == socket.AF_INET:
                    ips.append(sockaddr[0])
                elif family == socket.AF_INET6:
                    ips.append(sockaddr[0])
            except Exception:
                continue
        return list(dict.fromkeys(ips))
    except Exception:
        return []

def _validate_url_public(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https schemes are allowed")
    if not parsed.netloc:
        raise ValueError("URL must include a valid host")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL must include a valid host")
    # Block common localhost tokens early
    if host in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Local addresses are not allowed")

    ips = _resolve_host_ips(host)
    if not ips:
        raise ValueError("Unable to resolve host")
    # Reject if any resolved IP is private or otherwise unsafe
    for ip in ips:
        if _is_ip_disallowed(ip):
            raise ValueError("Target host resolves to a disallowed address")
    return url

# --- Pydantic Models ---
class ScreenshotRequest(BaseModel):
    url: str = Field(..., description="URL of the webpage to screenshot")
    browser_type: Literal["chromium", "firefox", "webkit"] = Field(DEFAULT_SETTINGS["browser_type"], description="Browser engine to use")
    headless: bool = Field(DEFAULT_SETTINGS["headless"], description="Run browser in headless or headful mode.")
    viewport_width: int = Field(DEFAULT_SETTINGS["viewport_width"], ge=320, le=3840, description="Viewport width in pixels")
    viewport_height: int = Field(DEFAULT_SETTINGS["viewport_height"], ge=240, le=2160, description="Viewport height in pixels")
    full_page: bool = Field(DEFAULT_SETTINGS["full_page"], description="Capture full page or just viewport")
    image_type: Literal["png", "jpeg"] = Field(DEFAULT_SETTINGS["image_type"], description="Image format")
    quality: Optional[int] = Field(DEFAULT_SETTINGS["quality"], ge=0, le=100, description="Image quality (0-100, only for JPEG)")
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = Field(DEFAULT_SETTINGS["wait_until"], description="When to consider navigation succeeded")
    wait_for_selector: Optional[str] = Field(None, description="CSS selector to wait for before taking screenshot")
    wait_timeout: int = Field(DEFAULT_SETTINGS["wait_timeout"], ge=1000, le=120000, description="Maximum wait time in milliseconds")
    clip_x: Optional[int] = Field(None, description="X coordinate for clipping area")
    clip_y: Optional[int] = Field(None, description="Y coordinate for clipping area")
    clip_width: Optional[int] = Field(None, description="Width of clipping area")
    clip_height: Optional[int] = Field(None, description="Height of clipping area")
    user_agent: Optional[str] = Field(None, description="Custom user agent string")
    camoufox_fallback: bool = Field(
        True,
        description="If Cloudflare/Turnstile is detected, retry with Stealth Browser"
    )
    post_wait_ms: int = Field(DEFAULT_SETTINGS["post_wait_ms"], ge=0, le=120000, description="Extra delay after navigation/selector before capture (milliseconds)")
    dismiss_popups: bool = Field(DEFAULT_SETTINGS["dismiss_popups"], description="Attempt to close or hide obstructive popups before capturing")
    group_id: Optional[str] = Field(None, description="Optional identifier to group related tasks for shared VPN lifecycle")
    vpn_country: Optional[str] = Field(None, description="VPN country for proxy (requires vpn_city)")
    vpn_city: Optional[str] = Field(None, description="VPN city for proxy (requires vpn_country)")

    @validator('url')
    def validate_url_public(cls, v):
        return _validate_url_public(v)

    @validator('quality')
    def validate_quality(cls, v, values):
        # If PNG, ignore any provided quality
        if values.get('image_type') == 'png':
            return None
        return v
    
    @validator('clip_height')
    def validate_clip_and_full_page(cls, v, values):
        if values.get('full_page') and any([
            values.get('clip_x') is not None,
            values.get('clip_y') is not None,
            values.get('clip_width') is not None,
            v is not None
        ]):
            raise ValueError("Cannot use 'clip' and 'full_page' options simultaneously.")
        return v
    
    @validator('vpn_city')
    def validate_vpn_location(cls, v, values):
        # If vpn_city is provided, vpn_country must also be provided.
        if v is not None and values.get('vpn_country') is None:
            raise ValueError("vpn_country must be provided if vpn_city is specified")
        return v

class RecordingRequest(BaseModel):
    url: str = Field(..., description="URL of the webpage to record")
    browser_type: Literal["chromium", "firefox", "webkit"] = Field(DEFAULT_SETTINGS["browser_type"], description="Browser engine to use")
    headless: bool = Field(DEFAULT_SETTINGS["headless"], description="Run browser in headless or headful mode.")
    viewport_width: int = Field(DEFAULT_SETTINGS["viewport_width"], ge=320, le=3840, description="Viewport width in pixels")
    viewport_height: int = Field(DEFAULT_SETTINGS["viewport_height"], ge=240, le=2160, description="Viewport height in pixels")
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = Field(DEFAULT_SETTINGS["wait_until"], description="When to consider navigation succeeded")
    wait_timeout: int = Field(DEFAULT_SETTINGS["wait_timeout"], ge=1000, le=120000, description="Maximum wait time in milliseconds")
    user_agent: Optional[str] = Field(None, description="Custom user agent string")
    record_duration: int = Field(DEFAULT_SETTINGS["record_duration"], ge=1, le=120, description="Maximum recording duration in seconds")
    scroll_enabled: bool = Field(DEFAULT_SETTINGS["scroll_enabled"], description="Enable smooth scrolling during recording")
    scroll_speed: int = Field(DEFAULT_SETTINGS["scroll_speed"], ge=10, le=500, description="Pixels to scroll per iteration")
    scroll_up_after: bool = Field(DEFAULT_SETTINGS["scroll_up_after"], description="Scroll back to the top after reaching the bottom.")
    scroll_timeout: int = Field(DEFAULT_SETTINGS["scroll_timeout"], ge=1, le=120, description="Maximum time to spend auto-scrolling in seconds")
    camoufox_fallback: bool = Field(
        True,
        description="If Cloudflare/Turnstile is detected, retry with Stealth Browser"
    )
    pre_record_wait_ms: int = Field(DEFAULT_SETTINGS["pre_record_wait_ms"], ge=0, le=120000, description="Extra delay after navigation before starting actions (milliseconds)")
    pause_before_scroll_ms: int = Field(DEFAULT_SETTINGS["pause_before_scroll_ms"], ge=0, le=120000, description="Pause duration before starting auto-scroll (milliseconds)")
    post_scroll_pause_ms: int = Field(DEFAULT_SETTINGS["post_scroll_pause_ms"], ge=0, le=120000, description="Pause duration after scrolling completes (milliseconds)")
    dismiss_popups: bool = Field(DEFAULT_SETTINGS["dismiss_popups"], description="Attempt to close or hide obstructive popups before or during recording")
    group_id: Optional[str] = Field(None, description="Optional identifier to group related tasks for shared VPN lifecycle")
    vpn_country: Optional[str] = Field(None, description="VPN country for proxy (requires vpn_city)")
    vpn_city: Optional[str] = Field(None, description="VPN city for proxy (requires vpn_country)")

    @validator('url')
    def validate_url_public(cls, v):
        return _validate_url_public(v)
    
    @validator('vpn_city')
    def validate_vpn_location(cls, v, values):
        # If vpn_city is provided, vpn_country must also be provided.
        if v is not None and values.get('vpn_country') is None:
            raise ValueError("vpn_country must be provided if vpn_city is specified")
        return v

# --- Queue & Task Models ---

TaskStatus = Literal["queued", "running", "completed", "failed"]
TaskKind = Literal["screenshot", "record"]

class TaskInfo(BaseModel):
    task_id: str
    kind: TaskKind
    status: TaskStatus
    enqueued_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    content_type: Optional[str] = None
    bytes_size: Optional[int] = None
    group_id: Optional[str] = None

# In-memory task store and queue (global, shared across all users)
# All tasks from all users are queued here and processed sequentially
_task_store: Dict[str, Dict] = {}
_task_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_queue_initialized = False
# --- WebSocket Manager for task updates ---
class TaskWebSocketManager:
    def __init__(self):
        self.connections_by_task: Dict[str, set[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections_by_task.setdefault(task_id, set()).add(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        try:
            conns = self.connections_by_task.get(task_id)
            if conns and websocket in conns:
                conns.remove(websocket)
            if conns is not None and len(conns) == 0:
                self.connections_by_task.pop(task_id, None)
        except Exception:
            pass

    async def broadcast(self, task_id: str, payload: dict):
        message = json.dumps(payload)
        conns = list(self.connections_by_task.get(task_id, set()))
        to_remove: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(task_id, ws)


ws_manager = TaskWebSocketManager()

# --- Helper: create task record ---
def _create_task(kind: TaskKind, payload: dict) -> str:
    task_id = uuid.uuid4().hex
    _task_store[task_id] = {
        "task_id": task_id,
        "kind": kind,
        "status": "queued",
        "enqueued_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "finished_at": None,
        "error": None,
        "result_bytes": None,
        "content_type": None,
        "payload": payload,
        "group_id": payload.get("group_id"),
    }
    # fire-and-forget broadcast of initial queued state
    try:
        asyncio.create_task(ws_manager.broadcast(task_id, {
            "task_id": task_id,
            "kind": kind,
            "status": "queued",
            "enqueued_at": _task_store[task_id]["enqueued_at"],
            "group_id": payload.get("group_id"),
        }))
    except Exception:
        pass
    return task_id

# --- Background worker ---
async def _queue_worker():
    """
    Global queue worker that processes tasks from all users sequentially.
    
    IMPORTANT: Only one instance of this worker runs at a time to ensure
    tasks are processed one-by-one and the API is not overwhelmed.
    """
    assert _task_queue is not None
    log_info("[QUEUE] Sequential worker started - processing tasks one at a time from global queue")
    while True:
        task_id = None
        try:
            task_id = await _task_queue.get()
            queue_size = _task_queue.qsize()
            record = _task_store.get(task_id)
            if not record:
                log_warning(f"[QUEUE] Task {task_id} not found in store, skipping")
                _task_queue.task_done()
                continue
            
            log_info(f"[QUEUE] Processing task {task_id} (kind: {record['kind']}, queue size: {queue_size}) - ONE TASK AT A TIME")
            record["status"] = "running"
            record["started_at"] = datetime.utcnow().isoformat()
            try:
                await ws_manager.broadcast(task_id, {
                    "task_id": task_id,
                    "kind": record["kind"],
                    "status": record["status"],
                    "started_at": record["started_at"],
                    "group_id": record.get("group_id"),
                })
            except Exception:
                pass
            try:
                kind: TaskKind = record["kind"]
                payload = record["payload"]
                async def progress_cb(stage: str, details: Dict | None = None):
                    try:
                        msg = {
                            "task_id": task_id,
                            "kind": record["kind"],
                            "status": "running",
                            "stage": stage,
                        }
                        if details:
                            msg.update(details)
                        await ws_manager.broadcast(task_id, msg)
                    except Exception:
                        pass
                if kind == "screenshot":
                    request_model = ScreenshotRequest(**payload)
                    result_bytes, content_type = await _capture_raw_screenshot_in_new_browser(
                        request_model,
                        progress_cb,
                        task_id=task_id,
                    )
                else:
                    request_model = RecordingRequest(**payload)
                    result_bytes, content_type = await _capture_raw_recording_in_new_browser(
                        request_model,
                        progress_cb,
                        task_id=task_id,
                    )
                record["result_bytes"] = result_bytes
                record["content_type"] = content_type
                record["status"] = "completed"
                record["finished_at"] = datetime.utcnow().isoformat()
                log_info(f"[QUEUE] Task {task_id} completed successfully")
                try:
                    await ws_manager.broadcast(task_id, {
                        "task_id": task_id,
                        "kind": record["kind"],
                        "status": record["status"],
                        "finished_at": record["finished_at"],
                        "content_type": content_type,
                        "bytes_size": len(result_bytes) if result_bytes is not None else None,
                        "group_id": record.get("group_id"),
                    })
                except Exception:
                    pass
                await _on_group_task_finalized(record)
            except Exception as e:
                logger.exception(f"Task {task_id} failed")
                if record:
                    record["status"] = "failed"
                    record["error"] = str(e)
                    record["finished_at"] = datetime.utcnow().isoformat()
                log_error(f"[QUEUE] Task {task_id} failed: {str(e)}")
                try:
                    await ws_manager.broadcast(task_id, {
                        "task_id": task_id,
                        "kind": record["kind"] if record else "unknown",
                        "status": "failed",
                        "finished_at": record["finished_at"] if record else None,
                        "error": str(e),
                        "group_id": record.get("group_id") if record else None,
                    })
                except Exception:
                    pass
                if record:
                    await _on_group_task_finalized(record)
        except Exception as e:
            log_error(f"[QUEUE] Error in queue worker: {e}")
        finally:
            if task_id:
                _task_queue.task_done()
                remaining = _task_queue.qsize()
                if remaining > 0:
                    log_info(f"[QUEUE] Task {task_id} done, {remaining} tasks remaining in queue")

# --- App lifecycle: start/stop worker ---
@app.on_event("startup")
async def _startup_queue_worker():
    global _task_queue, _worker_task, _queue_initialized
    # Initialize global queue (shared across all users)
    if _task_queue is None:
        _task_queue = asyncio.Queue()
        log_info("[QUEUE] Global task queue initialized")
    
    # Start worker if not already running
    # IMPORTANT: Only one worker task processes tasks sequentially to avoid overwhelming the API
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_queue_worker())
        _queue_initialized = True
        log_info("[QUEUE] Single sequential worker started - tasks will be processed one at a time")
    else:
        _queue_initialized = True
        log_warning("[QUEUE] Queue worker already running - this should not happen, only one worker is supported")

@app.on_event("shutdown")
async def _shutdown_queue_worker():
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass
        log_info("Queue worker stopped")

# --- Helper Functions ---

async def _get_or_create_shared_proxy(country: str, city: Optional[str]) -> tuple[Optional[str], Optional[str], str]:
    """
    Get or create a shared gluetun proxy for the given VPN location.
    Returns (proxy_url, container_id, location_key) where location_key should be used to release the proxy.
    If proxy already exists, reuses it and increments ref count.
    If proxy doesn't exist, creates a new one with ref_count=1.
    """
    if not city:
        location_key = f"{country}/_random_"
    else:
        location_key = f"{country}/{city}"
    
    async with _proxy_manager_lock:
        if location_key in _shared_proxy_manager:
            # Proxy already exists, reuse it
            proxy_info = _shared_proxy_manager[location_key]
            destroy_task = proxy_info.get('destroy_task')
            if destroy_task:
                try:
                    destroy_task.cancel()
                except Exception:
                    pass
                proxy_info['destroy_task'] = None
                log_info(f"[VPN] Cancelled pending destroy for {location_key}; reusing shared proxy")
            proxy_info['ref_count'] += 1
            log_info(f"[VPN] Reusing existing shared proxy for {location_key} (ref_count={proxy_info['ref_count']})")
            return proxy_info['proxy_url'], proxy_info['container_id'], location_key
        else:
            # Create new proxy
            log_info(f"[VPN] Creating new shared proxy for {location_key}")
            proxy_url, container_id = await _create_gluetun_proxy(country, city or "")
            if not proxy_url or not container_id:
                return None, None, None
            
            # Store in shared manager with ref_count=1 (first user)
            _shared_proxy_manager[location_key] = {
                'container_id': container_id,
                'proxy_url': proxy_url,
                'ref_count': 1,
                'destroy_task': None
            }
            log_info(f"[VPN] Created shared proxy for {location_key} (ref_count=1)")
            return proxy_url, container_id, location_key

async def _create_gluetun_proxy(country: str, city: str) -> tuple[Optional[str], Optional[str]]:
    """
    Create a gluetun proxy instance via the gluetun API.
    Returns (proxy_url, container_id) on success, (None, None) on failure.
    
    The proxy_url format is: http://username:password@host:port
    We need to convert this to a format that Playwright can use from within Docker.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GLUETUN_API_URL}/start",
                json={"country": country, "city": city},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    log_warning(f"Failed to create gluetun proxy: {response.status} - {error_text}")
                    return None, None
                
                data = await response.json()
                container_id = data.get("id")
                proxy_url = data.get("proxy")
                service_url = data.get("service_url")
                
                if not container_id or not proxy_url:
                    log_warning(f"Invalid response from gluetun API: {data}")
                    return None, None
                
                # If we are in Kubernetes (indicated by service_url being present),
                # use the service URL directly as it provides a stable DNS name.
                if service_url:
                    log_info(f"[VPN] Using Kubernetes service URL: {service_url}")
                    proxy_for_docker = service_url
                else:
                    # Parse proxy URL: http://username:password@localhost:port
                    # For Docker containers, we need to access the gluetun container directly
                    # The gluetun container name is gluetun-{container_id}
                    # We need to replace localhost with the container name, but preserve credentials
                    parsed = urlparse(proxy_url)
                    container_name = f"gluetun-{container_id}"
                    
                    # Construct proxy URL accessible from Docker network
                    # Use the container name instead of localhost
                    # Port 8888 is the internal port in the gluetun container
                    # Preserve username and password from original URL
                    netloc = f"{container_name}:8888"
                    if parsed.username and parsed.password:
                        netloc = f"{parsed.username}:{parsed.password}@{netloc}"
                    elif parsed.username:
                        netloc = f"{parsed.username}@{netloc}"
                    
                    proxy_for_docker = urlunparse((
                        parsed.scheme,
                        netloc,  # Include credentials and container name
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment
                    ))
                
                # Parse proxy config for logging
                proxy_config_for_log = _parse_proxy_for_playwright(proxy_for_docker)
                log_info(f"[VPN] Created gluetun proxy: {proxy_for_docker} (container: {container_id})")
                log_info(f"[VPN] Proxy details - Server: {proxy_config_for_log.get('server')}, Username: {proxy_config_for_log.get('username', 'None')}, Has Password: {bool(proxy_config_for_log.get('password'))}")
                # Also log the original proxy URL for debugging
                log_info(f"[VPN] Original proxy URL from gluetun API: {proxy_url}")
                return proxy_for_docker, container_id
    except asyncio.TimeoutError:
        log_warning(f"Timeout creating gluetun proxy for {country}/{city}")
        return None, None
    except Exception as e:
        log_warning(f"Error creating gluetun proxy: {e}")
        return None, None

async def _destroy_gluetun_proxy(container_id: str) -> bool:
    """Destroy a gluetun proxy instance via the gluetun API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GLUETUN_API_URL}/destroy",
                json={"id": container_id},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    log_info(f"Destroyed gluetun proxy container: {container_id}")
                    return True
                else:
                    error_text = await response.text()
                    log_warning(f"Failed to destroy gluetun proxy {container_id}: {response.status} - {error_text}")
                    return False
    except Exception as e:
        log_warning(f"Error destroying gluetun proxy {container_id}: {e}")
        return False

def _parse_proxy_for_playwright(proxy_url: str) -> Dict[str, str]:
    """
    Parse proxy URL (http://user:pass@host:port) into Playwright proxy format.
    Returns dict with 'server' and optionally 'username' and 'password'.
    """
    parsed = urlparse(proxy_url)
    proxy_dict = {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8888}"
    }
    if parsed.username:
        proxy_dict["username"] = parsed.username
    if parsed.password:
        proxy_dict["password"] = parsed.password
    return proxy_dict

async def _scroll_to_end(page: Page, scroll_speed: int, direction: str = "down", hard_deadline_ms: Optional[int] = None):
    """Scrolls until the end of the page is reached in the given direction.
    If the page exhibits infinite scrolling behavior (document height keeps increasing and never stabilizes),
    apply a 30s cutoff to avoid scrolling forever. Otherwise, allow scrolling to complete naturally with no cap.
    """
    last_pos = -1
    stable_count = 0
    max_stable_count = 15
    scroll_by = scroll_speed if direction == "down" else -scroll_speed

    # Infinite-scroll detection: track page height growth and elapsed time
    start_ms = int(time.time() * 1000)
    last_height = await page.evaluate("document.body ? document.body.scrollHeight : 0")
    height_growth_events = 0
    INFINITE_SCROLL_CUTOFF_MS = 30000  # 30s, nonconfigurable

    while True:
        await page.evaluate(f"window.scrollBy(0, {scroll_by})")
        await page.wait_for_timeout(100)

        current_pos, current_height = await page.evaluate("[window.pageYOffset, document.body ? document.body.scrollHeight : 0]")

        # Detect stabilization of position to decide natural end
        if current_pos == last_pos:
            stable_count += 1
            if stable_count >= max_stable_count:
                log_info(f"Reached {direction} end of page.")
                break
        else:
            stable_count = 0
            last_pos = current_pos

        # Detect reaching top while scrolling up
        if direction == "up" and current_pos == 0:
            log_info("Reached top of page.")
            break

        # Track growth of page height as a proxy for infinite loading
        if current_height > last_height:
            height_growth_events += 1
            last_height = current_height

        # Only apply 30s cutoff if height keeps growing and page never stabilizes
        now_ms = int(time.time() * 1000)
        if (now_ms - start_ms) >= INFINITE_SCROLL_CUTOFF_MS and height_growth_events >= 10 and stable_count < max_stable_count:
            log_info(f"Infinite scroll detected; stopping after {INFINITE_SCROLL_CUTOFF_MS // 1000}s while scrolling {direction}")
            break

async def _perform_scroll_sequence(page: Page, request: RecordingRequest):
    """Manages the sequence of scrolling actions (down, pause, up).
    Allows finite pages to complete; caps only true infinite scroll at 30s.
    """
    await _scroll_to_end(page, request.scroll_speed, direction="down")
    if request.scroll_up_after:
        log_info("Pausing at bottom before scrolling up...")
        await page.wait_for_timeout(1000)
        await _scroll_to_end(page, request.scroll_speed, direction="up")


async def _dismiss_page_obstructions(
    page: Page,
    *,
    max_rounds: int = 4,
    delay_between_rounds_ms: int = 600,
    progress_cb: Optional[Callable[[str, Optional[Dict]], Awaitable[None]]] = None,
) -> int:
    """Best-effort attempt to dismiss or hide obstructive popups/modals.

    Returns the number of actions taken (clicks or removals)."""

    async def _notify(stage: str, details: Optional[Dict] = None) -> None:
        if progress_cb:
            try:
                await progress_cb(stage, details or {})
            except Exception:
                pass

    async def _safe_click(locator, description: str) -> bool:
        try:
            await locator.wait_for(state="attached", timeout=500)
        except PlaywrightTimeoutError:
            return False
        except Exception:
            return False
        try:
            await locator.scroll_into_view_if_needed(timeout=400)
        except Exception:
            pass
        try:
            await locator.click(timeout=600)
            log_info(f"Dismissed popup via {description}")
            await page.wait_for_timeout(150)
            return True
        except PlaywrightTimeoutError:
            pass
        except Exception:
            pass
        try:
            await locator.evaluate(
                "node => { if (!node) return; try { node.click(); } catch (error) {} "
                "if (node.dispatchEvent) { node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } }"
            )
            log_info(f"Dismissed popup via JS fallback ({description})")
            await page.wait_for_timeout(150)
            return True
        except Exception:
            return False

    async def _click_locator_batch(locator, description: str, max_clicks: int = 2) -> int:
        try:
            count = await locator.count()
        except Exception:
            return 0
        actions = 0
        limit = min(count, max_clicks)
        for idx in range(limit):
            candidate = locator.nth(idx)
            success = await _safe_click(candidate, description)
            if success:
                actions += 1
        return actions

    await _notify("popup_cleanup_start")
    total_actions = 0

    for attempt in range(1, max_rounds + 1):
        await _notify("popup_cleanup_attempt", {"attempt": attempt})
        round_actions = 0

        # Click accessible buttons/links by text pattern
        for pattern in POPUP_CLOSE_TEXT_PATTERNS:
            try:
                button_locator = page.get_by_role("button", name=pattern)
                round_actions += await _click_locator_batch(button_locator, f"button[name~={pattern.pattern}]")
            except Exception:
                pass
            try:
                link_locator = page.get_by_role("link", name=pattern)
                round_actions += await _click_locator_batch(link_locator, f"link[name~={pattern.pattern}]", max_clicks=1)
            except Exception:
                pass

        # Click generic selectors (close icons etc.)
        for selector in POPUP_CLICKABLE_SELECTORS:
            try:
                locator = page.locator(selector)
                round_actions += await _click_locator_batch(locator, f"selector:{selector}")
            except Exception:
                pass

        # Hide fixed/sticky overlays via DOM manipulation
        try:
            removed = await page.evaluate(
                POPUP_REMOVAL_JS,
                list(POPUP_CLICKABLE_SELECTORS),
                list(POPUP_OVERLAY_KEYWORDS),
            )
            if isinstance(removed, (int, float)):
                round_actions += int(removed)
        except Exception:
            pass

        total_actions += round_actions
        await _notify("popup_cleanup_attempt_done", {"attempt": attempt, "removed": round_actions})

        if round_actions == 0:
            if attempt < max_rounds:
                try:
                    await page.wait_for_timeout(delay_between_rounds_ms)
                except Exception:
                    pass
            else:
                break
        else:
            try:
                await page.wait_for_timeout(250)
            except Exception:
                pass

    await _notify("popup_cleanup_done", {"removed": total_actions})
    if total_actions:
        log_info(f"Popup cleanup removed or dismissed {total_actions} element(s)")
    return total_actions

async def _capture_raw_recording_in_new_browser(
    request_model: RecordingRequest,
    progress_cb: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
    *,
    task_id: Optional[str] = None,
) -> tuple[bytes, str]:
    """Handles the entire lifecycle of capturing a video in a new browser instance."""
    display = None
    gluetun_container_id = None
    proxy_url = None
    proxy_location_key = None
    proxy_release: Optional[Callable[[], Awaitable[None]]] = None
    
    proxy_url, gluetun_container_id, proxy_location_key, proxy_release, _ = await _obtain_vpn_proxy_for_request(
        request_model,
        progress_cb=progress_cb,
        task_id=task_id,
    )
    
    if not request_model.headless:
        log_info(f"Starting virtual display for headful request: {request_model.viewport_width}x{request_model.viewport_height}")
        display = Display(visible=0, size=(request_model.viewport_width, request_model.viewport_height))
        display.start()
        
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            async with async_playwright() as p:
                browser_launcher = getattr(p, request_model.browser_type)
                browser = await browser_launcher.launch(headless=request_model.headless)
                
                context_options = {
                    'viewport': {'width': request_model.viewport_width, 'height': request_model.viewport_height},
                    'record_video_dir': temp_dir,
                    'record_video_size': {'width': request_model.viewport_width, 'height': request_model.viewport_height}
                }
                if request_model.user_agent:
                    context_options['user_agent'] = request_model.user_agent
                
                # Add proxy configuration if VPN is used
                if gluetun_container_id and proxy_url:
                    proxy_config = _parse_proxy_for_playwright(proxy_url)
                    context_options['proxy'] = proxy_config
                    log_info(f"[VPN-RECORD] Using proxy: {proxy_config.get('server')} for URL: {request_model.url}")
                    log_info(f"[VPN-RECORD] Proxy container ID: {gluetun_container_id}")
                    log_info(f"[VPN-RECORD] Navigation timeout set to: {request_model.wait_timeout}ms")
                    
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                
                # Add request/response logging for VPN debugging
                if gluetun_container_id and proxy_url:
                    async def handle_request(request):
                        log_info(f"[VPN-RECORD] Request started: {request.method} {request.url}")
                    async def handle_response(response):
                        log_info(f"[VPN-RECORD] Response received: {response.status} {response.url}")
                    page.on("request", handle_request)
                    page.on("response", handle_response)
                
                # Debug: Check IP address when using VPN proxy
                if gluetun_container_id and proxy_url:
                    try:
                        log_info(f"[VPN-RECORD] Verifying proxy connection by checking IP address...")
                        log_info(f"[VPN-RECORD] Using proxy URL for IP check: {proxy_url}")
                        ip_check_start = time.time()
                        
                        # Use aiohttp to make direct HTTP request through proxy (curl-like)
                        # For aiohttp, proxy URL should include credentials: http://user:pass@host:port
                        # The proxy_url already has this format from gluetun API
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                "https://showmethisip.com/api",
                                proxy=proxy_url,  # Use full proxy URL with credentials
                                timeout=aiohttp.ClientTimeout(total=30)
                            ) as response:
                                if response.status == 200:
                                    ip_data = await response.json()
                                    ip_check_time = (time.time() - ip_check_start) * 1000
                                    log_info(f"[VPN-RECORD] IP check completed in {ip_check_time:.2f}ms")
                                    log_info(f"[VPN-RECORD] IP Address Response: {json.dumps(ip_data, indent=2)}")
                                else:
                                    ip_check_time = (time.time() - ip_check_start) * 1000
                                    error_text = await response.text()
                                    log_warning(f"[VPN-RECORD] IP check completed in {ip_check_time:.2f}ms but got status {response.status}: {error_text[:200]}")
                    except asyncio.TimeoutError:
                        ip_check_time = (time.time() - ip_check_start) * 1000
                        log_error(f"[VPN-RECORD] IP check timed out after {ip_check_time:.2f}ms")
                    except Exception as ip_check_error:
                        ip_check_time = (time.time() - ip_check_start) * 1000
                        log_error(f"[VPN-RECORD] IP check failed after {ip_check_time:.2f}ms: {type(ip_check_error).__name__}: {str(ip_check_error)}")
                        # Don't fail the whole request if IP check fails, just log it
                
                video_path = None
                use_stealth_fallback = False  # Track if we're using stealth browser fallback
                try:
                    if progress_cb:
                        try:
                            await progress_cb("navigating", {"url": request_model.url})
                        except Exception:
                            pass
                    
                    navigation_start = time.time()
                    log_info(f"[VPN-RECORD] Starting navigation to {request_model.url} (wait_until={request_model.wait_until}, timeout={request_model.wait_timeout}ms)")
                    try:
                        await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                        navigation_time = (time.time() - navigation_start) * 1000
                        log_info(f"[VPN-RECORD] Navigation completed successfully in {navigation_time:.2f}ms")
                    except Exception as nav_error:
                        navigation_time = (time.time() - navigation_start) * 1000
                        error_type = type(nav_error).__name__
                        log_error(f"[VPN-RECORD] Navigation failed after {navigation_time:.2f}ms: {error_type}: {str(nav_error)}")
                        if "timeout" in str(nav_error).lower() or "TimeoutError" in error_type:
                            log_error(f"[VPN-RECORD] TIMEOUT DETAILS - URL: {request_model.url}, Proxy: {proxy_url if proxy_url else 'None'}, Timeout: {request_model.wait_timeout}ms")
                            # Try to get page state for debugging
                            try:
                                page_url = page.url
                                page_title = await page.title()
                                log_error(f"[VPN-RECORD] Page state at timeout - URL: {page_url}, Title: {page_title}")
                            except Exception:
                                log_error(f"[VPN-RECORD] Could not retrieve page state after timeout")
                        raise
                    if progress_cb:
                        try:
                            await progress_cb("navigated", {"url": request_model.url})
                        except Exception:
                            pass
                    if getattr(request_model, "dismiss_popups", True):
                        try:
                            await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                        except Exception:
                            log_warning("Popup cleanup failed during primary navigation (recording)")
                    if await _page_contains_turnstile(page):
                        snippet = (await page.evaluate("document.body && document.body.innerText ? document.body.innerText.slice(0, 2000) : ''")) or ''
                        log_info(f"Turnstile indicators present (recording). Body snippet: {snippet[:300].replace('\n',' ')}...")
                    
                    # Optional Stealth Browser fallback
                    # If fallback is needed, we need to keep the browser open for the entire recording process
                    use_stealth_fallback = await _page_contains_turnstile(page) and request_model.camoufox_fallback
                    
                    if use_stealth_fallback:
                        if progress_cb:
                            try:
                                await progress_cb("fallback_retry", {"reason": "turnstile_detected"})
                            except Exception:
                                pass
                        log_info(f"Turnstile detected for recording {request_model.url}; retrying with Stealth Browser")
                        await context.close()
                        await browser.close()
                        
                        # Use stealth browser for entire recording process - keep browser open until recording completes
                        async with _launch_maybe_camoufox(request_model.headless) as cf_browser:
                            cf_context_opts = {
                                'viewport': {'width': request_model.viewport_width, 'height': request_model.viewport_height},
                                'record_video_dir': temp_dir,
                                'record_video_size': {'width': request_model.viewport_width, 'height': request_model.viewport_height}
                            }
                            if request_model.user_agent:
                                cf_context_opts['user_agent'] = request_model.user_agent
                            
                            # Add proxy configuration if VPN is used
                            if gluetun_container_id and proxy_url:
                                proxy_config = _parse_proxy_for_playwright(proxy_url)
                                cf_context_opts['proxy'] = proxy_config
                                log_info(f"[VPN-FALLBACK] Using proxy: {proxy_config.get('server')} for fallback recording")
                            
                            cf_context = await cf_browser.new_context(**cf_context_opts)
                            page = await cf_context.new_page()
                            
                            # Navigate with stealth browser
                            await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                            if progress_cb:
                                try:
                                    await progress_cb("fallback_success", {})
                                except Exception:
                                    pass
                            log_info(f"Stealth Browser navigation successful for recording {request_model.url}")
                            if getattr(request_model, "dismiss_popups", True):
                                try:
                                    await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                                except Exception:
                                    log_warning("Popup cleanup failed during fallback navigation (recording)")
                            
                            # Optional pre-record wait for background resources
                            if request_model.pre_record_wait_ms and request_model.pre_record_wait_ms > 0:
                                if progress_cb:
                                    try:
                                        await progress_cb("pre_record_wait_start", {"ms": request_model.pre_record_wait_ms})
                                    except Exception:
                                        pass
                                await page.wait_for_timeout(request_model.pre_record_wait_ms)
                                if progress_cb:
                                    try:
                                        await progress_cb("pre_record_wait_done", {})
                                    except Exception:
                                        pass
                            if getattr(request_model, "dismiss_popups", True):
                                try:
                                    await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                                except Exception:
                                    log_warning("Popup cleanup failed prior to fallback recording actions")

                            # Perform actions after load. Scrolling may stop early if infinite-scroll is detected.
                            # When auto-scroll is enabled, we use explicit pre/post pauses and do not use record_duration
                            # for post-scroll waiting. When auto-scroll is disabled, we use record_duration.
                            if request_model.scroll_enabled:
                                # Optional explicit pause before starting scroll sequence
                                if request_model.pause_before_scroll_ms and request_model.pause_before_scroll_ms > 0:
                                    if progress_cb:
                                        try:
                                            await progress_cb("pause_before_scroll_start", {"ms": request_model.pause_before_scroll_ms})
                                        except Exception:
                                            pass
                                    await page.wait_for_timeout(request_model.pause_before_scroll_ms)
                                    if progress_cb:
                                        try:
                                            await progress_cb("pause_before_scroll_done", {})
                                        except Exception:
                                            pass
                                if progress_cb:
                                    try:
                                        await progress_cb("scrolling_start", {"infinite_cap_s": 30, "speed": request_model.scroll_speed})
                                    except Exception:
                                        pass
                                await _perform_scroll_sequence(page, request_model)
                                if progress_cb:
                                    try:
                                        await progress_cb("scrolling_done", {})
                                    except Exception:
                                        pass
                                # Post-scroll pause (milliseconds)
                                if request_model.post_scroll_pause_ms and request_model.post_scroll_pause_ms > 0:
                                    if progress_cb:
                                        try:
                                            await progress_cb("post_scroll_pause_start", {"ms": request_model.post_scroll_pause_ms})
                                        except Exception:
                                            pass
                                    await page.wait_for_timeout(request_model.post_scroll_pause_ms)
                                    if progress_cb:
                                        try:
                                            await progress_cb("post_scroll_pause_done", {})
                                        except Exception:
                                            pass
                            else:
                                await asyncio.sleep(request_model.record_duration)
                            
                            # Get video path before context closes
                            try:
                                if page.video:
                                    video_path = await page.video.path()
                            except Exception:
                                pass
                            # Context and browser will be closed by context manager
                    else:
                        # No fallback needed - use regular browser flow
                        # Optional pre-record wait for background resources
                        if request_model.pre_record_wait_ms and request_model.pre_record_wait_ms > 0:
                            if progress_cb:
                                try:
                                    await progress_cb("pre_record_wait_start", {"ms": request_model.pre_record_wait_ms})
                                except Exception:
                                    pass
                            await page.wait_for_timeout(request_model.pre_record_wait_ms)
                            if progress_cb:
                                try:
                                    await progress_cb("pre_record_wait_done", {})
                                except Exception:
                                    pass
                        if getattr(request_model, "dismiss_popups", True):
                            try:
                                await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                            except Exception:
                                log_warning("Popup cleanup failed prior to recording actions")

                        # Perform actions after load. Scrolling may stop early if infinite-scroll is detected.
                        # When auto-scroll is enabled, we use explicit pre/post pauses and do not use record_duration
                        # for post-scroll waiting. When auto-scroll is disabled, we use record_duration.
                        if request_model.scroll_enabled:
                            # Optional explicit pause before starting scroll sequence
                            if request_model.pause_before_scroll_ms and request_model.pause_before_scroll_ms > 0:
                                if progress_cb:
                                    try:
                                        await progress_cb("pause_before_scroll_start", {"ms": request_model.pause_before_scroll_ms})
                                    except Exception:
                                        pass
                                await page.wait_for_timeout(request_model.pause_before_scroll_ms)
                                if progress_cb:
                                    try:
                                        await progress_cb("pause_before_scroll_done", {})
                                    except Exception:
                                        pass
                            if progress_cb:
                                try:
                                    await progress_cb("scrolling_start", {"infinite_cap_s": 30, "speed": request_model.scroll_speed})
                                except Exception:
                                    pass
                            await _perform_scroll_sequence(page, request_model)
                            if progress_cb:
                                try:
                                    await progress_cb("scrolling_done", {})
                                except Exception:
                                    pass
                            # Post-scroll pause (milliseconds)
                            if request_model.post_scroll_pause_ms and request_model.post_scroll_pause_ms > 0:
                                if progress_cb:
                                    try:
                                        await progress_cb("post_scroll_pause_start", {"ms": request_model.post_scroll_pause_ms})
                                    except Exception:
                                        pass
                                await page.wait_for_timeout(request_model.post_scroll_pause_ms)
                                if progress_cb:
                                    try:
                                        await progress_cb("post_scroll_pause_done", {})
                                    except Exception:
                                        pass
                        else:
                            await asyncio.sleep(request_model.record_duration)
                    
                finally:
                    # Only close browser/context if we didn't use stealth fallback (stealth browser closes automatically)
                    if not use_stealth_fallback:
                        try:
                            if page.video:
                                video_path = await page.video.path()
                        except Exception:
                            pass
                        for obj in (context, browser):
                            try:
                                await obj.close()
                            except Exception:
                                pass
                    # For stealth fallback, video_path is already set and browser closes via context manager
            
            if video_path and Path(video_path).exists():
                if progress_cb:
                    try:
                        await progress_cb("encoding", {})
                    except Exception:
                        pass
                video_buffer = Path(video_path).read_bytes()
                if progress_cb:
                    try:
                        await progress_cb("encoded", {"bytes_size": len(video_buffer)})
                    except Exception:
                        pass
                return video_buffer, "video/webm"
            else:
                raise FileNotFoundError("Video file was not created.")
    finally:
        # Release shared proxy (will decrement ref count and destroy if needed)
        if proxy_release:
            try:
                await proxy_release()
            except Exception as e:
                log_warning(f"Error releasing proxy: {e}")
        
        if display:
            log_info("Stopping virtual display.")
            display.stop()

async def _capture_raw_screenshot_in_new_browser(
    request_model: ScreenshotRequest,
    progress_cb: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
    *,
    task_id: Optional[str] = None,
) -> tuple[bytes, str]:
    """Handles the entire lifecycle of capturing a screenshot in a new browser instance."""
    display = None
    gluetun_container_id = None
    proxy_url = None
    proxy_location_key = None
    proxy_release: Optional[Callable[[], Awaitable[None]]] = None
    
    proxy_url, gluetun_container_id, proxy_location_key, proxy_release, _ = await _obtain_vpn_proxy_for_request(
        request_model,
        progress_cb=progress_cb,
        task_id=task_id,
    )
    
    if not request_model.headless:
        log_info(f"Starting virtual display for headful request: {request_model.viewport_width}x{request_model.viewport_height}")
        display = Display(visible=0, size=(request_model.viewport_width, request_model.viewport_height))
        display.start()
        
    try:
        async with async_playwright() as p:
            # Primary attempt using requested engine
            browser_launcher = getattr(p, request_model.browser_type)
            browser = await browser_launcher.launch(headless=request_model.headless)
            
            context_options = {
                'viewport': {'width': request_model.viewport_width, 'height': request_model.viewport_height}
            }
            if request_model.user_agent:
                context_options['user_agent'] = request_model.user_agent
            
            # Add proxy configuration if VPN is used
            if gluetun_container_id and proxy_url:
                proxy_config = _parse_proxy_for_playwright(proxy_url)
                context_options['proxy'] = proxy_config
                log_info(f"[VPN] Using proxy: {proxy_config.get('server')} for URL: {request_model.url}")
                log_info(f"[VPN] Proxy container ID: {gluetun_container_id}")
                log_info(f"[VPN] Navigation timeout set to: {request_model.wait_timeout}ms")
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Add request/response logging for VPN debugging
            if gluetun_container_id and proxy_url:
                async def handle_request(request):
                    log_info(f"[VPN] Request started: {request.method} {request.url}")
                async def handle_response(response):
                    log_info(f"[VPN] Response received: {response.status} {response.url}")
                page.on("request", handle_request)
                page.on("response", handle_response)
            
            # Debug: Check IP address when using VPN proxy
            if gluetun_container_id and proxy_url:
                try:
                    log_info(f"[VPN] Verifying proxy connection by checking IP address...")
                    log_info(f"[VPN] Using proxy URL for IP check: {proxy_url}")
                    ip_check_start = time.time()
                    
                    # Use aiohttp to make direct HTTP request through proxy (curl-like)
                    # For aiohttp, proxy URL should include credentials: http://user:pass@host:port
                    # The proxy_url already has this format from gluetun API
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            "https://showmethisip.com/api",
                            proxy=proxy_url,  # Use full proxy URL with credentials
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            if response.status == 200:
                                ip_data = await response.json()
                                ip_check_time = (time.time() - ip_check_start) * 1000
                                log_info(f"[VPN] IP check completed in {ip_check_time:.2f}ms")
                                log_info(f"[VPN] IP Address Response: {json.dumps(ip_data, indent=2)}")
                            else:
                                ip_check_time = (time.time() - ip_check_start) * 1000
                                error_text = await response.text()
                                log_warning(f"[VPN] IP check completed in {ip_check_time:.2f}ms but got status {response.status}: {error_text[:200]}")
                except asyncio.TimeoutError:
                    ip_check_time = (time.time() - ip_check_start) * 1000
                    log_error(f"[VPN] IP check timed out after {ip_check_time:.2f}ms")
                except Exception as ip_check_error:
                    ip_check_time = (time.time() - ip_check_start) * 1000
                    log_error(f"[VPN] IP check failed after {ip_check_time:.2f}ms: {type(ip_check_error).__name__}: {str(ip_check_error)}")
                    # Don't fail the whole request if IP check fails, just log it
            
            try:
                if progress_cb:
                    try:
                        await progress_cb("navigating", {"url": request_model.url})
                    except Exception:
                        pass
                
                navigation_start = time.time()
                log_info(f"[VPN] Starting navigation to {request_model.url} (wait_until={request_model.wait_until}, timeout={request_model.wait_timeout}ms)")
                try:
                    await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                    navigation_time = (time.time() - navigation_start) * 1000
                    log_info(f"[VPN] Navigation completed successfully in {navigation_time:.2f}ms")
                except Exception as nav_error:
                    navigation_time = (time.time() - navigation_start) * 1000
                    error_type = type(nav_error).__name__
                    log_error(f"[VPN] Navigation failed after {navigation_time:.2f}ms: {error_type}: {str(nav_error)}")
                    if "timeout" in str(nav_error).lower() or "TimeoutError" in error_type:
                        log_error(f"[VPN] TIMEOUT DETAILS - URL: {request_model.url}, Proxy: {proxy_url if proxy_url else 'None'}, Timeout: {request_model.wait_timeout}ms")
                        # Try to get page state for debugging
                        try:
                            page_url = page.url
                            page_title = await page.title()
                            log_error(f"[VPN] Page state at timeout - URL: {page_url}, Title: {page_title}")
                        except Exception:
                            log_error(f"[VPN] Could not retrieve page state after timeout")
                    raise
                if progress_cb:
                    try:
                        await progress_cb("navigated", {"url": request_model.url})
                    except Exception:
                        pass
                if getattr(request_model, "dismiss_popups", True):
                    try:
                        await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                    except Exception:
                        log_warning("Popup cleanup failed during primary navigation")
                # Log body snippet for debugging when indicators are present
                if await _page_contains_turnstile(page):
                    snippet = (await page.evaluate("document.body && document.body.innerText ? document.body.innerText.slice(0, 2000) : ''")) or ''
                    log_info(f"Turnstile indicators present. Body snippet: {snippet[:300].replace('\n',' ') }...")

                # If Cloudflare/Turnstile is detected and fallback enabled, retry with Stealth Browser
                if await _page_contains_turnstile(page):
                    if not request_model.camoufox_fallback:
                        log_warning(f"Turnstile detected for {request_model.url} but stealth fallback is disabled; proceeding without fallback")
                    else:
                        log_info(f"Turnstile detected for {request_model.url}; retrying with Stealth Browser")
                    if progress_cb:
                        try:
                            await progress_cb("fallback_retry", {"reason": "turnstile_detected"})
                        except Exception:
                            pass
                    await context.close()
                    await browser.close()
                    if request_model.camoufox_fallback:
                        async with _launch_maybe_camoufox(request_model.headless) as cf_browser:
                            cf_context_opts = {
                                'viewport': {'width': request_model.viewport_width, 'height': request_model.viewport_height}
                            }
                            if CAMOUFOX_DEFAULT_UA and not request_model.user_agent:
                                cf_context_opts['user_agent'] = CAMOUFOX_DEFAULT_UA
                            elif request_model.user_agent:
                                cf_context_opts['user_agent'] = request_model.user_agent
                            
                            # Add proxy configuration if VPN is used
                            if gluetun_container_id and proxy_url:
                                proxy_config = _parse_proxy_for_playwright(proxy_url)
                                cf_context_opts['proxy'] = proxy_config
                                log_info(f"[VPN-FALLBACK] Using proxy: {proxy_config.get('server')} for fallback navigation")
                            
                            cf_context = await cf_browser.new_context(**cf_context_opts)
                            page = await cf_context.new_page()
                            
                            fallback_nav_start = time.time()
                            log_info(f"[VPN-FALLBACK] Starting fallback navigation to {request_model.url} (timeout={request_model.wait_timeout}ms)")
                            try:
                                await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                                fallback_nav_time = (time.time() - fallback_nav_start) * 1000
                                log_info(f"[VPN-FALLBACK] Fallback navigation completed in {fallback_nav_time:.2f}ms")
                            except Exception as fallback_error:
                                fallback_nav_time = (time.time() - fallback_nav_start) * 1000
                                error_type = type(fallback_error).__name__
                                log_error(f"[VPN-FALLBACK] Fallback navigation failed after {fallback_nav_time:.2f}ms: {error_type}: {str(fallback_error)}")
                                raise
                            if getattr(request_model, "dismiss_popups", True):
                                try:
                                    await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                                except Exception:
                                    log_warning("Popup cleanup failed during fallback navigation")
                            if await _page_contains_turnstile(page):
                                log_info("Turnstile still present after Stealth Browser retry")
                                if progress_cb:
                                    try:
                                        await progress_cb("fallback_no_effect", {})
                                    except Exception:
                                        pass
                            else:
                                log_info(f"Stealth Browser navigation successful for {request_model.url}")
                                if progress_cb:
                                    try:
                                        await progress_cb("fallback_success", {})
                                    except Exception:
                                        pass

                            # If requested, wait for selector before capture
                            if request_model.wait_for_selector:
                                if progress_cb:
                                    try:
                                        await progress_cb("waiting_for_selector", {"selector": request_model.wait_for_selector})
                                    except Exception:
                                        pass
                                selector_start = time.time()
                                log_info(f"[VPN-FALLBACK] Waiting for selector: {request_model.wait_for_selector} (timeout={request_model.wait_timeout}ms)")
                                try:
                                    await page.wait_for_selector(request_model.wait_for_selector, timeout=request_model.wait_timeout)
                                    selector_time = (time.time() - selector_start) * 1000
                                    log_info(f"[VPN-FALLBACK] Selector found after {selector_time:.2f}ms")
                                except Exception as selector_error:
                                    selector_time = (time.time() - selector_start) * 1000
                                    log_error(f"[VPN-FALLBACK] Selector wait failed after {selector_time:.2f}ms: {str(selector_error)}")
                                    raise
                                if progress_cb:
                                    try:
                                        await progress_cb("selector_ready", {"selector": request_model.wait_for_selector})
                                    except Exception:
                                        pass
                            if getattr(request_model, "dismiss_popups", True):
                                try:
                                    await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                                except Exception:
                                    log_warning("Popup cleanup failed before fallback screenshot capture")

                            # Capture screenshot inside Stealth Browser context and return immediately
                            screenshot_options = {'full_page': request_model.full_page, 'type': request_model.image_type}
                            if request_model.image_type == 'jpeg':
                                screenshot_options['quality'] = request_model.quality
                            if all([request_model.clip_x is not None, request_model.clip_y is not None, request_model.clip_width is not None, request_model.clip_height is not None]):
                                screenshot_options['clip'] = {'x': request_model.clip_x, 'y': request_model.clip_y, 'width': request_model.clip_width, 'height': request_model.clip_height}

                            if progress_cb:
                                try:
                                    await progress_cb("capturing", {})
                                except Exception:
                                    pass
                            screenshot_buffer = await page.screenshot(**screenshot_options)
                            if progress_cb:
                                try:
                                    await progress_cb("captured", {"bytes_size": len(screenshot_buffer)})
                                except Exception:
                                    pass
                            try:
                                await cf_context.close()
                            except Exception:
                                pass
                            content_type = f"image/{request_model.image_type}"
                            return screenshot_buffer, content_type
                
                if request_model.wait_for_selector:
                    if progress_cb:
                        try:
                            await progress_cb("waiting_for_selector", {"selector": request_model.wait_for_selector})
                        except Exception:
                            pass
                    selector_start = time.time()
                    vpn_prefix = "[VPN]" if (gluetun_container_id and proxy_url) else ""
                    log_info(f"{vpn_prefix} Waiting for selector: {request_model.wait_for_selector} (timeout={request_model.wait_timeout}ms)")
                    try:
                        await page.wait_for_selector(request_model.wait_for_selector, timeout=request_model.wait_timeout)
                        selector_time = (time.time() - selector_start) * 1000
                        log_info(f"{vpn_prefix} Selector found after {selector_time:.2f}ms")
                    except Exception as selector_error:
                        selector_time = (time.time() - selector_start) * 1000
                        log_error(f"{vpn_prefix} Selector wait failed after {selector_time:.2f}ms: {str(selector_error)}")
                        raise
                    if progress_cb:
                        try:
                            await progress_cb("selector_ready", {"selector": request_model.wait_for_selector})
                        except Exception:
                            pass
                # Optional post-wait for background resources
                if hasattr(request_model, 'post_wait_ms') and request_model.post_wait_ms:
                    if progress_cb:
                        try:
                            await progress_cb("post_wait_start", {"ms": request_model.post_wait_ms})
                        except Exception:
                            pass
                    await page.wait_for_timeout(request_model.post_wait_ms)
                    if progress_cb:
                        try:
                            await progress_cb("post_wait_done", {})
                        except Exception:
                            pass
                if getattr(request_model, "dismiss_popups", True):
                    try:
                        await _dismiss_page_obstructions(page, progress_cb=progress_cb)
                    except Exception:
                        log_warning("Popup cleanup failed before screenshot capture")
                
                screenshot_options = {'full_page': request_model.full_page, 'type': request_model.image_type}
                if request_model.image_type == 'jpeg':
                    screenshot_options['quality'] = request_model.quality
                
                if all([request_model.clip_x is not None, request_model.clip_y is not None, request_model.clip_width is not None, request_model.clip_height is not None]):
                    screenshot_options['clip'] = {'x': request_model.clip_x, 'y': request_model.clip_y, 'width': request_model.clip_width, 'height': request_model.clip_height}
                
                if progress_cb:
                    try:
                        await progress_cb("capturing", {})
                    except Exception:
                        pass
                screenshot_buffer = await page.screenshot(**screenshot_options)
                if progress_cb:
                    try:
                        await progress_cb("captured", {"bytes_size": len(screenshot_buffer)})
                    except Exception:
                        pass
            finally:
                # Try closing any open contexts/browsers best-effort
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
                
        content_type = f"image/{request_model.image_type}"
        return screenshot_buffer, content_type
    finally:
        # Release shared proxy (will decrement ref count and destroy if needed)
        if proxy_release:
            try:
                await proxy_release()
            except Exception as e:
                log_warning(f"Error releasing proxy: {e}")
        
        if display:
            log_info("Stopping virtual display.")
            display.stop()

# --- Generic Request Handler ---
async def handle_request(handler_func, request_model):
    """Generic handler for processing requests and managing errors."""
    log_message_start = f"Processing {'record' if 'record' in handler_func.__name__ else 'screenshot'} request for URL"
    log_message_fail = f"{'Recording' if 'record' in handler_func.__name__ else 'Screenshot'} failed for URL"
    
    try:
        log_info(f"{log_message_start}: {request_model.url}")
        return await handler_func(request_model)
    except Exception as e:
        logger.exception(f"{log_message_fail} {request_model.url}")
        raise HTTPException(status_code=500, detail=str(e))

# --- API Endpoints ---
api_router = APIRouter()

# Enqueue endpoints (non-blocking)
@api_router.post("/queue/screenshot")
async def enqueue_screenshot(request: ScreenshotRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    global _task_queue, _queue_initialized
    
    # Ensure queue is initialized (fallback if startup event hasn't fired yet)
    if _task_queue is None:
        _task_queue = asyncio.Queue()
        log_warning("[QUEUE] Queue was None, initializing now (startup event may not have fired)")
    
    if not _queue_initialized:
        raise HTTPException(status_code=503, detail="Queue worker not initialized")
    
    task_id = _create_task("screenshot", request.dict())
    await _task_queue.put(task_id)
    queue_size = _task_queue.qsize()
    log_info(f"[QUEUE] Enqueued screenshot task {task_id} (queue size: {queue_size})")
    return {"task_id": task_id, "status": "queued"}

@api_router.post("/queue/record")
async def enqueue_record(request: RecordingRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    global _task_queue, _queue_initialized
    
    # Ensure queue is initialized (fallback if startup event hasn't fired yet)
    if _task_queue is None:
        _task_queue = asyncio.Queue()
        log_warning("[QUEUE] Queue was None, initializing now (startup event may not have fired)")
    
    if not _queue_initialized:
        raise HTTPException(status_code=503, detail="Queue worker not initialized")
    
    task_id = _create_task("record", request.dict())
    await _task_queue.put(task_id)
    queue_size = _task_queue.qsize()
    log_info(f"[QUEUE] Enqueued recording task {task_id} (queue size: {queue_size})")
    return {"task_id": task_id, "status": "queued"}

# Poll status
@api_router.get("/queue/{task_id}", response_model=TaskInfo)
async def get_task_status(task_id: str):
    record = _task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskInfo(
        task_id=record["task_id"],
        kind=record["kind"],
        status=record["status"],
        enqueued_at=record["enqueued_at"],
        started_at=record["started_at"],
        finished_at=record["finished_at"],
        error=record["error"],
        content_type=record["content_type"],
        bytes_size=(len(record["result_bytes"]) if record.get("result_bytes") is not None else None),
        group_id=record.get("group_id"),
    )

# Fetch result (binary)
@api_router.get("/queue/{task_id}/result")
async def get_task_result(task_id: str):
    record = _task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    if record["status"] != "completed" or record.get("result_bytes") is None:
        raise HTTPException(status_code=409, detail="Result not ready")
    filename = "screenshot.png" if record["kind"] == "screenshot" else "recording.webm"
    if record.get("content_type") == "image/jpeg":
        filename = "screenshot.jpg"
    return Response(
        content=record["result_bytes"],
        media_type=record.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

# Fetch result (base64 JSON)
@api_router.get("/queue/{task_id}/result/base64")
async def get_task_result_base64(task_id: str):
    record = _task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    if record["status"] != "completed" or record.get("result_bytes") is None:
        raise HTTPException(status_code=409, detail="Result not ready")
    b64 = base64.b64encode(record["result_bytes"]).decode("utf-8")
    payload_key = "image" if record["kind"] == "screenshot" else "video"
    return JSONResponse(content={
        "task_id": record["task_id"],
        "kind": record["kind"],
        payload_key: b64,
        "format": (record.get("content_type") or "").split("/")[-1] if record.get("content_type") else None
    })

@api_router.post("/screenshot")
async def take_screenshot_endpoint(request: ScreenshotRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    async def handler(req):
        screenshot_buffer, content_type = await _capture_raw_screenshot_in_new_browser(req)
        return Response(content=screenshot_buffer, media_type=content_type, headers={"Content-Disposition": f"inline; filename=screenshot.{req.image_type}"})
    return await handle_request(handler, request)

@api_router.post("/screenshot/base64")
async def take_screenshot_base64_endpoint(request: ScreenshotRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    async def handler(req):
        screenshot_buffer, _ = await _capture_raw_screenshot_in_new_browser(req)
        base64_image = base64.b64encode(screenshot_buffer).decode('utf-8')
        return JSONResponse(content={"url": req.url, "image": base64_image, "format": req.image_type})
    return await handle_request(handler, request)

@api_router.post("/record")
async def take_recording_endpoint(request: RecordingRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    async def handler(req):
        video_buffer, content_type = await _capture_raw_recording_in_new_browser(req)
        return Response(content=video_buffer, media_type=content_type, headers={"Content-Disposition": "inline; filename=recording.webm"})
    return await handle_request(handler, request)

@api_router.post("/record/base64")
async def take_recording_base64_endpoint(request: RecordingRequest, _auth=Depends(require_api_key), _rl=Depends(rate_limit)):
    async def handler(req):
        video_buffer, _ = await _capture_raw_recording_in_new_browser(req)
        base64_video = base64.b64encode(video_buffer).decode('utf-8')
        return JSONResponse(content={"url": req.url, "video": base64_video, "format": "webm"})
    return await handle_request(handler, request)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Playwright API", "timestamp": datetime.utcnow().isoformat()}

app.include_router(api_router)

# --- Camoufox detection/launch helpers ---
CAMOUFOX_EXECUTABLE = os.getenv("CAMOUFOX_EXECUTABLE")  # e.g. /usr/bin/camoufox or a firefox-like binary
CAMOUFOX_DEFAULT_UA = os.getenv("CAMOUFOX_UA")

TURNSTILE_PATTERNS = (
    re.compile(r"cloudflare", re.I),
    re.compile(r"turnstile", re.I),
    re.compile(r"cdn-cgi/challenge-platform", re.I),
    re.compile(r"checking your browser", re.I),
    re.compile(r"Verifying you are human", re.I),
)

async def _page_contains_turnstile(page: Page) -> bool:
    try:
        # quick text signals
        body_text = await page.evaluate("document.body ? document.body.innerText : ''")
        if any(p.search(body_text or '') for p in TURNSTILE_PATTERNS):
            try:
                log_info(f"Turnstile/Cloudflare indicators found in body on: {page.url}")
            except Exception:
                log_info("Turnstile/Cloudflare indicators found in body")
            return True
        # script/link src signals
        script_srcs = await page.evaluate("Array.from(document.scripts).map(s=>s.src||'')")
        if any("challenges.cloudflare.com" in (src or '') for src in script_srcs):
            log_info("Turnstile script detected on page")
            return True
        # raw HTML signals (fallback)
        html = await page.content()
        if html and ("challenges.cloudflare.com" in html or "cf-chl" in html or "data-sitekey" in html and "turnstile" in html.lower()):
            log_info("Turnstile indicators found in HTML content")
            return True
        # dom locator signals (best-effort)
        try:
            iframe_count = await page.locator('iframe[src*="challenges.cloudflare.com"]').count()
            if iframe_count and iframe_count > 0:
                log_info("Turnstile iframe detected via locator")
                return True
        except Exception:
            pass
        try:
            ts_count = await page.locator('[id*="turnstile"], [class*="turnstile"]').count()
            if ts_count and ts_count > 0:
                log_info("Turnstile element detected via locator")
                return True
        except Exception:
            pass
        # title heuristic
        try:
            title = await page.title()
            if title and ("Just a moment" in title or "Verifying you are human" in title):
                log_info(f"Turnstile title heuristic matched: {title}")
                return True
        except Exception:
            pass
    except Exception:
        return False
    return False

def _launch_maybe_camoufox(request_headless: bool) -> AsyncCamoufox:
    # Use AsyncCamoufox per official docs; executable is managed by the package
    # headless can be True or "virtual" on linux
    return AsyncCamoufox(headless=request_headless)

# --- WebSocket subscription endpoint ---
@app.websocket("/ws/tasks/{task_id}")
async def ws_task_updates(websocket: WebSocket, task_id: str):
    await ws_manager.connect(task_id, websocket)
    try:
        # Send initial snapshot if available
        record = _task_store.get(task_id)
        if record:
            try:
                await websocket.send_text(json.dumps({
                    "task_id": record["task_id"],
                    "kind": record["kind"],
                    "status": record["status"],
                    "enqueued_at": record["enqueued_at"],
                    "started_at": record["started_at"],
                    "finished_at": record["finished_at"],
                    "error": record["error"],
                    "content_type": record["content_type"],
                    "bytes_size": len(record["result_bytes"]) if record.get("result_bytes") is not None else None,
                    "group_id": record.get("group_id"),
                }))
            except Exception:
                pass
        # Keep the connection open; we do not require client messages
        while True:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(task_id, websocket)

async def _obtain_vpn_proxy_for_request(
    request_model: ScreenshotRequest | RecordingRequest,
    *,
    progress_cb: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
    task_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[Callable[[], Awaitable[None]]], Optional[str]]:
    country = getattr(request_model, "vpn_country", None)
    city = getattr(request_model, "vpn_city", None)
    group_id = getattr(request_model, "group_id", None)

    if not country:
        return None, None, None, None, group_id

    if progress_cb:
        try:
            await progress_cb("creating_proxy", {"country": country, "city": city or "random"})
        except Exception:
            pass

    if group_id:
        proxy_url, container_id = await _acquire_group_proxy(group_id, country, city, task_id=task_id)

        async def release_group() -> None:
            await _release_group_proxy(group_id)

        if progress_cb:
            try:
                await progress_cb("proxy_created", {})
            except Exception:
                pass
        return proxy_url, container_id, None, release_group, group_id

    proxy_url, container_id, location_key = await _get_or_create_shared_proxy(country, city)
    if not proxy_url or not location_key:
        raise Exception(f"Failed to create gluetun proxy for {country}/{city or 'random'}")

    async def release_shared() -> None:
        await _release_shared_proxy(location_key)

    if progress_cb:
        try:
            await progress_cb("proxy_created", {})
        except Exception:
            pass

    return proxy_url, container_id, location_key, release_shared, None

