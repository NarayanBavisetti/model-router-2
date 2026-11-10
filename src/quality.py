"""Quality scoring. Swappable: replace `score()` with anything that returns the same dict.
Default = exact match for classification, LLM-as-judge (frontier tier, 0-10) for everything else.
Judge tokens/cost are returned separately and never mixed into serving cost."""
import json, re
from config import JUDGE_TIER, JUDGE_MAX_TOKENS, JUDGE_EXTRA
from providers import call_model, cost_inr

JUDGE_SYSTEM = "You are a strict grader. Reply with JSON only."
JUDGE_PROMPT = """Grade the ANSWER to the TASK against the REFERENCE/RUBRIC on a 0-10 scale.
10 = fully correct and complete, 5 = partially correct or missing key points, 0 = wrong, empty, off-task or refused.
Judge content, not style. Do not reward length. Answers in the language the task asked for are fine.

TASK:
{task}

REFERENCE/RUBRIC:
{rubric}

ANSWER:
{answer}

Reply exactly as: {{"score": <integer 0-10>, "reason": "<one short sentence>"}}"""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-෿ ]+", " ", (s or "").lower()).strip()


def score(prompt_item: dict, answer: str) -> dict:
    """Returns {score (0-10), method, reason, judge_input_tokens, judge_output_tokens, judge_cost_inr, judge_error}."""
    base = {"judge_input_tokens": 0, "judge_output_tokens": 0, "judge_cost_inr": 0.0, "judge_error": "none"}
    if prompt_item["domain"] == "classification":
        ref, ans = _norm(prompt_item["reference_or_rubric"]), _norm(answer)
        # exact match, or the label is the whole first line / the answer is short and contains only that label
        lines = [l.strip() for l in ans.split("\n") if l.strip()]
        first, last = (lines[0], lines[-1]) if lines else ("", "")
        # Accept the label as the whole answer, as the first line, as the last line (prompts that ask for
        # reasoning first and the label at the end), or as a short answer that contains nothing else.
        ok = (ans == ref or first == ref or last == ref or last.endswith(" " + ref) or last.startswith(ref + " ")
              or (ref in ans and len(ans.split()) <= len(ref.split()) + 3))
        return {**base, "score": 10 if ok else 0, "method": "exact_match",
                "reason": f"expected '{ref}', got '{ans[:40]}'"}

    res = call_model(JUDGE_TIER, JUDGE_PROMPT.format(task=prompt_item["prompt"][:6000],
                                                     rubric=prompt_item["reference_or_rubric"],
                                                     answer=(answer or "")[:6000]),
                     system=JUDGE_SYSTEM, max_tokens=JUDGE_MAX_TOKENS, extra=JUDGE_EXTRA)
    out = {**base, "method": f"llm_judge:{JUDGE_TIER}",
           "judge_input_tokens": res["input_tokens"], "judge_output_tokens": res["output_tokens"],
           "judge_cost_inr": round(cost_inr(JUDGE_TIER, res["input_tokens"], res["output_tokens"]), 4)}
    if res["error"] != "none":
        return {**out, "score": None, "reason": "judge failed", "judge_error": res["error"]}
    m = re.search(r"\{.*?\}", res["text"], re.S)
    try:
        j = json.loads(m.group(0))
        return {**out, "score": max(0, min(10, int(j["score"]))), "reason": str(j.get("reason", ""))[:200]}
    except Exception:
        n = re.search(r"\d+", res["text"])
        return {**out, "score": int(n.group(0)) if n else None, "reason": "unparsed: " + res["text"][:80]}
