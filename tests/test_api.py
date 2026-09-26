"""API 层测试：健康检查、示例可裁决、成功/失败证据响应、非法草稿 400。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import SAMPLE_PROBLEM

client = TestClient(app)


def test_healthz_and_index():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "位移联合裁决" in page.text


def test_sample_is_feasible_and_requires_joint_choice():
    s = client.get("/api/sample").json()
    assert s == SAMPLE_PROBLEM
    r = client.post("/api/solve", json=s)
    assert r.status_code == 200
    data = r.json()
    assert data["feasible"] is True
    # 内置示例：原点不动组合在 P0 关联边上越界，P0 必须采用候选 2。
    assert data["choices"][0]["selected_index"] == 2
    assert all(e["within"] for e in data["edges"])
    assert all(t["preserved"] for t in data["triangles"])
    # 每点恰选一条，其余候选全部列入 rejected。
    for ch in data["choices"]:
        assert len(ch["rejected"]) == len(
            s["candidates"][ch["point_index"]]) - 1
    assert data["problem"]["points"][0]["name"] == "P0"


def test_infeasible_orientation_evidence_is_stable():
    problem = {
        "points": [
            {"name": "P0", "x": 0, "y": 0}, {"name": "P1", "x": 4, "y": 0},
            {"name": "P2", "x": 5, "y": 3}, {"name": "P3", "x": 2, "y": 5},
            {"name": "P4", "x": -1, "y": 3},
        ],
        "candidates": [
            [{"dx": 0, "dy": 0}, {"dx": 0, "dy": 0}],
            [{"dx": 0, "dy": 0}, {"dx": 0, "dy": 0}],
            [{"dx": 0, "dy": -4}, {"dx": 1, "dy": -3}],
            [{"dx": 0, "dy": 0}, {"dx": 0, "dy": 0}],
            [{"dx": 0, "dy": 0}, {"dx": 0, "dy": 0}],
        ],
        "triangles": [
            {"a": 0, "b": 1, "c": 2},
            {"a": 0, "b": 2, "c": 3},
            {"a": 0, "b": 3, "c": 4},
        ],
        "edges": [
            {"u": 0, "v": 1, "min_sq": 0, "max_sq": 100},
            {"u": 1, "v": 2, "min_sq": 0, "max_sq": 100},
            {"u": 2, "v": 3, "min_sq": 0, "max_sq": 100},
            {"u": 3, "v": 4, "min_sq": 0, "max_sq": 100},
            {"u": 4, "v": 0, "min_sq": 0, "max_sq": 100},
        ],
    }
    r1 = client.post("/api/solve", json=problem).json()
    r2 = client.post("/api/solve", json=problem).json()
    assert r1["feasible"] is False
    assert r1["violation"]["kind"] == "orientation"
    assert r1["violation"]["message"]
    # 证据稳定可复现。
    assert r1["violation"] == r2["violation"]


def test_invalid_draft_returns_400_not_500():
    bad = {
        "points": [
            {"name": "A", "x": 0, "y": 0}, {"name": "B", "x": 1, "y": 0},
            {"name": "C", "x": 2, "y": 0}, {"name": "D", "x": 2, "y": 2},
            {"name": "E", "x": 0, "y": 2},
        ],
        "candidates": [[{"dx": 0, "dy": 0}, {"dx": 1, "dy": 0}]] * 5,
        "triangles": [{"a": 0, "b": 1, "c": 2}],  # 原始共线
        "edges": [{"u": 0, "v": 3, "min_sq": 0, "max_sq": 9}],
    }
    r = client.post("/api/solve", json=bad)
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "invalid_problem"
    assert "共线" in body["message"]
