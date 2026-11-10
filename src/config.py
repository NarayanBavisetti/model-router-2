"""
Model tiers, prices, Prism questions and knobs. Edit this file to swap models.

Everything runs on Sarvam: one key, one base URL.
  - Decide:  POST /v2/systemone          (sarvam-prism, returns a probability per option, no text)
  - Answer:  POST /v2/chat/completions   (open-weight models on serverless endpoints)

Prices verified on 2026-11-10 from https://docs.sarvam.ai/api/getting-started/pricing (INR per 1M tokens).
Reasoning tokens are billed as output tokens.
"""
import os

SARVAM_BASE_URL = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai/v2")

# Tier order from cheapest-to-run to most capable. Three models cost about the same per token, so the
# order is by how much reasoning they do (and so how many output tokens and seconds they spend).
TIER_ORDER = ["fast", "indic", "mid", "think", "frontier"]

# "extra" holds the body fields each model needs. Sarvam returns HTTP 400 for a field a model does not
# support (it does not ignore it), so nothing else is ever sent. Verified with smoke.py on 2026-11-10.
MODELS = {
    "fast": {
        "model_id": "deepseekv4.1-flash-1017",
        "input_inr_per_m": 14.0,
        "output_inr_per_m": 55.0,
        "timeout_s": 30,
        "max_tokens": 4096,
        "extra": {"reasoning_effort": "none"},  # default is "high"; "none" measured at 0 reasoning tokens
    },
    "indic": {
        "model_id": "sarvam-105b",
        "input_inr_per_m": 15.0,
        "output_inr_per_m": 60.0,
        "timeout_s": 30,
        "max_tokens": 4096,
        "extra": {"reasoning_effort": "none"},  # default is "low"; "none" measured at 0 reasoning tokens
    },
    "mid": {
        "model_id": "gemma4",
        "input_inr_per_m": 35.0,
        "output_inr_per_m": 90.0,
        "timeout_s": 45,
        "max_tokens": 4096,
        "extra": {},  # does not reason unless asked
    },
    "think": {
        "model_id": "glm5.3-flash",
        "input_inr_per_m": 13.5,
        "output_inr_per_m": 45.0,
        "timeout_s": 90,
        "max_tokens": 8192,  # reasoning tokens come out of this budget
        "extra": {"reasoning_effort": "high"},  # accepts low / high / max only; cannot be turned off
    },
    "frontier": {
        "model_id": "glm5.3",
        "input_inr_per_m": 126.0,
        "output_inr_per_m": 390.0,
        "timeout_s": 120,
        "max_tokens": 8192,  # server default is 2048, which reasoning alone can use up
        # accepts low / high / max only. On a loan-EMI question "max" (the default) and "high" both spent
        # ~7,900 of the 8,192 tokens thinking and ran out mid-answer (64 s, ₹3.2). "low" finished in 14 s
        # with 1,031 reasoning tokens (₹0.70).
        "extra": {"reasoning_effort": "low"},
    },
}

# Two ladders.
# FAILOVER_TIER: where a request goes when the chosen model is DOWN (timeout, rate limit, overloaded).
# One tier DOWN: a cheaper answer beats no answer, and an outage must never make a request more expensive.
# Only the cheapest tier has nowhere to go down, so it goes up. Used by the pre-check and by engine.py.
FAILOVER_TIER = {"frontier": "think", "think": "mid", "mid": "fast", "indic": "fast", "fast": "mid"}
# NEXT_TIER: where a request goes when the model ANSWERED but badly (refusal, truncated, judge score below the floor).
# One tier UP, because a weaker model will not fix a bad answer.
NEXT_TIER = {"fast": "mid", "indic": "mid", "mid": "think", "think": "frontier", "frontier": None}

# Lookup 1: workload -> what the customer cares about. Detected from the prompt by Prism.
WORKLOAD_PRIORITY = {
    "classification": "speed",        # voice agent / intent tagging: a pause past ~1.5 s ends the call
    "call_centre_summary": "cost",    # volume makes cost dominant
    "translation": "cost",            # bulk throughput; Indic goes to sarvam-105b anyway
    "document_extraction": "quality", # a wrong number or date is unacceptable
}
DEFAULT_PRIORITY = "balanced"         # workload "other", or Prism not confident enough

# Lookup 3: priority row x difficulty column -> tier.
ROUTE_TABLE = {
    "speed":    {"easy": "fast", "medium": "fast",  "hard": "mid"},
    "cost":     {"easy": "fast", "medium": "mid",   "hard": "think"},
    "balanced": {"easy": "fast", "medium": "mid",   "hard": "frontier"},
    "quality":  {"easy": "mid",  "medium": "think", "hard": "frontier"},
}

