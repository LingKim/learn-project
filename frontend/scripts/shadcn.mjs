import { spawn } from "node:child_process";
import path from "node:path";

const proxyVariables = [
  "ALL_PROXY",
  "HTTPS_PROXY",
  "HTTP_PROXY",
  "all_proxy",
  "https_proxy",
  "http_proxy",
];

const childEnvironment = { ...process.env };
for (const variable of proxyVariables) delete childEnvironment[variable];

const executable = path.resolve(
  "node_modules",
  ".bin",
  process.platform === "win32" ? "shadcn.cmd" : "shadcn",
);
const child = spawn(executable, process.argv.slice(2), {
  cwd: process.cwd(),
  env: childEnvironment,
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`无法启动本地 shadcn CLI：${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});
