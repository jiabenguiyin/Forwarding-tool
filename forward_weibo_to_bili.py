#!/usr/bin/env python3
"""自动转发指定微博用户最新动态到 B 站动态。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

WEIBO_API = "https://m.weibo.cn/api/container/getIndex"
BILI_CREATE_API = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/create"
DEFAULT_WEIBO_UID = "5657426591"
M_WEIBO_UID_URL_RE = re.compile(r"https?://m\.weibo\.cn/u/(\d+)")
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Mobile Safari/537.36"
)

# 通过 CookieJar 维持 m.weibo.cn 的上下文，降低 432 风控命中率。
_COOKIE_JAR = CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_COOKIE_JAR))


@dataclass
class Config:
    weibo_uids: list[str]
    bili_cookie: str
    state_file: Path = Path(".forward_state.json")
    dry_run: bool = False
    prefix: str = "转自{name}微博：\n\n"


def html_to_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def normalize_one_uid(value: str) -> str:
    """支持纯 UID 或 m.weibo.cn/u/<uid> 链接。"""
    val = value.strip()
    if not val:
        return ""
    m = M_WEIBO_UID_URL_RE.match(val)
    if m:
        return m.group(1)
    return val


def normalize_uids(raw_single_uid: str, raw_uids: str) -> list[str]:
    values: list[str] = []
    if raw_single_uid:
        uid = normalize_one_uid(raw_single_uid)
        if uid:
            values.append(uid)
    if raw_uids:
        for item in raw_uids.split(","):
            uid = normalize_one_uid(item)
            if uid:
                values.append(uid)
    if not values:
        values = [DEFAULT_WEIBO_UID]

    dedup: list[str] = []
    seen: set[str] = set()
    for uid in values:
        if uid not in seen:
            dedup.append(uid)
            seen.add(uid)
    return dedup


def load_config() -> Config:
    weibo_uid = os.getenv("WEIBO_UID", "").strip()
    weibo_uids = os.getenv("WEIBO_UIDS", "").strip()
    weibo_user_input = os.getenv("WEIBO_USER_INPUT", "").strip()
    if weibo_user_input and not weibo_uid:
        weibo_uid = weibo_user_input
    bili_cookie = os.getenv("BILI_COOKIE", "").strip()
    state_file = Path(os.getenv("STATE_FILE", ".forward_state.json"))
    dry_run = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"}
    prefix = os.getenv("FORWARD_PREFIX", "转自{name}微博：\n\n")

    uid_list = normalize_uids(weibo_uid, weibo_uids)

    if not bili_cookie and not dry_run:
        print("[WARN] 未提供 BILI_COOKIE，自动切换到 DRY_RUN=true（仅预览，不发布）。")
        dry_run = True

    return Config(
        weibo_uids=uid_list,
        bili_cookie=bili_cookie,
        state_file=state_file,
        dry_run=dry_run,
        prefix=prefix,
    )


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    full_url = url
    body: bytes | None = None

    if params:
        full_url = f"{url}?{urllib.parse.urlencode(params)}"
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(full_url, data=body, method="POST" if body else "GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 432:
            raise RuntimeError(
                "HTTP 432（微博风控）: 目标接口拒绝当前请求。"
                "请稍后重试，或更换出口 IP/代理，并确保使用 m.weibo.cn 链接。"
            ) from e
        raise RuntimeError(f"HTTP 错误: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络请求失败: {e.reason}") from e

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("接口返回不是有效 JSON") from e


def warmup_weibo(uid: str) -> None:
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://m.weibo.cn/",
        "Accept": "text/html,application/xhtml+xml",
    }
    req = urllib.request.Request(f"https://m.weibo.cn/u/{uid}", headers=headers, method="GET")
    try:
        with _OPENER.open(req, timeout=10):
            return
    except Exception:
        # 预热失败不终止，继续尝试 API 拉取。
        return


def fetch_latest_weibo(uid: str) -> dict[str, Any]:
    warmup_weibo(uid)
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": f"https://m.weibo.cn/u/{uid}",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "MWeibo-Pwa": "1",
    }
    data = request_json(
        WEIBO_API,
        params={"containerid": f"107603{uid}", "count": 1},
        headers=headers,
    )

    cards = data.get("data", {}).get("cards", [])
    if not cards:
        # 某些情况下需要补充 type/value 参数。
        data = request_json(
            WEIBO_API,
            params={
                "type": "uid",
                "value": uid,
                "containerid": f"107603{uid}",
                "count": 1,
            },
            headers=headers,
        )
        cards = data.get("data", {}).get("cards", [])

    if not cards:
        raise RuntimeError(
            f"未获取到微博内容（可能是风控、IP 受限或 UID 不可见）: {uid}"
        )

    mblog = cards[0].get("mblog")
    if not mblog:
        raise RuntimeError(f"微博返回结构异常，未找到 mblog: {uid}")
    return mblog


def read_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_csrf(cookie: str) -> str:
    match = re.search(r"(?:^|;\s*)bili_jct=([^;]+)", cookie)
    if not match:
        raise ValueError("BILI_COOKIE 中未找到 bili_jct，无法提交动态")
    return match.group(1)


def post_to_bilibili(content: str, cookie: str) -> None:
    csrf = get_csrf(cookie)
    headers = {
        "Cookie": cookie,
        "Origin": "https://t.bilibili.com",
        "Referer": "https://t.bilibili.com/",
        "User-Agent": "Mozilla/5.0",
    }
    payload = {
        "dynamic_id": 0,
        "type": 4,
        "rid": 0,
        "content": content,
        "up_choose_comment": 0,
        "extension": "{\"emoji_type\":1}",
        "csrf": csrf,
    }
    data = request_json(BILI_CREATE_API, data=payload, headers=headers)
    if data.get("code") != 0:
        raise RuntimeError(f"B站发布失败: code={data.get('code')}, msg={data.get('msg')}")


def build_forward_text(mblog: dict[str, Any], prefix_template: str) -> str:
    name = mblog.get("user", {}).get("screen_name", "未知用户")
    text = html_to_text(mblog.get("text", ""))
    prefix = prefix_template.format(name=name)
    return f"{prefix}{text}".strip()


def process_uid(config: Config, uid: str, state: dict[str, str]) -> bool:
    latest = fetch_latest_weibo(uid)

    mid = str(latest.get("mid") or latest.get("id"))
    if not mid:
        raise RuntimeError(f"微博缺少 mid/id，无法去重: {uid}")

    last_mid = state.get(uid)
    if last_mid == mid:
        print(f"[{uid}] 无新微博，跳过。mid={mid}")
        return False

    content = build_forward_text(latest, config.prefix)

    if config.dry_run:
        print(f"[DRY_RUN][{uid}] 将要发布的 B 站动态内容：\n")
        print(content)
    else:
        post_to_bilibili(content, config.bili_cookie)
        print(f"[{uid}] 发布成功。")

    state[uid] = mid
    return True


def main() -> None:
    config = load_config()
    state = read_state(config.state_file)

    changed = False
    for uid in config.weibo_uids:
        if process_uid(config, uid, state):
            changed = True

    if changed:
        save_state(config.state_file, state)
        print(f"状态已更新：{config.state_file}")
    else:
        print("所有 UID 均无更新。")


if __name__ == "__main__":
    main()
