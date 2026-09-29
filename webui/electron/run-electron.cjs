const path = require("node:path");
const { spawn } = require("node:child_process");

// Local development must not pair a new Python version with stale renderer JS.
if (!process.env.NOAHAI_WEB_UI_DEV_URL && !require('./ui-build-contract.cjs').isCurrent(path.resolve(__dirname,'..'))) {
  console.error('화면 빌드가 없거나 현재 소스와 다릅니다. webui에서 npm run build 후 다시 실행하세요. 엔진 버전 표시는 화면 빌드 확인을 대신하지 않습니다.');
  process.exit(1);
}

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
