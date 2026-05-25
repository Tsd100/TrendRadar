# coding=utf-8
"""
变化对比模块

检测本次报告与上次报告之间的变化：
- 新增 🆕：本次新出现的条目
- 上升 🔺：排名显著上升（≥3 位）
- 下降 🔻：排名显著下降（≥3 位）
- 消失 💨：上次在榜但本次不在榜的条目
"""

from typing import Dict, List, Optional, Tuple


def _best_rank(ranks: List[int]) -> int:
    """获取最佳排名（最小值），排除 0"""
    valid = [r for r in ranks if r > 0]
    return min(valid) if valid else 999


def _rank_change(ranks: List[int]) -> Tuple[int, int]:
    """计算排名变化幅度和方向

    Returns:
        (magnitude, direction): magnitude >= 0; direction: -1=上升, 0=不变, 1=下降
    """
    valid = [r for r in ranks if r > 0]
    if len(valid) < 2:
        return 0, 0
    prev, curr = valid[-2], valid[-1]
    diff = curr - prev
    magnitude = abs(diff)
    if diff < 0:
        return magnitude, -1
    elif diff > 0:
        return magnitude, 1
    return 0, 0


def detect_changes_from_stats(
    stats: List[Dict],
    new_titles: Optional[List[Dict]] = None,
    rise_threshold: int = 3,
    fall_threshold: int = 3,
) -> Dict[str, List[Dict]]:
    """从报告统计数据中检测变化

    Args:
        stats: 报告统计列表
        new_titles: 新增标题列表（可选）
        rise_threshold: 排名上升阈值（变化量 ≥ 此值才算上升）
        fall_threshold: 排名下降阈值（变化量 ≥ 此值才算下降）

    Returns:
        变化分类字典:
        {
            "new": [...],       # 新增条目
            "rising": [...],    # 上升条目
            "falling": [...],   # 下降条目
            "disappeared": [...] # 消失条目（需外部提供）
        }
    """
    new_items = []
    rising_items = []
    falling_items = []

    # 从 stats 中提取所有有变化趋势的条目
    for stat in stats:
        keyword = stat.get("word", "")
        for title_data in stat.get("titles", []):
            ranks = title_data.get("ranks", [])
            is_new = title_data.get("is_new", False)
            count = title_data.get("count", 1)

            item = {
                "title": title_data.get("title", ""),
                "source_name": title_data.get("source_name", ""),
                "url": title_data.get("url", ""),
                "mobile_url": title_data.get("mobile_url", ""),
                "ranks": ranks,
                "count": count,
                "matched_keyword": keyword,
                "is_new": is_new,
            }

            # 有历史排名数据时，优先检测变化趋势
            if count > 1:
                magnitude, direction = _rank_change(ranks)
                if direction == -1 and magnitude >= rise_threshold:
                    item["change_magnitude"] = magnitude
                    rising_items.append(item)
                    continue
                elif direction == 1 and magnitude >= fall_threshold:
                    item["change_magnitude"] = magnitude
                    falling_items.append(item)
                    continue

            if is_new or count <= 1:
                new_items.append(item)

    # 排序：上升按变化幅度降序，下降按变化幅度降序
    rising_items.sort(key=lambda x: x["change_magnitude"], reverse=True)
    falling_items.sort(key=lambda x: x["change_magnitude"], reverse=True)

    return {
        "new": new_items,
        "rising": rising_items,
        "falling": falling_items,
        "disappeared": [],  # 需要外部提供
    }


