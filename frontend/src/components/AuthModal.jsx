import { useState } from "react";
import { ChevronDown } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import { login, signup, getCurrentUser } from "../api/authApi.js";

const GENDER_OPTIONS = [
  { value: "", label: "선택 안 함" },
  { value: "남성", label: "남성" },
  { value: "여성", label: "여성" },
  { value: "기타", label: "기타" },
];

function AuthModal({ initialMode, onClose, onAuthSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [age, setAge] = useState("");
  const [job, setJob] = useState("");
  const [gender, setGender] = useState("");
  const [showProfile, setShowProfile] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isLoginMode = mode === "login";

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setErrorMessage("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMessage("");
    setSubmitting(true);

    try {
      if (isLoginMode) {
        await login({ username, password });
      } else {
        await signup({ username, email, password, age, job, gender });
      }

      // 로그인/회원가입 후 쿠키 기준으로 현재 사용자를 재조회(hydrate)한다.
      let user;
      try {
        user = await getCurrentUser();
      } catch {
        // /me 조회 실패 시에도 입력값 기반으로 진행(앱은 계속 동작)
        user = { username, email, name: username };
      }
      onAuthSuccess(user);
    } catch (error) {
      const detail = error?.message;
      setErrorMessage(
        isLoginMode
          ? detail || "로그인에 실패했어요. 아이디와 비밀번호를 확인해주세요."
          : detail || "회원가입에 실패했어요. 입력값을 다시 확인해주세요.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell className="authModal" labelledBy="authModalTitle" onClose={onClose}>
      <div className="registerModalHeader">
        <div>
          <h2 id="authModalTitle">{isLoginMode ? "로그인" : "회원가입"}</h2>
          <p>
            {isLoginMode
              ? "로그인 후 맞춤 공지를 확인하세요."
              : "계정을 만들고 맞춤 공지를 받아보세요."}
          </p>
        </div>
        <button
          type="button"
          className="modalCloseButton"
          onClick={onClose}
          aria-label="닫기"
        >
          ×
        </button>
      </div>

      <div className="authTabButtons" role="tablist">
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

      <form className="authForm" onSubmit={handleSubmit}>
        <label className="authInputGroup">
          <span>아이디</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="로그인에 사용할 아이디"
            autoComplete="username"
            required
          />
        </label>

        {!isLoginMode && (
          <label className="authInputGroup">
            <span>이메일</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="공지 알림을 받을 이메일"
              autoComplete="email"
              required
            />
          </label>
        )}

        <label className="authInputGroup">
          <span>비밀번호</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="비밀번호를 입력하세요"
            autoComplete={isLoginMode ? "current-password" : "new-password"}
            required
          />
        </label>

        {!isLoginMode && (
          <div className="profileDisclosure">
            <button
              type="button"
              className="profileToggle"
              onClick={() => setShowProfile((prev) => !prev)}
              aria-expanded={showProfile}
            >
              <span>추가 정보 입력 (선택) · AI 추천 정확도 향상</span>
              <ChevronDown
                size={16}
                className={`chevron ${showProfile ? "open" : ""}`}
              />
            </button>

            {showProfile && (
              <div className="profileFields">
                <label className="authInputGroup">
                  <span>나이</span>
                  <input
                    type="number"
                    min="0"
                    value={age}
                    onChange={(event) => setAge(event.target.value)}
                    placeholder="예: 24"
                  />
                </label>
                <label className="authInputGroup">
                  <span>직무 / 전공</span>
                  <input
                    value={job}
                    onChange={(event) => setJob(event.target.value)}
                    placeholder="예: 백엔드 개발자, 컴퓨터공학"
                  />
                </label>
                <label className="authInputGroup">
                  <span>성별</span>
                  <select
                    className="authSelect"
                    value={gender}
                    onChange={(event) => setGender(event.target.value)}
                  >
                    {GENDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <p className="authError" role="alert">
            {errorMessage}
          </p>
        )}

        <button className="authSubmitButton" disabled={submitting}>
          {submitting ? "처리 중..." : isLoginMode ? "로그인" : "회원가입"}
        </button>
      </form>
    </ModalShell>
  );
}

export default AuthModal;
