"""请求/响应模式与求解器领域对象之间的转换。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import solver as S


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------


class CandidateIn(BaseModel):
    dx: int
    dy: int


class PointIn(BaseModel):
    name: str = Field(min_length=1)
    x: int
    y: int


class TriangleIn(BaseModel):
    a: int
    b: int
    c: int


class EdgeIn(BaseModel):
    u: int
    v: int
    min_sq: int = Field(ge=0)
    max_sq: int = Field(ge=0)


class ProblemIn(BaseModel):
    points: list[PointIn]
    candidates: list[list[CandidateIn]]
    triangles: list[TriangleIn]
    edges: list[EdgeIn]


def parse_problem(data: ProblemIn) -> tuple[
    list[S.Point], list[list[S.Candidate]], list[S.Triangle], list[S.Edge]
]:
    points = [S.Point(p.name, p.x, p.y) for p in data.points]
    candidates = [
        [S.Candidate(c.dx, c.dy) for c in group] for group in data.candidates
    ]
    triangles = [S.Triangle(t.a, t.b, t.c) for t in data.triangles]
    edges = [S.Edge(e.u, e.v, e.min_sq, e.max_sq) for e in data.edges]
    return points, candidates, triangles, edges


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

_VIOLATION_TEXT = {
    "orientation": "三角面朝向被破坏（翻折或退化为共线）",
    "length": "边长平方超出登记闭区间",
    "intersection": "不共享端点的边相交或相切",
}


def _violation_message(v: S.Violation, points: list[S.Point]) -> str:
    d = v.detail
    head = _VIOLATION_TEXT.get(v.kind, "约束被破坏")
    if v.kind == "orientation":
        names = "、".join(d["names"])
        if "reachable_positions" in d:
            return (
                f"{head}：三角面（{names}）在全部候选位移组合下均无法保持原始朝向 "
                f"（原二倍有向面积 {d['original_signed_double_area']}），"
                "任何选法都会翻折或退化，无可行方案。"
            )
        return (
            f"{head}：三角面（{names}）二倍有向面积由 "
            f"{d['original_signed_double_area']} 变为 "
            f"{d['actual_signed_double_area']}（枚举顺序下首个破坏朝向的组合）。"
        )
    if v.kind == "length":
        names = "、".join(d["names"])
        if "reachable_min_length_sq" in d:
            return (
                f"{head}：边 {names} 在全部候选组合下长度平方范围仅为 "
                f"[{d['reachable_min_length_sq']}, {d['reachable_max_length_sq']}]，"
                f"与登记闭区间 [{d['min_sq']}, {d['max_sq']}] 无交集，无可行方案。"
            )
        return (
            f"{head}：边 {names} 复测长度平方为 {d['actual_length_sq']}，"
            f"不在闭区间 [{d['min_sq']}, {d['max_sq']}] 内"
            "（枚举顺序下首个破坏长度约束的组合）。"
        )
    names_i = "、".join(d.get("edge_i_names", []))
    names_j = "、".join(d.get("edge_j_names", []))
    return (
        f"{head}：边（{names_i}）与边（{names_j}）不共享端点却存在公共点"
        "（枚举顺序下首个破坏边界不相交约束的组合）。"
    )


def serialize_result(result: S.SolveResult, points: list[S.Point]) -> dict:
    if not result.feasible:
        v = result.violation
        return {
            "feasible": False,
            "combinations_checked": result.combinations_checked,
            "violation": {
                "kind": v.kind,
                "detail": v.detail,
                "message": _violation_message(v, points),
            },
        }

    return {
        "feasible": True,
        "combinations_checked": result.combinations_checked,
        "objective": result.objective,
        "choices": [
            {
                "point_index": ch.point_index,
                "point_name": ch.point_name,
                "original": {"x": points[ch.point_index].x,
                             "y": points[ch.point_index].y},
                "selected_index": ch.selected + 1,  # 页面/接口候选序号自 1 起
                "selected": {"dx": ch.candidate.dx, "dy": ch.candidate.dy},
                "displacement_sq": ch.candidate.dx**2 + ch.candidate.dy**2,
                "moved": {"x": ch.moved_x, "y": ch.moved_y},
                "rejected": [
                    {"index": j + 1, "dx": c.dx, "dy": c.dy,
                     "displacement_sq": c.dx**2 + c.dy**2}
                    for j, c in ch.rejected
                ],
            }
            for ch in result.choices
        ],
        "edges": [
            {
                "edge_index": er.edge_index + 1,
                "u": er.u,
                "v": er.v,
                "names": [points[er.u].name, points[er.v].name],
                "length_sq": er.length_sq,
                "min_sq": er.min_sq,
                "max_sq": er.max_sq,
                "within": er.within,
            }
            for er in result.edges
        ],
        "triangles": [
            {
                "triangle_index": tr.triangle_index + 1,
                "names": [points[tr.a].name, points[tr.b].name,
                          points[tr.c].name],
                "original_signed_double_area": tr.signed_double_area,
                "moved_signed_double_area": tr.moved_signed_double_area,
                "preserved": tr.preserved,
            }
            for tr in result.triangles
        ],
        "moved_points": [
            {"x": x, "y": y} for x, y in result.moved_points
        ],
    }


# ---------------------------------------------------------------------------
# 内置示例（5 个基准点的三角网穹顶片段）
# ---------------------------------------------------------------------------

SAMPLE_PROBLEM: dict = {
    "points": [
        {"name": "P0", "x": 0, "y": 0},
        {"name": "P1", "x": 4, "y": 0},
        {"name": "P2", "x": 5, "y": 3},
        {"name": "P3", "x": 2, "y": 5},
        {"name": "P4", "x": -1, "y": 3},
    ],
    # 每点 2~3 条候选整数位移（含"未位移"基准）。
    "candidates": [
        [{"dx": 0, "dy": 0}, {"dx": 1, "dy": 0}],
        [{"dx": 0, "dy": 0}, {"dx": 0, "dy": 1}],
        [{"dx": 0, "dy": 0}, {"dx": -1, "dy": 0}],
        [{"dx": 0, "dy": 0}, {"dx": 0, "dy": -1}],
        [{"dx": 0, "dy": 0}, {"dx": 1, "dy": 0}, {"dx": 1, "dy": 1}],
    ],
    # 五边形外周 + 自 P0 的两条对角线，剖分为三个同向三角形。
    "triangles": [
        {"a": 0, "b": 1, "c": 2},
        {"a": 0, "b": 2, "c": 3},
        {"a": 0, "b": 3, "c": 4},
    ],
    "edges": [
        # 闭区间刻意收紧：原位置组合在 P0 关联边上全部越界，
        # 只有 P0 采用候选 2（+1,0）复测长度才同时落入区间——演示"联合选定"。
        {"u": 0, "v": 1, "min_sq": 9, "max_sq": 15},    # 原 16 / P0 右移后 9
        {"u": 1, "v": 2, "min_sq": 7, "max_sq": 13},    # 原 10
        {"u": 2, "v": 3, "min_sq": 10, "max_sq": 16},   # 原 13
        {"u": 3, "v": 4, "min_sq": 10, "max_sq": 16},   # 原 13
        {"u": 4, "v": 0, "min_sq": 11, "max_sq": 14},   # 原 10 / 右移后 13
        {"u": 0, "v": 2, "min_sq": 24, "max_sq": 26},   # 原 34 / 右移后 25
        {"u": 0, "v": 3, "min_sq": 25, "max_sq": 27},   # 原 29 / 右移后 26
    ],
}
