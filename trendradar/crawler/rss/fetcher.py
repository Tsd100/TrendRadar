# coding=utf-8
"""
RSS 抓取器

负责从配置的 RSS 源抓取数据并转换为标准格式
支持：指数退避重试、UA 轮换、源健康监控
"""

import json
import os
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import requests

from .parser import RSSParser
from trendradar.storage.base import RSSItem, RSSData
from trendradar.utils.time import get_configured_time, is_within_days, DEFAULT_TIMEZONE

# 健康监控文件路径
HEALTH_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "output", "rss_health.json")

# 连续失败多少次后告警
ALERT_THRESHOLD = 3

# 重试配置
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # 指数退避基数（秒）

# UA 池（轮换使用）
_USER_AGENTS = [
    "TrendRadar/2.0 RSS Reader (https://github.com/trendradar)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "FeedFetcher/1.0 (compatible; RSS Reader Bot)",
]


def _load_health_record() -> Dict:
    """加载 RSS 源健康记录"""
    if not os.path.exists(HEALTH_FILE):
        return {}
    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as f:
            record = json.load(f)
            return {k: v for k, v in record.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, IOError):
        return {}


def _save_health_record(record: Dict) -> None:
    """保存 RSS 源健康记录"""
    os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
    with open(HEALTH_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def _check_health_alert(feed_id: str) -> Optional[str]:
    """检查是否需要健康告警，返回告警消息或 None"""
    record = _load_health_record()
    info = record.get(feed_id, {})
    consecutive = info.get("consecutive_failures", 0)
    if consecutive >= ALERT_THRESHOLD:
        return (
            f"RSS 源 [{feed_id}] 已连续失败 {consecutive} 次，"
            f"最后错误: {info.get('last_error', '未知')}"
        )
    return None


@dataclass
class RSSFeedConfig:
    """RSS 源配置"""
    id: str
    name: str
    url: str
    max_items: int = 0
    enabled: bool = True
    max_age_days: Optional[int] = None


class RSSFetcher:
    """RSS 抓取器（支持重试、UA 轮换、健康监控）"""

    def __init__(
        self,
        feeds: List[RSSFeedConfig],
        request_interval: int = 2000,
        timeout: int = 15,
        use_proxy: bool = False,
        proxy_url: str = "",
        timezone: str = DEFAULT_TIMEZONE,
        freshness_enabled: bool = True,
        default_max_age_days: int = 3,
    ):
        self.feeds = [f for f in feeds if f.enabled]
        self.request_interval = request_interval
        self.timeout = timeout
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url
        self.timezone = timezone
        self.freshness_enabled = freshness_enabled
        self.default_max_age_days = default_max_age_days
        self.parser = RSSParser()

    def _create_session(self) -> requests.Session:
        """创建请求会话"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "application/feed+json, application/json, application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        if self.use_proxy and self.proxy_url:
            session.proxies = {"http": self.proxy_url, "https": self.proxy_url}
        return session

    def _rotate_ua(self, session: requests.Session) -> None:
        """轮换 User-Agent"""
        session.headers["User-Agent"] = random.choice(_USER_AGENTS)

    def _retry_request(self, feed: RSSFeedConfig) -> Tuple[Optional[requests.Response], Optional[str]]:
        """带指数退避重试的 HTTP 请求"""
        session = self._create_session()
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._rotate_ua(session)
                response = session.get(feed.url, timeout=self.timeout)
                response.raise_for_status()
                return response, None
            except requests.Timeout:
                last_error = f"请求超时 ({self.timeout}s)"
            except requests.HTTPError as e:
                status = e.response.status_code if hasattr(e, "response") and e.response else "?"
                last_error = f"HTTP {status}"
                if status == 403:
                    break  # 403 不重试
            except requests.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
            except Exception as e:
                last_error = f"未知错误: {e}"
                break  # 非网络错误不重试

            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(0, 1)
                print(f"[RSS] {feed.name}: {last_error}, {wait:.1f}s 后重试 ({attempt}/{MAX_RETRIES})")
                time.sleep(wait)

        return None, last_error

    def _update_health(self, feed_id: str, feed_name: str, success: bool, error: str = "") -> None:
        """更新 RSS 源健康状态"""
        record = _load_health_record()
        info = record.get(feed_id, {
            "name": feed_name,
            "consecutive_failures": 0,
            "total_failures": 0,
            "last_error": "",
            "last_success": "",
        })

        info["name"] = feed_name
        now = get_configured_time(self.timezone).strftime("%Y-%m-%d %H:%M")

        if success:
            info["consecutive_failures"] = 0
            info["last_success"] = now
        else:
            info["consecutive_failures"] = info.get("consecutive_failures", 0) + 1
            info["total_failures"] = info.get("total_failures", 0) + 1
            info["last_error"] = error

        record[feed_id] = info
        _save_health_record(record)

    def get_health_status(self) -> List[Dict]:
        """获取所有 RSS 源的健康状态"""
        record = _load_health_record()
        status = []
        for feed in self.feeds:
            info = record.get(feed.id, {})
            consecutive = info.get("consecutive_failures", 0)
            status.append({
                "id": feed.id,
                "name": feed.name,
                "consecutive_failures": consecutive,
                "total_failures": info.get("total_failures", 0),
                "last_error": info.get("last_error", ""),
                "last_success": info.get("last_success", ""),
                "healthy": consecutive < ALERT_THRESHOLD,
                "alert": f"[{feed.name}] 已连续失败 {consecutive} 次: {info.get('last_error', '')}"
                    if consecutive >= ALERT_THRESHOLD else "",
            })
        return status

    def _filter_by_freshness(
        self,
        items: List[RSSItem],
        feed: RSSFeedConfig,
    ) -> Tuple[List[RSSItem], int]:
        if not self.freshness_enabled:
            return items, 0
        max_days = feed.max_age_days
        if max_days is None:
            max_days = self.default_max_age_days
        if max_days == 0:
            return items, 0
        filtered = []
        for item in items:
            if not item.published_at:
                filtered.append(item)
            elif is_within_days(item.published_at, max_days, self.timezone):
                filtered.append(item)
        return filtered, len(items) - len(filtered)

    def fetch_feed(self, feed: RSSFeedConfig) -> Tuple[List[RSSItem], Optional[str]]:
        """抓取单个 RSS 源（带重试和健康追踪）"""
        response, error = self._retry_request(feed)

        if error:
            self._update_health(feed.id, feed.name, success=False, error=error)
            alert = _check_health_alert(feed.id)
            if alert:
                print(f"[RSS] 健康告警: {alert}")
            return [], error

        try:
            parsed_items = self.parser.parse(response.text, feed.url)
            if feed.max_items > 0:
                parsed_items = parsed_items[:feed.max_items]

            now = get_configured_time(self.timezone)
            crawl_time = now.strftime("%H:%M")
            items = []
            for parsed in parsed_items:
                items.append(RSSItem(
                    title=parsed.title,
                    feed_id=feed.id,
                    feed_name=feed.name,
                    url=parsed.url,
                    guid=parsed.guid or "",
                    published_at=parsed.published_at or "",
                    summary=parsed.summary or "",
                    author=parsed.author or "",
                    crawl_time=crawl_time,
                    first_time=crawl_time,
                    last_time=crawl_time,
                    count=1,
                ))

            print(f"[RSS] {feed.name}: 获取 {len(items)} 条")
            self._update_health(feed.id, feed.name, success=True)
            return items, None

        except ValueError as e:
            error = f"解析失败: {e}"
            print(f"[RSS] {feed.name}: {error}")
            self._update_health(feed.id, feed.name, success=False, error=error)
            return [], error
        except Exception as e:
            error = f"未知错误: {e}"
            print(f"[RSS] {feed.name}: {error}")
            self._update_health(feed.id, feed.name, success=False, error=error)
            return [], error

    def fetch_all(self) -> RSSData:
        """抓取所有 RSS 源"""
        all_items: Dict[str, List[RSSItem]] = {}
        id_to_name: Dict[str, str] = {}
        failed_ids: List[str] = []

        now = get_configured_time(self.timezone)
        crawl_time = now.strftime("%H:%M")
        crawl_date = now.strftime("%Y-%m-%d")

        print(f"[RSS] 开始抓取 {len(self.feeds)} 个 RSS 源...")

        for i, feed in enumerate(self.feeds):
            if i > 0:
                interval = self.request_interval / 1000
                jitter = random.uniform(-0.2, 0.2) * interval
                time.sleep(interval + jitter)

            items, error = self.fetch_feed(feed)
            id_to_name[feed.id] = feed.name

            if error:
                failed_ids.append(feed.id)
            else:
                all_items[feed.id] = items

        total_items = sum(len(items) for items in all_items.values())
        failed_count = len(failed_ids)
        print(f"[RSS] 抓取完成: {len(all_items)} 个源成功, {failed_count} 个失败, 共 {total_items} 条")

        # 汇总健康状态
        if failed_count > 0:
            health_status = self.get_health_status()
            unhealthy = [h["alert"] for h in health_status if h["alert"]]
            for alert in unhealthy:
                print(f"[RSS] 健康告警: {alert}")

        return RSSData(
            date=crawl_date,
            crawl_time=crawl_time,
            items=all_items,
            id_to_name=id_to_name,
            failed_ids=failed_ids,
        )

    @classmethod
    def from_config(cls, config: Dict) -> "RSSFetcher":
        freshness_config = config.get("freshness_filter", {})
        freshness_enabled = freshness_config.get("enabled", True)
        default_max_age_days = freshness_config.get("max_age_days", 3)

        feeds = []
        for feed_config in config.get("feeds", []):
            max_age_days_raw = feed_config.get("max_age_days")
            max_age_days = None
            if max_age_days_raw is not None:
                try:
                    max_age_days = int(max_age_days_raw)
                    if max_age_days < 0:
                        feed_id = feed_config.get("id", "unknown")
                        print(f"[警告] RSS feed '{feed_id}' 的 max_age_days 为负数，将使用全局默认值")
                        max_age_days = None
                except (ValueError, TypeError):
                    feed_id = feed_config.get("id", "unknown")
                    print(f"[警告] RSS feed '{feed_id}' 的 max_age_days 格式错误：{max_age_days_raw}")
                    max_age_days = None

            feed = RSSFeedConfig(
                id=feed_config.get("id", ""),
                name=feed_config.get("name", ""),
                url=feed_config.get("url", ""),
                max_items=feed_config.get("max_items", 0),
                enabled=feed_config.get("enabled", True),
                max_age_days=max_age_days,
            )
            if feed.id and feed.url:
                feeds.append(feed)

        return cls(
            feeds=feeds,
            request_interval=config.get("request_interval", 2000),
            timeout=config.get("timeout", 15),
            use_proxy=config.get("use_proxy", False),
            proxy_url=config.get("proxy_url", ""),
            timezone=config.get("timezone", DEFAULT_TIMEZONE),
            freshness_enabled=freshness_enabled,
            default_max_age_days=default_max_age_days,
        )
