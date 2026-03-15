from __future__ import annotations

import json
import os


def llm_call(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    try:
        import litellm
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except ImportError:
        pass

    return _raw_openai_call(messages, model, temperature, max_tokens)


def llm_call_structured(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict:
    text = llm_call(messages, model, temperature, max_tokens)
    # Extract JSON from response (handle markdown code blocks)
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines[1:] if not l.strip() == "```"]
        text = "\n".join(lines)
    return json.loads(text)


def _raw_openai_call(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    import urllib.request
    import urllib.error

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]
