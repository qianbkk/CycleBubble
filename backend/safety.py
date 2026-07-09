"""危机信号检测与援助资源

设计原则（参考 frontend-design 流程的"restraint and self-critique"）：
- **永远不阻断**用户保存记录——这是兜底，不是审查
- 关键词分级：高风险（自伤/自杀意念）一定弹出援助资源；中风险（强烈负面
  情绪持续）给轻提示
- 资源是**静态 + 权威**的，不引向商业 / 政治 / 宗教机构
- 隐私：检测完全在请求体内存中完成，**不写日志、不发外部服务**

检测逻辑：扫描 raw_text 中是否出现关键词（多模式 OR 匹配）。
返回：matched 列表 + risk_level + resources 列表（结构化）。

资源库（仅中国大陆地区，**应用前请根据目标地区替换**）：

| 名称 | 电话 | 时间 |
|---|---|---|
| 北京心理危机研究与干预中心 | 010-82951332 | 24h |
| 全国心理援助热线 | 400-161-9995 | 24h |
| 希望24热线 | 400-161-9995 | 24h |
| 生命热线（上海） | 021-12320-5 | 24h |
| 香港撒瑪利亞防止自殺會 | 2389-2222 | 24h |
| 台湾生命线 | 1995（拨打）/ +886-2585-9595 | 24h |

文字资源（不依赖电话）：
- 简单心理（simplecare.cn）：在线心理咨询
- 壹心理（xinli001.com）：心理学科普 + 自助
- KnowYourself（knowyourself.cc）：心理学知识科普
"""
from typing import List, Dict, Any
import re


# 高风险关键词：自伤 / 自杀 / 死亡意愿 / 具体计划
# 触发时**一定**弹出援助资源 modal
# 每个模式直接做子串匹配（re.escape 防特殊字符），多个词拆成多条避免顺序问题
HIGH_RISK_PATTERNS = [
    # 中文
    r"自杀", r"想死", r"不想活", r"了结自己", r"结束生命",
    r"自我了断", r"轻生", r"自残", r"伤害自己", r"割腕",
    r"跳楼", r"安眠药", r"农药",
    r"活着没意思", r"活够了",
    # 英文（拆词避免顺序问题）
    r"suicide", r"suicidal",
    r"kill myself", r"killing myself",
    r"end my life", r"ending my life",
    r"self harm", r"self-harm", r"selfharm", r"self cut", r"self-cut", r"selfcut",
    r"cut myself", r"cutting myself",
    r"take my life", r"taking my life",
    r"don't want to live", r"don't want to be alive",
    r"want to die",
    r"jump off", r"jump from",
]

# 中风险关键词：强烈情绪 + 持续性描述
# 触发时**只**在保存响应里标记，不弹 modal（让产品其他文案做柔性提示）
MEDIUM_RISK_PATTERNS = [
    r"活不下去", r"熬不下去", r"撑不住", r"没意思",
    r"想消失", r"想逃跑", r"彻底崩溃", r"扛不住",
    r"受不了了", r"没人理解", r"没人要",
    r"hopeless", r"can't go on", r"give up",
]


# 结构化资源（与前端约定：含 type 字段以决定渲染样式）
RESOURCES = [
    {"name": "全国心理援助热线",        "phone": "400-161-9995", "hours": "24h", "type": "phone"},
    {"name": "北京心理危机研究与干预中心", "phone": "010-82951332",  "hours": "24h", "type": "phone"},
    {"name": "希望24热线",             "phone": "400-161-9995", "hours": "24h", "type": "phone"},
    {"name": "生命热线（上海）",         "phone": "021-12320-5",  "hours": "24h", "type": "phone"},
    {"name": "简单心理",   "url": "https://www.simplecare.cn",    "type": "online"},
    {"name": "壹心理",     "url": "https://www.xinli001.com",     "type": "online"},
    {"name": "KnowYourself", "url": "https://www.knowyourself.cc", "type": "online"},
]

# 编译为正则（IGNORECASE + UNICODE + 子串匹配）
_HIGH_RE = [re.compile(re.escape(p), re.IGNORECASE | re.UNICODE) for p in HIGH_RISK_PATTERNS]
_MED_RE  = [re.compile(re.escape(p), re.IGNORECASE | re.UNICODE) for p in MEDIUM_RISK_PATTERNS]


def scan_crisis(text: str) -> Dict[str, Any]:
    """扫描文本中的危机信号。

    返回结构：
    {
        "risk_level": "none" | "medium" | "high",
        "matched":    [命中的关键词...],
        "resources":  [...]   # 高/中风险时返回援助资源；none 时为空列表
    }
    永远返回 dict，从不抛异常。
    """
    if not text or not isinstance(text, str):
        return {"risk_level": "none", "matched": [], "resources": []}

    high_matched = sorted({p for r in _HIGH_RE for p in r.findall(text)})
    med_matched  = sorted({p for r in _MED_RE  for p in r.findall(text)})

    if high_matched:
        return {
            "risk_level": "high",
            "matched": high_matched,
            "resources": RESOURCES,
        }
    if med_matched:
        return {
            "risk_level": "medium",
            "matched": med_matched,
            "resources": RESOURCES,
        }
    return {"risk_level": "none", "matched": [], "resources": []}


# 保留原 dev0709 接口名 `scan` 作为别名，方便旧调用
def scan(text: str) -> Dict[str, Any]:
    """dev0709 旧接口名的别名，转发到 scan_crisis。"""
    return scan_crisis(text)