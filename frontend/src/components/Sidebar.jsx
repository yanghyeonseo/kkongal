function Sidebar({
  sources,
  selectedView,
  onChangeView,
  onOpenSiteRegister,
  aiCount,
  unreadCount,
  activeSourceIds,
  onToggleSource,
}) {
  const subscribedSources = sources.filter((source) => source.isSubscribed);

  return (
    <aside className="sidebar">
      <nav className="menu">
        <button
          className={`menuItem ${selectedView === "all" ? "active" : ""}`}
          onClick={() => onChangeView("all")}
        >
          <span>🌐 전체</span>
        </button>

        <button
          className={`menuItem ${selectedView === "ai" ? "active" : ""}`}
          onClick={() => onChangeView("ai")}
        >
          <span>⚡ AI 추천</span>
          <strong className="menuBadge">{aiCount}</strong>
        </button>

        <button
          className={`menuItem ${selectedView === "unread" ? "active" : ""}`}
          onClick={() => onChangeView("unread")}
        >
          <span>🔔 안 읽음</span>
          <strong className="menuBadge">{unreadCount}</strong>
        </button>

        <button
          className={`menuItem ${selectedView === "saved" ? "active" : ""}`}
          onClick={() => onChangeView("saved")}
        >
          <span>🔖 저장됨</span>
        </button>
      </nav>

      <div className="divider" />

      <p className="sideTitle">내 사이트</p>

      <div className="siteList">
        {subscribedSources.map((source) => {
          const isActive = activeSourceIds.includes(source.id);

          return (
            <button
              key={source.id}
              className={`sitePill ${isActive ? "active" : "inactive"}`}
              onClick={() => onToggleSource(source.id)}
            >
              <span className="dot" />
              {source.displayName}
            </button>
          );
        })}
      </div>

      <button className="addSite" onClick={onOpenSiteRegister}>
        + 사이트 등록
      </button>
    </aside>
  );
}

export default Sidebar;
