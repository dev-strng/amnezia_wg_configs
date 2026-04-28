from fastapi import FastAPI, HTTPException
from mangum import Mangum
from generator import generate_awg_config, get_recommended_awg_params
from models import ConfigRequest, ConfigResponse, ScanRequest
from warp_keys import generate_keypair, register_warp_account
from scanner import DEFAULT_RANGES, DEFAULT_PORTS

app = FastAPI(title="AmneziaWG Gen", version="1.0.0")

@app.get("/api/ranges")
async def get_ranges():
    return {"ranges": DEFAULT_RANGES, "ports": DEFAULT_PORTS}

@app.get("/api/params")
async def get_params():
    return get_recommended_awg_params()

@app.post("/api/scan/start")
async def start_scan(req: ScanRequest):
    # Vercel serverless doesn't support background scanning.
    raise HTTPException(status_code=501, detail="Background scanning not supported on Vercel.")

@app.post("/api/generate")
async def generate_config(req: ConfigRequest) -> ConfigResponse:
    return generate_awg_config(req)

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

handler = Mangum(app)
