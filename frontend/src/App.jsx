import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";

import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import AiRecommendBox from "./components/AiRecommendBox.jsx";
import NoticeCard from "./components/NoticeCard.jsx";
import SiteRegisterModal from "./components/SiteRegisterModal.jsx";
import InterestSettingModal from "./components/InterestSettingModal.jsx";
import AlertSettingsModal from "./components/AlertSettingsModal.jsx";
import AuthModal from "./components/AuthModal.jsx";

import { getMyInboxNotices, toggleInboxNoticeSave } from "./api/inboxApi.js";
import { getNoticeSources } from "./api/sourceApi.js";
import { getMyInterests } from "./api/interestApi.js";
import {
  getStoredUser,
  saveStoredUser,
  clearStoredUser,
  getCurrentUser,
  logout,
} from "./api/authApi.js";

import { isToday } from "./utils/date.js";
import { isAiMatched } from "./utils/relevance.js";
import { useToast } from "./context/toast.js";

const VIEW_TITLES = {
  all: "오늘 새 공지",
  ai: "AI 추천 공지",
  saved: "저장한 공지",
};

const CATEGORY_FILTERS = [
  { id: "all", label: "전체" },
  { id: "deadline", label: "마감임박" },
];

const NOTICES_PER_PAGE = 5;

