import re
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()

# username 자동 생성에 쓸 안전 문자만 남긴다(영숫자/./_/-/+ → Django 기본 규칙).
_USERNAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._+-]")
_USERNAME_MAX = 140  # AbstractUser.username 은 150자. 접미사 여유를 둔다.


def generate_username_from_email(email: str) -> str:
    """이메일에서 내부용 username 을 만든다(사용자에게 노출되지 않는 식별자).

    로그인 ID 는 이메일이지만 Django/admin 이 username 을 요구하므로 자리를 채운다.
    충돌하면 짧은 랜덤 접미사를 붙여 유니크를 보장한다.
    """
    local = (email or "").split("@")[0]
    base = _USERNAME_SAFE_RE.sub("", local)[:_USERNAME_MAX] or "user"

    username = base
    while User.objects.filter(username=username).exists():
        username = f"{base}-{secrets.token_hex(3)}"
    return username


class SignUpRequestSerializer(serializers.Serializer):
    """회원가입 입력. 로그인 ID 는 이메일이라 아이디는 받지 않는다.

    닉네임도 여기서 받지 않는다 — 가입 폼을 최소로 유지하고, 온보딩 첫 단계에서
    "어떻게 불러드릴까요?"로 묻는다(PATCH /api/account/profile/).
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    # 고정·보편 프로필 필드(모두 optional). validated_data 로 흘러 create() 의 User(**...) 에 반영된다.
    age = serializers.IntegerField(required=False, allow_null=True)
    job = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    region = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip()
        # 로그인 ID 이므로 대소문자를 무시하고 유니크를 본다. 저장도 소문자로 통일해
        # 조회(iexact)와 유니크 제약(대소문자 구분)이 어긋나지 않게 한다.
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return value

    def validate(self, attrs):
        # 비밀번호는 Django AUTH_PASSWORD_VALIDATORS 로 검증한다(최소 길이/흔한 비번/
        # 숫자-only/유저 속성 유사성). 유사성 검사를 위해 아직 저장 전인 임시 User 를
        # 넘겨 이메일과 너무 비슷한 비밀번호를 걸러낸다.
        candidate = User(email=attrs.get("email", ""))
        try:
            validate_password(attrs.get("password", ""), user=candidate)
        except DjangoValidationError as exc:
            # 검증기 메시지를 password 필드 에러로 그대로 전달한다.
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(
            username=generate_username_from_email(validated_data["email"]),
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


class SignInRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class EmailVerifyRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, required=False)
