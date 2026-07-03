import { useCallback, useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { ToastContext } from "../context/toast.js";

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const AUTO_DISMISS_MS = 4000;
const TOAST_EXIT_MS = 200;

function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const idRef = useRef(0);

  // 실제 제거(상태에서 삭제)
  const remove = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  // 닫기: 종료 애니메이션을 재생한 뒤 제거(모션 감소 설정이면 즉시 제거).
  const dismiss = useCallback(
    (id) => {
      const timer = timers.current.get(id);
      if (timer) {
        clearTimeout(timer);
        timers.current.delete(id);
      }
      if (prefersReducedMotion()) {
        remove(id);
        return;
      }
      setToasts((prev) =>
        prev.map((toast) =>
          toast.id === id ? { ...toast, exiting: true } : toast,
        ),
      );
      const exitTimer = setTimeout(() => remove(id), TOAST_EXIT_MS);
      timers.current.set(id, exitTimer);
    },
    [remove],
  );

  const show = useCallback(
    (message, type = "info") => {
      if (!message) return;
      idRef.current += 1;
      const id = idRef.current;

      setToasts((prev) => [...prev, { id, message, type, exiting: false }]);

      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timers.current.set(id, timer);
      return id;
    },
    [dismiss],
  );

  const value = useMemo(
    () => ({
      show,
      dismiss,
      success: (message) => show(message, "success"),
      error: (message) => show(message, "error"),
      info: (message) => show(message, "info"),
    }),
    [show, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}

      <div className="toastViewport" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type] || Info;
          return (
            <div
              key={toast.id}
              className={`toast toast-${toast.type}`}
              data-exiting={toast.exiting ? "true" : "false"}
              role={toast.type === "error" ? "alert" : "status"}
            >
              <Icon size={18} className="toastIcon" aria-hidden="true" />
              <span className="toastMessage">{toast.message}</span>
              <button
                type="button"
                className="toastClose"
                onClick={() => dismiss(toast.id)}
                aria-label="알림 닫기"
              >
                <X size={15} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export default ToastProvider;
