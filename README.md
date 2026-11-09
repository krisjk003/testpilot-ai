# TestPilot AI

TestPilot AI converts test instructions into browser actions, runs them with Playwright, and records PASS/FAIL results.

## Requirements

- Python 3.10 or later
- A Gemini API key
- Chromium installed through Playwright

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Create `.env` from the example file and add a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey):

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Keep `.env` local. Do not commit the API key.

## Run

```bash
streamlit run app.py
```

Open the local Streamlit URL in a browser.

## Example

Website URL:

```text
https://example.com
```

Test instructions:

```text
Open the website and verify that the text
"This domain is for use in documentation examples"
is visible.
```

The application inspects the page, sends the snapshot and instructions to Gemini, builds an execution plan, runs it with Playwright, and displays a PASS/FAIL report.

## Execution Flow

```text
Test instructions -> Page inspection -> Gemini plan -> Playwright execution -> Result verification -> JSON report
```

## Security and Limitations

- The API key is loaded from the local `.env` file.
- Credential placeholders are never populated by the application.
- Generated actions are restricted to supported browser operations.
- Cross-domain navigation after the initial page is restricted.
- CAPTCHA, multi-factor authentication, complex shadow DOM elements, and highly dynamic websites may require additional handling.
- Test only websites you are authorized to access.
