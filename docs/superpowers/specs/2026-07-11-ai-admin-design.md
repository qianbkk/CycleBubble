# CycleBubble 真实账号体验 + AI 接入 + 管理员后台 设计 v2

## 目标

把当前"演示模式看着挺好、真实用户走不通"的体验补全，接入 MiniMax/DeepSeek 双供应商的 AI 记忆分析能力，并以专用 `/admin/*` 后台承载配置与运营需求。同时把"危机检测 / 密钥管理 / 隐私披露 / 管理员权限范围 / JWT 密钥隔离 / 登录锁定 / 一次性访问令牌"等安全约束明确化。

## 范围

### Part A：五条产品断层修复（与原方案一致）

1. **回应前端接线**：`script.js` 的 `bindResponseChips()` 改为调用 `CB_API.resonance.respond`，使用后端要求的中文类型（`我也经历过 / 谢谢 / 抱抱 / 继续说 / 分享我的经历`）。
2. **公开/私密选项默认私密**：保存记录弹窗增加"允许匿名出现在共鸣流"开关，**默认不勾选**；UI 文案写明「公开后原文会被同样经历相似感受的人看到」；首次公开时给一次性提示（localStorage 标记）。
3. **成长页数据源切换**：`loadAndApplyGrowthData()` 优先使用后端 `discoveries/timeline`，保留本地 `renderGrowthPage` 兜底；不再并行维护两套逻辑。
4. **举报前端入口**：共鸣卡片底部加"举报"按钮，调用 `CB_API.reports.create`，带原因下拉（spam / harassment / self_harm_concern / other）。
5. **关键词一致化**：删除 `script.js` 的 `extractMemory` 与 `themeKeywords` 等；关键词仅作为后端 AI 失败时的降级路径，保留 `memory.py` 的关键词后备。

### Part B：AI 接入

#### B.1 供应商与模型

- 供应商：`minimax`、`deepseek`
- 默认：`minimax`
- 模型映射：
  - `minimax`：`M3`（默认）、`M2.7`
  - `deepseek`：`v4-flash`（默认）、`pro`

#### B.2 Key 管理：DB 覆盖 + env 兜底

- 读取顺序：`AdminSetting` 表覆盖值 → 环境变量 `CB_MINIMAX_KEY` / `CB_DEEPSEEK_KEY` → 报错"未配置 AI"。
- **不**写回环境变量。容器/只读 env 部署安全。
- 启动时若 `AdminSetting` 表无当前供应商的 Key 记录，把 env 值写入一次（DB 是动态源，env 是默认种子）。
- Key 长度 ≥ 16 字符，PUT `/admin/ai/settings` 时校验。

#### B.3 危机检测路径完全独立（最关键）

- `backend/services/safety.py` 仍是危机检测第一道闸门。约束：**纯本地同步、无外部依赖、优先级最高**。
- AI 提取路径**完全不再做危机判断**，仅输出 `themes / triggers / recovery / emotions / mood / is_sensitive`，不返回 `risk_level`。
- 保存记忆流程：`safety.py` 同步命中 → 立即弹援助 modal，不等 AI；AI 仅做情绪结构化分析，失败/超时降级到关键词；`is_sensitive` 用于把记忆标记为不进入共鸣 feed。
- **AI 降级开关不影响 safety.py**——无论 ON 还是 OFF，安全网始终开启。
- 验收指标：safety.py 检测路径本地响应 < 50ms（在 CI 上断言）。

#### B.4 `is_sensitive` 优先级（写死）

- **`is_sensitive=true` 时，无论 `is_public` 如何，都不进入共鸣 feed。**
- 实现位置：`backend/routers/resonance.py` 的 `/feed` 查询必须在 WHERE 子句附加 `is_sensitive == false`。

#### B.5 AI 服务接口

- 新增 `backend/services/ai_extractor.py`，暴露 `extract_memory(raw_text) -> dict`：
  - 输入：用户原始文本
  - 输出：`{themes: List[str], triggers: List[str], recovery: List[str], emotions: List[{name,intensity}], mood: str, is_sensitive: bool}`
  - 失败时抛 `AIUnavailable`，由调用方决定降级或返回错误
