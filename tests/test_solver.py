"""求解器单元测试：几何判定、目标序、首违证据稳定性。"""

from __future__ import annotations

import itertools

import pytest

from app.solver import (
    Candidate,
    Edge,
    Point,
    ProblemError,
    Triangle,
    _segments_intersect_or_touch,
    cross,
    solve,
)


# ---------------------------------------------------------------------------
# 几何原语
# ---------------------------------------------------------------------------


def test_cross_sign():
    assert cross(0, 0, 1, 0, 0, 1) == 1
    assert cross(0, 0, 0, 1, 1, 0) == -1
    assert cross(0, 0, 1, 1, 2, 2) == 0


@pytest.mark.parametrize(
    "p,q,r,s,expected",
    [
        # 规范相交
        ((0, 0), (4, 0), (2, -2), (2, 2), True),
        # 不相交
        ((0, 0), (1, 0), (2, 0), (3, 0), False),
        # T 形相接（相切必须算冲突）
        ((0, 0), (4, 0), (2, 0), (2, 3), True),
        # 端点恰好落在另一线段内部
        ((0, 0), (4, 0), (4, 0), (4, 4), True),
        # 共线重叠
        ((0, 0), (4, 0), (2, 0), (6, 0), True),
        # 共线但不接触
        ((0, 0), (2, 0), (3, 0), (5, 0), False),
        # 共线端点相接
        ((0, 0), (2, 0), (2, 0), (4, 0), True),
        # 交叉于线段延长线上（不算）
        ((0, 0), (2, 2), (0, 3), (1, 2), False),
    ],
)
def test_segment_intersection(p, q, r, s, expected):
    assert _segments_intersect_or_touch(p, q, r, s) is expected
    # 交换两线段、反向，结论不变。
    assert _segments_intersect_or_touch(r, s, p, q) is expected
    assert _segments_intersect_or_touch(q, p, r, s) is expected


# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------


def base_problem():
    """凸五边形 P0..P4，三条从 P0 出发的剖分对角线。"""
    pts = [
        Point("P0", 0, 0), Point("P1", 4, 0), Point("P2", 5, 3),
        Point("P3", 2, 5), Point("P4", -1, 3),
    ]
    tris = [Triangle(0, 1, 2), Triangle(0, 2, 3), Triangle(0, 3, 4)]
    edges = [
        Edge(0, 1, 0, 100), Edge(1, 2, 0, 100), Edge(2, 3, 0, 100),
        Edge(3, 4, 0, 100), Edge(4, 0, 0, 100),
        Edge(0, 2, 0, 100), Edge(0, 3, 0, 100),
    ]
    return pts, tris, edges


def make_candidates(cands_per_point):
    return [[Candidate(dx, dy) for dx, dy in cs] for cs in cands_per_point]


# ---------------------------------------------------------------------------
# 基本裁决
# ---------------------------------------------------------------------------


def test_each_point_picks_exactly_one_and_zero_combination_feasible():
    pts, tris, edges = base_problem()
    cands = make_candidates([[(0, 0), (1, 1)]] * 5)
    res = solve(pts, cands, tris, edges)
    assert res.feasible
    assert len(res.choices) == 5
    assert all(ch.moved_x == pts[i].x and ch.moved_y == pts[i].y
               for i, ch in enumerate(res.choices))
    # 全零：目标值为 0，且按字典序各点选候选 1。
    assert res.objective == {"max_displacement_sq": 0, "sum_displacement_sq": 0}
    assert [ch.selected for ch in res.choices] == [0, 0, 0, 0, 0]
    assert all(len(ch.rejected) == 1 for ch in res.choices)
    assert res.combinations_checked == 2**5
    assert all(t.preserved for t in res.triangles)
    assert all(e.within for e in res.edges)


def test_enumerates_all_combinations_three_to_the_eighth():
    ys = [0, 2, 1, 3, 0, 2, 4, 1]  # 任意相邻三点不共线
    pts = [Point(f"P{i}", i, ys[i]) for i in range(8)]
    tris = [Triangle(0, 1, 2), Triangle(2, 3, 4)]
    edges = [Edge(0, 1, 0, 10_000), Edge(1, 2, 0, 10_000),
             Edge(2, 3, 0, 10_000), Edge(3, 4, 0, 10_000)]
    cands = [[Candidate(0, 0), Candidate(1, 0), Candidate(0, 1)] for _ in pts]
    res = solve(pts, cands, tris, edges)
    assert res.feasible
    assert res.combinations_checked == 3**8  # 6561
    assert [ch.selected for ch in res.choices] == [0] * 8


