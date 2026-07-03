import { AlertTriangle, Info, X } from "lucide-react";

const QUOTA_TEXT =
  "AI 사용량이 일시적으로 소진돼 키워드 기반으로 임시 동작 중이에요. 잠시 후 다시 정상화됩니다.";
const DISABLED_TEXT = "AI 키가 설정되지 않아 키워드 기반으로 동작 중이에요.";

// AI 파이프라인 저하(쿼터 소진/미설정) 알림 배너.
function AiStatusBanner({ reason, message, onDismiss }) {
  const isQuota = reason === "quota";
  const text = message || (isQuota ? QUOTA_TEXT : DISABLED_TEXT);

  return (
    <div className={`aiStatusBanner ${isQuota ? "warn" : "info"}`} role="status">
      <span className="aiStatusIcon" aria-hidden="true">
        {isQuota ? <AlertTriangle size={18} /> : <Info size={18} />}
      </span>
      <p className="aiStatusText">{text}</p>
      <button
        type="button"
        className="aiStatusClose"
        onClick={onDismiss}
        aria-label="배너 닫기"
      >
        <X size={16} />
      </button>
    </div>
  );
}

export default AiStatusBanner;