- 超时：单次 8s；超时降级。
- 失败原因记录到 `logs/ai.log`（不写入数据库）。

### Part C：管理员后台（`/admin`）

#### C.1 页面与样式

- 独立 `admin.html`，样式沿用现有 Bubble 视觉：白底、手机框、薰衣草/浅粉强调色、轻量边框。
- 路由：`admin.html` 通过 nginx 与 `api.js` 协同访问 `/admin/*`。

#### C.2 后端：路由组 `/admin/*`

`backend/routers/admin.py`：

- `POST /admin/login {username, password}` → `{token, expires_at}`
- `GET /admin/stats` 聚合统计：用户数 / 记忆数 / 经期数 / 活跃度（不含个体关联）
- `GET /admin/reports?status=open&page=` 待处理举报列表
- `GET /admin/reports/{id}` 单条举报详情（被举报记忆原文、作者、回应数）
- `POST /admin/reports/{id}/dismiss` 关闭举报
- `POST /admin/reports/{id}/action` 处理举报（含删除记忆等）
- `GET /admin/ai/settings` 当前 AI 配置
- `PUT /admin/ai/settings` 更新默认供应商、模型、降级开关、Key 覆盖
- `POST /admin/ai/test` 测试当前 AI 配置连通性，返回 `{ok, latency_ms, model, provider, error?}`
- `GET /admin/audit?from=&to=` 审计日志（仅过去 90 天）
- `POST /admin/users/{id}/disable` 禁用用户

#### C.3 鉴权：独立签名密钥 + aud + kid

- **JWT header** 使用 `kid="admin"` 标识管理员签名密钥。
- **JWT payload** 包含 `aud="admin"`、`exp`、`iat`、`sub=username`。
- 签名密钥：`CB_ADMIN_JWT_SECRET`（≥ 16 字符）。若未配置，dev 模式派生为 `CB_JWT_SECRET + "::admin"`，生产部署强制要求独立密钥。
- Token 有效期：4 小时。
- `require_admin` 依赖校验：解析 header + 验证 `kid`、`aud`、`exp`、签名。

#### C.4 登录失败锁定（写死）

- `AdminLoginAttempt` 表字段：`username`, `ip`, `success`, `timestamp`, `fail_count_window`
- 5 次失败 → 账号锁定 15 分钟（响应 `429`，含 `Retry-After`）；锁定期间密码正确也拒绝。
- 锁定判定：同 `username + IP` 在 15 分钟内失败次数 ≥ 5。
- IP 限速：10/min 保留作为额外保护（防单 IP 暴力扫描）。

#### C.5 记忆 / 经期原文：管理员不可常规浏览（写死）

- **常规后台不暴露** `GET /admin/memories?user_id=` 与 `GET /admin/cycles?user_id=`。
- 改为：管理员只能通过举报（`/admin/reports/{id}`）查看原文。
- **高危一次性访问**：管理员显式提供访问理由（≥ 10 字）→ 服务端生成一次性 token → 表 `AdminMemoryAccessToken` 字段：
  ```
  id (uuid), admin_username, memory_id, reason, expires_at, used_at (nullable)
  ```
  → 通过 `GET /admin/memories/{memory_id}?access_token=...` 访问 → 响应成功即写入 `used_at`，**不可重用**。
  → `expires_at` 默认 10 分钟；过期或 `used_at` 非空均返回 `410 Gone`。

#### C.6 操作日志

- 所有 admin 操作双写到 `logs/admin.log` 与 `AdminAudit` 表：
  - `admin_username`, `action`, `target`, `ip`, `ua`, `timestamp`, `reason?`
- `GET /admin/audit` 仅返回过去 90 天记录。

### Part D：隐私披露（写死）

- "关于" 弹层增加说明：「Bubble 使用 AI 辅助理解你的情绪记录（默认供应商：MiniMax）。你的原始文本会被发送给该供应商用于分析；管理员可调整供应商或关闭 AI。」
- 首页底部首次提示（一次性，localStorage 标记）。
- 隐私披露明确：管理员可关闭「上传到第三方 AI」开关；关闭后仅走关键词/规则降级，与"AI 降级开关不影响 safety.py"一致——也就是说即便关掉第三方 AI，safety.py 仍然工作。
- README/隐私说明文档同步更新。

