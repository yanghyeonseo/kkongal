import { useState } from "react";
import { login, signup } from "../api/authApi.js";

function AuthModal({ initialMode, onClose, onAuthSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [errorMessage, setErrorMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isLoginMode = mode === "login";

  const handleSubmit = async (event) => {
    event.preventDefault();

    setErrorMessage("");
    setSubmitting(true);

    try {
      const user = isLoginMode
        ? await login({ email, password })
        : await signup({ name, email, password });

      onAuthSuccess(user);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        isLoginMode
          ? "로그인에 실패했어요. 이메일과 비밀번호를 확인해주세요."
          : "회원가입에 실패했어요. 입력값을 다시 확인해주세요.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modalOverlay">
      <div className="authModal">
        <div className="registerModalHeader">
          <div>
            <h2>{isLoginMode ? "로그인" : "회원가입"}</h2>
            <p>
              {isLoginMode
                ? "로그인 후 맞춤 공지를 확인하세요"
                : "계정을 만들고 맞춤 공지를 받아보세요"}
            </p>
          </div>

          <button className="modalCloseButton" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="authTabButtons">
          <button
            className={isLoginMode ? "active" : ""}
            onClick={() => setMode("login")}
          >
            로그인
          </button>

          <button
            className={!isLoginMode ? "active" : ""}
            onClick={() => setMode("signup")}
          >
            회원가입
          </button>
        </div>

        <form className="authForm" onSubmit={handleSubmit}>
          {!isLoginMode && (
            <label className="authInputGroup">
              <span>이름</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="예: 김현서"
                required
              />
            </label>
          )}

          <label className="authInputGroup">
            <span>이메일</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="example@email.com"
              required
            />
          </label>

          <label className="authInputGroup">
            <span>비밀번호</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="비밀번호를 입력하세요"
              required
            />
          </label>

          {errorMessage && <p className="authError">{errorMessage}</p>}

          <button className="authSubmitButton" disabled={submitting}>
            {submitting ? "처리 중..." : isLoginMode ? "로그인" : "회원가입"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default AuthModal;
