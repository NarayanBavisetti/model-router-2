"""Batch benchmark. Runs every prompt SEQUENTIALLY through each config so latency numbers stay honest.
Usage: python run_benchmark.py [--limit 3] [--all-models] [--classifiers] [--all-modes]
Writes results/summary.csv, results/economics.md and prints a table per config."""
import argparse, csv, os, statistics, time, uuid
from collections import Counter
from datetime import date
from config import (MODELS, TIER_ORDER, RESULTS_DIR, QUALITY_FLOOR, JUDGE_TIER, RESOLVED_SCORE, PRISM_INPUT_INR_PER_M,
                    WORKLOAD_MIN_CONFIDENCE, DIFFICULTY_CUTS, DIFFICULTY_MIN_CONFIDENCE)
from engine import load_prompts, run_request
from router import read_prism
import health, providers

CONFIGS = [("always_fast", None), ("always_frontier", None), ("router", None)]
ALL_MODELS = [("always_indic", None), ("always_mid", None), ("always_think", None)]  # every other model on its own
CLASSIFIERS = [("router_rules", None)]                                    # same policy, keyword classifier instead of Prism
EXTRA = [("router", "speed"), ("router", "cost"), ("router", "quality")]  # force one priority for every prompt
REQUESTS_PER_MIN = 45  # Sarvam allows 50 per model per minute on pay-as-you-go


def p95(xs):
    xs = sorted(xs)
    return xs[max(0, int(round(0.95 * len(xs))) - 1)] if xs else 0


def summarise(name, recs):
    n = len(recs)
    scored = [r["quality_score"] for r in recs if r["quality_score"] is not None]
    mix = Counter(r["route"] for r in recs)
    cost = sum(r["cost_inr"] for r in recs)
    in_tok, out_tok = sum(r["input_tokens"] for r in recs), sum(r["output_tokens"] for r in recs)
    answer_tok = out_tok - sum(r["reasoning_tokens"] for r in recs)  # output the user actually reads
    ttfts = [r["ttft_ms"] for r in recs if r["ttft_ms"] is not None]
    acc = [r["difficulty"] == r["hidden_difficulty"] for r in recs if r["hidden_difficulty"]]
    wacc = [r["workload"] == r["hidden_workload"] for r in recs if r["hidden_workload"]]
    resolved = sum(1 for s in scored if s >= RESOLVED_SCORE)
    return {
        "config": name, "n": n,
        "cost_inr": round(cost, 4), "router_cost_inr": round(sum(r["router_cost_inr"] for r in recs), 4),
        "input_tokens": in_tok, "output_tokens": out_tok, "reasoning_tokens": out_tok - answer_tok,
        # ₹ per 1M input tokens (Prism included) and per 1M ANSWER tokens (reasoning tokens are paid for but not
        # read, so their cost is spread over the answer tokens). These two rates drive the monthly projection.
        "blended_in_inr_per_m": round(sum(r["model_in_inr"] + r["router_cost_inr"] for r in recs) / in_tok * 1e6, 2) if in_tok else 0,
        "blended_out_inr_per_m": round(sum(r["model_out_inr"] for r in recs) / answer_tok * 1e6, 2) if answer_tok else 0,
        "mean_latency_ms": round(statistics.mean(r["total_latency_ms"] for r in recs), 0),
        "p95_latency_ms": round(p95([r["total_latency_ms"] for r in recs]), 0),
        "mean_ttft_ms": round(statistics.mean(ttfts), 0) if ttfts else None,
        "mean_router_overhead_ms": round(statistics.mean(r["router_overhead_ms"] for r in recs), 1),
        "mean_quality": round(statistics.mean(scored), 2) if scored else None,
        "resolved_rate": round(resolved / n, 3),
        "cost_per_resolved_inr": round(cost / resolved, 4) if resolved else None,
        "fallback_rate": round(sum(r["fallback_fired"] for r in recs) / n, 3),
        "error_rate": round(sum(r["error"] != "none" for r in recs) / n, 3),
        "routing_accuracy": round(sum(acc) / len(acc), 3) if acc else None,
        "workload_accuracy": round(sum(wacc) / len(wacc), 3) if wacc else None,
        "judge_cost_inr": round(sum(r["judge_cost_inr"] for r in recs), 4),
        **{f"mix_{t}": round(mix[t] / n, 3) for t in TIER_ORDER},
    }


