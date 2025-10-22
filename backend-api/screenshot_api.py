from fastapi import FastAPI, HTTPException, Query, APIRouter, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, Dict
import asyncio
from playwright.async_api import async_playwright, Page
import base64
import logging
from datetime import datetime
import os
import tempfile
from pathlib import Path
import time
from pyvirtualdisplay import Display
import uuid
import json

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default settings for API parameters
DEFAULT_SETTINGS = {
    "viewport_width": 1920,
    "viewport_height": 1080,
    "full_page": False,
    "image_type": "png",
    "quality": None,
    "wait_until": "domcontentloaded",
    "wait_timeout": 30000,
    "browser_type": "chromium",
    "record_duration": 10,
    "scroll_enabled": False,
    "scroll_speed": 100,
    "scroll_up_after": False,
    "headless": True
}

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Playwright Screenshot & Recorder API",
    description="API service for taking screenshots and recording videos using Playwright",
    version="2.3.3"
)

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

# In-memory task store and queue (single-process)
_task_store: Dict[str, Dict] = {}
_task_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
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
    }
    # fire-and-forget broadcast of initial queued state
    try:
        asyncio.create_task(ws_manager.broadcast(task_id, {
            "task_id": task_id,
            "kind": kind,
            "status": "queued",
            "enqueued_at": _task_store[task_id]["enqueued_at"],
        }))
    except Exception:
        pass
    return task_id

# --- Background worker ---
async def _queue_worker():
    assert _task_queue is not None
    while True:
        task_id = await _task_queue.get()
        record = _task_store.get(task_id)
        if not record:
            _task_queue.task_done()
            continue
        record["status"] = "running"
        record["started_at"] = datetime.utcnow().isoformat()
        try:
            await ws_manager.broadcast(task_id, {
                "task_id": task_id,
                "kind": record["kind"],
                "status": record["status"],
                "started_at": record["started_at"],
            })
        except Exception:
            pass
        try:
            kind: TaskKind = record["kind"]
            payload = record["payload"]
            if kind == "screenshot":
                request_model = ScreenshotRequest(**payload)
                result_bytes, content_type = await _capture_raw_screenshot_in_new_browser(request_model)
            else:
                request_model = RecordingRequest(**payload)
                result_bytes, content_type = await _capture_raw_recording_in_new_browser(request_model)
            record["result_bytes"] = result_bytes
            record["content_type"] = content_type
            record["status"] = "completed"
            record["finished_at"] = datetime.utcnow().isoformat()
            try:
                await ws_manager.broadcast(task_id, {
                    "task_id": task_id,
                    "kind": record["kind"],
                    "status": record["status"],
                    "finished_at": record["finished_at"],
                    "content_type": content_type,
                    "bytes_size": len(result_bytes) if result_bytes is not None else None,
                })
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            record["status"] = "failed"
            record["error"] = str(e)
            record["finished_at"] = datetime.utcnow().isoformat()
            try:
                await ws_manager.broadcast(task_id, {
                    "task_id": task_id,
                    "kind": record["kind"],
                    "status": record["status"],
                    "finished_at": record["finished_at"],
                    "error": record["error"],
                })
            except Exception:
                pass
        finally:
            _task_queue.task_done()

# --- App lifecycle: start/stop worker ---
@app.on_event("startup")
async def _startup_queue_worker():
    global _task_queue, _worker_task
    if _task_queue is None:
        _task_queue = asyncio.Queue()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_queue_worker())
        logger.info("Queue worker started")

@app.on_event("shutdown")
async def _shutdown_queue_worker():
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass
        logger.info("Queue worker stopped")

# --- Helper Functions ---

async def _scroll_to_end(page: Page, scroll_speed: int, direction: str = "down"):
    """Scrolls until the end of the page is reached in the given direction."""
    last_pos = -1
    stable_count = 0
    max_stable_count = 15
    scroll_by = scroll_speed if direction == "down" else -scroll_speed

    while True:
        await page.evaluate(f"window.scrollBy(0, {scroll_by})")
        await page.wait_for_timeout(100)
        
        current_pos = await page.evaluate("window.pageYOffset")

        if current_pos == last_pos:
            stable_count += 1
            if stable_count >= max_stable_count:
                logger.info(f"Reached {direction} end of page.")
                break
        else:
            stable_count = 0
            last_pos = current_pos
        
        if direction == "up" and current_pos == 0:
            logger.info("Reached top of page.")
            break

async def _perform_scroll_sequence(page: Page, request: RecordingRequest):
    """Manages the sequence of scrolling actions (down, pause, up)."""
    await _scroll_to_end(page, request.scroll_speed, direction="down")
    
    if request.scroll_up_after:
        logger.info("Pausing at bottom before scrolling up...")
        await page.wait_for_timeout(1000)
        await _scroll_to_end(page, request.scroll_speed, direction="up")

