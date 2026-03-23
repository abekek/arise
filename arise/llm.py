from __future__ import annotations

import json
import os
import sys
import threading
import time


class CostTracker:
    """Thread-safe LLM cost tracker."""

    # Approximate costs per 1M tokens (as of 2024)
    MODEL_COSTS = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "claude-sonnet": {"input": 3.00, "output": 15.00},
    }

    def __init__(self):
        self._lock = threading.Lock()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.total_cost_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int):
        with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_calls += 1
            # Estimate cost
            costs = self._get_costs(model)
            self.total_cost_usd += (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    def _get_costs(self, model: str) -> dict:
        for key, costs in self.MODEL_COSTS.items():
            if key in model.lower():
                return costs
        return {"input": 1.0, "output": 3.0}  # conservative default

    def summary(self) -> dict:
        with self._lock:
            return {
                "total_calls": self.total_calls,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_cost_usd": round(self.total_cost_usd, 4),
            }

    def reset(self):
        with self._lock:
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_calls = 0
            self.total_cost_usd = 0.0


# Module-level singleton
cost_tracker = CostTracker()


def llm_call(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _llm_call_once(messages, model, temperature, max_tokens)
        except Exception as e:
            last_error = e
            if not _is_retryable(e):
                raise
            wait = min(2 ** attempt, 10)
            print(f"[ARISE:llm] Retry {attempt + 1}/{max_retries} after {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
    raise last_error  # type: ignore[misc]


def _llm_call_once(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        import litellm
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120,
        )
        # Record usage
        if hasattr(response, 'usage') and response.usage:
            cost_tracker.record(model, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0)
        return response.choices[0].message.content
    except ImportError:
        pass

    return _raw_openai_call(messages, model, temperature, max_tokens)


def _is_retryable(error: Exception) -> bool:
    error_str = str(error).lower()
    # Rate limits, timeouts, server errors
    for pattern in ["429", "rate limit", "timeout", "timed out", "502", "503", "504", "connection"]:
        if pattern in error_str:
            return True
    return False


def llm_call_structured(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 8192,
    max_retries: int = 3,
) -> dict:
    text = llm_call(messages, model, temperature, max_tokens, max_retries)
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip() == "```"]
        text = "\n".join(lines)
    # Try to extract JSON object or array from the text
    if not text.startswith(("{", "[")):
        start = text.find("{")
        arr_start = text.find("[")
        if arr_start != -1 and (start == -1 or arr_start < start):
            start = arr_start
        if start != -1:
            text = text[start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to parse just the first JSON object or array
        decoder = json.JSONDecoder()
        try:
            result, _ = decoder.raw_decode(text)
            return result
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {text[:200]}") from e


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

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        # Record usage
        usage = data.get("usage", {})
        if usage:
            cost_tracker.record(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenAI API error {e.code}: {body[:200]}") from e
