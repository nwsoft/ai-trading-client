import { useEffect, useState, type FormEvent } from "react";

import type { GatewayClient } from "../api";
import type { SessionSnapshot } from "../types";

export function LoginScreen({ client, onSuccess }: { client: GatewayClient; onSuccess: (session: SessionSnapshot) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [saveLogin, setSaveLogin] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    document.body.classList.add("login-surface");
    document.title = "NoahAI Finance Decision OS - 로그인";
    window.noahAI?.credentials?.load().then((saved) => {
      if (!saved.saved) return;
      setUsername(saved.username ?? "");
      setPassword(saved.password ?? "");
      setSaveLogin(true);
    }).catch(() => undefined);
    return () => document.body.classList.remove("login-surface");
  }, []);

  function openHelp() {
    const desktop = window.noahAI?.window?.openLoginHelp;
    if (desktop) {
      void desktop();
      return;
    }
    window.open(`${window.location.pathname}?surface=login-help`, "noahai-login-help", "width=640,height=540");
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const session = await client.login(username, password);
      try {
        if (saveLogin) await window.noahAI?.credentials?.save(username, password);
        else await window.noahAI?.credentials?.clear();
      } catch (_) {
        // A platform keychain failure must not turn a successful account login
        // into an authentication failure. The credential simply remains unsaved.
      }
      setPassword("");
      onSuccess(session);
    }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : "로그인에 실패했습니다."); }
    finally { setBusy(false); }
  }
  return (
    <main className="legacy-login-shell">
      <section className="legacy-login-window" aria-label="NoahAI 로그인">
        <header className="legacy-login-logo">
          <div className="legacy-login-title-row">
            <img className="legacy-login-logo-image" src="/icon.png" alt="" />
            <h1>NoahAI Decision OS</h1>
          </div>
          <p>AI 재테크 의사결정 파트너</p>
        </header>
        <form className="legacy-login-form" onSubmit={submit}>
          <h2>로그인</h2>
          <label>
            <span>아이디</span>
            <input autoComplete="username" placeholder="아이디를 입력하세요" value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            <span>패스워드</span>
            <input autoComplete="current-password" placeholder="패스워드를 입력하세요" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <div className="legacy-login-options">
            <label className="legacy-checkbox">
              <input type="checkbox" checked={saveLogin} onChange={(event) => setSaveLogin(event.target.checked)} />
              <span>로그인 정보 저장</span>
            </label>
            <button className="legacy-help-button" type="button" onClick={openHelp}>도움말</button>
          </div>
          {message && <div className="legacy-login-message error-text">{message}</div>}
          <div className="legacy-login-actions">
            <a className="legacy-signup-button" href="https://daltrading.net" rel="noreferrer" target="_blank">회원가입</a>
            <button className="legacy-login-button" disabled={busy || !username.trim() || !password} type="submit">{busy ? "인증 중…" : "로그인"}</button>
          </div>
        </form>
      </section>
    </main>
  );
}

const LOGIN_HELP_TABS = [
  {
    id: "login",
    label: "로그인 안내",
    content: `NoahAI Decision OS — 로그인

1) 아이디·패스워드
   • 가입 시 등록한 계정으로 로그인합니다.
   • 「로그인 정보 저장」을 켜두면 다음 실행 시 아이디가 채워질 수 있습니다.

2) 회원가입
   • 「회원가입」 버튼을 누르면 웹(https://daltrading.net)으로 이동합니다.
   • 웹에서 회원가입을 완료한 뒤, 이 화면으로 돌아와 다시 로그인합니다.
   • 운영 정책에 따라 가입키가 필요한 계정은 판매 채널 또는 공식 고객지원 경로에서 발급받습니다.
   • 약관·필수 동의는 회원가입 웹 절차에서 진행합니다.

3) 보안
   • 충분히 긴 패스워드 사용과 주기적 변경을 권장합니다.
   • 의심스러운 접근이 있으면 비밀번호를 바꾸고 지원 채널로 문의하세요.

4) 기타
   • 본 앱은 고정 스킨 UI를 사용합니다.
   • 문의는 고객지원 채널을 이용해 주세요.
   • 이용·책임 문구는 「이용·책임 참고」 탭에서 확인할 수 있습니다.`,
  },
  {
    id: "policy",
    label: "이용·책임 참고",
    content: `참고용 안내 (로그인할 때마다 동의 절차를 두지 않습니다)

1) 서비스 성격
   • 베타·테스트 성격의 기능이 포함될 수 있습니다.
   • NoahAI는 투자·금융 자문이 아니며 AI 분석·판단 정보는 참고용입니다.
   • 최종 금융 결정과 결과는 사용자 본인 책임입니다.

2) 역할 구분
   • 앱은 판단·설명·기록·검증·환류를 돕습니다.
   • 주문·체결·자금 이동은 사용자 계정과 거래소·증권사 등 외부 API가 수행합니다.

3) 약관·동의
   • 필수 약관·동의는 회원가입 또는 운영 정책이 정한 최초 1회 절차에서 처리합니다.
   • 이 탭은 로그인 전에도 내용을 읽을 수 있게 제공하는 참고 문구입니다.

4) 손실·장애
   • 시장 변동, API 오류, 거래소 장애 등 실행 구간 이슈가 발생할 수 있습니다.

5) XAI·규제 정렬
   • 판단 근거를 로그·화면으로 추적할 수 있는 방향을 지향합니다.
   • 로그인 후 메뉴얼 「이용 안내·책임」에서 항목별 전문을 확인할 수 있습니다.`,
  },
  { id: "web", label: "공식 안내(웹)", content: "" },
] as const;

export function LoginHelpScreen() {
  const [tab, setTab] = useState<(typeof LOGIN_HELP_TABS)[number]["id"]>("login");
  useEffect(() => {
    document.body.classList.add("login-help-surface");
    document.title = "도움말";
    return () => document.body.classList.remove("login-help-surface");
  }, []);
  const selected = LOGIN_HELP_TABS.find((item) => item.id === tab) ?? LOGIN_HELP_TABS[0];
  return <main className="login-help-shell">
    <section className="login-help-window" aria-label="로그인 도움말">
      <nav className="login-help-tabs" aria-label="도움말 분류">
        {LOGIN_HELP_TABS.map((item) => <button className={tab === item.id ? "active" : ""} key={item.id} onClick={() => setTab(item.id)} type="button">{item.label}</button>)}
      </nav>
      {selected.id === "web" ? <div className="login-help-web">
        <p>Noah AI Labs 공식 사이트에서 회사 소개, 서비스·적용 영역, 기술 소개, 금융 AI와 미래를 확인할 수 있습니다.</p>
        <a href="https://noahailabs.com/ko/about" rel="noreferrer" target="_blank">회사 소개</a>
        <a href="https://noahailabs.com/ko/product" rel="noreferrer" target="_blank">서비스·적용 영역</a>
        <a href="https://noahailabs.com/ko/technology" rel="noreferrer" target="_blank">기술 소개</a>
        <a href="https://noahailabs.com/ko/service/financial-ai-future" rel="noreferrer" target="_blank">금융 AI와 미래</a>
      </div> : <pre className="login-help-content">{selected.content}</pre>}
      <footer><button type="button" onClick={() => window.close()}>닫기</button></footer>
    </section>
  </main>;
}
