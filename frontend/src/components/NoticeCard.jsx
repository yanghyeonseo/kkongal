import { useState } from "react";
import { formatRelativeTime, isToday, calculateDday } from "../utils/date.js";

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
        <div className="noticeLogo">{notice.sourceDisplayName.slice(0, 1)}</div>

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
              ⚡ AI 매치
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
              ⚡
            </span>
          )}

          <button
            className={`saveIconButton ${notice.isSaved ? "saved" : ""}`}
            onClick={handleToggleSave}
            aria-label="공지 저장"
          >
            {notice.isSaved ? "★" : "☆"}
          </button>
        </div>
      </div>

      {isAiMatched && isAiReasonOpen && (
        <div className="aiReasonBox">
          <p className="aiReasonTitle">⚡ AI 선별 이유</p>

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
