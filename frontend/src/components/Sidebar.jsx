import { Globe, Sparkles, Bookmark, Plus } from "lucide-react";

function Sidebar({
  sources,
  selectedView,
  onChangeView,
  onOpenSiteRegister,
  aiCount,
  savedCount,
  activeSourceIds,
  onToggleSource,
}) {
  const subscribedSources = sources.filter((source) => source.isSubscribed);

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

      <p className="sideTitle">내 사이트</p>

      <div className="siteList">
        {subscribedSources.length === 0 ? (
          <p className="siteListEmpty">등록된 사이트가 없어요.</p>
        ) : (
          subscribedSources.map((source) => {
            const isActive = activeSourceIds.includes(source.id);
            return (
              <button
                key={source.id}
                className={`sitePill ${isActive ? "active" : "inactive"}`}
                aria-pressed={isActive}
                title={source.url}
                onClick={() => onToggleSource(source.id)}
              >
                <span className="dot" />
                {source.displayName}
              </button>
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
