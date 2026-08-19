from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Interest, ProfileAttribute


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "password",
            "email",
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
