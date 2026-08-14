"""Start Streamlit without reading a malformed Windows certificate-store entry."""

from __future__ import annotations

import ssl
import sys
import os

import certifi


_original_create_default_context = ssl.create_default_context


def create_default_context_with_certifi(*args, **kwargs):
    try:
        return _original_create_default_context(*args, **kwargs)
    except ssl.SSLError:
        purpose = kwargs.get("purpose", args[0] if args else ssl.Purpose.SERVER_AUTH)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        if purpose == ssl.Purpose.CLIENT_AUTH:
            context.check_hostname = False
        return context


ssl.create_default_context = create_default_context_with_certifi

from streamlit.web.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.argv = [
        "streamlit",
        "run",
        "ui/streamlit_app.py",
        "--server.address",
        os.getenv("STREAMLIT_SERVER_ADDRESS", "127.0.0.1"),
        "--server.port",
        "8501",
        "--server.headless",
        "true",
    ]
    main()
