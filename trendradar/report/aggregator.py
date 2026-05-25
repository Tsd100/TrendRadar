# coding=utf-8
"""
跨平台同主题聚合模块

检测不同平台上报道的同一主题新闻，合并为统一条目。
使用字符级相似度算法（针对中文优化）。
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple


def _char_bigram_jaccard(a: str, b: str) -> float:
    """计算两个字符串的字符 bigram Jaccard 相似度

    对中文文本更鲁棒，能捕捉到字符对级别的重合。
    """
    if len(a) < 2 or len(b) < 2:
        return 0.0
    def _bigrams(s):
        return {s[i:i+2] for i in range(len(s) - 1)}
    ba = _bigrams(a)
    bb = _bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _normalize_title(title: str) -> str:
    """标准化标题用于相似度比较

    - 去除标点符号和特殊字符
    - 去除多余空白
    - 转小写（处理英文部分）
    """
    if not title:
        return ""
    # 去除 URL
    title = re.sub(r'https?://\S+', '', title)
    # 保留中文字符、英文字母、数字
    title = re.sub(r'[^一-鿿\w]', '', title, flags=re.UNICODE)
    return title.lower().strip()


def _title_similarity(a: str, b: str) -> float:
    """计算两个标题的字符级相似度

    使用 SequenceMatcher 计算最长公共子序列比率。
    对于中文文本，字符级比较比词级比较更有效。
    """
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _has_common_substring(a: str, b: str, min_len: int = 4) -> bool:
    """检查两个标准化后的字符串是否有公共子串（长度 >= min_len）"""
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if len(na) < min_len or len(nb) < min_len:
        return False
    # 滑动窗口检查
    for i in range(len(na) - min_len + 1):
        if na[i:i + min_len] in nb:
            return True
    return False


def aggregate_cross_platform(
    stats: List[Dict],
    similarity_threshold: float = 0.45,
    min_common_len: int = 3,
) -> List[Dict]:
    """检测跨平台同主题新闻，在 title_data 上附加 platform_count 信息

    对 stats 中每个 title 检查是否在其他 source_name 中有相似标题。
    为每个 title_data 添加:
    - cross_platform_count: 覆盖平台数
    - cross_platform_sources: 覆盖的平台名称列表

    如果 stats 中已有 cross_platform_count 字段则跳过（避免重复计算）。

    Args:
        stats: 报告统计列表 [{"word": ..., "titles": [{"title": ..., "source_name": ...}]}]
        similarity_threshold: 相似度阈值（0-1 之间，越高越严格）
        min_common_len: 公共子串最小长度

    Returns:
        处理后的 stats 列表（原地修改 + 返回）
    """
    if not stats:
        return stats

    # 已聚合过则跳过
    first_title = None
    for stat in stats:
        for t in stat.get("titles", []):
            first_title = t
            break
        if first_title:
            break
    if first_title and "cross_platform_count" in first_title:
        return stats
    # 构建全局标题索引：title -> [(stat_idx, title_idx, source_name)]
    title_index: Dict[int, List[Tuple[int, int, str, str]]] = {}
    all_titles = []

    for si, stat in enumerate(stats):
        for ti, title_data in enumerate(stat.get("titles", [])):
            idx = len(all_titles)
            title_text = title_data.get("title", "")
            source = title_data.get("source_name", "")
            all_titles.append((title_text, source, si, ti))
            title_index[idx] = []

    if len(all_titles) < 2:
        return stats

    # 两两比较，建立相似性关系
    n = len(all_titles)
    groups = []  # List[Set[int]] 每组内的 title index
    assigned = set()

    for i in range(n):
        if i in assigned:
            continue
        group = {i}
        ti_text, ti_source, _, _ = all_titles[i]

        for j in range(i + 1, n):
            if j in assigned:
                continue
            tj_text, tj_source, _, _ = all_titles[j]

            # 跳过同源比较
            if ti_source == tj_source:
                continue

            # 快速过滤：公共子串检查
            if not _has_common_substring(ti_text, tj_text, min_common_len):
                continue

            # 相似度计算：SequenceMatcher 为主，bigram Jaccard 为补充
            sim = _title_similarity(ti_text, tj_text)
            if sim >= similarity_threshold:
                group.add(j)
                assigned.add(j)
            elif sim >= 0.35:
                # 处于灰色区间时，用 bigram Jaccard 辅助判断
                bg_sim = _char_bigram_jaccard(
                    _normalize_title(ti_text),
                    _normalize_title(tj_text),
                )
                if bg_sim >= 0.35:
                    group.add(j)
                    assigned.add(j)

        if len(group) > 1:
            groups.append(group)
        assigned.add(i)

    # 为每个 title_data 添加跨平台信息
    for group in groups:
        sources = set()
        for idx in group:
            _, source, _, _ = all_titles[idx]
            sources.add(source)

        for idx in group:
            _, _, si, ti = all_titles[idx]
            title_data = stats[si]["titles"][ti]
            title_data["cross_platform_count"] = len(sources)
            title_data["cross_platform_sources"] = sorted(sources)

    return stats


def get_top_cross_platform_titles(
    stats: List[Dict],
    top_n: int = 5,
) -> List[Dict]:
    """获取跨平台覆盖最广的 TOP N 标题

    Args:
        stats: 包含 cross_platform_count 的统计列表
        top_n: 返回条数

    Returns:
        跨平台覆盖度最高的标题列表
    """
    cross_titles = []
    for stat in stats:
        for title_data in stat.get("titles", []):
            count = title_data.get("cross_platform_count", 1)
            if count > 1:
                cross_titles.append({
                    "title": title_data.get("title", ""),
                    "source_name": title_data.get("source_name", ""),
                    "url": title_data.get("url", ""),
                    "mobile_url": title_data.get("mobile_url", ""),
                    "ranks": title_data.get("ranks", []),
                    "cross_platform_count": count,
                    "cross_platform_sources": title_data.get("cross_platform_sources", []),
                    "matched_keyword": stat.get("word", ""),
                })

    cross_titles.sort(key=lambda x: x["cross_platform_count"], reverse=True)
    return cross_titles[:top_n]


def format_cross_platform_card(
    cross_titles: List[Dict],
    format_type: str,
) -> str:
    """将跨平台聚合结果格式化为消息卡片

    Args:
        cross_titles: get_top_cross_platform_titles 的返回值
        format_type: 目标平台类型

    Returns:
        格式化后的卡片字符串
    """
    if not cross_titles:
        return ""

    lines = []

    if format_type == "feishu":
        lines.append("🌐 **跨平台热点** (多平台同时报道)\n")
    elif format_type == "dingtalk":
        lines.append("🌐 **跨平台热点** (多平台同时报道)\n")
    elif format_type == "telegram":
        lines.append("🌐 <b>跨平台热点</b> (多平台同时报道)\n")
    elif format_type == "slack":
        lines.append("🌐 *跨平台热点* (多平台同时报道)\n")
    elif format_type == "html":
        lines.append('<div class="cross-platform-card"><h3>🌐 跨平台热点</h3><ol>')
    else:
        lines.append("🌐 **跨平台热点** (多平台同时报道)\n")

    for i, item in enumerate(cross_titles, 1):
        title = item["title"]
        link_url = item.get("mobile_url") or item.get("url", "")
        platform_count = item.get("cross_platform_count", 0)
        sources = item.get("cross_platform_sources", [])
        sources_str = ", ".join(sources)

        if format_type == "feishu":
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" <font color='blue'>[{platform_count}平台: {sources_str}]</font>\n"

        elif format_type == "dingtalk":
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" [{platform_count}平台: {sources_str}]\n"

        elif format_type == "telegram":
            if link_url:
                line = f'{i}. <a href="{link_url}">{title}</a>'
            else:
                line = f"{i}. {title}"
            line += f" <code>[{platform_count}平台: {sources_str}]</code>\n"

        elif format_type == "slack":
            if link_url:
                line = f"{i}. <{link_url}|{title}>"
            else:
                line = f"{i}. {title}"
            line += f" `[{platform_count}平台: {sources_str}]`\n"

        elif format_type == "html":
            if link_url:
                line = f'<li><a href="{link_url}" target="_blank">{title}</a>'
            else:
                line = f"<li>{title}"
            line += f' <span class="platform-tag">[{platform_count}平台: {sources_str}]</span></li>\n'

        else:
            if link_url:
                line = f"{i}. [{title}]({link_url})"
            else:
                line = f"{i}. {title}"
            line += f" [{platform_count}平台: {sources_str}]\n"

        lines.append(line)

    if format_type == "html":
        lines.append("</ol></div>\n")
    else:
        lines.append("\n")

    return "".join(lines)
