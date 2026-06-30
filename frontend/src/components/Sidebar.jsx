function Sidebar({ sources, onOpenSources }) {
  const subscribedSources = sources.filter((source) => source.isSubscribed);

  return (
    <aside className="sidebar">
      <nav className="menu">
        <button className="menuItem active">🌐 전체</button>
        <button className="menuItem">⚡ AI 추천</button>
        <button className="menuItem">🔔 안 읽음</button>
        <button className="menuItem">🔖 저장됨</button>
      </nav>

      <div className="divider" />

      <p className="sideTitle">내 사이트</p>

      <div className="siteList">
        {subscribedSources.map((source) => (
          <button key={source.id} className="sitePill">
            <span className="dot" />
            {source.displayName}
          </button>
        ))}
      </div>

      <button className="addSite" onClick={onOpenSources}>
        관심 사이트 관리
      </button>
    </aside>
  );
}

export default Sidebar;
