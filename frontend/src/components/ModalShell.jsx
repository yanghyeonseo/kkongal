import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 접근성을 갖춘 모달 셸.
 * - Escape 로 닫기
 * - 오버레이 클릭으로 닫기
 * - 포커스 트랩(Tab 순환) + 열릴 때 첫 요소 포커스, 닫힐 때 이전 포커스 복원
 * - role="dialog" aria-modal
 */
function ModalShell({ onClose, className = "", labelledBy, ariaLabel, children }) {
  const dialogRef = useRef(null);
  const previouslyFocused = useRef(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement;

    const dialog = dialogRef.current;
    // 열릴 때 모달 내부 첫 포커스 가능한 요소로 포커스 이동
    const focusables = dialog?.querySelectorAll(FOCUSABLE);
    if (focusables && focusables.length > 0) {
      focusables[0].focus();
    } else {
      dialog?.focus();
    }

    return () => {
      // 닫힐 때 원래 포커스 복원
      const previous = previouslyFocused.current;
      if (previous && typeof previous.focus === "function") {
        previous.focus();
      }
    };
  }, []);

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
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

  return (
    <div
      className="modalOverlay"
      onMouseDown={(event) => {
        // 오버레이(자기 자신) 클릭 시에만 닫기
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={className}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={ariaLabel}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        {children}
      </div>
    </div>
  );
}

export default ModalShell;
