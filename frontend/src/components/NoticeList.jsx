import { Globe, Plus } from "lucide-react";
import NoticeCard from "./NoticeCard.jsx";

function NoticeListSkeleton() {
  return (
    <div className="noticeList">
      {[0, 1, 2, 3].map((key) => (
        <div key={key} className="noticeCard noticeCardSkeleton">
          <div className="skeletonLine skeletonAvatar" />
          <div className="skeletonStack">
            <div className="skeletonLine w30" />
            <div className="skeletonLine w80" />
            <div className="skeletonLine w60" />
          </div>
        </div>
      ))}
    </div>
  );
}

// 페이지네이션이 적용된 공지 목록. 로딩/에러/빈 상태를 함께 처리한다.
function NoticeList({
  loading,
  error,
  onRetry,
  notices,
  hasSubscriptions,
  searchQuery,
  selectedView,
  activeSourceCount,
  onOpenSiteRegister,
  onOpenNotice,
  onToggleSave,
}) {
  if (loading) return <NoticeListSkeleton />;

  if (error) {
    return (
      <div className="emptyNoticeBox error">
        <p>{error}</p>
        <button className="retryButton" onClick={onRetry}>
          다시 시도
        </button>
      </div>
    );
  }

  if (notices.length === 0) {
    const trimmedQuery = searchQuery.trim();

    // 첫 진입(구독 사이트 0개)은 "켜주세요"가 아니라 사이트 등록으로 유도한다.
    if (!hasSubscriptions && !trimmedQuery) {
      return (
        <div className="emptyNoticeBox cta">
          <span className="emptyCtaIcon" aria-hidden="true">
            <Globe size={26} />
          </span>
          <strong>아직 등록한 사이트가 없어요</strong>
          <p>관심 사이트를 등록하면 새 공지를 AI가 골라 모아드려요.</p>
          <button type="button" className="primaryButton" onClick={onOpenSiteRegister}>
            <Plus size={16} /> 사이트 등록하기
          </button>
        </div>
      );
    }

    let message = "조건에 맞는 공지가 아직 없어요.";
    if (trimmedQuery) message = `'${trimmedQuery}' 검색 결과가 없어요.`;
    else if (selectedView === "saved") message = "저장한 공지가 아직 없어요.";
    else if (selectedView === "ai") message = "AI가 강하게 추천하는 공지가 아직 없어요.";
    else if (activeSourceCount === 0) message = "왼쪽에서 볼 사이트를 하나 이상 켜주세요.";

    return <div className="emptyNoticeBox">{message}</div>;
  }

  return (
    <div className="noticeList">
      {notices.map((notice) => (
        <NoticeCard
          key={notice.inboxNoticeId}
          notice={notice}
          onOpenNotice={onOpenNotice}
          onToggleSave={onToggleSave}
        />
      ))}
    </div>
  );
}

export default NoticeList;
