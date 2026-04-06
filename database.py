import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from astrbot.api import logger
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin

BLACKLIST_KV_KEY = "blacklist_entries"
BLACKLIST_HISTORY_KV_KEY = "blacklist_history"
BlacklistEntry = dict[str, str | None]
BlacklistHistoryEntry = dict[str, str | None]


class BlacklistDatabase:
    def __init__(
        self,
        plugin: PluginKVStoreMixin,
        auto_delete_expired_after: int = -1,
        legacy_db_paths: list[Path] | None = None,
    ):
        self.plugin = plugin
        self.auto_delete_expired_after = auto_delete_expired_after
        self.legacy_db_paths = [Path(path) for path in (legacy_db_paths or [])]
        self._blacklist: dict[str, BlacklistEntry] = {}
        self._history: dict[str, list[BlacklistHistoryEntry]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self):
        """初始化 KV 存储，并在需要时迁移旧版 SQLite 数据。"""
        stored_entries = await self.plugin.get_kv_data(BLACKLIST_KV_KEY, None)
        stored_history = await self.plugin.get_kv_data(BLACKLIST_HISTORY_KV_KEY, None)

        if isinstance(stored_entries, dict) or isinstance(stored_history, dict):
            self._blacklist = self._normalize_blacklist(
                stored_entries if isinstance(stored_entries, dict) else {}
            )
            self._history = self._normalize_history(
                stored_history if isinstance(stored_history, dict) else {}
            )
            if not self._history and self._blacklist:
                self._history = self._build_history_from_blacklist(self._blacklist)
                await self._save_history()
            if self._blacklist != stored_entries:
                await self._save_blacklist()
            self._cleanup_legacy_sqlite_files()
            return

        if stored_entries is not None:
            logger.warning("黑名单 KV 数据格式异常，将尝试迁移旧版 SQLite 数据。")

        migrated = await self._migrate_legacy_sqlite()
        if migrated:
            return

        self._blacklist = {}
        self._history = {}
        await self._save_blacklist()
        await self._save_history()

    async def terminate(self):
        """KV 存储无需显式关闭。"""

    async def is_user_blacklisted(self, user_id: str) -> bool:
        """检查用户是否在黑名单中，如果过期则按配置处理。"""
        user_id = str(user_id)
        async with self._lock:
            user = self._blacklist.get(user_id)
            if not user:
                return False

            expire_time = user.get("expire_time")
            if not expire_time:
                logger.info(f"用户 {user_id} 在永久黑名单中，消息已被阻止")
                return True

            try:
                expire_datetime = datetime.fromisoformat(expire_time)
            except ValueError:
                logger.warning(f"用户 {user_id} 的过期时间格式异常，已视为未过期")
                return True

            now = datetime.now()
            if now <= expire_datetime:
                logger.info(f"用户 {user_id} 在黑名单中，消息已被阻止")
                return True

            if self.auto_delete_expired_after != -1:
                delete_time = expire_datetime + timedelta(
                    seconds=self.auto_delete_expired_after
                )
                if now > delete_time:
                    self._blacklist.pop(user_id, None)
                    await self._save_blacklist()
            return False

    async def get_blacklist_count(self) -> int:
        """获取黑名单中的用户数量。"""
        async with self._lock:
            return len(self._blacklist)

    async def get_blacklist_users(self, page: int = 1, page_size: int = 10):
        """获取黑名单用户列表（支持分页）。"""
        async with self._lock:
            offset = max(page - 1, 0) * page_size
            users = self._sorted_users()
            return users[offset : offset + page_size]

    async def get_user_info(self, user_id: str):
        """获取特定用户的黑名单信息。"""
        user_id = str(user_id)
        async with self._lock:
            user = self._blacklist.get(user_id)
            if not user:
                return None
            return (
                user_id,
                user.get("ban_time") or "",
                user.get("expire_time"),
                user.get("reason") or "",
            )

    async def add_user(
        self, user_id: str, ban_time: str, expire_time: str = None, reason: str = ""
    ):
        """添加用户到黑名单。"""
        user_id = str(user_id)
        async with self._lock:
            self._blacklist[user_id] = {
                "ban_time": str(ban_time),
                "expire_time": str(expire_time) if expire_time else None,
                "reason": str(reason or ""),
            }
            self._history.setdefault(user_id, []).append(
                {
                    "ban_time": str(ban_time),
                    "expire_time": str(expire_time) if expire_time else None,
                    "reason": str(reason or ""),
                }
            )
            await self._save_blacklist()
            await self._save_history()
            return True

    async def remove_user(self, user_id: str):
        """从黑名单中移除用户。"""
        user_id = str(user_id)
        async with self._lock:
            self._blacklist.pop(user_id, None)
            await self._save_blacklist()
            return True

    async def clear_blacklist(self):
        """清空黑名单。"""
        async with self._lock:
            self._blacklist.clear()
            await self._save_blacklist()
            return True

    async def _save_blacklist(self) -> None:
        await self.plugin.put_kv_data(BLACKLIST_KV_KEY, self._blacklist)

    async def _save_history(self) -> None:
        await self.plugin.put_kv_data(BLACKLIST_HISTORY_KV_KEY, self._history)

    async def get_user_history_count(self, user_id: str) -> int:
        user_id = str(user_id)
        async with self._lock:
            return len(self._history.get(user_id, []))

    async def get_user_history(
        self, user_id: str, limit: int = 5
    ) -> tuple[list[tuple[str, str | None, str]], int]:
        user_id = str(user_id)
        limit = max(1, limit)
        async with self._lock:
            history = self._sorted_history(self._history.get(user_id, []))
            shown = history[:limit]
            remaining = max(len(history) - limit, 0)
            return shown, remaining

    def _normalize_blacklist(self, entries: dict) -> dict[str, BlacklistEntry]:
        normalized: dict[str, BlacklistEntry] = {}
        for raw_user_id, raw_entry in entries.items():
            if not isinstance(raw_entry, dict):
                continue
            user_id = str(raw_user_id)
            normalized[user_id] = {
                "ban_time": str(raw_entry.get("ban_time") or ""),
                "expire_time": (
                    str(raw_entry.get("expire_time"))
                    if raw_entry.get("expire_time")
                    else None
                ),
                "reason": str(raw_entry.get("reason") or ""),
            }
        return normalized

    def _normalize_history(
        self, entries: dict
    ) -> dict[str, list[BlacklistHistoryEntry]]:
        normalized: dict[str, list[BlacklistHistoryEntry]] = {}
        for raw_user_id, raw_items in entries.items():
            if not isinstance(raw_items, list):
                continue
            user_id = str(raw_user_id)
            normalized[user_id] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                normalized[user_id].append(
                    {
                        "ban_time": str(item.get("ban_time") or ""),
                        "expire_time": (
                            str(item.get("expire_time"))
                            if item.get("expire_time")
                            else None
                        ),
                        "reason": str(item.get("reason") or ""),
                    }
                )
        return normalized

    def _sorted_users(self) -> list[tuple[str, str, str | None, str]]:
        users = [
            (
                user_id,
                entry.get("ban_time") or "",
                entry.get("expire_time"),
                entry.get("reason") or "",
            )
            for user_id, entry in self._blacklist.items()
        ]
        users.sort(key=lambda item: item[1], reverse=True)
        return users

    def _sorted_history(
        self, history: list[BlacklistHistoryEntry]
    ) -> list[tuple[str, str | None, str]]:
        items = [
            (
                entry.get("ban_time") or "",
                entry.get("expire_time"),
                entry.get("reason") or "",
            )
            for entry in history
        ]
        items.sort(key=lambda item: item[0], reverse=True)
        return items

    def _build_history_from_blacklist(
        self, blacklist: dict[str, BlacklistEntry]
    ) -> dict[str, list[BlacklistHistoryEntry]]:
        return {
            user_id: [
                {
                    "ban_time": entry.get("ban_time") or "",
                    "expire_time": entry.get("expire_time"),
                    "reason": entry.get("reason") or "",
                }
            ]
            for user_id, entry in blacklist.items()
        }

    async def _migrate_legacy_sqlite(self) -> bool:
        merged_entries: dict[str, BlacklistEntry] = {}
        migrated_paths: list[Path] = []

        for db_path in self.legacy_db_paths:
            if not db_path.exists():
                continue
            try:
                entries = self._read_sqlite_entries(db_path)
            except Exception as e:
                logger.error(f"读取旧版黑名单数据库失败 {db_path}: {e}")
                continue

            for user_id, entry in entries.items():
                current = merged_entries.get(user_id)
                if not current or (entry.get("ban_time") or "") >= (
                    current.get("ban_time") or ""
                ):
                    merged_entries[user_id] = entry

            migrated_paths.append(db_path)

        if not migrated_paths:
            return False

        self._blacklist = self._normalize_blacklist(merged_entries)
        self._history = self._build_history_from_blacklist(self._blacklist)
        await self._save_blacklist()
        await self._save_history()

        for db_path in migrated_paths:
            self._delete_legacy_db_files(db_path)

        logger.info(
            f"黑名单数据已从 SQLite 迁移到 AstrBot KV，共 {len(self._blacklist)} 条记录。"
        )
        return True

    def _read_sqlite_entries(self, db_path: Path) -> dict[str, BlacklistEntry]:
        entries: dict[str, BlacklistEntry] = {}
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = conn.execute(
                "SELECT user_id, ban_time, expire_time, reason FROM blacklist"
            )
            for row in cursor.fetchall():
                user_id, ban_time, expire_time, reason = row
                entries[str(user_id)] = {
                    "ban_time": str(ban_time or ""),
                    "expire_time": str(expire_time) if expire_time else None,
                    "reason": str(reason or ""),
                }
        finally:
            conn.close()
        return entries

    def _delete_legacy_db_files(self, db_path: Path) -> None:
        for suffix in ("", "-wal", "-shm"):
            target = (
                db_path if not suffix else db_path.with_name(f"{db_path.name}{suffix}")
            )
            try:
                if target.exists():
                    target.unlink()
                    logger.info(f"已删除旧版黑名单数据库文件: {target}")
            except Exception as e:
                logger.warning(f"删除旧版黑名单数据库文件失败 {target}: {e}")

    def _cleanup_legacy_sqlite_files(self) -> None:
        for db_path in self.legacy_db_paths:
            if db_path.exists():
                self._delete_legacy_db_files(db_path)
