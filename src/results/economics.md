# Economics: 50M input + 10M output tokens / month

Generated 2026-11-10. Prices as listed in `config.py` on that date, in INR.

| Config | Monthly cost (INR) | Saved vs always_frontier | ₹ / 1M input | ₹ / 1M answer tokens |
|---|---:|---:|---:|---:|
| always_fast | ₹1,250 | 88.5% | 14.0 | 55.0 |
| always_indic | ₹1,350 | 87.6% | 15.0 | 60.0 |
| always_mid | ₹2,650 | 75.7% | 35.0 | 90.0 |
| always_think | ₹1,232 | 88.7% | 13.5 | 55.65 |
| always_frontier | ₹10,896 | 0.0% | 126.0 | 459.55 |
| router | ₹4,834 | 55.6% | 58.48 | 191.01 |
| router_rules | ₹3,446 | 68.4% | 43.09 | 129.12 |

## Cost per resolved business outcome

A request is resolved when the judge scores it >= 8/10. This is the number to show client teams: not price per token, but what one usable result costs.

| Config | Resolved rate | Cost per resolved outcome (₹) | Mean quality | Mean latency (ms) | First token (ms) |
|---|---:|---:|---:|---:|---:|
| always_fast | 95% | 0.0251 | 9.54 | 1958 | 435.0 |
| always_indic | 82% | 0.0356 | 8.79 | 5342 | 281.0 |
| always_mid | 85% | 0.0494 | 8.97 | 1117 | 216.0 |
| always_think | 92% | 0.0315 | 9.51 | 3846 | 997.0 |
| always_frontier | 97% | 0.234 | 9.62 | 5582 | 1651.0 |
| router | 97% | 0.0991 | 9.62 | 3658 | 1229.0 |
| router_rules | 95% | 0.076 | 9.54 | 3840 | 1684.0 |

## Measured routing mix (share of prompts by final tier)

| Config | fast | indic | mid | think | frontier | fallback rate | mean quality |
|---|---:|---:|---:|---:|---:|---:|---:|
| always_fast | 100% | 0% | 0% | 0% | 0% | 0% | 9.54 |
| always_indic | 0% | 100% | 0% | 0% | 0% | 0% | 8.79 |
| always_mid | 0% | 0% | 100% | 0% | 0% | 0% | 8.97 |
| always_think | 0% | 0% | 0% | 100% | 0% | 0% | 9.51 |
| always_frontier | 0% | 0% | 0% | 0% | 100% | 0% | 9.62 |
| router | 8% | 18% | 28% | 28% | 18% | 3% | 9.62 |
| router_rules | 10% | 31% | 15% | 33% | 10% | 5% | 9.54 |

## Tier list prices used (INR per 1M tokens)

| Tier | Model | Input | Output | Body fields sent |
|---|---|---:|---:|---|
| fast | deepseekv4.1-flash-1017 | ₹14.0 | ₹55.0 | `{'reasoning_effort': 'none'}` |
| indic | sarvam-105b | ₹15.0 | ₹60.0 | `{'reasoning_effort': 'none'}` |
| mid | gemma4 | ₹35.0 | ₹90.0 | `none` |
| think | glm5.3-flash | ₹13.5 | ₹45.0 | `{'reasoning_effort': 'high'}` |
| frontier | glm5.3 | ₹126.0 | ₹390.0 | `{'reasoning_effort': 'low'}` |

## Assumptions

- Volume: 50M input + 10M output tokens per month. Output means answer tokens the user reads.
- Every row uses rates measured in this benchmark: serving cost divided by tokens. Reasoning tokens are billed as output but are not part of the answer, so their cost is spread over the answer tokens. That is why a model that reasons costs more per 1M answer tokens than its list price.
- Router rows include the Prism call (₹4.0 per 1M input tokens, output free) and any fallback retries.
- The prompt mix of the benchmark is assumed representative of production traffic.
- Judge (LLM-as-judge) cost is an evaluation cost and is excluded from all monthly figures.
- No prompt caching, batch discounts or volume discounts assumed.
- Quality floor for fallback = 5/10; judge = frontier tier.
