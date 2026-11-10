# Model router 2

Sends each prompt to the cheapest Sarvam-hosted open-weight model that is still good enough.
[Sarvam Prism](https://docs.sarvam.ai) decides what kind of task it is and how hard; a small table picks the model.

## How a request is routed

1. **Prism** answers three questions in one call: workload, difficulty, Indic or not (~300 ms, ₹4 per 1M input tokens).
2. Workload → priority (`speed`, `cost`, `balanced`, `quality`).
3. Priority × difficulty → tier. Indic prompts that are not hard go to `sarvam-105b`.
4. If the model is down, step one tier down. If the answer is bad, step one tier up. At most once.

If Prism fails or takes over 3 s, keyword rules decide instead.

| Tier | Model | ₹ per 1M in / out |
|---|---|---|
| fast | `deepseekv4.1-flash-1017` | 14 / 55 |
| indic | `sarvam-105b` | 15 / 60 |
| mid | `gemma4` | 35 / 90 |
| think | `glm5.3-flash` | 13.5 / 45 |
| frontier | `glm5.3` | 126 / 390 |

Models, prices, the route table and thresholds are all in `src/config.py`.

## Run

```bash
python -m venv .venv && .venv/bin/pip install -r src/requirements.txt
cp src/.env.example src/.env      # add SARVAM_API_KEY
cd src
../.venv/bin/python smoke.py                      # checks the key, Prism and all five models
../.venv/bin/uvicorn app:app --reload             # UI at http://localhost:8000
../.venv/bin/python run_benchmark.py --limit 5    # drop --limit for all 39 prompts
```

The benchmark writes `results/summary.csv` and `results/economics.md`. Every request is logged to `logs/requests.jsonl`.

## Results (39 prompts, 2026-11-10)

| Config | Cost (₹) | Mean quality (0-10) | Mean latency |
|---|---:|---:|---:|
| always fast | 0.93 | 9.54 | 2.0 s |
| always frontier | 8.89 | 9.62 | 5.6 s |
| router (Prism) | 3.77 | 9.62 | 3.7 s |

Prism labelled the workload correctly on 39/39 prompts and the difficulty on 33/39.
The router matches the frontier model's quality at 42% of its cost, but on this dataset the fast model alone is nearly as good, so the route table is not yet tuned.
