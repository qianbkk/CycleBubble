"""经期周期阶段计算引擎

基于医学文献的周期阶段模型：
- 周期长度 = 相邻两次经期开始的间隔
- 黄体期相对固定（约 14 天），排卵日 = 下次经期前 14 天
- 因此对当前进行中的周期，用历史平均周期长度预测排卵日

阶段划分（以 28 天标准周期为例，排卵日 = 14）：
- 月经期（menstrual）  : 第 1-5 天
- 卵泡期（follicular） : 第 6-12 天
- 排卵期（ovulation）  : 第 13-15 天（排卵日 ± 1 天，3 天窗口）
- 黄体期（luteal）     : 第 16-28 天

说明：需求文档中写「卵泡期 6-13 / 排卵期 14±1 / 黄体期 15-28」存在边界重叠，
此处按「排卵日 ±1 天」定义为 3 天窗口（13-15），卵泡期上移到 12、黄体期从 16 起，
以得到无重叠的可分类阶段划分，符合医学上「排卵窗约 3 天」的常识。

置信度：
- 0 次记录：none    — 无数据，不显示阶段
- 1 次记录：low     — 低置信度，用 28 天默认值
- 2-5 次记录：medium — 中置信度（文档明确 2-3 为中，4-5 仍归为中）
- ≥6 次记录：high   — 高置信度，可判断规律性

文案保持中性、不说教，仅描述所处阶段与常见身体信号。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

# 默认周期长度（天），用于单次记录的低置信度估算
DEFAULT_CYCLE_LENGTH = 28
# 黄体期固定长度（天），医学上相对稳定
LUTEAL_PHASE_LENGTH = 14
# 月经期典型持续天数
MENSTRUAL_LENGTH = 5
# 排卵窗口半宽（排卵日 ± N 天）
OVULATION_HALF_WINDOW = 1
# 周期长度合理医学区间，超出则钳制（避免异常值干扰阶段判定）
MIN_CYCLE_LENGTH = 21
MAX_CYCLE_LENGTH = 35


def to_naive_utc(dt: datetime) -> datetime:
    """统一为 naive UTC，与 models.py 的 utcnow() 风格一致

    aware datetime 会先转到 UTC 再去掉 tzinfo；naive datetime 原样返回。
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _confidence_for_count(n: int) -> str:
    """根据记录条数给出置信度等级"""
    if n <= 0:
        return "none"
    if n == 1:
        return "low"
    if n < 6:
        return "medium"
    return "high"


def compute_cycle_lengths(period_starts: list[datetime]) -> list[int]:
    """根据相邻两次经期开始日期计算周期长度列表（天）。

    返回长度 = len(period_starts) - 1，按时间正序。
    """
    starts = sorted(to_naive_utc(s) for s in period_starts)
    lengths = []
    for i in range(1, len(starts)):
        delta_days = (starts[i] - starts[i - 1]).days
        lengths.append(delta_days)
    return lengths


def _determine_phase(cycle_day: int, cycle_length: int, ovulation_day: int) -> dict:
    """根据周期第几天判定阶段（无重叠划分）。

    边界（以 28 天、ovulation_day=14 为例）：
        月经期  : 1 ~ 5
        卵泡期  : 6 ~ (ov_low - 1)         = 6 ~ 12
        排卵期  : ov_low ~ ov_high         = 13 ~ 15
        黄体期  : (ov_high + 1) ~ cycle    = 16 ~ 28
    """
    ov_low = ovulation_day - OVULATION_HALF_WINDOW
    ov_high = ovulation_day + OVULATION_HALF_WINDOW
    fol_low = MENSTRUAL_LENGTH + 1
    fol_high = ov_low - 1
    lut_low = ov_high + 1

    if cycle_day < 1:
        # 还没到经期开始（理论上不会发生，保险处理）
        return {
            "key": "pre_period",
            "label": "经期前",
            "day_range": "—",
            "copy": "新的周期还没开始。",
        }
    if cycle_day <= MENSTRUAL_LENGTH:
        return {
            "key": "menstrual",
            "label": "月经期",
            "day_range": f"第 1-{MENSTRUAL_LENGTH} 天",
            "copy": "身体在排出内膜，部分人会感觉疲惫或不适。需要的话可以放慢节奏。",
        }
    if fol_low <= cycle_day <= fol_high:
        return {
            "key": "follicular",
            "label": "卵泡期",
            "day_range": f"第 {fol_low}-{fol_high} 天",
            "copy": "雌激素逐渐升高，很多人这段时间精力相对稳定。",
        }
    if ov_low <= cycle_day <= ov_high:
        return {
            "key": "ovulation",
            "label": "排卵期",
            "day_range": f"第 {ov_low}-{ov_high} 天",
            "copy": "排卵日前后约 3 天，是周期中受孕概率较高的窗口。",
        }
    if cycle_day <= cycle_length:
        return {
            "key": "luteal",
            "label": "黄体期",
            "day_range": f"第 {lut_low}-{cycle_length} 天",
            "copy": "孕激素升高，部分人会出现情绪波动或身体胀感，临近经期时更明显。",
        }
    # 超过预测周期长度 — 下次经期可能即将到来或已逾期
    return {
        "key": "late",
        "label": "经期临近/逾期",
        "day_range": f"第 {cycle_length + 1} 天起",
        "copy": "已超过预测的周期长度。如果延迟较多，可以留意身体信号或咨询专业人士。",
    }


