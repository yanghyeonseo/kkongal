import { useState } from "react";
import { Bell, Search, Plus } from "lucide-react";

function Header({
  currentUser,
  onOpenAuth,
  onOpenSiteRegister,
  onOpenInterestSetting,
  onLogout,
}) {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);

  const userInitial = currentUser?.name?.slice(0, 1) || "김";

  const handleOpenInterestSetting = () => {
    setIsProfileMenuOpen(false);
    onOpenInterestSetting();
  };

  const handleLogout = () => {
    setIsProfileMenuOpen(false);
    onLogout();
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
        <span>⌕</span>
        <input placeholder="공지·사이트 검색" />
      </div>

      {currentUser ? (
        <>
          <button className="siteButton" onClick={onOpenSiteRegister}>
            + 사이트 등록
          </button>

          <div className="profileArea">
            <button
              className="profileButton"
              onClick={() => setIsProfileMenuOpen((prev) => !prev)}
            >
              {userInitial}
            </button>

            {isProfileMenuOpen && (
              <div className="profileMenu">
                <p>
                  <strong>{currentUser.name}</strong>
                  <span>{currentUser.email}</span>
                </p>

                <button
                  className="profileMenuButton"
                  onClick={handleOpenInterestSetting}
                >
                  관심사 설정
                </button>

                <button
                  className="profileMenuButton logout"
                  onClick={handleLogout}
                >
                  로그아웃
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
