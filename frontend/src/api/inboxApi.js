import { apiRequest } from "./client.js";

function displayNameFromUrl(url) {
  if (!url) return "공지 사이트";
  try {
    const { hostname } = new URL(url);
    return hostname.replace(/^www\./, "");
  } catch {
    return "공지 사이트";
  }
}

// matched_keywords 는 계약상 콤마-join 문자열이지만, JSON 배열 문자열이 올 수도 있어 방어적으로 파싱.
function parseMatchedKeywords(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean);

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.map((v) => String(v).trim()).filter(Boolean);
        }
      } catch {
        // fallthrough → 콤마 분리
      }
    }
    return trimmed
      .split(",")
      .map((keyword) => keyword.trim())
      .filter(Boolean);
  }

  return [];
}

function getIsDeadlineSoon(deadlineAt) {
  if (!deadlineAt) return false;

  const today = new Date();
  const deadline = new Date(deadlineAt);

  today.setHours(0, 0, 0, 0);
  deadline.setHours(0, 0, 0, 0);

  const diffDays = Math.ceil((deadline - today) / (1000 * 60 * 60 * 24));
  return diffDays >= 0 && diffDays <= 7;
}

function normalizeInboxNotice(item) {
  const notice = item.notice || {};
  const source = notice.source || {};

  const deadlineAt = item.deadline_at ?? notice.deadline_at ?? null;
  const sourceName =
    (source.name && source.name.trim()) || displayNameFromUrl(notice.url);

  return {
    inboxNoticeId: item.id,
    noticeId: item.notice_id ?? notice.id,

    sourceId: notice.source_id ?? source.id,
    sourceName,
    sourceDisplayName: sourceName,

    title: notice.title ?? "",
    description: (notice.content ?? "").slice(0, 90),
    url: notice.url ?? "",
    publisher: notice.publisher ?? "",

    publishedAt: notice.published_at ?? null,
    deadlineAt,

    relevanceScore: Number(item.relevance_score ?? 0),
    matchedInterestTags: parseMatchedKeywords(item.matched_keywords),
    reason: item.reason ?? "",

    isRead: item.is_read ?? false,
    isSaved: item.is_saved ?? false,
    isDeadlineSoon: getIsDeadlineSoon(deadlineAt),
  };
}

export async function getMyInboxNotices({ saved } = {}) {
  const query = saved === true ? "?saved=true" : saved === false ? "?saved=false" : "";
  const data = await apiRequest(`/api/notices/inbox/${query}`);
  return Array.isArray(data) ? data.map(normalizeInboxNotice) : [];
}

export async function toggleInboxNoticeSave(inboxNoticeId, isSaved) {
  const data = await apiRequest(`/api/notices/inbox/${inboxNoticeId}/save/`, {
    method: "PATCH",
    body: JSON.stringify({ is_saved: isSaved }),
  });
  return normalizeInboxNotice(data);
}
