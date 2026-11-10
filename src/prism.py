"""Sarvam Prism, the decision model. One call per request: the prompt goes in as `state`, the three
questions from config.py go with it, and a probability for every option comes back. No text is generated.
This file only asks and returns the raw answers; router.py turns them into a decision."""
import time, httpx
from config import (SARVAM_BASE_URL, PRISM_MODEL, PRISM_QUESTIONS, PRISM_TIMEOUT_S, PRISM_HEAD_CHARS,
                    PRISM_TAIL_CHARS, PRISM_INPUT_INR_PER_M)
from providers import auth_headers, classify_http

PRISM_URL = SARVAM_BASE_URL + "/systemone"


def trim(prompt: str) -> str:
    """Prism rejects an over-long input instead of cutting it, so keep the start and the end."""
    if len(prompt) <= PRISM_HEAD_CHARS + PRISM_TAIL_CHARS:
        return prompt
    return prompt[:PRISM_HEAD_CHARS] + "\n[...]\n" + prompt[-PRISM_TAIL_CHARS:]


def decide(prompt: str) -> dict:
    """Returns {error, detail, ms, input_tokens, cost_inr, workload, workload_confidence, workload_probabilities,
    difficulty_score, difficulty_confidence, difficulty_probabilities, indic_p}. error is "none" when Prism answered."""
    out = {"error": "none", "detail": "", "ms": 0.0, "input_tokens": 0, "cost_inr": 0.0}
    body = {"model": PRISM_MODEL, "state": trim(prompt), "questions": PRISM_QUESTIONS}
    t0 = time.perf_counter()
    try:
        r = httpx.post(PRISM_URL, headers=auth_headers(), json=body, timeout=PRISM_TIMEOUT_S)
        out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if r.status_code != 200:
            out["error"], out["detail"] = classify_http(r)
            return out
        data = r.json()
        a = data["answers"]
        w, d = a["workload"], a["difficulty"]
        out.update(
            input_tokens=(data.get("usage") or {}).get("input_tokens") or 0,
            workload=w["choice"], workload_confidence=round(w["confidence"], 4),
            workload_probabilities={k: round(v, 4) for k, v in w["probabilities"].items()},
            difficulty_score=round(d["score"], 4), difficulty_confidence=round(d["confidence"], 4),
            difficulty_probabilities={k: round(v, 4) for k, v in d["probabilities"].items()},
            indic_p=round(a["indic"]["noul"], 4),
        )
        out["cost_inr"] = out["input_tokens"] / 1e6 * PRISM_INPUT_INR_PER_M
    except httpx.TimeoutException:
        out.update(error="timeout", detail=f"> {PRISM_TIMEOUT_S}s", ms=round((time.perf_counter() - t0) * 1000, 1))
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        out.update(error="overloaded", detail=f"{type(e).__name__}: {e}"[:200],
                   ms=round((time.perf_counter() - t0) * 1000, 1))
    return out
