function NoticeCard({ notice }) {
  const score = Math.round(notice.relevanceScore * 100);

  return (
    <article className="noticeCard">
      <div className="noticeLogo">{notice.sourceDisplayName.slice(0, 1)}</div>

      <div className="noticeContent">
        <p>{notice.sourceDisplayName}</p>
        <h3>{notice.title}</h3>
        <span>{notice.description}</span>

        <div className="keywordList">
          {notice.matchedKeywords.map((keyword) => (
            <em key={keyword}>{keyword}</em>
          ))}
        </div>

        <p className="reason">{notice.reason}</p>
      </div>

      <div className="noticeMeta">
        <b>AI {score}%</b>

        {notice.isNew && <strong className="newBadge">NEW</strong>}
        {notice.isDeadlineSoon && (
          <strong className="deadlineBadge">마감임박</strong>
        )}

        <span>{notice.isRead ? "읽음" : "안 읽음"}</span>

        <a href={notice.url} target="_blank" rel="noreferrer">
          원문 보기
        </a>
      </div>
    </article>
  );
}

export default NoticeCard;
