import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from generator import generate_awg_config, get_recommended_awg_params
from models import (
    ConfigRequest,
    ConfigResponse,
    ScanRequest,
    ScanProgress,
)
from scanner import scan_endpoints, DEFAULT_RANGES, DEFAULT_PORTS
from warp_keys import generate_keypair, register_warp_account

app = FastAPI(title="AmneziaWG Gen", version="1.0.0")

# In-memory job store  {job_id: list[ScanProgress]}
_jobs: Dict[str, list] = {}
_job_done: Dict[str, asyncio.Event] = {}


# ─── REST endpoints ──────────────────────────────────────────────────────────

@app.get("/api/ranges")
async def get_ranges():
    return {"ranges": DEFAULT_RANGES, "ports": DEFAULT_PORTS}


@app.get("/api/params")
async def get_params():
    return get_recommended_awg_params()


@app.post("/api/scan/start")
async def start_scan(req: ScanRequest):
    job_id = uuid.uuid4().hex
    _jobs[job_id] = []
    event = asyncio.Event()
    _job_done[job_id] = event

    async def run():
        async for progress in scan_endpoints(req):
            _jobs[job_id].append(progress.model_dump())
        event.set()

    asyncio.create_task(run())
    return {"job_id": job_id}


@app.get("/api/scan/{job_id}/results")
async def get_results(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    events = _jobs[job_id]
    results = [e["result"] for e in events if e.get("result") and e["result"]["status"] == "ok"]
    results.sort(key=lambda r: r["latency_ms"] or 9999)
    return {"results": results, "done": _job_done[job_id].is_set()}


@app.post("/api/generate")
async def generate_config(req: ConfigRequest) -> ConfigResponse:
    return generate_awg_config(req)


@app.get("/api/generate/download/{job_id}")
async def download_config(job_id: str):
    # For file download — config is posted then returned; this is a demo placeholder
    raise HTTPException(status_code=404, detail="Use POST /api/generate")


@app.post("/api/warp/register")
async def warp_register():
    try:
        account = await register_warp_account()
        return account
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WARP API error: {e}")


@app.post("/api/keys/generate")
async def generate_keys():
    return generate_keypair()


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/api/scan/ws/{job_id}")
async def scan_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    if job_id not in _jobs:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    sent_index = 0
    try:
        while True:
            events = _jobs.get(job_id, [])
            while sent_index < len(events):
                await websocket.send_json(events[sent_index])
                sent_index += 1

            if _job_done.get(job_id) and _job_done[job_id].is_set() and sent_index >= len(_jobs.get(job_id, [])):
                break

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()


# ─── Static frontend ──────────────────────────────────────────────────────────

FRONTEND = Path(__file__).parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="static")
