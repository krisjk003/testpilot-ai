# TestPilot AI

TestPilot AI converts test instructions into browser actions, runs them with Playwright, and records PASS/FAIL results.

## Requirements

- Python 3.10 or later
- A Gemini API key
- Git
- Chromium installed through Playwright

## Clone the Repository

Clone the project from GitHub:

```bash
git clone https://github.com/krisjk003/testpilot-ai.git

```

Navigate into the project directory:

```bash
cd testpilot-ai
```

## Installation

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright Chromium:

```bash
playwright install chromium
```

## Configuration

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) and add it to `.env`:

```env
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Keep `.env` local. Do not commit or share your API key.

## Run

Start the application:

```bash
streamlit run app.py
```

Open the local Streamlit URL displayed in your terminal.

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