def _bruteforce_optimum(pts, cands, tris, edges):
    """独立穷举 oracle：复算全部约束与目标序，返回最优键（含相交判定）。"""
    pairs = [(i, j) for i in range(len(edges)) for j in range(i + 1, len(edges))
             if len({edges[i].u, edges[i].v, edges[j].u, edges[j].v}) == 4]
    orig = [cross(pts[t.a].x, pts[t.a].y, pts[t.b].x, pts[t.b].y,
                  pts[t.c].x, pts[t.c].y) for t in tris]
    best = None
    for combo in itertools.product(*[range(len(c)) for c in cands]):
        moved = [(pts[i].x + cands[i][k].dx, pts[i].y + cands[i][k].dy)
                 for i, k in enumerate(combo)]
        ok = True
        for ti, t in enumerate(tris):
            a = cross(*moved[t.a], *moved[t.b], *moved[t.c])
            if a == 0 or (a > 0) != (orig[ti] > 0):
                ok = False
                break
        if not ok:
            continue
        for e in edges:
            d = (moved[e.u][0] - moved[e.v][0]) ** 2 + (
                moved[e.u][1] - moved[e.v][1]) ** 2
            if not e.min_sq <= d <= e.max_sq:
                ok = False
                break
        if not ok:
            continue
        for i, j in pairs:
            ei, ej = edges[i], edges[j]
            if _segments_intersect_or_touch(moved[ei.u], moved[ei.v],
                                            moved[ej.u], moved[ej.v]):
                ok = False
                break
        if not ok:
            continue
        key = (
            max(cands[i][k].dx ** 2 + cands[i][k].dy ** 2
                for i, k in enumerate(combo)),
            sum(cands[i][k].dx ** 2 + cands[i][k].dy ** 2
                for i, k in enumerate(combo)),
            combo,
        )
        if best is None or key < best:
            best = key
    return best


def test_objective_order_max_then_sum_then_lexicographic():
    # 定制场景：边 P4-P0 的闭区间 [6,18] 使 P0 的候选 sq=1（位移 (0,1)，
    # 长度²=5）越界；只剩 sq=2 的 (1,1)（长度²=8）与 sq=4 的 (2,0)（长度²=18）
    # 可行 => "最大位移²最小"必须选择 (1,1)，而不是局部位移看似更大的 (2,0)。
    pts, tris, edges = base_problem()
    edges[4] = Edge(4, 0, 6, 18)
    cands = make_candidates([
        [(0, 1), (1, 1), (2, 0)],   # P0：sq ∈ {1, 2, 4}（按录入序）
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
    ])
    res = solve(pts, cands, tris, edges)
    assert res.feasible
    assert res.objective["max_displacement_sq"] == 2
    assert res.objective["sum_displacement_sq"] == 2
    sel = [ch.selected for ch in res.choices]
    assert sel[0] == 1  # (1,1)，sq=2

    # 独立穷举复核完整目标序（max → sum → 点序候选序号字典序）。
    best = _bruteforce_optimum(pts, cands, tris, edges)
    assert best is not None
    assert (res.objective["max_displacement_sq"],
            res.objective["sum_displacement_sq"], tuple(sel)) == best


def test_lexicographic_tie_break_prefers_earlier_point_smaller_index():
    pts, tris, edges = base_problem()
    # 两条候选完全等价（同为零位移）时，序号字典序最小 => 全部候选 1。
    cands = [[Candidate(0, 0), Candidate(0, 0)] for _ in pts]
    res = solve(pts, cands, tris, edges)
    assert res.feasible
    assert [ch.selected for ch in res.choices] == [0] * 5


# ---------------------------------------------------------------------------
# 三类约束
# ---------------------------------------------------------------------------


def test_orientation_flip_detected_and_reported():
    pts, tris, edges = base_problem()
    # P2 的两条候选都把它拉到边 P0-P1 另一侧/共线：面 (P0,P1,P2) 必翻或退化，
    # 与其他点如何选择无关 => 全局不可行的朝向证据。
    cands = make_candidates([
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
        [(0, -4), (1, -3)],   # (5,-1) 翻到 P0P1 另一侧；(6,0) 共线退化
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
    ])
    res = solve(pts, cands, tris, edges)
    assert not res.feasible
    assert res.violation.kind == "orientation"
    d = res.violation.detail
    assert d["triangle_index"] == 0
    assert "reachable_positions" in d


