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

  const subscribedCount = sources.length;

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title="사이트 등록"
      subtitle="지원하는 사이트에서 골라 구독하면 새 공지를 자동으로 모아드려요."
    >
      <div className="registerListHead">
        <span>지원 사이트</span>
        <strong>{subscribedCount}개 구독 중</strong>
      </div>

      <SiteCatalog isSubscribed={isSubscribed} onToggle={handleToggle} />
    </ModalShell>
  );
}

export default SiteRegisterModal;
