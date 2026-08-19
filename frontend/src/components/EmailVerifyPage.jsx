import { useEffect, useRef, useState } from "react";
import { CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import logo from "../assets/logo.png";
import { verifyEmail } from "../api/authApi.js";

/**
 * 메일의 인증 링크(`/verify-email?token=...`)가 도착하는 화면.
 *
 * 로그인 없이도 동작해야 한다 — 사용자가 폰이나 다른 브라우저에서 메일을 열 수
 * 있기 때문이다. 토큰 자체가 인증 수단이라 백엔드도 이 엔드포인트만 AllowAny 다.
 */
function EmailVerifyPage({ token, onDone }) {
  const [state, setState] = useState("verifying"); // verifying | ok | fail
  const [message, setMessage] = useState("");
  // React 18 StrictMode 는 개발 중 effect 를 두 번 실행한다. 인증 토큰은 일회성이라
  // 두 번째 호출이 "이미 사용됨"으로 실패할 수 있어 한 번만 보내도록 막는다.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (!token) {
      setState("fail");
      setMessage("인증 링크가 올바르지 않아요. 메일의 주소를 그대로 열어주세요.");
      return;
    }

    verifyEmail(token)
      .then((data) => {
        setState("ok");
        setMessage(data?.detail || "이메일 인증이 완료됐어요.");
      })
      .catch((error) => {
        setState("fail");
        setMessage(
          error?.message ||
            "인증에 실패했어요. 링크가 만료됐다면 인증 메일을 다시 받아주세요.",
        );
      });
  }, [token]);

  return (
    <div className="onb">
      <div className="onbCard" style={{ maxWidth: 460 }}>
        <div className="onbHead">
          <div className="lpBrand">
            <img
              src={logo}
              className="brandMark"
              style={{ width: 30, height: 30 }}
              alt="꽁알꽁알"
            />
            <strong>이메일 인증</strong>
          </div>
        </div>

        <div className="onbBody">
          <div className="onbStepInner" style={{ textAlign: "center" }}>
            {state === "verifying" && (
              <>
                <Loader2 size={40} className="spin" aria-hidden="true" />
                <h2 className="onbStepHeading">인증하는 중이에요...</h2>
              </>
            )}
            {state === "ok" && (
              <>
                <CheckCircle2
                  size={40}
                  aria-hidden="true"
                  style={{ color: "var(--c-success)" }}
                />
                <h2 className="onbStepHeading">인증이 완료됐어요!</h2>
                <p className="onbStepSub">
                  이제 관심 공지를 메일로 받아보실 수 있어요.
                </p>
              </>
            )}
            {state === "fail" && (
              <>
                <AlertTriangle
                  size={40}
                  aria-hidden="true"
                  style={{ color: "var(--c-warning)" }}
                />
                <h2 className="onbStepHeading">인증하지 못했어요</h2>
                <p className="onbStepSub">{message}</p>
              </>
            )}
          </div>
        </div>

        <div className="onbFooter">
          <button
            type="button"
            className="onbNavBtn primary"
            onClick={onDone}
            disabled={state === "verifying"}
            style={{ marginLeft: "auto" }}
          >
            꽁알꽁알로 이동
          </button>
        </div>
      </div>
    </div>
  );
}

export default EmailVerifyPage;
