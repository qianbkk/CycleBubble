# CycleBubble 真实账号体验 + AI 接入 + 管理员后台 实现计划

## 目标

按 v2 规格 `docs/superpowers/specs/2026-07-11-ai-admin-design.md` 完成：Part A 修复 5 条产品断层、Part B 接入 MiniMax/DeepSeek AI、Part C 新增管理员后台。所有改动保留现有 Bubble 视觉与演示/真实双数据库隔离。

## 阶段 1：Part A 五条产品断层修复

### 1.1 回应前端接线

- `api.js`：扩展 `resonance.respond` 文档，确认使用中文类型。
- `script.js`：`bindResponseChips()` 把 `data-response` 映射到后端中文枚举（`empathy → 我也经历过`、`thanks → 谢谢`、`hug → 抱抱`、`share → 分享我的经历`、`continue → 继续说`）；调用 `CB_API.resonance.respond(memory_id, type)`，成功后刷新该卡片状态。
- 演示模式仍然使用本地 `bubbleDNA.relationshipSignals` 兜底，不调用后端。

### 1.2 公开/私密开关默认私密

- `index.html`：保存记录弹窗增加"允许匿名出现在共鸣流"复选框 + 文案说明，默认 `unchecked`。
- `script.js`：第一次公开时显示一次性提示（localStorage `cb_public_ack`）。
- `api.js.memory.create`：增加 `isPublic` 参数。
- `script.js.persistMemoryToBackend`：把开关状态透传。
- 真实账号：写入 `is_public`；演示模式：仍然仅写 localStorage。

### 1.3 成长页数据源切换

- `script.js.loadAndApplyGrowthData`：优先用后端 `discoveries/timeline`，本地 `renderGrowthPage` 作为兜底（仅当后端数据为空且本地 memories 非空时启用）。
- 移除前端重复的"成长故事"算法（保留 `generateGrowthStories` 函数但标记为 deprecated，注释说明）。

### 1.4 举报前端入口

- `api.js`：新增 `reports.create(memoryId, reason, note?)`。
- `script.js`：共鸣卡片底部加"举报"按钮，点击展开举报原因下拉 + 提交。
- `index.html`：共鸣卡片模板增加举报按钮位置。

### 1.5 关键词一致化

- `script.js`：删除 `extractMemory`、`themeKeywords`、`triggerKeywords`、`recoveryKeywords`、`emotionKeywords`、相关注释。
- 保留 `backend/routers/memory.py` 的关键词后备逻辑作为 AI 失败时的 fallback。

## 阶段 2：Part B AI 接入

### 2.1 配置与 settings

- `backend/config.py`：新增 `ai_default_provider: str = "minimax"`，`ai_default_model_minimax: str = "M3"`，`ai_default_model_deepseek: str = "v4-flash"`，`ai_request_timeout_seconds: int = 8`。
- 新增 `backend/models.py`：`AdminSetting` 表（`key`, `value`, `updated_at`, `updated_by`）。
- 新增 `backend/services/admin_settings.py`：
  - `get_setting(key) -> Optional[str]`：DB 优先 → env 兜底；启动时把 env 值写入 DB 一次。
  - `set_setting(key, value, updated_by)`：写入 DB，返回是否变更。
  - `init_settings_from_env()`：启动钩子。
- `backend/main.py` 启动钩子：调用 `init_settings_from_env()`，创建 `AdminSetting` 表。

### 2.2 AI Extractor

- 新增 `backend/services/ai_extractor.py`：
  - `class AIUnavailable(Exception)`。
  - `async extract_memory(raw_text: str) -> dict`：返回 `{themes, triggers, recovery, emotions, mood, is_sensitive}`。
  - 内部按 `AdminSetting.default_provider` 选供应商；请求体构造使用 httpx 8s 超时。
  - MiniMax/DeepSeek endpoint 通过 Provider 配置支持：仅在第一期接入 MiniMax（默认）；DeepSeek 留 provider 类结构但实际请求返回 `AIUnavailable`（不在第一期做联调）。
  - prompt：要求 JSON 输出，限定 schema，禁止字段名漂移。
  - 失败、超时、payload 不合法都抛 `AIUnavailable`。

### 2.3 接入记忆保存

- `backend/routers/memory.py` 的 `POST /api/memories`：
  1. 先调 `safety.check(raw_text)` → 命中则置 `risk_level="high"` 并返回触发援助 modal。
  2. 读取两个开关：`enable_third_party_ai`、`enable_keyword_fallback`。
  3. 决策：
     - `enable_third_party_ai=False` → 关键词后备
     - `enable_third_party_ai=True` + AI 成功 → 用 AI 结果
     - `enable_third_party_ai=True` + AI 失败 + `enable_keyword_fallback=True` → 关键词后备
     - `enable_third_party_ai=True` + AI 失败 + `enable_keyword_fallback=False` → 返回 `503`
  4. safety 始终执行，不受开关影响。
- 写入 `is_sensitive` 到 DB（来自 AI 输出）。

