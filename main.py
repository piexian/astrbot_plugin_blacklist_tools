from html import escape
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_tools import StarTools
from .utils.text_to_image import text_to_image
from .database import BlacklistDatabase

LEGACY_DATA_DIR_NAMES = ("astrbot_plugin_blacklist_toolss",)
BLACKLIST_IMAGE_OPTIONS = {
    "type": "png",
    "full_page": True,
    "scale": "device",
    "animations": "disabled",
    "timeout": 20000,
}
BLACKLIST_LIST_TEMPLATE = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    background: #f4f7fb;
  }
  body {
    min-width: 0;
  }
  *, *::before, *::after {
    box-sizing: border-box;
  }
</style>
<div style="
    width: 100%;
    padding: 40px;
    color: #132238;
    font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background:
      radial-gradient(circle at top left, rgba(255, 183, 77, 0.18), transparent 28%),
      radial-gradient(circle at bottom right, rgba(20, 184, 166, 0.16), transparent 26%),
      linear-gradient(180deg, #fbf7ef 0%, #f4f7fb 100%);
">
  <div style="
      width: 1240px;
      margin: 0 auto;
      background: rgba(255,255,255,0.82);
      border: 1px solid rgba(19,34,56,0.08);
      border-radius: 32px;
      padding: 34px 36px 30px;
      box-shadow: 0 28px 80px rgba(19,34,56,0.10);
      backdrop-filter: blur(10px);
  ">
    <div style="display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:28px;">
      <div>
        <div style="
            display:inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            background:#132238;
            color:#fffaf2;
            font-size:14px;
            letter-spacing:1.2px;
        ">BLACKLIST LEDGER</div>
        <div style="margin-top:16px; font-size:42px; font-weight:800; letter-spacing:1px;">黑名单档案</div>
        <div style="margin-top:8px; color:#5f6f85; font-size:18px;">共 {{ total_count }} 条记录，当前第 {{ page }}/{{ total_pages }} 页</div>
      </div>
      <div style="
          min-width: 220px;
          padding: 16px 18px;
          border-radius: 22px;
          background: linear-gradient(135deg, #fff4d8 0%, #fffaf2 100%);
          border: 1px solid rgba(217, 119, 6, 0.14);
          text-align:right;
      ">
        <div style="font-size:14px; color:#9a6b15; letter-spacing:1px;">PAGE SIZE</div>
        <div style="margin-top:8px; font-size:28px; font-weight:800;">{{ page_size }}</div>
      </div>
    </div>

    {% for entry in entries %}
    <div style="
        margin-top: {{ 0 if loop.first else 18 }}px;
        border-radius: 26px;
        background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(247,250,252,0.96) 100%);
        border: 1px solid rgba(19,34,56,0.08);
        overflow:hidden;
        box-shadow: 0 12px 30px rgba(19,34,56,0.06);
    ">
      <div style="
          display:flex;
          justify-content:space-between;
          gap:18px;
          align-items:flex-start;
          padding: 22px 24px 18px;
          border-bottom: 1px solid rgba(19,34,56,0.06);
      ">
        <div>
          <div style="font-size:13px; color:#7b8798; letter-spacing:1.1px;">用户 {{ entry.index }}</div>
          <div style="margin-top:10px; font-size:30px; font-weight:800; line-height:1.2;">{{ entry.user_label }}</div>
          <div style="
              margin-top:10px;
              display:inline-block;
              padding:7px 12px;
              border-radius:999px;
              background:#eef2f7;
              color:#4b5d73;
              font-size:14px;
              font-weight:600;
          ">UID {{ entry.user_id }}</div>
        </div>
        <div style="
            padding: 10px 16px;
            border-radius: 999px;
            background: {{ entry.badge_bg }};
            color: {{ entry.badge_fg }};
            font-size: 15px;
            font-weight: 700;
            white-space: nowrap;
        ">{{ entry.badge_text }}</div>
      </div>

      <div style="padding: 20px 24px 24px;">
        <div style="display:flex; gap:16px;">
          <div style="
              flex:1;
              padding:14px 16px;
              border-radius:18px;
              background:#f5f7fb;
          ">
            <div style="font-size:13px; color:#6f7f92; letter-spacing:1px;">加入时间</div>
            <div style="margin-top:8px; font-size:19px; font-weight:700; line-height:1.45;">{{ entry.ban_time }}</div>
          </div>
          <div style="
              flex:1;
              padding:14px 16px;
              border-radius:18px;
              background:#f5f7fb;
          ">
            <div style="font-size:13px; color:#6f7f92; letter-spacing:1px;">过期时间</div>
            <div style="margin-top:8px; font-size:19px; font-weight:700; line-height:1.45;">{{ entry.expire_time }}</div>
          </div>
        </div>
        <div style="
            margin-top:16px;
            padding:18px 18px 16px;
            border-radius:20px;
            background: linear-gradient(135deg, rgba(20,184,166,0.08) 0%, rgba(255,255,255,0.94) 100%);
            border:1px solid rgba(20,184,166,0.10);
        ">
          <div style="font-size:13px; color:#0f766e; letter-spacing:1px;">封禁理由</div>
          <div style="margin-top:10px; font-size:18px; line-height:1.7; white-space:pre-wrap;">{{ entry.reason }}</div>
        </div>
      </div>
    </div>
    {% endfor %}

    <div style="
        margin-top: 24px;
        display:flex;
        justify-content:space-between;
        gap:18px;
        align-items:center;
        color:#6c7a8a;
        font-size:16px;
    ">
      <div>{{ pagination_hint }}</div>
      <div>Generated by astrbot_plugin_blacklist_tools</div>
    </div>
  </div>
</div>
"""
BLACKLIST_INFO_TEMPLATE = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    background: #f4f7fb;
  }
  body {
    min-width: 0;
  }
  *, *::before, *::after {
    box-sizing: border-box;
  }
</style>
<div style="
    width: 100%;
    padding: 40px;
    color: #132238;
    font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background:
      radial-gradient(circle at top left, rgba(255, 183, 77, 0.18), transparent 28%),
      radial-gradient(circle at bottom right, rgba(20, 184, 166, 0.16), transparent 26%),
      linear-gradient(180deg, #fbf7ef 0%, #f4f7fb 100%);
">
  <div style="
      width: 1120px;
      margin: 0 auto;
      background: rgba(255,255,255,0.84);
      border: 1px solid rgba(19,34,56,0.08);
      border-radius: 32px;
      padding: 34px 36px 30px;
      box-shadow: 0 28px 80px rgba(19,34,56,0.10);
  ">
    <div style="display:flex; justify-content:space-between; gap:20px; align-items:flex-start;">
      <div>
        <div style="
            display:inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            background:#132238;
            color:#fffaf2;
            font-size:14px;
            letter-spacing:1.2px;
        ">BLACKLIST PROFILE</div>
        <div style="margin-top:16px; font-size:40px; font-weight:800; line-height:1.2;">{{ user_label }}</div>
        <div style="
            margin-top:12px;
            display:inline-block;
            padding:8px 14px;
            border-radius:999px;
            background:#eef2f7;
            color:#4b5d73;
            font-size:15px;
            font-weight:700;
        ">UID {{ user_id }}</div>
      </div>
      <div style="
          padding: 10px 16px;
          border-radius: 999px;
          background: {{ badge_bg }};
          color: {{ badge_fg }};
          font-size: 15px;
          font-weight: 700;
          white-space: nowrap;
      ">{{ badge_text }}</div>
    </div>

    <div style="margin-top:22px; display:flex; gap:16px;">
      <div style="flex:1; padding:16px 18px; border-radius:18px; background:#f5f7fb;">
        <div style="font-size:13px; color:#6f7f92; letter-spacing:1px;">加入时间</div>
        <div style="margin-top:8px; font-size:20px; font-weight:700; line-height:1.45;">{{ ban_time }}</div>
      </div>
      <div style="flex:1; padding:16px 18px; border-radius:18px; background:#f5f7fb;">
        <div style="font-size:13px; color:#6f7f92; letter-spacing:1px;">过期时间</div>
        <div style="margin-top:8px; font-size:20px; font-weight:700; line-height:1.45;">{{ expire_time }}</div>
      </div>
    </div>

    <div style="
        margin-top:18px;
        padding:20px 20px 18px;
        border-radius:22px;
        background: linear-gradient(135deg, rgba(20,184,166,0.08) 0%, rgba(255,255,255,0.94) 100%);
        border:1px solid rgba(20,184,166,0.10);
    ">
      <div style="font-size:13px; color:#0f766e; letter-spacing:1px;">封禁理由</div>
      <div style="margin-top:10px; font-size:19px; line-height:1.75; white-space:pre-wrap;">{{ reason }}</div>
    </div>
  </div>
</div>
"""


@register(
    "astrbot_plugin_blacklist_tools",
    "piexian",
    "允许管理员和 LLM 将用户添加到黑名单中，阻止他们的消息，自动拉黑！",
    "1.6.1",
    "https://github.com/piexian/astrbot_plugin_blacklist_tools",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 黑名单最长时长
        self.max_blacklist_duration = config.get(
            "max_blacklist_duration", 1 * 24 * 60 * 60
        )
        # 是否允许永久黑名单
        self.allow_permanent_blacklist = config.get("allow_permanent_blacklist", True)
        # 是否向被拉黑用户显示拉黑状态
        self.show_blacklist_status = config.get("show_blacklist_status", False)
        # 黑名单提示消息
        self.blacklist_message = config.get("blacklist_message", "[连接已中断]")
        # 自动删除过期多久的黑名单
        self.auto_delete_expired_after = config.get("auto_delete_expired_after", 86400)
        # 是否允许拉黑管理员
        self.allow_blacklist_admin = config.get("allow_blacklist_admin", False)

        self.db = BlacklistDatabase(
            self,
            self.auto_delete_expired_after,
            legacy_db_paths=self._get_legacy_db_paths(),
        )

    def _get_legacy_db_paths(self) -> list[Path]:
        data_dir = StarTools.get_data_dir()
        paths = [data_dir / "blacklist.db"]
        for legacy_name in LEGACY_DATA_DIR_NAMES:
            paths.append(data_dir.parent / legacy_name / "blacklist.db")
        return list(dict.fromkeys(paths))

    def _should_notify_blacklisted_user(self) -> bool:
        return self.show_blacklist_status and bool(self.blacklist_message)

    def _build_blacklist_status_result(
        self, event: AstrMessageEvent
    ) -> MessageEventResult:
        return event.plain_result(self.blacklist_message).stop_event()

    def _parse_history_limit(
        self, limit: str, default: int = 5, max_limit: int = 20
    ) -> int:
        try:
            parsed = int(limit)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, max_limit))

    async def _resolve_user_display_name(
        self, event: AstrMessageEvent, user_id: str
    ) -> str:
        user_id = str(user_id)
        if user_id == str(event.get_sender_id()):
            sender_name = event.get_sender_name().strip()
            if sender_name:
                return sender_name

        if not event.get_group_id():
            return ""

        try:
            group = await event.get_group()
        except Exception as e:
            logger.debug(f"获取群成员信息失败，无法解析昵称 {user_id}: {e}")
            return ""

        if not group or not group.members:
            return ""

        for member in group.members:
            if str(member.user_id) != user_id:
                continue
            nickname = (member.nickname or "").strip()
            if nickname:
                return nickname
        return ""

    async def _format_user_label(self, event: AstrMessageEvent, user_id: str) -> str:
        user_id = str(user_id)
        display_name = await self._resolve_user_display_name(event, user_id)
        if display_name and display_name != user_id:
            return f"{display_name}({user_id})"
        return user_id

    @staticmethod
    def _sanitize_template_text(value: str | None, default: str) -> str:
        normalized = "" if value is None else str(value).strip()
        if not normalized:
            normalized = default
        return escape(normalized)

    def _build_blacklist_badge(self, expire_time: str | None) -> dict[str, str]:
        if not expire_time:
            return {
                "badge_text": "永久封禁",
                "badge_bg": "linear-gradient(135deg, #ffe6cf 0%, #fff4e8 100%)",
                "badge_fg": "#9a3412",
            }

        try:
            expire_dt = datetime.fromisoformat(expire_time)
        except Exception:
            return {
                "badge_text": "状态异常",
                "badge_bg": "linear-gradient(135deg, #e5e7eb 0%, #f8fafc 100%)",
                "badge_fg": "#475569",
            }

        if datetime.now() >= expire_dt:
            return {
                "badge_text": "已过期",
                "badge_bg": "linear-gradient(135deg, #e2e8f0 0%, #f8fafc 100%)",
                "badge_fg": "#475569",
            }

        return {
            "badge_text": "限时封禁",
            "badge_bg": "linear-gradient(135deg, #d9f99d 0%, #ecfccb 100%)",
            "badge_fg": "#3f6212",
        }

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        await self.db.initialize()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await self.db.terminate()

    def _format_datetime(
        self, iso_datetime_str, show_remaining=False, check_expire=False
    ):
        """统一格式化日期时间字符串
        Args:
            iso_datetime_str: ISO格式的日期时间字符串
            show_remaining: 是否显示剩余时间
            check_expire: 是否检查是否过期（仅对过期时间有效）
        """
        if not iso_datetime_str:
            return "永久"
        try:
            datetime_obj = datetime.fromisoformat(iso_datetime_str)
            formatted_time = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")

            if check_expire:
                if datetime.now() > datetime_obj:
                    return "已过期"

            if show_remaining:
                if datetime.now() > datetime_obj:
                    return "已过期"
                else:
                    remaining_time = datetime_obj - datetime.now()
                    days = remaining_time.days
                    hours, remainder = divmod(remaining_time.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    return (
                        f"{formatted_time} (剩余: {days}天 {hours}小时 {minutes}分钟)"
                    )
            else:
                return formatted_time
        except Exception as e:
            logger.error(f"格式化日期时间时出错：{e}")
            return "格式错误"

    def _build_pagination_hint(
        self, page: int, total_pages: int, page_size: int
    ) -> str:
        hints = []
        if page > 1:
            hints.append(f"上一页: /black ls {page - 1} {page_size}")
        if page < total_pages:
            hints.append(f"下一页: /black ls {page + 1} {page_size}")
        if not hints:
            hints.append("当前只有一页")
        hints.append("可用 /black ls <页码> <每页数量> 切换分页")
        return " | ".join(hints)

    async def _build_blacklist_entry(
        self,
        event: AstrMessageEvent,
        user: tuple[str, str, str | None, str | None],
        index: int,
        show_remaining: bool = False,
    ) -> dict[str, str | int]:
        user_id, ban_time, expire_time, reason = user
        user_label = await self._format_user_label(event, user_id)
        badge = self._build_blacklist_badge(expire_time)
        return {
            "index": index,
            "user_label": user_label or user_id,
            "user_id": str(user_id),
            "ban_time": self._format_datetime(ban_time, check_expire=False),
            "expire_time": self._format_datetime(
                expire_time,
                show_remaining=show_remaining,
                check_expire=True,
            ),
            "reason": reason or "未填写理由",
            **badge,
        }

    def _escape_blacklist_entry(
        self, entry: dict[str, str | int]
    ) -> dict[str, str | int]:
        return {
            **entry,
            "user_label": self._sanitize_template_text(
                str(entry["user_label"]), str(entry["user_id"])
            ),
            "user_id": self._sanitize_template_text(
                str(entry["user_id"]), str(entry["user_id"])
            ),
            "ban_time": self._sanitize_template_text(str(entry["ban_time"]), "未知"),
            "expire_time": self._sanitize_template_text(
                str(entry["expire_time"]), "永久"
            ),
            "reason": self._sanitize_template_text(str(entry["reason"]), "未填写理由"),
            "badge_text": self._sanitize_template_text(
                str(entry["badge_text"]), "状态未知"
            ),
        }

    def _build_blacklist_list_fallback_text(
        self,
        entries: list[dict[str, str | int]],
        total_count: int,
        page: int,
        total_pages: int,
        page_size: int,
        pagination_hint: str,
    ) -> str:
        lines = [
            "黑名单档案",
            "=" * 64,
            f"页码: {page}/{total_pages}",
            f"总数: {total_count}",
            f"每页: {page_size}",
            "",
        ]
        for entry in entries:
            lines.extend(
                [
                    f"[{entry['index']}] 用户: {entry['user_label']}",
                    f"UID: {entry['user_id']}",
                    f"状态: {entry['badge_text']}",
                    f"加入时间: {entry['ban_time']}",
                    f"过期时间: {entry['expire_time']}",
                    "封禁理由:",
                    str(entry["reason"]),
                    "-" * 64,
                ]
            )

        lines.append(pagination_hint)
        return "\n".join(lines)

    def _build_blacklist_info_fallback_text(self, entry: dict[str, str | int]) -> str:
        return "\n".join(
            [
                "黑名单详情",
                "=" * 48,
                f"用户: {entry['user_label']}",
                f"UID: {entry['user_id']}",
                f"状态: {entry['badge_text']}",
                f"加入时间: {entry['ban_time']}",
                f"过期时间: {entry['expire_time']}",
                "封禁理由:",
                str(entry["reason"]),
            ]
        )

    async def _render_blacklist_list_result(
        self,
        event: AstrMessageEvent,
        entries: list[dict[str, str | int]],
        total_count: int,
        page: int,
        total_pages: int,
        page_size: int,
    ) -> MessageEventResult:
        pagination_hint = self._build_pagination_hint(page, total_pages, page_size)
        html_entries = [self._escape_blacklist_entry(entry) for entry in entries]
        try:
            url = await self.html_render(
                BLACKLIST_LIST_TEMPLATE,
                {
                    "entries": html_entries,
                    "total_count": total_count,
                    "page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "pagination_hint": self._sanitize_template_text(
                        pagination_hint, "当前只有一页"
                    ),
                },
                options=BLACKLIST_IMAGE_OPTIONS,
            )
            if url:
                return event.image_result(url)
        except Exception as e:
            logger.warning(f"渲染黑名单列表 HTML 图片失败，回退文本图：{e}")

        result = self._build_blacklist_list_fallback_text(
            entries, total_count, page, total_pages, page_size, pagination_hint
        )
        image_data = await text_to_image(result)
        if image_data:
            return event.chain_result([Comp.Image.fromBase64(image_data)])
        return event.plain_result(result)

    async def _render_blacklist_info_result(
        self, event: AstrMessageEvent, entry: dict[str, str | int]
    ) -> MessageEventResult:
        html_entry = self._escape_blacklist_entry(entry)
        try:
            url = await self.html_render(
                BLACKLIST_INFO_TEMPLATE,
                html_entry,
                options=BLACKLIST_IMAGE_OPTIONS,
            )
            if url:
                return event.image_result(url)
        except Exception as e:
            logger.warning(f"渲染黑名单详情 HTML 图片失败，回退文本图：{e}")

        result = self._build_blacklist_info_fallback_text(entry)
        image_data = await text_to_image(result)
        if image_data:
            return event.chain_result([Comp.Image.fromBase64(image_data)])
        return event.plain_result(result)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=sys.maxsize - 1)
    async def on_all_message(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        try:
            if event.is_admin() and not self.allow_blacklist_admin:
                return

            if await self.db.is_user_blacklisted(sender_id):
                event.stop_event()
                if self._should_notify_blacklisted_user():
                    await event.send(MessageChain().message(self.blacklist_message))

        except Exception as e:
            logger.error(f"检查黑名单时出错：{e}")

    @filter.command_group("blacklist", alias=["black", "bl"])
    def blacklist():
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("ls")
    async def ls(self, event: AstrMessageEvent, page: int = 1, page_size: int = 10):
        """列出黑名单中的所有用户（支持分页）
        Args:
            page: 页码，从1开始
            page_size: 每页显示的数量
        """
        try:
            total_count = await self.db.get_blacklist_count()

            if total_count == 0:
                yield event.plain_result("黑名单为空。")
                return

            page_size = max(1, min(page_size, 20))
            total_pages = (total_count + page_size - 1) // page_size
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages

            users = await self.db.get_blacklist_users(page, page_size)
            item_offset = (page - 1) * page_size
            entries = [
                await self._build_blacklist_entry(event, user, index)
                for index, user in enumerate(users, start=item_offset + 1)
            ]
            yield await self._render_blacklist_list_result(
                event,
                entries,
                total_count,
                page,
                total_pages,
                page_size,
            )
        except Exception as e:
            logger.error(f"列出黑名单时出错：{e}")
            yield event.plain_result("列出黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("rm")
    async def rm(self, event: AstrMessageEvent, user_id: str):
        """从黑名单中移除用户"""
        try:
            user_label = await self._format_user_label(event, user_id)
            user = await self.db.get_user_info(user_id)

            if not user:
                yield event.plain_result(f"用户 {user_label} 不在黑名单中。")
                return

            if await self.db.remove_user(user_id):
                yield event.plain_result(f"用户 {user_label} 已从黑名单中移除。")
            else:
                yield event.plain_result("从黑名单移除用户时出错。")
        except Exception as e:
            logger.error(f"从黑名单移除用户 {user_id} 时出错：{e}")
            yield event.plain_result("从黑名单移除用户时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("add")
    async def add(
        self, event: AstrMessageEvent, user_id: str, duration: int = 0, reason: str = ""
    ):
        """添加用户到黑名单"""
        try:
            user_label = await self._format_user_label(event, user_id)
            ban_time = datetime.now().isoformat()
            expire_time = None

            if duration > 0:
                expire_time = (datetime.now() + timedelta(seconds=duration)).isoformat()

            if await self.db.add_user(user_id, ban_time, expire_time, reason):
                if duration > 0:
                    yield event.plain_result(
                        f"用户 {user_label} 已被加入黑名单，时长 {duration} 秒。"
                    )
                else:
                    yield event.plain_result(f"用户 {user_label} 已被永久加入黑名单。")
            else:
                yield event.plain_result("添加用户到黑名单时出错。")

        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            yield event.plain_result("添加用户到黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("clear")
    async def clear(self, event: AstrMessageEvent):
        """清空黑名单"""
        try:
            count = await self.db.get_blacklist_count()

            if count == 0:
                yield event.plain_result("黑名单已经为空。")
                return

            if await self.db.clear_blacklist():
                yield event.plain_result(f"黑名单已清空，共移除 {count} 个用户。")
            else:
                yield event.plain_result("清空黑名单时出错。")
        except Exception as e:
            logger.error(f"清空黑名单时出错：{e}")
            yield event.plain_result("清空黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("info")
    async def info(self, event: AstrMessageEvent, user_id: str):
        """查看特定用户的黑名单信息"""
        try:
            user_label = await self._format_user_label(event, user_id)
            user = await self.db.get_user_info(user_id)

            if not user:
                yield event.plain_result(f"用户 {user_label} 不在黑名单中。")
                return

            entry = await self._build_blacklist_entry(
                event, user, index=1, show_remaining=True
            )
            entry["user_label"] = user_label
            yield await self._render_blacklist_info_result(event, entry)
        except Exception as e:
            logger.error(f"查看用户 {user_id} 黑名单信息时出错：{e}")
            yield event.plain_result("查看用户黑名单信息时出错。")

    @filter.llm_tool(name="add_to_block_user")
    async def add_to_block_user(
        self,
        event: AstrMessageEvent,
        duration: str = "0",
        reason: str = "",
        confirm: bool = False,
    ) -> AsyncGenerator[MessageEventResult | str, None]:
        """
        Block a user. All messages from this user will be ignored immediately.
        Use this function when you decide to blacklist a user and cease all contact.

        Args:
            duration (string): The block duration in seconds. Use "0" to make it permanent.
            reason (string): The reason for blocking this user.
            confirm (boolean): Must be true when the user already has blacklist history and you still want to block again.
        """
        user_id = event.get_sender_id()
        try:
            # 在函数内部将字符串转换为整数 ---
            try:
                duration_sec = int(duration)
            except (ValueError, TypeError):
                # 如果LLM给了一个无法转换的字符串，则默认为0
                duration_sec = 0
                logger.warning(
                    f"LLM 工具 'block_user' 接收到无效的 duration '{duration}'，已默认使用 0 秒。"
                )
            # -----------------------------------------

            ban_time = datetime.now().isoformat()
            expire_time = None
            actual_duration = duration_sec
            history_count = await self.db.get_user_history_count(user_id)

            if history_count > 0 and not confirm:
                yield (
                    f"该用户已有 {history_count} 次历史封禁记录，本次不要直接封禁。"
                    "请先评估本次封禁程度。"
                    "如果仍需封禁，请再次调用 add_to_block_user 并传入 confirm=true。"
                    "你可以先调用 get_block_user_history(limit=5) 查看最近的封禁理由，再决定封禁时长。"
                )
                return

            # 如果不允许永久黑名单，则使用默认时长
            if duration_sec == 0 and not self.allow_permanent_blacklist:
                actual_duration = self.max_blacklist_duration

            # 超出使用最大时间
            if actual_duration > self.max_blacklist_duration:
                actual_duration = self.max_blacklist_duration

            if actual_duration > 0:
                expire_time = (
                    datetime.now() + timedelta(seconds=actual_duration)
                ).isoformat()

            if not await self.db.add_user(user_id, ban_time, expire_time, reason):
                yield event.plain_result("添加用户到黑名单时出错。")
                return

            if self._should_notify_blacklisted_user():
                yield self._build_blacklist_status_result(event)
            else:
                event.stop_event()
                yield

        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            yield event.plain_result("添加用户到黑名单时出错。")

    @filter.llm_tool(name="get_block_user_history")
    async def get_block_user_history(
        self, event: AstrMessageEvent, limit: str = "5"
    ) -> str:
        """
        View the current user's previous blacklist reasons in reverse chronological order.
        Use this before deciding how severe the next blacklist should be.

        Args:
            limit (string): Maximum number of history records to return. Default is "5".
        """
        user_id = event.get_sender_id()
        limit_num = self._parse_history_limit(limit)
        history, remaining = await self.db.get_user_history(user_id, limit_num)

        if not history:
            return "该用户没有历史封禁记录。"

        total_count = len(history) + remaining
        lines = [
            f"该用户共有 {total_count} 次历史封禁记录，以下按时间倒序展示最近 {len(history)} 条："
        ]
        for index, item in enumerate(history, start=1):
            ban_time, expire_time, reason = item
            expire_text = expire_time or "永久"
            reason_text = reason or "无"
            lines.append(
                f"{index}. 封禁时间: {ban_time} | 结束时间: {expire_text} | 理由: {reason_text}"
            )

        if remaining > 0:
            lines.append(
                f"还有 {remaining} 条更早的封禁理由未展示，如需查看更多，可提高 limit 后再次调用。"
            )

        return "\n".join(lines)
