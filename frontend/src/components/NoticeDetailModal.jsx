import { Sparkles, CalendarDays, CalendarClock, ExternalLink, Bookmark } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import Markdown from "./Markdown.jsx";
import SourceFavicon from "./SourceFavicon.jsx";
import { formatDate, calculateDday } from "../utils/date.js";
import { isAiMatched, relevanceTier } from "../utils/relevance.js";

function ddayLabel(dDay) {
  if (dDay === null) return null;
  if (dDay === 0) return "오늘 마감";
  if (dDay > 0) return `D-${dDay}`;
  return "마감됨";
}

// summary 는 보통 3문장 한 덩어리. 문장 끝/줄바꿈 기준으로 나눠 3줄로 보여준다.
function splitSummary(summary) {
  if (!summary) return [];
  const byLine = summary
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (byLine.length > 1) return byLine;

  const bySentence = summary
    .split(/(?<=[.!?。])\s+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return bySentence.length > 0 ? bySentence : [summary.trim()];
}

function NoticeDetailModal({ notice, onClose, onToggleSave }) {
  if (!notice) return null;

  const aiMatched = isAiMatched(notice);
  const scorePercent = Math.round((Number(notice.relevanceScore) || 0) * 100);
  const scoreTier = relevanceTier(notice.relevanceScore);
  const dDay = calculateDday(notice.deadlineAt);
  const dLabel = ddayLabel(dDay);
  const expired = dDay !== null && dDay < 0;
  const summaryLines = splitSummary(notice.summary);
  const tags = notice.matchedInterestTags || [];

  const handleSave = () => onToggleSave?.(notice.inboxNoticeId);

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title={notice.title || "공지 상세"}
      subtitle={notice.sourceDisplayName}
      footer={
        <>
          <button
            type="button"
            className={`ghostButton ${notice.isSaved ? "isSaved" : ""}`}
            onClick={handleSave}
          >
            <Bookmark size={15} fill={notice.isSaved ? "currentColor" : "none"} />
            {notice.isSaved ? "저장됨" : "저장"}
          </button>
          {notice.url && (
            <a
              className="primaryButton"
              href={notice.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              원문 보기 <ExternalLink size={15} />
            </a>
          )}
        </>
      }
    >
      <div className="detailMetaBar">
        <SourceFavicon
          name={notice.sourceDisplayName}
          faviconUrl={notice.sourceFaviconUrl}
          siteUrl={notice.url}
          size={40}
          rounded="12px"
        />
        <div className="detailMetaText">
          <strong>{notice.sourceDisplayName}</strong>
          <div className="detailDates">
            {notice.publishedAt && (
              <span>
                <CalendarDays size={14} aria-hidden="true" />
                게시 {formatDate(notice.publishedAt)}
              </span>
            )}
            {notice.deadlineAt && (
              <span className={expired ? "isPast" : ""}>
                <CalendarClock size={14} aria-hidden="true" />
                마감 {formatDate(notice.deadlineAt)}
                {dLabel && <em className="detailDday">{dLabel}</em>}
              </span>
            )}
          </div>
        </div>

        {aiMatched && (
          <div className={`detailAiSeal tier-${scoreTier}`} title={`AI 매칭 ${scorePercent}%`}>
            <Sparkles size={15} aria-hidden="true" />
            <b>{scorePercent}%</b>
            <span>AI 매칭</span>
          </div>
        )}
      </div>

      {aiMatched && (notice.reason || tags.length > 0) && (
        <section className="detailSection detailReason">
          <p className="detailSectionTitle">
            <Sparkles size={14} aria-hidden="true" /> 선별 이유
          </p>
          <p className="detailReasonText">
            {notice.reason || "사용자의 관심 조건과 공지 내용의 관련성이 높습니다."}
          </p>
          {tags.length > 0 && (
            <div className="detailTagRow">
              {tags.map((tag) => (
                <em key={tag}>{tag}</em>
              ))}
            </div>
          )}
        </section>
      )}

      {summaryLines.length > 0 && (
        <section className="detailSection">
          <p className="detailSectionTitle">3줄 요약</p>
          <ul className="detailSummaryList">
            {summaryLines.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="detailSection">
        <p className="detailSectionTitle">본문</p>
        {notice.contentMarkdown ? (
          <Markdown text={notice.contentMarkdown} />
        ) : notice.content ? (
          <p className="detailPlainBody">{notice.content}</p>
        ) : (
          <p className="detailEmptyBody">본문 내용이 아직 없어요. 원문에서 확인해주세요.</p>
        )}
      </section>
    </ModalShell>
  );
}

export default NoticeDetailModal;
