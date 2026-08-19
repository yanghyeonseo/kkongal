import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import NoticeToolbar from "./components/NoticeToolbar.jsx";
import NoticeList from "./components/NoticeList.jsx";
import AiStatusBanner from "./components/AiStatusBanner.jsx";
import NoticeDetailModal from "./components/NoticeDetailModal.jsx";
import SiteRegisterModal from "./components/SiteRegisterModal.jsx";
import InterestSettingModal from "./components/InterestSettingModal.jsx";
import ProfileSettingModal from "./components/ProfileSettingModal.jsx";
import AlertSettingsModal from "./components/AlertSettingsModal.jsx";
import AuthModal from "./components/AuthModal.jsx";
import Landing from "./components/Landing.jsx";
import OnboardingWizard from "./components/OnboardingWizard.jsx";

import {
  getMyInboxNotices,
  toggleInboxNoticeSave,
  markInboxNoticeRead,
} from "./api/inboxApi.js";
import {
  getNoticeSources,
  getSyncStatus,
  syncSource,
  updateSourceName,
} from "./api/sourceApi.js";
import { getMyInterests } from "./api/interestApi.js";
import { getAiStatus } from "./api/aiApi.js";
import { setUnauthorizedHandler } from "./api/client.js";
import {
  saveStoredUser,
  clearStoredUser,
  getCurrentUser,
  logout,
} from "./api/authApi.js";

import { useNoticeFilters } from "./hooks/useNoticeFilters.js";
import { useToast } from "./context/toast.js";

// 동기화 스피너 무한 대기 방지용 가드.
// SYNC_MAX_MS: 상태와 무관하게 이 시간이 지나면 개별 사이트를 종료로 간주(절대 타임아웃).
// SYNC_MAX_ERRORS: getSyncStatus 가 이 횟수만큼 연속 실패하면 배치 전체를 포기한다.
const SYNC_MAX_MS = 90_000;
const SYNC_MAX_ERRORS = 5;

