"""经期周期路由 — 添加经期 / 获取状态 / 获取记录

端点：
- POST /api/cycle/periods  — 添加一次经期开始日期（可选结束日期）
- GET  /api/cycle/status   — 获取当前周期阶段 + 置信度
- GET  /api/cycle/periods  — 获取所有经期记录（按开始日期正序）

datetime 统一使用 naive UTC（与 models.py 一致）。
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from database import get_session
from models import User, Cycle
from auth import get_current_user
from cycle_engine import compute_cycle_status, to_naive_utc

router = APIRouter(prefix="/api/cycle", tags=["cycle"])


class AddPeriodRequest(BaseModel):
    period_start: datetime  # 经期开始日期（ISO 8601）
    period_end: datetime | None = None  # 经期结束日期（可选）


def cycle_to_dict(c: Cycle) -> dict:
    """Cycle 对象转前端兼容的 dict"""
    return {
        "id": c.id,
        "period_start": c.period_start.isoformat(),
        "period_end": c.period_end.isoformat() if c.period_end else None,
        "cycle_length": c.cycle_length,
        "created_at": c.created_at.isoformat(),
    }


@router.post("/periods")
def add_period(
    req: AddPeriodRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """添加一次经期开始日期

    - 同一天不允许重复录入（按 UTC 日期判断）
    - 新增后会回填「上一次经期」所在记录的 cycle_length（本次开始 - 上次开始的天数）
    """
    start = to_naive_utc(req.period_start)
    end = to_naive_utc(req.period_end) if req.period_end else None

    if end is not None and end < start:
        raise HTTPException(status_code=400, detail="经期结束日期不能早于开始日期")

    # 同一天去重
    existing = session.exec(
        select(Cycle).where(Cycle.user_id == user.id)
    ).all()
    for e in existing:
        if to_naive_utc(e.period_start).date() == start.date():
            raise HTTPException(status_code=400, detail="该日期已有经期记录")

    cycle = Cycle(
        user_id=user.id,
        period_start=start,
        period_end=end,
    )
    session.add(cycle)
    session.flush()  # 拿到 id

    # 回填周期长度（cycle_length = 相邻两次开始的间隔，归属于「较早开始」的那条记录）
    # 1) 若存在更早的经期，则该更早记录的周期长度 = 本次开始 - 更早开始
    prev = session.exec(
        select(Cycle)
        .where(Cycle.user_id == user.id)
        .where(Cycle.id != cycle.id)
        .where(Cycle.period_start < start)
        .order_by(Cycle.period_start.desc())
    ).first()
    if prev is not None:
        prev_start = to_naive_utc(prev.period_start)
        prev.cycle_length = (start - prev_start).days
        session.add(prev)

    # 2) 若存在更晚的经期，则本次（新插入）记录的周期长度 = 更晚开始 - 本次开始
    nxt = session.exec(
        select(Cycle)
        .where(Cycle.user_id == user.id)
        .where(Cycle.id != cycle.id)
        .where(Cycle.period_start > start)
        .order_by(Cycle.period_start.asc())
    ).first()
    if nxt is not None:
        nxt_start = to_naive_utc(nxt.period_start)
        cycle.cycle_length = (nxt_start - start).days

    session.commit()
    session.refresh(cycle)

    return {"cycle": cycle_to_dict(cycle)}


@router.get("/periods")
def list_periods(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """获取所有经期记录（按开始日期正序）"""
    cycles = session.exec(
        select(Cycle)
        .where(Cycle.user_id == user.id)
        .order_by(Cycle.period_start.asc())
    ).all()

    return {
        "periods": [cycle_to_dict(c) for c in cycles],
        "total": len(cycles),
    }


@router.get("/status")
def get_status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """获取当前周期阶段 + 置信度

    新用户无数据时返回 has_data=False、phase=None，不假设任何阶段。
    """
    cycles = session.exec(
        select(Cycle)
        .where(Cycle.user_id == user.id)
        .order_by(Cycle.period_start.asc())
    ).all()
    period_starts = [to_naive_utc(c.period_start) for c in cycles]

    return compute_cycle_status(period_starts)
