const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..");

function createWindow() {
  const win = new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 1040,
    minHeight: 720,
    title: "OpenSore Case Desk",
    backgroundColor: "#f6f4ef",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: { x: 18, y: 18 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.loadFile(path.join(__dirname, "renderer.html"));
  return win;
}

app.whenReady().then(() => {
  const win = createWindow();
  if (process.argv.includes("--smoke")) {
    win.webContents.once("did-finish-load", () => {
      setTimeout(() => app.quit(), 250);
    });
  }
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

ipcMain.handle("dialog:openSources", async () => {
  const result = await dialog.showOpenDialog({
    title: "Select exported evidence sources",
    buttonLabel: "Add exports",
    properties: ["openFile", "multiSelections"],
    filters: [
      { name: "Discovery exports", extensions: ["csv", "json", "jsonl", "ndjson"] },
      { name: "All files", extensions: ["*"] },
    ],
  });
  return result.canceled ? [] : result.filePaths;
});

ipcMain.handle("dialog:selectOutput", async () => {
  const result = await dialog.showOpenDialog({
    title: "Select discovery output folder",
    buttonLabel: "Use folder",
    properties: ["openDirectory", "createDirectory"],
  });
  return result.canceled ? "" : result.filePaths[0];
});

ipcMain.handle("shell:openPath", async (_event, targetPath) => {
  if (!targetPath) {
    return;
  }
  await shell.openPath(targetPath);
});

ipcMain.handle("opensore:planDiscovery", async (_event, request) => {
  const configPath = await writeTempConfig(request);
  const result = await runOpenSore(["discovery", "plan", configPath]);
  await safeUnlink(configPath);
  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout || "Discovery planning failed");
  }
  return JSON.parse(result.stdout);
});

ipcMain.handle("opensore:runDiscovery", async (_event, payload) => {
  const configPath = await writeTempConfig(payload.request);
  const args = ["discovery", "run", configPath];
  for (const source of payload.sources || []) {
    args.push("--source", source);
  }
  args.push("--out", payload.outputDir);

  const result = await runOpenSore(args);
  await safeUnlink(configPath);
  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout || "Discovery run failed");
  }

  const manifestPath = path.join(payload.outputDir, "discovery_manifest.json");
  const hitReportPath = path.join(payload.outputDir, "discovery_hit_report.csv");
  const evidencePath = path.join(payload.outputDir, "discovery_evidence.csv");
  const [manifest, hitReport, evidence] = await Promise.all([
    readJson(manifestPath),
    readCsv(hitReportPath),
    readCsv(evidencePath),
  ]);
  return {
    stdout: result.stdout,
    manifest,
    hitReport,
    evidence,
  };
});

async function writeTempConfig(request) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "opensore-discovery-"));
  const filePath = path.join(dir, "matter.json");
  await fs.writeFile(filePath, `${JSON.stringify(request, null, 2)}\n`, "utf8");
  return filePath;
}

function runOpenSore(args) {
  return new Promise((resolve, reject) => {
    const child = spawn("uv", ["run", "opensore", ...args], {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
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
      resolve({ code, stdout, stderr });
    });
  });
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function readCsv(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  const rows = parseCsv(raw);
  if (rows.length === 0) {
    return [];
  }
  const [headers, ...records] = rows;
  return records
    .filter((row) => row.some((value) => value.trim()))
    .map((row) =>
      Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])),
    );
}

function parseCsv(raw) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < raw.length; index += 1) {
    const char = raw[index];
    const next = raw[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        value += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else if (char !== "\r") {
      value += char;
    }
  }

  if (value || row.length) {
    row.push(value);
    rows.push(row);
  }
  return rows;
}

async function safeUnlink(filePath) {
  try {
    await fs.rm(path.dirname(filePath), { recursive: true, force: true });
  } catch (_error) {
    // Temp cleanup should not mask the discovery result.
  }
}
