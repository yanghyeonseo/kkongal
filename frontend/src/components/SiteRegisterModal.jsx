import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Loader2, Pencil, Trash2, Check, X } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import SiteCatalog from "./SiteCatalog.jsx";
import SourceFavicon from "./SourceFavicon.jsx";
import { useToast } from "../context/toast.js";
import {
  createSourceSubscription,
  deleteSourceSubscription,
  updateSourceName,
} from "../api/sourceApi.js";

// 등록 대상은 '공지가 목록으로 쌓이는 게시판' 페이지다. 사이트 메인이나 개별 공지글을
// 넣으면 크롤러가 목록에서 새 글을 뽑아낼 수 없어 수집이 0건이 된다. 글로 설명하면
// 잘 안 읽히므로 O/X 예시를 나란히 보여준다.
const URL_EXAMPLES = {
  good: [
    { url: "example.com/notice", note: "공지 목록 페이지" },
    { url: "example.com/board/list", note: "게시판 목록" },
  ],
  bad: [
    { url: "example.com", note: "사이트 메인" },
    { url: "example.com/notice/1234", note: "개별 공지글" },
  ],
};

function UrlExampleGuide() {
  return (
    <div className="urlGuide">
      <div className="urlGuideCol good">
        <span className="urlGuideHead">
          <Check size={14} aria-hidden="true" /> 이런 주소를 넣어주세요
        </span>
        {URL_EXAMPLES.good.map((item) => (
          <div key={item.url} className="urlGuideItem">
            <code>{item.url}</code>
            <span>{item.note}</span>
          </div>
        ))}
      </div>
      <div className="urlGuideCol bad">
        <span className="urlGuideHead">
          <X size={14} aria-hidden="true" /> 이런 주소는 수집이 안 돼요
        </span>
        {URL_EXAMPLES.bad.map((item) => (
          <div key={item.url} className="urlGuideItem">
            <code>{item.url}</code>
            <span>{item.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// 카탈로그 항목과 구독중 소스를 매칭(우선 sourceId, 없으면 url).
function matchesCatalog(source, item) {
  if (item.sourceId != null && source.id === item.sourceId) return true;
  return source.url === item.url;
}

// 표시용 호스트명 유추(파비콘 대체 텍스트 · "내가 추가한 사이트" 목록의 보조 텍스트).
function hostOf(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function SiteRegisterModal({
  sources,
  onClose,
  onSourceAdded,
  onSourceRemoved,
  onSyncSource,
}) {
  const toast = useToast();

  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);

  // 카탈로그(내장 + 이미 확정·공유된 커스텀) url 집합. SiteCatalog 로드 완료 시
  // onCatalogLoaded 로 전달받아 별도 fetch 없이 "내가 추가한 사이트"를 가려낸다.
  // 카탈로그에 이미 오른(공유된) 사이트는 아래 catalog 그리드에서 관리하므로 여기서는
  // 아직 공유되지 않은 나만의 커스텀 사이트만 보여준다. null === 아직 로드 전.
  const [catalogUrls, setCatalogUrls] = useState(null);
  const handleCatalogLoaded = (catalog) => {
    setCatalogUrls(new Set(catalog.map((item) => item.url)));
  };

  // 표시명 인라인 편집(로컬 반영). 이 모달은 rename 콜백을 부모로부터 받지 않으므로,
  // 성공 시 화면에는 즉시 반영하고 백엔드에도 저장하되, 사이드바 등 다른 화면은
  // 다음 새로고침/재조회 때 최신 이름을 받는다.
  const [nameOverrides, setNameOverrides] = useState({});
  const [renamingId, setRenamingId] = useState(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSavingId, setRenameSavingId] = useState(null);
  const [removingId, setRemovingId] = useState(null);
  const renameInputRef = useRef(null);
  // Enter 로 커밋한 뒤 이어지는 blur(또는 Escape 후 blur)가 다시 저장하지 않도록,
  // 편집 중인 id 를 동기 ref 로도 들고 있어 commit 이 한 번만 실행되게 한다.
  const renamingIdRef = useRef(null);

  useEffect(() => {
    if (renamingId != null && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  const isSubscribed = (item) =>
    sources.some((source) => matchesCatalog(source, item));

  // 내가 추가한 사이트 = 구독 중인 사이트 중 카탈로그(내장+공유 커스텀)에 아직 없는 것.
  const mySites = useMemo(() => {
    if (!catalogUrls) return null;
    return sources
      .filter((source) => !catalogUrls.has(source.url))
      .map((source) => ({
        ...source,
        displayName: nameOverrides[source.id] ?? source.displayName,
      }));
  }, [sources, catalogUrls, nameOverrides]);

  const startRename = (source) => {
    renamingIdRef.current = source.id;
    setRenamingId(source.id);
    setRenameDraft(source.displayName);
  };
  const cancelRename = () => {
    renamingIdRef.current = null;
    setRenamingId(null);
  };

  const commitRename = async (source) => {
    // ref 가드로 Enter+blur / Escape+blur 이중 호출에도 딱 한 번만 저장한다.
    if (renamingIdRef.current !== source.id) return;
    renamingIdRef.current = null;
    setRenamingId(null);
    const name = renameDraft.trim();
    if (!name || name === source.displayName) return;
    setRenameSavingId(source.id);
    try {
      const updated = await updateSourceName(source.id, name);
      const finalName = updated.name || name;
      setNameOverrides((prev) => ({ ...prev, [source.id]: finalName }));
      toast.success(`'${finalName}'(으)로 이름을 바꿨어요.`);
    } catch (error) {
      toast.error(error.message || "이름 변경에 실패했어요.");
    } finally {
      setRenameSavingId(null);
    }
  };

  const handleUnsubscribeMySite = async (source) => {
    setRemovingId(source.id);
    try {
      await deleteSourceSubscription(source.subscriptionId);
      onSourceRemoved?.(source);
      toast.info(`'${source.displayName}' 구독을 해제했어요.`);
    } catch (error) {
      toast.error(error.message || "구독 해제에 실패했어요.");
    } finally {
      setRemovingId(null);
    }
  };

  const handleToggle = async (item, next) => {
    if (next) {
      try {
        const source = await createSourceSubscription({ url: item.url });
        onSourceAdded?.(source);
        toast.success(`'${item.name}' 구독을 시작했어요.`);
        // 첫 구독 직후 자동 동기화 → 새 사이트도 곧바로 공지가 노출되도록.
        onSyncSource?.(source.id, { silentUnsupported: true });
      } catch (error) {
        toast.error(error.message || "구독에 실패했어요.");
      }
      return;
    }

    const subscription = sources.find((source) => matchesCatalog(source, item));
    if (!subscription) return;
    try {
      await deleteSourceSubscription(subscription.subscriptionId);
      onSourceRemoved?.(subscription);
      toast.info(`'${item.name}' 구독을 해제했어요.`);
    } catch (error) {
      toast.error(error.message || "구독 해제에 실패했어요.");
    }
  };

  // 지원 목록에 없는 사이트를 URL 로 직접 등록한다(백엔드가 표시명·파비콘을 추정).
  const handleAddByUrl = async (event) => {
    event.preventDefault();
    const value = url.trim();
    if (!value) {
      toast.error("사이트 URL을 입력해주세요.");
      return;
    }

    const normalized = /^https?:\/\//i.test(value) ? value : `https://${value}`;
    setAdding(true);
    try {
      const source = await createSourceSubscription({ url: normalized });
      onSourceAdded?.(source);
      toast.success(`'${source.displayName}' 구독을 시작했어요.`);
      onSyncSource?.(source.id, { silentUnsupported: true });
      setUrl("");
    } catch (error) {
      toast.error(error.message || "URL 등록에 실패했어요.");
    } finally {
      setAdding(false);
    }
  };

  const subscribedCount = sources.length;

  return (
    <ModalShell
      size="lg"
      onClose={onClose}
      title="사이트 등록"
      subtitle="지원하는 사이트에서 골라 구독하거나, URL로 직접 등록하세요."
    >
      <form className="urlRegisterForm" onSubmit={handleAddByUrl}>
        <label className="urlRegisterLabel" htmlFor="siteUrlInput">
          직접 URL로 등록
        </label>
        <div className="urlRegisterRow">
          <input
            id="siteUrlInput"
            className="urlRegisterInput"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="예: https://example.com/notice (공지 목록 페이지)"
            aria-label="등록할 사이트 URL"
          />
          <button type="submit" className="primaryButton" disabled={adding}>
            {adding ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
            등록
          </button>
        </div>
        <p className="urlRegisterHint">
          <strong>공지가 목록으로 쌓이는 게시판 주소</strong>를 넣어주세요. 사이트 메인이나
          공지글 하나를 넣으면 새 글을 찾아낼 수 없어요.
        </p>

        <UrlExampleGuide />

        <p className="urlRegisterHint">
          지원 목록에 없는 사이트도 URL로 추가할 수 있어요. 첫 동기화 후 AI가 이름과
          카테고리를 자동으로 채우고, 다른 사용자도 검색해 구독할 수 있게 돼요.
        </p>
      </form>

      <div className="registerDivider" />

      <div className="mySitesSection">
        <div className="sectionTitleRow">
          <div>
            <h3>내가 추가한 사이트</h3>
            <p>직접 URL로 등록한 사이트예요. 이름을 바꾸거나 구독을 해제할 수 있어요.</p>
          </div>
          {mySites && mySites.length > 0 && <strong>{mySites.length}개</strong>}
        </div>

        {mySites === null ? (
          <div className="mySitesLoading">
            <Loader2 size={15} className="spin" /> 불러오는 중...
          </div>
        ) : mySites.length === 0 ? (
          <div className="emptyTagBox">아직 직접 추가한 사이트가 없어요.</div>
        ) : (
          <ul className="mySiteList">
            {mySites.map((source) => {
              const isEditing = renamingId === source.id;
              const isSaving = renameSavingId === source.id;
              const isRemoving = removingId === source.id;
              return (
                <li
                  key={source.id}
                  className={`mySiteItem ${isEditing ? "editing" : ""}`}
                >
                  <SourceFavicon
                    name={source.displayName}
                    faviconUrl={source.faviconUrl}
                    siteUrl={source.url}
                    size={32}
                    rounded="9px"
                  />
                  <div className="mySiteInfo">
                    {isEditing ? (
                      <input
                        ref={renameInputRef}
                        className="siteRenameInput"
                        value={renameDraft}
                        onChange={(event) => setRenameDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            commitRename(source);
                          } else if (event.key === "Escape") {
                            event.preventDefault();
                            cancelRename();
                          }
                        }}
                        onBlur={() => commitRename(source)}
                        aria-label={`${source.displayName} 이름 편집`}
                      />
                    ) : (
                      <>
                        <strong>{source.displayName}</strong>
                        <span className="mySiteHost">{hostOf(source.url)}</span>
                      </>
                    )}
                  </div>
                  <div className="mySiteActions">
                    <button
                      type="button"
                      className="iconGhostButton"
                      onClick={() => startRename(source)}
                      disabled={isEditing || isSaving}
                      aria-label={`${source.displayName} 이름 변경`}
                      title="이름 변경"
                    >
                      {isSaving ? (
                        <Loader2 size={15} className="spin" />
                      ) : (
                        <Pencil size={15} />
                      )}
                    </button>
                    <button
                      type="button"
                      className="iconGhostButton danger"
                      onClick={() => handleUnsubscribeMySite(source)}
                      disabled={isRemoving || isEditing}
                      aria-label={`${source.displayName} 구독 해제`}
                      title="구독 해제"
                    >
                      {isRemoving ? (
                        <Loader2 size={15} className="spin" />
                      ) : (
                        <Trash2 size={15} />
                      )}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="registerDivider" />

      <div className="registerListHead">
        <span>지원 사이트</span>
        <strong>{subscribedCount}개 구독 중</strong>
      </div>

      <SiteCatalog
        isSubscribed={isSubscribed}
        onToggle={handleToggle}
        onCatalogLoaded={handleCatalogLoaded}
      />
    </ModalShell>
  );
}

export default SiteRegisterModal;
