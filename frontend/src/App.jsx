import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";

import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import NoticeCard from "./components/NoticeCard.jsx";
import NoticeDetailModal from "./components/NoticeDetailModal.jsx";
import SiteRegisterModal from "./components/SiteRegisterModal.jsx";
import InterestSettingModal from "./components/InterestSettingModal.jsx";
import AlertSettingsModal from "./components/AlertSettingsModal.jsx";
import AuthModal from "./components/AuthModal.jsx";
import Landing from "./components/Landing.jsx";
import OnboardingWizard from "./components/OnboardingWizard.jsx";

import {
  getMyInboxNotices,
  toggleInboxNoticeSave,
  markInboxNoticeRead,
} from "./api/inboxApi.js";
import { getNoticeSources, syncSource, updateSourceName } from "./api/sourceApi.js";
import { getMyInterests } from "./api/interestApi.js";
import { getAiStatus } from "./api/aiApi.js";
import {
  saveStoredUser,
  clearStoredUser,
  getCurrentUser,
  logout,
} from "./api/authApi.js";

import { Globe, Plus, AlertTriangle, Info, X } from "lucide-react";

import { isAiMatched } from "./utils/relevance.js";
import { useToast } from "./context/toast.js";

const VIEW_TITLES = {
  all: "전체 공지",
  ai: "AI 추천 공지",
  saved: "저장한 공지",
};

