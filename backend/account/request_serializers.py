from rest_framework import serializers

class SignUpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField()
    username = serializers.CharField()
    age = serializers.IntegerField(required=False, allow_null=True)
    job = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)

class SignInRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, required=False)