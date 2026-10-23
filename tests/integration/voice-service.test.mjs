// Cross-runtime integration test: Node (future shell/UI runtime) <-> Python voice service,
// using only built-in modules (node:test, global WebSocket). No npm dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const svc = path.join(root, "services", "voice");
const venvPy = path.join(svc, ".venv", "Scripts", "python.exe");

function startService(token) {
  assert.ok(fs.existsSync(venvPy), `missing venv: run scripts/setup.ps1 (${venvPy})`);
  const child = spawn(venvPy, ["-m", "veronica_voice"], {
    cwd: svc,
    env: { ...process.env, PYTHONPATH: path.join(svc, "src"), VERONICA_TOKEN: token },
    stdio: ["ignore", "pipe", "inherit"],
  });
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("service did not start in 10s")), 10_000);
    createInterface({ input: child.stdout }).once("line", (line) => {
      clearTimeout(t);
      resolve({ child, port: JSON.parse(line).port });
    });
    child.once("exit", (c) => reject(new Error(`service exited early (${c})`)));
  });
}

const next = (ws) => new Promise((res) => ws.addEventListener("message", (e) => res(JSON.parse(e.data)), { once: true }));
const opened = (ws) => new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

test("node client completes hello -> ping -> pong against the python service", async () => {
  const token = randomBytes(24).toString("hex");
  const { child, port } = await startService(token);
  try {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    await opened(ws);
    ws.send(JSON.stringify({ v: 1, id: "h", type: "hello", payload: { token } }));
    assert.equal((await next(ws)).type, "ready");
    const t0 = performance.now();
    ws.send(JSON.stringify({ v: 1, id: "p", type: "ping" }));
    const pong = await next(ws);
    console.log(`# loopback ping rtt: ${(performance.now() - t0).toFixed(2)} ms`);
    assert.equal(pong.type, "pong");
    ws.close();
  } finally {
    child.kill();
  }
});
