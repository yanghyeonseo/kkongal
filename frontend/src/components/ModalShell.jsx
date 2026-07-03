import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const EXIT_MS = 170;

// 열려 있는 모달 수(중첩 대비). 0 이 될 때만 배경 스크롤 잠금을 해제한다.
let openModalCount = 0;

function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * 접근성 + 일관된 레이아웃을 갖춘 모달 셸.
 * - 안정적 크기: flex column + max-height, 본문(.modalBody)만 스크롤, 헤더/푸터 고정
 * - Escape / 오버레이 클릭 / 닫기(X) 로 닫힘 (닫기 애니메이션 후 onClose 호출)
 * - 포커스 트랩(Tab 순환) + 열릴 때 첫 요소 포커스, 닫힐 때 이전 포커스 복원
 * - role="dialog" aria-modal, prefers-reduced-motion 존중
 *
 * props:
 *   title, subtitle  — 표준 헤더. 생략하면 헤더 미표시(커스텀 children 사용).
 *   size             — "sm" | "md" | "lg" (기본 md)
 *   headerAccessory  — 헤더 우측 닫기 버튼 옆에 들어갈 요소(예: 도움말 ?)
 *   footer           — 하단 고정 푸터 내용
 *   bodyClassName    — 본문 영역 추가 클래스
 */
function ModalShell({
  onClose,
  className = "",
  size = "md",
  title,
  subtitle,
  headerAccessory,
  footer,
  bodyClassName = "",
  labelledBy,
  ariaLabel,
  children,
}) {
  const dialogRef = useRef(null);
  const previouslyFocused = useRef(null);
  const closeTimer = useRef(null);
  const [closing, setClosing] = useState(false);

  const titleId = labelledBy || (title ? "modalShellTitle" : undefined);

  // 닫기 요청: 종료 애니메이션을 재생한 뒤 실제 onClose 를 호출한다.
  const requestClose = useCallback(() => {
    if (prefersReducedMotion()) {
      onClose();
      return;
    }
    setClosing(true);
    closeTimer.current = setTimeout(onClose, EXIT_MS);
  }, [onClose]);

  useEffect(() => {
    previouslyFocused.current = document.activeElement;

    // 배경 스크롤 잠금(중첩 모달 대비 refcount)
    openModalCount += 1;
    document.documentElement.classList.add("modalOpen");

    // 열릴 때 본문의 첫 입력요소로 포커스(닫기 X 버튼이 아니라).
    const dialog = dialogRef.current;
    const body = dialog?.querySelector(".modalBody");
    const target =
      body?.querySelector("input, textarea, select") ||
      body?.querySelector(FOCUSABLE) ||
      dialog?.querySelector(FOCUSABLE);
    (target || dialog)?.focus();

    return () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);

      openModalCount = Math.max(0, openModalCount - 1);
      if (openModalCount === 0) {
        document.documentElement.classList.remove("modalOpen");
      }

      const previous = previouslyFocused.current;
      if (previous && typeof previous.focus === "function") previous.focus();
    };
  }, []);

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      requestClose();
      return;
    }

    if (event.key !== "Tab") return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusables = Array.from(dialog.querySelectorAll(FOCUSABLE)).filter(
      (element) => element.offsetParent !== null || element === document.activeElement,
    );
    if (focusables.length === 0) return;

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const hasStandardHeader = Boolean(title);

  return (
    <div
      className="modalOverlay"
      data-closing={closing ? "true" : "false"}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div
        ref={dialogRef}
        className={`modalCard size-${size} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-label={ariaLabel}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        {hasStandardHeader && (
          <header className="modalHeader">
            <div className="modalHeadingWrap">
              <h2 className="modalTitle" id={titleId}>
                {title}
              </h2>
              {subtitle && <p className="modalSubtitle">{subtitle}</p>}
            </div>
            <div className="modalHeaderActions">
              {headerAccessory}
              <button
                type="button"
                className="modalIconBtn modalClose"
                onClick={requestClose}
                aria-label="닫기"
              >
                <X size={18} strokeWidth={2.4} />
              </button>
            </div>
          </header>
        )}

        <div className={`modalBody ${bodyClassName}`}>{children}</div>

        {footer && <footer className="modalFooter">{footer}</footer>}
      </div>
    </div>
  );
}

export default ModalShell;
