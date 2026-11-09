import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_DIR.mkdir(exist_ok=True)

def _locator(page, step):
    by = step.get("by", "none")
    target = step.get("target", "")
    role = step.get("role", "")
    if by == "role":
        if not role or not target:
            raise ValueError("Role locator requires both role and accessible name.")
        return page.get_by_role(role, name=target, exact=False)
    if by == "label":
        return page.get_by_label(target, exact=False)
    if by == "placeholder":
        return page.get_by_placeholder(target, exact=False)
    if by == "text":
        return page.get_by_text(target, exact=False)
    if by == "alt_text":
        return page.get_by_alt_text(target, exact=False)
    if by == "test_id":
        return page.get_by_test_id(target)
    if by == "css":
        # CSS is reserved for cases where semantic locators are unavailable.
        return page.locator(target)
    raise ValueError(f"Unsupported locator type: {by}")

def _resolve_value(value, credentials):
    value = value or ""
    if "{{USERNAME}}" in value and not credentials.get("USERNAME"):
        raise ValueError("A required username or email was not provided in the form.")
    if "{{PASSWORD}}" in value and not credentials.get("PASSWORD"):
        raise ValueError("A required password was not provided in the form.")
    value = value.replace("{{USERNAME}}", credentials.get("USERNAME") or "")
    value = value.replace("{{PASSWORD}}", credentials.get("PASSWORD") or "")
    if "{{USERNAME}}" in value or "{{PASSWORD}}" in value:
        raise ValueError("A required credential was not provided in the form.")
    return value

def _safe_navigation(current_url, destination):
    if not destination.startswith(("http://", "https://")):
        raise ValueError("Navigation target must be an http:// or https:// URL.")
    current = urlparse(current_url)
    target = urlparse(destination)
    # The initial URL is the trust boundary. Cross-origin navigation is blocked.
    if target.netloc != current.netloc:
        raise ValueError("Blocked navigation to a different domain for safety.")
    return destination

def _failure_details(error, credentials):
    details = f"{type(error).__name__}: {str(error)[:500]}"
    for key in ("USERNAME", "PASSWORD"):
        value = credentials.get(key) or ""
        if value:
            details = details.replace(value, "[REDACTED]")
    return details


def execute_test(url: str, plan: dict, credentials: dict, headless: bool = True, stage_callback=None) -> dict:
    started = time.time()
    steps_log = []
    screenshot_path = REPORT_DIR / f"last_run_{int(started)}.png"
    status = "PASS"
    def report_stage(stage):
        if stage_callback:
            stage_callback(stage)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.set_default_timeout(10000)
        try:
            report_stage("1. Opening target URL...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for index, step in enumerate(plan["steps"], start=1):
                action = step["action"]
                description = step.get("description", action)
                try:
                    if action in {"assert_visible", "assert_text"}:
                        report_stage("5. Checking expected results...")
                    else:
                        report_stage("4. Running browser steps...")
                    if action == "navigate":
                        destination = _safe_navigation(page.url, _resolve_value(step.get("value"), credentials))
                        page.goto(destination, wait_until="domcontentloaded", timeout=30000)
                    elif action == "wait":
                        delay = int(step.get("timeout_ms") or 1000)
                        page.wait_for_timeout(max(100, min(delay, 5000)))
                    elif action == "click":
                        loc = _locator(page, step).first
                        loc.click()
                    elif action == "fill":
                        loc = _locator(page, step).first
                        loc.fill(_resolve_value(step.get("value"), credentials))
                    elif action == "press":
                        loc = _locator(page, step).first
                        loc.press(step.get("value") or "Enter")
                    elif action == "assert_visible":
                        loc = _locator(page, step).first
                        loc.wait_for(state="visible", timeout=int(step.get("timeout_ms") or 10000))
                    elif action == "assert_text":
                        expected = step.get("target", "")
                        body_match = expected and page.get_by_text(expected, exact=False).first.is_visible()
                        title_match = expected and expected.lower() in page.title().lower()
                        if not expected or not body_match and not title_match:
                            raise AssertionError(f"Expected visible text was not found: {expected}")
                    else:
                        raise ValueError(f"Unsupported action: {action}")
                    steps_log.append({
                        "index": index, "description": description, "status": "PASS", "details": ""
                    })
                except Exception as exc:
                    status = "FAIL"
                    steps_log.append({
                        "index": index, "description": description, "status": "FAIL",
                        "details": _failure_details(exc, credentials)
                    })
                    break
            if not credentials.get("PASSWORD"):
                page.screenshot(path=str(screenshot_path), full_page=True, timeout=10000)
        except Exception as exc:
            status = "FAIL"
            steps_log.append({
                "index": len(steps_log) + 1, "description": "Open website",
                "status": "FAIL", "details": _failure_details(exc, credentials)
            })
        finally:
            context.close()
            browser.close()

    passed = sum(1 for item in steps_log if item["status"] == "PASS")
    return {
        "status": status,
        "steps_passed": passed,
        "steps_total": len(plan.get("steps", [])),
        "steps": steps_log,
        "duration_seconds": time.time() - started,
        "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
    }
