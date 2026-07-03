import { useState } from "react";
import { Plus, Loader2 } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import SiteCatalog from "./SiteCatalog.jsx";
import { useToast } from "../context/toast.js";
import {
  createSourceSubscription,
  deleteSourceSubscription,
} from "../api/sourceApi.js";

// 카탈로그 항목과 구독중 소스를 매칭(우선 sourceId, 없으면 url).
function matchesCatalog(source, item) {
  if (item.sourceId != null && source.id === item.sourceId) return true;
  return source.url === item.url;
}

function SiteRegisterModal({
  sources,
  onClose,
  onSourceAdded,
  onSourceRemoved,
  onSyncSource,
}) {
  const toast = useToast();

  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);

  const isSubscribed = (item) =>
    sources.some((source) => matchesCatalog(source, item));

  const handleToggle = async (item, next) => {
    if (next) {
      try {
        const source = await createSourceSubscription({ url: item.url });
        onSourceAdded?.(source);
        toast.success(`'${item.name}' 구독을 시작했어요.`);
        // 첫 구독 직후 자동 동기화 → 새 사이트도 곧바로 공지가 노출되도록.
        onSyncSource?.(source.id, { silentUnsupported: true });
      } catch (error) {
        toast.error(error.message || "구독에 실패했어요.");
      }
      return;
    }

    const subscription = sources.find((source) => matchesCatalog(source, item));
    if (!subscription) return;
    try {
      await deleteSourceSubscription(subscription.subscriptionId);
      onSourceRemoved?.(subscription);
      toast.info(`'${item.name}' 구독을 해제했어요.`);
    } catch (error) {
      toast.error(error.message || "구독 해제에 실패했어요.");
    }
  };

  // 지원 목록에 없는 사이트를 URL 로 직접 등록한다(백엔드가 표시명·파비콘을 추정).
  const handleAddByUrl = async (event) => {
    event.preventDefault();
    const value = url.trim();
    if (!value) {
      toast.error("사이트 URL을 입력해주세요.");
      return;
    }

    const normalized = /^https?:\/\//i.test(value) ? value : `https://${value}`;
    setAdding(true);
    try {
      const source = await createSourceSubscription({ url: normalized });
      onSourceAdded?.(source);
      toast.success(`'${source.displayName}' 구독을 시작했어요.`);
      onSyncSource?.(source.id, { silentUnsupported: true });
      setUrl("");
    } catch (error) {
      toast.error(error.message || "URL 등록에 실패했어요.");
    } finally {
      setAdding(false);
    }
  };

  const subscribedCount = sources.length;

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title="사이트 등록"
      subtitle="지원하는 사이트에서 골라 구독하거나, URL로 직접 등록하세요."
    >
      <form className="urlRegisterForm" onSubmit={handleAddByUrl}>
        <label className="urlRegisterLabel" htmlFor="siteUrlInput">
          직접 URL로 등록
        </label>
        <div className="urlRegisterRow">
          <input
            id="siteUrlInput"
            className="urlRegisterInput"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="예: https://example.com/notice"
            aria-label="등록할 사이트 URL"
          />
          <button type="submit" className="primaryButton" disabled={adding}>
            {adding ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
            등록
          </button>
        </div>
        <p className="urlRegisterHint">
          지원 목록에 없는 사이트도 URL로 추가할 수 있어요.
        </p>
      </form>

      <div className="registerDivider" />

      <div className="registerListHead">
        <span>지원 사이트</span>
        <strong>{subscribedCount}개 구독 중</strong>
      </div>

      <SiteCatalog isSubscribed={isSubscribed} onToggle={handleToggle} />
    </ModalShell>
  );
}

export default SiteRegisterModal;
