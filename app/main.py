from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .schemas import ClassifyRequest, ClassifyResponse
from .agent import CClastribAgent

APP_NAME = "cclastrib-agent"
app = FastAPI(title=APP_NAME, version="1.0.0")


def get_data_anexos_dir() -> str:
    # Rodando dentro do container, normalmente seu WORKDIR é a raiz do projeto.
    # Ajuste se necessário.
    base = os.getenv("DATA_DIR", "data/anexos")
    return os.path.abspath(base)


agent = CClastribAgent(data_anexos_dir=get_data_anexos_dir(), cache_ttl_seconds=int(os.getenv("CACHE_TTL", "3600")))


@app.get("/health")
def health():
    return {"status": "ok", "data_dir": agent.data_anexos_dir}


@app.post("/classificar", response_model=ClassifyResponse)
def classificar(req: ClassifyRequest):
    try:
        return agent.handle(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload")
def reload_sources():
    # Recarrega CSVs sem reiniciar container
    try:
        agent.reload_sources()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
