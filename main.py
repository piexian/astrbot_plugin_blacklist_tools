from os import path
import sys
import aiosqlite
from datetime import datetime, timedelta
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_tools import StarTools
from .utils.text_to_image import text_to_image


@register(
    "astrbot_plugin_blacklist_tools",
    "ctrlkk",
    "允许管理员和 LLM 将用户添加到黑名单中，阻止他们的消息，自动拉黑！",
    "1.1",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        data_dir = StarTools.get_data_dir()
        self.db_path = path.join(data_dir, "blacklist.db")
        self.db = None

        # 黑名单最长时长
        self.max_blacklist_duration = config.get(
            "max_blacklist_duration", 1 * 24 * 60 * 60
        )
        # 是否允许永久黑名单
        self.allow_permanent_blacklist = config.get("allow_permanent_blacklist", True)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.db = await aiosqlite.connect(self.db_path)
        # 增加缓存大小
        await self.db.execute("PRAGMA cache_size = -10000")
        await self._init_db()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if self.db:
            await self.db.close()
            self.db = None

    async def _init_db(self):
        """初始化数据库，创建黑名单表"""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id TEXT PRIMARY KEY,
                ban_time TEXT NOT NULL,
                expire_time TEXT,
                reason TEXT
            )
        """)
        await self.db.commit()

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

    @filter.event_message_type(filter.EventMessageType.ALL, property=sys.maxsize - 1)
    async def on_all_message(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        try:
            # 检查用户是否在黑名单中
            cursor = await self.db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (sender_id,)
            )
            user = await cursor.fetchone()

            if user:
                expire_time = user[2]
                if expire_time:
                    expire_datetime = datetime.fromisoformat(expire_time)
                    if datetime.now() > expire_datetime:
                        await self.db.execute(
                            "DELETE FROM blacklist WHERE user_id = ?", (sender_id,)
                        )
                        await self.db.commit()
                        logger.info(f"用户 {sender_id} 的黑名单已过期，已自动移除")
                    else:
                        logger.info(f"用户 {sender_id} 在黑名单中，消息已被阻止")
                        event.stop_event()
                else:
                    logger.info(f"用户 {sender_id} 在永久黑名单中，消息已被阻止")
                    event.stop_event()
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
            cursor = await self.db.execute("SELECT COUNT(*) FROM blacklist")
            total_count = (await cursor.fetchone())[0]

            if total_count == 0:
                yield event.plain_result("黑名单为空。")
                return

            # 计算分页参数
            offset = (page - 1) * page_size
            total_pages = (total_count + page_size - 1) // page_size
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages

            offset = (page - 1) * page_size

            cursor = await self.db.execute(
                "SELECT * FROM blacklist ORDER BY ban_time DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            )
            users = await cursor.fetchall()

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
            cursor = await self.db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (user_id,)
            )
            user = await cursor.fetchone()

            if not user:
                yield event.plain_result(f"用户 {user_id} 不在黑名单中。")
                return

            await self.db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await self.db.commit()

            logger.info(f"用户 {user_id} 已从黑名单中移除")
            yield event.plain_result(f"用户 {user_id} 已从黑名单中移除。")
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
            actual_duration = duration

            # 如果不允许永久黑名单，则使用默认时长
            if duration == 0 and not self.allow_permanent_blacklist:
                actual_duration = self.max_blacklist_duration

            # 超出使用最大时间
            if actual_duration > self.max_blacklist_duration:
                actual_duration = self.max_blacklist_duration

            if actual_duration > 0:
                expire_time = (
                    datetime.now() + timedelta(seconds=actual_duration)
                ).isoformat()

            await self.db.execute(
                """INSERT OR REPLACE INTO blacklist (user_id, ban_time, expire_time, reason)
                VALUES (?, ?, ?, ?)""",
                (user_id, ban_time, expire_time, reason),
            )
            await self.db.commit()

            if actual_duration > 0:
                logger.info(
                    f"用户 {user_id} 已被加入黑名单，时长 {actual_duration} 秒，原因：{reason}"
                )
                yield event.plain_result(
                    f"用户 {user_id} 已被加入黑名单，时长 {actual_duration} 秒。"
                )

            else:
                logger.info(f"用户 {user_id} 已被永久加入黑名单，原因：{reason}")
                yield event.plain_result(f"用户 {user_id} 已被永久加入黑名单。")

        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            yield event.plain_result("添加用户到黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("clear")
    async def clear(self, event: AstrMessageEvent):
        """清空黑名单"""
        try:
            cursor = await self.db.execute("SELECT COUNT(*) FROM blacklist")
            count = (await cursor.fetchone())[0]

            if count == 0:
                yield event.plain_result("黑名单已经为空。")
                return

            await self.db.execute("DELETE FROM blacklist")
            await self.db.commit()

            logger.info(f"黑名单已清空，共移除 {count} 个用户")
            yield event.plain_result(f"黑名单已清空，共移除 {count} 个用户。")
        except Exception as e:
            logger.error(f"清空黑名单时出错：{e}")
            yield event.plain_result("清空黑名单时出错。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @blacklist.command("info")
    async def info(self, event: AstrMessageEvent, user_id: str):
        """查看特定用户的黑名单信息"""
        try:
            cursor = await self.db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (user_id,)
            )
            user = await cursor.fetchone()

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

    @filter.llm_tool(name="add_to_blacklist")
    async def add_to_blacklist(
        self, event: AstrMessageEvent, user_id: str, duration: int = 0, reason: str = ""
    ) -> MessageEventResult:
        """
        Add a user to the blacklist. The user's messages will be ignored.
        Use this when you've completely lost goodwill toward the user or no longer wish to receive messages from them.
        Args:
            user_id(string): The ID of the user to be added to the blacklist
            duration(number): The duration of the blacklist in seconds. Set to 0 for permanent blacklist
            reason(string): The reason for adding the user to the blacklist
        """
        try:
            ban_time = datetime.now().isoformat()
            expire_time = None
            actual_duration = duration

            # 如果不允许永久黑名单，则使用默认时长
            if duration == 0 and not self.allow_permanent_blacklist:
                actual_duration = self.max_blacklist_duration

            # 超出使用最大时间
            if actual_duration > self.max_blacklist_duration:
                actual_duration = self.max_blacklist_duration

            if actual_duration > 0:
                expire_time = (
                    datetime.now() + timedelta(seconds=actual_duration)
                ).isoformat()

            await self.db.execute(
                """INSERT OR REPLACE INTO blacklist (user_id, ban_time, expire_time, reason)
                VALUES (?, ?, ?, ?)""",
                (user_id, ban_time, expire_time, reason),
            )
            await self.db.commit()

            if actual_duration > 0:
                logger.info(
                    f"用户 {user_id} 已被加入黑名单，时长 {actual_duration} 秒，原因：{reason}"
                )
                return f"用户 {user_id} 已被加入黑名单。"

            else:
                logger.info(f"用户 {user_id} 已被永久加入黑名单，原因：{reason}")
                return f"用户 {user_id} 已被永久加入黑名单。"

        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            return "添加用户到黑名单时出错"

    @filter.llm_tool(name="remove_from_blacklist")
    async def remove_from_blacklist(
        self, event: AstrMessageEvent, user_id: str
    ) -> MessageEventResult:
        """
        Remove a user from the blacklist.
        Args:
            user_id(string): The ID of the user to be removed from the blacklist
        """
        try:
            cursor = await self.db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (user_id,)
            )
            user = await cursor.fetchone()

            if not user:
                return f"用户 {user_id} 不在黑名单中。"

            await self.db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await self.db.commit()

            logger.info(f"用户 {user_id} 已从黑名单中移除")
            return f"用户 {user_id} 已从黑名单中移除。"
        except Exception as e:
            logger.error(f"从黑名单移除用户 {user_id} 时出错：{e}")
            return MessageEventResult().message("从黑名单移除用户时出错")