function App() {
  const toast = useToast();

  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [notices, setNotices] = useState([]);
  const [sources, setSources] = useState([]);
  const [interests, setInterests] = useState([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState("");

  const [selectedView, setSelectedView] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [activeSourceIds, setActiveSourceIds] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");

  const [isSiteRegisterOpen, setIsSiteRegisterOpen] = useState(false);
  const [isInterestSettingOpen, setIsInterestSettingOpen] = useState(false);
  const [isAlertSettingsOpen, setIsAlertSettingsOpen] = useState(false);
  const [authMode, setAuthMode] = useState(null);

  const [currentPage, setCurrentPage] = useState(1);

  // 최초 진입 시 쿠키(access_token) 기준으로 로그인 상태를 복원한다.
  useEffect(() => {
    let active = true;

    const hydrate = async () => {
      const stored = getStoredUser();
      if (stored) setCurrentUser(stored); // 낙관적 표시(깜빡임 방지)

      try {
        const user = await getCurrentUser();
        if (!active) return;
        setCurrentUser(user);
        saveStoredUser(user);
      } catch {
        if (!active) return;
        setCurrentUser(null);
        clearStoredUser();
      } finally {
        if (active) setAuthLoading(false);
      }
    };

    hydrate();
    return () => {
      active = false;
    };
  }, []);

  const loadDashboardData = useCallback(async () => {
    setDashboardLoading(true);
    setDashboardError("");
    try {
      const [nextNotices, nextSources, nextInterests] = await Promise.all([
        getMyInboxNotices(),
        getNoticeSources(),
        getMyInterests(),
      ]);

      setNotices(nextNotices);
      setSources(nextSources);
      setInterests(nextInterests);
      setActiveSourceIds(
        nextSources.filter((source) => source.isSubscribed).map((source) => source.id),
      );
    } catch (error) {
      console.error(error);
      setDashboardError("대시보드 데이터를 불러오지 못했어요.");
      toast.error("대시보드 데이터를 불러오지 못했어요.");
    } finally {
      setDashboardLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!currentUser) return;
    loadDashboardData();
  }, [currentUser, loadDashboardData]);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedView, selectedCategory, activeSourceIds, searchQuery]);

  const handleOpenAuth = (mode) => setAuthMode(mode);

  const handleAuthSuccess = (user) => {
    saveStoredUser(user);
    setCurrentUser(user);
    setAuthMode(null);
    toast.success(`${user.name}님, 환영해요!`);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error(error);
    } finally {
      clearStoredUser();
      setCurrentUser(null);
      setNotices([]);
      setSources([]);
      setInterests([]);
      setActiveSourceIds([]);
      setSearchQuery("");
      setSelectedView("all");
      toast.info("로그아웃했어요.");
    }
  };

  const handleToggleSource = (sourceId) => {
    setActiveSourceIds((prev) =>
      prev.includes(sourceId)
        ? prev.filter((id) => id !== sourceId)
        : [...prev, sourceId],
    );
  };

  const handleSourceAdded = (source) => {
    setSources((prev) =>
      prev.some((item) => item.subscriptionId === source.subscriptionId)
        ? prev
        : [...prev, source],
    );
    setActiveSourceIds((prev) =>
      prev.includes(source.id) ? prev : [...prev, source.id],
    );
  };

  const handleSourceRemoved = (source) => {
    setSources((prev) =>
      prev.filter((item) => item.subscriptionId !== source.subscriptionId),
    );
    setActiveSourceIds((prev) => prev.filter((id) => id !== source.id));
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
      toast.error("저장 상태 변경에 실패했어요.");
    }
  };

  const sourceFilteredNotices = useMemo(() => {
    return notices.filter((notice) => {
      if (activeSourceIds.length === 0) return false;
      return activeSourceIds.includes(notice.sourceId);
    });
  }, [notices, activeSourceIds]);

  const aiCount = useMemo(
    () => sourceFilteredNotices.filter(isAiMatched).length,
    [sourceFilteredNotices],
  );

  const savedCount = useMemo(
    () => sourceFilteredNotices.filter((notice) => notice.isSaved).length,
    [sourceFilteredNotices],
  );

  const todayNoticeCount = useMemo(
    () => sourceFilteredNotices.filter((notice) => isToday(notice.publishedAt)).length,
    [sourceFilteredNotices],
  );

  const filteredNotices = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return sourceFilteredNotices.filter((notice) => {
      if (selectedView === "ai" && !isAiMatched(notice)) return false;
      if (selectedView === "saved" && !notice.isSaved) return false;
      if (selectedCategory === "deadline" && !notice.isDeadlineSoon) return false;

      if (query) {
        const haystack = [
          notice.title,
          notice.sourceDisplayName,
          notice.description,
          ...(notice.matchedInterestTags || []),
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(query)) return false;
      }

      return true;
    });
  }, [sourceFilteredNotices, selectedView, selectedCategory, searchQuery]);

  const totalPages = Math.ceil(filteredNotices.length / NOTICES_PER_PAGE) || 1;
  const paginatedNotices = useMemo(() => {
    const startIndex = (currentPage - 1) * NOTICES_PER_PAGE;
    return filteredNotices.slice(startIndex, startIndex + NOTICES_PER_PAGE);
  }, [filteredNotices, currentPage]);

  const headlineCount =
    selectedView === "all" ? todayNoticeCount : filteredNotices.length;

  const renderNoticeArea = () => {
    if (dashboardLoading) {
      return (
        <div className="noticeList">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="noticeCard noticeCardSkeleton">
              <div className="skeletonLine skeletonAvatar" />
              <div className="skeletonStack">
                <div className="skeletonLine w30" />
                <div className="skeletonLine w80" />
                <div className="skeletonLine w60" />
              </div>
            </div>
          ))}
        </div>
      );
    }

    if (dashboardError) {
      return (
        <div className="emptyNoticeBox error">
          <p>{dashboardError}</p>
          <button className="retryButton" onClick={loadDashboardData}>
            다시 시도
          </button>
        </div>
      );
    }

    if (paginatedNotices.length === 0) {
      let message = "조건에 맞는 공지가 아직 없어요.";
      if (searchQuery.trim()) message = `'${searchQuery.trim()}' 검색 결과가 없어요.`;
      else if (activeSourceIds.length === 0)
        message = "왼쪽에서 볼 사이트를 하나 이상 켜주세요.";
      else if (selectedView === "saved") message = "저장한 공지가 아직 없어요.";
      else if (selectedView === "ai") message = "AI가 강하게 추천하는 공지가 아직 없어요.";

      return <div className="emptyNoticeBox">{message}</div>;
    }

    return (
      <div className="noticeList">
        {paginatedNotices.map((notice) => (
          <NoticeCard
            key={notice.inboxNoticeId}
            notice={notice}
            onOpenNotice={handleOpenNotice}
            onToggleSave={handleToggleSave}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="app">
      <Header
        currentUser={currentUser}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onOpenAuth={handleOpenAuth}
        onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
        onOpenInterestSetting={() => setIsInterestSettingOpen(true)}
        onOpenAlertSettings={() => setIsAlertSettingsOpen(true)}
        onLogout={handleLogout}
      />

      {authLoading ? (
        <main className="authGate">
          <div className="authRequiredBox">
            <span className="bigSpinner" aria-hidden="true" />
            <strong>불러오는 중...</strong>
          </div>
        </main>
      ) : !currentUser ? (
        <main className="authGate">
          <div className="authRequiredBox landing">
            <div className="landingIcon">🔔</div>
            <strong>로그인하고 맞춤 공지를 받아보세요</strong>
            <p>여러 사이트의 공지를 AI가 골라 한 곳에 모아드려요.</p>
            <div className="landingButtons">
              <button className="signupButton" onClick={() => handleOpenAuth("signup")}>
                회원가입
              </button>
              <button className="loginButton" onClick={() => handleOpenAuth("login")}>
                로그인
              </button>
            </div>
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
            savedCount={savedCount}
            activeSourceIds={activeSourceIds}
            onToggleSource={handleToggleSource}
          />

          <main className="main">
            <AiRecommendBox notices={sourceFilteredNotices} interests={interests} />

            <section className="noticeSection">
              <div className="noticeTitleRow">
                <div>
                  <p className="sectionEyebrow">맞춤 공지함</p>
                  <h2>
                    {VIEW_TITLES[selectedView]} <span>{headlineCount}</span>건
                  </h2>
                </div>

                <div className="filterButtons">
                  {CATEGORY_FILTERS.map((category) => (
                    <button
                      key={category.id}
                      className={selectedCategory === category.id ? "active" : ""}
                      aria-pressed={selectedCategory === category.id}
                      onClick={() => setSelectedCategory(category.id)}
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>

              {renderNoticeArea()}

              {!dashboardLoading && filteredNotices.length > NOTICES_PER_PAGE && (
                <div className="pagination">
                  {Array.from({ length: totalPages }, (_, index) => {
                    const pageNumber = index + 1;
                    return (
                      <button
                        key={pageNumber}
                        className={`pageButton ${
                          currentPage === pageNumber ? "active" : ""
                        }`}
                        aria-current={currentPage === pageNumber ? "page" : undefined}
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
        <SiteRegisterModal
          sources={sources}
          onClose={() => setIsSiteRegisterOpen(false)}
          onSourceAdded={handleSourceAdded}
          onSourceRemoved={handleSourceRemoved}
        />
      )}

      {isInterestSettingOpen && (
        <InterestSettingModal
          interests={interests}
          onClose={() => setIsInterestSettingOpen(false)}
          onInterestsChange={setInterests}
        />
      )}

      {isAlertSettingsOpen && (
        <AlertSettingsModal
          currentUser={currentUser}
          onClose={() => setIsAlertSettingsOpen(false)}
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