def test_orientation_collinear_degeneration_is_strict():
    pts, tris, edges = base_problem()
    cands = make_candidates([
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
        [(0, -3), (1, -3)],   # P2 → (5,0) 或 (6,0)，均落在 P0P1 直线上 => 面积 0
        [(0, 0), (0, 0)],
        [(0, 0), (0, 0)],
    ])
    res = solve(pts, cands, tris, edges)
    assert not res.feasible
    assert res.violation.kind == "orientation"


def test_length_closed_interval_inclusive_bounds():
    pts, tris, edges = base_problem()
    edges[0] = Edge(0, 1, 16, 16)  # 原长平方恰为 16
    cands = make_candidates([[(0, 0), (-1, 0)]] + [[(0, 0), (0, 0)]] * 4)
    res = solve(pts, cands, tris, edges)
    assert res.feasible  # 闭区间：恰好 16 合法
    assert res.edges[0].length_sq == 16 and res.edges[0].within

    edges[0] = Edge(0, 1, 17, 100)  # 可达 {16（不动）, 25（P0 左移）}
    res = solve(pts, cands, tris, edges)
    assert res.feasible and res.choices[0].selected == 1

    edges[0] = Edge(0, 1, 17, 24)  # 可达 {16,25} 全部在区间外
    res = solve(pts, cands, tris, edges)
    assert not res.feasible
    assert res.violation.kind == "length"
    d = res.violation.detail
    assert d["edge_index"] == 0
    assert (d["reachable_min_length_sq"], d["reachable_max_length_sq"]) == (16, 25)


def test_nonadjacent_edge_touching_is_rejected():
    # 构造：两条不共享端点的边在某种选法下端点相切 => 该选法非法。
    pts = [
        Point("P0", 0, 0), Point("P1", 4, 0), Point("P2", 4, 4),
        Point("P3", 0, 4), Point("P4", -3, 2),
    ]
    tris = [Triangle(0, 1, 2), Triangle(0, 2, 3)]
    edges = [
        Edge(0, 1, 0, 100), Edge(1, 2, 0, 100), Edge(2, 3, 0, 100),
        Edge(3, 0, 0, 100), Edge(0, 2, 0, 100),
        Edge(4, 0, 0, 100),  # P4-P0 与边 1-2 不共享端点
    ]
    # P4 候选 (-3,2)（原位，不相切）或 (5,2)：移动后 P4-P0 穿过/接触边 1-2？
    # P4=(5,2)：线段 (5,2)-(0,0) 与竖直线段 (4,0)-(4,4) 在 (4,1.6) 相交。
    cands = make_candidates([
        [(0, 0), (0, 0)], [(0, 0), (0, 0)], [(0, 0), (0, 0)],
        [(0, 0), (0, 0)], [(-3, 2), (5, 2)],
    ])
    res = solve(pts, cands, tris, edges)
    assert res.feasible  # 退回原位可行
    assert res.choices[4].selected == 0

    # 两条候选都把 P4 移到与竖边 P1-P2 相交的位置 => 无解，证据为 intersection。
    cands[4] = [Candidate(5, 2), Candidate(5, 4)]
    res = solve(pts, cands, tris, edges)
    assert not res.feasible
    assert res.violation.kind == "intersection"


def test_shared_endpoint_edges_never_count_as_intersection():
    pts, tris, edges = base_problem()
    cands = make_candidates([[(0, 0), (0, 0)]] * 5)
    res = solve(pts, cands, tris, edges)
    assert res.feasible  # 剖分对角线在 P0 处共享端点，合法


# ---------------------------------------------------------------------------
# 录入校验
# ---------------------------------------------------------------------------


def test_invalid_inputs():
    pts, tris, edges = base_problem()
    with pytest.raises(ProblemError):
        solve(pts[:4], [[Candidate(0, 0)] * 2] * 4, tris, edges)
    with pytest.raises(ProblemError):
        solve(pts, [[Candidate(0, 0)]] * 5, tris, edges)  # 每点仅 1 条候选
    bad_tris = [Triangle(0, 0, 1), *tris]
    with pytest.raises(ProblemError):
        solve(pts, make_candidates([[(0, 0)]] * 5), bad_tris, edges)
    collin = [Point("A", 0, 0), Point("B", 1, 0), Point("C", 2, 0),
              Point("D", 2, 2), Point("E", 0, 2)]
    with pytest.raises(ProblemError):
        solve(collin, make_candidates([[(0, 0)]] * 5),
              [Triangle(0, 1, 2)], [Edge(0, 3, 0, 9), Edge(1, 4, 0, 9)])
    with pytest.raises(ProblemError):
        solve(pts, make_candidates([[(0, 0)]] * 5), tris,
              [Edge(0, 1, 10, 5), *edges[1:]])  # 下界 > 上界
