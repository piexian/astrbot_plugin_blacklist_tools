import aiosqlite
from datetime import datetime, timedelta
from astrbot.api import logger


class BlacklistDatabase:
    def __init__(self, db_path: str, auto_delete_expired_after: int = -1):
        self.db_path = db_path
        self._db = None
        self.auto_delete_expired_after = auto_delete_expired_after

    async def initialize(self):
        """初始化数据库连接"""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA cache_size=10000")
        await self._init_db()

    async def terminate(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    async def _init_db(self):
        """初始化数据库，创建黑名单表"""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id TEXT PRIMARY KEY,
                ban_time TEXT NOT NULL,
                expire_time TEXT,
                reason TEXT
            )
        """)
        await self._db.commit()

    async def is_user_blacklisted(self, user_id: str) -> bool:
        """检查用户是否在黑名单中，如果过期则自动移除"""
        try:
            cursor = await self._db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (user_id,)
            )
            user = await cursor.fetchone()

            if user:
                expire_time = user[2]
                if expire_time:
                    expire_datetime = datetime.fromisoformat(expire_time)
                    now = datetime.now()
                    if now > expire_datetime:
                        if not self.auto_delete_expired_after == -1:
                            delete_time = expire_datetime + timedelta(
                                seconds=self.auto_delete_expired_after
                            )
                            if now > delete_time:
                                await self.remove_user(user_id)
                        return False
                    else:
                        logger.info(f"用户 {user_id} 在黑名单中，消息已被阻止")
                        return True
                else:
                    logger.info(f"用户 {user_id} 在永久黑名单中，消息已被阻止")
                    return True
            return False
        except Exception as e:
            logger.error(f"检查黑名单时出错：{e}")
            return False

    async def get_blacklist_count(self) -> int:
        """获取黑名单中的用户数量"""
        try:
            cursor = await self._db.execute("SELECT COUNT(*) FROM blacklist")
            return (await cursor.fetchone())[0]
        except Exception as e:
            logger.error(f"获取黑名单数量时出错：{e}")
            return 0

    async def get_blacklist_users(self, page: int = 1, page_size: int = 10):
        """获取黑名单用户列表（支持分页）"""
        try:
            offset = (page - 1) * page_size
            cursor = await self._db.execute(
                "SELECT * FROM blacklist ORDER BY ban_time DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            )
            return await cursor.fetchall()
        except Exception as e:
            logger.error(f"获取黑名单列表时出错：{e}")
            return []

    async def get_user_info(self, user_id: str):
        """获取特定用户的黑名单信息"""
        try:
            cursor = await self._db.execute(
                "SELECT * FROM blacklist WHERE user_id = ?", (user_id,)
            )
            return await cursor.fetchone()
        except Exception as e:
            logger.error(f"获取用户 {user_id} 黑名单信息时出错：{e}")
            return None

    async def add_user(
        self, user_id: str, ban_time: str, expire_time: str = None, reason: str = ""
    ):
        """添加用户到黑名单"""
        try:
            await self._db.execute(
                """INSERT OR REPLACE INTO blacklist (user_id, ban_time, expire_time, reason)
                VALUES (?, ?, ?, ?)""",
                (user_id, ban_time, expire_time, reason),
            )
            await self._db.commit()
            return True
        except Exception as e:
            logger.error(f"添加用户 {user_id} 到黑名单时出错：{e}")
            return False

    async def remove_user(self, user_id: str):
        """从黑名单中移除用户"""
        try:
            await self._db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await self._db.commit()
            return True
        except Exception as e:
            logger.error(f"从黑名单移除用户 {user_id} 时出错：{e}")
            return False

    async def clear_blacklist(self):
        """清空黑名单"""
        try:
            await self._db.execute("DELETE FROM blacklist")
            await self._db.commit()
            return True
        except Exception as e:
            logger.error(f"清空黑名单时出错：{e}")
            return False
