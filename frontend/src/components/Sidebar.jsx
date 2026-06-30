const sites = [
  "서울대 컴공 공지",
  "서울대 경영대 공지",
  "사람인 HOT100",
  "네이버 채용",
  "잡코리아 AI 채용",
];

function Sidebar() {
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
        {sites.map((site) => (
          <button key={site} className="sitePill">
            <span className="dot" />
            {site}
          </button>
        ))}
      </div>

      <button className="addSite">관심 사이트 관리</button>
    </aside>
  );
}

export default Sidebar;
