from os import path
import sys
from datetime import datetime, timedelta
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


@register(
    "astrbot_plugin_blacklist_tools",
    "ctrlkk",
    "允许管理员和 LLM 将用户添加到黑名单中，阻止他们的消息，自动拉黑！",
    "1.6",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        data_dir = StarTools.get_data_dir()
        self.db_path = path.join(data_dir, "blacklist.db")

        # 黑名单最长时长
        self.max_blacklist_duration = config.get(
            "max_blacklist_duration", 1 * 24 * 60 * 60
        )
        # 是否允许永久黑名单
        self.allow_permanent_blacklist = config.get("allow_permanent_blacklist", True)
        # 是否向被拉黑用户显示拉黑状态
        self.show_blacklist_status = config.get("show_blacklist_status", True)
        # 黑名单提示消息
        self.blacklist_message = config.get("blacklist_message", "[连接已中断]")
        # 自动删除过期多久的黑名单
        self.auto_delete_expired_after = config.get("auto_delete_expired_after", 86400)
        # 是否允许拉黑管理员
        self.allow_blacklist_admin = config.get("allow_blacklist_admin", False)

        self.db = BlacklistDatabase(self.db_path, self.auto_delete_expired_after)

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

    @filter.event_message_type(filter.EventMessageType.ALL, priority=sys.maxsize - 1)
    async def on_all_message(self, event: AstrMessageEvent):
        if not event.is_at_or_wake_command:
            return

        sender_id = event.get_sender_id()
        try:
            if event.is_admin() and not self.allow_blacklist_admin:
                return

            if await self.db.is_user_blacklisted(sender_id):
                event.stop_event()
                if not event.get_messages():
                    pass
                elif self.show_blacklist_status:
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

            # 计算分页参数
            total_pages = (total_count + page_size - 1) // page_size
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages

            users = await self.db.get_blacklist_users(page, page_size)

            result = "黑名单列表\n"
            result += "=" * 60 + "\n\n"

            result += f"{'ID':<20} {'加入时间':<20} {'过期时间':<20} {'原因':<20}\n"
            result += "-" * 80 + "\n"

            for user in users:
                user_id, ban_time, expire_time, reason = user
                ban_time_str = self._format_datetime(ban_time, check_expire=False)
                expire_time_str = self._format_datetime(expire_time, check_expire=True)
                reason_str = reason if reason else "无"
                result += f"{user_id:<20} {ban_time_str:<20} {expire_time_str:<20} {reason_str:<20}\n"

            result += "-" * 80 + "\n"
            result += f"第 {page}/{total_pages} 页，共 {total_count} 条记录\n"
            result += f"每页显示 {page_size} 条记录\n"

            if page > 1:
                result += f"使用 `/black ls {page - 1} {page_size}` 查看上一页\n"
            if page < total_pages:
                result += f"使用 `/black ls {page + 1} {page_size}` 查看下一页\n"

            image_data = await text_to_image(result)
            if image_data:
                yield event.chain_result([Comp.Image.fromBase64(image_data)])
            else:
                yield event.plain_result(result)
        except Exception as e:
            logger.error(f"列出黑名单时出错：{e}")
            yield event.plain_result("列出黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("rm")
    async def rm(self, event: AstrMessageEvent, user_id: str):
        """从黑名单中移除用户"""
        try:
            user = await self.db.get_user_info(user_id)

            if not user:
                yield event.plain_result(f"用户 {user_id} 不在黑名单中。")
                return

            if await self.db.remove_user(user_id):
                yield event.plain_result(f"用户 {user_id} 已从黑名单中移除。")
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
            ban_time = datetime.now().isoformat()
            expire_time = None

            if duration > 0:
                expire_time = (datetime.now() + timedelta(seconds=duration)).isoformat()

            if await self.db.add_user(user_id, ban_time, expire_time, reason):
                if duration > 0:
                    yield event.plain_result(
                        f"用户 {user_id} 已被加入黑名单，时长 {duration} 秒。"
                    )
                else:
                    yield event.plain_result(f"用户 {user_id} 已被永久加入黑名单。")
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
            user = await self.db.get_user_info(user_id)

            if not user:
                yield event.plain_result(f"用户 {user_id} 不在黑名单中。")
                return

            user_id, ban_time, expire_time, reason = user
            ban_time_str = self._format_datetime(ban_time, check_expire=False)
            expire_time_str = self._format_datetime(
                expire_time, show_remaining=True, check_expire=True
            )
            reason_str = reason if reason else "无"

            result = f"用户 {user_id} 的黑名单信息：\n"
            result += "=" * 40 + "\n"
            result += f"加入时间: {ban_time_str}\n"
            result += f"过期时间: {expire_time_str}\n"
            result += f"原因: {reason_str}\n"

            image_data = await text_to_image(result)
            if image_data:
                yield event.chain_result([Comp.Image.fromBase64(image_data)])
            else:
                yield event.plain_result(result)
        except Exception as e:
            logger.error(f"查看用户 {user_id} 黑名单信息时出错：{e}")
            yield event.plain_result("查看用户黑名单信息时出错。")



    @filter.llm_tool(name="block_user")
    async def add_to_block_user(
        self, event: AstrMessageEvent, duration: str = "0", reason: str = ""
    ) -> AsyncGenerator[MessageEventResult, None]:
        """
        Block a user. All messages from this user will be ignored immediately.
        Use this function when you decide to blacklist a user and cease all contact.

        Args:
            duration (string): The block duration in seconds. Use "0" to make it permanent.
            reason (string): The reason for blocking this user.
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

            await self.db.add_user(user_id, ban_time, expire_time, reason)

            # --- 关键修改：使用 yield event.plain_result ---
            if actual_duration > 0:
                yield event.plain_result(f"用户 {user_id} 已被加入黑名单，时长 {actual_duration} 秒。")
            else:
                yield event.plain_result(f"用户 {user_id} 已被永久加入黑名单。")

        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            yield event.plain_result("添加用户到黑名单时出错。")
