"""Thin HTTP wrapper around Sarvam chat completions (streaming). Every call names the exact model id
from config.py and sends only the body fields that model accepts."""
import json, os, time, httpx
from dotenv import load_dotenv
from config import MODELS, SARVAM_BASE_URL, TEMPERATURE, RETRY_BUDGET_S, MAX_RETRIES, RETRY_BACKOFF_S

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
CHAT_URL = SARVAM_BASE_URL + "/chat/completions"

REFUSAL_PHRASES = [
    "i can't help", "i cannot help", "i can't assist", "i cannot assist", "i'm unable to",
    "i am unable to", "i can't provide", "i cannot provide", "i won't be able to",
    "as an ai language model", "i'm not able to help", "i must decline",
]

# Error classes. Each one tells the engine what to do next.
RETRYABLE = ("rate_limit", "overloaded")                              # one retry on the same model
OUTAGE = ("timeout", "rate_limit", "model_rate_limit", "overloaded")  # this model is down: fail over to another
FATAL = ("no_credits", "auth", "bad_request")                         # another model cannot help: stop

MIN_INTERVAL_S = 0.0  # run_benchmark.py raises this to stay under the per-model requests-per-minute limit
_last_call: dict[str, float] = {}


def looks_like_refusal(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    head = t[:200]
    return any(p in head for p in REFUSAL_PHRASES)


def auth_headers() -> dict:
    return {"api-subscription-key": os.getenv("SARVAM_API_KEY", ""), "Content-Type": "application/json"}


def _result(text="", input_tokens=0, output_tokens=0, reasoning_tokens=0, latency_ms=0.0, ttft_ms=None,
            error="none", detail="", retries=0, served_model=None):
    return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens, "latency_ms": round(latency_ms, 1),
            "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
            "error": error, "error_detail": detail, "retries": retries, "served_model": served_model}


def classify_http(r: httpx.Response) -> tuple[str, str]:
    """Map a non-200 Sarvam response to an error class, using the status and error.code from the body."""
    code, msg = "", r.text[:200]
    try:
        e = r.json().get("error")
        if isinstance(e, dict):
            code, msg = str(e.get("code") or ""), str(e.get("message") or "")[:200]
    except ValueError:
        pass
    detail = f"HTTP {r.status_code} {code}: {msg}".replace("  ", " ")
    s = r.status_code
    if s == 402 or code == "seat_budget_exhausted_error":
        return "no_credits", detail   # topping up fixes it, waiting does not
    if s == 403:
        return "auth", detail         # Sarvam answers a bad key with 403, not 401
    if s == 429:
        return ("model_rate_limit" if code == "model_rate_limit_exceeded_error" else "rate_limit"), detail
    if s in (500, 502, 503):
        return "overloaded", detail
    if s in (408, 504):
        return "timeout", detail
    return "bad_request", detail      # 400 / 404 / 422: our request is wrong, retrying will not change it


def _stream_once(body: dict, timeout_s: float, on_token) -> tuple[str, str, dict, str | None]:
    """One streamed attempt. Returns (error_class, detail, collected, retry_after_header)."""
    got = {"text": "", "usage": {}, "finish": None, "model": None, "ttft_ms": None}
    t0 = time.perf_counter()
    try:
        with httpx.stream("POST", CHAT_URL, headers=auth_headers(), json=body, timeout=timeout_s) as r:
            if r.status_code != 200:
                r.read()
                err, detail = classify_http(r)
                return err, detail, got, r.headers.get("retry-after")
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                if obj.get("error"):  # an error can arrive mid-stream with HTTP 200
                    return "overloaded", str(obj["error"])[:200], got, None
                got["model"] = obj.get("model") or got["model"]
                if obj.get("usage"):  # the last chunk has empty choices and carries usage
                    got["usage"] = obj["usage"]
                for ch in obj.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content") or ""
                    if piece:
                        if got["ttft_ms"] is None:
                            got["ttft_ms"] = (time.perf_counter() - t0) * 1000
                        got["text"] += piece
                        if on_token:
                            on_token(piece)
                    if ch.get("finish_reason"):
                        got["finish"] = ch["finish_reason"]
    except httpx.TimeoutException:
        return "timeout", f"> {timeout_s}s", got, None
    except httpx.HTTPError as e:
        return "overloaded", f"{type(e).__name__}: {e}"[:200], got, None
    return "none", "", got, None


def call_model(tier: str, prompt: str, system: str | None = None, max_tokens: int | None = None,
               on_token=None, extra: dict | None = None) -> dict:
    """Stream one chat completion. on_token(text) is called for every piece of the answer as it arrives.
    extra overrides the tier's own body fields (the judge uses it to ask for less reasoning). Returns a dict with text, token counts, latency, time to first token and an error class ("none" = ok)."""
    m = MODELS[tier]
    if not os.getenv("SARVAM_API_KEY"):
        return _result(error="auth", detail="SARVAM_API_KEY is not set in .env")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": m["model_id"], "messages": messages, "max_tokens": max_tokens or m["max_tokens"],
            "temperature": TEMPERATURE, "stream": True, "stream_options": {"include_usage": True}, **(m["extra"] if extra is None else extra)}

    wait = _last_call.get(m["model_id"], 0) + MIN_INTERVAL_S - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[m["model_id"]] = time.time()

    # Waits count as latency. Failed attempts carry no tokens and no cost. A retry only happens before any text
    # has been streamed, so the caller never sees an answer restart.
    t0 = time.perf_counter()
    retries = 0
    while True:
        err, detail, got, retry_after = _stream_once(body, m["timeout_s"], on_token)
        elapsed = time.perf_counter() - t0
        if err in RETRYABLE and not got["text"] and retries < MAX_RETRIES and elapsed < RETRY_BUDGET_S:
            pause = RETRY_BACKOFF_S * (retries + 1)
            try:
                pause = float(retry_after) if retry_after else pause
            except ValueError:
                pass
            time.sleep(min(pause, max(0.0, RETRY_BUDGET_S - elapsed)))
            retries += 1
            continue
        break
    latency = (time.perf_counter() - t0) * 1000
    served = got["model"] or m["model_id"]
    if err != "none":
        return _result(latency_ms=latency, error=err, detail=detail + (f" (after {retries} retries)" if retries else ""),
                       retries=retries, served_model=served)
    usage = got["usage"]
    text = got["text"].strip()
    in_tok, out_tok = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
    reason_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    # A stream that ends without a normal finish, with text but no billed output, or that ran out of
    # max_tokens (reasoning tokens come out of the same budget, so the answer is cut off or missing) is a failed call.
    if got["finish"] not in (None, "stop", "end_turn") or (text and not out_tok):
        return _result(text, in_tok, out_tok, reason_tok, latency, got["ttft_ms"], error="truncated",
                       detail=f"finish_reason={got['finish']}, completion_tokens={usage.get('completion_tokens')}",
                       retries=retries, served_model=served)
    return _result(text, in_tok, out_tok, reason_tok, latency, got["ttft_ms"], retries=retries, served_model=served)


def cost_inr(tier: str, input_tokens: int, output_tokens: int) -> float:
    m = MODELS[tier]
    return input_tokens / 1e6 * m["input_inr_per_m"] + output_tokens / 1e6 * m["output_inr_per_m"]