const CATEGORY_FILTERS = [
  { id: "all", label: "전체" },
  { id: "deadline", label: "마감임박" },
  { id: "expired", label: "마감" },
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
  const [selectedInterests, setSelectedInterests] = useState([]);
  const [activeSourceIds, setActiveSourceIds] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNoticeId, setSelectedNoticeId] = useState(null);

  const [isSiteRegisterOpen, setIsSiteRegisterOpen] = useState(false);
  const [isInterestSettingOpen, setIsInterestSettingOpen] = useState(false);
  const [isAlertSettingsOpen, setIsAlertSettingsOpen] = useState(false);
  const [authMode, setAuthMode] = useState(null);

  const [currentPage, setCurrentPage] = useState(1);
  const [syncingSourceIds, setSyncingSourceIds] = useState([]);

  // AI 파이프라인 저하(쿼터 소진/미설정) 배너 상태.
  // dismissedReason: 세션 내에서 사용자가 닫은 사유. 상태가 정상으로 돌아갔다가
  // 다시 저하되면(아래 effect 가 초기화) 배너를 다시 노출한다.
  const [aiStatus, setAiStatus] = useState({
    degraded: false,
    reason: "ok",
    message: "",
  });
  const [aiBannerDismissedReason, setAiBannerDismissedReason] = useState(null);

  // 최초 진입 시 쿠키(access_token) 기준으로 로그인 상태를 복원한다.
  useEffect(() => {
    let active = true;

    const hydrate = async () => {
      // 인증 확인(=/me 성공) 전에는 currentUser 를 세우지 않는다. 낙관적으로 세우면
      // 대시보드 로딩 이펙트가 돌아 interests/inbox/subscriptions 가 미인증으로 호출된다.
      // 이 대기 구간은 authLoading 스피너가 가려준다.
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

  // AI 상태 조회(대시보드 로드 시 · 동기화 완료 후). 실패해도 조용히 정상으로 둔다.
  const refreshAiStatus = useCallback(async () => {
    const status = await getAiStatus();
    setAiStatus(status);
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    loadDashboardData();
    refreshAiStatus();
  }, [currentUser, loadDashboardData, refreshAiStatus]);

  // 상태가 정상으로 돌아오면 닫기 기억을 초기화 → 이후 다시 저하되면 배너를 재노출.
  useEffect(() => {
    if (!aiStatus.degraded) setAiBannerDismissedReason(null);
  }, [aiStatus.degraded]);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedView, selectedCategory, selectedInterests, activeSourceIds, searchQuery]);

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
      setAiStatus({ degraded: false, reason: "ok", message: "" });
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

  // 온디맨드 동기화: 해당 사이트를 즉시 크롤+선별한 뒤 인박스를 새로고침한다.
  // opts.silentUnsupported: 첫 구독 직후 자동 호출 시 '자동 수집 미지원(400)'은 조용히 넘긴다.
  const handleSyncSource = useCallback(
    async (sourceId, opts = {}) => {
      setSyncingSourceIds((prev) =>
        prev.includes(sourceId) ? prev : [...prev, sourceId],
      );
      try {
        const result = await syncSource(sourceId);
        const nextNotices = await getMyInboxNotices();
        setNotices(nextNotices);

        const added = result.inboxAdded || result.newNotices || 0;
        if (added > 0) {
          toast.success(`${added}건 새로 추천했어요.`);
        } else if (result.message) {
          toast.info(result.message);
        } else {
          toast.info("새로 추천할 공지가 없어요.");
        }
      } catch (error) {
        if (opts.silentUnsupported && error?.status === 400) {
          // 자동 수집 미지원 사이트를 자동 sync 한 경우 — 사용자에게 알리지 않음
          console.info("sync skipped:", error.message);
        } else {
          toast.error(error.message || "동기화에 실패했어요.");
        }
      } finally {
        setSyncingSourceIds((prev) => prev.filter((id) => id !== sourceId));
        // 동기화가 쿼터를 소진시켰거나 반대로 정상화됐을 수 있어 상태를 다시 확인.
        refreshAiStatus();
      }
    },
    [toast, refreshAiStatus],
  );

  // 전체 동기화: 구독 중인 모든 사이트를 병렬로 sync 하고, 결과를 한 번에 요약한다.
  const handleSyncAll = useCallback(async () => {
    const ids = sources.filter((source) => source.isSubscribed).map((source) => source.id);
    if (ids.length === 0) return;

    setSyncingSourceIds(ids);
    let added = 0;
    await Promise.all(
      ids.map(async (id) => {
        try {
          const result = await syncSource(id);
          added += result.inboxAdded || result.newNotices || 0;
        } catch {
          // 개별 사이트 실패(자동 수집 미지원 등)는 무시하고 전체는 계속 진행
        }
      }),
    );
    try {
      setNotices(await getMyInboxNotices());
    } catch {
      // 인박스 새로고침 실패는 조용히 무시
    }
    setSyncingSourceIds([]);
    refreshAiStatus();
    if (added > 0) toast.success(`${added}건 새로 추천했어요.`);
    else toast.info("새로 추천할 공지가 없어요.");
  }, [sources, toast, refreshAiStatus]);

  const handleOnboardingComplete = useCallback(
    (user) => {
      const nextUser = { ...user, onboarded: true };
      setCurrentUser(nextUser);
      saveStoredUser(nextUser);
      toast.success("설정을 마쳤어요! 맞춤 공지를 확인해보세요.");
    },
    [toast],
  );

  // 카드 클릭 → 상세 모달을 열고, 여는 즉시 읽음 처리(안 읽음 점 사라짐).
  const handleOpenNotice = (notice) => {
    if (!notice.isRead) {
      setNotices((prev) =>
        prev.map((item) =>
          item.inboxNoticeId === notice.inboxNoticeId
            ? { ...item, isRead: true }
            : item,
        ),
      );
      // 서버에도 읽음 저장 → 새로고침 후에도 안읽음 점이 사라진 상태 유지.
      // 실패해도 열람은 막지 않는다(로컬은 이미 읽음 처리).
      markInboxNoticeRead(notice.inboxNoticeId).catch((error) =>
        console.error(error),
      );
    }
    setSelectedNoticeId(notice.inboxNoticeId);
  };

  // 표시명 인라인 편집. 낙관적 갱신 후 실패 시 이전 이름으로 되돌린다.
  const handleRenameSource = useCallback(
    async (sourceId, name) => {
      const target = sources.find((source) => source.id === sourceId);
      const prevName = target ? target.displayName : name;

      const applyName = (nextName) => {
        setSources((prev) =>
          prev.map((source) =>
            source.id === sourceId
              ? { ...source, name: nextName, displayName: nextName }
              : source,
          ),
        );
        setNotices((prev) =>
          prev.map((notice) =>
            notice.sourceId === sourceId
              ? { ...notice, sourceName: nextName, sourceDisplayName: nextName }
              : notice,
          ),
        );
      };

      applyName(name);
      try {
        const updated = await updateSourceName(sourceId, name);
        const finalName = updated.name || name;
        applyName(finalName);
        if (updated.faviconUrl) {
          setSources((prev) =>
            prev.map((source) =>
              source.id === sourceId
                ? { ...source, faviconUrl: updated.faviconUrl }
                : source,
            ),
          );
        }
        toast.success("사이트 이름을 변경했어요.");
      } catch (error) {
        applyName(prevName);
        toast.error(error.message || "이름 변경에 실패했어요.");
      }
    },
    [sources, toast],
  );

  const handleToggleInterest = (keyword) => {
    setSelectedInterests((prev) =>
      prev.includes(keyword)
        ? prev.filter((item) => item !== keyword)
        : [...prev, keyword],
    );
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

  // 배지/뷰는 사이드바 소스 토글과 무관하게 durable 하도록 전체 notices 기준으로 센다.
  const aiCount = useMemo(() => notices.filter(isAiMatched).length, [notices]);

  const savedCount = useMemo(
    () => notices.filter((notice) => notice.isSaved).length,
    [notices],
  );

  const filteredNotices = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    // 저장됨/AI 추천 뷰는 durable: 소스 토글과 무관하게 전체 notices 에서 뽑는다.
    // '전체' 뷰만 소스 필터(sourceFilteredNotices)를 적용한다.
    const base =
      selectedView === "saved" || selectedView === "ai"
        ? notices
        : sourceFilteredNotices;

    const activeInterests = selectedInterests.map((keyword) => keyword.toLowerCase());

    return base.filter((notice) => {
      if (selectedView === "ai" && !isAiMatched(notice)) return false;
      if (selectedView === "saved" && !notice.isSaved) return false;
      if (selectedCategory === "deadline" && !notice.isDeadlineSoon) return false;
      if (selectedCategory === "expired" && !notice.isExpired) return false;

      // 관심사별 매칭: 선택한 관심 키워드 중 하나라도 matched_keywords 와 겹치면 통과(OR).
      if (activeInterests.length > 0) {
        const tags = (notice.matchedInterestTags || []).map((tag) => tag.toLowerCase());
        const hit = activeInterests.some((keyword) =>
          tags.some((tag) => tag.includes(keyword) || keyword.includes(tag)),
        );
        if (!hit) return false;
      }

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
  }, [
    notices,
    sourceFilteredNotices,
    selectedView,
    selectedCategory,
    selectedInterests,
    searchQuery,
  ]);

  const totalPages = Math.ceil(filteredNotices.length / NOTICES_PER_PAGE) || 1;
  const paginatedNotices = useMemo(() => {
    const startIndex = (currentPage - 1) * NOTICES_PER_PAGE;
    return filteredNotices.slice(startIndex, startIndex + NOTICES_PER_PAGE);
  }, [filteredNotices, currentPage]);

  // 헤드라인 수치는 항상 실제로 보여주는 카드 수와 일치시킨다.
  const headlineCount = filteredNotices.length;

  // 상세 모달은 notices 에서 파생 — 저장 토글 등 갱신이 모달에 즉시 반영된다.
  const selectedNotice = useMemo(
    () => notices.find((notice) => notice.inboxNoticeId === selectedNoticeId) || null,
    [notices, selectedNoticeId],
  );

  // AI 저하 배너: 저하 상태이고, 이번 세션에 같은 사유로 닫지 않았을 때만 노출.
  const showAiBanner =
    aiStatus.degraded && aiBannerDismissedReason !== aiStatus.reason;
  const aiBannerText =
    aiStatus.message ||
    (aiStatus.reason === "quota"
      ? "AI 사용량이 일시적으로 소진돼 키워드 기반으로 임시 동작 중이에요. 잠시 후 다시 정상화됩니다."
      : "AI 키가 설정되지 않아 키워드 기반으로 동작 중이에요.");

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
      const hasSubscriptions = sources.some((source) => source.isSubscribed);

      // 첫 진입(구독 사이트 0개)은 사이드바도 비어 있으니 "켜주세요"가 아니라
      // 사이트 등록으로 유도하는 별도 CTA 를 보여준다.
      if (!hasSubscriptions && !searchQuery.trim()) {
        return (
          <div className="emptyNoticeBox cta">
            <span className="emptyCtaIcon" aria-hidden="true">
              <Globe size={26} />
            </span>
            <strong>아직 등록한 사이트가 없어요</strong>
            <p>관심 사이트를 등록하면 새 공지를 AI가 골라 모아드려요.</p>
            <button
              type="button"
              className="primaryButton"
              onClick={() => setIsSiteRegisterOpen(true)}
            >
              <Plus size={16} /> 사이트 등록하기
            </button>
          </div>
        );
      }

      let message = "조건에 맞는 공지가 아직 없어요.";
      if (searchQuery.trim()) message = `'${searchQuery.trim()}' 검색 결과가 없어요.`;
      else if (selectedView === "saved") message = "저장한 공지가 아직 없어요.";
      else if (selectedView === "ai") message = "AI가 강하게 추천하는 공지가 아직 없어요.";
      else if (activeSourceIds.length === 0)
        message = "왼쪽에서 볼 사이트를 하나 이상 켜주세요.";

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

  const showOnboarding = currentUser && currentUser.onboarded === false;

  let content;
  if (authLoading) {
    content = (
      <div className="bootLoader">
        <span className="bigSpinner" aria-hidden="true" />
        <strong>불러오는 중...</strong>
      </div>
    );
  } else if (!currentUser) {
    content = <Landing onOpenAuth={handleOpenAuth} />;
  } else if (showOnboarding) {
    content = (
      <OnboardingWizard user={currentUser} onComplete={handleOnboardingComplete} />
    );
  } else {
    content = (
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
            syncingSourceIds={syncingSourceIds}
            onSyncSource={handleSyncSource}
            onSyncAll={handleSyncAll}
            onRenameSource={handleRenameSource}
          />

          <main className="main">
            {showAiBanner && (
              <div
                className={`aiStatusBanner ${aiStatus.reason === "quota" ? "warn" : "info"}`}
                role="status"
              >
                <span className="aiStatusIcon" aria-hidden="true">
                  {aiStatus.reason === "quota" ? (
                    <AlertTriangle size={18} />
                  ) : (
                    <Info size={18} />
                  )}
                </span>
                <p className="aiStatusText">{aiBannerText}</p>
                <button
                  type="button"
                  className="aiStatusClose"
                  onClick={() => setAiBannerDismissedReason(aiStatus.reason)}
                  aria-label="배너 닫기"
                >
                  <X size={16} />
                </button>
              </div>
            )}

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

              {interests.length > 0 && (
                <div className="interestFilterRow">
                  <span className="interestFilterLabel">관심사</span>
                  <div className="interestFilterChips">
                    {interests.map((interest) => {
                      const active = selectedInterests.includes(interest.keyword);
                      return (
                        <button
                          key={interest.id}
                          type="button"
                          className={`interestFilterChip ${active ? "active" : ""}`}
                          aria-pressed={active}
                          onClick={() => handleToggleInterest(interest.keyword)}
                        >
                          {interest.keyword}
                        </button>
                      );
                    })}
                    {selectedInterests.length > 0 && (
                      <button
                        type="button"
                        className="interestFilterClear"
                        onClick={() => setSelectedInterests([])}
                      >
                        초기화
                      </button>
                    )}
                  </div>
                </div>
              )}

              <div
                className="viewFade"
                key={`${selectedView}-${selectedCategory}-${selectedInterests.join(",")}`}
              >
                {renderNoticeArea()}
              </div>

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
      </div>
    );
  }

  return (
    <>
      {content}

      {selectedNotice && (
        <NoticeDetailModal
          notice={selectedNotice}
          onClose={() => setSelectedNoticeId(null)}
          onToggleSave={handleToggleSave}
        />
      )}

      {isSiteRegisterOpen && currentUser && (
        <SiteRegisterModal
          sources={sources}
          onClose={() => setIsSiteRegisterOpen(false)}
          onSourceAdded={handleSourceAdded}
          onSourceRemoved={handleSourceRemoved}
          onSyncSource={handleSyncSource}
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
    </>
  );
}

export default App;
