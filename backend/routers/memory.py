from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select
from ..database import get_session
from ..models import Memory, User
from ..auth import get_current_user
from ..safety import scan_crisis

router = APIRouter()


def _is_demo_mode(request: Request) -> bool:
    """判断请求是否来自演示模式（前端 X-Demo-Mode: 1 header）"""
    return request.headers.get("X-Demo-Mode", "").strip() == "1"


def _demo_mode_block():
    """演示模式下写入操作的拒绝响应"""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="演示模式只读，无法保存数据。请登录后使用完整功能。",
    )


class MemoryCreate(BaseModel):
    raw_text: str
    is_public: bool = False
    themes: List[str] = []
    triggers: List[str] = []
    recovery: List[str] = []
    emotions: List[dict] = []  # [{"name": "焦虑", "intensity": 3}]
    mood: str = ""


class MemoryResponse(BaseModel):
    id: int
    raw_text: str
    themes: List[str]
    triggers: List[str]
    recovery: List[str]
    emotions: List[dict]
    mood: str
    is_public: bool
    is_sensitive: bool
    created_at: str


import json


def parse_json_list(s: str, default=None):
    """安全解析 JSON 列表"""
    if default is None:
        default = []
    if not s:
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


# 关键词后备：仅在 AI 不可用时使用
KEYWORD_BACKFILL = {
    "themes": {
        "工作": ["工作", "老板", "同事", "上班", "开会", "项目", "领导", "加班", "绩效"],
        "家庭": ["家", "父母", "妈妈", "爸爸", "孩子", "家人"],
        "关系": ["朋友", "恋人", "对象", "分手", "吵架", "伴侣"],
        "自我": ["自己", "我", "价值", "意义", "敏感", "认可"],
        "身体": ["累", "疼", "病", "睡", "周期", "生理期", "黄体"]
    },
    "triggers": {
        "评价": ["说", "评价", "批评", "表扬", "认可", "指责"],
        "比较": ["比", "比较", "别人", "不如"],
        "冲突": ["吵架", "冲突", "矛盾"],
        "变化": ["变化", "改变", "突然"],
        "压力": ["压力", "紧张", "焦虑"]
    },
    "recovery": {
        "独处": ["一个人", "独处", "安静"],
        "运动": ["运动", "跑步", "散步", "瑜伽"],
        "倾诉": ["说", "聊", "朋友", "倾诉"],
        "创作": ["写", "画", "创作", "听音乐"],
        "休息": ["睡", "休息", "放松"]
    },
}

MOOD_KEYWORDS = {
    "焦虑": ["焦虑", "担心", "紧张", "不安", "反复想"],
    "难过": ["难过", "伤心", "哭", "失落", "沮丧", "委屈"],
    "开心": ["开心", "高兴", "快乐", "愉快", "满足"],
    "平静": ["平静", "宁静", "放松", "安心", "释然"],
    "愤怒": ["生气", "愤怒", "恼火", "烦", "讨厌"],
    "低落": ["低落", "丧", "空虚", "没力气"],
    "力量": ["力量", "勇气", "决定", "终于", "突破"]
}


def _keyword_backfill(text: str) -> dict:
    """用关键词提取主题/触发/恢复/情绪，作为 AI 失败时的兜底。"""
    t = (text or "").lower()
    themes, triggers, recovery = [], [], []
    for cat, words in KEYWORD_BACKFILL["themes"].items():
        if any(w in t for w in words):
            themes.append(cat)
    for cat, words in KEYWORD_BACKFILL["triggers"].items():
        if any(w in t for w in words):
            triggers.append(cat)
    for cat, words in KEYWORD_BACKFILL["recovery"].items():
        if any(w in t for w in words):
            recovery.append(cat)
    mood = ""
    for m, words in MOOD_KEYWORDS.items():
        if any(w in t for w in words):
            mood = m
            break
    if not mood:
        mood = "平静"
    return {
        "themes": themes,
        "triggers": triggers,
        "recovery": recovery,
        "emotions": [],
        "mood": mood,
        "is_sensitive": False,
    }


