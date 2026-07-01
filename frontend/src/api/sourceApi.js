import { apiRequest } from "./client.js";

function normalizeSource(item) {
  const source = item.source || item.notice_source || item;

  return {
    id: source.id ?? item.source_id ?? item.id,
    subscriptionId: item.id ?? item.subscription_id,

    name: source.name ?? item.name ?? "",
    displayName:
      source.display_name ??
      source.displayName ??
      source.name ??
      item.display_name ??
      item.name ??
      "공지 사이트",

    category:
      source.category ??
      source.source_type ??
      item.category ??
      item.source_type ??
      "etc",

    url: source.url ?? item.url ?? "",
    isSubscribed: true,
    notifyEnabled: item.notify_enabled ?? item.notifyEnabled ?? true,
  };
}

export async function getNoticeSources() {
  const data = await apiRequest("/api/subscriptions/");
  return data.map(normalizeSource);
}

export async function createSourceSubscription(sourceId) {
  return apiRequest("/api/subscriptions/", {
    method: "POST",
    body: JSON.stringify({
      source: sourceId,
    }),
  });
}

export async function deleteSourceSubscription(subscriptionId) {
  return apiRequest(`/api/subscriptions/${subscriptionId}/`, {
    method: "DELETE",
  });
}
