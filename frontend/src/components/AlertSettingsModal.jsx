import { useEffect, useState } from "react";
import { Mail, MessageSquare, Trash2, Send, Loader2, Plus } from "lucide-react";
import ModalShell from "./ModalShell.jsx";
import SlackWebhookHelp from "./SlackWebhookHelp.jsx";
import { useToast } from "../context/toast.js";
import {
  getAlertChannels,
  createAlertChannel,
  updateAlertChannel,
  deleteAlertChannel,
  testAlertChannel,
} from "../api/alertApi.js";

const CHANNEL_META = {
  email: { label: "이메일", Icon: Mail },
  slack: { label: "슬랙", Icon: MessageSquare },
};

function channelSummary(channel) {
  if (channel.type === "email") {
    return channel.config?.address || "가입 이메일로 발송";
  }
  if (channel.type === "slack") {
    return channel.config?.webhook_url
      ? "hooks.slack.com/services/•••"
      : "Webhook 미설정";
  }
  return "";
}

function isValidWebhook(url) {
  return /^https:\/\/hooks\.slack\.com\/services\/.+/i.test(url.trim());
}

function AlertSettingsModal({ currentUser, onClose }) {
  const toast = useToast();

  // 채널 생성 직후 백엔드가 보낸 연동 확인 메시지 결과(confirmation)를 사용자에게 반영한다.
  const reflectConfirmation = (channel, label) => {
    const confirmation = channel.confirmation;
    if (!confirmation) {
      toast.success(`${label} 알림 채널을 추가했어요.`);
    } else if (confirmation.ok) {
      // 확인 메시지는 백그라운드 발송 → "완료"가 아니라 "보내는 중"으로 안내한다.
      toast.success(`${label} 채널이 추가됐어요 · 확인 메시지를 보내고 있어요.`);
    } else {
      toast.info(`${label} 채널을 추가했어요. 확인 메시지 발송은 실패했어요.`);
    }
  };

  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [newEmail, setNewEmail] = useState(currentUser?.email || "");
  const [newWebhook, setNewWebhook] = useState("");
  const [addingType, setAddingType] = useState(null); // 'email' | 'slack' | null

  const [busyId, setBusyId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [testResults, setTestResults] = useState({}); // { [id]: { ok, error } }

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setLoadError("");
      try {
        const data = await getAlertChannels();
        if (active) setChannels(data);
      } catch (error) {
        if (active) setLoadError(error.message || "알림 채널을 불러오지 못했어요.");
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    return () => {
      active = false;
    };
  }, []);

  const handleAddEmail = async () => {
    const address = newEmail.trim();
    if (!address) {
      toast.error("이메일 주소를 입력해주세요.");
      return;
    }

    setAddingType("email");
    try {
      const channel = await createAlertChannel({
        type: "email",
        config: { address },
      });
      setChannels((prev) => [...prev, channel]);
      reflectConfirmation(channel, "이메일");
    } catch (error) {
      toast.error(error.message || "이메일 채널 추가에 실패했어요.");
    } finally {
      setAddingType(null);
    }
  };

  const handleAddSlack = async () => {
    const webhookUrl = newWebhook.trim();
    if (!isValidWebhook(webhookUrl)) {
      toast.error("https://hooks.slack.com/services/... 형식의 URL을 입력해주세요.");
      return;
    }

    setAddingType("slack");
    try {
      const channel = await createAlertChannel({
        type: "slack",
        config: { webhook_url: webhookUrl },
      });
      setChannels((prev) => [...prev, channel]);
      setNewWebhook("");
      reflectConfirmation(channel, "슬랙");
    } catch (error) {
      toast.error(error.message || "슬랙 채널 추가에 실패했어요.");
    } finally {
      setAddingType(null);
    }
  };

  const handleToggleActive = async (channel) => {
    setBusyId(channel.id);
    try {
      const updated = await updateAlertChannel(channel.id, {
        isActive: !channel.isActive,
      });
      setChannels((prev) =>
        prev.map((item) => (item.id === channel.id ? updated : item)),
      );
    } catch (error) {
      toast.error(error.message || "상태 변경에 실패했어요.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (channel) => {
    setBusyId(channel.id);
    try {
      await deleteAlertChannel(channel.id);
      setChannels((prev) => prev.filter((item) => item.id !== channel.id));
      setConfirmDeleteId(null);
      toast.success("알림 채널을 삭제했어요.");
    } catch (error) {
      toast.error(error.message || "삭제에 실패했어요.");
    } finally {
      setBusyId(null);
    }
  };

  const handleTest = async (channel) => {
    setBusyId(channel.id);
    setTestResults((prev) => ({ ...prev, [channel.id]: undefined }));
    try {
      const result = await testAlertChannel(channel.id);
      setTestResults((prev) => ({ ...prev, [channel.id]: result }));
      if (result.ok) {
        toast.success(`${CHANNEL_META[channel.type]?.label} 테스트 메시지를 보냈어요.`);
      } else {
        toast.error(result.error || "테스트 전송에 실패했어요.");
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <ModalShell
      size="md"
      onClose={onClose}
      title="알림 설정"
      subtitle="선별된 공지를 이메일과 슬랙으로 받아보세요."
    >
      <section className="alertSection">
          <h3 className="alertSectionTitle">내 알림 채널</h3>

          {loading ? (
            <div className="alertChannelList">
              {[0, 1].map((key) => (
                <div key={key} className="channelCard skeletonCard">
                  <div className="skeletonLine skeletonAvatar" />
                  <div className="skeletonStack">
                    <div className="skeletonLine w40" />
                    <div className="skeletonLine w70" />
                  </div>
                </div>
              ))}
            </div>
          ) : loadError ? (
            <div className="alertErrorBox">{loadError}</div>
          ) : channels.length === 0 ? (
            <div className="alertEmptyBox">
              아직 등록된 알림 채널이 없어요. 아래에서 이메일이나 슬랙을 추가해보세요.
            </div>
          ) : (
            <div className="alertChannelList">
              {channels.map((channel) => {
                const meta = CHANNEL_META[channel.type] || CHANNEL_META.email;
                const Icon = meta.Icon;
                const isBusy = busyId === channel.id;
                const result = testResults[channel.id];

                return (
                  <div
                    key={channel.id}
                    className={`channelCard ${channel.isActive ? "" : "inactive"}`}
                  >
                    <div className={`channelIcon type-${channel.type}`}>
                      <Icon size={18} />
                    </div>

                    <div className="channelInfo">
                      <div className="channelTopRow">
                        <strong>{meta.label}</strong>
                        <span
                          className={`channelStatus ${channel.isActive ? "on" : "off"}`}
                        >
                          {channel.isActive ? "활성" : "비활성"}
                        </span>
                      </div>
                      <span className="channelSummary">{channelSummary(channel)}</span>

                      {result && (
                        <span
                          className={`channelTestResult ${result.ok ? "ok" : "fail"}`}
                          role="status"
                        >
                          {result.ok
                            ? "테스트 메시지를 보냈어요."
                            : result.error || "테스트 전송에 실패했어요."}
                        </span>
                      )}
                    </div>

                    <div className="channelActions">
                      <button
                        type="button"
                        className="channelTestButton"
                        onClick={() => handleTest(channel)}
                        disabled={isBusy}
                      >
                        {isBusy ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <Send size={14} />
                        )}
                        테스트 전송
                      </button>

                      <button
                        type="button"
                        role="switch"
                        aria-checked={channel.isActive}
                        aria-label={`${meta.label} 알림 ${channel.isActive ? "끄기" : "켜기"}`}
                        className={`switch ${channel.isActive ? "on" : ""}`}
                        onClick={() => handleToggleActive(channel)}
                        disabled={isBusy}
                      >
                        <span className="switchThumb" />
                      </button>

                      {confirmDeleteId === channel.id ? (
                        <div className="deleteConfirm">
                          <button
                            type="button"
                            className="deleteConfirmYes"
                            onClick={() => handleDelete(channel)}
                            disabled={isBusy}
                          >
                            삭제
                          </button>
                          <button
                            type="button"
                            className="deleteConfirmNo"
                            onClick={() => setConfirmDeleteId(null)}
                            disabled={isBusy}
                          >
                            취소
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="channelDeleteButton"
                          onClick={() => setConfirmDeleteId(channel.id)}
                          disabled={isBusy}
                          aria-label={`${meta.label} 채널 삭제`}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="alertSection">
          <h3 className="alertSectionTitle">채널 추가</h3>

          <div className="addChannelBlock">
            <label className="addChannelLabel" htmlFor="alertEmailInput">
              <Mail size={15} /> 이메일
            </label>
            <div className="addChannelRow">
              <input
                id="alertEmailInput"
                type="email"
                value={newEmail}
                onChange={(event) => setNewEmail(event.target.value)}
                placeholder="example@email.com"
              />
              <button
                type="button"
                className="addChannelButton"
                onClick={handleAddEmail}
                disabled={addingType === "email"}
              >
                {addingType === "email" ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Plus size={15} />
                )}
                추가
              </button>
            </div>
            <p className="addChannelHint">
              비워두면 가입한 이메일 주소로 발송돼요.
            </p>
          </div>

          <div className="addChannelBlock">
            <label className="addChannelLabel" htmlFor="alertSlackInput">
              <MessageSquare size={15} /> 슬랙 Webhook URL
              <SlackWebhookHelp />
            </label>
            <div className="addChannelRow">
              <input
                id="alertSlackInput"
                type="url"
                value={newWebhook}
                onChange={(event) => setNewWebhook(event.target.value)}
                placeholder="https://hooks.slack.com/services/..."
              />
              <button
                type="button"
                className="addChannelButton"
                onClick={handleAddSlack}
                disabled={addingType === "slack"}
              >
                {addingType === "slack" ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Plus size={15} />
                )}
                추가
              </button>
            </div>
            <p className="addChannelHint">
              슬랙 워크스페이스의 Incoming Webhook 주소를 붙여넣으세요. 옆의 ? 를
              누르면 발급 방법을 볼 수 있어요.
            </p>
          </div>
        </section>
    </ModalShell>
  );
}

export default AlertSettingsModal;
