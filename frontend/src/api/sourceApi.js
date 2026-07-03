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
// { id, user_id, source_id, source: { id, name, url, favicon_url, crawl_interval_minutes, ... } }
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
    faviconUrl: source.favicon_url ?? "",
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

// 표시명 편집: PATCH /api/sources/{id}/ { name } → 갱신된 source 반환.
// 응답은 subscription wrapper 가 아닌 bare source 일 수 있어 방어적으로 파싱한다.
export async function updateSourceName(sourceId, name) {
  const data = await apiRequest(`/api/sources/${sourceId}/`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
  const source = (data && (data.source || data)) || {};
  const url = source.url ?? "";
  const nextName = (source.name && source.name.trim()) || name || displayNameFromUrl(url);
  return {
    id: source.id ?? sourceId,
    name: nextName,
    displayName: nextName,
    url,
    faviconUrl: source.favicon_url ?? "",
  };
}

// 지원 사이트 카탈로그: config 기반 목록 + 사용자가 추가해 공개된 커스텀 사이트.
// 백엔드: [{ name, url, category, favicon_url, source_id, subscribed, custom }]
// custom=true 는 다른 사용자가 URL로 직접 등록해 발견 가능해진 사이트.
function normalizeCatalogItem(item) {
  const url = item.url ?? "";
  const name = (item.name && item.name.trim()) || displayNameFromUrl(url);
  return {
    name,
    url,
    category: item.category ?? "etc",
    subscribed: item.subscribed ?? false,
    sourceId: item.source_id ?? null,
    faviconUrl: item.favicon_url ?? "",
    custom: item.custom ?? false,
  };
}

export async function getSourceCatalog() {
  const data = await apiRequest("/api/sources/catalog/");
  return Array.isArray(data) ? data.map(normalizeCatalogItem) : [];
}

// 온디맨드 동기화(비동기 시작): 백엔드가 백그라운드 작업을 큐에 넣고 즉시 반환한다.
// 백엔드: { status: "started", source_id }. 미지원 사이트는 400 → 호출자가 처리한다.
export async function syncSource(sourceId) {
  const data = await apiRequest(`/api/sources/${sourceId}/sync/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    status: data?.status ?? "started",
    sourceId: data?.source_id ?? sourceId,
  };
}

// 동기화 진행 상태 폴링: 구독 사이트들의 작업 상태 맵을 반환한다.
// 백엔드: { jobs: { "<source_id>": { status, inbox_added, message } } } (idle 은 생략).
// → { [sourceId:number]: { status, inboxAdded, message } } 로 정규화한다.
export async function getSyncStatus() {
  const data = await apiRequest("/api/sources/sync/status/");
  const jobs = (data && data.jobs) || {};
  const normalized = {};
  for (const [sourceId, job] of Object.entries(jobs)) {
    normalized[Number(sourceId)] = {
      status: job?.status ?? "running",
      inboxAdded: Number(job?.inbox_added ?? 0),
      message: job?.message ?? "",
    };
  }
  return normalized;
}
