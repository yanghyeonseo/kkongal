import { useEffect, useState } from "react";

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

/**
 * 사이트 파비콘 아바타.
 * - favicon_url 이 있으면 <img> 로 표시하고, 로드 실패(onError)하면 앞글자 원형으로 폴백한다.
 * - size(px)와 rounded(테두리 반경)를 조절해 카드/사이드바/카탈로그에서 재사용한다.
 */
function SourceFavicon({
  name = "",
  faviconUrl = "",
  size = 44,
  rounded = "50%",
  className = "",
}) {
  const [failed, setFailed] = useState(false);

  // 소스가 바뀌면(파비콘 URL 변경) 실패 상태를 초기화한다.
  useEffect(() => {
    setFailed(false);
  }, [faviconUrl]);

  const showImage = Boolean(faviconUrl) && !failed;
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
        <img src={faviconUrl} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        initial
      )}
    </span>
  );
}

export default SourceFavicon;
