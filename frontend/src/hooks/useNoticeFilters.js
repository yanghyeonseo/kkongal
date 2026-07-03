import { useEffect, useMemo, useState } from "react";
import { filterNotices } from "../utils/noticeFilters.js";

const NOTICES_PER_PAGE = 5;

/**
 * 대시보드 공지 필터링 상태와 파생 목록을 관리한다.
 * 뷰/카테고리/관심사/소스/검색어/페이지 상태를 소유하고, 필터 적용된 목록과
 * 페이지 슬라이스, 배지 카운트를 계산한다.
 */
export function useNoticeFilters(notices, interests = []) {
  const [selectedView, setSelectedView] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedInterests, setSelectedInterests] = useState([]);
  const [activeSourceIds, setActiveSourceIds] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedView, selectedCategory, selectedInterests, activeSourceIds, searchQuery]);

  // 관심사 목록이 바뀌면(삭제 등) selectedInterests 를 현재 키워드와의 교집합으로 정리한다.
  // 이렇게 하지 않으면 삭제된 관심사가 칩은 사라진 채로 계속 필터링해(보이지 않는 필터)
  // 공지가 이유 없이 비어 보인다.
  useEffect(() => {
    const keywords = new Set(interests.map((interest) => interest.keyword));
    setSelectedInterests((prev) => {
      const next = prev.filter((keyword) => keywords.has(keyword));
      return next.length === prev.length ? prev : next;
    });
  }, [interests]);

  const sourceFilteredNotices = useMemo(() => {
    if (activeSourceIds.length === 0) return [];
    return notices.filter((notice) => activeSourceIds.includes(notice.sourceId));
  }, [notices, activeSourceIds]);

  // 저장됨/AI 뷰는 소스 토글과 무관하게 전체 notices 기준(durable). '전체' 뷰만 소스 필터를 적용한다.
  const filteredNotices = useMemo(() => {
    const base =
      selectedView === "saved" || selectedView === "ai" ? notices : sourceFilteredNotices;
    return filterNotices(base, {
      view: selectedView,
      category: selectedCategory,
      interests: selectedInterests,
      query: searchQuery,
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

  // 필터된 목록이 줄어(예: 2페이지에서 저장 해제 → 항목이 빠짐) 현재 페이지가 범위를
  // 벗어나면 마지막 페이지로 당긴다. 안 그러면 빈 슬라이스가 나와 가짜 빈 상태가 뜬다.
  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const paginatedNotices = useMemo(() => {
    const startIndex = (currentPage - 1) * NOTICES_PER_PAGE;
    return filteredNotices.slice(startIndex, startIndex + NOTICES_PER_PAGE);
  }, [filteredNotices, currentPage]);

  // 배지/카운트는 사이드바 소스 토글과 무관하게 전체 notices 기준으로 센다.
  // AI 배지는 안 읽은 추천 공지 수만 표시(읽으면 배지에서 빠짐).
  const aiCount = useMemo(
    () => notices.filter((n) => n.isRecommended && !n.isRead).length,
    [notices],
  );
  const savedCount = useMemo(
    () => notices.filter((notice) => notice.isSaved).length,
    [notices],
  );

  const toggleSource = (sourceId) =>
    setActiveSourceIds((prev) =>
      prev.includes(sourceId)
        ? prev.filter((id) => id !== sourceId)
        : [...prev, sourceId],
    );

  const toggleInterest = (keyword) =>
    setSelectedInterests((prev) =>
      prev.includes(keyword)
        ? prev.filter((item) => item !== keyword)
        : [...prev, keyword],
    );

  const resetForSignedOut = () => {
    setSelectedView("all");
    setSearchQuery("");
    setActiveSourceIds([]);
  };

  return {
    selectedView,
    setSelectedView,
    selectedCategory,
    setSelectedCategory,
    selectedInterests,
    setSelectedInterests,
    activeSourceIds,
    setActiveSourceIds,
    searchQuery,
    setSearchQuery,
    currentPage,
    setCurrentPage,
    filteredNotices,
    paginatedNotices,
    totalPages,
    perPage: NOTICES_PER_PAGE,
    aiCount,
    savedCount,
    toggleSource,
    toggleInterest,
    resetForSignedOut,
  };
}
