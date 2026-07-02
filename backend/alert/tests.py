"""alert 앱 테스트: 발송기, 디스패치 서비스, 테스트 발송 엔드포인트.

이메일은 locmem/console 백엔드로, 슬랙은 httpx.post 를 목(mock)으로 대체해
실제 외부 호출 없이 검증한다.
"""

from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from notices.models import InboxNotice, Notice
from sources.models import NoticeSource

from .models import AlertChannel, AlertLog
from .service import dispatch_pending

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

    def _url(self, channel_id):
        return f"/api/alert-channels/{channel_id}/test/"

    def test_owner_email_test_send(self):
        channel = self.make_channel("email", config={"address": "alice@example.com"})
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._url(channel.id))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["error"], "")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("테스트", mail.outbox[0].subject)
        # 테스트 발송은 AlertLog 를 남기지 않는다
        self.assertEqual(AlertLog.objects.count(), 0)

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
