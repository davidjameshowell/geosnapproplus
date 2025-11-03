"""
Enhanced test client for the Playwright Screenshot & Recorder API
"""
import requests
import base64
from PIL import Image
from io import BytesIO
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"
OUTPUT_DIR = Path("validation")

def run_test(test_func):
    """Decorator to run a test, print status, and measure execution time."""
    def wrapper(*args, **kwargs):
        print("-" * 50)
        print(f"Running test: {test_func.__name__}...")
        start_time = time.time()
        try:
            test_func(*args, **kwargs)
        except Exception as e:
            print(f"✗ Test failed with an unexpected error: {e}")
        finally:
            end_time = time.time()
            print(f"Finished in {end_time - start_time:.2f} seconds.")
    return wrapper

@run_test
def test_health_check():
    """Test the health check endpoint."""
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200 and response.json().get("status") == "healthy":
        print("✓ Health check successful.")
    else:
        print(f"✗ Health check failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_basic_screenshot():
    """Test basic screenshot functionality in both headless and headful modes."""
    # Headless test
    response_headless = requests.post(f"{BASE_URL}/screenshot", json={"url": "https://example.com", "headless": True})
    if response_headless.status_code == 200:
        output_path = OUTPUT_DIR / "test_screenshot_headless.png"
        with open(output_path, "wb") as f:
            f.write(response_headless.content)
        print(f"✓ Headless screenshot saved to {output_path}")
    else:
        print(f"✗ Headless failed: Status {response_headless.status_code}, Response: {response_headless.text}")

    # Headful test
    response_headful = requests.post(f"{BASE_URL}/screenshot", json={"url": "https://example.com", "headless": False})
    if response_headful.status_code == 200:
        output_path = OUTPUT_DIR / "test_screenshot_headful.png"
        with open(output_path, "wb") as f:
            f.write(response_headful.content)
        print(f"✓ Headful screenshot saved to {output_path}")
    else:
        print(f"✗ Headful failed: Status {response_headful.status_code}, Response: {response_headful.text}")


@run_test
def test_browser_types():
    """Test screenshot functionality with different browser types in both modes."""
    for browser_type in ["chromium", "firefox", "webkit"]:
        for headless_mode in [True, False]:
            mode_str = "headless" if headless_mode else "headful"
            print(f"  Testing with {browser_type} ({mode_str})...")
            response = requests.post(
                f"{BASE_URL}/screenshot",
                json={"url": "https://www.whatismybrowser.com/", "browser_type": browser_type, "headless": headless_mode}
            )
            if response.status_code == 200:
                output_path = OUTPUT_DIR / f"test_browser_{browser_type}_{mode_str}.png"
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ Screenshot for {browser_type} ({mode_str}) saved to {output_path}")
            else:
                print(f"  ✗ Failed for {browser_type} ({mode_str}): Status {response.status_code}, Response: {response.text}")


@run_test
def test_base64_screenshot():
    """Test base64 encoded screenshot in both modes."""
    # Headless test
    response_headless = requests.post(f"{BASE_URL}/screenshot/base64", json={"url": "https://example.com", "headless": True})
    if response_headless.status_code == 200:
        data = response_headless.json()
        image_data = base64.b64decode(data["image"])
        img = Image.open(BytesIO(image_data))
        output_path = OUTPUT_DIR / "test_base64_headless.png"
        img.save(output_path)
        print(f"✓ Headless Base64 screenshot saved to {output_path}. Size: {img.size}")
    else:
        print(f"✗ Headless Base64 failed: {response_headless.text}")

    # Headful test
    response_headful = requests.post(f"{BASE_URL}/screenshot/base64", json={"url": "https://example.com", "headless": False})
    if response_headful.status_code == 200:
        data = response_headful.json()
        image_data = base64.b64decode(data["image"])
        img = Image.open(BytesIO(image_data))
        output_path = OUTPUT_DIR / "test_base64_headful.png"
        img.save(output_path)
        print(f"✓ Headful Base64 screenshot saved to {output_path}. Size: {img.size}")
    else:
        print(f"✗ Headful Base64 failed: {response_headful.text}")

@run_test
def test_slow_loading_site_with_timeout():
    """Test a slow-loading site by increasing the timeout in both modes."""
    print("  Testing with increased timeout (60s)...")
    for headless_mode in [True, False]:
        mode_str = "headless" if headless_mode else "headful"
        response = requests.post(
            f"{BASE_URL}/screenshot",
            json={
                "url": "https://www.republicservices.com/",
                "wait_timeout": 60000,
                "headless": headless_mode
            }
        )
        if response.status_code == 200:
            output_path = OUTPUT_DIR / f"test_slow_site_{mode_str}.png"
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"✓ Screenshot of slow site ({mode_str}) saved to {output_path}")
        else:
            print(f"✗ Failed ({mode_str}): Status {response.status_code}, Response: {response.text}")


