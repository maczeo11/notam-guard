from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
load_dotenv()

from .graph import graph

app = FastAPI(title="NOTAM-Guard", version="0.1.0")

class FlightPlan(BaseModel):
    lat: float
    lon: float
    alt: int
    drone_id: str
    query: Optional[str] = "validate flight DGCA NOTAM"

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/validate")
def validate(fp: FlightPlan):
    state = {"query": fp.query, "lat": fp.lat, "lon": fp.lon, "alt": fp.alt, "drone_id": fp.drone_id,
             "retrieved": [], "citations": [], "verdict": "", "reason": "", "confidence": 0, "ticket_id": "", "requires_human": False}
    # LangSmith trace if env set
    try:
        from langsmith import traceable
        # wrap not needed — langsmith auto via LANGCHAIN_TRACING_V2
        pass
    except: pass
    out = graph.invoke(state)
    return {"verdict": out["verdict"], "reason": out["reason"], "citations": out["citations"],
            "ticket_id": out["ticket_id"], "requires_human": out["requires_human"], "retrieved": out["retrieved"]}

@app.post("/ingest")
def ingest():
    return {"msg": "run python src/ingest.py --docs data/dgca_car.pdf"}

@app.get("/ticket/{tid}")
def ticket(tid: str):
    return {"ticket_id": tid, "status": "open"}