def print_table(s):
    print(f"\n=== {s['config']} (n={s['n']}) ===")
    print(f"  total serving cost : ₹{s['cost_inr']:.4f}  (of which Prism ₹{s['router_cost_inr']:.4f})   judge cost (separate): ₹{s['judge_cost_inr']:.2f}")
    print(f"  latency mean / p95 : {s['mean_latency_ms']:.0f} ms / {s['p95_latency_ms']:.0f} ms  (first token {s['mean_ttft_ms']} ms, router overhead {s['mean_router_overhead_ms']:.0f} ms)")
    print(f"  mean quality (0-10): {s['mean_quality']}    fallback rate: {s['fallback_rate']:.0%}    error rate: {s['error_rate']:.0%}")
    print(f"  resolved (>= {RESOLVED_SCORE}/10): {s['resolved_rate']:.0%}    cost per resolved outcome: ₹{s['cost_per_resolved_inr']}")
    print(f"  tokens             : {s['input_tokens']} in, {s['output_tokens']} out ({s['reasoning_tokens']} of them reasoning)")
    print(f"  routing mix        : " + ", ".join(f"{t} {s['mix_' + t]:.0%}" for t in TIER_ORDER if s['mix_' + t]))
    print(f"  routing accuracy   : difficulty {s['routing_accuracy']}, workload {s['workload_accuracy']}  (vs hidden labels)")


def print_sweep(recs):
    """Re-read the Prism answers already logged for this run under other thresholds. No new calls."""
    rows = [r for r in recs if r["prism"] and r["prism"]["error"] == "none" and r["hidden_difficulty"]]
    if not rows:
        return
    n = len(rows)
    print(f"\n--- Prism threshold sweep (n={n}, same answers, no new calls). Current settings marked * ---")
    print("  workload: min confidence -> accuracy, prompts sent to 'other'")
    for wmin in (0.0, 0.3, 0.5, 0.7, 0.9):
        got = [read_prism(r["prism"], workload_min=wmin)[0] for r in rows]
        ok = sum(g == r["hidden_workload"] for g, r in zip(got, rows))
        print(f"   {'*' if wmin == WORKLOAD_MIN_CONFIDENCE else ' '} {wmin:.1f} -> {ok}/{n}, {got.count('other')} other")
    print("  difficulty: cut points, min confidence (below it: round up) -> accuracy, called too easy / too hard")
    order = {"easy": 0, "medium": 1, "hard": 2}
    for cuts in ((0.5, 1.5), (0.6, 1.4), (0.7, 1.3), (0.4, 1.6), (0.5, 1.3), (0.7, 1.5)):
        for dmin in (0.0, 0.5, 0.7):
            got = [read_prism(r["prism"], cuts=cuts, difficulty_min=dmin)[1] for r in rows]
            ok = sum(g == r["hidden_difficulty"] for g, r in zip(got, rows))
            low = sum(order[g] < order[r["hidden_difficulty"]] for g, r in zip(got, rows))
            mark = "*" if cuts == DIFFICULTY_CUTS and dmin == DIFFICULTY_MIN_CONFIDENCE else " "
            print(f"   {mark} {cuts}, {dmin:.1f} -> {ok}/{n}, {low} too easy, {n - ok - low} too hard")


