/**
 * Huly 连接与数据验证脚本（最小版）。
 *
 * 目的：确认你的自部署 Huly 实例能连上、能列出项目、能按项目查到 issue（bug）。
 * 用法见本目录 README。
 */
import { connect } from "@hcengineering/api-client";
import tracker from "@hcengineering/tracker";
import core from "@hcengineering/core";

// —— 从环境变量读取连接信息（不要写死凭据）——
const url = process.env.HULY_URL || "http://localhost:8087";
const workspace = process.env.HULY_WORKSPACE || "";
const token = process.env.HULY_TOKEN || "";
const email = process.env.HULY_EMAIL || "";
const password = process.env.HULY_PASSWORD || "";

if (!workspace) {
  console.error("缺少 HULY_WORKSPACE 环境变量");
  process.exit(1);
}
if (!token && !(email && password)) {
  console.error("请提供 HULY_TOKEN，或 HULY_EMAIL + HULY_PASSWORD");
  process.exit(1);
}

const options = token
  ? { token, workspace }
  : { email, password, workspace };

console.log(`连接 ${url}，workspace=${workspace} ...`);

const client = await connect(url, options);
console.log("✅ 连接成功");

// 列出所有项目（tracker.class.Project）
const projects = await client.findAll(tracker.class.Project, {});
console.log(`\n项目数：${projects.length}`);
for (const p of projects.slice(0, 20)) {
  console.log(`  - ${p.identifier ?? ""}  ${p.name}  (id=${p._id})`);
}

// 对每个项目统计 issue 数，并抽样看字段
console.log("\n按项目查询 issue：");
for (const p of projects.slice(0, 5)) {
  const issues = await client.findAll(tracker.class.Issue, { space: p._id });
  console.log(`  ${p.name}: ${issues.length} 个 issue`);
  if (issues.length > 0) {
    const s = issues[0];
    console.log(`    样例字段：title=${JSON.stringify(s.title)} status=${s.status} priority=${s.priority} assignee=${s.assignee}`);
  }
}

await client.close();
console.log("\n✅ 验证完成");
