import { apiRequest } from "./client.js";

/**
 * AI 파이프라인 상태를 조회한다.
 * 백엔드: GET /api/ai/status/ → { degraded: bool, reason: "quota"|"disabled"|"ok", message: string }
 *
 * 엔드포인트가 없거나(404) 조회에 실패하면 "정상(비저하)"으로 간주해 UI 를 막지 않는다.
 */
export async function getAiStatus() {
  try {
    const data = await apiRequest("/api/ai/status/");
    return {
      degraded: Boolean(data?.degraded),
      reason: data?.reason ?? "ok",
      message: data?.message ?? "",
    };
  } catch {
    return { degraded: false, reason: "ok", message: "" };
  }
}
