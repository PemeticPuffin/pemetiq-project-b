"""
Pemetiq Narrative Stress Test — Flask server
Run: python server.py
"""
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from flask import Flask, render_template, request, jsonify
import anthropic
from dotenv import load_dotenv

load_dotenv()

from schema.enums import CompanyType, InputType
from schema.models import Company
from pipeline.orchestrator import run_analysis
from utils.company_lookup import lookup_cik

app = Flask(__name__)

_ALERT_FLAG_PATH = Path("data/spend_alert_sent.txt")

def _maybe_send_spend_alert(status: dict) -> None:
    """Send one email per day when the daily spend limit is first hit."""
    from config import settings
    if not settings.ALERT_EMAIL or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return  # alerts not configured

    today = datetime.now(timezone.utc).date().isoformat()
    _ALERT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _ALERT_FLAG_PATH.exists() and _ALERT_FLAG_PATH.read_text().strip() == today:
        return  # already sent today

    subject = f"[Pemetiq] Daily spend limit reached — ${status['spent_usd']:.2f} / ${status['limit_usd']:.2f}"
    body = (
        f"The Pemetiq Narrative Stress Test hit its daily spend limit.\n\n"
        f"Date: {today}\n"
        f"Spent: ${status['spent_usd']:.4f}\n"
        f"Limit: ${status['limit_usd']:.2f}\n"
        f"Analyses today: {status['analyses_today']}\n\n"
        f"No further analyses will run today. The limit resets at midnight UTC."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = settings.ALERT_EMAIL

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        _ALERT_FLAG_PATH.write_text(today)
    except Exception:
        pass  # don't crash the app if email fails

SIGNAL_SOURCES = [
    "SEC EDGAR", "Google Trends", "GitHub", "App Store",
    "Job postings", "Wayback Machine", "GDELT", "Wappalyzer",
]

INPUT_TYPE_MAP = {
    "company_name":        InputType.company_name,
    "earnings_transcript": InputType.earnings_transcript,
    "investor_memo":       InputType.investor_memo,
}


@app.route("/")
def index():
    return render_template("index.html", signal_sources=SIGNAL_SOURCES)


@app.route("/run", methods=["POST"])
def run():
    company_name    = request.form.get("company_name", "").strip()
    company_domain  = request.form.get("company_domain", "").strip()
    company_type_str = request.form.get("company_type", "Public")
    input_mode      = request.form.get("input_mode", "company_name")
    input_text      = request.form.get("input_text", "").strip() or None
    competitors_raw = request.form.get("competitors", "").strip()

    if not company_name:
        return render_template("index.html", signal_sources=SIGNAL_SOURCES,
                               error="Company name is required.")

    try:
        cik, ticker = None, None
        if company_type_str == "Public":
            cik, ticker = lookup_cik(company_name)

        domain    = company_domain or f"{company_name.lower().replace(' ','')}.com"
        entity_id = company_name.lower().strip().replace(" ", "_")

        company = Company(
            entity_id=entity_id,
            name=company_name,
            ticker=ticker,
            cik=cik,
            domain=domain,
            company_type=(CompanyType.public if company_type_str == "Public"
                          else CompanyType.private),
        )

        competitors = (
            [c.strip() for c in competitors_raw.split(",") if c.strip()]
            if competitors_raw else None
        )

        result = run_analysis(
            company=company,
            input_text=input_text,
            input_type=INPUT_TYPE_MAP.get(input_mode, InputType.company_name),
            competitors=competitors,
        )

        return render_template("results.html", result=result, company=company)

    except RuntimeError as e:
        if "Daily spend limit" in str(e):
            from spend.tracker import SpendTracker
            _maybe_send_spend_alert(SpendTracker().status())
        return render_template("index.html", signal_sources=SIGNAL_SOURCES,
                               error=str(e))
    except Exception as e:
        return render_template("index.html", signal_sources=SIGNAL_SOURCES,
                               error=f"Analysis failed: {e}")


@app.route("/suggest")
def suggest():
    company_name = request.args.get("company", "").strip()
    if not company_name:
        return jsonify({"competitors": ""})
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content":
                f"Name 4 direct competitors of {company_name}. "
                "Return only a comma-separated list of company names, nothing else."}],
        )
        return jsonify({"competitors": msg.content[0].text.strip()})
    except Exception:
        return jsonify({"competitors": ""})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
