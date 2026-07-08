"""Pattern 聚合 + Bubble 状态计算

和前端 computePatterns() / computeBubbleState() 逻辑对齐。
后端从数据库聚合 Memory，计算出 Pattern 和 Bubble 视觉状态。
"""
from collections import Counter
from typing import Optional


# 情绪 → hue 映射（和前端 moodColorMap 一致）
MOOD_HUE_MAP = {
    "焦虑": {"hue": 265, "sat": 0.15},
    "委屈": {"hue": 340, "sat": 0.14},
    "愤怒": {"hue": 10, "sat": 0.18},
    "低落": {"hue": 220, "sat": 0.08},
    "平静": {"hue": 180, "sat": 0.06},
    "温暖": {"hue": 35, "sat": 0.14},
    "力量": {"hue": 50, "sat": 0.16},
    "未明": {"hue": 275, "sat": 0.08},
}


def compute_patterns(memories: list) -> dict:
    """从 Memory 列表聚合 Pattern（等价前端 computePatterns）"""
    theme_counter = Counter()
    trigger_counter = Counter()
    recovery_counter = Counter()
    expression_counter = Counter()

    for m in memories:
        for t in (m.themes or []):
            theme_counter[t] += 1
        for t in (m.triggers or []):
            trigger_counter[t] += 1
        for r in (m.recovery or []):
            recovery_counter[r] += 1
        if m.expression_style:
            expression_counter[m.expression_style] += 1

    # 近期情绪（最近 3 条）
    recent = memories[-3:] if len(memories) >= 3 else memories
    recent_moods = [m.mood or "未明" for m in recent]
    mood_counter = Counter(recent_moods)
    recent_mood = mood_counter.most_common(1)[0][0] if recent_moods else "未明"

    return {
        "themes": dict(theme_counter),
        "triggers": dict(trigger_counter),
        "recovery": dict(recovery_counter),
        "expressions": dict(expression_counter),
        "theme_count": len(theme_counter),
        "recovery_count": len(recovery_counter),
        "total_memories": len(memories),
        "recent_mood": recent_mood,
    }


def compute_bubble_state(patterns: dict) -> dict:
    """从 Pattern 计算 Bubble 视觉状态（等价前端 computeBubbleState）"""
    total = patterns["total_memories"]
    richness = patterns["theme_count"] + patterns["recovery_count"]

    mood_info = MOOD_HUE_MAP.get(patterns["recent_mood"], MOOD_HUE_MAP["未明"])

    return {
        "liquid_layers": min(total, 8),
        "particle_density": min(richness * 2, 16),
        "mood_hue": mood_info["hue"],
        "mood_sat": mood_info["sat"],
        "breathe_duration": 5.0 - min(total * 0.1, 1.5),  # 连续性越高，呼吸越稳
        "opacity": min(0.4 + total * 0.05, 0.85),
        "texture_layers": min(total // 2, 5),
    }