### 2.4 `is_sensitive` 优先级

- `backend/routers/resonance.py` 的 `/feed`：
  ```python
  .where(Memory.is_public == True,
         Memory.is_sensitive == False,
         Memory.user_id != current_user.id)
  ```

### 2.5 隐私披露

- `index.html` "关于" 弹层增加说明段落。
- 首页底部首次提示（一次性，localStorage 标记 `cb_ai_ack`）。

## 阶段 3：Part C 管理员后台

### 3.1 配置

- `backend/config.py`：新增 `admin_username: str = "admin"`，`admin_password: str`（≥ 16 字符，启动时校验），`admin_jwt_secret: Optional[str]`（默认派生 `jwt_secret + "::admin"`），`admin_jwt_expire_hours: int = 4`，`admin_login_lock_minutes: int = 15`，`admin_login_max_fails: int = 5`。

### 3.2 数据模型

- `AdminLoginAttempt(id, username, ip, success, timestamp)` —— 纯事件表
- `AdminAudit(id, admin_username, action, target, ip, ua, reason, timestamp)`
- `AdminMemoryAccessToken(id, admin_username, memory_id, reason, expires_at, used_at)`
- 创建：`backend/models.py` 增加表，启动钩子创建。

### 3.3 鉴权

- `backend/auth.py`：
  - `create_admin_token(username) -> str`：使用 `admin_jwt_secret` 签名；JWT header `kid="admin"`，payload `aud="admin"`。
  - `require_admin`：解析 header 校验 `kid`、`aud`、`exp`、签名。

### 3.4 路由

- 新增 `backend/routers/admin.py`：
  - `POST /admin/login {username, password}` → `{token, expires_at}`；锁定 15 分钟；登录成功与失败都写 `AdminLoginAttempt`。
  - `GET /admin/stats`：聚合统计。
  - `GET /admin/reports?status=open&page=` / `GET /admin/reports/{id}` / `POST /admin/reports/{id}/dismiss` / `POST /admin/reports/{id}/action`。
  - `GET /admin/ai/settings` / `PUT /admin/ai/settings` / `POST /admin/ai/test`。
  - `GET /admin/audit?from=&to=`。
  - `POST /admin/users/{id}/disable`。
  - `POST /admin/memory-access-tokens {memory_id, reason}` → `{access_token, expires_at}`。
  - `GET /admin/memories/{memory_id}?access_token=...`：三因素校验后返回原文，使用即写 `used_at`，访问记录写 `AdminAudit`。

### 3.5 限速与日志

- IP 限速 10/min：内存字典（开发期）。
- 操作日志：双写到 `logs/admin.log` 与 `AdminAudit`。

### 3.6 前端 `admin.html`

- 独立页面，样式沿用 Bubble 视觉。
- 登录表单 → token → 加载数据。
- 数据视图：用户列表、记忆/经期（通过举报）、统计。
- AI 配置：默认供应商切换、模型切换、两个开关、Key 覆盖、测试连接按钮。
- 审计日志查看。

### 3.7 风格保持

- 复用现有 CSS 变量、字体、轻量边框；登录卡片与现有登录页视觉一致。
- 顶部 logo "CycleBubble Admin"，底部不引入新设计系统。

## 阶段 4：测试与验证

### 单元 / 集成

- pytest 覆盖：
  - AI 提取正常、超时、Key 缺失、payload 不合法
  - 两个开关的优先级分支
  - `safety.py` 命中时 AI 失败也能弹援助
  - admin 登录失败 5 次锁定
  - admin token 用普通 token 替换被拒
  - `AdminSetting` 覆盖 env 生效
  - 一次性访问令牌三因素
  - `is_sensitive=true` 屏蔽
  - `/api/resonance/respond` 中文类型
  - `/admin/reports/{id}/action` 级联

### 浏览器

- 真实账号：回应、公开开关、举报、成长页使用后端数据、关于弹层披露。
- 管理员：登录、查看举报、调整 AI 配置、测试连接、审计日志、一次性访问。
- 演示模式：保持只读、不调用第三方 AI。

### 安全网

- `safety.py` 本地同步路径延迟目标 < 50ms（CI 相对断言）。
- AI 调用即便整体失败，safety.py 命中仍触发援助 modal。

## 提交与 PR

- 每阶段独立提交；Part A 完成后立即提交 + PR。
- Part B 完成后单独提交 + PR。
- Part C 完成后单独提交 + PR。

## 影响范围汇总

### 新增

- `admin.html`
- `backend/routers/admin.py`
- `backend/services/ai_extractor.py`
- `backend/services/admin_settings.py`

### 修改

- `index.html`、`script.js`、`api.js`、`styles.css`
- `backend/main.py`、`backend/auth.py`、`backend/config.py`、`backend/models.py`
- `backend/routers/memory.py`、`backend/routers/resonance.py`、`backend/routers/growth.py`、`backend/routers/reports.py`
- `backend/services/safety.py`（仅明确调用顺序）