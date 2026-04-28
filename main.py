"""astrbot_plugin_groupsays — main entry.

Two entry points to the same render pipeline:

1. ``/群友说 @某人 要说的话`` — slash command (group chat only)
2. ``generate_groupsays_meme`` LLM tool — registered as a function-call
   tool so the LLM can invoke it from natural-language phrasing like
   "帮我生成一个 xxx 说 yyy 的表情包".

Both paths converge on ``_run_pipeline``: sanitize → permission-check
(whitelist / exemption / counter-attack) → fetch nickname & avatar in
parallel → blocking PIL render in a thread → return as image chain.

Platform support: aiocqhttp (NapCat / OneBot v11) only. The avatar URL,
nickname lookup, and member-list APIs are all OneBot-specific.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

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
ONEBOT_PLATFORM_NAME = "aiocqhttp"


@register(
    "astrbot_plugin_groupsays",
    "Yukin",
    "群友说 表情包生成器 — @某人 或让 LLM 指定群友 + 一段话 → 聊天气泡图",
    "v0.2.2",
    "https://github.com/Catkamakura/astrbot_plugin_groupsays",
)
class GroupSaysPlugin(Star):
    def __init__(self, context: Context, config: Optional[dict] = None):
        super().__init__(context)
        cfg = config or {}
        self.max_nickname_len: int = int(cfg.get("max_nickname_length", 20))
        self.max_text_len: int = int(cfg.get("max_text_length", 200))
        self.strip_emoji: bool = bool(cfg.get("strip_emoji_in_nickname", True))
        self.canvas_bg: str = str(cfg.get("canvas_bg", "#E4E8F0"))
        self.bubble_bg: str = str(cfg.get("bubble_bg", "#FFFFFF"))

        # Exemption / counter-attack / whitelist
        self.exemption_qqs: set[str] = self._parse_csv(cfg.get("exemption_list", ""))
        self.whitelist_qqs: set[str] = self._parse_csv(cfg.get("whitelist", ""))
        self.counter_attack: bool = bool(cfg.get("counter_attack", False))
        self.counter_attack_text: str = str(cfg.get("counter_attack_text", ""))

        logger.info(
            "[groupsays] loaded v0.2.2 — nickname<=%d, text<=%d, strip_emoji=%s, "
            "exempt=%d, whitelist=%d, counter=%s",
            self.max_nickname_len, self.max_text_len, self.strip_emoji,
            len(self.exemption_qqs), len(self.whitelist_qqs), self.counter_attack,
        )

    async def terminate(self) -> None:
        """Lifecycle hook called when the plugin is unloaded / disabled.

        Nothing stateful to clean up — there are no background tasks,
        no open connections, no scheduled jobs. The httpx client used
        by ``_fetch_avatar`` is short-lived (created per-request), and
        the font cache lives in ``fonts._cached_path`` which is
        process-global.
        """
        return None

    # ── Entry 1: slash command ────────────────────────────────────────

    @filter.command("群友说")
    async def cmd_say(self, event: AstrMessageEvent):
        if not self._platform_ok(event):
            yield event.plain_result("此功能目前仅支持 QQ 群 (NapCat / OneBot v11)")
            return

        at_qq, raw_text = parse_at_and_text(event)
        if not at_qq:
            yield event.plain_result(
                "请 @ 一位群友\n用法：/群友说 @某人 要说的话"
            )
            return

        async for result in self._run_pipeline(event, at_qq, raw_text):
            yield result

    # ── Entry 2: LLM-callable tool ────────────────────────────────────

    @filter.llm_tool(name="generate_groupsays_meme")
    async def llm_generate(
        self,
        event: AstrMessageEvent,
        target_name: str,
        text: str,
    ):
        """生成"群友说"风格的聊天气泡表情包。
        当用户想让某个群友"说"一段话，并生成一张对应的聊天截图表情包时调用此工具。
        仅在 QQ 群聊中可用。

        Args:
            target_name(string): 要说话的目标群友。可以是该群友的群昵称、QQ 昵称、或 QQ 号。支持模糊匹配。
            text(string): 让该群友"说"的内容（会作为聊天气泡里的文本）。
        """
        if not self._platform_ok(event):
            yield event.plain_result("此功能仅支持 QQ 群 (NapCat / OneBot v11)")
            return

        resolved, hint = await self._resolve_member(event, target_name)
        if not resolved:
            yield event.plain_result(hint or f"找不到群友「{target_name}」。")
            return

        async for result in self._run_pipeline(event, resolved, text):
            yield result

    # ── Core pipeline shared by both entries ──────────────────────────

    async def _run_pipeline(
        self,
        event: AstrMessageEvent,
        at_qq: str,
        raw_text: str,
    ):
        """Full pipeline: sanitize → exemption → fetch → render → yield image."""
        text = sanitize_body(raw_text, max_len=self.max_text_len)
        if not text:
            yield event.plain_result("他要说点啥？")
            return

        # ── Permission layer ────────────────────────────────────────
        # Priority: whitelist bypass > exemption check > counter-attack reflect
        sender_qq = (
            str(event.get_sender_id()) if event.get_sender_id() else None
        )

        sender_whitelisted = bool(sender_qq and sender_qq in self.whitelist_qqs)

        if sender_whitelisted:
            # Whitelisted sender can target anyone, including exempt users.
            # Self-targeting from the whitelist also works here.
            logger.debug(
                "[groupsays] whitelist bypass by %s targeting %s",
                sender_qq, at_qq,
            )
        elif at_qq in self.exemption_qqs:
            if not self.counter_attack:
                yield event.plain_result("该成员受保护，不允许被群友说")
                return
            # Counter-attack: reflect to sender.
            if not sender_qq:
                yield event.plain_result("该成员受保护，不允许被群友说")
                return
            # If sender is also exempt → no further deflection possible.
            if sender_qq in self.exemption_qqs:
                yield event.plain_result("该成员受保护，不允许被群友说")
                return
            logger.info(
                "[groupsays] counter-attack: %s reflected back (origin target %s)",
                sender_qq, at_qq,
            )
            at_qq = sender_qq
            if self.counter_attack_text:
                text = f"{self.counter_attack_text}{text}"

        # Parallel fetch: nickname + avatar
        try:
            nickname_raw, avatar_bytes = await asyncio.gather(
                self._fetch_nickname(event, at_qq),
                self._fetch_avatar(at_qq),
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

        # Font (auto-download on first call)
        try:
            font_path = await ensure_font()
        except Exception as e:
            logger.exception("[groupsays] font setup failed")
            yield event.plain_result(f"字体准备失败: {e}")
            return

        # Render (blocking → thread)
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

    # ── Name resolution for the LLM tool ──────────────────────────────

    async def _resolve_member(
        self,
        event: AstrMessageEvent,
        query: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolve ``query`` (QQ number or name) to a QQ id.

        Returns ``(qq_id, error_hint)``. On failure the qq_id is None and
        the hint is a message suitable for feeding back to the user / LLM.
        """
        q = (query or "").strip()
        if not q:
            return None, "未提供目标群友"

        # Pure digits → treat as QQ directly
        if q.isdigit():
            return q, None

        group_id = event.get_group_id()
        if not group_id:
            return None, "请在群聊中使用此功能（私聊下无法通过名字查找群友）"

        try:
            bot = event.bot
            members = await bot.call_action(
                "get_group_member_list",
                group_id=int(group_id),
                no_cache=False,
            )
        except Exception as e:
            logger.warning(f"[groupsays] member list fetch failed: {e}")
            return None, "获取群成员列表失败"

        qq = self._fuzzy_match(members or [], q)
        if not qq:
            return None, f"群里找不到「{query}」，请尝试更准确的群昵称或直接 @。"
        return qq, None

    @staticmethod
    def _fuzzy_match(members: List[dict], query: str) -> Optional[str]:
        """Priority: exact > startswith > contains. Tie-break: shortest name."""
        ql = query.casefold()
        exact: List[Tuple[int, str, str]] = []
        starts: List[Tuple[int, str, str]] = []
        contains: List[Tuple[int, str, str]] = []

        for m in members:
            uid = m.get("user_id")
            if uid is None:
                continue
            candidates = [
                (m.get("card") or "").strip(),
                (m.get("nickname") or "").strip(),
            ]
            best_bucket = None
            best_name = ""
            for name in candidates:
                if not name:
                    continue
                nl = name.casefold()
                if nl == ql:
                    best_bucket, best_name = "exact", name
                    break
                if best_bucket is None and nl.startswith(ql):
                    best_bucket, best_name = "starts", name
                elif best_bucket is None and ql in nl:
                    best_bucket, best_name = "contains", name

            if best_bucket == "exact":
                exact.append((uid, best_name, candidates[0] or candidates[1]))
            elif best_bucket == "starts":
                starts.append((uid, best_name, candidates[0] or candidates[1]))
            elif best_bucket == "contains":
                contains.append((uid, best_name, candidates[0] or candidates[1]))

        for bucket in (exact, starts, contains):
            if not bucket:
                continue
            # Shortest display name wins when multiple hits.
            bucket.sort(key=lambda t: len(t[1]))
            return str(bucket[0][0])
        return None

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _platform_ok(event: AstrMessageEvent) -> bool:
        return event.get_platform_name() == ONEBOT_PLATFORM_NAME

    @staticmethod
    def _parse_csv(s: str) -> set[str]:
        if not s:
            return set()
        return {x.strip() for x in str(s).split(",") if x.strip().isdigit()}

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
