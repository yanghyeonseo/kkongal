import { Globe, Sparkles, Bookmark, Plus, RefreshCw } from "lucide-react";

function Sidebar({
  sources,
  selectedView,
  onChangeView,
  onOpenSiteRegister,
  aiCount,
  savedCount,
  activeSourceIds,
  onToggleSource,
  syncingSourceIds = [],
  onSyncSource,
  onSyncAll,
}) {
  const subscribedSources = sources.filter((source) => source.isSubscribed);
  const syncingAll =
    subscribedSources.length > 0 &&
    subscribedSources.every((source) => syncingSourceIds.includes(source.id));

  const MENU = [
    { id: "all", label: "전체", Icon: Globe, badge: null },
    { id: "ai", label: "AI 추천", Icon: Sparkles, badge: aiCount },
    { id: "saved", label: "저장됨", Icon: Bookmark, badge: savedCount },
  ];

  return (
    <aside className="sidebar">
      <nav className="menu" aria-label="공지 보기 필터">
        {MENU.map(({ id, label, Icon, badge }) => (
          <button
            key={id}
            className={`menuItem ${selectedView === id ? "active" : ""}`}
            aria-current={selectedView === id ? "page" : undefined}
            onClick={() => onChangeView(id)}
          >
            <span className="menuLeft">
              <Icon size={18} className="menuIcon" />
              {label}
            </span>
            {badge > 0 && <strong className="menuBadge">{badge}</strong>}
          </button>
        ))}
      </nav>

      <div className="divider" />

      <div className="siteListHead">
        <span className="sideTitle" style={{ margin: 0, padding: 0 }}>
          내 사이트
        </span>
        {subscribedSources.length > 0 && onSyncAll && (
          <button
            type="button"
            className="syncAllButton"
            onClick={onSyncAll}
            disabled={syncingAll}
            title="구독 중인 모든 사이트에서 새 공지 가져오기"
          >
            <RefreshCw size={13} className={syncingAll ? "spin" : ""} /> 전체 동기화
          </button>
        )}
      </div>

      <div className="siteList">
        {subscribedSources.length === 0 ? (
          <p className="siteListEmpty">등록된 사이트가 없어요.</p>
        ) : (
          subscribedSources.map((source) => {
            const isActive = activeSourceIds.includes(source.id);
            const isSyncing = syncingSourceIds.includes(source.id);
            return (
              <div className="siteRow" key={source.id}>
                <button
                  className={`sitePill ${isActive ? "active" : "inactive"}`}
                  aria-pressed={isActive}
                  title={source.url}
                  onClick={() => onToggleSource(source.id)}
                >
                  <span className="dot" />
                  {source.displayName}
                </button>
                <button
                  type="button"
                  className="syncPillButton"
                  onClick={() => onSyncSource?.(source.id)}
                  disabled={isSyncing}
                  title={isSyncing ? "가져오는 중..." : "새 공지 동기화"}
                  aria-label={`${source.displayName} 새 공지 동기화`}
                >
                  <RefreshCw size={15} className={isSyncing ? "spin" : ""} />
                </button>
              </div>
            );
          })
        )}
      </div>

      <button className="addSite" onClick={onOpenSiteRegister}>
        <Plus size={16} /> 사이트 등록
      </button>
    </aside>
  );
}

export default Sidebar;
