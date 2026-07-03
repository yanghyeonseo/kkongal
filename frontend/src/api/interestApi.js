import { apiRequest } from "./client.js";

// 백엔드 InterestSerializer: { id, user_id, keyword, description, priority, created_at }
function normalizeInterest(item) {
  return {
    id: item.id,
    keyword: item.keyword ?? "",
    description: item.description ?? "",
    priority: item.priority ?? 0,
  };
}

export async function getMyInterests() {
  const data = await apiRequest("/api/interests/");
  return Array.isArray(data) ? data.map(normalizeInterest) : [];
}

// 관심사는 항목 단위 CRUD (bulk PUT 없음).
export async function createInterest({ keyword, description = "", priority = 0 }) {
  const data = await apiRequest("/api/interests/", {
    method: "POST",
    body: JSON.stringify({ keyword, description, priority }),
  });
  return normalizeInterest(data);
}

export async function updateInterest(
  interestId,
  { keyword, description = "", priority = 0 },
) {
  const data = await apiRequest(`/api/interests/${interestId}/`, {
    method: "PUT",
    body: JSON.stringify({ keyword, description, priority }),
  });
  return normalizeInterest(data);
}

export async function deleteInterest(interestId) {
  return apiRequest(`/api/interests/${interestId}/`, { method: "DELETE" });
}
