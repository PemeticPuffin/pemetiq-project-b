"""Inject the Cloudflare Web Analytics beacon into Streamlit's served HTML.

Runs once before `streamlit run` (see railway.toml startCommand / Procfile).
Streamlit has no supported way to add <head> tags, so we patch its static
index.html in place. Idempotent — safe to run on every boot.

The beacon token is public by design (it ships in client HTML regardless).
"""
from pathlib import Path

import streamlit

SNIPPET = (
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"bd5755fbe1e84bad8cff2f8db3e0364c\"}'></script>"
)


def main() -> None:
    index = Path(streamlit.__file__).parent / "static" / "index.html"
    html = index.read_text()
    if "cloudflareinsights.com/beacon" in html:
        print("Analytics beacon already present — nothing to do.")
        return
    index.write_text(html.replace("</head>", SNIPPET + "</head>", 1))
    print(f"Analytics beacon injected into {index}")


if __name__ == "__main__":
    main()
