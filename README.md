# AstrBot 黑名单工具插件

一个面向 AstrBot 的黑名单管理插件。管理员可以直接管理黑名单，LLM 也可以按工具调用规则执行封禁；被拉黑用户的消息会被统一拦截。

当前仓库信息：

- 插件名：`astrbot_plugin_blacklist_tools`
- 作者：`piexian`
- 仓库：`https://github.com/piexian/astrbot_plugin_blacklist_tools`
- 当前仓库基于 `https://github.com/ctrlkk/astrbot_plugin_blacklist_tools` 改版并持续维护。

## 功能特性

- 拦截所有消息类型，不再只限唤醒或命令消息。
- 支持临时封禁和永久封禁。
- 支持管理员命令：`add`、`rm`、`ls`、`info`、`clear`。
- 支持按配置决定是否向被拉黑用户显示提示语。
- `ls` 和 `info` 优先使用 AstrBot 的 `HTML + Jinja2` 文转图渲染，展示为现代化卡片；渲染失败时自动回退到文本图。
- 管理端展示会优先解析昵称，显示为 `昵称(用户ID)`。
- LLM 重复封禁采用二次确认机制：如果用户有封禁历史，会先提示查看历史并要求再次确认。
- 支持查询历史封禁理由，按时间倒序返回，默认显示最近 5 条。
- 使用 AstrBot 内置插件 KV 存储，不再依赖 SQLite。
- 启动时会自动迁移旧版 SQLite 数据，并在迁移完成后删除旧数据库文件。

## 配置项

在插件配置中可使用以下字段：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `max_blacklist_duration` | `86400` | 最大封禁时长，单位秒。LLM 或管理员传入更大值时会被截断到此上限。 |
| `allow_permanent_blacklist` | `true` | 是否允许永久封禁。为 `false` 时，传入 `0` 会自动改为最大封禁时长。 |
| `show_blacklist_status` | `false` | 是否向被拉黑用户发送提示消息。 |
| `blacklist_message` | `[连接已中断]` | 被拉黑用户收到的提示内容。仅在 `show_blacklist_status=true` 时生效。 |
| `auto_delete_expired_after` | `86400` | 过期黑名单在超出该秒数后自动从当前黑名单中清除。设为 `-1` 表示不自动删除。 |
| `allow_blacklist_admin` | `false` | 是否允许把管理员加入黑名单。 |

配置示例：

```yaml
max_blacklist_duration: 86400
allow_permanent_blacklist: true
show_blacklist_status: false
blacklist_message: "[连接已中断]"
auto_delete_expired_after: 86400
allow_blacklist_admin: false
```

## 管理员命令

所有命令都需要管理员权限，可使用 `/blacklist`、`/black` 或 `/bl` 前缀。

### 添加用户到黑名单

```text
/black add <用户ID> [时长(秒)] [原因]
```

示例：

```text
/black add 123456 3600 发送垃圾信息
/black add 123456 0 恶意攻击
/black add 123456
```

### 从黑名单中移除用户

```text
/black rm <用户ID>
```

### 查看黑名单列表

```text
/black ls [页码] [每页数量]
```

说明：

- 页码从 `1` 开始。
- 每页数量当前会被限制在 `1` 到 `20` 之间。

示例：

```text
/black ls
/black ls 2
/black ls 1 20
```

### 查看单个用户详情

```text
/black info <用户ID>
```

### 清空黑名单

```text
/black clear
```

## LLM 工具

### `add_to_block_user`

用于把当前触发事件的用户加入黑名单。

```python
add_to_block_user(duration="0", reason="", confirm=False)
```

参数说明：

- `duration`：字符串形式的封禁秒数，`"0"` 表示永久封禁。
- `reason`：封禁理由。
- `confirm`：当存在历史封禁记录且仍要继续封禁时，第二次调用必须传 `true`。

行为说明：

- 工具默认操作的是当前用户，不需要额外传 `user_id`。
- 如果当前用户已有封禁历史，且 `confirm=false`，工具不会立即封禁，而是先告知历史次数，并要求再次调用确认。
- 当 `show_blacklist_status=false` 时，工具会静默封禁并直接停止事件传播，不会额外向用户解释。

### `get_block_user_history`

用于查看当前用户历史封禁理由，供 LLM 判断本次封禁程度。

```python
get_block_user_history(limit="5")
```

参数说明：

- `limit`：最多返回多少条历史记录，默认 `5`，当前最大 `20`。

返回规则：

- 按封禁时间倒序返回最近记录。
- 如果历史记录超过 `limit`，返回结果会额外提示还有多少条未展示。

## 存储与迁移

插件当前使用 AstrBot 插件 KV 存储两类数据：

- `blacklist_entries`：当前黑名单。
- `blacklist_history`：历史封禁记录。

旧版 SQLite 迁移规则：

- 插件初始化时会自动检查旧版 `blacklist.db`。
- 如果发现旧数据库，会自动迁移到 KV。
- 迁移完成后会立即删除旧的 `blacklist.db`、`blacklist.db-wal`、`blacklist.db-shm`。
- 如果 KV 已经存在，也会继续清理残留的旧 SQLite 文件。

## 工作方式

1. 插件在消息入口检查发送者是否在黑名单中。
2. 命中黑名单后，消息会被直接拦截。
3. 如果启用了 `show_blacklist_status`，会向被拉黑用户发送 `blacklist_message`。
4. 临时封禁过期后将不再生效；如果配置了自动清理，会在指定延迟后从当前黑名单中移除。
5. 每次新增封禁都会写入历史记录，供后续 LLM 复核和人工查询。

## 注意事项

- 只有管理员可以使用黑名单管理命令。
- 默认不允许封禁管理员，除非将 `allow_blacklist_admin` 改为 `true`。
- 如果远端 `t2i` 渲染不可用，列表和详情会自动回退到文本图或纯文本响应。
