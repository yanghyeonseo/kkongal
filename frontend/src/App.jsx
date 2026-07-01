import { useEffect, useState } from "react";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import AiRecommendBox from "./components/AiRecommendBox";
import NoticeCard from "./components/NoticeCard";
import SiteRegisterModal from "./components/SiteRegisterModal";
import InterestSettingModal from "./components/InterestSettingModal";
import AuthModal from "./components/AuthModal";
import { getMyInboxNotices } from "./api/inboxApi.js";
import { getNoticeSources } from "./api/sourceApi.js";
import { getMyInterests } from "./api/interestApi.js";
import {
  clearStoredUser,
  getStoredUser,
  logout,
  saveStoredUser,
} from "./api/authApi.js";
import { isToday } from "./utils/date.js";
import "./App.css";

const MAIN_FILTERS = [
  {
    label: "전체",
    value: "all",
  },
  {
    label: "채용",
    value: "job",
  },
  {
    label: "학사",
    value: "school",
  },
  {
    label: "마감임박",
    value: "deadline",
  },
];

const VIEW_TITLES = {
  all: "오늘 새 공지",
  ai: "AI 추천 공지",
  unread: "안 읽은 공지",
  saved: "저장한 공지",
};

function App() {
  const [currentUser, setCurrentUser] = useState(() => getStoredUser());

  const [notices, setNotices] = useState([]);
  const [sources, setSources] = useState([]);
  const [interests, setInterests] = useState([]);

  const [activeSourceIds, setActiveSourceIds] = useState([]);

  const [loading, setLoading] = useState(Boolean(currentUser));

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");

  const [isSiteRegisterOpen, setIsSiteRegisterOpen] = useState(false);
  const [isInterestModalOpen, setIsInterestModalOpen] = useState(false);

  const [selectedView, setSelectedView] = useState("all");
  const [selectedMainFilter, setSelectedMainFilter] = useState("all");

  const [currentPage, setCurrentPage] = useState(1);
  const noticesPerPage = 5;

  useEffect(() => {
    if (!currentUser) {
      setNotices([]);
      setSources([]);
      setInterests([]);
      setActiveSourceIds([]);
      setLoading(false);
      return;
    }

    async function loadInitialData() {
      setLoading(true);

      try {
        const [noticeData, sourceData, interestData] = await Promise.all([
          getMyInboxNotices(),
          getNoticeSources(),
          getMyInterests(),
        ]);

        setNotices(noticeData);
        setSources(sourceData);
        setInterests(interestData);

        setActiveSourceIds(
          sourceData
            .filter((source) => source.isSubscribed)
            .map((source) => source.id),
        );
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    loadInitialData();
  }, [currentUser]);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedView, selectedMainFilter, activeSourceIds]);

  const handleOpenAuth = (mode) => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
  };

  const handleAuthSuccess = (user) => {
    saveStoredUser(user);
    setCurrentUser(user);
    setIsAuthModalOpen(false);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error(error);
    } finally {
      clearStoredUser();
      setCurrentUser(null);
      setSelectedView("all");
      setSelectedMainFilter("all");
      setCurrentPage(1);
    }
  };

  const handleOpenNotice = (notice) => {
    setNotices((prevNotices) =>
      prevNotices.map((item) =>
        item.inboxNoticeId === notice.inboxNoticeId
          ? {
              ...item,
              isRead: true,
            }
          : item,
      ),
    );

    window.open(notice.url, "_blank", "noopener,noreferrer");
  };

  const handleToggleSave = (inboxNoticeId) => {
    setNotices((prevNotices) =>
      prevNotices.map((notice) =>
        notice.inboxNoticeId === inboxNoticeId
          ? {
              ...notice,
              isSaved: !notice.isSaved,
            }
          : notice,
      ),
    );
  };

  const handleToggleSource = (sourceId) => {
    setActiveSourceIds((prevSourceIds) => {
      if (prevSourceIds.includes(sourceId)) {
        return prevSourceIds.filter((id) => id !== sourceId);
      }

      return [...prevSourceIds, sourceId];
    });
  };

  if (!currentUser) {
    return (
      <div className="app">
        <Header
          currentUser={null}
          onOpenAuth={handleOpenAuth}
          onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
          onOpenInterestSetting={() => setIsInterestModalOpen(true)}
          onLogout={handleLogout}
        />

        <div className="authGate">
          <div className="authRequiredBox">
            <strong>로그인을 진행해주세요</strong>
          </div>
        </div>

        {isAuthModalOpen && (
          <AuthModal
            initialMode={authMode}
            onClose={() => setIsAuthModalOpen(false)}
            onAuthSuccess={handleAuthSuccess}
          />
        )}
      </div>
    );
  }

  const activeSources = sources.filter((source) =>
    activeSourceIds.includes(source.id),
  );

  const sourceFilteredNotices = notices.filter((notice) => {
    if (activeSourceIds.length === 0) {
      return false;
    }

    return activeSources.some(
      (source) =>
        source.id === notice.sourceId ||
        source.name === notice.sourceName ||
        source.displayName === notice.sourceDisplayName,
    );
  });

  const isAiMatched = (notice) =>
    notice.relevanceScore >= 0.8 || notice.matchedInterestTags?.length > 0;

  const aiCount = sourceFilteredNotices.filter(isAiMatched).length;

  const unreadCount = sourceFilteredNotices.filter(
    (notice) => !notice.isRead,
  ).length;

  const viewFilteredNotices = sourceFilteredNotices.filter((notice) => {
    if (selectedView === "ai") {
      return isAiMatched(notice);
    }

    if (selectedView === "unread") {
      return !notice.isRead;
    }

    if (selectedView === "saved") {
      return notice.isSaved;
    }

    return true;
  });

  const filteredNotices = viewFilteredNotices.filter((notice) => {
    if (selectedMainFilter === "all") {
      return true;
    }

    if (selectedMainFilter === "deadline") {
      return notice.isDeadlineSoon;
    }

    return notice.category === selectedMainFilter;
  });

  const todayNewCount = filteredNotices.filter((notice) =>
    isToday(notice.publishedAt),
  ).length;

  const sectionCount =
    selectedView === "all" ? todayNewCount : filteredNotices.length;

  const sortedNotices = [...filteredNotices].sort(
    (a, b) => new Date(b.publishedAt) - new Date(a.publishedAt),
  );

  const totalPages = Math.ceil(sortedNotices.length / noticesPerPage);

  const startIndex = (currentPage - 1) * noticesPerPage;
  const endIndex = startIndex + noticesPerPage;

  const pagedNotices = sortedNotices.slice(startIndex, endIndex);

  return (
    <div className="app">
      <Header
        currentUser={currentUser}
        onOpenAuth={handleOpenAuth}
        onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
        onOpenInterestSetting={() => setIsInterestModalOpen(true)}
        onLogout={handleLogout}
      />

      {loading ? (
        <div className="loading">공지 목록을 불러오는 중...</div>
      ) : (
        <div className="layout">
          <Sidebar
            sources={sources}
            selectedView={selectedView}
            onChangeView={setSelectedView}
            onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
            aiCount={aiCount}
            unreadCount={unreadCount}
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
                <h2>
                  {VIEW_TITLES[selectedView]} <span>{sectionCount}건</span>
                </h2>

                <div className="filterButtons">
                  {MAIN_FILTERS.map((filter) => (
                    <button
                      key={filter.value}
                      className={
                        selectedMainFilter === filter.value ? "active" : ""
                      }
                      onClick={() => setSelectedMainFilter(filter.value)}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredNotices.length === 0 ? (
                <div className="emptyNotice">
                  <strong>아직 해당 조건의 공지가 없어요.</strong>
                  <p>다른 필터를 선택하거나 사이트를 추가해보세요.</p>
                </div>
              ) : (
                <div className="noticeList">
                  {pagedNotices.map((notice) => (
                    <NoticeCard
                      key={notice.inboxNoticeId}
                      notice={notice}
                      onOpenNotice={handleOpenNotice}
                      onToggleSave={handleToggleSave}
                    />
                  ))}

                  {totalPages > 1 && (
                    <div className="pagination">
                      {Array.from({ length: totalPages }, (_, index) => {
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
                </div>
              )}
            </section>
          </main>
        </div>
      )}

      {isAuthModalOpen && (
        <AuthModal
          initialMode={authMode}
          onClose={() => setIsAuthModalOpen(false)}
          onAuthSuccess={handleAuthSuccess}
        />
      )}

      {isSiteRegisterOpen && (
        <SiteRegisterModal onClose={() => setIsSiteRegisterOpen(false)} />
      )}

      {isInterestModalOpen && (
        <InterestSettingModal
          interests={interests}
          onClose={() => setIsInterestModalOpen(false)}
          onSave={setInterests}
        />
      )}
    </div>
  );
}

export default App;
