import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("..", import.meta.url));
const python = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
if (!existsSync(python)) {
  console.error(
    "Create .venv with Python 3.11+ and install backend/requirements.lock.txt. See README.md.",
  );
  process.exit(1);
}
const commands = {
  dev: [
    "-m",
    "uvicorn",
    "backend.app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
    "--reload",
    "--reload-dir",
    "backend",
  ],
  start: [
    "-m",
    "uvicorn",
    "backend.app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
  ],
  test: ["-m", "pytest", "backend/tests", "-q"],
};
const command = commands[process.argv[2]];
if (!command) throw new Error("Unknown backend command");
const child = spawn(python, command, { cwd: root, stdio: "inherit" });
child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
