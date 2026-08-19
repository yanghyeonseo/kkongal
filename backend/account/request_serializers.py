from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class SignUpRequestSerializer(serializers.Serializer):
    # email 은 알림 발송에 쓰이므로 필수 + 형식 + 유니크(대소문자 무시).
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    username = serializers.CharField()
    # 고정·보편 프로필 필드(모두 optional). validated_data 로 흘러 create() 의 User(**...) 에 반영된다.
    age = serializers.IntegerField(required=False, allow_null=True)
    job = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    region = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip()
        # 대소문자를 무시한 유니크 검사(알림 수신자 식별을 위해 이메일은 유일해야 함).
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("이미 사용 중인 사용자 이름입니다.")
        return value

    def validate(self, attrs):
        # 비밀번호는 Django AUTH_PASSWORD_VALIDATORS 로 검증한다(최소 길이/흔한 비번/
        # 숫자-only/유저 속성 유사성). 유사성 검사를 위해 아직 저장 전인 임시 User 를
        # 넘겨 username/email 과 너무 비슷한 비밀번호를 걸러낸다.
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
        )
        try:
            validate_password(attrs.get("password", ""), user=candidate)
        except DjangoValidationError as exc:
            # 검증기 메시지를 password 필드 에러로 그대로 전달한다.
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class SignInRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, required=False)
