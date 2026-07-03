// 같은 오리진(Vite dev 프록시)으로 요청하므로 base URL 은 비워둔다. → `/api/...`
const API_BASE_URL = "";

// 인증 자체를 수행하는 공개 엔드포인트. 이 경로들에는 (만료됐을 수 있는) access_token 을
// 실어 보내지 않고, 401 이어도 refresh 재시도를 하지 않는다. 그래야 브라우저에 남은
// stale 토큰 때문에 로그인/회원가입이 막히거나 무의미한 refresh 루프가 돌지 않는다.
const AUTH_PATHS = [
  "/api/account/signin/",
  "/api/account/signup/",
  "/api/account/refresh/",
  "/api/account/logout/",
];

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

// 비-httponly 쿠키(access_token 등)를 읽는다. 백엔드가 httponly 없이 내려주므로 JS 접근 가능.
function readCookie(name) {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

async function rawFetch(path, options, accessToken) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  // 백엔드의 request.user 인증(JWTAuthentication)은 Authorization 헤더를 읽는다.
  // 로그인 시 쿠키에 저장된 access_token 을 Bearer 로 실어 보낸다.
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });
}

// access_token 이 만료(401)됐을 때 refresh_token 으로 재발급을 1회 시도한다.
// 초기 로드 시 병렬 요청이 동시에 401 나더라도 refresh 는 한 번만 돌도록 dedupe.
let refreshInFlight = null;
async function refreshAccessToken() {
  if (!readCookie("refresh_token")) return false;

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
 * - 같은 오리진 + credentials:include 로 쿠키를 주고받고
 * - 비-httponly access_token 쿠키를 Bearer 헤더로 첨부하며
 * - 401 이면 refresh 후 1회 재시도한다.
 */
export async function apiRequest(path, options = {}, _retried = false) {
  const isAuthPath = AUTH_PATHS.some((p) => path.startsWith(p));
  // 인증 엔드포인트에는 stale 토큰을 붙이지 않는다(쿠키 credentials 는 그대로 전송).
  const accessToken = isAuthPath ? null : readCookie("access_token");
  const response = await rawFetch(path, options, accessToken);

  if (response.status === 401 && !_retried && !isAuthPath) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest(path, options, true);
    }
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
