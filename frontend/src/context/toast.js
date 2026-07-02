import { createContext, useContext } from "react";

// 토스트 컨텍스트. 컴포넌트가 아닌 파일에 두어 fast-refresh 규칙을 만족시킨다.
export const ToastContext = createContext(null);

/**
 * 토스트 훅.
 * const toast = useToast();
 * toast.success("저장했어요");  toast.error("실패했어요");  toast.info("...")
 */
export function useToast() {
  const context = useContext(ToastContext);

  if (!context) {
    // Provider 밖에서 호출돼도 앱이 죽지 않도록 no-op 폴백 제공
    const noop = () => {};
    return { show: noop, success: noop, error: noop, info: noop, dismiss: noop };
  }

  return context;
}