# --- Prism: the decision model -------------------------------------------------------
# "prism" (one hosted call, three questions) or "rules" (keyword lists in router.py, ~0.05 ms, no network).
# Rules are also what the router falls back to when the Prism call fails or times out.
ROUTER_CLASSIFIER = "prism"
PRISM_MODEL = "sarvam-prism"
PRISM_INPUT_INR_PER_M = 4.0  # output is free; the prompt is billed once however many questions are asked
PRISM_TIMEOUT_S = 3          # Prism's own server timeout is 60 s; the router must never wait that long
# Prism never cuts the input short: over 32,768 tokens per question the whole request fails with 422.
# So long prompts are trimmed here to the start (where the instruction is) plus the end.
PRISM_HEAD_CHARS = 6000
PRISM_TAIL_CHARS = 2000

# Only "type", "instructions" and "criteria" are allowed per question; any other key is a 422.
PRISM_QUESTIONS = {
    "workload": {  # Lookup 1
        "type": "choice",
        "instructions": "What kind of task is the user asking for?",
        "criteria": {
            "call_centre_summary": "Summarise or review a customer service call, chat or support conversation transcript",
            "document_extraction": "Pull specific fields, values, dates, clauses or tables out of a document such as an "
                                   "invoice, contract, report or form, often returned as JSON or a list",
            "translation": "Translate text from one language into another",
            "classification": "Assign one label, category, intent or sentiment to a short message; the answer is just the label",
            "other": "Anything else",
        },
    },
    "difficulty": {  # Lookup 2. Levels are ordered lowest first; the answer is the expected level, 0.0 to 2.0.
        "type": "score",
        "instructions": "How much reasoning does a correct answer to this task need?",
        "criteria": [
            "Easy: a simple lookup, a label or a yes/no answer",
            "Medium: a straightforward summary, extraction or translation with no calculation or judgement",
            "Hard: multi-step reasoning, analysis, calculation, or reconciling conflicting information",
        ],
    },
    "indic": {
        "type": "noul",
        "instructions": "Is the user's text, or the output they ask for, in an Indian language or Hinglish?",
    },
}

# How the router reads Prism's answers. Starting values; run_benchmark.py prints a sweep to tune them.
WORKLOAD_MIN_CONFIDENCE = 0.5    # below this the workload is treated as "other" (balanced priority)
DIFFICULTY_CUTS = (0.5, 1.5)     # score < 0.5 easy, < 1.5 medium, otherwise hard
DIFFICULTY_MIN_CONFIDENCE = 0.5  # below this the difficulty is rounded UP one level (unsure -> stronger model)
INDIC_MIN_P = 0.5                # P(yes) at or above this counts as Indic

RESOLVED_SCORE = 8  # a request counts as a resolved business outcome when the judge gives >= this

# Failure handling.
# 1. Pre-check: a tier with >= HEALTH_FAIL_THRESHOLD failures in the last HEALTH_WINDOW_S is skipped BEFORE the call
#    (FAILOVER_TIER), so an outage costs the user no extra latency. Failures expire out of the window on their own.
HEALTH_WINDOW_S = 30
HEALTH_FAIL_THRESHOLD = 2
# 2. Same-model retry (providers.py): an account-level rate limit or a 5xx gets one retry inside RETRY_BUDGET_S,
#    and only if no text has been streamed yet. A per-model rate limit is not retried: another model is free now.
RETRY_BUDGET_S = 5
MAX_RETRIES = 1
RETRY_BACKOFF_S = 1.0   # used when Sarvam sends no Retry-After header
# 3. Escalation (engine.py): anything still failing moves once along FAILOVER_TIER; a refusal, a truncated reply
#    or a low judge score moves once along NEXT_TIER. Out of credits, a bad key or a bad request stop the request:
#    every model shares the same key and credits, so another model cannot help.

QUALITY_FLOOR = 5          # judge score (0-10) below which the router escalates once
JUDGE_TIER = "frontier"    # LLM-as-judge runs on this tier; its cost is reported separately
JUDGE_EXTRA = {"reasoning_effort": "low"}  # same as the frontier tier today; kept separate so either can change
JUDGE_MAX_TOKENS = 2048    # the judge model always reasons, and reasoning comes out of this budget
TEMPERATURE = 0.2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # paths work from any working directory
LOG_DIR = os.path.join(BASE_DIR, "logs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
PROMPTS_FILE = os.path.join(BASE_DIR, "data", "prompts.json")