def format_changes_card(
    changes: Dict[str, List[Dict]],
    format_type: str,
    max_per_category: int = 5,
) -> str:
    """将变化对比数据格式化为各平台的消息卡片

    Args:
        changes: detect_changes_from_stats 的返回值
        format_type: 目标平台类型
        max_per_category: 每个类别最多显示条数

    Returns:
        格式化后的变化卡片字符串
    """
    # 检查是否有任何变化
    has_content = any(
        len(changes.get(cat, [])) > 0
        for cat in ["new", "rising", "falling", "disappeared"]
    )
    if not has_content:
        return ""

    lines = []

    # 卡片标题
    if format_type == "feishu":
        lines.append("📊 **变化对比**\n")
    elif format_type == "dingtalk":
        lines.append("📊 **变化对比**\n")
    elif format_type == "telegram":
        lines.append("📊 <b>变化对比</b>\n")
    elif format_type == "slack":
        lines.append("📊 *变化对比*\n")
    elif format_type == "html":
        lines.append('<div class="changes-card"><h3>📊 变化对比</h3>')
    else:
        lines.append("📊 **变化对比**\n")

    # 各分类
    categories = [
        ("new", "🆕 新增", "new"),
        ("rising", "🔺 排名上升", "rising"),
        ("falling", "🔻 排名下降", "falling"),
        ("disappeared", "💨 已消失", "disappeared"),
    ]

    for cat_key, cat_label, css_class in categories:
        items = changes.get(cat_key, [])[:max_per_category]
        if not items:
            continue

        if format_type == "html":
            lines.append(f'<div class="changes-group {css_class}">')
            lines.append(f"<h4>{cat_label} ({len(items)})</h4><ul>")
        elif format_type == "feishu":
            lines.append(f"\n**{cat_label}** ({len(items)}):\n")
        elif format_type == "telegram":
            lines.append(f"\n<b>{cat_label}</b> ({len(items)}):\n")
        elif format_type == "slack":
            lines.append(f"\n*{cat_label}* ({len(items)}):\n")
        else:
            lines.append(f"\n**{cat_label}** ({len(items)}):\n")

        for item in items:
            title = item["title"]
            source = item["source_name"]
            link_url = item.get("mobile_url") or item.get("url", "")
            ranks = item.get("ranks", [])
            magnitude = item.get("change_magnitude", 0)

            # 排名变化标注
            change_note = ""
            if cat_key == "rising" and magnitude:
                change_note = f" ↑{magnitude}"
            elif cat_key == "falling" and magnitude:
                change_note = f" ↓{magnitude}"

            if format_type == "feishu":
                if link_url:
                    line = f"· [{title}]({link_url})"
                else:
                    line = f"· {title}"
                line += f" <font color='grey'>[{source}{change_note}]</font>\n"

            elif format_type == "dingtalk":
                if link_url:
                    line = f"· [{title}]({link_url})"
                else:
                    line = f"· {title}"
                line += f" [{source}{change_note}]\n"

            elif format_type == "telegram":
                if link_url:
                    line = f'· <a href="{link_url}">{title}</a>'
                else:
                    line = f"· {title}"
                line += f" <code>[{source}{change_note}]</code>\n"

            elif format_type == "slack":
                if link_url:
                    line = f"· <{link_url}|{title}>"
                else:
                    line = f"· {title}"
                line += f" `[{source}{change_note}]`\n"

            elif format_type == "html":
                if link_url:
                    line = f'<li><a href="{link_url}" target="_blank">{title}</a>'
                else:
                    line = f"<li>{title}"
                line += f' <span class="source-tag">[{source}{change_note}]</span></li>\n'

            else:
                # markdown
                if link_url:
                    line = f"· [{title}]({link_url})"
                else:
                    line = f"· {title}"
                line += f" [{source}{change_note}]\n"

            lines.append(line)

        if format_type == "html":
            lines.append("</ul></div>")

    if format_type == "html":
        lines.append("</div>\n")
    else:
        lines.append("\n")

    return "".join(lines)


def generate_changes_for_report(
    report_data: Dict,
    format_type: str,
    rise_threshold: int = 3,
    fall_threshold: int = 3,
) -> str:
    """为报告生成变化对比卡片（一站式接口）

    Args:
        report_data: 报告数据字典
        format_type: 目标平台类型
        rise_threshold: 排名上升阈值
        fall_threshold: 排名下降阈值

    Returns:
        格式化后的变化对比卡片字符串
    """
    stats = report_data.get("stats", [])
    new_titles = report_data.get("new_titles", [])

    if not stats:
        return ""

    changes = detect_changes_from_stats(stats, new_titles, rise_threshold, fall_threshold)
    return format_changes_card(changes, format_type)
