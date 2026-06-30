import { mockSources } from "../data/mockSources.js";

const USE_MOCK = true;

export async function getNoticeSources() {
  if (USE_MOCK) {
    return mockSources;
  }

  const response = await fetch("/api/notice-sources");

  if (!response.ok) {
    throw new Error("사이트 목록을 불러오지 못했습니다.");
  }

  return response.json();
}

export async function updateSourceSubscriptions(sourceIds) {
  if (USE_MOCK) {
    return {
      message: "관심 사이트가 저장되었습니다.",
      sourceIds,
    };
  }

  const response = await fetch("/api/me/source-subscriptions", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sourceIds }),
  });

  if (!response.ok) {
    throw new Error("관심 사이트 저장에 실패했습니다.");
  }

  return response.json();
}
