import { apiRequest } from "./client.js";

// URL 에서 사람이 읽기 좋은 사이트 이름을 유추한다.
// 사용자가 직접 등록한 소스는 백엔드 name 이 비어있을 수 있어 host 로 대체한다.
function displayNameFromUrl(url) {
  if (!url) return "공지 사이트";
  try {
    const { hostname } = new URL(url);
    return hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// 백엔드 SourceSubscriptionSerializer:
// { id, user_id, source_id, source: { id, name, url, crawl_interval_minutes, ... } }
function normalizeSource(item) {
  const source = item.source || item;
  const url = source.url ?? "";
  const name = (source.name && source.name.trim()) || displayNameFromUrl(url);

  return {
    id: source.id ?? item.source_id ?? item.id,
    subscriptionId: item.id,
    name,
    displayName: name,
    url,
    isSubscribed: true,
  };
}

export async function getNoticeSources() {
  const data = await apiRequest("/api/subscriptions/");
  return Array.isArray(data) ? data.map(normalizeSource) : [];
}

// 사이트 등록: 백엔드는 url 만 받아 전역 NoticeSource 를 get_or_create 하고 구독을 연결한다.
export async function createSourceSubscription({ url }) {
  const data = await apiRequest("/api/subscriptions/", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  return normalizeSource(data);
}

export async function deleteSourceSubscription(subscriptionId) {
  return apiRequest(`/api/subscriptions/${subscriptionId}/`, {
    method: "DELETE",
  });
}
