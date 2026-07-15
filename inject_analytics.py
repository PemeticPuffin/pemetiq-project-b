"""Inject the Cloudflare Web Analytics beacon into Streamlit's served HTML.

Runs once before `streamlit run` (see railway.toml startCommand / Procfile).
Streamlit has no supported way to add <head> tags, so we patch its static
index.html in place. Idempotent — safe to run on every boot; replaces any
stale beacon (e.g. an old token) rather than duplicating it.

The beacon token is public by design (it ships in client HTML regardless).
"""
import re
from pathlib import Path

import streamlit

SNIPPET = (
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"34111545a9ac499097ad6fcfcaba5081\"}'></script>"
)

_STALE_BEACON = re.compile(r"<script[^>]*cloudflareinsights[^>]*></script>")


def main() -> None:
    index = Path(streamlit.__file__).parent / "static" / "index.html"
    html = index.read_text()
    if SNIPPET in html:
        print("Analytics beacon already current — nothing to do.")
        return
    html = _STALE_BEACON.sub("", html)
    index.write_text(html.replace("</head>", SNIPPET + "</head>", 1))
    print(f"Analytics beacon injected into {index}")


if __name__ == "__main__":
    main()
