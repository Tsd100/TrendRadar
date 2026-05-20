# coding=utf-8
"""
报告辅助函数模块

提供报告生成相关的通用辅助函数
"""

import re
from typing import List, Optional


def calc_duration(first_time: str, last_time: str) -> str:
    """计算在榜时长，返回人性化显示

    Args:
        first_time: 首次上榜时间 (HH:MM 或 HH-MM 格式)
        last_time: 最后在榜时间

    Returns:
        时长描述如 "2h30m"、"45m"、"新上榜"，空字符串表示数据不足
    """
    if not first_time or not last_time:
        return ""
    try:
        ft = first_time.replace("-", ":")
        lt = last_time.replace("-", ":")
        fh, fm = map(int, ft.split(":"))
        lh, lm = map(int, lt.split(":"))
        duration_minutes = (lh * 60 + lm) - (fh * 60 + fm)
        if duration_minutes <= 0:
            return "新上榜"
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        if hours > 0 and mins > 0:
            return f"⏱{hours}h{mins}m"
        elif hours > 0:
            return f"⏱{hours}h"
        else:
            return f"⏱{mins}m"
    except (ValueError, TypeError):
        return ""


def calc_trend_label(ranks: List[int], rank_timeline: Optional[List[dict]] = None) -> str:
    """计算趋势标签

    Args:
        ranks: 排名历史列表
        rank_timeline: 排名时间线（可选，用于更精确判断）

    Returns:
        趋势标签如 "急升🔥"、"上升🔺"、"平稳➖"、"下降🔻"
    """
    if not ranks or len(ranks) < 2:
        return ""
    # 排除脱榜(0)后取有效排名
    valid = [r for r in ranks if r > 0]
    if len(valid) < 2:
        return ""
    # 最近两次有效排名
    prev, curr = valid[-2], valid[-1]
    diff = curr - prev  # 正数=排名数值变大=下降，负数=上升
    magnitude = abs(diff)

    if diff < 0:
        if magnitude >= 5:
            return "急升🔥"
        return "上升🔺"
    elif diff > 0:
        if magnitude >= 5:
            return "骤降📉"
        return "下降🔻"
    else:
        return "平稳➖"


def clean_title(title: str) -> str:
    """清理标题中的特殊字符

    清理规则：
    - 将换行符(\n, \r)替换为空格
    - 将多个连续空白字符合并为单个空格
    - 去除首尾空白

    Args:
        title: 原始标题字符串

    Returns:
        清理后的标题字符串
    """
    if not isinstance(title, str):
        title = str(title)
    cleaned_title = title.replace("\n", " ").replace("\r", " ")
    cleaned_title = re.sub(r"\s+", " ", cleaned_title)
    cleaned_title = cleaned_title.strip()
    return cleaned_title


def html_escape(text: str) -> str:
    """HTML特殊字符转义

    转义规则（按顺序）：
    - & → &amp;
    - < → &lt;
    - > → &gt;
    - " → &quot;
    - ' → &#x27;

    Args:
        text: 原始文本

    Returns:
        转义后的文本
    """
    if not isinstance(text, str):
        text = str(text)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def format_rank_display(ranks: List[int], rank_threshold: int, format_type: str) -> str:
    """格式化排名显示

    根据不同平台类型生成对应格式的排名字符串。
    当最小排名小于等于阈值时，使用高亮格式。

    Args:
        ranks: 排名列表（可能包含重复值）
        rank_threshold: 高亮阈值，小于等于此值的排名会高亮显示
        format_type: 平台类型，支持:
            - "html": HTML格式
            - "feishu": 飞书格式
            - "dingtalk": 钉钉格式
            - "wework": 企业微信格式
            - "telegram": Telegram格式
            - "slack": Slack格式
            - 其他: 默认markdown格式

    Returns:
        格式化后的排名字符串，如 "[1]" 或 "[1 - 5]"
        如果排名列表为空，返回空字符串
    """
    if not ranks:
        return ""

    unique_ranks = sorted(set(ranks))
    min_rank = unique_ranks[0]
    max_rank = unique_ranks[-1]

    # 根据平台类型选择高亮格式
    if format_type == "html":
        highlight_start = "<font color='red'><strong>"
        highlight_end = "</strong></font>"
    elif format_type == "feishu":
        highlight_start = "<font color='red'>**"
        highlight_end = "**</font>"
    elif format_type == "dingtalk":
        highlight_start = "**"
        highlight_end = "**"
    elif format_type == "wework":
        highlight_start = "**"
        highlight_end = "**"
    elif format_type == "telegram":
        highlight_start = "<b>"
        highlight_end = "</b>"
    elif format_type == "slack":
        highlight_start = "*"
        highlight_end = "*"
    else:
        # 默认 markdown 格式
        highlight_start = "**"
        highlight_end = "**"

    # 生成排名显示
    rank_str = ""
    if min_rank <= rank_threshold:
        if min_rank == max_rank:
            rank_str = f"{highlight_start}[{min_rank}]{highlight_end}"
        else:
            rank_str = f"{highlight_start}[{min_rank} - {max_rank}]{highlight_end}"
    else:
        if min_rank == max_rank:
            rank_str = f"[{min_rank}]"
        else:
            rank_str = f"[{min_rank} - {max_rank}]"

    # 计算热度趋势
    trend_arrow = ""
    if len(ranks) >= 2:
        prev_rank = ranks[-2]
        curr_rank = ranks[-1]
        if curr_rank < prev_rank:
            trend_arrow = "🔺"  # 排名上升（数值变小）
        elif curr_rank > prev_rank:
            trend_arrow = "🔻"  # 排名下降（数值变大）
        else:
            trend_arrow = "➖"  # 排名持平
    # len(ranks) == 1 时不显示趋势箭头（新上榜由 is_new 字段在 formatter.py 中处理）

    return f"{rank_str} {trend_arrow}" if trend_arrow else rank_str