async def _capture_raw_recording_in_new_browser(request_model: RecordingRequest) -> tuple[bytes, str]:
    """Handles the entire lifecycle of capturing a video in a new browser instance."""
    display = None
    if not request_model.headless:
        logger.info(f"Starting virtual display for headful request: {request_model.viewport_width}x{request_model.viewport_height}")
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
                    
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                
                video_path = None
                try:
                    await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                    
                    # The record_duration is now a timeout for the actions that happen *after* page load.
                    try:
                        if request_model.scroll_enabled:
                            scroll_task = asyncio.create_task(
                                _perform_scroll_sequence(page, request_model)
                            )
                            await asyncio.wait_for(scroll_task, timeout=request_model.record_duration)
                        else:
                            await asyncio.sleep(request_model.record_duration)
                    except asyncio.TimeoutError:
                        logger.info(f"Recording duration of {request_model.record_duration}s reached. Stopping actions.")
                        # The task will be cancelled automatically by wait_for
                    
                finally:
                    if page.video:
                        video_path = await page.video.path()
                    await context.close()
                    await browser.close()
            
            if video_path and Path(video_path).exists():
                video_buffer = Path(video_path).read_bytes()
                return video_buffer, "video/webm"
            else:
                raise FileNotFoundError("Video file was not created.")
    finally:
        if display:
            logger.info("Stopping virtual display.")
            display.stop()

async def _capture_raw_screenshot_in_new_browser(request_model: ScreenshotRequest) -> tuple[bytes, str]:
    """Handles the entire lifecycle of capturing a screenshot in a new browser instance."""
    display = None
    if not request_model.headless:
        logger.info(f"Starting virtual display for headful request: {request_model.viewport_width}x{request_model.viewport_height}")
        display = Display(visible=0, size=(request_model.viewport_width, request_model.viewport_height))
        display.start()
        
    try:
        async with async_playwright() as p:
            browser_launcher = getattr(p, request_model.browser_type)
            browser = await browser_launcher.launch(headless=request_model.headless)
            
            context_options = {
                'viewport': {'width': request_model.viewport_width, 'height': request_model.viewport_height}
            }
            if request_model.user_agent:
                context_options['user_agent'] = request_model.user_agent
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            try:
                await page.goto(request_model.url, wait_until=request_model.wait_until, timeout=request_model.wait_timeout)
                
                if request_model.wait_for_selector:
                    await page.wait_for_selector(request_model.wait_for_selector, timeout=request_model.wait_timeout)
                
                screenshot_options = {'full_page': request_model.full_page, 'type': request_model.image_type}
                if request_model.image_type == 'jpeg':
                    screenshot_options['quality'] = request_model.quality
                
                if all([request_model.clip_x is not None, request_model.clip_y is not None, request_model.clip_width is not None, request_model.clip_height is not None]):
                    screenshot_options['clip'] = {'x': request_model.clip_x, 'y': request_model.clip_y, 'width': request_model.clip_width, 'height': request_model.clip_height}
                
                screenshot_buffer = await page.screenshot(**screenshot_options)
            finally:
                await context.close()
                await browser.close()
                
        content_type = f"image/{request_model.image_type}"
        return screenshot_buffer, content_type
    finally:
        if display:
            logger.info("Stopping virtual display.")
            display.stop()

# --- Generic Request Handler ---
async def handle_request(handler_func, request_model):
    """Generic handler for processing requests and managing errors."""
    log_message_start = f"Processing {'record' if 'record' in handler_func.__name__ else 'screenshot'} request for URL"
    log_message_fail = f"{'Recording' if 'record' in handler_func.__name__ else 'Screenshot'} failed for URL"
    
    try:
        logger.info(f"{log_message_start}: {request_model.url}")
        return await handler_func(request_model)
    except Exception as e:
        logger.exception(f"{log_message_fail} {request_model.url}")
        raise HTTPException(status_code=500, detail=str(e))

# --- API Endpoints ---
api_router = APIRouter()

# Enqueue endpoints (non-blocking)
@api_router.post("/queue/screenshot")
async def enqueue_screenshot(request: ScreenshotRequest):
    if _task_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")
    task_id = _create_task("screenshot", request.dict())
    await _task_queue.put(task_id)
    return {"task_id": task_id, "status": "queued"}

@api_router.post("/queue/record")
async def enqueue_record(request: RecordingRequest):
    if _task_queue is None:
        raise HTTPException(status_code=503, detail="Queue not initialized")
    task_id = _create_task("record", request.dict())
    await _task_queue.put(task_id)
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
async def take_screenshot_endpoint(request: ScreenshotRequest):
    async def handler(req):
        screenshot_buffer, content_type = await _capture_raw_screenshot_in_new_browser(req)
        return Response(content=screenshot_buffer, media_type=content_type, headers={"Content-Disposition": f"inline; filename=screenshot.{req.image_type}"})
    return await handle_request(handler, request)

@api_router.post("/screenshot/base64")
async def take_screenshot_base64_endpoint(request: ScreenshotRequest):
    async def handler(req):
        screenshot_buffer, _ = await _capture_raw_screenshot_in_new_browser(req)
        base64_image = base64.b64encode(screenshot_buffer).decode('utf-8')
        return JSONResponse(content={"url": req.url, "image": base64_image, "format": req.image_type})
    return await handle_request(handler, request)

@api_router.post("/record")
async def take_recording_endpoint(request: RecordingRequest):
    async def handler(req):
        video_buffer, content_type = await _capture_raw_recording_in_new_browser(req)
        return Response(content=video_buffer, media_type=content_type, headers={"Content-Disposition": "inline; filename=recording.webm"})
    return await handle_request(handler, request)

@api_router.post("/record/base64")
async def take_recording_base64_endpoint(request: RecordingRequest):
    async def handler(req):
        video_buffer, _ = await _capture_raw_recording_in_new_browser(req)
        base64_video = base64.b64encode(video_buffer).decode('utf-8')
        return JSONResponse(content={"url": req.url, "video": base64_video, "format": "webm"})
    return await handle_request(handler, request)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Playwright API", "timestamp": datetime.utcnow().isoformat()}

app.include_router(api_router)

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

