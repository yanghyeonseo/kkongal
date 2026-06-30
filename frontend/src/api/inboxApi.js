import { mockInboxNotices } from "../data/mockInboxNotices";

const USE_MOCK = true;

export async function getMyInboxNotices() {
  if (USE_MOCK) {
    return mockInboxNotices;
  }

  const response = await fetch("/api/me/inbox");

  if (!response.ok) {
    throw new Error("공지 목록을 불러오지 못했습니다.");
  }

  return response.json();
}
