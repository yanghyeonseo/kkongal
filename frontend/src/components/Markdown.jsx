// 의존성 없는 경량 Markdown 렌더러.
// 백엔드가 content_markdown 으로 내려주는 제목/목록/굵게/링크/인용/코드 위주의
// 마크다운을 안전하게(React 노드로만; dangerouslySetInnerHTML 미사용) 렌더한다.

// 인라인 토큰: [텍스트](url) · **굵게** · `코드` · *기울임* · _기울임_
const INLINE_RE = /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

function renderInline(text) {
  if (!text) return null;

  const nodes = [];
  let cursor = 0;
  let key = 0;
  let match;

  INLINE_RE.lastIndex = 0;
  while ((match = INLINE_RE.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));

    const token = match[0];
    if (token.startsWith("[")) {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (link) {
        const href = link[2].trim();
        const safe = /^(https?:|mailto:)/i.test(href) ? href : "#";
        nodes.push(
          <a key={key++} href={safe} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key++}>{token.slice(1, -1)}</code>);
    } else {
      // *기울임* 또는 _기울임_
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }

    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));

  return nodes;
}

const BLOCK_START_RE = /^\s*([-*+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s?|```)/;
const HR_RE = /^\s*([-*_])\1{2,}\s*$/;

function Markdown({ text }) {
  if (!text || !text.trim()) return null;

  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      const buf = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      i += 1; // 닫는 펜스 건너뛰기
      blocks.push(
        <pre key={key++}>
          <code>{buf.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (HR_RE.test(line)) {
      blocks.push(<hr key={key++} />);
      i += 1;
      continue;
    }

    // 모달 맥락상 제목을 한 단계 낮춰 렌더(#→h2)해 시각 위계를 맞춘다.
    const heading = /^(#{1,6})\s+(.*)$/.exec(line.trim());
    if (heading) {
      const Tag = `h${Math.min(heading[1].length + 1, 6)}`;
      blocks.push(<Tag key={key++}>{renderInline(heading[2])}</Tag>);
      i += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push(<blockquote key={key++}>{renderInline(buf.join(" "))}</blockquote>);
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ul key={key++}>
          {items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ol key={key++}>
          {items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // 문단 — 다음 빈 줄/블록 시작 전까지 이어붙인다.
    const buf = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !BLOCK_START_RE.test(lines[i]) &&
      !HR_RE.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={key++}>{renderInline(buf.join(" "))}</p>);
  }

  return <div className="markdownBody">{blocks}</div>;
}

export default Markdown;
