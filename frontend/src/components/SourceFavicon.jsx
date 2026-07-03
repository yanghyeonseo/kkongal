import { useEffect, useMemo, useState } from "react";

// 사이트 이름 기반 결정론적 색상(파비콘 로드 실패 시 앞글자 원형 배경).
const LOGO_COLORS = [
  "#1677f2",
  "#ef2b55",
  "#ff6b2c",
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
];

function colorFor(name) {
  const key = name || "";
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) hash += key.charCodeAt(i);
  return LOGO_COLORS[hash % LOGO_COLORS.length];
}

// URL(또는 google s2 파비콘 URL)에서 hostname(도메인)을 뽑아낸다. www. 는 떼어낸다.
function hostnameOf(url) {
  if (!url) return "";
  try {
    const withProtocol = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    return new URL(withProtocol).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// 대체 파비콘용 도메인: 소스 url 우선, 없으면 google s2 파비콘 URL 의 domain 쿼리에서 유추.
function domainFor(siteUrl, faviconUrl) {
  const fromSite = hostnameOf(siteUrl);
  if (fromSite) return fromSite;
  if (faviconUrl) {
    try {
      const parsed = new URL(faviconUrl, window.location.origin);
      const domainParam =
        parsed.searchParams.get("domain") || parsed.searchParams.get("domain_url");
      if (domainParam) return hostnameOf(domainParam) || domainParam.replace(/^www\./, "");
    } catch {
      // 무시하고 도메인 없음 처리
    }
  }
  return "";
}

/**
 * 사이트 파비콘 아바타.
 * - 파비콘을 여러 소스로 순차 시도한다: 저장된 favicon_url(google s2) → icon.horse → 앞글자 원형.
 *   (jobkorea 처럼 s2 가 404 나는 사이트는 icon.horse 로, snu/naver 는 s2 로 렌더된다.)
 * - 이미지는 원을 꽉 채우도록 크롭(object-fit: cover)한다.
 * - size(px)와 rounded(테두리 반경)를 조절해 카드/사이드바/카탈로그에서 재사용한다.
 */
function SourceFavicon({
  name = "",
  faviconUrl = "",
  siteUrl = "",
  size = 44,
  rounded = "50%",
  className = "",
}) {
  // 순서대로 시도할 파비콘 후보. 다 실패하면 앞글자 원형으로 폴백.
  const candidates = useMemo(() => {
    const list = [];
    if (faviconUrl) list.push(faviconUrl);
    const domain = domainFor(siteUrl, faviconUrl);
    if (domain) list.push(`https://icon.horse/icon/${domain}`);
    return list;
  }, [faviconUrl, siteUrl]);

  const [index, setIndex] = useState(0);

  // 소스가 바뀌면(파비콘/URL 변경) 첫 후보부터 다시 시도한다.
  useEffect(() => {
    setIndex(0);
  }, [faviconUrl, siteUrl]);

  const currentSrc = index < candidates.length ? candidates[index] : null;
  const showImage = Boolean(currentSrc);
  const initial = (name || "?").trim().slice(0, 1).toUpperCase() || "?";

  return (
    <span
      className={`sourceFavicon ${showImage ? "hasFavicon" : ""} ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: rounded,
        background: showImage ? "#fff" : colorFor(name),
        fontSize: Math.round(size * 0.42),
      }}
      aria-hidden="true"
    >
      {showImage ? (
        <img
          key={currentSrc}
          src={currentSrc}
          alt=""
          loading="lazy"
          onError={() => setIndex((current) => current + 1)}
        />
      ) : (
        initial
      )}
    </span>
  );
}

export default SourceFavicon;