def compute_cycle_status(
    period_starts: list[datetime],
    now: Optional[datetime] = None,
) -> dict:
    """计算当前所处的周期阶段 + 置信度。

    参数：
        period_starts: 经期开始日期数组（naive 或 aware 均可，内部统一为 naive UTC）
        now: 参考时刻，默认 utcnow()

    返回 dict：
        has_data: bool — 是否有经期记录
        confidence: "none" / "low" / "medium" / "high"
        phase: None 或 {"key", "label", "day_range", "copy"}
        cycle_day: 当前周期第几天（1-based），无数据时为 None
        cycle_length: 预测/平均周期长度（天），无数据时为 None
        ovulation_day: 预测排卵日（周期第几天）
        days_until_next_period: 距预测下次经期天数（可负，表示已逾期）
        next_period_date: 预测下次经期开始日期（ISO 字符串）
        last_period_start: 最近一次经期开始日期（ISO 字符串）
        record_count: 经期记录数
        cycle_lengths: 历史周期长度列表（天）
        is_regular: 是否规律（仅高置信度时计算，其余为 None）
    """
    now = to_naive_utc(now) if now is not None else datetime.utcnow()
    starts = sorted(to_naive_utc(s) for s in period_starts)
    n = len(starts)

    if n == 0:
        return {
            "has_data": False,
            "confidence": "none",
            "phase": None,
            "cycle_day": None,
            "cycle_length": None,
            "ovulation_day": None,
            "days_until_next_period": None,
            "next_period_date": None,
            "last_period_start": None,
            "record_count": 0,
            "cycle_lengths": [],
            "is_regular": None,
        }

    cycle_lengths = compute_cycle_lengths(starts)
    confidence = _confidence_for_count(n)

    # 平均周期长度（无历史数据时用默认 28 天）
    if not cycle_lengths:
        avg_cycle = DEFAULT_CYCLE_LENGTH
    else:
        avg_cycle = round(sum(cycle_lengths) / len(cycle_lengths))
    # 钳制到合理医学区间，避免异常值干扰阶段判定
    avg_cycle = max(MIN_CYCLE_LENGTH, min(MAX_CYCLE_LENGTH, avg_cycle))

    last_start = starts[-1]
    cycle_day = (now - last_start).days + 1  # day 1 = 经期开始当天

    # 预测排卵日 = 周期长度 - 黄体期长度（即下次经期前 14 天）
    ovulation_day = avg_cycle - LUTEAL_PHASE_LENGTH

    # 预测下次经期
    next_period_date = last_start + timedelta(days=avg_cycle)
    days_until_next_period = (next_period_date - now).days

    # 规律性判断（仅高置信度，且至少有若干历史周期时计算）
    is_regular = None
    if confidence == "high" and len(cycle_lengths) >= 5:
        mean_len = sum(cycle_lengths) / len(cycle_lengths)
        var = sum((x - mean_len) ** 2 for x in cycle_lengths) / len(cycle_lengths)
        std = var ** 0.5
        is_regular = std <= 7  # 标准差 <= 7 天视为相对规律

    phase = _determine_phase(cycle_day, avg_cycle, ovulation_day)

    return {
        "has_data": True,
        "confidence": confidence,
        "phase": phase,
        "cycle_day": cycle_day,
        "cycle_length": avg_cycle,
        "ovulation_day": ovulation_day,
        "days_until_next_period": days_until_next_period,
        "next_period_date": next_period_date.isoformat(),
        "last_period_start": last_start.isoformat(),
        "record_count": n,
        "cycle_lengths": cycle_lengths,
        "is_regular": is_regular,
    }
