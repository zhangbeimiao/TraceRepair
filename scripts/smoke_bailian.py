"""Run one tiny local connectivity check against Model Studio.

Run this only from a terminal where DASHSCOPE_API_KEY is already set.  It never
prints the key and uses a 64-token output limit.
"""

import os

from tracerepair.model_planner import BailianChatTransport, PlannerError


def main() -> None:
    model = os.getenv("TRACEREPAIR_MODEL", "qwen3.8-flash")
    try:
        response = BailianChatTransport().complete(
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 64,
                "enable_thinking": False,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": 'Return exactly this JSON and nothing else: {"status":"ok"}',
                    }
                ],
            }
        )
    except PlannerError as error:
        print(f"Model Studio connectivity check failed safely: {error}")
        raise SystemExit(1) from error

    choice = response.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    usage = response.get("usage", {})
    print("Model Studio connectivity check succeeded.")
    print(f"Model: {model}")
    print(f"Response: {content}")
    print(f"Usage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}")


if __name__ == "__main__":
    main()
