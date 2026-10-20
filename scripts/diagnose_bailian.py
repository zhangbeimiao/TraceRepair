"""Zero-token local diagnostic for a Model Studio workspace endpoint."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> None:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("TRACEREPAIR_BAILIAN_BASE_URL", "").rstrip("/")
    if not api_key or not base_url:
        print("Missing DASHSCOPE_API_KEY or TRACEREPAIR_BAILIAN_BASE_URL.")
        raise SystemExit(1)
    suffix = "/compatible-mode/v1"
    if not base_url.endswith(suffix):
        print("Base URL does not end with /compatible-mode/v1; copy it again from Model Studio.")
        raise SystemExit(1)

    models_url = base_url[: -len(suffix)] + "/api/v1/models?name=qwen&language=en-US&page_size=100"
    request = Request(models_url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - user-configured Model Studio URL
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = f"Model list request rejected: HTTP {error.code}"
        raw = ""
        diagnostic_found = False
        try:
            raw = error.read().decode("utf-8", errors="replace")[:600]
            parsed = json.loads(raw)
            nested = parsed.get("error")
            candidate = parsed.get("message") or parsed.get("code")
            if not candidate and isinstance(nested, dict):
                candidate = nested.get("message") or nested.get("code")
            if isinstance(candidate, str) and candidate:
                safe = re.sub(r"sk-[A-Za-z0-9._-]+", "[redacted]", candidate)
                detail += f" ({' '.join(safe.split())[:240]})"
                diagnostic_found = True
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        print(detail)
        print(f"Response reason: {error.reason}")
        print(f"Response content type: {error.headers.get('Content-Type', 'unknown')}")
        request_id = error.headers.get("x-request-id") or error.headers.get("x-acs-request-id")
        if request_id:
            print(f"Response request id: {request_id}")
        if raw and not diagnostic_found:
            safe_raw = raw.replace(api_key, "[redacted]")
            safe_raw = re.sub(r"sk-[A-Za-z0-9._-]+", "[redacted]", safe_raw)
            print(f"Sanitized response body: {' '.join(safe_raw.split())[:300]}")
        elif not raw:
            print("Response body: empty")
        raise SystemExit(1) from error
    except URLError as error:
        print(f"Model list request failed: {type(error.reason).__name__}")
        raise SystemExit(1) from error

    models = body.get("output", {}).get("models", [])
    model_ids = [item.get("model") for item in models if isinstance(item, dict) and item.get("model")]
    print("Model list request succeeded.")
    print("Available Qwen model IDs: " + (", ".join(model_ids) if model_ids else "none"))


if __name__ == "__main__":
    main()
