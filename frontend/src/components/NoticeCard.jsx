import { Sparkles, Bookmark } from "lucide-react";
import { formatRelativeTime, calculateDday } from "../utils/date.js";
import { isAiMatched } from "../utils/relevance.js";
import SourceFavicon from "./SourceFavicon.jsx";

function ddayLabel(dDay) {
  if (dDay === null) return null;
  if (dDay === 0) return "D-DAY";
  if (dDay > 0) return `D-${dDay}`;
  return "마감";
}

function NoticeCard({ notice, onOpenNotice, onToggleSave }) {
  const dDay = calculateDday(notice.deadlineAt);
  const dLabel = ddayLabel(dDay);
  const aiMatched = isAiMatched(notice);
  const scorePercent = Math.round((Number(notice.relevanceScore) || 0) * 100);

  let ddayVariant = "";
  if (dDay !== null) {
    if (dDay < 0) ddayVariant = "expired";
    else if (dDay <= 3) ddayVariant = "urgent";
  }

  const open = () => onOpenNotice(notice);

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  };

  const handleToggleSave = (event) => {
    event.stopPropagation();
    onToggleSave(notice.inboxNoticeId);
  };

  return (
    <div
      className={`noticeCard ${notice.isRead ? "read" : ""} ${aiMatched ? "aiMatched" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`${notice.title} 상세 보기`}
      onClick={open}
      onKeyDown={handleKeyDown}
    >
      <span className="noticeUnreadSlot" aria-hidden="true">
        {!notice.isRead && <span className="noticeUnreadDot" />}
      </span>

      <div className="noticeLead">
        <SourceFavicon
          name={notice.sourceDisplayName}
          faviconUrl={notice.sourceFaviconUrl}
          size={46}
        />
        {aiMatched && (
          <span className="noticeAiMark" title={`AI 매칭 ${scorePercent}%`}>
            <span className="noticeAiGlow">
              <Sparkles size={15} className="noticeAiSpark" aria-hidden="true" />
            </span>
            <b>{scorePercent}%</b>
          </span>
        )}
      </div>

      <div className="noticeContent">
        <p className="noticeSource">{notice.sourceDisplayName}</p>
        <h3 className="noticeTitleText">{notice.title}</h3>
        {notice.description && <span className="noticeSnippet">{notice.description}</span>}
      </div>

      <div className="noticeMeta">
        {dLabel && (
          <strong className={`deadlineDday ${ddayVariant}`}>{dLabel}</strong>
        )}
        <span className="noticeTime">{formatRelativeTime(notice.publishedAt)}</span>
        <button
          className={`saveIconButton ${notice.isSaved ? "saved" : ""}`}
          onClick={handleToggleSave}
          aria-pressed={notice.isSaved}
          aria-label={notice.isSaved ? "저장 해제" : "공지 저장"}
        >
          <Bookmark size={16} fill={notice.isSaved ? "currentColor" : "none"} />
        </button>
      </div>
    </div>
  );
}

export default NoticeCard;
