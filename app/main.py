"""玻璃穹顶裂纹监测位移联合裁决 —— FastAPI 服务。

路由：
  GET  /                 录入与裁决页面（静态单页）
  GET  /healthz          健康检查
  GET  /api/sample       内置示例草稿
  POST /api/solve        提交草稿，返回裁决结果或首个破坏约束的证据
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import solver
from .schemas import SAMPLE_PROBLEM, parse_problem, serialize_result
from .schemas import ProblemIn

logger = logging.getLogger("dome-adjudicator")

app = FastAPI(
    title="玻璃穹顶裂纹监测位移联合裁决",
    version="1.0.0",
    description="每点恰选一条整数候选位移，在朝向、边长闭区间、"
    "非共端点边不相交/相切约束下做全局裁决。",
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/sample")
def get_sample() -> dict:
    return SAMPLE_PROBLEM


@app.post("/api/solve")
def solve_problem(problem: ProblemIn) -> JSONResponse:
    points, candidates, triangles, edges = parse_problem(problem)
    try:
        result = solver.solve(points, candidates, triangles, edges)
    except solver.ProblemError as exc:
        # 录入数据非法：422 风格的稳定错误，而非 500。
        return JSONResponse(
            status_code=400,
            content={
                "feasible": False,
                "error": "invalid_problem",
                "message": str(exc),
            },
        )
    payload = serialize_result(result, points)
    payload["problem"] = problem.model_dump()
    return JSONResponse(payload)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# 静态资源（如有）。
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
