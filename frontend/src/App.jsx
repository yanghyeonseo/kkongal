import { useEffect, useMemo, useState } from "react";
import "./App.css";

import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import AiRecommendBox from "./components/AiRecommendBox.jsx";
import NoticeCard from "./components/NoticeCard.jsx";
import SiteRegisterModal from "./components/SiteRegisterModal.jsx";
import InterestSettingModal from "./components/InterestSettingModal.jsx";
import AuthModal from "./components/AuthModal.jsx";

import { getMyInboxNotices, toggleInboxNoticeSave } from "./api/inboxApi.js";
import { getNoticeSources } from "./api/sourceApi.js";
import { getMyInterests } from "./api/interestApi.js";
import {
  getStoredUser,
  saveStoredUser,
  clearStoredUser,
  logout,
} from "./api/authApi.js";

import { isToday } from "./utils/date.js";

const VIEW_TITLES = {
  all: "오늘 새 공지",
  ai: "AI 추천 공지",
  saved: "저장한 공지",
};

const CATEGORY_FILTERS = [
  { id: "all", label: "전체" },
  { id: "job", label: "채용" },
  { id: "school", label: "학사" },
  { id: "deadline", label: "마감임박" },
];

const MOCK_USER = {
  id: 1,
  name: "김현서",
  username: "김현서",
  email: "test@example.com",
};

