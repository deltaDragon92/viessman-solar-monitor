import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const uiRoot = process.cwd();
const projectRoot = path.resolve(uiRoot, "..");
const backendRoot = path.join(projectRoot, "backend");
const venvPython = path.join(projectRoot, ".venv", "bin", "python");
const pythonCommand = fs.existsSync(venvPython) ? venvPython : "python3";

const backend = spawn(
  pythonCommand,
  [path.join(backendRoot, "solar_api_server.py")],
  {
    cwd: projectRoot,
    stdio: "inherit"
  }
);

const frontend = spawn(
  "npx",
  ["parcel", "serve", "index.html", "--host", "0.0.0.0", "--port", "1420"],
  {
    cwd: uiRoot,
    stdio: "inherit"
  }
);

function shutdown(code = 0) {
  backend.kill("SIGTERM");
  frontend.kill("SIGTERM");
  process.exit(code);
}

backend.on("exit", (code) => {
  if (code && code !== 0) {
    shutdown(code);
  }
});

frontend.on("exit", (code) => {
  shutdown(code ?? 0);
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
