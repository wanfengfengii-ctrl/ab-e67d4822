#!/usr/bin/env python3
"""裁决 API 冒烟脚本（仅用标准库），由一次性 verify 服务调用。

前置：web 服务已通过 compose 的 service_healthy 健康门控；本脚本仍自带
短暂重试。任一步骤失败即以非零退出码终止，供 ``docker compose`` 上报。

环境变量：
  BASE_URL  被测服务地址，默认 http://web:8000（compose 网络内）
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://web:8000").rstrip("/")


def call(path: str, payload=None, timeout: int = 10):
    headers = {}
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def must(cond: bool, msg: str) -> None:
    if not cond:
        print(f"SMOKE FAIL: {msg}", file=sys.stderr)
        sys.exit(1)


def wait_healthy(deadline_s: float = 60.0) -> None:
    deadline = time.time() + deadline_s
    last = None
    while time.time() < deadline:
        try:
            status, body = call("/healthz", timeout=3)
            if status == 200 and body.get("status") == "ok":
                print(f"[ok] GET /healthz -> {body}")
                return
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1)
    print(f"SMOKE FAIL: 服务在 {deadline_s:.0f}s 内未通过健康检查: {last}",
          file=sys.stderr)
    sys.exit(1)


def main() -> None:
    print(f"冒烟目标: {BASE}")
    wait_healthy()

    # 页面可打开。
    with urllib.request.urlopen(BASE + "/", timeout=5) as resp:
        html = resp.read().decode("utf-8")
        must(resp.status == 200 and "位移联合裁决" in html, "首页未正常返回")
        print("[ok] GET / -> 裁决页面")

    # 示例问题必须裁决可行（含"每点恰选一条、边在区间、面保持朝向"）。
    status, sample = call("/api/sample")
    must(status == 200 and len(sample["points"]) == 5, "示例草稿读取失败")
    print("[ok] GET /api/sample -> 内置示例")

    status, result = call("/api/solve", sample)
    must(status == 200, "可行示例返回非 200")
    must(result.get("feasible") is True, "内置示例被错误判为无解")
    must(all(e["within"] for e in result["edges"]), "裁决方案存在越界边")
    must(all(t["preserved"] for t in result["triangles"]), "裁决方案存在朝向翻转面")
    must(len(result["choices"]) == len(sample["points"]), "逐点选择数量不符")
    must(all(
        len(ch["rejected"]) == len(sample["candidates"][ch["point_index"]]) - 1
        for ch in result["choices"]
    ), "未采用候选未完整列出")
    print(f"[ok] POST /api/solve 可行：目标 {result['objective']}，"
          f"枚举 {result['combinations_checked']} 种组合")

    # 无方案问题：必须稳定给出朝向首违证据，而不是伪结论。
    infeasible = {
        "points": sample["points"],
        "candidates": [
            *sample["candidates"][:2],
            [{"dx": 0, "dy": -4}, {"dx": 1, "dy": -3}],
            *sample["candidates"][3:],
        ],
        "triangles": sample["triangles"],
        "edges": sample["edges"],
    }
    status, result = call("/api/solve", infeasible)
    must(status == 200, "无解问题返回非 200")
    must(result.get("feasible") is False, "应判无解却返回了方案")
    v = result.get("violation") or {}
    must(v.get("kind") == "orientation", "首个证据应当是朝向破坏")
    must(bool(v.get("message")), "证据缺少可读说明")
    print(f"[ok] POST /api/solve 无解证据：{v['kind']} —— {v['message']}")

    # 非法草稿（三角面重复顶点）：400 稳定错误。
    bad = json.loads(json.dumps(sample))
    bad["triangles"] = [{"a": 0, "b": 1, "c": 1}]
    try:
        call("/api/solve", bad)
        must(False, "非法草稿（退化面/重复顶点）应被拒绝")
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        must(exc.code == 400 and body.get("error") == "invalid_problem",
             f"非法草稿响应异常: {exc.code} {body}")
        print(f"[ok] 非法草稿稳定拒绝：400 {body['message'][:40]}…")

    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