function App() {
  const [currentUser, setCurrentUser] = useState(() => {
    return getStoredUser() || MOCK_USER;
  });

  const [notices, setNotices] = useState([]);
  const [sources, setSources] = useState([]);
  const [interests, setInterests] = useState([]);

  const [selectedView, setSelectedView] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [activeSourceIds, setActiveSourceIds] = useState([]);

  const [isSiteRegisterOpen, setIsSiteRegisterOpen] = useState(false);
  const [isInterestSettingOpen, setIsInterestSettingOpen] = useState(false);
  const [authMode, setAuthMode] = useState(null);

  const [currentPage, setCurrentPage] = useState(1);
  const noticesPerPage = 5;

  useEffect(() => {
    if (!currentUser) return;

    const loadDashboardData = async () => {
      try {
        const [nextNotices, nextSources, nextInterests] = await Promise.all([
          getMyInboxNotices(),
          getNoticeSources(),
          getMyInterests(),
        ]);

        setNotices(nextNotices);
        setSources(nextSources);
        setInterests(nextInterests);

        const subscribedSourceIds = nextSources
          .filter((source) => source.isSubscribed)
          .map((source) => source.id);

        setActiveSourceIds(subscribedSourceIds);
      } catch (error) {
        console.error(error);
        alert("대시보드 데이터를 불러오지 못했어요.");
      }
    };

    loadDashboardData();
  }, [currentUser]);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedView, selectedCategory, activeSourceIds]);

  const handleOpenAuth = (mode) => {
    setAuthMode(mode);
  };

  const handleAuthSuccess = (user) => {
    saveStoredUser(user);
    setCurrentUser(user);
    setAuthMode(null);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error(error);
    } finally {
      clearStoredUser();

      // 지금은 테스트를 편하게 하기 위해 로그아웃 후에도 mock 로그인 상태 유지
      setCurrentUser(MOCK_USER);
      saveStoredUser(MOCK_USER);

      // 실제 로그아웃 화면을 보고 싶으면 위 2줄 대신 아래 코드 사용
      // setCurrentUser(null);
    }
  };

  const handleToggleSource = (sourceId) => {
    setActiveSourceIds((prev) => {
      if (prev.includes(sourceId)) {
        return prev.filter((id) => id !== sourceId);
      }

      return [...prev, sourceId];
    });
  };

  const handleOpenNotice = (notice) => {
    setNotices((prev) =>
      prev.map((item) =>
        item.inboxNoticeId === notice.inboxNoticeId
          ? { ...item, isRead: true }
          : item,
      ),
    );

    window.open(notice.url, "_blank", "noopener,noreferrer");
  };

  const handleToggleSave = async (inboxNoticeId) => {
    const targetNotice = notices.find(
      (notice) => notice.inboxNoticeId === inboxNoticeId,
    );

    if (!targetNotice) return;

    const nextIsSaved = !targetNotice.isSaved;

    setNotices((prev) =>
      prev.map((notice) =>
        notice.inboxNoticeId === inboxNoticeId
          ? { ...notice, isSaved: nextIsSaved }
          : notice,
      ),
    );

    try {
      await toggleInboxNoticeSave(inboxNoticeId, nextIsSaved);
    } catch (error) {
      console.error(error);

      setNotices((prev) =>
        prev.map((notice) =>
          notice.inboxNoticeId === inboxNoticeId
            ? { ...notice, isSaved: !nextIsSaved }
            : notice,
        ),
      );

      alert("저장 상태 변경에 실패했어요.");
    }
  };

  const handleSaveInterests = (nextInterests) => {
    setInterests(nextInterests);
  };

  const sourceFilteredNotices = useMemo(() => {
    return notices.filter((notice) => {
      if (activeSourceIds.length === 0) return false;
      return activeSourceIds.includes(notice.sourceId);
    });
  }, [notices, activeSourceIds]);

  const aiCount = useMemo(() => {
    return sourceFilteredNotices.filter(
      (notice) =>
        notice.relevanceScore >= 0.8 || notice.matchedInterestTags?.length > 0,
    ).length;
  }, [sourceFilteredNotices]);

  const todayNoticeCount = useMemo(() => {
    return sourceFilteredNotices.filter((notice) => isToday(notice.publishedAt))
      .length;
  }, [sourceFilteredNotices]);

  const filteredNotices = useMemo(() => {
    return sourceFilteredNotices.filter((notice) => {
      if (selectedView === "ai") {
        const isAiMatched =
          notice.relevanceScore >= 0.8 ||
          notice.matchedInterestTags?.length > 0;

        if (!isAiMatched) return false;
      }

      if (selectedView === "saved") {
        if (!notice.isSaved) return false;
      }

      if (selectedCategory === "job") {
        if (notice.category !== "job") return false;
      }

      if (selectedCategory === "school") {
        if (notice.category !== "school") return false;
      }

      if (selectedCategory === "deadline") {
        if (!notice.isDeadlineSoon) return false;
      }

      return true;
    });
  }, [sourceFilteredNotices, selectedView, selectedCategory]);

  const totalPages = Math.ceil(filteredNotices.length / noticesPerPage);
  const safeTotalPages = totalPages === 0 ? 1 : totalPages;

  const paginatedNotices = useMemo(() => {
    const startIndex = (currentPage - 1) * noticesPerPage;
    const endIndex = startIndex + noticesPerPage;

    return filteredNotices.slice(startIndex, endIndex);
  }, [filteredNotices, currentPage]);

  return (
    <div className="app">
      <Header
        currentUser={currentUser}
        onOpenAuth={handleOpenAuth}
        onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
        onOpenInterestSetting={() => setIsInterestSettingOpen(true)}
        onLogout={handleLogout}
      />

      {!currentUser ? (
        <main className="authGate">
          <div className="authRequiredBox">
            <strong>로그인을 진행해주세요</strong>
          </div>
        </main>
      ) : (
        <div className="dashboard">
          <Sidebar
            sources={sources}
            selectedView={selectedView}
            onChangeView={setSelectedView}
            onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
            aiCount={aiCount}
            activeSourceIds={activeSourceIds}
            onToggleSource={handleToggleSource}
          />

          <main className="main">
            <AiRecommendBox
              notices={sourceFilteredNotices}
              interests={interests}
            />

            <section className="noticeSection">
              <div className="noticeTitleRow">
                <div>
                  <p className="sectionEyebrow">맞춤 공지함</p>

                  <h2>
                    {VIEW_TITLES[selectedView]}{" "}
                    <span>
                      {selectedView === "all"
                        ? todayNoticeCount
                        : filteredNotices.length}
                    </span>
                    건
                  </h2>
                </div>

                <div className="filterButtons">
                  {CATEGORY_FILTERS.map((category) => (
                    <button
                      key={category.id}
                      className={
                        selectedCategory === category.id ? "active" : ""
                      }
                      onClick={() => setSelectedCategory(category.id)}
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="noticeList">
                {paginatedNotices.length === 0 ? (
                  <div className="emptyNoticeBox">
                    조건에 맞는 공지가 아직 없어요.
                  </div>
                ) : (
                  paginatedNotices.map((notice) => (
                    <NoticeCard
                      key={notice.inboxNoticeId}
                      notice={notice}
                      onOpenNotice={handleOpenNotice}
                      onToggleSave={handleToggleSave}
                    />
                  ))
                )}
              </div>

              {filteredNotices.length > noticesPerPage && (
                <div className="pagination">
                  {Array.from({ length: safeTotalPages }, (_, index) => {
                    const pageNumber = index + 1;

                    return (
                      <button
                        key={pageNumber}
                        className={`pageButton ${
                          currentPage === pageNumber ? "active" : ""
                        }`}
                        onClick={() => setCurrentPage(pageNumber)}
                      >
                        {pageNumber}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
          </main>
        </div>
      )}

      {isSiteRegisterOpen && (
        <SiteRegisterModal onClose={() => setIsSiteRegisterOpen(false)} />
      )}

      {isInterestSettingOpen && (
        <InterestSettingModal
          interests={interests}
          onClose={() => setIsInterestSettingOpen(false)}
          onSave={handleSaveInterests}
        />
      )}

      {authMode && (
        <AuthModal
          initialMode={authMode}
          onClose={() => setAuthMode(null)}
          onAuthSuccess={handleAuthSuccess}
        />
      )}
    </div>
  );
}

export default App;
