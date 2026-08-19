import hashlib
import secrets
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    # 로그인 ID 는 이메일이다. username 은 Django/admin 이 요구하는 내부 식별자로만
    # 남아 있고(가입 시 이메일에서 자동 생성), 사용자에게 노출되지 않는다.
    # 알림 수신자 식별과 로그인 조회가 모두 이 필드에 걸리므로 unique 는 필수다.
    email = models.EmailField(max_length=128, unique=True)
    # 화면에 표시할 이름("어떻게 불러드릴까요?"). 온보딩 첫 단계에서 받는다.
    # 비어 있으면 프론트가 이메일 로컬파트로 폴백하므로 blank 를 허용한다.
    nickname = models.CharField(max_length=32, blank=True)
    # 이메일 소유 확인 여부. 미인증이어도 로그인은 되지만, 알림 발송은 막는다
    # (오타/타인 주소로 메일이 나가는 것을 방지 — account/emails.py 참고).
    email_verified = models.BooleanField(default=False)
    # 고정·보편 필드: 대부분의 공지에서 '제약/자격'으로 작용하는 개인 배경.
    age = models.IntegerField(null=True, blank=True)
    job = models.CharField(max_length=128, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    region = models.CharField(max_length=128, blank=True)
    bio = models.TextField(blank=True)  # 자유서술 catch-all: 정형 필드로 못 담는 맥락
    onboarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def display_name(self) -> str:
        """UI 표시용 이름. 닉네임 → 이메일 로컬파트 순으로 폴백한다."""
        return self.nickname or (self.email or "").split("@")[0] or "사용자"

    def __str__(self):
        return f"id={self.id}, email={self.email}"


def hash_verification_token(raw_token: str) -> str:
    """인증 토큰을 저장/조회용 해시로 바꾼다.

    DB 에는 원문 대신 해시만 남긴다. DB 가 유출돼도 그 값으로는 인증을 통과시킬 수
    없다(메일로 전달된 원문을 알아야 한다). 토큰은 128비트 이상 난수라 사전 공격이
    무의미하므로 salt 없는 sha256 으로 충분하다.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class EmailVerification(models.Model):
    """이메일 소유 확인용 일회성 토큰.

    가입 시(그리고 재발송 요청 시) 발급하고, 사용자가 메일의 링크를 열면 소비한다.
    원문 토큰은 저장하지 않는다(:func:`hash_verification_token`).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="email_verifications"
    )
    # 발급 시점의 대상 주소. 사용자가 그 사이 이메일을 바꿨다면 이 토큰은 무효가
    # 되어야 하므로, 검증할 때 user.email 과 비교한다.
    email = models.EmailField(max_length=128)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"EmailVerification(user_id={self.user_id}, email={self.email})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not self.is_expired

    @classmethod
    def issue(cls, user, ttl_hours: int) -> tuple["EmailVerification", str]:
        """새 토큰을 발급하고 ``(레코드, 원문 토큰)`` 을 돌려준다.

        같은 사용자의 기존 미사용 토큰은 즉시 만료시킨다. 재발송을 누르면 이전
        링크가 죽어야 메일함에 살아 있는 링크가 하나만 남는다.
        """
        now = timezone.now()
        cls.objects.filter(user=user, used_at__isnull=True).update(expires_at=now)

        raw_token = secrets.token_urlsafe(32)
        record = cls.objects.create(
            user=user,
            email=user.email,
            token_hash=hash_verification_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        return record, raw_token


class Interest(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interests")
    keyword = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.keyword


class ProfileAttribute(models.Model):
    # Category 2: 도메인별로 달라지는 정보를 사용자가 직접 label+value 로 추가한다.
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="profile_attributes")
    label = models.CharField(max_length=64)    # 예: "학교", "직급", "가입 팬클럽"
    value = models.CharField(max_length=256)   # 예: "서울대학교", "과장", "OO 팬클럽"
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.label}: {self.value}"
