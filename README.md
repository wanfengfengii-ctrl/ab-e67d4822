# 玻璃穹顶裂纹监测 · 位移联合裁决

历史建筑玻璃穹顶布设裂纹监测点后，每个基准点复测时存在 2~3 条**候选整数位移**。
本服务从每个点的候选中**恰好联合选定一条**，使复测基线网仍是可解释的变形依据：
不让某点局部位移看似最小，却导致三角网翻折或缆线（边）交叉。

工程师在页面录入 5~8 个基准点、已登记三角面与边、每点候选位移、每条边允许的
长度平方闭区间，修改草稿后提交裁决，并查看：

- 每点**采用 / 未采用**的候选位移与位移平方；
- 每条边复测后的**实际长度平方**与闭区间判定；
- 每个三角面复测前后的**二倍有向面积**（符号即严格朝向证据）；
- 原基线网 / 复测网双图，无解时以红色画出违例证据组合或候选可达位置。

## 裁决语义（服务端，全部整数精确运算）

每个点从其候选位移中**恰选一条**，并同时满足：

1. **严格朝向**：每个登记三角面复测后的有向面积符号必须与原基线网一致，
   翻折（符号反向）与退化（面积为 0）均不允许；
2. **边长闭区间**：每条登记边的复测长度平方必须落在登记的 `[min_sq, max_sq]`
   闭区间内（端点取等号合法）；
3. **边不相交/不相切**：任意两条**不共享端点**的边不得有任何公共点
   （规范相交、T 形相接、端点接触、共线重叠全部判为冲突）；共享端点的边合法。

可行方案按字典优先级裁决（前者相同才比较后者）：

1. 最大位移平方 `max_i (dx_i² + dy_i²)` 最小；
2. 位移平方和 `Σ(dx_i² + dy_i²)` 最小；
3. 按**点录入顺序**的候选序号字典序最小（候选序号自 1 起）。

点规模 5~8、每点 2~3 候选，组合数至多 3⁸ = 6561，服务端完整枚举，因此裁决结果
是可证明的全局最优，而非局部贪心。

### 无方案时的"首个破坏约束证据"（确定性、可复现）

无可行方案时，服务端与页面**不会给出局部可用的伪结论**，而是按固定规则给出证据：

- 先按面录入顺序找一个在**全部候选组合下**都无法保持朝向的三角面
  （附三个顶点的全部可达坐标作为证伪证据）；
- 否则按边录入顺序找一条在全部候选组合下长度平方都落在闭区间外的边
  （附可达长度平方最小值/最大值）；
- 否则说明各约束单独都存在可行组合、但不存在共同满足的组合，此时按
  **朝向 → 长度 → 相交**的固定裁决顺序，给出枚举顺序（点序 × 候选序号递增）下
  最先出现违例的组合，并列出该组合每点选用的候选序号；
- 证据完全由录入数据决定，重复请求结果逐字节一致（有测试覆盖）。

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000
```

## Docker 与 Docker Compose

```bash
docker compose up --build          # 启动裁决服务（含 /healthz 健康检查）
HOST_PORT=9000 docker compose up   # 自定义宿主机端口（容器内固定 8000）
```

宿主机端口通过环境变量 `HOST_PORT`（默认 8000）配置，也可复制
`.env.example` 为 `.env` 后修改。

### 一次性 verify 服务

`docker compose.yaml` 中的 `verify` 服务通过
`depends_on: condition: service_healthy` **等待 web 健康检查通过后**才启动，
顺序执行：

1. 代码测试（pytest）；
2. 构建检查（字节码编译 + 应用装配）；
3. 裁决 API 冒烟（健康检查、页面、可行裁决、无方案朝向证据、非法草稿 400）。

```bash
docker compose build
docker compose run --rm verify     # 全部通过退出码 0，任一失败退出码非 0
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查，返回 `{"status":"ok"}` |
| GET | `/` | 录入与裁决单页 |
| GET | `/api/sample` | 内置示例草稿（原位置组合故意越界，须联合选定） |
| POST | `/api/solve` | 提交草稿并裁决 |

请求体：

```json
{
  "points":     [{"name": "P0", "x": 0, "y": 0}],
  "candidates": [[{"dx": 0, "dy": 0}, {"dx": 1, "dy": 0}]],
  "triangles":  [{"a": 0, "b": 1, "c": 2}],
  "edges":      [{"u": 0, "v": 1, "min_sq": 9, "max_sq": 25}]
}
```

`triangles` / `edges` 中的下标为点录入下标（自 0 起）。

成功响应含 `feasible: true`、`objective`、逐点 `choices`（含 `rejected`
未采用候选）、`edges`、`triangles`、`moved_points` 与 `combinations_checked`；
无解时含 `feasible: false` 与 `violation`（`kind` ∈
`orientation` / `length` / `intersection`，附 `detail` 与可读 `message`）；
录入草稿本身非法（点数越界、候选数越界、原始面共线、区间倒置等）返回
`400 {"error":"invalid_problem", ...}`。

## 测试

```bash
.venv/bin/python -m pytest tests/ -q
```

覆盖：整数叉积与线段相交/相切的全部边界情形、每点恰选一条、完整枚举计数、
三级目标序（含独立穷举 oracle 复核）、闭区间取等、翻折/退化、非共端点边相切、
共享端点合法、证据稳定性，以及 API 健康检查/页面/可行/无方案/400。

## 目录结构

```
app/
  solver.py          # 整数几何原语、校验、完整枚举裁决、首违证据
  schemas.py         # 请求/响应模型、序列化、内置示例
  main.py            # FastAPI 路由
  static/index.html  # 录入与证据展示单页（草稿本地持久化、双网 Canvas）
scripts/
  entrypoint.sh      # serve / verify 入口
  smoke.py           # 仅标准库的裁决 API 冒烟
tests/               # pytest 测试
Dockerfile
docker-compose.yaml  # web（健康检查）+ 一次性 verify（service_healthy 门控）
```
