import { useState } from "react";
import { MailWarning, Loader2, Check } from "lucide-react";
import { resendVerificationEmail } from "../api/authApi.js";
import { useToast } from "../context/toast.js";

/**
 * 이메일 미인증 안내 배너.
 *
 * 인증 전에도 서비스는 그대로 쓸 수 있지만 알림 메일은 발송되지 않는다
 * (백엔드 alert/service.py 가 미인증 계정의 이메일 채널을 건너뛴다).
 * 그 사실을 알려주고 재발송 버튼을 제공한다.
 *
 * 마크업은 AiStatusBanner 와 같은 클래스를 써서 배너 스타일을 공유한다.
 */
function EmailVerifyBanner({ email }) {
  const toast = useToast();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const resend = async () => {
    setSending(true);
    try {
      await resendVerificationEmail();
      setSent(true);
      toast.success("인증 메일을 다시 보냈어요. 메일함을 확인해주세요.");
    } catch (error) {
      toast.error(error.message || "인증 메일 발송에 실패했어요.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="aiStatusBanner warn" role="status">
      <span className="aiStatusIcon" aria-hidden="true">
        <MailWarning size={18} />
      </span>
      <p className="aiStatusText">
        이메일 인증을 완료해주세요.{" "}
        <span style={{ fontWeight: 500 }}>
          {email ? `${email} 으로 ` : "가입하신 주소로 "}
          보낸 메일의 링크를 열면 끝나요. 인증 전에는 공지 알림 메일이 발송되지
          않아요.
        </span>
      </p>
      <button
        type="button"
        className="verifyResendBtn"
        onClick={resend}
        disabled={sending || sent}
      >
        {sending ? (
          <>
            <Loader2 size={13} className="spin" /> 보내는 중
          </>
        ) : sent ? (
          <>
            <Check size={13} /> 보냈어요
          </>
        ) : (
          "메일 다시 보내기"
        )}
      </button>
    </div>
  );
}

export default EmailVerifyBanner;
