import { apiRequest, ApiError } from "./client.js";

// 백엔드 AlertChannelSerializer: { id, user_id, type, config, is_active, created_at }
// config 계약:
//   email → { "address": "user@example.com" }  (없으면 백엔드가 user.email 사용)
//   slack → { "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ" }
function normalizeChannel(item) {
  return {
    id: item.id,
    type: item.type,
    config: item.config ?? {},
    isActive: item.is_active ?? true,
    createdAt: item.created_at ?? null,
  };
}

export async function getAlertChannels() {
  const data = await apiRequest("/api/alert-channels/");
  return Array.isArray(data) ? data.map(normalizeChannel) : [];
}

export async function createAlertChannel({ type, config, isActive = true }) {
  const data = await apiRequest("/api/alert-channels/", {
    method: "POST",
    body: JSON.stringify({ type, config, is_active: isActive }),
  });
  const channel = normalizeChannel(data);
  // 채널 생성 직후 백엔드가 확인 메시지를 발송하고 결과를 함께 내려준다.
  // { confirmation: { ok, error } } — 발송 실패해도 채널 생성 자체는 성공.
  if (data && typeof data === "object" && data.confirmation) {
    channel.confirmation = {
      ok: data.confirmation.ok !== false,
      error: data.confirmation.error ?? "",
    };
  }
  return channel;
}

export async function updateAlertChannel(channelId, patch) {
  const body = {};
  if (patch.type !== undefined) body.type = patch.type;
  if (patch.config !== undefined) body.config = patch.config;
  if (patch.isActive !== undefined) body.is_active = patch.isActive;

  const data = await apiRequest(`/api/alert-channels/${channelId}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return normalizeChannel(data);
}

export async function deleteAlertChannel(channelId) {
  return apiRequest(`/api/alert-channels/${channelId}/`, { method: "DELETE" });
}

// 테스트 전송: POST /api/alert-channels/{id}/test/ → { ok, error }
// 응답이 {ok,error} 형태이든 에러 상태이든 항상 { ok, error } 로 정규화해 반환한다.
export async function testAlertChannel(channelId) {
  try {
    const data = await apiRequest(`/api/alert-channels/${channelId}/test/`, {
      method: "POST",
      body: JSON.stringify({}),
    });

    if (data && typeof data === "object") {
      return { ok: data.ok !== false, error: data.error ?? "" };
    }
    return { ok: true, error: "" };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { ok: false, error: "테스트 전송 기능이 아직 준비되지 않았어요." };
    }
    return { ok: false, error: error.message || "테스트 전송에 실패했어요." };
  }
}
