"""alert 앱 테스트: 발송기, 디스패치 서비스, 테스트 발송 엔드포인트.

이메일은 locmem/console 백엔드로, 슬랙은 httpx.post 를 목(mock)으로 대체해
실제 외부 호출 없이 검증한다.
"""

from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from notices.models import InboxNotice, Notice
from sources.models import NoticeSource

from .models import AlertChannel, AlertLog
from .senders import send_channel_connected_async
from .serializers import AlertChannelSerializer
from .service import dispatch_pending
from .throttling import TestSendRateThrottle

User = get_user_model()

LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


def make_slack_response(status_code=200, text="ok"):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    return resp


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class AlertTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw12345!"
        )
        self.source = NoticeSource.objects.create(
            name="서울대 공지", url="https://snu.example.com/notices"
        )

    def make_notice(self, url, title="채용 공고 안내", content="본문"):
        return Notice.objects.create(
            source_id=self.source,
            url=url,
            title=title,
            content=content,
            publisher="커리어센터",
        )

    def make_inbox(
        self,
        notice,
        user=None,
        score=0.9,
        keywords="채용,인턴",
        reason="관심사 '채용'과 관련도가 높습니다.",
        notified_at=None,
    ):
        return InboxNotice.objects.create(
            user_id=user or self.user,
            notice_id=notice,
            relevance_score=score,
            matched_keywords=keywords,
            reason=reason,
            notified_at=notified_at,
        )

    def make_channel(self, ctype, config=None, is_active=True, user=None):
        return AlertChannel.objects.create(
            user_id=user or self.user,
            type=ctype,
            config=config or {},
            is_active=is_active,
        )


