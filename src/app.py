"""FastAPI app: serves the single-page UI and its endpoints. Run from src/: uvicorn app:app --reload"""
import threading, subprocess, sys, os, csv, json, queue
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from config import MODELS, RESULTS_DIR, BASE_DIR
from engine import load_prompts, run_request

app = FastAPI(title="Model Router 2")
_bench = {"running": False, "log": [], "returncode": None}


class RunBody(BaseModel):
    prompt: str
    mode: str | None = None  # None = priority derived from the detected workload
    prompt_id: str | None = None
    config: str = "router"   # router | router_rules | always_<tier>


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.get("/prompts")
def prompts():
    # hidden_difficulty is stripped so the UI (and the router) never see it
    return [{k: v for k, v in p.items() if k != "hidden_difficulty"} for p in load_prompts()]


@app.get("/models")
def models():
    return {"models": MODELS}


def _resolve(body: RunBody) -> tuple[dict, bool]:
    """Match the text to a dataset prompt (by id, or by exact text) so the judge has a rubric. Otherwise it is a
    custom prompt: judge is skipped because there is no reference answer."""
    ps = load_prompts()
    item = next((p for p in ps if p["id"] == body.prompt_id), None)
    if item is None or item["prompt"] != body.prompt:
        item = next((p for p in ps if p["prompt"] == body.prompt), None)
    if item is None:
        return {"id": "custom", "domain": "custom", "prompt": body.prompt, "reference_or_rubric": ""}, False
    return item, True


@app.post("/run")
def run(body: RunBody):
    item, judge = _resolve(body)
    return run_request(item, body.mode, body.config, judge=judge)


@app.post("/run/stream")
def run_stream(body: RunBody):
    """Same as /run but as server-sent events: one event per stage (routed, calling, token, called, judging,
    judged, fallback) and a final `done` with the full record. `token` carries the answer as the model writes it."""
    item, judge = _resolve(body)
    q: queue.Queue = queue.Queue()

    def work():
        try:
            rec = run_request(item, body.mode, body.config, judge=judge,
                              on_event=lambda name, payload: q.put((name, payload)))
            q.put(("done", rec))
        except Exception as e:  # surface the failure to the UI instead of hanging the stream
            q.put(("error", {"message": f"{type(e).__name__}: {e}"}))
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def gen():
        yield f"event: start\ndata: {json.dumps({'judge': judge, 'prompt_id': item['id']})}\n\n"
        while (ev := q.get()) is not None:
            name, payload = ev
            yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/compare")
def compare(body: RunBody):
    """Run the same prompt through the two baselines (real calls, judged) so the router result can be compared."""
    item = next((p for p in load_prompts() if p["id"] == body.prompt_id), None)
    judge = item is not None and item["prompt"] == body.prompt
    if not judge:
        item = {"id": "custom", "domain": "custom", "prompt": body.prompt, "reference_or_rubric": ""}
    return [run_request(item, None, cfg, judge=judge) for cfg in ("always_fast", "always_frontier")]


def _run_benchmark(args):
    _bench.update(running=True, log=[], returncode=None)
    proc = subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "run_benchmark.py"), *args], cwd=BASE_DIR,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        _bench["log"].append(line.rstrip())
    proc.wait()
    _bench.update(running=False, returncode=proc.returncode)


@app.post("/benchmark")
def benchmark(limit: int = 0, all_models: bool = False, classifiers: bool = False):
    if _bench["running"]:
        return {"status": "already running"}
    args = (["--limit", str(limit)] if limit else []) + (["--all-models"] if all_models else []) + (["--classifiers"] if classifiers else [])
    threading.Thread(target=_run_benchmark, args=(args,), daemon=True).start()
    return {"status": "started"}


@app.get("/benchmark/status")
def benchmark_status():
    summary = []
    path = os.path.join(RESULTS_DIR, "summary.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            summary = list(csv.DictReader(f))
    return {**_bench, "log": _bench["log"][-40:], "summary": summary}
