import http from "node:http";
import apiClientPkg from "@hcengineering/api-client";
import trackerPkg from "@hcengineering/tracker";
import corePkg from "@hcengineering/core";
import contactPkg from "@hcengineering/contact";

// Resolve the plugin resource map (packages nest their registry under .default).
const unwrap = (m) => {
  let x = m;
  while (x && x.default && typeof x.default === "object") x = x.default;
  return x;
};
const tracker = unwrap(trackerPkg);
const core = unwrap(corePkg);
const contact = unwrap(contactPkg);
const { connect } = apiClientPkg as any;

const url = process.env.HULY_URL || "http://localhost:8087";
const workspace = process.env.HULY_WORKSPACE || "";
const token = process.env.HULY_TOKEN || "";
const email = process.env.HULY_EMAIL || "";
const password = process.env.HULY_PASSWORD || "";
const bridgeToken = process.env.BRIDGE_TOKEN || "";
const bridgePort = parseInt(process.env.BRIDGE_PORT || "8600", 10);

if (!workspace) {
  console.error("缺少 HULY_WORKSPACE");
  process.exit(1);
}
if (!token && !(email && password)) {
  console.error("请提供 HULY_TOKEN，或 HULY_EMAIL + HULY_PASSWORD");
  process.exit(1);
}

const options = token ? { token, workspace } : { email, password, workspace };
const client = await connect(url, options);

// Issue-status categories that count as finished vs cancelled, read live from
// the workspace's IssueStatus docs. Values are `task:statusCategory:*`.
// Done(Won) -> resolved; Canceled(Lost) -> closed; everything else stays active.
const DONE_CATEGORIES = new Set(["task:statusCategory:Won"]);
const CANCELED_CATEGORIES = new Set(["task:statusCategory:Lost"]);

// Cache of statusRef -> category string, loaded lazily and refreshed per request
// batch so the report always sees current workflow definitions.
let statusCategoryByRef = new Map();

async function loadStatusCategories() {
  const statuses = await client.findAll(tracker.class.IssueStatus, {});
  const map = new Map();
  for (const s of statuses) {
    map.set(s._id, String(s.category || ""));
  }
  statusCategoryByRef = map;
  return map;
}

// Normalized to the ZenTao-compatible shape the Python report layer consumes.
function normalizeIssue(issue, users, components, projectIdentifier) {
  const category = statusCategoryByRef.get(issue.status) || "";
  let status = "active";
  if (DONE_CATEGORIES.has(category)) status = "resolved";
  else if (CANCELED_CATEGORIES.has(category)) status = "closed";

  const severity = mapPriorityToSeverity(issue.priority);
  const componentId = issue.component;
  const moduleTitle = components.get(componentId) || "";
  const openedBy = users.get(String(issue.createdBy || issue.modifiedBy || "")) || "";
  const assignedTo = users.get(String(issue.assignee || "")) || "";
  const openedDate = issue.createdOn
    ? new Date(issue.createdOn).toISOString().slice(0, 19).replace("T", " ")
    : "";

  return {
    // Keep ZenTao's numeric id (the project-local issue number) so the report
    // sorting/rendering logic is unchanged; expose the human key separately.
    id: issue.number,
    key: projectIdentifier ? `${projectIdentifier}-${issue.number}` : String(issue.number),
    title: issue.title,
    status,
    severity,
    pri: severity,
    module: componentId,
    moduleTitle,
    openedBy,
    openedDate,
    // Huly has no standard resolved-by/resolved-date; Python snapshot logic fills these.
    resolvedBy: "",
    resolvedDate: "",
    assignedTo,
  };
}

function mapPriorityToSeverity(priority) {
  // Huly IssuePriority: 0 NoPriority, 1 Low, 2 Medium, 3 High, 4 Urgent.
  // Map onto ZenTao's 1..4 severity so the report's S1/S2 high-risk logic works.
  if (typeof priority === "number") {
    if (priority >= 4) return 1; // Urgent -> S1
    if (priority === 3) return 2; // High -> S2
    if (priority === 2) return 3; // Medium -> S3
    return 4; // Low / NoPriority -> S4
  }
  const p = String(priority ?? "").toLowerCase();
  if (p.includes("urgent") || p.includes("critical")) return 1;
  if (p.includes("high")) return 2;
  if (p.includes("medium") || p.includes("normal")) return 3;
  return 4;
}