def write_economics(summaries, path):
    IN_M, OUT_M = 50, 10  # million tokens / month
    rows = [(s["config"], IN_M * s["blended_in_inr_per_m"] + OUT_M * s["blended_out_inr_per_m"], s) for s in summaries]
    frontier = next((r[1] for r in rows if r[0] == "always_frontier"), None)
    lines = [f"# Economics: 50M input + 10M output tokens / month", "",
             f"Generated {date.today().isoformat()}. Prices as listed in `config.py` on that date, in INR.", "",
             "| Config | Monthly cost (INR) | Saved vs always_frontier | ₹ / 1M input | ₹ / 1M answer tokens |",
             "|---|---:|---:|---:|---:|"]
    for name, inr, s in rows:
        saved = f"{(1 - inr / frontier):.1%}" if frontier else "n/a"
        lines.append(f"| {name} | ₹{inr:,.0f} | {saved} | {s['blended_in_inr_per_m']} | {s['blended_out_inr_per_m']} |")
    lines += ["", "## Cost per resolved business outcome", "",
              f"A request is resolved when the judge scores it >= {RESOLVED_SCORE}/10. This is the number to show client teams: not price per token, but what one usable result costs.", "",
              "| Config | Resolved rate | Cost per resolved outcome (₹) | Mean quality | Mean latency (ms) | First token (ms) |", "|---|---:|---:|---:|---:|---:|"]
    for name, inr, s in rows:
        lines.append(f"| {name} | {s['resolved_rate']:.0%} | {s['cost_per_resolved_inr']} | {s['mean_quality']} | {s['mean_latency_ms']:.0f} | {s['mean_ttft_ms']} |")
    lines += ["", "## Measured routing mix (share of prompts by final tier)", "",
              "| Config | " + " | ".join(TIER_ORDER) + " | fallback rate | mean quality |", "|---|" + "---:|" * (len(TIER_ORDER) + 2)]
    for name, inr, s in rows:
        lines.append(f"| {name} | " + " | ".join(f"{s['mix_' + t]:.0%}" for t in TIER_ORDER) + f" | {s['fallback_rate']:.0%} | {s['mean_quality']} |")
    lines += ["", "## Tier list prices used (INR per 1M tokens)", "", "| Tier | Model | Input | Output | Body fields sent |", "|---|---|---:|---:|---|"]
    for t in TIER_ORDER:
        m = MODELS[t]
        lines.append(f"| {t} | {m['model_id']} | ₹{m['input_inr_per_m']} | ₹{m['output_inr_per_m']} | `{m['extra'] or 'none'}` |")
    lines += ["", "## Assumptions", "",
              f"- Volume: {IN_M}M input + {OUT_M}M output tokens per month. Output means answer tokens the user reads.",
              "- Every row uses rates measured in this benchmark: serving cost divided by tokens. Reasoning tokens are billed as output but are not part of the answer, so their cost is spread over the answer tokens. That is why a model that reasons costs more per 1M answer tokens than its list price.",
              f"- Router rows include the Prism call (₹{PRISM_INPUT_INR_PER_M} per 1M input tokens, output free) and any fallback retries.",
              "- The prompt mix of the benchmark is assumed representative of production traffic.",
              "- Judge (LLM-as-judge) cost is an evaluation cost and is excluded from all monthly figures.",
              "- No prompt caching, batch discounts or volume discounts assumed.",
              f"- Quality floor for fallback = {QUALITY_FLOOR}/10; judge = {JUDGE_TIER} tier.", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only run the first N prompts (dry run)")
    ap.add_argument("--all-models", action="store_true", help="also run every other model on its own (always_indic / always_mid / always_think)")
    ap.add_argument("--classifiers", action="store_true", help="also run the router with the keyword-rules classifier")
    ap.add_argument("--all-modes", action="store_true", help="also run the router with one forced priority (speed / cost / quality)")
    args = ap.parse_args()
    prompts = load_prompts()[: args.limit or None]
    run_id = uuid.uuid4().hex[:8]
    configs = (CONFIGS[:1] + (ALL_MODELS if args.all_models else []) + CONFIGS[1:]
               + (CLASSIFIERS if args.classifiers else []) + (EXTRA if args.all_modes else []))
    os.makedirs(RESULTS_DIR, exist_ok=True)
    providers.MIN_INTERVAL_S = 60 / REQUESTS_PER_MIN
    summaries, t0 = [], time.time()
    for config, mode in configs:
        name = config if not (config == "router" and mode) else f"router_{mode}_forced"
        health.reset()
        recs = []
        for i, p in enumerate(prompts, 1):
            r = run_request(p, mode, config, run_id=run_id)
            recs.append(r)
            print(f"[{name}] {i}/{len(prompts)} {p['id']:6s} -> {r['route']:9s} q={r['quality_score']} "
                  f"{r['total_latency_ms']:.0f}ms ₹{r['cost_inr']:.4f} fb={r['fallback_fired']} err={r['error']}", flush=True)
        s = summarise(name, recs)
        summaries.append(s)
        print_table(s)
        by_dom = {}
        for r in recs:
            by_dom.setdefault(r["domain"], []).append(r)
        print("  per workload       : " + "; ".join(
            f"{d}: ₹{sum(x['cost_inr'] for x in xs):.3f}, q={statistics.mean([x['quality_score'] for x in xs if x['quality_score'] is not None] or [0]):.1f}, p95={p95([x['total_latency_ms'] for x in xs]):.0f}ms"
            for d, xs in by_dom.items()))
        if name == "router":
            print_sweep(recs)
    with open(os.path.join(RESULTS_DIR, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
        w.writeheader(); w.writerows(summaries)
    write_economics(summaries, os.path.join(RESULTS_DIR, "economics.md"))
    print(f"\nDone in {time.time() - t0:.0f}s. run_id={run_id}. Wrote results/summary.csv and results/economics.md")


if __name__ == "__main__":
    main()
