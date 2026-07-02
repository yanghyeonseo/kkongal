import { useEffect, useRef, useState } from "react";
import { Bell, Search, X, Tag, BellRing, LogOut, Plus } from "lucide-react";

function Header({
  currentUser,
  searchQuery,
  onSearchChange,
  onOpenAuth,
  onOpenSiteRegister,
  onOpenInterestSetting,
  onOpenAlertSettings,
  onLogout,
}) {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const profileRef = useRef(null);

  const userInitial = currentUser?.name?.slice(0, 1) || "?";

  useEffect(() => {
    if (!isProfileMenuOpen) return;

    const handlePointerDown = (event) => {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setIsProfileMenuOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setIsProfileMenuOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isProfileMenuOpen]);

  const runAndClose = (action) => {
    setIsProfileMenuOpen(false);
    action();
  };

  return (
    <header className="header">
      <div className="brand">
        <div className="brandIcon">
          <Bell size={21} strokeWidth={2.4} />
        </div>
        <strong>맞춤 공지 알리미</strong>
      </div>

      <div className="searchBox">
        <Search size={18} className="searchIcon" aria-hidden="true" />
        <input
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="공지·사이트 검색"
          aria-label="공지 검색"
          disabled={!currentUser}
        />
        {searchQuery && (
          <button
            type="button"
            className="searchClear"
            onClick={() => onSearchChange("")}
            aria-label="검색어 지우기"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {currentUser ? (
        <>
          <button className="siteButton" onClick={onOpenSiteRegister}>
            <Plus size={16} /> 사이트 등록
          </button>

          <div className="profileArea" ref={profileRef}>
            <button
              className="profileButton"
              onClick={() => setIsProfileMenuOpen((prev) => !prev)}
              aria-haspopup="menu"
              aria-expanded={isProfileMenuOpen}
              aria-label="내 계정 메뉴"
            >
              {userInitial}
            </button>

            {isProfileMenuOpen && (
              <div className="profileMenu" role="menu">
                <p>
                  <strong>{currentUser.name}</strong>
                  <span>{currentUser.email || "이메일 미등록"}</span>
                </p>

                <button
                  className="profileMenuButton"
                  role="menuitem"
                  onClick={() => runAndClose(onOpenInterestSetting)}
                >
                  <Tag size={16} /> 관심사 설정
                </button>

                <button
                  className="profileMenuButton"
                  role="menuitem"
                  onClick={() => runAndClose(onOpenAlertSettings)}
                >
                  <BellRing size={16} /> 알림 설정
                </button>

                <button
                  className="profileMenuButton logout"
                  role="menuitem"
                  onClick={() => runAndClose(onLogout)}
                >
                  <LogOut size={16} /> 로그아웃
                </button>
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="authButtons">
          <button className="loginButton" onClick={() => onOpenAuth("login")}>
            로그인
          </button>
          <button className="signupButton" onClick={() => onOpenAuth("signup")}>
            회원가입
          </button>
        </div>
      )}
    </header>
  );
}

export default Header;
