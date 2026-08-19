"""account 앱 테스트: 회원가입 검증 + 온보딩 완료 엔드포인트.

실제 네트워크/이메일 발송은 일어나지 않는다(가입/온보딩은 외부 발송이 없다).
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .emails import issue_and_send_verification
from .models import EmailVerification, ProfileAttribute

User = get_user_model()

SIGNUP_URL = "/api/account/signup/"
SIGNIN_URL = "/api/account/signin/"
VERIFY_URL = "/api/account/verify-email/"
RESEND_URL = "/api/account/verify-email/resend/"
ONBOARDING_URL = "/api/account/onboarding/complete/"
PROFILE_URL = "/api/account/profile/"
PROFILE_ATTRIBUTES_URL = "/api/account/profile/attributes/"


def profile_attribute_detail_url(attribute_id):
    return f"/api/account/profile/attributes/{attribute_id}/"

# 모든 검증기(최소 길이/흔한 비번/숫자-only/유저 속성 유사성)를 통과하는 비밀번호.
STRONG_PASSWORD = "Str0ngPass!2026"

LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


class SignUpValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_weak_password_rejected(self):
        # 너무 짧고 숫자-only → AUTH_PASSWORD_VALIDATORS 에 걸린다.
        response = self.client.post(
            SIGNUP_URL,
            {"email": "newbie@example.com", "password": "1234"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        # 검증기 메시지가 실제로 담겨 있어야 한다.
        self.assertTrue(len(response.data["password"]) >= 1)
        self.assertFalse(User.objects.filter(email="newbie@example.com").exists())

    def test_common_password_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"email": "newbie@example.com", "password": "password"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_invalid_email_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"email": "not-an-email", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_missing_email_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user(
            username="existing", email="dup@example.com", password=STRONG_PASSWORD
        )
        response = self.client.post(
            SIGNUP_URL,
            # 대소문자만 다른 이메일도 중복으로 거부되어야 한다.
            {"email": "DUP@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_username_is_generated_from_email(self):
        """가입 폼은 아이디를 받지 않는다 — 서버가 이메일에서 만들어 넣는다."""
        response = self.client.post(
            SIGNUP_URL,
            {"email": "hong.gil-dong@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        # 내부 식별자라 응답에는 실리지 않는다(프론트가 표시명으로 오해하면 안 된다).
        self.assertNotIn("username", response.data)

        user = User.objects.get(email="hong.gil-dong@example.com")
        self.assertEqual(user.username, "hong.gil-dong")

    def test_generated_username_avoids_collision(self):
        """로컬파트가 같은 다른 도메인으로 가입해도 username 이 충돌하지 않는다."""
        User.objects.create_user(
            username="taken", email="taken@example.com", password=STRONG_PASSWORD
        )
        response = self.client.post(
            SIGNUP_URL,
            {"email": "taken@other.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        user = User.objects.get(email="taken@other.com")
        self.assertNotEqual(user.username, "taken")
        self.assertTrue(user.username.startswith("taken-"))

    def test_email_is_stored_lowercased(self):
        """조회는 iexact, 유니크 제약은 대소문자 구분이라 저장 시 소문자로 통일한다."""
        response = self.client.post(
            SIGNUP_URL,
            {"email": "MixedCase@Example.COM", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email="mixedcase@example.com").exists())

    def test_valid_signup_returns_onboarded_false(self):
        response = self.client.post(
            SIGNUP_URL,
            {"email": "fresh@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("onboarded", response.data)
        self.assertFalse(response.data["onboarded"])
        # 비밀번호는 응답에 노출되지 않는다.
        self.assertNotIn("password", response.data)
        # JWT 쿠키 성공 동작 유지.
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)

        user = User.objects.get(email="fresh@example.com")
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertFalse(user.onboarded)


class OnboardingCompleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="onboarder", email="onb@example.com", password=STRONG_PASSWORD
        )

    def test_requires_auth(self):
        response = self.client.post(ONBOARDING_URL)
        self.assertEqual(response.status_code, 401)

    def test_flips_onboarded_true(self):
        self.assertFalse(self.user.onboarded)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(ONBOARDING_URL)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["onboarded"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.onboarded)


class ProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="profiler", email="prof@example.com", password=STRONG_PASSWORD
        )

    def test_requires_auth(self):
        response = self.client.patch(
            PROFILE_URL, {"region": "서울 관악구"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_updates_profile_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            PROFILE_URL,
            {"region": "서울 관악구", "job": "학생", "bio": "국가장학금 5구간", "age": 24},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["region"], "서울 관악구")
        self.assertEqual(response.data["job"], "학생")
        self.assertEqual(response.data["bio"], "국가장학금 5구간")
        self.assertEqual(response.data["age"], 24)
        self.user.refresh_from_db()
        self.assertEqual(self.user.region, "서울 관악구")
        self.assertEqual(self.user.job, "학생")
        self.assertEqual(self.user.bio, "국가장학금 5구간")
        self.assertEqual(self.user.age, 24)

    def test_cannot_change_identity_fields(self):
        """이메일(로그인 ID)·username·인증 상태는 프로필 엔드포인트로 못 바꾼다."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            PROFILE_URL,
            {
                "username": "hacker",
                "email": "hacker@example.com",
                "email_verified": True,
                "region": "부산",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        # 화이트리스트 밖 필드는 조용히 무시되고, 허용 필드만 반영된다.
        self.assertEqual(response.data["email"], "prof@example.com")
        self.assertFalse(response.data["email_verified"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profiler")
        self.assertEqual(self.user.email, "prof@example.com")
        self.assertFalse(self.user.email_verified)
        self.assertEqual(self.user.region, "부산")

    def test_nickname_updated_and_trimmed(self):
        """온보딩 1단계가 쓰는 경로. 공백은 잘라내고 길이 제한을 넘기지 않는다."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            PROFILE_URL, {"nickname": "  현서  "}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["nickname"], "현서")

        response = self.client.patch(
            PROFILE_URL, {"nickname": "가" * 50}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(len(self.user.nickname), 32)


class ProfileAttributeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="attr_owner", email="attr@example.com", password=STRONG_PASSWORD
        )
        self.other = User.objects.create_user(
            username="attr_other", email="other@example.com", password=STRONG_PASSWORD
        )

    def test_list_requires_auth(self):
        response = self.client.get(PROFILE_ATTRIBUTES_URL)
        self.assertEqual(response.status_code, 401)

    def test_create_requires_auth(self):
        response = self.client.post(
            PROFILE_ATTRIBUTES_URL, {"label": "학교", "value": "서울대학교"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_create_attribute(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            PROFILE_ATTRIBUTES_URL, {"label": "학교", "value": "서울대학교"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["label"], "학교")
        self.assertEqual(response.data["value"], "서울대학교")
        self.assertEqual(response.data["user_id"], self.user.id)
        self.assertTrue(
            ProfileAttribute.objects.filter(id=response.data["id"], user_id=self.user).exists()
        )

    def test_list_returns_only_own_newest_first(self):
        ProfileAttribute.objects.create(user_id=self.user, label="학교", value="서울대")
        ProfileAttribute.objects.create(user_id=self.user, label="직급", value="과장")
        # 다른 사용자의 attribute 는 목록에 섞이면 안 된다.
        ProfileAttribute.objects.create(user_id=self.other, label="부서", value="영업")

        self.client.force_authenticate(user=self.user)
        response = self.client.get(PROFILE_ATTRIBUTES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        # 최신순: 나중에 만든 "직급" 이 먼저 온다.
        self.assertEqual(response.data[0]["label"], "직급")
        self.assertEqual(response.data[1]["label"], "학교")

    def test_update_attribute(self):
        attribute = ProfileAttribute.objects.create(
            user_id=self.user, label="직급", value="사원"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.put(
            profile_attribute_detail_url(attribute.id),
            {"label": "직급", "value": "과장"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["value"], "과장")
        attribute.refresh_from_db()
        self.assertEqual(attribute.value, "과장")

    def test_delete_attribute(self):
        attribute = ProfileAttribute.objects.create(
            user_id=self.user, label="학교", value="서울대"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(profile_attribute_detail_url(attribute.id))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProfileAttribute.objects.filter(id=attribute.id).exists())

    def test_cannot_update_others_attribute(self):
        attribute = ProfileAttribute.objects.create(
            user_id=self.other, label="학교", value="연세대"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.put(
            profile_attribute_detail_url(attribute.id),
            {"label": "학교", "value": "고려대"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        attribute.refresh_from_db()
        self.assertEqual(attribute.value, "연세대")

    def test_cannot_delete_others_attribute(self):
        attribute = ProfileAttribute.objects.create(
            user_id=self.other, label="학교", value="연세대"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(profile_attribute_detail_url(attribute.id))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProfileAttribute.objects.filter(id=attribute.id).exists())

    def test_detail_requires_auth(self):
        attribute = ProfileAttribute.objects.create(
            user_id=self.user, label="학교", value="서울대"
        )
        response = self.client.delete(profile_attribute_detail_url(attribute.id))
        self.assertEqual(response.status_code, 401)


class SignInTests(TestCase):
    """로그인은 이메일로 한다(아이디 개념이 사라졌다)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="signin-internal",
            email="signin@example.com",
            password=STRONG_PASSWORD,
        )

    def test_signin_with_email(self):
        response = self.client.post(
            SIGNIN_URL,
            {"email": "signin@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)

    def test_signin_email_is_case_insensitive(self):
        """가입은 소문자로 저장하지만 대문자로 입력해도 로그인돼야 한다."""
        response = self.client.post(
            SIGNIN_URL,
            {"email": "SignIn@Example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_signin_with_username_no_longer_works(self):
        response = self.client.post(
            SIGNIN_URL,
            {"username": "signin-internal", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_wrong_password_does_not_reveal_account_existence(self):
        """가입 여부가 새어나가지 않도록 실패 메시지를 구분하지 않는다."""
        known = self.client.post(
            SIGNIN_URL,
            {"email": "signin@example.com", "password": "WrongPass!2026"},
            format="json",
        )
        unknown = self.client.post(
            SIGNIN_URL,
            {"email": "nobody@example.com", "password": "WrongPass!2026"},
            format="json",
        )
        self.assertEqual(known.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(known.data["message"], unknown.data["message"])


class EmailVerificationTests(TestCase):
    """가입 시 발급되는 일회성 토큰으로 이메일 소유를 확인한다."""

    def setUp(self):
        self.client = APIClient()

    def _signup(self, email="verify@example.com"):
        response = self.client.post(
            SIGNUP_URL, {"email": email, "password": STRONG_PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        return User.objects.get(email=email)

    def test_signup_creates_unverified_user_and_token(self):
        user = self._signup()
        self.assertFalse(user.email_verified)
        self.assertEqual(EmailVerification.objects.filter(user=user).count(), 1)

    def test_verify_marks_user_verified(self):
        user = self._signup()
        record, raw = EmailVerification.issue(user, ttl_hours=48)

        response = self.client.post(VERIFY_URL, {"token": raw}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["email_verified"])

        user.refresh_from_db()
        record.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(record.used_at)

    def test_verify_works_without_login(self):
        """메일을 다른 브라우저/폰에서 열 수 있으므로 인증은 로그인 없이 동작해야 한다."""
        user = self._signup()
        _record, raw = EmailVerification.issue(user, ttl_hours=48)

        anonymous = APIClient()  # 쿠키 없음
        response = anonymous.post(VERIFY_URL, {"token": raw}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_invalid_token_rejected(self):
        self._signup()
        response = self.client.post(VERIFY_URL, {"token": "not-a-real-token"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_expired_token_rejected(self):
        user = self._signup()
        record, raw = EmailVerification.issue(user, ttl_hours=48)
        record.expires_at = timezone.now() - timedelta(minutes=1)
        record.save(update_fields=["expires_at"])

        response = self.client.post(VERIFY_URL, {"token": raw}, format="json")
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_reusing_token_after_verification_is_idempotent(self):
        """메일 클라이언트의 링크 프리페치나 새로고침으로 흔히 일어난다 → 200."""
        user = self._signup()
        _record, raw = EmailVerification.issue(user, ttl_hours=48)

        first = self.client.post(VERIFY_URL, {"token": raw}, format="json")
        second = self.client.post(VERIFY_URL, {"token": raw}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["email_verified"])

    def test_issuing_new_token_invalidates_the_previous_one(self):
        """재발송하면 메일함에 살아 있는 링크가 하나만 남아야 한다."""
        user = self._signup()
        _old_record, old_raw = EmailVerification.issue(user, ttl_hours=48)
        _new_record, new_raw = EmailVerification.issue(user, ttl_hours=48)

        stale = self.client.post(VERIFY_URL, {"token": old_raw}, format="json")
        self.assertEqual(stale.status_code, 400)

        fresh = self.client.post(VERIFY_URL, {"token": new_raw}, format="json")
        self.assertEqual(fresh.status_code, 200)

    def test_token_is_not_stored_in_plaintext(self):
        user = self._signup()
        _record, raw = EmailVerification.issue(user, ttl_hours=48)
        self.assertFalse(EmailVerification.objects.filter(token_hash=raw).exists())

    def test_resend_requires_login(self):
        response = self.client.post(RESEND_URL, {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_resend_rejected_when_already_verified(self):
        user = self._signup()
        user.email_verified = True
        user.save(update_fields=["email_verified"])

        self.client.force_authenticate(user=user)
        response = self.client.post(RESEND_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)

    @mock.patch("account.views.issue_and_send_verification")
    def test_signup_triggers_verification_email(self, mock_send):
        """뷰의 계약은 '발송을 트리거하고 즉시 응답'이다. 실제 발송 내용은 아래에서
        스레드를 join 해 결정적으로 검증한다(alert 앱의 비동기 발송과 같은 패턴)."""
        response = self.client.post(
            SIGNUP_URL,
            {"email": "trigger@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        mock_send.assert_called_once()
        self.assertEqual(
            mock_send.call_args.args[0], User.objects.get(email="trigger@example.com")
        )

    @override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
    def test_verification_email_content(self):
        """실제 메일: 제목·인증 링크·유효시간 안내가 담기고, 링크의 토큰이 실제로 통한다."""
        user = User.objects.create_user(
            username="mailer", email="mailer@example.com", password=STRONG_PASSWORD
        )
        mail.outbox.clear()

        thread = issue_and_send_verification(user)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["mailer@example.com"])
        self.assertIn("인증", message.subject)
        self.assertIn("/verify-email?token=", message.body)

        # 메일에 실린 링크의 토큰이 실제로 인증을 통과시켜야 한다(해시 저장이라
        # 원문은 메일에서만 얻을 수 있다 — 링크가 곧 계약이다).
        token = message.body.split("/verify-email?token=")[1].split()[0]
        response = self.client.post(VERIFY_URL, {"token": token}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
