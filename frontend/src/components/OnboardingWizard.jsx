import { useMemo, useRef, useState } from "react";
import {
  Sparkles,
  Plus,
  X,
  Check,
  Loader2,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  BellRing,
  Globe,
  UserRound,
  Smile,
} from "lucide-react";
import logo from "../assets/logo.png";
import { GmailLogo, SlackLogo } from "./BrandLogos.jsx";
import SlackWebhookHelp from "./SlackWebhookHelp.jsx";
import SiteCatalog from "./SiteCatalog.jsx";
import ProfileAttributeEditor from "./ProfileAttributeEditor.jsx";
import { useToast } from "../context/toast.js";
import { createInterest, deleteInterest } from "../api/interestApi.js";
import { createAlertChannel } from "../api/alertApi.js";
import {
  createSourceSubscription,
  deleteSourceSubscription,
} from "../api/sourceApi.js";
import { completeOnboarding } from "../api/authApi.js";
import { updateProfile } from "../api/profileApi.js";
import { useProfileAttributes } from "../hooks/useProfileAttributes.js";

const STEPS = [
  // 호칭을 맨 앞에 둔다 — 첫 질문이 가벼울수록 이탈이 적고, 이후 단계에서
  // "OO님" 으로 부를 수 있다. 상세 프로필은 그다음이다.
  { id: 1, label: "호칭", Icon: Smile },
  { id: 2, label: "프로필", Icon: UserRound },
  { id: 2, label: "관심사", Icon: Sparkles },
  { id: 3, label: "알림", Icon: BellRing },
  { id: 4, label: "사이트", Icon: Globe },
];

const LAST_STEP = STEPS.length;
const NICKNAME_MAX = 32;

