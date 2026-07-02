import { useCallback, useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { ToastContext } from "../context/toast.js";

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const AUTO_DISMISS_MS = 4000;

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (message, type = "info") => {
      if (!message) return;
      idRef.current += 1;
      const id = idRef.current;

      setToasts((prev) => [...prev, { id, message, type }]);

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
