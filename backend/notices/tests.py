"""notices 앱 테스트 — inbox API(목록/저장/읽음)와 AI 상태 엔드포인트.

모두 결정론적이며 실제 LLM/네트워크를 호출하지 않는다. 인증은 APIClient 의
``force_authenticate`` 로 주입한다(쿠키 JWT 흐름을 우회).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from ai.status import mark_degraded
from notices.models import InboxNotice, Notice
from sources.models import NoticeSource

User = get_user_model()

INBOX_URL = "/api/notices/inbox/"
AI_STATUS_URL = "/api/ai/status/"


def _save_url(inbox_id: int) -> str:
    return f"/api/notices/inbox/{inbox_id}/save/"


def _read_url(inbox_id: int) -> str:
    return f"/api/notices/inbox/{inbox_id}/read/"


class InboxFixtures(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.source = NoticeSource.objects.create(
            name="테스트 공지처", url="https://example.com/notices"
        )
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com"
        )
        self.other = User.objects.create_user(
            username="stranger", email="stranger@example.com"
        )

        self.notice_saved = self._make_notice("저장된 공지", 1)
        self.notice_unsaved = self._make_notice("저장 안 된 공지", 2)
        self.inbox_saved = InboxNotice.objects.create(
            user_id=self.user,
            notice_id=self.notice_saved,
            relevance_score=0.9,
            matched_keywords="채용",
            reason="채용 공고로 판단",
            is_saved=True,
        )
        self.inbox_unsaved = InboxNotice.objects.create(
            user_id=self.user,
            notice_id=self.notice_unsaved,
            relevance_score=0.7,
            reason="관련 있음",
            is_saved=False,
        )
        # 다른 사용자의 inbox 행 — 요청자에게 절대 새어 나오면 안 된다.
        other_notice = self._make_notice("남의 공지", 3)
        self.other_inbox = InboxNotice.objects.create(
            user_id=self.other, notice_id=other_notice, reason="남의 것"
        )

    def _make_notice(self, title: str, n: int) -> Notice:
        return Notice.objects.create(
            source_id=self.source,
            url=f"https://example.com/notices/{n}",
            title=title,
            content="본문",
            publisher="ACME",
        )


class InboxListTests(InboxFixtures):
    def test_requires_authentication(self) -> None:
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"detail": "please signin"})

    def test_lists_only_requesting_users_notices(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(INBOX_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {self.inbox_saved.id, self.inbox_unsaved.id})
        self.assertNotIn(self.other_inbox.id, ids)

    def test_response_shape_has_notice_and_inbox_fields(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(INBOX_URL)

        row = next(r for r in response.data if r["id"] == self.inbox_saved.id)
        for key in (
            "id", "notice_id", "notice", "relevance_score",
            "matched_keywords", "reason", "is_read", "is_saved",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["notice"]["title"], "저장된 공지")
        self.assertTrue(row["is_saved"])

    def test_saved_filter_true_returns_only_saved(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(INBOX_URL, {"saved": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {self.inbox_saved.id})

    def test_saved_filter_false_returns_only_unsaved(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(INBOX_URL, {"saved": "false"})

        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {self.inbox_unsaved.id})

    def test_saved_filter_invalid_value_is_rejected(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(INBOX_URL, {"saved": "maybe"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InboxSaveTests(InboxFixtures):
    def test_save_toggle_persists(self) -> None:
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            _save_url(self.inbox_unsaved.id), {"is_saved": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_saved"])
        self.inbox_unsaved.refresh_from_db()
        self.assertTrue(self.inbox_unsaved.is_saved)

        response = self.client.patch(
            _save_url(self.inbox_unsaved.id), {"is_saved": False}, format="json"
        )
        self.assertFalse(response.data["is_saved"])
        self.inbox_unsaved.refresh_from_db()
        self.assertFalse(self.inbox_unsaved.is_saved)

    def test_cannot_save_another_users_notice(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            _save_url(self.other_inbox.id), {"is_saved": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InboxReadTests(InboxFixtures):
    def test_read_mark_defaults_to_true_and_persists(self) -> None:
        self.client.force_authenticate(user=self.user)
        self.assertFalse(self.inbox_unsaved.is_read)

        # 본문 없이 호출하면 읽음(is_read 기본 True) 처리된다.
        response = self.client.patch(_read_url(self.inbox_unsaved.id), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])
        self.inbox_unsaved.refresh_from_db()
        self.assertTrue(self.inbox_unsaved.is_read)

    def test_can_mark_unread(self) -> None:
        self.client.force_authenticate(user=self.user)
        self.inbox_saved.is_read = True
        self.inbox_saved.save(update_fields=["is_read"])

        response = self.client.patch(
            _read_url(self.inbox_saved.id), {"is_read": False}, format="json"
        )
        self.assertFalse(response.data["is_read"])
        self.inbox_saved.refresh_from_db()
        self.assertFalse(self.inbox_saved.is_read)

    def test_requires_authentication(self) -> None:
        response = self.client.patch(
            _read_url(self.inbox_saved.id), {"is_read": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AiStatusEndpointTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()

    @override_settings(LLM_API_KEY="")
    def test_disabled_when_key_missing(self) -> None:
        response = self.client.get(AI_STATUS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data), {"degraded", "reason", "message"}
        )
        self.assertTrue(response.data["degraded"])
        self.assertEqual(response.data["reason"], "disabled")

    @override_settings(LLM_API_KEY="test-key")
    def test_ok_when_key_present_and_not_degraded(self) -> None:
        response = self.client.get(AI_STATUS_URL)
        self.assertFalse(response.data["degraded"])
        self.assertEqual(response.data["reason"], "ok")
        self.assertEqual(response.data["message"], "")

    @override_settings(LLM_API_KEY="test-key")
    def test_quota_flag_surfaces_as_degraded(self) -> None:
        mark_degraded("quota")
        response = self.client.get(AI_STATUS_URL)
        self.assertTrue(response.data["degraded"])
        self.assertEqual(response.data["reason"], "quota")

    def test_status_is_public(self) -> None:
        # 인증 없이도 200(프론트 배너가 로그인 전에도 상태를 읽는다).
        with override_settings(LLM_API_KEY="test-key"):
            response = self.client.get(AI_STATUS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RemovedAiEndpointsTests(TestCase):
    """죽은 AI HTTP 계약(ORM 파이프라인으로 대체됨)이 실제로 사라졌는지 확인."""

    def test_removed_ai_routes_return_404(self) -> None:
        client = APIClient()
        for path in ("/api/ai/notices/", "/api/ai/inbox-notices/"):
            self.assertEqual(
                client.get(path).status_code,
                status.HTTP_404_NOT_FOUND,
                msg=f"{path} 는 제거되어 404 여야 한다",
            )
