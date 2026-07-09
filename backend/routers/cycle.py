from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..database import get_session
from ..models import Cycle, User
from ..auth import get_current_user
from ..cycle_engine import compute_cycle_status

router = APIRouter()

class PeriodCreate(BaseModel):
    start_date: date
    end_date: Optional[date] = None
    flow: Optional[str] = None  # 'light' | 'medium' | 'heavy'
    source: str = "manual"

class ManyouImport(BaseModel):
    periods: List[dict]  # [{"start_date": "2025-12-15", "end_date": "2025-12-20"}, ...]

class AppleHealthImport(BaseModel):
    records: List[dict]  # 标准化格式

class CycleStatusResponse(BaseModel):
    phase: str
    phase_name: str
    description: str
    day_in_cycle: Optional[int]
    days_until_next_period: Optional[int]
    next_period_date: Optional[str]
    confidence: str
    cycle_lengths: List[int]
    is_regular: Optional[bool]

@router.post("/periods")
def create_period(
    req: PeriodCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """添加一次经期记录"""
    cycle = Cycle(
        user_id=current_user.id,
        start_date=req.start_date,
        end_date=req.end_date,
        flow=req.flow,
        source=req.source,
        created_at=datetime.utcnow()
    )
    session.add(cycle)
    session.commit()
    session.refresh(cycle)
    return {
        "id": cycle.id,
        "start_date": cycle.start_date.isoformat(),
        "end_date": cycle.end_date.isoformat() if cycle.end_date else None,
        "flow": cycle.flow,
        "source": cycle.source
    }

@router.post("/import/manyou")
def import_manyou(
    req: ManyouImport,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """导入美柚格式的经期数据"""
    imported = []
    for p in req.periods:
        start = p.get("start_date") or p.get("start")
        end = p.get("end_date") or p.get("end")
        if not start:
            continue
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end) if end else None
        except ValueError:
            continue

        cycle = Cycle(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            flow=p.get("flow"),
            source="manyou",
            created_at=datetime.utcnow()
        )
        session.add(cycle)
        imported.append(cycle)

    session.commit()
    return {"imported_count": len(imported)}

@router.post("/import/apple-health")
def import_apple_health(
    req: AppleHealthImport,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """导入 Apple Health 格式的经期数据"""
    imported = []
    for r in req.records:
        start = r.get("startDate") or r.get("start_date")
        end = r.get("endDate") or r.get("end_date")
        if not start:
            continue
        try:
            start_date = date.fromisoformat(start[:10])
            end_date = date.fromisoformat(end[:10]) if end else None
        except (ValueError, TypeError):
            continue

        cycle = Cycle(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            flow=r.get("flow"),
            source="apple_health",
            created_at=datetime.utcnow()
        )
        session.add(cycle)
        imported.append(cycle)

    session.commit()
    return {"imported_count": len(imported)}

@router.get("/periods")
def list_periods(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取所有经期记录"""
    cycles = session.exec(
        select(Cycle).where(Cycle.user_id == current_user.id).order_by(Cycle.start_date.desc())
    ).all()
    return {
        "periods": [
            {
                "id": c.id,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "flow": c.flow,
                "source": c.source
            }
            for c in cycles
        ]
    }

@router.get("/status", response_model=CycleStatusResponse)
def get_cycle_status(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取当前周期状态"""
    cycles = session.exec(
        select(Cycle).where(Cycle.user_id == current_user.id).order_by(Cycle.start_date)
    ).all()
    return compute_cycle_status(cycles)