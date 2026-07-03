import { useMemo, useState } from "react";
import {
  Sparkles,
  Plus,
  X,
  Mail,
  MessageSquare,
  Check,
  Loader2,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  BellRing,
  Globe,
} from "lucide-react";
import logo from "../assets/logo.png";
import SlackWebhookHelp from "./SlackWebhookHelp.jsx";
import SiteCatalog from "./SiteCatalog.jsx";
import { useToast } from "../context/toast.js";
import { createInterest, deleteInterest } from "../api/interestApi.js";
import { createAlertChannel } from "../api/alertApi.js";
import {
  createSourceSubscription,
  deleteSourceSubscription,
} from "../api/sourceApi.js";
import { completeOnboarding } from "../api/authApi.js";

const STEPS = [
  { id: 1, label: "관심사", Icon: Sparkles },
  { id: 2, label: "알림", Icon: BellRing },
  { id: 3, label: "사이트", Icon: Globe },
];

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

function OnboardingWizard({ user, onComplete }) {
  const toast = useToast();

  const [step, setStep] = useState(1);
  const [finishing, setFinishing] = useState(false);

  // Step 1 — interests (persisted as you go)
  const [keywords, setKeywords] = useState([]); // { id, keyword }
  const [keywordInput, setKeywordInput] = useState("");
  const [addingKeyword, setAddingKeyword] = useState(false);

  // Step 2 — channels
  const [email, setEmail] = useState(user?.email || "");
  const [emailStatus, setEmailStatus] = useState(null); // null | 'busy' | {ok,error}
  const [webhook, setWebhook] = useState("");
  const [slackStatus, setSlackStatus] = useState(null);

  // Step 3 — sites (local subscribed map: url -> { subscriptionId, sourceId })
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
    try {
      const updated = await completeOnboarding();
      onComplete(updated);
    } catch {
      // 완료 API 실패해도 유저를 막지 않는다 — onboarded 로 간주하고 진행.
      onComplete({ ...user, onboarded: true });
    }
  };

  const goNext = () => {
    if (step < 3) setStep(step + 1);
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

        <div className="onbProgress" aria-label={`3단계 중 ${step}단계`}>
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

          {step === 2 && (
            <div className="onbStepInner">
              <h2 className="onbStepHeading">어디로 알림을 보낼까요?</h2>
              <p className="onbStepSub">
                선별된 공지를 받을 채널이에요. 이메일은 기본, 슬랙은 선택이에요.
              </p>

              <div className="onbChannelBlock">
                <div className="onbChannelTop">
                  <span className="onbChannelIcon email">
                    <Mail size={20} />
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
                    <MessageSquare size={20} />
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

          {step === 3 && (
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
            disabled={finishing}
          >
            {finishing ? (
              <>
                <Loader2 size={17} className="spin" /> 마무리 중...
              </>
            ) : step < 3 ? (
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
