"""Step 0: check the Sarvam endpoints with the real key before building on them.

Run:  python smoke.py
Makes 1 model-list call, 1 Prism call and 1 tiny chat call per pool model.
"""
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
BASE = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai/v2")
HEADERS = {"api-subscription-key": os.environ["SARVAM_API_KEY"], "Content-Type": "application/json"}

# model -> extra body fields (the reasoning setting the router plans to send)
POOL = {
    "deepseekv4.1-flash-1017": {"reasoning_effort": "none"},
    "sarvam-105b": {"reasoning_effort": "none"},
    "gemma4": {},
    "glm5.3-flash": {},
    "glm5.3": {},
}

PRISM_BODY = {
    "model": "sarvam-prism",
    "state": "Summarise this support call: customer ka refund 10 din se pending hai, agent ne 48 ghante ka promise kiya.",
    "questions": {
        "workload": {
            "type": "choice",
            "instructions": "What kind of task is this?",
            "criteria": {
                "call_centre_summary": "A customer service call transcript to summarise",
                "document_extraction": "A document to extract fields from",
                "translation": "Text to translate into another language",
                "classification": "A message to classify with a label",
                "other": "Anything else",
            },
        },
        "difficulty": {
            "type": "score",
            "instructions": "How much reasoning does a correct answer need?",
            "criteria": [
                "A simple lookup, label or yes/no answer",
                "A summarisation, extraction or translation task",
                "Multi-step reasoning, analysis or calculation",
            ],
        },
        "indic": {
            "type": "noul",
            "instructions": "Is the text, or the requested output, in an Indian language or Hinglish?",
        },
    },
}


def show_headers(r):
    keep = {k: v for k, v in r.headers.items()
            if any(s in k.lower() for s in ("ratelimit", "rate-limit", "retry-after", "request-id"))}
    print("  headers:", keep or "(no rate-limit / request-id headers)")


def call(method, path, body=None, timeout=60):
    t0 = time.perf_counter()
    r = httpx.request(method, BASE + path, headers=HEADERS, json=body, timeout=timeout)
    ms = round((time.perf_counter() - t0) * 1000)
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:500]}
    return r, data, ms


def main():
    print(f"== GET {BASE}/models")
    r, data, ms = call("GET", "/models")
    print(f"  status {r.status_code} in {ms} ms")
    listed = {}
    for m in data.get("data", data if isinstance(data, list) else []):
        if isinstance(m, dict) and m.get("type", "chat") == "chat":
            listed[m.get("id")] = m
            print(f"  {m.get('id'):40} access={m.get('access')} ctx={m.get('context_length')}")
    if not listed:
        print("  body:", json.dumps(data)[:600])
    for model in POOL:
        if listed and model not in listed:
            print(f"  !! {model} is not in the model list")

    print(f"\n== POST {BASE}/systemone  (sarvam-prism)")
    r, data, ms = call("POST", "/systemone", PRISM_BODY)
    print(f"  status {r.status_code} in {ms} ms")
    show_headers(r)
    print("  body:", json.dumps(data, ensure_ascii=False, indent=2)[:1500])

    for model, extra in POOL.items():
        print(f"\n== POST {BASE}/chat/completions  ({model}, extra={extra})")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 512,
            "temperature": 0.2,
            **extra,
        }
        r, data, ms = call("POST", "/chat/completions", body)
        print(f"  status {r.status_code} in {ms} ms")
        show_headers(r)
        if r.status_code != 200 or not data.get("choices"):
            print("  body:", json.dumps(data, ensure_ascii=False)[:600])
            continue
        choice = data["choices"][0]
        msg = choice.get("message", {})
        print(f"  served model: {data.get('model')}  finish_reason: {choice.get('finish_reason')}")
        print(f"  content: {(msg.get('content') or '')[:80]!r}")
        print(f"  reasoning chars: {len(msg.get('reasoning_content') or '')}")
        print("  usage:", json.dumps(data.get("usage")))


if __name__ == "__main__":
    main()
