import { apiRequest } from "./client.js";

function normalizeInboxNotice(item) {
  const notice = item.notice || item;
  const source = item.source || notice.source || {};

  return {
    inboxNoticeId: item.id ?? item.inbox_notice_id ?? item.inboxNoticeId,
    noticeId: item.notice_id ?? notice.id ?? item.noticeId,

    sourceId: item.source_id ?? source.id ?? item.sourceId,
    sourceName: item.source_name ?? source.name ?? item.sourceName ?? "",
    sourceDisplayName:
      item.source_display_name ??
      source.display_name ??
      source.name ??
      item.sourceDisplayName ??
      "공지 사이트",

    category:
      item.category ??
      source.category ??
      source.source_type ??
      item.sourceType ??
      "etc",

    title: item.title ?? notice.title ?? "",
    description:
      item.description ??
      item.content_summary ??
      notice.description ??
      notice.content?.slice(0, 80) ??
      "",
    url: item.url ?? notice.url ?? "",

    publishedAt:
      item.published_at ??
      notice.published_at ??
      item.publishedAt ??
      notice.publishedAt,

    deadlineAt:
      item.deadline_at ??
      notice.deadline_at ??
      item.deadlineAt ??
      notice.deadlineAt ??
      null,

    relevanceScore: Number(item.relevance_score ?? item.relevanceScore ?? 0),

    matchedInterestTags:
      item.matched_interest_tags ??
      item.matched_keywords ??
      item.matchedInterestTags ??
      item.matchedKeywords ??
      [],

    reason: item.reason ?? "",

    isRead: item.is_read ?? item.isRead ?? false,
    isSaved: item.is_saved ?? item.isSaved ?? false,
    isDeadlineSoon: item.is_deadline_soon ?? item.isDeadlineSoon ?? false,
  };
}

export async function getMyInboxNotices() {
  const data = await apiRequest("/api/notices/inbox/");
  return data.map(normalizeInboxNotice);
}
