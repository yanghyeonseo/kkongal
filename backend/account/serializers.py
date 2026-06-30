from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Interest


User = get_user_model()


class UserIdUsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


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
            "created_at",
        )
        extra_kwargs = {
            "password": {"write_only": True},
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