async def _extract_or_fallback(raw_text: str) -> dict:
    """AI 优先；不可用或禁用时按开关决定降级或抛错。"""
    from ..services.ai_extractor import AIUnavailable, extract_memory
    from ..services.admin_settings import (
        KEY_ENABLE_THIRD_PARTY,
        KEY_ENABLE_KEYWORD_FALLBACK,
        get_setting,
    )

    if get_setting(KEY_ENABLE_THIRD_PARTY, "true") != "true":
        # 完全关闭第三方 AI，仅走关键词
        return _keyword_backfill(raw_text)

    try:
        return await extract_memory(raw_text)
    except AIUnavailable as e:
        logger_msg = f"AI extract failed: {e}"
        try:
            from ..services.ai_extractor import logger as _ai_logger
            _ai_logger.warning(logger_msg)
        except Exception:
            pass
        if get_setting(KEY_ENABLE_KEYWORD_FALLBACK, "true") == "true":
            return _keyword_backfill(raw_text)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 服务暂不可用，且未启用关键词降级",
        )


@router.post("", response_model=MemoryResponse)
async def create_memory(
    req: MemoryCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """创建一条情绪记录

    流程：
    1. safety.py 同步危机检测（始终执行，不受 AI 开关影响）
    2. AI 提取（如可用）/ 关键词后备
    3. 写入数据库
    """
    if _is_demo_mode(request):
        _demo_mode_block()
    if not req.raw_text or len(req.raw_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="记录内容不能为空")

    # safety 始终执行（最高优先级，纯本地同步）
    crisis = scan_crisis(req.raw_text)

    # 客户端如果直接传了结构化字段且非空，优先使用（兼容未来客户端自定义）
    use_client_fields = bool(req.themes or req.triggers or req.recovery or req.emotions or req.mood)

    if use_client_fields:
        extracted = {
            "themes": list(req.themes or []),
            "triggers": list(req.triggers or []),
            "recovery": list(req.recovery or []),
            "emotions": list(req.emotions or []),
            "mood": req.mood or "平静",
            "is_sensitive": False,
        }
    else:
        extracted = await _extract_or_fallback(req.raw_text)

    # 如果 safety 命中高/中风险，把 is_sensitive 强制设为 true
    if crisis.get("risk_level") in ("high", "medium"):
        extracted["is_sensitive"] = True

    memory = Memory(
        user_id=current_user.id,
        raw_text=req.raw_text,
        themes=json.dumps(extracted["themes"], ensure_ascii=False),
        triggers=json.dumps(extracted["triggers"], ensure_ascii=False),
        recovery=json.dumps(extracted["recovery"], ensure_ascii=False),
        emotions=json.dumps(extracted["emotions"], ensure_ascii=False),
        mood=extracted["mood"] or "平静",
        is_public=req.is_public,
        is_sensitive=bool(extracted.get("is_sensitive", False)),
        created_at=datetime.utcnow(),
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)

    return {
        "id": memory.id,
        "raw_text": memory.raw_text,
        "themes": parse_json_list(memory.themes),
        "triggers": parse_json_list(memory.triggers),
        "recovery": parse_json_list(memory.recovery),
        "emotions": parse_json_list(memory.emotions),
        "mood": memory.mood,
        "is_public": memory.is_public,
        "is_sensitive": memory.is_sensitive,
        "created_at": memory.created_at.isoformat(),
        "crisis": crisis,
    }


@router.get("")
def list_memories(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0
):
    """获取用户所有记忆"""
    memories = session.exec(
        select(Memory)
        .where(Memory.user_id == current_user.id)
        .order_by(Memory.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "memories": [
            {
                "id": m.id,
                "raw_text": m.raw_text,
                "themes": parse_json_list(m.themes),
                "triggers": parse_json_list(m.triggers),
                "recovery": parse_json_list(m.recovery),
                "emotions": parse_json_list(m.emotions),
                "mood": m.mood,
                "is_public": m.is_public,
                "is_sensitive": m.is_sensitive,
                "created_at": m.created_at.isoformat()
            }
            for m in memories
        ],
        "total": len(memories)
    }