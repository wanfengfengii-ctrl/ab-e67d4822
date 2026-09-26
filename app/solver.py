"""玻璃穹顶裂纹监测点位移联合裁决 —— 精确整数几何求解器。

每个基准点从 2~3 条候选整数位移中恰好选择一条，要求：

  1. 所有登记三角面复测后保持与原基线网**严格相同**的有向朝向（面积符号不变）；
  2. 每条登记边的长度平方落在登记的闭区间 ``[min_sq, max_sq]`` 内；
  3. 任意两条不共享端点的边既不相交、也不相切（无任何公共点）。

可行方案按以下字典优先级裁决：

  a. 最大位移平方 ``max_i |d_i|^2`` 最小；
  b. 位移平方和 ``sum_i |d_i|^2`` 最小；
  c. 按点录入顺序的候选序号字典序最小（序号自 1 起，与页面/接口一致）。

点规模 5~8、每点候选 2~3 条，组合数至多 ``3^8 = 6561``，直接完整枚举即可
给出可证明的全局裁决；全部判定使用整数运算，无浮点误差。

无可行方案时，输出"首个破坏约束的证据"：

  * 朝向证据：取一个面，其在 *所有* 组合下都无法保持朝向（若存在），
    按面录入顺序的第一个；否则取枚举过程中最先被破坏的面；
  * 若无朝向破坏，同理给出长度证据 / 边相交证据；
  * 朝向证据优先于长度、长度优先于相交（与面、边、不共享端点边对的
    录入/判定顺序一致，故证据稳定、可复现）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """基准点：录入名称、原始整数坐标。"""

    name: str
    x: int
    y: int


@dataclass(frozen=True)
class Candidate:
    """一条候选整数位移（dx, dy）。"""

    dx: int
    dy: int


@dataclass(frozen=True)
class Triangle:
    """登记三角面：三个点的下标，朝向以原始坐标计算为准。"""

    a: int
    b: int
    c: int


@dataclass(frozen=True)
class Edge:
    """登记边：端点下标与允许的长度平方闭区间。"""

    u: int
    v: int
    min_sq: int
    max_sq: int


@dataclass(frozen=True)
class EdgePair:
    """一对不共享端点的登记边（相交约束的检查对象）。"""

    ei: int
    ej: int


@dataclass(frozen=True)
class Choice:
    """单个点的裁决结果。"""

    point_index: int
    point_name: str
    selected: int                 # 选中的候选序号（0 基）
    candidate: Candidate
    rejected: list[tuple[int, Candidate]]  # (候选序号 0 基, 候选)
    moved_x: int
    moved_y: int


@dataclass(frozen=True)
class EdgeResult:
    """一条边复测后的长度平方证据。"""

    edge_index: int
    u: int
    v: int
    length_sq: int
    min_sq: int
    max_sq: int
    within: bool


@dataclass(frozen=True)
class TriangleResult:
    """一个三角面复测后的有向面积证据（二倍有向面积，带符号）。"""

    triangle_index: int
    a: int
    b: int
    c: int
    signed_double_area: int       # (b-a) x (c-a)，原始朝向
    moved_signed_double_area: int
    preserved: bool


@dataclass(frozen=True)
class Violation:
    """无可行方案时的首违证据。"""

    kind: str                     # "orientation" | "length" | "intersection"
    detail: dict


@dataclass(frozen=True)
class SolveResult:
    feasible: bool
    choices: Optional[list[Choice]]
    edges: Optional[list[EdgeResult]]
    triangles: Optional[list[TriangleResult]]
    moved_points: Optional[list[tuple[int, int]]]
    objective: Optional[dict]
    combinations_checked: int
    violation: Optional[Violation]


class ProblemError(ValueError):
    """录入数据本身非法（无法构成裁决问题）。"""


# ---------------------------------------------------------------------------
# 整数几何原语
# ---------------------------------------------------------------------------


def cross(ax: int, ay: int, bx: int, by: int, cx: int, cy: int) -> int:
    """二倍有向面积 (b-a) x (c-a)；正为逆时针，严格非零才允许。"""

    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _edge_endpoints(e: Edge, moved: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    ux, uy = moved[e.u]
    vx, vy = moved[e.v]
    return ux, uy, vx, vy


def _segments_intersect_or_touch(
    p: tuple[int, int],
    q: tuple[int, int],
    r: tuple[int, int],
    s: tuple[int, int],
) -> bool:
    """闭合线段 pq 与 rs 是否存在任何公共点（相交或相切，含共线重叠/端点相接）。

    标准同侧判别：两线段恰有公共点当且仅当
      cross(p,q,r) 与 cross(p,q,s) 异号或为零，
    且 cross(r,s,p) 与 cross(r,s,q) 异号或为零。
    全整数运算；相切（某叉积为 0 且落在另一线段上）同样判为冲突。
    """

    px, py = p
    qx, qy = q
    rx, ry = r
    sx, sy = s

    d1 = cross(px, py, qx, qy, rx, ry)
    d2 = cross(px, py, qx, qy, sx, sy)
    d3 = cross(rx, ry, sx, sy, px, py)
    d4 = cross(rx, ry, sx, sy, qx, qy)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True

    def on_segment(
        x: int,
        y: int,
        ax: int,
        ay: int,
        bx: int,
        by: int,
    ) -> bool:
        return (
            cross(ax, ay, bx, by, x, y) == 0
            and min(ax, bx) <= x <= max(ax, bx)
            and min(ay, by) <= y <= max(ay, by)
        )

    if d1 == 0 and on_segment(rx, ry, px, py, qx, qy):
        return True
    if d2 == 0 and on_segment(sx, sy, px, py, qx, qy):
        return True
    if d3 == 0 and on_segment(px, py, rx, ry, sx, sy):
        return True
    if d4 == 0 and on_segment(qx, qy, rx, ry, sx, sy):
        return True
    return False


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def _validate(
    points: list[Point],
    candidates: list[list[Candidate]],
    triangles: list[Triangle],
    edges: list[Edge],
) -> list[EdgePair]:
    n = len(points)
    if not 5 <= n <= 8:
        raise ProblemError("基准点数量必须在 5 至 8 个之间")
    if len(candidates) != n:
        raise ProblemError("每个基准点都必须登记候选位移")
    for i, cands in enumerate(candidates):
        if not 2 <= len(cands) <= 3:
            raise ProblemError(f"点 {points[i].name} 必须有 2 至 3 条候选位移")

    def check_vertex(idx: Optional[int], where: str) -> int:
        if not isinstance(idx, int) or not 0 <= idx < n:
            raise ProblemError(f"{where} 引用了不存在的点下标 {idx!r}")
        return idx

    for ti, t in enumerate(triangles):
        check_vertex(t.a, f"三角面 {ti + 1}")
        check_vertex(t.b, f"三角面 {ti + 1}")
        check_vertex(t.c, f"三角面 {ti + 1}")
        if len({t.a, t.b, t.c}) != 3:
            raise ProblemError(f"三角面 {ti + 1} 的三个顶点必须互不相同")
        area = cross(points[t.a].x, points[t.a].y,
                     points[t.b].x, points[t.b].y,
                     points[t.c].x, points[t.c].y)
        if area == 0:
            raise ProblemError(
                f"三角面 {ti + 1}（{points[t.a].name}、{points[t.b].name}、"
                f"{points[t.c].name}）在原基线网中退化为共线，无严格朝向可言"
            )

    for ei, e in enumerate(edges):
        check_vertex(e.u, f"边 {ei + 1}")
        check_vertex(e.v, f"边 {ei + 1}")
        if e.u == e.v:
            raise ProblemError(f"边 {ei + 1} 的两个端点不能相同")
        if e.min_sq > e.max_sq:
            raise ProblemError(f"边 {ei + 1} 的长度区间下界不能大于上界")
        if e.min_sq < 0:
            raise ProblemError(f"边 {ei + 1} 的长度平方不能为负")

    # 不共享端点的边对（按边录入顺序）。
    pairs: list[EdgePair] = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if len({ei.u, ei.v, ej.u, ej.v}) == 4:
                pairs.append(EdgePair(i, j))
    return pairs


# ---------------------------------------------------------------------------
# 裁决
# ---------------------------------------------------------------------------


def solve(
    points: list[Point],
    candidates: list[list[Candidate]],
    triangles: list[Triangle],
    edges: list[Edge],
) -> SolveResult:
    """对录入问题执行完整枚举裁决，返回全局最优方案或稳定的首违证据。"""

    pairs = _validate(points, candidates, triangles, edges)
    n = len(points)

    original_areas = [
        cross(points[t.a].x, points[t.a].y,
              points[t.b].x, points[t.b].y,
              points[t.c].x, points[t.c].y)
        for t in triangles
    ]

    # 枚举中首次出现的各类违例（顺序固定：面 → 边 → 边对），用于无方案时兜底。
    first_orientation: Optional[Violation] = None
    first_length: Optional[Violation] = None
    first_intersection: Optional[Violation] = None

    best_sel: Optional[list[int]] = None
    best_key: Optional[tuple[int, int, tuple[int, ...]]] = None
    combinations = 0

    moved: list[tuple[int, int]] = [(0, 0)] * n
    sel = [0] * n

    def evaluate() -> None:
        nonlocal best_sel, best_key, combinations
        nonlocal first_orientation, first_length, first_intersection

        combinations += 1
        for i in range(n):
            c = candidates[i][sel[i]]
            moved[i] = (points[i].x + c.dx, points[i].y + c.dy)

        # 1) 严格朝向：符号必须与原始有向面积一致（不允许翻折或退化）。
        for ti, t in enumerate(triangles):
            area = cross(moved[t.a][0], moved[t.a][1],
                         moved[t.b][0], moved[t.b][1],
                         moved[t.c][0], moved[t.c][1])
            if (area > 0) != (original_areas[ti] > 0) or area == 0:
                if first_orientation is None:
                    first_orientation = Violation(
                        "orientation",
                        {
                            "triangle_index": ti,
                            "triangle": [t.a, t.b, t.c],
                            "names": [points[t.a].name, points[t.b].name,
                                      points[t.c].name],
                            "original_signed_double_area": original_areas[ti],
                            "actual_signed_double_area": area,
                            "candidate_indices": list(sel),
                        },
                    )
                return

        # 2) 边长平方闭区间。
        length_sq: list[int] = [0] * len(edges)
        for ei, e in enumerate(edges):
            ux, uy, vx, vy = _edge_endpoints(e, moved)
            dsq = (ux - vx) ** 2 + (uy - vy) ** 2
            length_sq[ei] = dsq
            if not e.min_sq <= dsq <= e.max_sq:
                if first_length is None:
                    first_length = Violation(
                        "length",
                        {
                            "edge_index": ei,
                            "endpoints": [e.u, e.v],
                            "names": [points[e.u].name, points[e.v].name],
                            "actual_length_sq": dsq,
                            "min_sq": e.min_sq,
                            "max_sq": e.max_sq,
                            "candidate_indices": list(sel),
                        },
                    )
                return

        # 3) 不共享端点的边不得相交或相切。
        for pair in pairs:
            ei, ej = edges[pair.ei], edges[pair.ej]
            p = moved[ei.u]
            q = moved[ei.v]
            r = moved[ej.u]
            s = moved[ej.v]
            if _segments_intersect_or_touch(p, q, r, s):
                if first_intersection is None:
                    first_intersection = Violation(
                        "intersection",
                        {
                            "edge_i": pair.ei,
                            "edge_j": pair.ej,
                            "edge_i_names": [points[ei.u].name, points[ei.v].name],
                            "edge_j_names": [points[ej.u].name, points[ej.v].name],
                            "candidate_indices": list(sel),
                        },
                    )
                return

        # 可行：按 (最大位移平方, 位移平方和, 候选序号字典序) 比较。
        sq = [
            candidates[i][sel[i]].dx ** 2 + candidates[i][sel[i]].dy ** 2
            for i in range(n)
        ]
        key = (max(sq), sum(sq), tuple(sel))
        if best_key is None or key < best_key:
            best_key = key
            best_sel = list(sel)

    def enumerate_at(i: int) -> None:
        if i == n:
            evaluate()
            return
        for k in range(len(candidates[i])):
            sel[i] = k
            enumerate_at(i + 1)

    enumerate_at(0)

    if best_sel is not None:
        choices: list[Choice] = []
        for i, k in enumerate(best_sel):
            c = candidates[i][k]
            choices.append(
                Choice(
                    point_index=i,
                    point_name=points[i].name,
                    selected=k,
                    candidate=c,
                    rejected=[(j, cc) for j, cc in enumerate(candidates[i]) if j != k],
                    moved_x=points[i].x + c.dx,
                    moved_y=points[i].y + c.dy,
                )
            )

        moved_points = [
            (points[i].x + candidates[i][best_sel[i]].dx,
             points[i].y + candidates[i][best_sel[i]].dy)
            for i in range(n)
        ]

        edge_results: list[EdgeResult] = []
        for ei, e in enumerate(edges):
            ux, uy = moved_points[e.u]
            vx, vy = moved_points[e.v]
            dsq = (ux - vx) ** 2 + (uy - vy) ** 2
            edge_results.append(
                EdgeResult(
                    edge_index=ei, u=e.u, v=e.v,
                    length_sq=dsq, min_sq=e.min_sq, max_sq=e.max_sq,
                    within=e.min_sq <= dsq <= e.max_sq,
                )
            )

        tri_results: list[TriangleResult] = []
        for ti, t in enumerate(triangles):
            area = cross(moved_points[t.a][0], moved_points[t.a][1],
                         moved_points[t.b][0], moved_points[t.b][1],
                         moved_points[t.c][0], moved_points[t.c][1])
            tri_results.append(
                TriangleResult(
                    triangle_index=ti, a=t.a, b=t.b, c=t.c,
                    signed_double_area=original_areas[ti],
                    moved_signed_double_area=area,
                    preserved=(area > 0) == (original_areas[ti] > 0) and area != 0,
                )
            )

        sq = [
            candidates[i][best_sel[i]].dx ** 2 + candidates[i][best_sel[i]].dy ** 2
            for i in range(n)
        ]
        return SolveResult(
            feasible=True,
            choices=choices,
            edges=edge_results,
            triangles=tri_results,
            moved_points=moved_points,
            objective={"max_displacement_sq": max(sq), "sum_displacement_sq": sum(sq)},
            combinations_checked=combinations,
            violation=None,
        )

    # 无可行方案：优先报告"在所有组合中都无法满足"的朝向证据，
    # 保证不是某个组合的局部失败，而是该约束本身被候选集证伪。
    violation = _global_impossibility(
        points, candidates, triangles, edges, pairs, original_areas,
        first_orientation, first_length, first_intersection,
    )
    return SolveResult(
        feasible=False, choices=None, edges=None, triangles=None,
        moved_points=None, objective=None,
        combinations_checked=combinations, violation=violation,
    )


def _global_impossibility(
    points, candidates, triangles, edges, pairs,
    original_areas, first_orientation, first_length, first_intersection,
) -> Violation:
    """构造稳定的"首违证据"。

    步骤一：按录入顺序找一个 *对任意候选组合* 都不能保持原始朝向的面，
    若存在则它是最根本的证据（朝向约束被候选集整体证伪）；
    步骤二：同理找恒越界的边；
    步骤三：返回枚举中按固定顺序最先见到的相交证据；
    最后退回到枚举最先见到的朝向/长度证据。
    """

    n = len(points)

    # 每点可达坐标集合。
    reach = [
        {(p.x + c.dx, p.y + c.dy) for c in candidates[i]}
        for i, p in enumerate(points)
    ]

    for ti, t in enumerate(triangles):
        want_positive = original_areas[ti] > 0
        possible = False
        for pa in reach[t.a]:
            for pb in reach[t.b]:
                for pc in reach[t.c]:
                    area = cross(pa[0], pa[1], pb[0], pb[1], pc[0], pc[1])
                    if area != 0 and ((area > 0) == want_positive):
                        possible = True
                        break
                if possible:
                    break
            if possible:
                break
        if not possible:
            return Violation(
                "orientation",
                {
                    "triangle_index": ti,
                    "triangle": [t.a, t.b, t.c],
                    "names": [points[t.a].name, points[t.b].name,
                              points[t.c].name],
                    "original_signed_double_area": original_areas[ti],
                    "reachable_positions": {
                        points[t.a].name: sorted(reach[t.a]),
                        points[t.b].name: sorted(reach[t.b]),
                        points[t.c].name: sorted(reach[t.c]),
                    },
                    "note": "该三角面在所有候选位移组合下均会翻折或退化",
                },
            )

    for ei, e in enumerate(edges):
        all_out = True
        dmin: Optional[int] = None
        dmax: Optional[int] = None
        for pu in reach[e.u]:
            for pv in reach[e.v]:
                dsq = (pu[0] - pv[0]) ** 2 + (pu[1] - pv[1]) ** 2
                dmin = dsq if dmin is None else min(dmin, dsq)
                dmax = dsq if dmax is None else max(dmax, dsq)
                if e.min_sq <= dsq <= e.max_sq:
                    all_out = False
            if not all_out:
                break
        if all_out:
            return Violation(
                "length",
                {
                    "edge_index": ei,
                    "endpoints": [e.u, e.v],
                    "names": [points[e.u].name, points[e.v].name],
                    "min_sq": e.min_sq,
                    "max_sq": e.max_sq,
                    "reachable_min_length_sq": dmin,
                    "reachable_max_length_sq": dmax,
                    "note": "该边在所有候选位移组合下长度平方都落在闭区间之外",
                },
            )

    # 朝向、长度都存在"某些组合可行"，但全局无解 => 约束相互耦合所致。
    # 按 朝向 → 长度 → 相交 的固定裁决顺序，报告枚举中最先出现的违例组合证据；
    # 枚举顺序确定（按点录入顺序、候选序号递增），故证据稳定可复现。
    if first_orientation is not None:
        return first_orientation
    if first_length is not None:
        return first_length
    if first_intersection is not None:
        return first_intersection
    # 理论上不可达（枚举了全部组合却无任何违例记录）。
    return Violation("intersection", {"detail": "不存在满足全部约束的候选组合"})
