"""astrbot_plugin_groupsays — main entry.

/群友说 @某人 要说的话  →  my_friend 风格聊天气泡图
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register

from .fonts import ensure_font
from .render import render_my_friend
from .utils import parse_at_and_text, sanitize_body, sanitize_nickname


AVATAR_URL_TEMPLATE = "https://q.qlogo.cn/g?b=qq&nk={qq}&s=640"
AVATAR_FETCH_TIMEOUT = 10.0
ONEBOT_PLATFORM_NAME = "aiocqhttp"  # NapCat adapter's name inside AstrBot


@register(
    "astrbot_plugin_groupsays",
    "Yukin",
    "群友说 表情包生成器 — @某人 + 一段话 → my_friend 风格聊天气泡图",
    "0.1.0",
    "",
)
class GroupSaysPlugin(Star):
    def __init__(self, context: Context, config: Optional[dict] = None):
        super().__init__(context)
        cfg = config or {}
        self.max_nickname_len: int = int(cfg.get("max_nickname_length", 20))
        self.max_text_len: int = int(cfg.get("max_text_length", 200))
        self.strip_emoji: bool = bool(cfg.get("strip_emoji_in_nickname", True))
        self.canvas_bg: str = str(cfg.get("canvas_bg", "#EBEBEB"))
        self.bubble_bg: str = str(cfg.get("bubble_bg", "#FFFFFF"))
        logger.info(
            "[groupsays] loaded. nickname<=%d, text<=%d, strip_emoji=%s",
            self.max_nickname_len, self.max_text_len, self.strip_emoji,
        )

    # ── Command handler ───────────────────────────────────────────────

    @filter.command("群友说")
    async def cmd_say(self, event: AstrMessageEvent):
        # Only OneBot v11 (NapCat) is supported for now
        if event.get_platform_name() != ONEBOT_PLATFORM_NAME:
            yield event.plain_result("此功能目前仅支持 QQ 群 (NapCat / OneBot v11)")
            return

        at_qq, raw_text = parse_at_and_text(event)
        if not at_qq:
            yield event.plain_result(
                "请 @ 一位群友\n用法：/群友说 @某人 要说的话"
            )
            return

        text = sanitize_body(raw_text, max_len=self.max_text_len)
        if not text:
            yield event.plain_result("他要说点啥？")
            return

        # Fetch avatar + nickname in parallel — they're independent.
        nickname_task = asyncio.create_task(self._fetch_nickname(event, at_qq))
        avatar_task = asyncio.create_task(self._fetch_avatar(at_qq))

        try:
            nickname_raw, avatar_bytes = await asyncio.gather(
                nickname_task, avatar_task
            )
        except Exception as e:
            logger.exception("[groupsays] fetch failed")
            yield event.plain_result(f"获取群友信息失败: {e}")
            return

        nickname = sanitize_nickname(
            nickname_raw,
            max_len=self.max_nickname_len,
            strip_emoji=self.strip_emoji,
        )

        # Font (downloaded on first call; cached afterwards)
        try:
            font_path = await ensure_font()
        except Exception as e:
            logger.exception("[groupsays] font setup failed")
            yield event.plain_result(f"字体准备失败: {e}")
            return

        # Render in a worker thread — PIL is blocking.
        try:
            img_bytes = await asyncio.to_thread(
                render_my_friend,
                avatar_bytes,
                nickname,
                text,
                font_path,
                canvas_bg=self.canvas_bg,
                bubble_bg=self.bubble_bg,
            )
        except Exception as e:
            logger.exception("[groupsays] render failed")
            yield event.plain_result(f"生成失败: {e}")
            return

        yield event.chain_result([Image.fromBytes(img_bytes)])

    # ── Data fetchers ─────────────────────────────────────────────────

    async def _fetch_nickname(self, event: AstrMessageEvent, qq: str) -> str:
        """Prefer group card, fall back to QQ nickname, fall back to QQ number."""
        group_id = event.get_group_id()
        bot = event.bot

        try:
            if group_id:
                info = await bot.call_action(
                    "get_group_member_info",
                    group_id=int(group_id),
                    user_id=int(qq),
                    no_cache=True,
                )
                return info.get("card") or info.get("nickname") or str(qq)

            # Private chat fallback
            info = await bot.call_action(
                "get_stranger_info",
                user_id=int(qq),
            )
            return info.get("nickname") or str(qq)

        except Exception as e:
            logger.warning(f"[groupsays] nickname fetch failed for {qq}: {e}")
            return str(qq)

    async def _fetch_avatar(self, qq: str) -> bytes:
        url = AVATAR_URL_TEMPLATE.format(qq=qq)
        async with httpx.AsyncClient(timeout=AVATAR_FETCH_TIMEOUT) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            return resp.content