const KEYWORD_SUGGESTIONS = [
  "인턴",
  "신입 채용",
  "장학금",
  "공모전",
  "대외활동",
  "개발",
  "디자인",
  "마케팅",
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function OnboardingWizard({ user, onComplete, onNicknameSaved }) {
  const toast = useToast();

  const [step, setStep] = useState(1);
  const [finishing, setFinishing] = useState(false);

  // Step 1 — 표시 이름. 비워두면 이메일 로컬파트로 폴백하므로 건너뛸 수 있다.
  const [nickname, setNickname] = useState(user?.nickname || "");
  const [savingNickname, setSavingNickname] = useState(false);

  // Step 2 — profile (고정·보편 필드 + 자유서술 bio). Prefilled from user prop.
  const [profile, setProfile] = useState({
    age: user?.age != null ? String(user.age) : "",
    gender: user?.gender || "",
    region: user?.region || "",
    job: user?.job || "",
    bio: user?.bio || "",
  });
  const profileSaved = useRef(false);

  const setProfileField = (key) => (event) =>
    setProfile((prev) => ({ ...prev, [key]: event.target.value }));

  // Step 1 — 사용자 지정 커스텀 필드(ProfileAttribute). interests 처럼 즉시 저장한다.
  // 로딩·CRUD·에러 처리는 '내 정보 설정' 모달과 공유하는 훅에 위임한다.
  const {
    attributes,
    create: handleAttributeCreate,
    update: handleAttributeUpdate,
    remove: handleAttributeDelete,
  } = useProfileAttributes();

  // Best-effort profile persistence. Never blocks progression (mirrors finish()).
  const saveProfile = async () => {
    if (profileSaved.current) return;
    const payload = {};
    Object.entries(profile).forEach(([key, raw]) => {
      const value = typeof raw === "string" ? raw.trim() : raw;
      if (value === "" || value == null) return;
      if (key === "age") {
        const num = Number(value);
        if (Number.isFinite(num)) payload.age = num;
        return;
      }
      payload[key] = value;
    });
    if (Object.keys(payload).length === 0) {
      profileSaved.current = true;
      return;
    }
    try {
      await updateProfile(payload);
      profileSaved.current = true;
    } catch {
      // 저장 실패해도 온보딩 진행을 막지 않는다.
    }
  };

  // Step 2 — interests (persisted as you go)
  const [keywords, setKeywords] = useState([]); // { id, keyword }
  const [keywordInput, setKeywordInput] = useState("");
  const [addingKeyword, setAddingKeyword] = useState(false);

  // Step 3 — channels
  const [email, setEmail] = useState(user?.email || "");
  const [emailStatus, setEmailStatus] = useState(null); // null | 'busy' | {ok,error}
  const [webhook, setWebhook] = useState("");
  const [slackStatus, setSlackStatus] = useState(null);

  // Step 4 — sites (local subscribed map: url -> { subscriptionId, sourceId })
  const [subscribed, setSubscribed] = useState({});

  const existingKeywords = useMemo(
    () => new Set(keywords.map((item) => item.keyword)),
    [keywords],
  );

  const addKeyword = async (raw) => {
    const keyword = raw.trim();
    if (!keyword || existingKeywords.has(keyword) || addingKeyword) return;
    setAddingKeyword(true);
    try {
      const created = await createInterest({ keyword, priority: 1 });
      setKeywords((prev) => [...prev, created]);
      setKeywordInput("");
    } catch (error) {
      toast.error(error.message || "키워드 추가에 실패했어요.");
    } finally {
      setAddingKeyword(false);
    }
  };

  const removeKeyword = async (item) => {
    setKeywords((prev) => prev.filter((k) => k.id !== item.id));
    try {
      await deleteInterest(item.id);
    } catch {
      // 실패 시 되돌리기
      setKeywords((prev) => [...prev, item]);
      toast.error("키워드 삭제에 실패했어요.");
    }
  };

  const connectEmail = async () => {
    const address = email.trim();
    if (!EMAIL_RE.test(address)) {
      toast.error("올바른 이메일 형식을 입력해주세요.");
      return;
    }
    setEmailStatus("busy");
    try {
      const channel = await createAlertChannel({
        type: "email",
        config: { address },
      });
      const confirmation = channel.confirmation ?? { ok: true };
      setEmailStatus(confirmation);
    } catch (error) {
      toast.error(error.message || "이메일 연동에 실패했어요.");
      setEmailStatus(null);
    }
  };

  const connectSlack = async () => {
    const url = webhook.trim();
    if (!/^https:\/\/hooks\.slack\.com\/services\/.+/i.test(url)) {
      toast.error("https://hooks.slack.com/services/... 형식의 URL을 입력해주세요.");
      return;
    }
    setSlackStatus("busy");
    try {
      const channel = await createAlertChannel({
        type: "slack",
        config: { webhook_url: url },
      });
      const confirmation = channel.confirmation ?? { ok: true };
      setSlackStatus(confirmation);
    } catch (error) {
      toast.error(error.message || "슬랙 연동에 실패했어요.");
      setSlackStatus(null);
    }
  };

  const isSubscribed = (item) => Boolean(subscribed[item.url]);

  const toggleSite = async (item, next) => {
    if (next) {
      try {
        const source = await createSourceSubscription({ url: item.url });
        setSubscribed((prev) => ({
          ...prev,
          [item.url]: { subscriptionId: source.subscriptionId, sourceId: source.id },
        }));
      } catch (error) {
        toast.error(error.message || "구독에 실패했어요.");
      }
      return;
    }
    const entry = subscribed[item.url];
    if (!entry) return;
    try {
      await deleteSourceSubscription(entry.subscriptionId);
      setSubscribed((prev) => {
        const nextMap = { ...prev };
        delete nextMap[item.url];
        return nextMap;
      });
    } catch (error) {
      toast.error(error.message || "구독 해제에 실패했어요.");
    }
  };

  const finish = async () => {
    setFinishing(true);
    // 프로필 스텝을 거치지 않고 "나중에 하기" 로 끝낼 수도 있으니 여기서도 저장 시도.
    await saveProfile();
    try {
      const updated = await completeOnboarding();
      onComplete(updated);
    } catch {
      // 완료 API 실패해도 유저를 막지 않는다 — onboarded 로 간주하고 진행.
      onComplete({ ...user, onboarded: true });
    }
  };

  // 닉네임은 "다음"을 누를 때 저장한다. 프로필 부분수정 엔드포인트를 그대로 쓴다
  // (PATCH /api/account/profile/ 화이트리스트에 nickname 포함). 실패해도 온보딩을
  // 막지 않는다 — 표시 이름은 없으면 이메일 로컬파트로 폴백되므로 치명적이지 않다.
  const saveNickname = async () => {
    const trimmed = nickname.trim();
    if (trimmed === (user?.nickname || "")) return;
    setSavingNickname(true);
    try {
      const updated = await updateProfile({ nickname: trimmed });
      onNicknameSaved?.(updated);
    } catch (error) {
      toast.error(error.message || "이름 저장에 실패했어요. 나중에 바꿀 수 있어요.");
    } finally {
      setSavingNickname(false);
    }
  };

  const goNext = async () => {
    if (step === 1) await saveNickname();
    if (step === 2) {
      // 프로필 스텝을 앞으로 넘어갈 때 best-effort 저장(진행은 막지 않음).
      saveProfile();
    }
    if (step < LAST_STEP) setStep(step + 1);
    else finish();
  };
  const goBack = () => setStep((prev) => Math.max(1, prev - 1));

  const renderStatus = (status) => {
    if (!status || status === "busy") return null;
    return status.ok ? (
      <span className="onbChannelStatus ok">
        <CheckCircle2 size={15} /> 연동됐어요 · 확인 메시지를 보내고 있어요
      </span>
    ) : (
      <span className="onbChannelStatus warn">
        <AlertTriangle size={15} /> 연동은 됐지만 확인 메시지 발송은 실패했어요
        {status.error ? ` (${status.error})` : ""}
      </span>
    );
  };

  return (
    <div className="onb">
      <div className="onbCard">
        <div className="onbHead">
          <div className="lpBrand">
            <img src={logo} className="brandMark" style={{ width: 30, height: 30 }} alt="꽁알꽁알" />
            <strong>꽁알꽁알 시작하기</strong>
          </div>
          <button
            type="button"
            className="onbSkip"
            onClick={finish}
            disabled={finishing}
          >
            나중에 하기
          </button>
        </div>

        <div className="onbProgress" aria-label={`${LAST_STEP}단계 중 ${step}단계`}>
          {STEPS.map((s, index) => (
            <div
              key={s.id}
              className={`onbStepDot ${
                step === s.id ? "active" : step > s.id ? "done" : ""
              }`}
              aria-current={step === s.id ? "step" : undefined}
              style={{ flex: index === STEPS.length - 1 ? "0 0 auto" : undefined }}
            >
              <span className="onbStepNum">
                {step > s.id ? <Check size={15} /> : s.id}
              </span>
              <span className="onbStepLabel">{s.label}</span>
              {index < STEPS.length - 1 && <span className="onbStepBar" />}
            </div>
          ))}
        </div>

        <div className="onbBody">
          {step === 1 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">어떻게 불러드릴까요?</h2>
              <p className="onbStepSub">
                알림과 화면에서 이렇게 불러드릴게요. 나중에 언제든 바꿀 수 있어요.
              </p>

              <div className="onbChipRow">
                <input
                  value={nickname}
                  onChange={(event) => setNickname(event.target.value.slice(0, NICKNAME_MAX))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      goNext();
                    }
                  }}
                  placeholder="예: 현서"
                  aria-label="표시할 이름"
                  maxLength={NICKNAME_MAX}
                  autoFocus
                />
              </div>

              <p className="onbEmptyHint">
                {nickname.trim()
                  ? `반가워요, ${nickname.trim()}님!`
                  : "비워두면 이메일 앞부분으로 불러드릴게요."}
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">당신에 대해 알려주세요</h2>
              <p className="onbStepSub">
                나이·성별·지역·직업 같은 기본 배경과, 직접 추가하는 정보를 알수록
                AI가 더 잘 맞는 공지를 골라줘요. 전부 선택이고, 나중에 언제든 바꿀 수
                있어요.
              </p>

              <div className="onbProfileGrid">
                <label className="onbField">
                  <span className="onbFieldLabel">나이</span>
                  <input
                    className="onbInput"
                    type="number"
                    inputMode="numeric"
                    value={profile.age}
                    onChange={setProfileField("age")}
                    placeholder="예: 24"
                  />
                </label>
                <label className="onbField">
                  <span className="onbFieldLabel">성별</span>
                  <select
                    className="onbInput"
                    value={profile.gender}
                    onChange={setProfileField("gender")}
                  >
                    <option value="">선택 안 함</option>
                    <option value="남성">남성</option>
                    <option value="여성">여성</option>
                    <option value="기타">기타</option>
                  </select>
                </label>
                <label className="onbField">
                  <span className="onbFieldLabel">거주·활동 지역</span>
                  <input
                    className="onbInput"
                    value={profile.region}
                    onChange={setProfileField("region")}
                    placeholder="예: 서울 관악구"
                  />
                </label>
                <label className="onbField">
                  <span className="onbFieldLabel">직업</span>
                  <input
                    className="onbInput"
                    value={profile.job}
                    onChange={setProfileField("job")}
                    placeholder="예: 대학생, 직장인"
                  />
                </label>
              </div>

              <label className="onbField onbFieldFull">
                <span className="onbFieldLabel">
                  기타 · 당신에 대해 자유롭게 알려주세요
                </span>
                <textarea
                  className="onbInput onbTextarea"
                  value={profile.bio}
                  onChange={setProfileField("bio")}
                  rows={4}
                  placeholder="정형 항목에 없는 건 뭐든 적어주세요 — 가족관계, 라이프스타일, 자격·혜택 조건, 취향 등 자유롭게."
                />
              </label>

              <div className="onbCustomFields">
                <span className="onbFieldLabel">추가 정보 (내가 만든 필드)</span>
                <p className="onbStepSub">
                  나에게 맞는 배경·자격을 직접 추가하세요. 예: 거주 형태, 자녀 유무,
                  반려동물, 사용 통신사, 관심 취미 등. 추가하면 바로 저장돼요.
                </p>
                <ProfileAttributeEditor
                  attributes={attributes}
                  onCreate={handleAttributeCreate}
                  onUpdate={handleAttributeUpdate}
                  onDelete={handleAttributeDelete}
                />
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">어떤 공지를 받고 싶으세요?</h2>
              <p className="onbStepSub">
                관심 키워드를 알려주면 AI가 이 조건에 맞는 공지를 골라줘요. 나중에
                언제든 바꿀 수 있어요.
              </p>

              <div className="onbChipRow">
                <input
                  value={keywordInput}
                  onChange={(event) => setKeywordInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addKeyword(keywordInput);
                    }
                  }}
                  placeholder="키워드 입력 (예: 백엔드 인턴)"
                  aria-label="관심 키워드"
                />
                <button
                  type="button"
                  className="onbInlineBtn"
                  onClick={() => addKeyword(keywordInput)}
                  disabled={addingKeyword || !keywordInput.trim()}
                >
                  {addingKeyword ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <Plus size={16} />
                  )}
                  추가
                </button>
              </div>

              <div className="onbSuggests">
                {KEYWORD_SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="suggestChip"
                    onClick={() => addKeyword(suggestion)}
                    disabled={existingKeywords.has(suggestion) || addingKeyword}
                  >
                    <Plus size={13} /> {suggestion}
                  </button>
                ))}
              </div>

              {keywords.length > 0 ? (
                <div className="onbKeywordList">
                  {keywords.map((item) => (
                    <span key={item.id} className="onbKeywordChip">
                      {item.keyword}
                      <button
                        type="button"
                        onClick={() => removeKeyword(item)}
                        aria-label={`${item.keyword} 제거`}
                      >
                        <X size={13} />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="onbEmptyHint">
                  아직 키워드가 없어요. 위에서 추천을 눌러 빠르게 시작해보세요.
                </p>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">어디로 알림을 보낼까요?</h2>
              <p className="onbStepSub">
                선별된 공지를 받을 채널이에요. 이메일은 기본, 슬랙은 선택이에요.
              </p>

              <div className="onbChannelBlock">
                <div className="onbChannelTop">
                  <span className="onbChannelIcon email">
                    <GmailLogo size={22} />
                  </span>
                  <div className="onbChannelMeta">
                    <strong>이메일 알림</strong>
                    <p>가입한 이메일로 공지를 보내드려요.</p>
                  </div>
                </div>
                <div className="onbChannelBody">
                  <div className="onbConnectRow">
                    <input
                      className="onbInput"
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="example@email.com"
                      aria-label="알림 받을 이메일"
                      disabled={emailStatus && emailStatus !== "busy"}
                    />
                    <button
                      type="button"
                      className="onbInlineBtn"
                      onClick={connectEmail}
                      disabled={Boolean(emailStatus)}
                    >
                      {emailStatus === "busy" ? (
                        <Loader2 size={16} className="spin" />
                      ) : emailStatus ? (
                        <Check size={16} />
                      ) : (
                        <Plus size={16} />
                      )}
                      {emailStatus && emailStatus !== "busy" ? "연동됨" : "연동"}
                    </button>
                  </div>
                  {renderStatus(emailStatus)}
                </div>
              </div>

              <div className="onbChannelBlock">
                <div className="onbChannelTop">
                  <span className="onbChannelIcon slack">
                    <SlackLogo size={22} />
                  </span>
                  <div className="onbChannelMeta">
                    <strong>
                      슬랙 알림 <span style={{ color: "var(--c-text-faint)" }}>(선택)</span>
                      <SlackWebhookHelp />
                    </strong>
                    <p>슬랙 Incoming Webhook 주소를 붙여넣으면 채널로 받아요.</p>
                  </div>
                </div>
                <div className="onbChannelBody">
                  <div className="onbConnectRow">
                    <input
                      className="onbInput"
                      type="url"
                      value={webhook}
                      onChange={(event) => setWebhook(event.target.value)}
                      placeholder="https://hooks.slack.com/services/..."
                      aria-label="슬랙 Webhook URL"
                      disabled={slackStatus && slackStatus !== "busy"}
                    />
                    <button
                      type="button"
                      className="onbInlineBtn"
                      onClick={connectSlack}
                      disabled={Boolean(slackStatus) || !webhook.trim()}
                    >
                      {slackStatus === "busy" ? (
                        <Loader2 size={16} className="spin" />
                      ) : slackStatus ? (
                        <Check size={16} />
                      ) : (
                        <Plus size={16} />
                      )}
                      {slackStatus && slackStatus !== "busy" ? "연동됨" : "연동"}
                    </button>
                  </div>
                  {renderStatus(slackStatus)}
                </div>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">어떤 사이트를 모아볼까요?</h2>
              <p className="onbStepSub">
                구독한 사이트의 새 공지를 자동으로 수집해요. 원하는 만큼 골라보세요.
              </p>
              <SiteCatalog isSubscribed={isSubscribed} onToggle={toggleSite} />
            </div>
          )}
        </div>

        <div className="onbFooter">
          <button
            type="button"
            className="onbNavBtn ghost"
            onClick={goBack}
            disabled={step === 1 || finishing}
          >
            <ArrowLeft size={17} /> 이전
          </button>
          <button
            type="button"
            className="onbNavBtn primary"
            onClick={goNext}
            disabled={finishing || savingNickname}
          >
            {finishing || savingNickname ? (
              <>
                <Loader2 size={17} className="spin" /> 마무리 중...
              </>
            ) : step < LAST_STEP ? (
              <>
                다음 <ArrowRight size={17} />
              </>
            ) : (
              <>
                시작하기 <ArrowRight size={17} />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default OnboardingWizard;
