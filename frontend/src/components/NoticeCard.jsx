import { useState } from "react";
import { Sparkles, Bookmark, ChevronDown, ExternalLink } from "lucide-react";
import { formatRelativeTime, isToday, calculateDday } from "../utils/date.js";
import { isAiMatched, formatRelevance, relevanceTier } from "../utils/relevance.js";

const LOGO_COLORS = [
  "#1677f2",
  "#ef2b55",
  "#ff6b2c",
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
];

function getLogoColor(sourceName) {
  if (!sourceName) return LOGO_COLORS[0];

  let hash = 0;
  for (let i = 0; i < sourceName.length; i += 1) {
    hash += sourceName.charCodeAt(i);
  }
  return LOGO_COLORS[hash % LOGO_COLORS.length];
}

function NoticeCard({ notice, onOpenNotice, onToggleSave }) {
  const [isAiReasonOpen, setIsAiReasonOpen] = useState(false);

  const isTodayNotice = isToday(notice.publishedAt);
  const dDay = calculateDday(notice.deadlineAt);
  const aiMatched = isAiMatched(notice);
  const tier = relevanceTier(notice.relevanceScore);
  const scorePercent = Math.round((Number(notice.relevanceScore) || 0) * 100);

  const handleToggleAiReason = (event) => {
    event.stopPropagation();
    setIsAiReasonOpen((prev) => !prev);
  };

  const handleToggleSave = (event) => {
    event.stopPropagation();
    onToggleSave(notice.inboxNoticeId);
  };

  return (
    <article
      className={`noticeCard ${notice.isRead ? "read" : ""} ${
        isAiReasonOpen ? "aiOpen" : ""
      }`}
    >
      <div className="noticeTop">
        <div
          className="noticeLogo"
          style={{ backgroundColor: getLogoColor(notice.sourceDisplayName) }}
          aria-hidden="true"
        >
          {notice.sourceDisplayName.slice(0, 1)}
        </div>

        <div className="noticeContent">
          <p>{notice.sourceDisplayName}</p>

          <button
            className="noticeTitleButton"
            onClick={() => onOpenNotice(notice)}
          >
            {notice.title}
            <ExternalLink size={14} className="titleExternalIcon" aria-hidden="true" />
          </button>

          {notice.description && <span>{notice.description}</span>}
        </div>

        <div className="noticeMeta">
          {aiMatched && (
            <button
              className={`aiScorePill tier-${tier} ${isAiReasonOpen ? "active" : ""}`}
              onClick={handleToggleAiReason}
              aria-expanded={isAiReasonOpen}
              aria-label={`AI 관련도 ${scorePercent}퍼센트, 선별 이유 보기`}
            >
              <Sparkles size={12} aria-hidden="true" />
              <span>AI {formatRelevance(notice.relevanceScore)}</span>
              <ChevronDown
                size={13}
                className={`aiPillChevron ${isAiReasonOpen ? "open" : ""}`}
                aria-hidden="true"
              />
            </button>
          )}

          {isTodayNotice && <strong className="newBadge">NEW</strong>}

          {notice.isDeadlineSoon && (
            <div className="deadlineGroup">
              <strong className="deadlineBadge">마감임박</strong>
              {dDay !== null && (
                <strong className="deadlineDday">
                  {dDay === 0 ? "D-DAY" : dDay > 0 ? `D-${dDay}` : "마감"}
                </strong>
              )}
            </div>
          )}

          <span className="noticeTime">
            {formatRelativeTime(notice.publishedAt)}
          </span>

          <button
            className={`saveIconButton ${notice.isSaved ? "saved" : ""}`}
            onClick={handleToggleSave}
            aria-pressed={notice.isSaved}
            aria-label={notice.isSaved ? "저장 해제" : "공지 저장"}
          >
            <Bookmark size={15} fill={notice.isSaved ? "currentColor" : "none"} />
          </button>
        </div>
      </div>

      {aiMatched && isAiReasonOpen && (
        <div className="aiReasonBox">
          <div className="aiReasonHead">
            <p className="aiReasonTitle">
              <Sparkles size={14} aria-hidden="true" />
              AI 선별 이유
            </p>
            <span className={`aiReasonScore tier-${tier}`}>
              관련도 {formatRelevance(notice.relevanceScore)}
            </span>
          </div>

          <div
            className="relevanceMeter"
            role="meter"
            aria-valuenow={scorePercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="AI 관련도"
          >
            <span
              className={`relevanceMeterFill tier-${tier}`}
              style={{ width: `${scorePercent}%` }}
            />
          </div>

          <p className="aiReasonText">
            {notice.reason ||
              "사용자의 관심 조건과 공지 내용의 관련성이 높습니다."}
          </p>

          {notice.matchedInterestTags?.length > 0 && (
            <div className="aiMatchedTagRow">
              <span>일치 조건</span>
              <div className="aiMatchedTags">
                {notice.matchedInterestTags.map((tag) => (
                  <em key={tag}>{tag}</em>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default NoticeCard;