function App() {
  const toast = useToast();

  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [notices, setNotices] = useState([]);
  const [sources, setSources] = useState([]);
  const [interests, setInterests] = useState([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState("");

  const [selectedNoticeId, setSelectedNoticeId] = useState(null);

  const [isSiteRegisterOpen, setIsSiteRegisterOpen] = useState(false);
  const [isInterestSettingOpen, setIsInterestSettingOpen] = useState(false);
  const [isProfileSettingOpen, setIsProfileSettingOpen] = useState(false);
  const [isAlertSettingsOpen, setIsAlertSettingsOpen] = useState(false);
  const [authMode, setAuthMode] = useState(null);

  const [syncingSourceIds, setSyncingSourceIds] = useState([]);
  // 폴링 루프가 최신 값을 stale closure 없이 읽도록 ref 로 미러링한다.
  const syncingIdsRef = useRef([]);
  const sourcesRef = useRef([]);
  const pollTimerRef = useRef(null);
  const pollActiveRef = useRef(false);
  // 동기화 중이나 상태 맵에서 사라진(만료/프로세스 재시작) 사이트의 연속 미검출 횟수.
  const missingPollsRef = useRef({});
  // 사이트별 동기화 시작 시각(ms). 절대 타임아웃(SYNC_MAX_MS) 판정에 쓴다.
  const syncStartedAtRef = useRef({});
  // getSyncStatus 연속 실패 횟수. SYNC_MAX_ERRORS 넘으면 배치를 포기한다.
  const syncErrorCountRef = useRef(0);
  const isMountedRef = useRef(true);
  // 세션 만료 핸들러가 stale closure 없이 최신 로그인 상태/필터를 읽도록 ref 로 미러링한다.
  const currentUserRef = useRef(null);

  const filters = useNoticeFilters(notices, interests);
  const { setActiveSourceIds } = filters;
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    currentUserRef.current = currentUser;
  }, [currentUser]);

  // dismissedReason: 세션 내에서 사용자가 배너를 닫은 사유. 상태가 정상으로 돌아갔다가
  // 다시 저하되면(아래 effect 가 초기화) 배너를 다시 노출한다.
  const [aiStatus, setAiStatus] = useState({
    degraded: false,
    reason: "ok",
    message: "",
  });
  const [aiBannerDismissedReason, setAiBannerDismissedReason] = useState(null);

  // 최초 진입 시 쿠키(access_token) 기준으로 로그인 상태를 복원한다.
  // 인증 확인(=/me 성공) 전에는 currentUser 를 세우지 않는다. 낙관적으로 세우면 대시보드
  // 로딩 이펙트가 돌아 interests/inbox/subscriptions 가 미인증으로 호출된다.
  useEffect(() => {
    let active = true;

    const hydrate = async () => {
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
  }, [toast, setActiveSourceIds]);

  // AI 상태 조회(대시보드 로드 시 · 동기화 완료 후). 실패해도 조용히 정상으로 둔다.
  const refreshAiStatus = useCallback(async () => {
    setAiStatus(await getAiStatus());
  }, []);

  // 진행 중 동기화를 최신값으로 폴링하기 위한 ref 미러링.
  useEffect(() => {
    syncingIdsRef.current = syncingSourceIds;
  }, [syncingSourceIds]);
  useEffect(() => {
    sourcesRef.current = sources;
  }, [sources]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    pollActiveRef.current = false;
    missingPollsRef.current = {};
    syncStartedAtRef.current = {};
    syncErrorCountRef.current = 0;
  }, []);

  // 한 폴링 주기: 상태 맵을 받아 done/failed 로 끝난 사이트마다 토스트를 띄우고
  // syncingSourceIds 에서 제거한다. 완료가 있었던 주기에만 인박스를 한 번 새로고침한다.
  // 백엔드 워커가 순차 처리하므로 완료(→토스트)는 사이트별로 하나씩 나타난다.
  const pollSyncStatus = useCallback(async () => {
    if (syncingIdsRef.current.length === 0) {
      stopPolling();
      return;
    }
    let jobs;
    try {
      jobs = await getSyncStatus();
      syncErrorCountRef.current = 0; // 성공하면 연속 실패 카운터 초기화
    } catch {
      // getSyncStatus 가 계속 던지면(네트워크/서버 장애) 카운터만 올라가고 아무 것도
      // 끝나지 않아 스피너가 영원히 남는다. 임계치를 넘으면 배치를 통째로 포기한다.
      syncErrorCountRef.current += 1;
      if (syncErrorCountRef.current >= SYNC_MAX_ERRORS && isMountedRef.current) {
        toast.info("동기화 상태를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.");
        setSyncingSourceIds([]);
        stopPolling();
      }
      return; // 그 전까지는 다음 주기에 재시도
    }
    if (!isMountedRef.current) return;

    const counts = missingPollsRef.current;
    const startedAt = syncStartedAtRef.current;
    const now = Date.now();
    const completed = []; // { id, job } — done/failed 로 끝난 사이트
    const timedOut = []; // id — 상태 확인 불가/시간 초과로 종료로 간주
    for (const id of syncingIdsRef.current) {
      // 절대 타임아웃: 상태(running 등)와 무관하게 시작 후 SYNC_MAX_MS 지나면 종료로 본다.
      // 백엔드 job 이 running 에 멈춰 있어도 스피너가 영원히 남지 않게 하는 최종 안전장치.
      if (startedAt[id] && now - startedAt[id] >= SYNC_MAX_MS) {
        timedOut.push(id);
        delete counts[id];
        continue;
      }
      const job = jobs[id];
      if (job && (job.status === "done" || job.status === "failed")) {
        completed.push({ id, job });
        delete counts[id];
      } else if (job) {
        counts[id] = 0; // 아직 running
      } else {
        // 상태 엔트리 없음(TTL 만료/프로세스 재시작). 두 주기 연속이면 종료로 처리해
        // 스피너·폴링이 무한정 남지 않게 한다.
        counts[id] = (counts[id] || 0) + 1;
        if (counts[id] >= 2) {
          timedOut.push(id);
          delete counts[id];
        }
      }
    }
    if (completed.length === 0 && timedOut.length === 0) return;

    const nameOf = (id) => {
      const site = sourcesRef.current.find((source) => source.id === id);
      return site?.displayName || site?.name || "사이트";
    };
    for (const { id, job } of completed) {
      if (job.status === "done") {
        const detail =
          job.inboxAdded > 0 ? `${job.inboxAdded}건 새로 추천` : "새 공지 없음";
        toast.success(`${nameOf(id)} 동기화 완료 · ${detail}`);
      } else {
        toast.error(job.message || `${nameOf(id)} 동기화 실패`);
      }
    }
    for (const id of timedOut) {
      toast.info(`${nameOf(id)} 동기화 상태를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.`);
    }

    const finishedIds = new Set([
      ...completed.map(({ id }) => id),
      ...timedOut,
    ]);
    finishedIds.forEach((id) => delete startedAt[id]); // 시작 시각 정리
    setSyncingSourceIds((prev) => prev.filter((id) => !finishedIds.has(id)));

    // 완료뿐 아니라 강제 종료(timedOut) 시에도 그 사이 반영됐을 수 있는 인박스를 한 번 새로고침.
    if (completed.length > 0 || timedOut.length > 0) {
      try {
        setNotices(await getMyInboxNotices());
      } catch {
        // 인박스 새로고침 실패는 조용히 무시
      }
      refreshAiStatus();
    }
  }, [toast, refreshAiStatus, stopPolling]);

  const ensurePolling = useCallback(() => {
    if (pollActiveRef.current) return;
    pollActiveRef.current = true;
    pollTimerRef.current = setInterval(pollSyncStatus, 2500);
  }, [pollSyncStatus]);

  // 언마운트 시 폴링 정리(인터벌 해제 + 이후 setState 차단).
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  // 세션 만료(access 토큰 만료 + refresh 재발급 실패) 시 client 가 이 핸들러를 호출한다.
  // 로그인 상태였을 때만 반응 — 최초 미인증 하이드레이트의 401 은 조용히 무시한다.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (!currentUserRef.current) return;
      currentUserRef.current = null; // 병렬 요청이 동시에 401 나도 한 번만 처리
      clearStoredUser();
      setCurrentUser(null);
      setNotices([]);
      setSources([]);
      setInterests([]);
      setSyncingSourceIds([]);
      stopPolling();
      filtersRef.current.resetForSignedOut();
      setAiStatus({ degraded: false, reason: "ok", message: "" });
      toast.info("세션이 만료됐어요. 다시 로그인해주세요.");
    });
    return () => setUnauthorizedHandler(null);
  }, [toast, stopPolling]);

  useEffect(() => {
    if (!currentUser) return;
    loadDashboardData();
    refreshAiStatus();
  }, [currentUser, loadDashboardData, refreshAiStatus]);

  // 상태가 정상으로 돌아오면 닫기 기억을 초기화 → 이후 다시 저하되면 배너를 재노출.
  useEffect(() => {
    if (!aiStatus.degraded) setAiBannerDismissedReason(null);
  }, [aiStatus.degraded]);

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
      setSyncingSourceIds([]);
      stopPolling();
      filters.resetForSignedOut();
      setAiStatus({ degraded: false, reason: "ok", message: "" });
      toast.info("로그아웃했어요.");
    }
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

  // 온디맨드 동기화(비동기): POST 로 백그라운드 작업을 시작(즉시 반환)하고 사이트를
  // syncingSourceIds 에 넣은 뒤, 폴링 루프가 완료를 사이트별로 반영하게 한다.
  // opts.silentUnsupported: 첫 구독 직후 자동 호출 시 '자동 수집 미지원(400)'은 조용히 넘긴다.
  const handleSyncSource = useCallback(
    async (sourceId, opts = {}) => {
      try {
        await syncSource(sourceId); // POST → { status: "started" } (빠르게 반환)
      } catch (error) {
        if (opts.silentUnsupported && error?.status === 400) {
          console.info("sync skipped:", error.message);
        } else {
          toast.error(error.message || "동기화에 실패했어요.");
        }
        return;
      }
      syncStartedAtRef.current[sourceId] = Date.now(); // 절대 타임아웃 기준 시각 기록
      setSyncingSourceIds((prev) =>
        prev.includes(sourceId) ? prev : [...prev, sourceId],
      );
      ensurePolling();
    },
    [toast, ensurePolling],
  );

  // 전체 동기화: 구독 중인 모든 사이트의 백그라운드 작업을 시작(enqueue)하고 폴링에 맡긴다.
  // 워커가 순차 처리하므로 완료 토스트는 사이트별로 하나씩 나타난다.
  const handleSyncAll = useCallback(async () => {
    const ids = sources.filter((source) => source.isSubscribed).map((source) => source.id);
    if (ids.length === 0) return;

    const enqueued = [];
    await Promise.all(
      ids.map(async (id) => {
        try {
          await syncSource(id);
          enqueued.push(id);
        } catch {
          // 개별 사이트 실패(자동 수집 미지원 등)는 무시하고 전체는 계속 진행
        }
      }),
    );
    if (enqueued.length === 0) {
      toast.info("동기화할 수 있는 사이트가 없어요.");
      return;
    }
    const startedAt = Date.now();
    enqueued.forEach((id) => {
      syncStartedAtRef.current[id] = startedAt; // 절대 타임아웃 기준 시각 기록
    });
    setSyncingSourceIds((prev) => {
      const next = new Set(prev);
      enqueued.forEach((id) => next.add(id));
      return Array.from(next);
    });
    ensurePolling();
  }, [sources, toast, ensurePolling]);

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
  // 서버 저장은 best-effort — 실패해도 열람을 막지 않는다(로컬은 이미 읽음).
  const handleOpenNotice = (notice) => {
    if (!notice.isRead) {
      setNotices((prev) =>
        prev.map((item) =>
          item.inboxNoticeId === notice.inboxNoticeId
            ? { ...item, isRead: true }
            : item,
        ),
      );
      markInboxNoticeRead(notice.inboxNoticeId).catch((error) => console.error(error));
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

  const handleToggleSave = async (inboxNoticeId) => {
    const targetNotice = notices.find(
      (notice) => notice.inboxNoticeId === inboxNoticeId,
    );
    if (!targetNotice) return;

    const nextIsSaved = !targetNotice.isSaved;
    const applySaved = (saved) =>
      setNotices((prev) =>
        prev.map((notice) =>
          notice.inboxNoticeId === inboxNoticeId
            ? { ...notice, isSaved: saved }
            : notice,
        ),
      );

    applySaved(nextIsSaved);
    try {
      await toggleInboxNoticeSave(inboxNoticeId, nextIsSaved);
    } catch (error) {
      console.error(error);
      applySaved(!nextIsSaved);
      toast.error("저장 상태 변경에 실패했어요.");
    }
  };

  // 상세 모달은 notices 에서 파생 — 저장 토글 등 갱신이 모달에 즉시 반영된다.
  const selectedNotice = useMemo(
    () => notices.find((notice) => notice.inboxNoticeId === selectedNoticeId) || null,
    [notices, selectedNoticeId],
  );

  // AI 저하 배너: 저하 상태이고, 이번 세션에 같은 사유로 닫지 않았을 때만 노출.
  const showAiBanner =
    aiStatus.degraded && aiBannerDismissedReason !== aiStatus.reason;

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
  } else if (currentUser.onboarded === false) {
    content = (
      <OnboardingWizard user={currentUser} onComplete={handleOnboardingComplete} />
    );
  } else {
    content = (
      <div className="app">
        <Header
          currentUser={currentUser}
          searchQuery={filters.searchQuery}
          onSearchChange={filters.setSearchQuery}
          onOpenAuth={handleOpenAuth}
          onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
          onOpenInterestSetting={() => setIsInterestSettingOpen(true)}
          onOpenProfileSetting={() => setIsProfileSettingOpen(true)}
          onOpenAlertSettings={() => setIsAlertSettingsOpen(true)}
          onLogout={handleLogout}
        />

        <div className="dashboard">
          <Sidebar
            sources={sources}
            selectedView={filters.selectedView}
            onChangeView={filters.setSelectedView}
            onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
            aiCount={filters.aiCount}
            savedCount={filters.savedCount}
            activeSourceIds={filters.activeSourceIds}
            onToggleSource={filters.toggleSource}
            syncingSourceIds={syncingSourceIds}
            onSyncSource={handleSyncSource}
            onSyncAll={handleSyncAll}
            onRenameSource={handleRenameSource}
          />

          <main className="main">
            {showAiBanner && (
              <AiStatusBanner
                reason={aiStatus.reason}
                message={aiStatus.message}
                onDismiss={() => setAiBannerDismissedReason(aiStatus.reason)}
              />
            )}

            <section className="noticeSection">
              <NoticeToolbar
                view={filters.selectedView}
                count={filters.filteredNotices.length}
                selectedCategory={filters.selectedCategory}
                onSelectCategory={filters.setSelectedCategory}
                interests={interests}
                selectedInterests={filters.selectedInterests}
                onToggleInterest={filters.toggleInterest}
                onClearInterests={() => filters.setSelectedInterests([])}
              />

              <div
                className="viewFade"
                key={`${filters.selectedView}-${filters.selectedCategory}-${filters.selectedInterests.join(",")}`}
              >
                <NoticeList
                  loading={dashboardLoading}
                  error={dashboardError}
                  onRetry={loadDashboardData}
                  notices={filters.paginatedNotices}
                  hasSubscriptions={sources.some((source) => source.isSubscribed)}
                  searchQuery={filters.searchQuery}
                  selectedView={filters.selectedView}
                  activeSourceCount={filters.activeSourceIds.length}
                  onOpenSiteRegister={() => setIsSiteRegisterOpen(true)}
                  onOpenNotice={handleOpenNotice}
                  onToggleSave={handleToggleSave}
                />
              </div>

              {!dashboardLoading && filters.filteredNotices.length > filters.perPage && (
                <div className="pagination">
                  {Array.from({ length: filters.totalPages }, (_, index) => {
                    const pageNumber = index + 1;
                    return (
                      <button
                        key={pageNumber}
                        className={`pageButton ${
                          filters.currentPage === pageNumber ? "active" : ""
                        }`}
                        aria-current={
                          filters.currentPage === pageNumber ? "page" : undefined
                        }
                        onClick={() => filters.setCurrentPage(pageNumber)}
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

      {isProfileSettingOpen && (
        <ProfileSettingModal
          currentUser={currentUser}
          onClose={() => setIsProfileSettingOpen(false)}
          onSaved={(user) => {
            const nextUser = { ...currentUser, ...user };
            setCurrentUser(nextUser);
            saveStoredUser(nextUser);
          }}
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
