import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";

const requiredFiles = [
  "desktop/main.js",
  "desktop/preload.js",
  "desktop/renderer.html",
  "desktop/renderer.js",
  "desktop/styles.css",
];

for (const file of requiredFiles) {
  const text = await readFile(file, "utf8");
  if (text.trim().length === 0) {
    throw new Error(`${file} is empty`);
  }
}

const html = await readFile("desktop/renderer.html", "utf8");
for (const id of ["plan-button", "run-button", "custodian-list", "keyword-list"]) {
  if (!html.includes(`id="${id}"`)) {
    throw new Error(`renderer.html is missing #${id}`);
  }
}

const request = {
  title: "Desktop smoke matter",
  matter_type: "workplace_misconduct",
  sources: [{ kind: "custom_csv", label: "Local export", scopes: ["read_export"] }],
  keyword_sets: [{ name: "harassment", terms: ["harass"], category: "investigation" }],
  export_target: "local_csv",
  store_evidence_locally: false,
};

const plan = await run("uv", [
  "run",
  "python",
  "-c",
  [
    "import json",
    "from app.discovery.models import DiscoveryInvestigationRequest, build_discovery_plan",
    `payload = ${JSON.stringify(JSON.stringify(request))}`,
    "plan = build_discovery_plan(DiscoveryInvestigationRequest.model_validate(json.loads(payload)))",
    "print(plan.model_dump_json())",
  ].join("; "),
]);

const parsed = JSON.parse(plan);
if (parsed.query_count === 0 && parsed.queries.length === 0) {
  throw new Error("discovery smoke plan did not generate queries");
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(stderr || stdout || `${command} exited ${code}`));
      }
    });
  });
}
