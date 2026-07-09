# CycleBubble

> 一个持续理解你的情绪空间。

CycleBubble 是一款帮助女性**理解周期与情绪关系**的产品。它通过长期记录用户的情绪表达，逐渐形成对该用户的理解（Emotional DNA），帮助用户看见"这种情绪可能从哪里来"。

## 🎯 核心理念

- **Settling, not Growing**：沉淀而非成长。Bubble 是随时间沉积出独特结构的生命体。
- **观察，不定义**：AI 永远只说"我注意到了"，不说"你是怎样的人"。
- **连接，不传播**：共鸣是"有人和我有相似经历"的温暖，不是"有多少人点赞"。

## 🏗️ 架构

```
CycleBubble/
├── index.html          # 前端主入口（视觉）
├── styles.css          # 前端样式
├── script.js           # 前端逻辑
├── backend/            # FastAPI 后端
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py       # 数据模型
│   ├── auth.py         # JWT 认证
│   ├── cycle_engine.py # 周期计算
│   └── routers/        # API 路由
│       ├── auth.py
│       ├── cycle.py
│       ├── memory.py
│       ├── resonance.py
│       └── growth.py
├── requirements.txt    # Python 依赖
├── dev.bat             # Windows 启动脚本
└── dev.ps1             # PowerShell 启动脚本
```

## 🚀 启动方式

### Windows（推荐）

双击运行 `dev.bat` 或在 PowerShell 中：
```powershell
.\dev.ps1
```

脚本会自动：
1. 创建 Python 虚拟环境（首次）
2. 安装依赖
3. 启动后端服务

服务启动后：
- API 地址：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`（Swagger UI）

### 手动启动

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate (Windows)

# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn backend.main:app --reload
```

### 前端

直接用浏览器打开 `index.html`，或者用本地 HTTP 服务器：
```bash
python -m http.server 8080
# 然后访问 http://localhost:8080
```

## 📡 API 端点

### 认证
- `POST /api/auth/register` — 注册
- `POST /api/auth/login` — 登录
- `GET /api/auth/me` — 获取当前用户

### 周期
- `POST /api/cycle/periods` — 手动添加一次经期
- `POST /api/cycle/import/manyou` — 导入美柚格式
- `POST /api/cycle/import/apple-health` — 导入 Apple Health 格式
- `GET /api/cycle/periods` — 获取所有经期记录
- `GET /api/cycle/status` — 获取当前周期状态

### 记忆
- `POST /api/memories` — 创建一条情绪记录
- `GET /api/memories` — 获取用户所有记忆

### 共鸣
- `GET /api/resonance/feed` — 获取公开故事流
- `POST /api/resonance/{id}/respond` — 对一条故事发送回应

### 成长
- `GET /api/growth` — 获取成长页数据

## 📊 数据模型

- **User**：用户（邮箱 + 密码哈希 + JWT）
- **Cycle**：经期记录（开始日期、结束日期、流量、来源）
- **Memory**：情绪记录（原文 + LLM 抽取的 themes/triggers/recovery/emotions）
- **Response**：共鸣回应（对某条公开记忆的回应）

## 📚 文献支撑

本产品的设计理念基于 16 篇精选学术文献，详见 `cyclebubble_literature/` 目录。

核心依据：
- 60万周期数据分析（npj Digital Medicine 2019）
- 数字心理健康 App 设计（JMIR Mental Health 2016/2020）
- 经期追踪 HCI 研究（CHI 2017）
- 隐私与女性健康（JMIR mHealth 2022）

## 🛠️ 技术栈

- **前端**：原生 HTML/CSS/JavaScript（无框架），保持轻量
- **后端**：FastAPI + SQLModel + SQLite
- **认证**：JWT (HS256)
- **数据库**：SQLite（本地文件 `cyclebubble.db`）

## ⚙️ 环境变量

后端支持以下环境变量（前缀 `CB_`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CB_DATABASE_URL` | `sqlite:///./cyclebubble.db` | 数据库连接字符串 |
| `CB_JWT_SECRET` | `dev-secret-change-me-in-production` | JWT 签名密钥 |
| `CB_JWT_EXPIRE_HOURS` | `168` | Token 有效期（小时） |
| `CB_CORS_ORIGINS` | `["*"]` | 允许的跨域来源（JSON 列表） |

## 📝 开发说明

- 数据库文件 `cyclebubble.db` 会在首次启动时自动创建
- 当前实现使用本地关键词抽取作为 LLM 的兜底
- 视觉风格严格保留早期 demo 的"流动泡泡"美学

## 📜 许可

仅供学习和个人使用。