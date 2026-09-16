const path = require("node:path");
const { spawn } = require("node:child_process");

const electronExecutable = require("electron");
const environment = { ...process.env };

// 임베디드 터미널이 이 값을 물려주면 Electron이 데스크톱 런타임이
// 아니라 일반 Node 프로세스로 실행되므로 개발 실행 전에 제거합니다.
delete environment.ELECTRON_RUN_AS_NODE;

const child = spawn(electronExecutable, [path.join(__dirname, "main.cjs")], {
  env: environment,
  stdio: "inherit",
});

child.once("error", (error) => {
  console.error(error);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => child.kill(signal));
}