class EmailDispatchTests(AlertTestBase):
    def test_email_dispatch_success(self):
        notice = self.make_notice("https://snu.example.com/n/1")
        inbox = self.make_inbox(notice)
        self.make_channel("email", config={})

        summary = dispatch_pending()

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        # 수신자는 config.address 없으면 user.email 폴백
        self.assertEqual(message.to, ["alice@example.com"])
        self.assertIn(notice.title, message.subject)
        # 평문 본문에 이유/키워드/원문 링크/대시보드 링크 포함
        self.assertIn("관련도가 높습니다", message.body)
        self.assertIn("채용", message.body)
        self.assertIn(notice.url, message.body)
        self.assertIn("http://localhost:3000", message.body)
        # HTML 대체본 존재
        self.assertTrue(message.alternatives)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertIn(notice.title, message.alternatives[0][0])

        inbox.refresh_from_db()
        self.assertIsNotNone(inbox.notified_at)

        log = AlertLog.objects.get(inbox_notice_id=inbox)
        self.assertEqual(log.status, AlertLog.Status.SENT)
        self.assertIsNotNone(log.sent_at)
        self.assertEqual(log.error, "")

        self.assertEqual(
            summary,
            {"attempted": 1, "sent": 1, "failed": 0, "users_notified": 1},
        )

    def test_email_recipient_uses_config_address(self):
        notice = self.make_notice("https://snu.example.com/n/2")
        self.make_inbox(notice)
        self.make_channel("email", config={"address": "override@dest.com"})

        dispatch_pending()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["override@dest.com"])

    def test_email_batches_multiple_notices_into_one_message(self):
        n1 = self.make_notice("https://snu.example.com/n/3", title="공고 A")
        n2 = self.make_notice("https://snu.example.com/n/4", title="공고 B")
        i1 = self.make_inbox(n1)
        i2 = self.make_inbox(n2)
        self.make_channel("email")

        summary = dispatch_pending()

        # 한 사용자의 여러 공지는 한 통으로 배치 발송
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("공고 A", body)
        self.assertIn("공고 B", body)
        # 그러나 AlertLog 는 공지별로 기록 (2건)
        self.assertEqual(AlertLog.objects.filter(status="sent").count(), 2)
        for inbox in (i1, i2):
            inbox.refresh_from_db()
            self.assertIsNotNone(inbox.notified_at)
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(summary["sent"], 1)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class SlackDispatchTests(AlertTestBase):
    @mock.patch("alert.senders.httpx.post")
    def test_slack_dispatch_success(self, mock_post):
        mock_post.return_value = make_slack_response(200, "ok")
        notice = self.make_notice("https://snu.example.com/s/1")
        inbox = self.make_inbox(notice)
        self.make_channel("slack", config={"webhook_url": "https://hooks.slack.com/x"})

        summary = dispatch_pending()

        mock_post.assert_called_once()
        called_url = mock_post.call_args.args[0]
        self.assertEqual(called_url, "https://hooks.slack.com/x")
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("blocks", payload)
        self.assertIn("text", payload)

        inbox.refresh_from_db()
        self.assertIsNotNone(inbox.notified_at)
        log = AlertLog.objects.get(inbox_notice_id=inbox)
        self.assertEqual(log.status, AlertLog.Status.SENT)
        self.assertEqual(summary["sent"], 1)

    @mock.patch("alert.senders.httpx.post")
    def test_slack_dispatch_http_failure(self, mock_post):
        mock_post.return_value = make_slack_response(500, "server error")
        notice = self.make_notice("https://snu.example.com/s/2")
        inbox = self.make_inbox(notice)
        self.make_channel("slack", config={"webhook_url": "https://hooks.slack.com/y"})

        summary = dispatch_pending()

        log = AlertLog.objects.get(inbox_notice_id=inbox)
        self.assertEqual(log.status, AlertLog.Status.FAILED)
        self.assertIn("500", log.error)
        # 업스트림 응답 본문("server error")은 API 로 노출되는 error 에 새지 않는다(H3).
        self.assertNotIn("server error", log.error)
        self.assertIsNone(log.sent_at)
        # 실패해도 시도했으므로 재발송 방지를 위해 notified_at 은 설정됨
        inbox.refresh_from_db()
        self.assertIsNotNone(inbox.notified_at)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["sent"], 0)

    @mock.patch("alert.senders.httpx.post")
    def test_slack_exception_is_captured_not_raised(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("boom")
        notice = self.make_notice("https://snu.example.com/s/3")
        inbox = self.make_inbox(notice)
        self.make_channel("slack", config={"webhook_url": "https://hooks.slack.com/z"})

        # 예외가 호출자에게 전파되지 않아야 한다
        summary = dispatch_pending()

        log = AlertLog.objects.get(inbox_notice_id=inbox)
        self.assertEqual(log.status, AlertLog.Status.FAILED)
        self.assertIn("ConnectError", log.error)
        self.assertEqual(summary["failed"], 1)

    def test_slack_missing_webhook_is_failure(self):
        notice = self.make_notice("https://snu.example.com/s/4")
        inbox = self.make_inbox(notice)
        self.make_channel("slack", config={})  # webhook_url 없음

        with override_settings(SLACK_DEFAULT_WEBHOOK_URL=""):
            summary = dispatch_pending()

        log = AlertLog.objects.get(inbox_notice_id=inbox)
        self.assertEqual(log.status, AlertLog.Status.FAILED)
        self.assertIn("webhook_url", log.error)
        self.assertEqual(summary["failed"], 1)

    @mock.patch("alert.senders.httpx.post")
    def test_one_failing_channel_does_not_stop_others(self, mock_post):
        # 슬랙은 실패(500), 이메일은 성공 — 둘 다 시도되어야 한다
        mock_post.return_value = make_slack_response(500, "nope")
        notice = self.make_notice("https://snu.example.com/mix/1")
        inbox = self.make_inbox(notice)
        self.make_channel("slack", config={"webhook_url": "https://hooks.slack.com/a"})
        self.make_channel("email", config={})

        summary = dispatch_pending()

        # 이메일은 정상 발송
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])
        # 두 채널 각각의 로그가 남는다
        self.assertEqual(
            AlertLog.objects.filter(inbox_notice_id=inbox, status="sent").count(),
            1,
        )
        self.assertEqual(
            AlertLog.objects.filter(inbox_notice_id=inbox, status="failed").count(),
            1,
        )
        inbox.refresh_from_db()
        self.assertIsNotNone(inbox.notified_at)
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["users_notified"], 1)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class DedupAndThresholdTests(AlertTestBase):
    def test_already_notified_is_not_resent(self):
        notice = self.make_notice("https://snu.example.com/d/1")
        self.make_inbox(notice, notified_at=timezone.now())
        self.make_channel("email")

        summary = dispatch_pending()

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(AlertLog.objects.count(), 0)
        self.assertEqual(summary["attempted"], 0)

    def test_below_threshold_is_skipped(self):
        notice = self.make_notice("https://snu.example.com/d/2")
        inbox = self.make_inbox(notice, score=0.2)  # 임계값 0.5 미만
        self.make_channel("email")

        summary = dispatch_pending()

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(AlertLog.objects.count(), 0)
        inbox.refresh_from_db()
        self.assertIsNone(inbox.notified_at)
        self.assertEqual(
            summary, {"attempted": 0, "sent": 0, "failed": 0, "users_notified": 0}
        )

    def test_at_threshold_is_included(self):
        notice = self.make_notice("https://snu.example.com/d/3")
        self.make_inbox(notice, score=0.5)  # 경계값 포함
        self.make_channel("email")

        dispatch_pending()

        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class NoChannelTests(AlertTestBase):
    def test_no_active_channel_leaves_notified_null(self):
        notice = self.make_notice("https://snu.example.com/nc/1")
        inbox = self.make_inbox(notice)
        # 채널 없음

        summary = dispatch_pending()

        inbox.refresh_from_db()
        self.assertIsNone(inbox.notified_at)
        self.assertEqual(AlertLog.objects.count(), 0)
        self.assertEqual(summary["users_notified"], 0)

    def test_inactive_channel_only_is_skipped(self):
        notice = self.make_notice("https://snu.example.com/nc/2")
        inbox = self.make_inbox(notice)
        self.make_channel("email", is_active=False)

        summary = dispatch_pending()

        inbox.refresh_from_db()
        self.assertIsNone(inbox.notified_at)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(summary["attempted"], 0)

    def test_unsupported_channel_type_only_is_skipped(self):
        # kakao 는 실제 발송기가 없다(get_sender→None). '발송 가능한 채널 없음'
        # 과 동일하게 취급되어 notified_at 은 NULL 로 남고 아무것도 보내지 않으며,
        # 나중에 email/slack 을 추가하면 재시도된다(블랙홀 방지 — S2).
        notice = self.make_notice("https://snu.example.com/nc/3")
        inbox = self.make_inbox(notice)
        self.make_channel("kakao", config={})

        summary = dispatch_pending()

        inbox.refresh_from_db()
        self.assertIsNone(inbox.notified_at)
        self.assertEqual(AlertLog.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(summary["attempted"], 0)
        self.assertEqual(summary["users_notified"], 0)

    def test_unsupported_channel_alongside_email_still_sends_email(self):
        # kakao(미지원) + email(지원) → email 만 발송, kakao 는 조용히 무시(로그 없음).
        notice = self.make_notice("https://snu.example.com/nc/4")
        inbox = self.make_inbox(notice)
        self.make_channel("kakao", config={})
        self.make_channel("email", config={})

        summary = dispatch_pending()

        self.assertEqual(len(mail.outbox), 1)
        inbox.refresh_from_db()
        self.assertIsNotNone(inbox.notified_at)
        # 발송을 시도한 email 채널에 대해서만 로그가 남는다(1건).
        self.assertEqual(AlertLog.objects.count(), 1)
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(summary["users_notified"], 1)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class UserScopingTests(AlertTestBase):
    def test_dispatch_can_target_single_user(self):
        other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pw12345!"
        )
        n1 = self.make_notice("https://snu.example.com/u/1")
        n2 = self.make_notice("https://snu.example.com/u/2")
        self.make_inbox(n1, user=self.user)
        self.make_inbox(n2, user=other)
        self.make_channel("email", user=self.user)
        self.make_channel("email", user=other)

        summary = dispatch_pending(user=self.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])
        self.assertEqual(summary["users_notified"], 1)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL, LLM_RELEVANCE_THRESHOLD=0.5)