@run_test
def test_webm_recording():
    """Test basic WebM video recording."""
    response = requests.post(
        f"{BASE_URL}/record",
        json={"url": "https://playwright.dev/python", "record_duration": 5}
    )
    if response.status_code == 200:
        output_path = OUTPUT_DIR / "test_record.webm"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ WebM recording saved to {output_path}")
    else:
        print(f"✗ Failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_webm_recording_with_scroll():
    """Test WebM video recording with smooth scrolling."""
    response = requests.post(
        f"{BASE_URL}/record",
        json={
            "url": "https://playwright.dev/python/docs/intro",
            "record_duration": 8,
            "scroll_enabled": True
        }
    )
    if response.status_code == 200:
        output_path = OUTPUT_DIR / "test_record_scroll.webm"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ WebM recording with scroll saved to {output_path}")
    else:
        print(f"✗ Failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_webm_recording_with_scroll_up():
    """Test WebM video recording with scrolling down and then back up."""
    response = requests.post(
        f"{BASE_URL}/record",
        json={
            "url": "https://playwright.dev/python/docs/intro",
            "record_duration": 15,
            "scroll_enabled": True,
            "scroll_up_after": True
        }
    )
    if response.status_code == 200:
        output_path = OUTPUT_DIR / "test_record_scroll_up.webm"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ WebM recording with scroll up/down saved to {output_path}")
    else:
        print(f"✗ Failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_active_site_recording():
    """Test recording a site with constant network activity by changing the wait_until strategy."""
    print("  Testing with wait_until='load' to handle active sites...")
    response = requests.post(
        f"{BASE_URL}/record",
        json={
            "url": "https://republicservices.com",
            "record_duration": 10,
            "wait_until": "load",
            "wait_timeout": 60000
        }
    )
    if response.status_code == 200:
        output_path = OUTPUT_DIR / "test_active_site_record.webm"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ Recording of active site saved to {output_path}")
    else:
        print(f"✗ Failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_infinite_scroll_recording():
    """Test the recording cutoff feature on an infinite scrolling page."""
    print("  Testing recording cutoff on an infinite scroll page (Reddit)...")
    response = requests.post(
        f"{BASE_URL}/record",
        json={
            "url": "https://www.reddit.com/r/all/",
            "record_duration": 12,
            "scroll_enabled": True,
            "wait_until": "load",
            "wait_timeout": 60000
        }
    )
    if response.status_code == 200:
        output_path = OUTPUT_DIR / "test_infinite_scroll.webm"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ Infinite scroll recording saved to {output_path}")
    else:
        print(f"✗ Failed: Status {response.status_code}, Response: {response.text}")

@run_test
def test_validation_error():
    """Test for a predictable validation error (e.g., full_page with clip)."""
    response = requests.post(
        f"{BASE_URL}/screenshot",
        json={
            "url": "https://example.com",
            "full_page": True,
            "clip_x": 0, "clip_y": 0, "clip_width": 100, "clip_height": 100
        }
    )
    if response.status_code == 422:
        print("✓ Correctly received validation error (422).")
    else:
        print(f"✗ Failed: Expected validation error but got {response.status_code}")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Test outputs will be saved in '{OUTPUT_DIR.resolve()}'")
    
    test_health_check()
    test_basic_screenshot()
    test_browser_types()
    test_base64_screenshot()
    test_slow_loading_site_with_timeout()
    test_webm_recording()
    test_webm_recording_with_scroll()
    test_webm_recording_with_scroll_up()
    test_active_site_recording()
    test_infinite_scroll_recording()
    test_validation_error()

