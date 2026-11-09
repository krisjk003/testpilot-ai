import json
import random
import time

from google import genai
from google.genai import types
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "enum": ["click", "fill", "press", "assert_visible", "assert_text", "navigate", "wait"]
                    },
                    "description": {"type": "STRING"},
                    "by": {
                        "type": "STRING",
                        "enum": ["role", "label", "placeholder", "text", "alt_text", "test_id", "css", "none"]
                    },
                    "role": {"type": "STRING"},
                    "target": {"type": "STRING"},
                    "value": {"type": "STRING"},
                    "timeout_ms": {"type": "INTEGER"}
                },
                "required": ["action", "description", "by", "role", "target", "value", "timeout_ms"]
            }
        }
    },
    "required": ["summary", "steps"]
}

INSPECT_SCRIPT = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const clean = (s) => (s || '').replace(/\\\\s+/g, ' ').trim().slice(0, 180);
  const nodes = [...document.querySelectorAll('a,button,input,textarea,select,[role="button"],[role="link"],[role="textbox"]')]
    .filter(visible).slice(0, 100).map((el) => ({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      type: el.getAttribute('type') || '',
      text: clean(el.innerText || el.value || el.getAttribute('aria-label')),
      label: clean(el.labels ? [...el.labels].map(x => x.innerText).join(' ') : ''),
      placeholder: clean(el.getAttribute('placeholder')),
      aria_label: clean(el.getAttribute('aria-label')),
      name: clean(el.getAttribute('name')),
      href: el.getAttribute('href') || ''
    }));
  return {
    title: document.title,
    url: location.href,
    headings: [...document.querySelectorAll('h1,h2,h3')].filter(visible).map(x => clean(x.innerText)).slice(0, 30),
    visible_text: clean(document.body.innerText).slice(0, 5000),
    interactive_elements: nodes
  };
}
"""

class PlannerError(RuntimeError):
    """Failure during site inspection or plan generation."""


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 4
REQUEST_TIMEOUT_MS = 30000


def _status_code(error: Exception):
    for candidate in (error, getattr(error, "response", None)):
        value = getattr(candidate, "status_code", None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _gemini_error_message(error: Exception, model: str) -> str:
    code = _status_code(error)
    text = str(error).replace("\n", " ")[:500]
    if code == 401 or code == 403:
        return "Gemini rejected the API key or permissions. Check GEMINI_API_KEY and try again."
    if code == 429:
        return "Gemini quota or rate limit was exhausted after retries. Check your project quota and billing."
    if code in RETRYABLE_STATUS_CODES:
        return f"Gemini model '{model}' remained unavailable after retries (HTTP {code}). Try again later or choose an available model."
    if code == 404:
        return f"Gemini model '{model}' is unavailable or not enabled for this API. Check GEMINI_MODEL and the models enabled for your API key."
    if "timeout" in text.lower() or "timed out" in text.lower():
        return "The Gemini request timed out. Check the network and try again."
    if "not found" in text.lower() or "model" in text.lower() and "supported" in text.lower():
        return f"Gemini model '{model}' is unavailable. Check GEMINI_MODEL and the models enabled for your API key."
    return f"Plan generation failed for model '{model}': {text}"


def _generate_with_retries(client, model: str, prompt: str):
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=PLAN_SCHEMA,
        temperature=0.1,
    )
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
        except Exception as error:
            code = _status_code(error)
            retryable = code in RETRYABLE_STATUS_CODES or "timeout" in str(error).lower()
            if not retryable or attempt == MAX_RETRIES:
                raise PlannerError(_gemini_error_message(error, model)) from error
            delay = min(16, 1.5 * (2 ** attempt)) + random.uniform(0, 0.4)
            time.sleep(delay)


def generate_test_plan(api_key: str, model: str, url: str, test_case: str) -> dict:
    if not api_key or not api_key.strip():
        raise PlannerError("A Gemini API key is required. Configure GEMINI_API_KEY in the local .env file.")
    if not model or not model.strip():
        raise PlannerError("No Gemini model is configured. Set GEMINI_MODEL in .env or select a model in the sidebar.")

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
    except Exception as error:
        raise PlannerError(f"Gemini client configuration failed: {str(error)[:500]}") from error

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(10000)
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
            page.wait_for_timeout(500)
            snapshot = page.evaluate(INSPECT_SCRIPT)
        except PlaywrightTimeoutError as error:
            raise PlannerError("The website inspection timed out while waiting for the DOM. Check the URL and try again.") from error
        except Exception as error:
            raise PlannerError(f"Page inspection failed: {type(error).__name__}: {str(error)[:400]}") from error
        finally:
            browser.close()

    prompt = f"""
You are a browser test planner. Convert the user's test case into a short, executable plan
for the current website. Use only the allowed actions and locator types in the schema.
The browser executor will resolve locators using the current page's accessible DOM.

User test case:
{test_case}

Initial website URL:
{url}

Initial website snapshot:
{json.dumps(snapshot, ensure_ascii=False)}

Rules:
- Produce 1 to 12 steps in the correct order.
- Use semantic locators: role, label, placeholder, text, alt_text, or test_id.
- For role locators, set role to a valid role such as button, link, textbox, heading, checkbox.
- For label/placeholder/text/alt_text/test_id locators, put the exact visible or accessible name in target.
- Use by="none" for navigate and wait.
- For a navigation action, value must be a URL. Prefer the supplied site's own origin.
- For fill actions involving credentials, use exactly {{USERNAME}} or {{PASSWORD}} as value.
  Never ask for or invent real credentials. Do not put credential values in the plan.
- Use assert_visible to verify that the expected page element is visible.
- Use assert_text to verify visible text exists on the page; target should be the expected text.
- Do not generate code, JavaScript, XPath, shell commands, or arbitrary selectors.
- Do not perform purchases, payments, account deletion, data destruction, or other irreversible actions.
- If the requested task cannot be completed from the available page context, return a short plan that ends with a verification step likely to fail, and explain the limitation in summary.
"""
    response = _generate_with_retries(client, model.strip(), prompt)
    try:
        plan = json.loads(response.text)
    except (TypeError, json.JSONDecodeError) as error:
        raise PlannerError("Gemini returned invalid JSON instead of a test plan. Try the request again.") from error
    if not isinstance(plan, dict):
        raise PlannerError("Gemini returned an invalid test plan object.")
    if not isinstance(plan.get("steps"), list) or not 1 <= len(plan["steps"]) <= 12:
        raise PlannerError("Gemini returned an invalid plan: expected between 1 and 12 steps.")
    allowed = {"click", "fill", "press", "assert_visible", "assert_text", "navigate", "wait"}
    for step in plan["steps"]:
        if step.get("action") not in allowed:
            raise PlannerError(f"Gemini returned unsupported browser action: {step.get('action')!r}.")
    return plan
