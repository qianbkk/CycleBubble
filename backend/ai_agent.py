"""DeepSeek AI Agent — 结构化 Memory 抽取

设计原则（来自产品宪法）：
- LLM 只做抽取，不做评价、不下结论
- event/objects 尽量使用用户原话（证据原则）
- 严禁输出人格标签、心理诊断、确定性结论
"""
import json
import httpx
from typing import Optional
from config import settings


EXTRACTION_PROMPT = """你是 Bubble 的记忆整理者。你的唯一任务是：从用户写下的一段情绪记录中，客观抽取结构化信息。

你只做抽取，不做评价、不下结论、不贴标签。

抽取规则：
1. 只抽取文本中明确出现或强烈暗示的信息，不要推断用户没有表达的内容。
2. event 字段尽量使用用户自己的原话描述具体发生了什么（这是"证据"原则）。
3. themes 从以下受控词表中选择，若无匹配则可新增一个词：认可、工作、家庭、关系、自我、身体、表达
4. triggers（触发因素）从以下选择或新增：评价、比较、冲突、变化、周期、孤独、压力、失去
5. recovery（恢复方式）从以下选择或新增：表达、独处、连接、运动、创作、休息、倾诉
6. emotions 需给出 1-5 的强度（1=轻微, 5=强烈）。情绪名称从以下选择或新增：焦虑、委屈、愤怒、低落、平静、温暖、力量、未明
7. expression_style 只选一个：倾诉、反思、提问、宣泄、行动
8. has_action：用户是否提到了具体行动或打算
9. 严禁输出任何人格标签、心理诊断、确定性结论、建议或安慰语。

输出严格 JSON，不要输出任何其他内容：
{
  "themes": ["..."],
  "event": "用原话描述具体发生了什么",
  "objects": ["..."],
  "triggers": ["..."],
  "recovery": ["..."],
  "emotions": [{"name": "焦虑", "intensity": 3}],
  "expression_style": "反思",
  "has_action": false
}"""


async def extract_memory(text: str) -> dict:
    """调用 DeepSeek 对用户输入做结构化抽取

    返回与前端 extractMemory() 形状一致的 dict。
    如果 API 不可用或出错，回退到基础抽取。
    """
    if not settings.deepseek_api_key:
        # 无 API Key 时回退：基础关键词匹配（和前端原逻辑一致）
        return _fallback_extract(text)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,  # 低温度保证抽取稳定性
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            # 补充 mood（主导情绪 = intensity 最高的）
            mood = "未明"
            if result.get("emotions"):
                sorted_emotions = sorted(
                    result["emotions"],
                    key=lambda e: e.get("intensity", 1),
                    reverse=True,
                )
                mood = sorted_emotions[0]["name"]

            result["mood"] = mood
            result["llm_raw"] = result
            return result

    except Exception as e:
        print(f"[AI Agent] DeepSeek 调用失败，回退到基础抽取: {e}")
        return _fallback_extract(text)


def _fallback_extract(text: str) -> dict:
    """无 API Key 时的基础关键词匹配（和前端 extractMemory 逻辑一致）"""
    themes = []
    triggers = []
    recovery = []
    emotions = []
    mood = "未明"
    expression_style = "倾诉"
    has_action = False

    theme_keywords = {
        "认可": ["认可", "肯定", "表扬", "被看到", "价值", "领导说", "评价"],
        "工作": ["工作", "加班", "同事", "领导", "项目", "会议", "开会", "任务"],
        "家庭": ["妈妈", "爸爸", "家里", "家人", "父母", "回家"],
        "关系": ["朋友", "伴侣", "恋爱", "吵架", "分手", "孤独", "陪伴"],
        "自我": ["我是不是", "我太", "我不够", "自我", "敏感", "脆弱", "坚强"],
        "身体": ["身体", "疲劳", "失眠", "经期", "黄体", "激素", "累"],
        "表达": ["说出来", "表达", "反驳", "不敢说", "没说出口", "想法"],
    }
    trigger_keywords = {
        "评价": ["评价", "批评", "表扬", "领导说", "别人怎么看"],
        "比较": ["比较", "别人都", "为什么别人", "不如"],
        "冲突": ["吵架", "冲突", "争论", "反驳"],
        "变化": ["变化", "突然", "不一样了", "第一次"],
        "周期": ["周期", "经期", "黄体", "又来了", "每次"],
        "压力": ["压力", "deadline", "截止", "太多", "忙"],
    }
    recovery_keywords = {
        "表达": ["说出来", "表达", "写下来", "记录"],
        "独处": ["独处", "一个人", "安静", "空间", "离开"],
        "连接": ["朋友", "聊", "陪伴", "倾诉", "分享"],
        "运动": ["运动", "跑步", "散步", "瑜伽"],
        "创作": ["创作", "画画", "写", "音乐"],
    }
    mood_keywords = {
        "焦虑": ["焦虑", "担心", "怕", "紧张", "不安", "反复想", "纠结"],
        "委屈": ["委屈", "不公平", "凭什么", "为什么我"],
        "愤怒": ["生气", "愤怒", "烦", "气", "讨厌"],
        "低落": ["低落", "难过", "哭", "丧", "没力气", "空"],
        "平静": ["平静", "还好", "释然", "接受", "稳定"],
        "温暖": ["温暖", "感动", "开心", "幸福", "感谢"],
        "力量": ["力量", "勇气", "决定", "终于", "突破"],
    }
    action_keywords = ["决定", "打算", "试试", "下次", "想要", "准备", "开始"]

    for theme, kws in theme_keywords.items():
        if any(kw in text for kw in kws):
            themes.append(theme)
    for trigger, kws in trigger_keywords.items():
        if any(kw in text for kw in kws):
            triggers.append(trigger)
    for rec, kws in recovery_keywords.items():
        if any(kw in text for kw in kws):
            recovery.append(rec)
    for m, kws in mood_keywords.items():
        if any(kw in text for kw in kws):
            emotions.append({"name": m, "intensity": 3})
            if mood == "未明":
                mood = m
    for kw in action_keywords:
        if kw in text:
            has_action = True
            break

    if any(kw in text for kw in ["反思", "是不是", "为什么", "也许", "可能"]):
        expression_style = "反思"
    elif any(kw in text for kw in ["？", "吗", "呢"]):
        expression_style = "提问"

    if not emotions:
        emotions = [{"name": "未明", "intensity": 1}]

    return {
        "themes": themes,
        "event": text[:80],
        "objects": [],
        "triggers": triggers,
        "recovery": recovery,
        "emotions": emotions,
        "expression_style": expression_style,
        "has_action": has_action,
        "mood": mood,
        "llm_raw": None,
    }
