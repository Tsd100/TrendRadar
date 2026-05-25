# coding=utf-8
"""
TL;DR 摘要卡片模块

从报告中提取 TOP 5 最热新闻条目，生成为各平台格式的摘要卡片。
热度评分综合考虑：排名、在榜时长、跨平台覆盖度。
"""

from typing import Dict, List, Optional


def _compute_hotness(title_data: Dict, rank_threshold: int = 10) -> float:
    """计算单条新闻的热度综合评分

    评分公式：排名得分 × 频率因子 × 新晋加分

    Args:
        title_data: 标题数据字典，包含 ranks, count, is_new 等
        rank_threshold: 排名高亮阈值

    Returns:
        热度评分（越高越热）
    """
    ranks = title_data.get("ranks", [])
    count = title_data.get("count", 1)
    is_new = title_data.get("is_new", False)

    # 1. 排名得分：取最佳排名（最小值），排名越靠前得分越高
    if ranks:
        best_rank = min(r for r in ranks if r > 0)
        rank_score = max(0, (rank_threshold - best_rank + 1) / rank_threshold)
    else:
        rank_score = 0.3  # 无排名数据给基础分

    # 2. 频率因子：出现次数越多越热（log 压缩避免极端值）
    freq_factor = 1.0 + 0.3 * min(count - 1, 10) / 10

    # 3. 新晋加分：新上榜的新闻给小幅加分
    new_bonus = 0.2 if is_new else 0

    return rank_score * freq_factor + new_bonus


def extract_top_titles(
    stats: List[Dict],
    top_n: int = 5,
    rank_threshold: int = 10,
) -> List[Dict]:
    """从报告统计中提取 TOP N 最热新闻条目

    Args:
        stats: 报告统计列表 [{"word": ..., "titles": [...]}, ...]
        top_n: 返回条数
        rank_threshold: 排名高亮阈值

    Returns:
        按热度降序排列的 TOP N 条目列表，每个条目包含:
        - title, source_name, url, mobile_url, ranks, count, is_new, hotness
    """
    all_titles = []
    for stat in stats:
        for title_data in stat.get("titles", []):
            score = _compute_hotness(title_data, rank_threshold)
            all_titles.append({
                "title": title_data.get("title", ""),
                "source_name": title_data.get("source_name", ""),
                "url": title_data.get("url", ""),
                "mobile_url": title_data.get("mobile_url", ""),
                "ranks": title_data.get("ranks", []),
                "count": title_data.get("count", 1),
                "is_new": title_data.get("is_new", False),
                "hotness": score,
                "matched_keyword": stat.get("word", ""),
            })

    # 按热度降序排序，取 TOP N
    all_titles.sort(key=lambda x: x["hotness"], reverse=True)
    return all_titles[:top_n]


def format_tldr_card(
    top_titles: List[Dict],
    format_type: str,
) -> str:
    """将 TOP 条目格式化为 TL;DR 摘要卡片

    Args:
        top_titles: extract_top_titles 的返回值
        format_type: 目标平台类型 (feishu, dingtalk, wework, telegram, html, etc.)

    Returns:
        格式化后的摘要卡片字符串
    """
    if not top_titles:
        return ""

    lines = []

    # 卡片标题
    if format_type == "feishu":
        lines.append("🔥 **TL;DR · 30秒速览**\n")
    elif format_type == "dingtalk":
        lines.append("🔥 **TL;DR · 30秒速览**\n")
    elif format_type == "telegram":
        lines.append("🔥 <b>TL;DR · 30秒速览</b>\n")
    elif format_type == "slack":
        lines.append("🔥 *TL;DR · 30秒速览*\n")
    elif format_type == "html":
        lines.append('<div class="tldr-card"><h3>🔥 TL;DR · 30秒速览</h3><ol>')
    else:
        lines.append("🔥 **TL;DR · 30秒速览**\n")

    for i, item in enumerate(top_titles, 1):
        title = item["title"]
        source = item["source_name"]
        link_url = item["mobile_url"] or item["url"]
        ranks = item.get("ranks", [])
        is_new = item.get("is_new", False)

        # 排名显示
        rank_str = ""
        if ranks:
            unique_ranks = sorted(set(ranks))
            if len(unique_ranks) == 1:
                rank_str = f"#{unique_ranks[0]}"
            else:
                rank_str = f"#{unique_ranks[0]}-{unique_ranks[-1]}"

        new_tag = " 🆕" if is_new else ""

        if format_type == "feishu":
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" <font color='grey'>[{source}{new_tag}{' ' + rank_str if rank_str else ''}]</font>\n"

        elif format_type == "dingtalk":
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" [{source}{new_tag}{' ' + rank_str if rank_str else ''}]\n"

        elif format_type == "telegram":
            if link_url:
                line = f'{i}. <a href="{link_url}">{title}</a>'
            else:
                line = f"{i}. {title}"
            line += f" <code>[{source}{new_tag}{' ' + rank_str if rank_str else ''}]</code>\n"

        elif format_type == "slack":
            if link_url:
                line = f"{i}. <{link_url}|{title}>"
            else:
                line = f"{i}. {title}"
            line += f" `[{source}{new_tag}{' ' + rank_str if rank_str else ''}]`\n"

        elif format_type == "html":
            if link_url:
                line = f'<li><a href="{link_url}" target="_blank">{title}</a>'
            else:
                line = f"<li>{title}"
            line += f' <span class="source-tag">[{source}{new_tag}{" " + rank_str if rank_str else ""}]</span></li>\n'

        else:
            # wework, bark, ntfy - markdown
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" [{source}{new_tag}{' ' + rank_str if rank_str else ''}]\n"

        lines.append(line)

    if format_type == "html":
        lines.append("</ol></div>\n")
    else:
        lines.append("\n")

    return "".join(lines)


def generate_tldr_for_report(
    report_data: Dict,
    format_type: str,
    top_n: int = 5,
    rank_threshold: int = 10,
) -> str:
    """为报告生成 TL;DR 摘要卡片（一站式接口）

    Args:
        report_data: 报告数据字典
        format_type: 目标平台类型
        top_n: TOP N 数量
        rank_threshold: 排名高亮阈值

    Returns:
        格式化后的 TL;DR 卡字符串
    """
    stats = report_data.get("stats", [])
    if not stats:
        return ""

    top_titles = extract_top_titles(stats, top_n, rank_threshold)
    if not top_titles:
        return ""

    return format_tldr_card(top_titles, format_type)