class TestSendEndpointTests(AlertTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        # throttle 은 (설정이 없으면) 프로세스 공유 LocMemCache 를 쓰므로 테스트 간
        # 상태가 남을 수 있다. 각 테스트가 깨끗한 한도에서 시작하도록 초기화한다.
        cache.clear()

    def _url(self, channel_id):
        return f"/api/alert-channels/{channel_id}/test/"

    def test_owner_email_test_send_uses_config_address(self):
        # 테스트 발송은 사용자가 이 채널에 등록한 주소(config.address)로 가야 한다.
        # 사용자가 확인하려는 바로 그 주소로 도착해야 "테스트가 안 온다"가 해결된다.
        channel = self.make_channel("email", config={"address": "dest@example.com"})
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["error"], "")
        self.assertEqual(len(mail.outbox), 1)
        # 회원 이메일(alice@example.com)이 아니라 등록 주소로 발송되어야 한다.
        self.assertEqual(mail.outbox[0].to, ["dest@example.com"])
        self.assertIn("테스트", mail.outbox[0].subject)
        # 테스트 발송은 AlertLog 를 남기지 않는다.
        self.assertEqual(AlertLog.objects.count(), 0)

    def test_owner_email_test_send_falls_back_to_member_email(self):
        # config.address 가 비어 있으면 회원 이메일로 폴백한다.
        channel = self.make_channel("email", config={})
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])

    @mock.patch.object(TestSendRateThrottle, "rate", "2/min")
    def test_test_send_is_rate_limited_per_user(self):
        # 임의 수신자 대량발송 악용 방지: 사용자당 빈도를 제한한다. 한도 안에서는
        # 200, 초과하면 429(Too Many Requests) 를 돌려준다.
        channel = self.make_channel("email", config={"address": "dest@example.com"})
        self.client.force_authenticate(user=self.user)

        for _ in range(2):
            ok_resp = self.client.post(self._url(channel.id))
            self.assertEqual(ok_resp.status_code, 200)

        throttled = self.client.post(self._url(channel.id))
        self.assertEqual(throttled.status_code, 429)
        # 한도 내 2건만 실제 발송되고 초과분은 발송되지 않는다.
        self.assertEqual(len(mail.outbox), 2)

    @mock.patch("alert.senders.httpx.post")
    def test_owner_slack_test_send(self, mock_post):
        mock_post.return_value = make_slack_response(200, "ok")
        channel = self.make_channel(
            "slack", config={"webhook_url": "https://hooks.slack.com/test"}
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        mock_post.assert_called_once()

    def test_slack_test_send_missing_webhook_returns_ok_false(self):
        channel = self.make_channel("slack", config={})
        self.client.force_authenticate(user=self.user)

        with override_settings(SLACK_DEFAULT_WEBHOOK_URL=""):
            response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ok"])
        self.assertIn("webhook_url", response.data["error"])

    def test_non_owner_gets_404(self):
        channel = self.make_channel("email")
        other = User.objects.create_user(
            username="mallory", email="mallory@example.com", password="pw12345!"
        )
        self.client.force_authenticate(user=other)

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_gets_401(self):
        channel = self.make_channel("email")

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 401)


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class ChannelCreateConfirmationTests(AlertTestBase):
    """채널 생성 응답 계약: 즉시 201 + best-effort confirmation, 발송은 논블로킹.

    연동 확인 발송이 SMTP 왕복을 기다리며 요청을 막으면 '추가' 버튼이 무한
    로딩된다(원래 버그). 그래서 뷰는 백그라운드 발송(send_channel_connected_async)
    만 트리거하고 즉시 반환한다. 여기서는 그 '트리거 + 즉시 응답' 계약을 검증하고,
    실제 발송(수신자/webhook)은 아래 ConnectedAsyncSendTests 에서 스레드를 join 해
    결정적으로 검증한다.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    URL = "/api/alert-channels/"

    @mock.patch("alert.views.send_channel_connected_async")
    def test_email_create_returns_201_and_triggers_async_send(self, mock_async):
        response = self.client.post(
            self.URL,
            {"type": "email", "config": {"address": "dest@example.com"}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        # confirmation 은 실제 도착이 아니라 'best-effort 로 발송 시도 중' 상태.
        self.assertTrue(response.data["confirmation"]["pending"])
        self.assertTrue(response.data["confirmation"]["ok"])
        self.assertEqual(response.data["confirmation"]["error"], "")
        # 채널이 실제로 생성됨.
        channel_id = response.data["id"]
        self.assertTrue(AlertChannel.objects.filter(id=channel_id).exists())
        # 발송은 동기 SMTP 가 아니라 백그라운드로 위임된다(무한로딩 방지). 뷰는
        # SMTP 왕복을 기다리지 않으므로 이 시점에 outbox 는 비어 있어야 한다.
        self.assertEqual(len(mail.outbox), 0)
        mock_async.assert_called_once()
        sent_channel, sent_user = mock_async.call_args.args
        self.assertEqual(sent_channel.id, channel_id)
        self.assertEqual(sent_user, self.user)

    @mock.patch("alert.views.send_channel_connected_async")
    def test_slack_create_returns_201_and_triggers_async_send(self, mock_async):
        response = self.client.post(
            self.URL,
            {
                "type": "slack",
                "config": {"webhook_url": "https://hooks.slack.com/services/A/B/C"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["confirmation"]["pending"])
        mock_async.assert_called_once()

    @mock.patch(
        "alert.views.send_channel_connected_async",
        side_effect=RuntimeError("thread spawn failed"),
    )
    def test_async_trigger_failure_never_500s_creation(self, _mock_async):
        # 백그라운드 발송 트리거 단계에서 예외가 나도 채널 생성은 500 이 아니라
        # 201 로 성공해야 한다(발송 실패가 절대 생성을 막지 않는다).
        response = self.client.post(
            self.URL,
            {"type": "email", "config": {"address": "dest@example.com"}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data.get("id"))
        self.assertFalse(response.data["confirmation"]["ok"])
        self.assertFalse(response.data["confirmation"]["pending"])
        self.assertTrue(AlertChannel.objects.filter(id=response.data["id"]).exists())


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class ConnectedAsyncSendTests(AlertTestBase):
    """send_channel_connected_async: 백그라운드 스레드에서 실제 발송을 수행한다.

    스레드를 join 해 결과를 결정적으로 검증한다(운영에서는 join 하지 않음). 스레드는
    ORM 을 건드리지 않으므로(channel/user 는 이미 로드됨) DB 커넥션 이슈가 없다.
    """

    def test_async_email_delivers_to_config_address(self):
        channel = self.make_channel("email", config={"address": "dest@example.com"})

        thread = send_channel_connected_async(channel, self.user)
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(mail.outbox), 1)
        # 연동 확인도 등록 주소로 발송된다(회원 이메일이 아님).
        self.assertEqual(mail.outbox[0].to, ["dest@example.com"])
        self.assertIn("연동", mail.outbox[0].subject)
        # 연동 확인은 실제 공지 알림이 아니므로 AlertLog 를 남기지 않는다.
        self.assertEqual(AlertLog.objects.count(), 0)

    def test_async_email_falls_back_to_member_email(self):
        channel = self.make_channel("email", config={})

        thread = send_channel_connected_async(channel, self.user)
        thread.join(timeout=5)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])

    @mock.patch("alert.senders.httpx.post")
    def test_async_slack_uses_registered_webhook(self, mock_post):
        mock_post.return_value = make_slack_response(200, "ok")
        channel = self.make_channel(
            "slack", config={"webhook_url": "https://hooks.slack.com/services/A/B/C"}
        )

        thread = send_channel_connected_async(channel, self.user)
        thread.join(timeout=5)

        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args.args[0], "https://hooks.slack.com/services/A/B/C"
        )

    @mock.patch("alert.senders.httpx.post", side_effect=httpx.ConnectError("boom"))
    def test_async_send_failure_is_swallowed_not_raised(self, _mock_post):
        # 발송 실패(예외)가 스레드 밖으로 전파되지 않아야 한다(프로세스 안전).
        channel = self.make_channel(
            "slack", config={"webhook_url": "https://hooks.slack.com/services/X/Y/Z"}
        )

        thread = send_channel_connected_async(channel, self.user)
        thread.join(timeout=5)

        # 스레드가 예외 없이 정상 종료(로그만 남김).
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(mail.outbox), 0)


class AlertChannelSerializerValidationTests(TestCase):
    """H3: 채널 config 검증 (슬랙 webhook SSRF 방어 + 이메일 주소 유효성)."""

    def test_slack_rejects_non_hooks_host(self):
        serializer = AlertChannelSerializer(
            data={
                "type": "slack",
                "config": {"webhook_url": "https://evil.example.com/hook"},
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("config", serializer.errors)

    def test_slack_rejects_http_scheme(self):
        serializer = AlertChannelSerializer(
            data={
                "type": "slack",
                "config": {"webhook_url": "http://hooks.slack.com/services/A/B/C"},
            }
        )
        self.assertFalse(serializer.is_valid())

    def test_slack_requires_webhook_url(self):
        serializer = AlertChannelSerializer(data={"type": "slack", "config": {}})
        self.assertFalse(serializer.is_valid())
        self.assertIn("config", serializer.errors)

    def test_slack_accepts_valid_hooks_url(self):
        serializer = AlertChannelSerializer(
            data={
                "type": "slack",
                "config": {
                    "webhook_url": "https://hooks.slack.com/services/T000/B000/XXXXXXXX"
                },
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_email_rejects_invalid_address(self):
        serializer = AlertChannelSerializer(
            data={"type": "email", "config": {"address": "not-an-email"}}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("config", serializer.errors)

    def test_email_allows_empty_address(self):
        serializer = AlertChannelSerializer(data={"type": "email", "config": {}})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_email_accepts_valid_address(self):
        serializer = AlertChannelSerializer(
            data={"type": "email", "config": {"address": "user@example.com"}}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
