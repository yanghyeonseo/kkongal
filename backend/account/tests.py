"""account 앱 테스트: 회원가입 검증 + 온보딩 완료 엔드포인트.

실제 네트워크/이메일 발송은 일어나지 않는다(가입/온보딩은 외부 발송이 없다).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import ProfileAttribute

User = get_user_model()

SIGNUP_URL = "/api/account/signup/"
ONBOARDING_URL = "/api/account/onboarding/complete/"
PROFILE_URL = "/api/account/profile/"
PROFILE_ATTRIBUTES_URL = "/api/account/profile/attributes/"


def profile_attribute_detail_url(attribute_id):
    return f"/api/account/profile/attributes/{attribute_id}/"

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

    def test_cannot_change_username(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            PROFILE_URL,
            {"username": "hacker", "region": "부산"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        # username 은 프로필 엔드포인트로 못 바꾼다(무시된다).
        self.assertEqual(response.data["username"], "profiler")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profiler")
        self.assertEqual(self.user.region, "부산")


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
