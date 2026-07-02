import { useState } from "react";
import { HelpCircle, ExternalLink, ShieldAlert } from "lucide-react";
import ModalShell from "./ModalShell.jsx";

const STEPS = [
  {
    title: "Slack 앱 만들기",
    body: (
      <>
        <a
          href="https://api.slack.com/apps"
          target="_blank"
          rel="noreferrer"
        >
          api.slack.com/apps
        </a>{" "}
        접속 → <b>Create New App</b> → <b>From scratch</b> 를 고르고, 앱 이름과
        사용할 워크스페이스를 선택해요.
      </>
    ),
  },
  {
    title: "Incoming Webhooks 켜기",
    body: (
      <>
        왼쪽 메뉴에서 <b>Incoming Webhooks</b> 로 이동한 뒤, 우측 상단 토글을{" "}
        <b>On</b> 으로 켜요.
      </>
    ),
  },
  {
    title: "워크스페이스에 웹훅 추가",
    body: (
      <>
        페이지 아래 <b>Add New Webhook to Workspace</b> 버튼을 눌러요.
      </>
    ),
  },
  {
    title: "채널 선택",
    body: (
      <>
        알림을 받을 <b>채널</b>을 고르고 <b>Allow(허용)</b> 를 눌러요.
      </>
    ),
  },
  {
    title: "URL 복사해서 붙여넣기",
    body: (
      <>
        생성된 <code>https://hooks.slack.com/services/…</code> 주소를 복사해, 아래{" "}
        <b>Webhook URL</b> 칸에 붙여넣으면 끝이에요.
      </>
    ),
  },
];

function SlackWebhookHelp() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="helpButton"
        onClick={() => setIsOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-label="슬랙 Webhook URL 받는 방법 도움말 열기"
        title="Webhook URL 받는 방법"
      >
        <HelpCircle size={16} />
      </button>

      {isOpen && (
        <ModalShell
          className="helpDialog"
          ariaLabel="슬랙 Webhook URL 받는 방법"
          onClose={() => setIsOpen(false)}
        >
          <div className="helpDialogHeader">
            <h3>슬랙 Webhook URL 받는 방법</h3>
            <button
              type="button"
              className="modalCloseButton"
              onClick={() => setIsOpen(false)}
              aria-label="도움말 닫기"
            >
              ×
            </button>
          </div>

          <div className="helpDialogBody">
            <ol className="helpSteps">
              {STEPS.map((step) => (
                <li key={step.title} className="helpStep">
                  <div className="helpStepText">
                    <strong>{step.title}</strong>
                    <p>{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="helpCaution" role="note">
              <ShieldAlert size={18} aria-hidden="true" />
              <p>
                이 Webhook URL 은 <b>비밀번호와 같아요.</b> 유출되면 누구나 그
                채널로 메시지를 보낼 수 있으니 다른 사람과 공유하지 마세요.
              </p>
            </div>

            <a
              className="helpDocsLink"
              href="https://api.slack.com/messaging/webhooks"
              target="_blank"
              rel="noreferrer"
            >
              Slack 공식 가이드 열기
              <ExternalLink size={14} />
            </a>
          </div>
        </ModalShell>
      )}
    </>
  );
}

export default SlackWebhookHelp;
