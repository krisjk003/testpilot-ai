import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from engine.planner import generate_test_plan
from engine.runner import execute_test

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def _redact(text, secrets):
    redacted = text or ""
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted

st.set_page_config(page_title="TestPilot AI", page_icon="🧪", layout="wide")
st.title("TestPilot AI")
st.caption("Browser test execution with Gemini and Playwright.")

with st.sidebar:
    st.header("TestPilot AI")
    model = st.text_input(
        "Gemini model",
        value=os.getenv("GEMINI_MODEL", ""),
        help="Model used to build the execution plan.",
    )
    headless = st.toggle("Headless mode", value=True)

api_key = os.getenv("GEMINI_API_KEY", "")

st.subheader("New Test")
with st.form("test_form"):
    url = st.text_input("Website URL", placeholder="https://example.com")
    test_case = st.text_area(
        "Test Instructions",
        placeholder="Open the login page and verify that the login form is visible.",
        height=110,
    )
    submitted = st.form_submit_button("Run Test", type="primary", use_container_width=True)

if submitted:
    if not api_key:
        st.error("Gemini API key is missing. Configure GEMINI_API_KEY in the local .env file and try again.")
        st.stop()
    if not url.strip() or not test_case.strip():
        st.error("Website URL and test instructions are required.")
        st.stop()
    if not url.strip().lower().startswith(("http://", "https://")):
        st.error("Website URL must start with http:// or https://")
        st.stop()

    credentials = {}
    status_box = st.status("Preparing test...", expanded=True)
    plan = None
    result = None
    def update_stage(message):
        status_box.write(message)

    try:
        status_box.write("1. Opening target URL...")
        status_box.write("2. Inspecting page structure...")
        plan = generate_test_plan(
            api_key=api_key,
            model=model.strip(),
            url=url.strip(),
            test_case=test_case.strip(),
        )
        status_box.write("3. Building execution plan... complete")
        status_box.write("4. Running browser steps...")
        result = execute_test(
            url=url.strip(),
            plan=plan,
            credentials=credentials,
            headless=headless,
            stage_callback=update_stage,
        )
        status_box.write("5. Checking expected results... complete")
        status_box.write("6. Writing report...")
        status_box.update(label=f"Execution Complete: {result['status']}", state="complete" if result["status"] == "PASS" else "error")
        st.subheader("Test Summary")
        if result["status"] == "PASS":
            st.success("PASS - all checks passed.")
        else:
            st.error("FAIL - one or more checks failed.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Result", result["status"])
        c2.metric("Steps completed", f"{result['steps_passed']}/{result['steps_total']}")
        c3.metric("Duration", f"{result['duration_seconds']:.1f}s")

        with st.expander("Execution Plan", expanded=True):
            st.json(plan)
        with st.expander("Step Log", expanded=True):
            for item in result["steps"]:
                icon = "✅" if item["status"] == "PASS" else "❌"
                st.write(f"{icon} Step {item['index']}: {item['description']} — {item['status']}")
                if item.get("details"):
                    st.caption(item["details"])
        if result.get("screenshot") and Path(result["screenshot"]).exists():
            st.subheader("Final Screenshot")
            st.image(result["screenshot"], use_container_width=True)

        report_path = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "url": url.strip(),
            "test_case": test_case.strip(),
            "model": model.strip(),
            "status": result["status"],
            "plan": plan,
            "execution": {k: v for k, v in result.items() if k != "screenshot"},
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        st.download_button(
            "Download Report (JSON)",
            data=json.dumps(report, indent=2),
            file_name=report_path.name,
            mime="application/json",
        )
    except Exception as exc:
        status_box.update(label="Execution Failed", state="error")
        message = _redact(str(exc), (api_key,))
        st.error(message[:800])
        failure_report = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "url": url.strip(),
            "test_case": test_case.strip(),
            "model": model.strip(),
            "status": "FAIL",
            "plan": plan,
            "execution": {
                "status": "FAIL",
                "steps_passed": result.get("steps_passed", 0) if result else 0,
                "steps_total": result.get("steps_total", 0) if result else 0,
                "steps": result.get("steps", []) if result else [],
                "error": message[:800],
            },
        }
        report_path = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(failure_report, indent=2), encoding="utf-8")
        st.caption(f"Failure report saved: {report_path.name}")

st.divider()
st.caption("Restricted browser actions. Test only websites you are authorized to access.")
