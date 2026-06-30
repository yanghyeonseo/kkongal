function Header({ onOpenSources }) {
  return (
    <header className="header">
      <div className="brand">
        <div className="brandIcon">🔔</div>
        <strong>맞춤 공지 알리미</strong>
      </div>

      <div className="searchBox">
        <span>⌕</span>
        <input placeholder="공지·사이트 검색" />
      </div>

      <button className="siteButton" onClick={onOpenSources}>
        관심 사이트 관리
      </button>

      <button className="profileButton">김</button>
    </header>
  );
}

export default Header;
