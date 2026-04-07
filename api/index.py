from flask import Flask, Response, request
import os
import requests
from urllib.parse import urlsplit

app = Flask(__name__)
BACKEND_URL = (os.getenv("BACKEND_URL") or "").strip().rstrip("/")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


def rewrite_location(location_value: str) -> str:
    if not location_value or not BACKEND_URL:
        return location_value
    backend_parts = urlsplit(BACKEND_URL)
    location_parts = urlsplit(location_value)

    if location_parts.scheme and location_parts.netloc:
        if location_parts.netloc == backend_parts.netloc:
            return location_parts._replace(scheme="", netloc="").geturl()
        return location_value

    return location_value


def forward_request(path: str = ""):
    if not BACKEND_URL:
        return {
            "error": "BACKEND_URL is not configured on Vercel.",
            "hint": "Set BACKEND_URL to your Render backend URL and redeploy.",
        }, 500

    target_url = f"{BACKEND_URL}/{path}" if path else BACKEND_URL
    if request.query_string:
        target_url = f"{target_url}?{request.query_string.decode('utf-8')}"

    headers = {
        key: value
        for key, value in request.headers
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    headers["Host"] = urlsplit(BACKEND_URL).netloc

    response = requests.request(
        method=request.method,
        url=target_url,
        headers=headers,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        timeout=60,
    )

    excluded_response_headers = {
        "content-length",
        "transfer-encoding",
        "connection",
    }

    response_headers = []
    for key, value in response.headers.items():
        if key.lower() in excluded_response_headers:
            continue
        if key.lower() == "location":
            value = rewrite_location(value)
        response_headers.append((key, value))

    return Response(
        response.content,
        status=response.status_code,
        headers=response_headers,
    )


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def proxy(path):
    return forward_request(path)
