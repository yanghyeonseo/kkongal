import { useEffect, useRef, useState } from "react";
import {
  Sparkles,
  ArrowRight,
  Check,
  Mail,
  MessageSquare,
  PenLine,
  Globe,
  BellRing,
  Rss,
} from "lucide-react";
import logo from "../assets/logo.png";

const HOW_STEPS = [
  {
    Icon: PenLine,
    title: "관심사 등록",
    body: "받고 싶은 키워드와 조건을 자연어로 알려주세요. 예: “서울 지역 백엔드 인턴”.",
  },
  {
    Icon: Globe,
    title: "사이트 선택",
    body: "학교·채용·장학·공모전 등 지원 사이트를 골라 구독하면 준비 끝이에요.",
  },
  {
    Icon: Sparkles,
    title: "AI가 선별",
    body: "새로 올라온 공지를 AI가 읽고 당신에게 맞는 것만 관련도와 함께 골라내요.",
  },
  {
    Icon: BellRing,
    title: "알림 받기",
    body: "선별된 공지를 이메일과 슬랙으로 바로 받아보세요. 놓칠 일이 없어요.",
  },
];

const FEATURES = [
  {
    key: "ai",
    Icon: Sparkles,
    title: "AI 맞춤 선별",
    body: "단순 키워드 매칭이 아니라, 공지 내용을 이해해 관련도를 매기고 선별 이유까지 설명해줘요.",
  },
  {
    key: "alert",
    Icon: BellRing,
    title: "멀티채널 알림",
    body: "이메일과 슬랙 웹훅으로 원하는 곳에서 공지를 받아요. 채널마다 켜고 끌 수 있어요.",
  },
  {
    key: "crawl",
    Icon: Rss,
    title: "자동 수집",
    body: "여러 사이트를 대신 주기적으로 돌며 새 공지를 모아요. “동기화” 한 번이면 즉시 최신화돼요.",
  },
];

function Landing({ onOpenAuth }) {
  const [scrolled, setScrolled] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const onScroll = () => setScrolled(el.scrollTop > 8);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className={`landing ${scrolled ? "scrolled" : ""}`} ref={rootRef}>
      <nav className="landingNav">
        <div className="lpBrand">
          <img src={logo} className="brandMark" alt="꽁알꽁알" />
          <strong>꽁알꽁알</strong>
        </div>
        <div className="landingNavActions">
          <button className="lpBtnGhost" onClick={() => onOpenAuth("login")}>
            로그인
          </button>
          <button className="lpBtnPrimary" onClick={() => onOpenAuth("signup")}>
            회원가입
          </button>
        </div>
      </nav>

      <header className="landingHero">
        <div className="heroCopy">
          <span className="heroBadge">
            <Sparkles size={14} /> AI 공지 큐레이션
          </span>
          <h1>
            흩어진 공지,
            <br />
            <em>AI가 골라</em> 한 곳에서.
          </h1>
          <p className="heroSub">
            학교·채용·장학·공모전 사이트를 매번 들여다볼 필요 없어요. 관심사만
            알려주면 꽁알꽁알이 새 공지를 선별해 이메일·슬랙으로 바로 보내드려요.
          </p>
          <div className="heroCtas">
            <button
              className="lpBtnPrimary lpBtnLg"
              onClick={() => onOpenAuth("signup")}
            >
              무료로 시작하기 <ArrowRight size={18} />
            </button>
            <button
              className="lpBtnGhost lpBtnLg"
              onClick={() => onOpenAuth("login")}
            >
              로그인
            </button>
          </div>
          <ul className="heroTrust">
            <li>
              <Check size={16} /> 관심사 기반 선별
            </li>
            <li>
              <Check size={16} /> 이메일·슬랙 알림
            </li>
            <li>
              <Check size={16} /> 지금 무료
            </li>
          </ul>
        </div>

        <div className="heroPreview" aria-hidden="true">
          <div className="previewCard">
            <div className="previewAi">
              <div className="previewAiHead">
                <span className="pvIcon">
                  <Sparkles size={16} />
                </span>
                <div>
                  <strong>AI 추천</strong>
                  <br />
                  <span>오늘 당신에게 꼭 맞는 공지 3건</span>
                </div>
              </div>
              <div className="pvRow">
                <span className="pvRank">1</span>
                <span className="pvBar">
                  <i />
                  <i className="short" />
                </span>
                <span className="pvScore">94%</span>
              </div>
              <div className="pvRow">
                <span className="pvRank">2</span>
                <span className="pvBar">
                  <i />
                  <i className="short" />
                </span>
                <span className="pvScore">88%</span>
              </div>
            </div>

            <div className="pvList">
              <div className="pvNotice">
                <span className="pvLogo" style={{ background: "#1677f2" }} />
                <span className="pvNoticeText">
                  <b />
                  <i />
                </span>
                <span className="pvBadge new">NEW</span>
              </div>
              <div className="pvNotice">
                <span className="pvLogo" style={{ background: "#ff6b2c" }} />
                <span className="pvNoticeText">
                  <b />
                  <i />
                </span>
                <span className="pvBadge dday">D-3</span>
              </div>
              <div className="pvNotice">
                <span className="pvLogo" style={{ background: "#8b5cf6" }} />
                <span className="pvNoticeText">
                  <b />
                  <i />
                </span>
              </div>
            </div>
          </div>

          <div className="previewFloat mail">
            <span className="pvfIcon">
              <Mail size={15} />
            </span>
            메일 발송됨
          </div>
          <div className="previewFloat slack">
            <span className="pvfIcon">
              <MessageSquare size={15} />
            </span>
            슬랙 알림
          </div>
        </div>
      </header>

      <section className="landingSection">
        <div className="sectionHead">
          <span className="sectionKicker">HOW IT WORKS</span>
          <h2>이렇게 동작해요</h2>
          <p>설정은 2분이면 충분해요. 그다음은 꽁알꽁알이 알아서 챙겨드려요.</p>
        </div>
        <ol className="howSteps">
          {HOW_STEPS.map(({ Icon, title, body }) => (
            <li key={title} className="howStep">
              <span className="howIcon">
                <Icon size={22} />
              </span>
              <h3>{title}</h3>
              <p>{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landingSection">
        <div className="sectionHead">
          <span className="sectionKicker">WHY 꽁알꽁알</span>
          <h2>공지 하나 놓치지 않도록</h2>
          <p>필요한 건 다 있고, 번거로운 건 전부 자동이에요.</p>
        </div>
        <div className="featureGrid">
          {FEATURES.map(({ key, Icon, title, body }) => (
            <article key={key} className={`featureCard f-${key}`}>
              <span className="featIcon">
                <Icon size={24} />
              </span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landingCta">
        <h2>오늘 올라온 공지, 이미 놓치고 있을지 몰라요</h2>
        <p>지금 가입하고 관심사에 딱 맞는 공지만 받아보세요.</p>
        <button
          className="lpBtnPrimary lpBtnLg"
          onClick={() => onOpenAuth("signup")}
        >
          무료로 시작하기 <ArrowRight size={18} />
        </button>
      </section>

      <footer className="landingFooter">
        <div className="lpBrand">
          <img src={logo} className="brandMark" style={{ width: 28, height: 28 }} alt="꽁알꽁알" />
          <strong>꽁알꽁알</strong>
        </div>
        <span>관심사 기반 공지 큐레이션 · AI가 골라주는 맞춤 알림</span>
      </footer>
    </div>
  );
}

export default Landing;
