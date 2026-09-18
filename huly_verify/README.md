# Huly 连接验证（最小脚本）

验证你的自部署 Huly 实例能否：连得上、列出项目、按项目查到 issue（bug）。

## 1. 安装依赖

```bash
cd huly_verify
npm install
```

## 2. 配置连接信息（用环境变量，别写死凭据）

PowerShell：

```powershell
$env:HULY_URL = "http://你的huly地址:8087"      # transactor 地址
$env:HULY_WORKSPACE = "你的工作区名"
# 二选一：
$env:HULY_TOKEN = "你的token"
# 或
$env:HULY_EMAIL = "邮箱"; $env:HULY_PASSWORD = "密码"
```

> Token 在 Huly 桌面端：设置 → Integrations → API tokens 生成。

## 3. 运行

```bash
npm run verify
```

## 看什么

- `✅ 连接成功` → 连接和认证 OK
- `项目数：N` → 能列出项目
- 每个项目的 `X 个 issue` 和 `样例字段` → 确认能拿到 bug 数据，以及字段名（title/status/priority/assignee），这是后面映射禅道字段的依据

## 如果报错

把报错原文发我，常见是：URL 没带端口、workspace 名不对、token 没权限。
