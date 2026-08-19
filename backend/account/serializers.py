from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Interest, ProfileAttribute


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # username 은 이메일에서 자동 생성한 내부 식별자라 응답에 싣지 않는다.
        # 프론트가 이걸 표시명으로 쓰면 "hong-a3f2" 같은 값이 화면에 노출된다.
        # 표시명은 nickname(없으면 프론트가 이메일 로컬파트로 폴백)을 쓴다.
        fields = (
            "id",
            "password",
            "email",
            "nickname",
            "email_verified",
            "age",
            "job",
            "gender",
            "region",
            "bio",
            "onboarded",
            "created_at",
        )
        extra_kwargs = {
            "password": {"write_only": True},
            # onboarded 는 온보딩 완료 엔드포인트에서만 갱신한다(가입/수정 입력으로는 못 바꿈).
            "onboarded": {"read_only": True},
            # 이메일 인증 상태는 인증 엔드포인트만 바꾼다.
            "email_verified": {"read_only": True},
        }


class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = (
            "id",
            "user_id",
            "keyword",
            "description",
            "priority",
            "created_at",
        )
        read_only_fields = ("id", "user_id", "created_at")


class ProfileAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileAttribute
        fields = (
            "id",
            "user_id",
            "label",
            "value",
            "created_at",
        )
        read_only_fields = ("id", "user_id", "created_at")
