# Model router 1 vs model router 2

Both routers use the same middle logic: classify the prompt, look up a priority, pick a tier from a table,
fall back once if needed. Two things changed.

| | Router 1 | Router 2 |
|---|---|---|
| Classifier | mDeBERTa zero-shot, runs locally | Sarvam Prism, one hosted call |
| Model pool | Gemini and Claude through OpenRouter, plus `sarvam-105b` | Five open-weight models on Sarvam serverless |
| Keys | OpenRouter + Sarvam | Sarvam only |
| Judge | `gemini-3.8-flash` | `glm5.3` |

Numbers below are from each project's `results/summary.csv`, on the same 39 prompts
(router 1 run on 2026-10-09, router 2 on 2026-11-10).

## Short answers

- **Did latency increase after adding Prism?** The classifier step did: 238 ms → 374 ms per request.
  The whole request got faster (5.0 s → 3.7 s), but that comes from the new model pool, not from Prism.
- **Did cost increase?** Prism adds about ₹0.003 per request, where the local classifier used no tokens.
  Total cost fell from ₹14.40 to ₹3.77 for 39 prompts, again because of the cheaper pool.
- **Did overall performance increase?** Classification did, clearly. Answer quality is the same (9.62),
  and the share of resolved requests went from 95% to 97%, which is one prompt.

## Classifier: DeBERTa vs Prism

| | DeBERTa (router 1) | Prism (router 2) |
|---|---:|---:|
| Workload correct | 32 / 39 | 39 / 39 |
| Difficulty correct | 30 / 39 | 33 / 39 |
| Mean overhead per request | 238 ms | 374 ms |
| Cost per request | no tokens | ₹0.0027 |
| Confidence per answer | no | yes |

## Whole router

| | Router 1 | Router 2 |
|---|---:|---:|
| Serving cost, 39 prompts | ₹14.40 | ₹3.77 |
| Cost vs always-frontier | 24% of ₹60.46 | 42% of ₹8.89 |
| Mean latency | 4,975 ms | 3,658 ms |
| p95 latency | 16,385 ms | 12,380 ms |
| Mean quality (0-10) | 9.62 | 9.62 |
| Resolved (score >= 8) | 94.9% | 97.4% |
| Cost per resolved request | ₹0.389 | ₹0.099 |

## Prism on its own (same pool, router 2 only)

This is the fairest test of Prism, because only the classifier differs: Prism against the keyword rules.

| | Keyword rules | Prism |
|---|---:|---:|
| Workload correct | 32 / 39 | 39 / 39 |
| Classifier overhead | 0.4 ms | 374 ms |
| Mean latency | 3,840 ms | 3,658 ms |
| Serving cost | ₹2.81 | ₹3.77 |
| Mean quality | 9.54 | 9.62 |

Prism classifies better but does not yet save money: it sends more prompts to the expensive `glm5.3`
tier (18% against 10%), and on this dataset the cheap models already score about as well.

## Benefits of router 2

- More accurate classification, with a confidence score the router can act on.
- No local model: no torch or transformers install, no model load at startup, no memory held.
- One provider, one key, one bill in INR.
- Answers stream, and time to first word is logged.
- About a quarter of router 1's cost per resolved request.

## Disadvantages of router 2

- The classifier is a network call: about 135 ms slower, and it can time out or be rate limited
  (the router then falls back to keyword rules). Prism's rate limits are not published.
- Every prompt is sent to Sarvam twice, once to classify and once to answer.
- The pool has no model as strong as Claude Opus, so the quality ceiling is lower for very hard tasks.
- All tiers share one provider and one credit balance: a Sarvam outage or an empty balance stops everything.
- The GLM models cannot turn reasoning off, and `glm5.3` ran out of tokens at higher reasoning settings.
- Routing saves less here (42% of frontier cost against 24% in router 1), because the pool's price
  spread is small and the cheapest model alone scores 9.54.

## Limits of this comparison

- The two projects use different judges, so quality scores are not strictly comparable across them.
- The runs are a month apart, one run each, on 39 prompts. A difference of one or two prompts is noise.
- Router 2's route table has not been tuned yet.
