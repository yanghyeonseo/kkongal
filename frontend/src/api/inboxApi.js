import { apiRequest } from "./client.js";
import { mockInboxNotices } from "../data/mockInboxNotices.js";

const USE_MOCK = true;

function parseMatchedKeywords(value) {
  if (!value) return [];

  if (Array.isArray(value)) return value;

  if (typeof value === "string") {
    return value
      .split(",")
      .map((keyword) => keyword.trim())
      .filter(Boolean);
  }

  return [];
}

function normalizeInboxNotice(item) {
  const notice = item.notice || {};
  const source = notice.source || {};

  const deadlineAt = item.deadline_at ?? notice.deadline_at ?? null;

  return {
    inboxNoticeId: item.id,
    noticeId: item.notice_id ?? notice.id,

    sourceId: notice.source_id ?? source.id,
    sourceName: source.name ?? "",
    sourceDisplayName: source.name ?? "공지 사이트",

    category: "etc",

    title: notice.title ?? "",
    description: notice.content?.slice(0, 80) ?? "",
    url: notice.url ?? "",

    publishedAt: notice.published_at ?? null,
    deadlineAt,

    relevanceScore: Number(item.relevance_score ?? 0),
    matchedInterestTags: parseMatchedKeywords(item.matched_keywords),

    reason: item.reason ?? "",

    isRead: item.is_read ?? false,
    isSaved: item.is_saved ?? false,
    isDeadlineSoon: Boolean(deadlineAt),
  };
}

export async function getMyInboxNotices({ saved = false } = {}) {
  if (USE_MOCK) {
    if (saved) {
      return mockInboxNotices.filter((notice) => notice.isSaved);
    }

    return mockInboxNotices;
  }

  const query = saved ? "?saved=true" : "";
  const data = await apiRequest(`/api/notices/inbox/${query}`);

  return data.map(normalizeInboxNotice);
}

export async function toggleInboxNoticeSave(inboxNoticeId, isSaved) {
  if (USE_MOCK) {
    return {
      id: inboxNoticeId,
      is_saved: isSaved,
    };
  }

  const data = await apiRequest(`/api/notices/inbox/${inboxNoticeId}/save/`, {
    method: "PATCH",
    body: JSON.stringify({
      is_saved: isSaved,
    }),
  });

  return normalizeInboxNotice(data);
}
