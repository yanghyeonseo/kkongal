import { useState } from "react";
import { Zap, Bookmark } from "lucide-react";
import { formatRelativeTime, isToday, calculateDday } from "../utils/date.js";

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

  const isAiMatched =
    notice.relevanceScore >= 0.8 ||
    (notice.matchedInterestTags && notice.matchedInterestTags.length > 0);

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
          style={{
            backgroundColor: getLogoColor(notice.sourceDisplayName),
          }}
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
          </button>

          <span>{notice.description}</span>
        </div>

        <div className="noticeMeta">
          {isAiMatched && (
            <button
              className={`aiMatchBadge ${isAiReasonOpen ? "active" : ""}`}
              onClick={handleToggleAiReason}
            >
              <Zap size={12} />
              AI 매치
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

          {isAiMatched && (
            <span
              className={`aiReasonIcon ${isAiReasonOpen ? "active" : ""}`}
              aria-hidden="true"
            >
              <Zap size={14} />
            </span>
          )}

          <button
            className={`saveIconButton ${notice.isSaved ? "saved" : ""}`}
            onClick={handleToggleSave}
            aria-label="공지 저장"
          >
            <Bookmark
              size={15}
              fill={notice.isSaved ? "currentColor" : "none"}
            />
          </button>
        </div>
      </div>

      {isAiMatched && isAiReasonOpen && (
        <div className="aiReasonBox">
          <p className="aiReasonTitle">
            <Zap size={14} />
            AI 선별 이유
          </p>

          <p className="aiReasonText">
            {notice.reason ||
              "사용자의 관심사 태그와 공지 내용이 관련성이 높습니다."}
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
