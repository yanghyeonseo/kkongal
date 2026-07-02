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

// 지원 사이트 카탈로그: config 기반 목록.
// 백엔드: [{ name, url, category, subscribed: bool, source_id: int|null }]
function normalizeCatalogItem(item) {
  const url = item.url ?? "";
  const name = (item.name && item.name.trim()) || displayNameFromUrl(url);
  return {
    name,
    url,
    category: item.category ?? "etc",
    subscribed: item.subscribed ?? false,
    sourceId: item.source_id ?? null,
  };
}

export async function getSourceCatalog() {
  const data = await apiRequest("/api/sources/catalog/");
  return Array.isArray(data) ? data.map(normalizeCatalogItem) : [];
}

// 온디맨드 동기화: 해당 소스를 즉시 크롤+선별한다.
// 백엔드: { crawled, fetched, new_notices, inbox_added, message }
export async function syncSource(sourceId) {
  const data = await apiRequest(`/api/sources/${sourceId}/sync/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    crawled: data?.crawled ?? false,
    fetched: Number(data?.fetched ?? 0),
    newNotices: Number(data?.new_notices ?? 0),
    inboxAdded: Number(data?.inbox_added ?? 0),
    message: data?.message ?? "",
  };
}
