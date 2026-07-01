import { apiRequest } from "./client.js";
import { mockSources } from "../data/mockSources.js";

const USE_MOCK = true;

function normalizeSource(item) {
  const source = item.source || item;

  return {
    id: source.id ?? item.source_id ?? item.id,
    subscriptionId: item.id,

    name: source.name ?? "",
    displayName: source.name ?? "공지 사이트",

    category: "etc",
    url: source.url ?? "",

    isSubscribed: true,
  };
}

export async function getNoticeSources() {
  if (USE_MOCK) {
    return mockSources;
  }

  const data = await apiRequest("/api/subscriptions/");
  return data.map(normalizeSource);
}

export async function createSourceSubscription({ url }) {
  if (USE_MOCK) {
    return {
      id: Date.now(),
      subscriptionId: Date.now(),
      name: url,
      displayName: url,
      category: "etc",
      url,
      isSubscribed: true,
    };
  }

  const data = await apiRequest("/api/subscriptions/", {
    method: "POST",
    body: JSON.stringify({ url }),
  });

  return normalizeSource(data);
}

export async function deleteSourceSubscription(subscriptionId) {
  if (USE_MOCK) {
    return null;
  }

  return apiRequest(`/api/subscriptions/${subscriptionId}/`, {
    method: "DELETE",
  });
}
