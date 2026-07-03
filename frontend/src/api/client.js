// 같은 오리진(Vite dev 프록시)으로 요청하므로 base URL 은 비워둔다. → `/api/...`
const API_BASE_URL = "";

// 인증 자체를 수행하는 공개 엔드포인트. 이 경로들은 401 이어도 refresh 재시도를 하지 않는다
// (그래야 로그인/회원가입/재발급 실패가 무의미한 refresh 루프로 번지지 않는다). 쿠키는
// credentials:"include" 로 그대로 전송되지만, 백엔드가 이 공개 엔드포인트에선 stale 토큰을
// 조용히 무시한다(CookieJWTAuthentication 이 예외 대신 None 반환).
const AUTH_PATHS = [
  "/api/account/signin/",
  "/api/account/signup/",
  "/api/account/refresh/",
  "/api/account/logout/",
];

// 인증 상실(access_token 만료 + refresh 재발급 실패) 시 호출할 콜백. App 이 등록해
// currentUser 를 비우고 로그인 화면으로 되돌린다. 최초 미인증 하이드레이트에서도 불릴 수
// 있으므로, "로그인 상태였을 때만" 반응하는 판단은 App 핸들러 쪽에서 한다.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

/**
 * API 에러. status 코드와 백엔드가 내려준 사람이 읽을 수 있는 메시지를 담는다.
 */
export class ApiError extends Error {
  constructor(status, payload) {
    super(extractMessage(payload) || "요청 처리 중 문제가 발생했어요.");
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

// 백엔드 응답(JSON/텍스트)에서 최대한 자연스러운 한 줄 메시지를 뽑아낸다.
function extractMessage(payload) {
  if (!payload) return "";
  if (typeof payload === "string") return payload;

  if (typeof payload === "object") {
    if (typeof payload.detail === "string") return payload.detail;
    if (typeof payload.message === "string") return payload.message;

    // DRF serializer 에러: { field: ["msg", ...] } 형태 → 첫 메시지
    const firstKey = Object.keys(payload)[0];
    if (firstKey) {
      const value = payload[firstKey];
      if (Array.isArray(value) && value.length > 0) return String(value[0]);
      if (typeof value === "string") return value;
    }
  }
  return "";
}

// 인증 쿠키(access_token/refresh_token)는 HttpOnly 라 JS 에서 읽을 수 없다. 같은 오리진 +
// credentials:"include" 로 브라우저가 자동으로 실어 보내고, 백엔드가 access_token 쿠키를
// 직접 읽어 인증한다(account.authentication.CookieJWTAuthentication). → JS 토큰 취급 불필요.
async function rawFetch(path, options) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });
}

// access_token 이 만료(401)됐을 때 refresh_token 쿠키로 재발급을 1회 시도한다. refresh_token 은
// HttpOnly 라 JS 로 존재 여부를 알 수 없으므로, 백엔드에 그대로 위임한다(쿠키가 없거나 만료면
// 400/401 → 아래에서 false). 초기 로드 시 병렬 요청이 동시에 401 나도 refresh 는 한 번만 돌도록 dedupe.
let refreshInFlight = null;
async function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/api/account/refresh/`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        // 다음 만료 때 다시 시도할 수 있도록 초기화 (microtask 이후)
        setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      });
  }

  return refreshInFlight;
}

/**
 * 공통 API 요청 헬퍼.
 * - 같은 오리진 + credentials:include 로 HttpOnly 인증 쿠키를 자동 송수신하고
 * - 401 이면 refresh 후 1회 재시도한다.
 */
export async function apiRequest(path, options = {}, _retried = false) {
  const isAuthPath = AUTH_PATHS.some((p) => path.startsWith(p));
  const response = await rawFetch(path, options);

  if (response.status === 401 && !_retried && !isAuthPath) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest(path, options, true);
    }
    // refresh 실패 = 세션 만료. 등록된 핸들러에 알려 로그인 화면으로 되돌리게 한다.
    // (하이드레이트 등 미로그인 상태에서의 401 은 App 핸들러가 조용히 무시한다.)
    if (onUnauthorized) onUnauthorized();
  }

  if (!response.ok) {
    let payload = null;
    const text = await response.text();
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = text;
    }
    throw new ApiError(response.status, payload);
  }

  if (response.status === 204) {
    return null;
  }

  // 본문이 비어있을 수 있는 응답 방어
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
