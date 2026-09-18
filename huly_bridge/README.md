# Huly Bridge（Huly 边车）

把 Huly 的 TypeScript 客户端包一层 REST 接口，输出与禅道相同的字段形状，供 AstrBot 插件（Python）直接调用。

## 架构

```
AstrBot 插件 (Python, httpx) --REST--> 本边车 (Node + api-client) --WebSocket--> Huly transactor
```

边车负责：连接/认证 Huly、把 Issue/Project/Employee 归一化成禅道字段（`id/title/status/severity/pri/openedBy/openedDate/assignedTo/moduleTitle/...`，status 归一化为 `active/resolved/closed`）。Python 侧只换传输层，报表逻辑与渲染零改动。

## 1. 安装

```bash
cd huly_bridge
npm install
```

## 2. 配置（环境变量，别写死凭据）

PowerShell：

```powershell
$env:HULY_URL = "http://你的huly地址:8087"      # transactor 地址
$env:HULY_WORKSPACE = "你的工作区名"
$env:HULY_TOKEN = "你的token"                    # 或 HULY_EMAIL + HULY_PASSWORD
$env:BRIDGE_PORT = "8600"                        # 可选，默认 8600
$env:BRIDGE_TOKEN = "边车自身的访问密钥"          # 可选，设置后插件须带同名 X-Bridge-Token 头
```

> Huly Token 在桌面端：设置 → Integrations → API tokens 生成。

## 3. 启动

```bash
npm start
```

## 4. 接口（输出禅道字段形状）

| 接口 | 说明 |
| --- | --- |
| `GET /health` | 连通性 + 认证状态（`{ok, auth}`） |
| `GET /projects` | `[{id, identifier, name, kind:"project"}]`；`id` = `identifier` = 项目字符串标识（如 `5092`、`509南昌`） |
| `GET /users` | `{任意person引用: 真名}` 映射（覆盖 Person._id / SocialIdentity._id / personUuid） |
| `GET /projects/:identifier/bugs` | 该项目的缺陷列表，字段为禅道形状：`id/key/title/status/severity/pri/assignedTo/openedBy/openedDate/resolvedBy/resolvedDate/module/moduleTitle` |

`:identifier` 是 Huly 项目字符串标识（URL 需百分号编码中文），不是数字。

**归一化规则（按真实 Huly 0.7.x 数据校准）：**

- `id` = issue 项目内序号（`number`），`key` = `identifier-number`（如 `5093-2`）
- `status`：按 `IssueStatus.category`（`task:statusCategory:*`）归一化——`Won`→`resolved`、`Lost`→`closed`、其余（`UnStarted`/`ToDo`/`Active`）→`active`
- `severity`/`pri`：由 `priority` 数字映射（`0/1`→S4、`2`→S3、`3`→S2、`4`(Urgent)→S1），Huly 无独立 severity 字段
- `openedBy`/`assignedTo`：查 Employee/SocialIdentity 换真名，逗号拼接已清洗（`侯,琛`→`侯琛`）
- `openedDate`：`createdOn` 毫秒时间戳转 `YYYY-MM-DD HH:MM:SS`
- `resolvedBy`/`resolvedDate`：Huly 无标准字段，返回空，由 Python 侧快照逻辑补齐
- `module`/`moduleTitle`：来自 `Component`（组件）；未设置时为空

## 5. 与 Python 侧对接

插件配置改为边车地址 + 可选密钥，无需 Huly 凭据：

- `huly_bridge_url`：例如 `http://127.0.0.1:8600`
- `huly_bridge_token`：与边车 `BRIDGE_TOKEN` 一致（可选）

## 如果报错

把报错原文贴回。常见：URL 没带端口、workspace 名不对、token 没权限、`@hcengineering/*` 版本与实例不匹配。
