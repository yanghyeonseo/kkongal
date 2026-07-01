import { mockInterests } from "../data/mockInterests.js";

const USE_MOCK = true;

export async function getMyInterests() {
  if (USE_MOCK) {
    return mockInterests;
  }

  const response = await fetch("http://127.0.0.1:8000/api/interests/", {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("관심사 목록을 불러오지 못했습니다.");
  }

  return response.json();
}

export async function updateMyInterests(interests) {
  if (USE_MOCK) {
    return interests;
  }

  const response = await fetch("http://127.0.0.1:8000/api/interests/", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ interests }),
  });

  if (!response.ok) {
    throw new Error("관심사 저장에 실패했습니다.");
  }

  return response.json();
}