### Part E：错误处理与不变量

- 管理员 token 永不复用普通用户 token；普通 token 访问 `/admin/*` 永远返回 `403`。
- `AdminSetting.Key` 值在 PUT 时仅回显掩码（`xxxx****xxxx`）。
- 真实/演示双库不变：所有 admin 操作作用于真实库；演示库管理员接口仅做只读 stats（`/admin/demo-stats`），便于核对 demo seed 健康。
- safety.py 命中关键词时不依赖 AI 即可触发援助 modal；演示模式援助 modal 行为不变。

## 验证

### 单元 / 集成（pytest）

- AI 提取正常、超时、Key 缺失、payload 不合法都走通；超时降级到关键词。
- safety.py 命中关键词时即便 AI 失败仍触发援助 modal。
- admin 登录失败 5 次触发锁定；锁定期间即使正确密码也拒绝。
- admin token 用普通 token 替换会被拒；`kid` 错误会被拒。
- `AdminSetting` 覆盖 env 值生效；启动时若 DB 无值，把 env 写入 DB 一次。
- 一次性访问令牌：未使用可访问，使用后 `used_at` 写入；过期返回 `410`。
- `is_sensitive=true` 的记忆无论 `is_public` 是否为真，都不出现在 `/api/resonance/feed`。
- `/api/resonance/respond` 类型字符串匹配后端 `VALID_RESPONSE_TYPES`；演示模式 403。
- `/admin/reports/{id}/action` 删除关联记忆，级联删除其响应与该记忆上的举报。
- 真实库演示隔离：所有 admin 操作不写演示库。

### 浏览器

- 真实账号：回应按钮调用后端；保存时公开/私密开关默认私密；公开时一次性提示；举报按钮可用；成长页使用后端 discoveries/timeline。
- 管理员：登录、查看举报、调整 AI 配置（默认供应商/模型/降级开关/Key 覆盖）、测试连接（返回延迟/状态）、查看审计。
- 关于弹层披露 AI 服务商与关闭方式。

### 安全网验收

- `safety.py` 命中关键词时延迟 < 50ms（CI 断言）。
- AI 调用即便整体失败，safety.py 命中仍触发援助 modal（集成测试覆盖）。

## 风险与权衡

- **AI 服务不可用时降级**：默认 ON，管理员可关；关闭后保存记录直接返回 `503`（管理员选择承担）。
- **管理员可访问举报记忆原文**：受限于举报处理需要，作为最低必要权限；非举报内容不可浏览。
- **AI 调用时间**：8s 超时；可在后台调整（默认固定 8s）。
- **容器只读 env**：通过 DB 覆盖解决；启动时把 env 写入 DB 一次即可。

## 数据模型

新增 SQLite 表：

- `AdminSetting(key, value, updated_at, updated_by)`
- `AdminLoginAttempt(id, username, ip, success, timestamp)`
- `AdminAudit(id, admin_username, action, target, ip, ua, reason, timestamp)`
- `AdminMemoryAccessToken(id, admin_username, memory_id, reason, expires_at, used_at)`

## 影响范围

### 前端

- `index.html`、`admin.html`（新）、`script.js`、`api.js`、`styles.css`

### 后端

- 新增：`backend/routers/admin.py`、`backend/services/ai_extractor.py`、`backend/services/admin_settings.py`
- 修改：`backend/auth.py`、`backend/config.py`、`backend/main.py`、`backend/models.py`、`backend/routers/memory.py`、`backend/routers/resonance.py`、`backend/routers/growth.py`、`backend/routers/reports.py`、`backend/services/safety.py`（仅明确调用顺序）

### 文档

- 本规格文档：`docs/superpowers/specs/2026-07-11-ai-admin-design.md`
- 实现计划：`docs/superpowers/plans/2026-07-11-ai-admin-plan.md`（下一步）