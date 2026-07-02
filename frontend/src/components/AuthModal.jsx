import { useMemo, useState } from "react";
import { AlertCircle, Check, CheckCircle2 } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import { login, signup, getCurrentUser } from "../api/authApi.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const STRENGTH_LABELS = ["", "약함", "보통", "강함", "매우 강함"];

function evaluatePassword(pw) {
  const rules = {
    length: pw.length >= 8,
    letter: /[a-zA-Z]/.test(pw),
    number: /[0-9]/.test(pw),
  };
  let score = 0;
  if (rules.length) score += 1;
  if (rules.letter && rules.number) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[^A-Za-z0-9]/.test(pw)) score += 1;
  // 제출 허용 조건: 8자 이상 + 영문 + 숫자 (아래 체크리스트와 일치)
  const valid = rules.length && rules.letter && rules.number;
  return { rules, score: pw ? Math.max(score, 1) : 0, valid };
}

function AuthModal({ initialMode, onClose, onAuthSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const [errorMessage, setErrorMessage] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const isLoginMode = mode === "login";

  const pw = useMemo(() => evaluatePassword(password), [password]);
  const emailValid = EMAIL_RE.test(email);
  const emailError = !isLoginMode && email.length > 0 && !emailValid;
  const confirmError = !isLoginMode && confirm.length > 0 && confirm !== password;

  const signupValid =
    username.trim().length > 0 && emailValid && pw.valid && confirm === password;

  const canSubmit = isLoginMode
    ? username.trim().length > 0 && password.length > 0
    : signupValid;

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setErrorMessage("");
    setFieldErrors({});
  };

  const applyServerErrors = (error, fallback) => {
    const payload = error?.payload;
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      const next = {};
      for (const key of ["username", "email", "password"]) {
        const value = payload[key];
        if (Array.isArray(value) && value.length > 0) next[key] = String(value[0]);
        else if (typeof value === "string") next[key] = value;
      }
      if (Object.keys(next).length > 0) {
        setFieldErrors(next);
        setErrorMessage("");
        return;
      }
    }
    setErrorMessage(error?.message || fallback);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMessage("");
    setFieldErrors({});
    setSubmitting(true);

    try {
      if (isLoginMode) {
        await login({ username, password });
      } else {
        await signup({ username, email, password });
      }

      let user;
      try {
        user = await getCurrentUser();
      } catch {
        user = { username, email, name: username };
      }
      onAuthSuccess(user);
    } catch (error) {
      applyServerErrors(
        error,
        isLoginMode
          ? "로그인에 실패했어요. 아이디와 비밀번호를 확인해주세요."
          : "회원가입에 실패했어요. 입력값을 다시 확인해주세요.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      size="sm"
      onClose={onClose}
      title={isLoginMode ? "로그인" : "회원가입"}
      subtitle={
        isLoginMode
          ? "로그인하고 맞춤 공지를 확인하세요."
          : "계정을 만들고 맞춤 공지를 받아보세요."
      }
    >
      <div className="authTabButtons" role="tablist" aria-label="로그인 또는 회원가입">
        <button
          type="button"
          role="tab"
          aria-selected={isLoginMode}
          className={isLoginMode ? "active" : ""}
          onClick={() => switchMode("login")}
        >
          로그인
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!isLoginMode}
          className={!isLoginMode ? "active" : ""}
          onClick={() => switchMode("signup")}
        >
          회원가입
        </button>
      </div>

      <form className="authForm" onSubmit={handleSubmit} noValidate>
        <label className={`authInputGroup ${fieldErrors.username ? "hasError" : ""}`}>
          <span>아이디</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="로그인에 사용할 아이디"
            autoComplete="username"
            aria-invalid={Boolean(fieldErrors.username)}
            required
          />
          {fieldErrors.username && (
            <p className="fieldError">
              <AlertCircle size={13} /> {fieldErrors.username}
            </p>
          )}
        </label>

        {!isLoginMode && (
          <label
            className={`authInputGroup ${
              fieldErrors.email || emailError ? "hasError" : ""
            }`}
          >
            <span>이메일</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="공지 알림을 받을 이메일"
              autoComplete="email"
              aria-invalid={Boolean(fieldErrors.email || emailError)}
              required
            />
            {fieldErrors.email ? (
              <p className="fieldError">
                <AlertCircle size={13} /> {fieldErrors.email}
              </p>
            ) : emailError ? (
              <p className="fieldError">
                <AlertCircle size={13} /> 올바른 이메일 형식이 아니에요.
              </p>
            ) : null}
          </label>
        )}

        <label className={`authInputGroup ${fieldErrors.password ? "hasError" : ""}`}>
          <span>비밀번호</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="비밀번호를 입력하세요"
            autoComplete={isLoginMode ? "current-password" : "new-password"}
            aria-invalid={Boolean(fieldErrors.password)}
            required
          />
          {fieldErrors.password && (
            <p className="fieldError">
              <AlertCircle size={13} /> {fieldErrors.password}
            </p>
          )}

          {!isLoginMode && (
            <>
              <div className={`pwMeter s${pw.score}`} aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="pwHintRow">
                <span className={`pwStrengthLabel s${pw.score}`}>
                  비밀번호 강도 · {pw.score ? STRENGTH_LABELS[pw.score] : "입력 전"}
                </span>
              </div>
              <ul className="pwRules">
                <li className={pw.rules.length ? "met" : ""}>
                  {pw.rules.length ? <Check size={12} /> : <span>·</span>} 8자 이상
                </li>
                <li className={pw.rules.letter ? "met" : ""}>
                  {pw.rules.letter ? <Check size={12} /> : <span>·</span>} 영문 포함
                </li>
                <li className={pw.rules.number ? "met" : ""}>
                  {pw.rules.number ? <Check size={12} /> : <span>·</span>} 숫자 포함
                </li>
              </ul>
            </>
          )}
        </label>

        {!isLoginMode && (
          <label className={`authInputGroup ${confirmError ? "hasError" : ""}`}>
            <span>비밀번호 확인</span>
            <input
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              placeholder="비밀번호를 한 번 더 입력하세요"
              autoComplete="new-password"
              aria-invalid={confirmError}
              required
            />
            {confirmError ? (
              <p className="fieldError">
                <AlertCircle size={13} /> 비밀번호가 일치하지 않아요.
              </p>
            ) : confirm.length > 0 && confirm === password ? (
              <p className="fieldError" style={{ color: "var(--c-success)" }}>
                <CheckCircle2 size={13} /> 비밀번호가 일치해요.
              </p>
            ) : null}
          </label>
        )}

        {errorMessage && (
          <p className="authError" role="alert">
            {errorMessage}
          </p>
        )}

        <button
          className="authSubmitButton"
          disabled={submitting || !canSubmit}
        >
          {submitting ? "처리 중..." : isLoginMode ? "로그인" : "회원가입"}
        </button>
      </form>
    </ModalShell>
  );
}

export default AuthModal;
