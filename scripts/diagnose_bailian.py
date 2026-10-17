"""Zero-token local diagnostic for a Model Studio workspace endpoint."""

import json
import os
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
        print(f"Model list request rejected: HTTP {error.code}")
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
