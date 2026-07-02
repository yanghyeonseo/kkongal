"""account 앱 테스트: 회원가입 검증 + 온보딩 완료 엔드포인트.

실제 네트워크/이메일 발송은 일어나지 않는다(가입/온보딩은 외부 발송이 없다).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()

SIGNUP_URL = "/api/account/signup/"
ONBOARDING_URL = "/api/account/onboarding/complete/"

# 모든 검증기(최소 길이/흔한 비번/숫자-only/유저 속성 유사성)를 통과하는 비밀번호.
STRONG_PASSWORD = "Str0ngPass!2026"


class SignUpValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_weak_password_rejected(self):
        # 너무 짧고 숫자-only → AUTH_PASSWORD_VALIDATORS 에 걸린다.
        response = self.client.post(
            SIGNUP_URL,
            {"username": "newbie", "email": "newbie@example.com", "password": "1234"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        # 검증기 메시지가 실제로 담겨 있어야 한다.
        self.assertTrue(len(response.data["password"]) >= 1)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_common_password_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"username": "newbie", "email": "newbie@example.com", "password": "password"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_invalid_email_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"username": "newbie", "email": "not-an-email", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_missing_email_rejected(self):
        response = self.client.post(
            SIGNUP_URL,
            {"username": "newbie", "password": STRONG_PASSWORD},
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
            {"username": "newbie", "email": "DUP@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(
            username="taken", email="a@example.com", password=STRONG_PASSWORD
        )
        response = self.client.post(
            SIGNUP_URL,
            {"username": "taken", "email": "new@example.com", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_valid_signup_returns_onboarded_false(self):
        response = self.client.post(
            SIGNUP_URL,
            {"username": "freshuser", "email": "fresh@example.com", "password": STRONG_PASSWORD},
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

        user = User.objects.get(username="freshuser")
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