// Huly stores person names as "last,first" via combineName; the Python report
// just displays the string, so join it back into a normal Chinese-readable name.
function cleanName(raw) {
  if (!raw) return "";
  const parts = String(raw).split(",").map((s) => s.trim()).filter(Boolean);
  return parts.join("");
}

async function buildUsersMap() {
  // Issue person fields may reference a Person by _id, or by a SocialIdentity
  // _id / personUuid (e.g. createdBy). Build one map covering every key form.
  const people = await client.findAll(contact.mixin.Employee, {});
  const socials = await client.findAll(contact.class.SocialIdentity, {});
  const personName = new Map();
  for (const p of people) {
    personName.set(String(p._id), cleanName(p.name || p.displayName || p.email) || String(p._id));
  }
  const map = new Map();
  for (const p of people) {
    const name = personName.get(String(p._id));
    map.set(String(p._id), name);
    if (p.personUuid) map.set(String(p.personUuid), name);
  }
  for (const s of socials) {
    const name = personName.get(String(s.attachedTo));
    if (name) {
      map.set(String(s._id), name);
      if (s.value) map.set(String(s.value), name);
    }
  }
  return map;
}

async function buildComponentsMap(projectId) {
  const components = await client.findAll(tracker.class.Component, { space: projectId });
  const map = new Map();
  for (const c of components) {
    map.set(c._id, c.label);
  }
  return map;
}

async function listProjects() {
  const projects = await client.findAll(tracker.class.Project, {});
  return projects
    .filter((p) => !p.archived)
    .map((p) => ({
      // identifier is the human/project key ("5092"); the report keys scopes by it.
      id: p.identifier,
      identifier: p.identifier,
      name: p.name,
      kind: "project",
    }));
}

async function listBugs(identifier) {
  const projects = await client.findAll(tracker.class.Project, { identifier });
  if (!projects.length) {
    const err: any = new Error(`project ${identifier} not found`);
    err.statusCode = 404;
    throw err;
  }
  const project = projects[0];
  const [issues, users, components] = await Promise.all([
    client.findAll(tracker.class.Issue, { space: project._id }),
    buildUsersMap(),
    buildComponentsMap(project._id),
    loadStatusCategories(),
  ]);
  return issues.map((i) => normalizeIssue(i, users, components, project.identifier));
}

async function listUsers() {
  const map = await buildUsersMap();
  return Object.fromEntries(map);
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Content-Type", "application/json; charset=utf-8");

  if (bridgeToken && req.headers["x-bridge-token"] !== bridgeToken) {
    res.statusCode = 401;
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }

  const reqUrl = new URL(req.url, `http://localhost:${bridgePort}`);
  const path = reqUrl.pathname;

  try {
    if (path === "/health") {
      res.end(JSON.stringify({ ok: true, auth: token ? "token" : "account" }));
      return;
    }
    if (path === "/projects") {
      res.end(JSON.stringify(await listProjects()));
      return;
    }
    if (path === "/users") {
      res.end(JSON.stringify(await listUsers()));
      return;
    }
    const m = path.match(/^\/projects\/([^/]+)\/bugs$/);
    if (m) {
      res.end(JSON.stringify(await listBugs(decodeURIComponent(m[1]))));
      return;
    }
    res.statusCode = 404;
    res.end(JSON.stringify({ error: "not found" }));
  } catch (err) {
    console.error(err);
    res.statusCode = err.statusCode || 500;
    res.end(JSON.stringify({ error: String(err && err.message ? err.message : err) }));
  }
});

server.listen(bridgePort, () => {
  console.log(`Huly Bridge 已启动，监听 ${bridgePort}`);
});
