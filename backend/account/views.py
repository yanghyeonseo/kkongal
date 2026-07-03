from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from account.request_serializers import (
    SignInRequestSerializer,
    SignUpRequestSerializer,
    TokenRefreshRequestSerializer,
    LogoutRequestSerializer,
)
from .models import Interest
from .serializers import InterestSerializer, UserSerializer

User = get_user_model()

_ACCESS_MAX_AGE = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
_REFRESH_MAX_AGE = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())


def _cookie_flags():
    """인증 쿠키 공통 플래그(HttpOnly/Secure/SameSite). settings 에서 관리한다."""
    return {
        "httponly": settings.AUTH_COOKIE_HTTPONLY,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }


def _set_access_cookie(response, access_token):
    response.set_cookie(
        "access_token", value=str(access_token), max_age=_ACCESS_MAX_AGE, **_cookie_flags()
    )


def _set_auth_cookies(response, refresh_token):
    """access_token + refresh_token 쿠키를 함께 심는다."""
    _set_access_cookie(response, refresh_token.access_token)
    response.set_cookie(
        "refresh_token", value=str(refresh_token), max_age=_REFRESH_MAX_AGE, **_cookie_flags()
    )


def set_token_on_response_cookie(user, status_code):
    token = RefreshToken.for_user(user)
    response = Response(UserSerializer(user).data, status=status_code)
    _set_auth_cookies(response, token)
    return response


def login_required_response(request):
    """기본 권한이 AllowAny 이므로 로그인이 필요한 뷰는 인증을 직접 확인한다.

    미인증이면 401 응답을, 인증된 요청이면 ``None`` 을 돌려준다.
    """
    if request.user.is_authenticated:
        return None
    return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)


class SignUpView(APIView):
    # 공개 엔드포인트(프로젝트 기본 권한은 IsAuthenticated). 무차별 가입 남용을 막기 위해
    # 'auth' scope 로 빈도 제한한다.
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="회원가입",
        description="회원가입을 진행합니다.",
        request=SignUpRequestSerializer,
        responses={201: "JWT Token 발급", 400: "Bad Request"},
    )
    def post(self, request):
        # 이메일/사용자명/비밀번호 검증은 SignUpRequestSerializer 가 담당하며,
        # 실패 시 raise_exception 이 400 필드 에러로 응답한다.
        serializer = SignUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return set_token_on_response_cookie(user, status_code=status.HTTP_201_CREATED)


class SignInView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="로그인",
        description="로그인을 진행합니다.",
        request=SignInRequestSerializer,
        responses={200: UserSerializer, 400: "Bad Request", 401: "Unauthorized"},
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response(
                {"message": "missing fields ['username', 'password'] in body"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # 사용자 존재 여부를 노출하지 않도록: 사용자가 없으면 더미 해시로 check_password 를
        # 수행해 타이밍 차이를 없애고, 실패 사유를 구분하지 않는 단일 메시지를 돌려준다.
        user = User.objects.filter(username=username).first()
        if user is None:
            User().set_password(password)  # 타이밍 공격 완화용 더미 해시
            password_ok = False
        else:
            password_ok = user.check_password(password)

        if not password_ok:
            return Response(
                {"message": "아이디 또는 비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return set_token_on_response_cookie(user, status_code=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="토큰 재발급",
        description="access 토큰을 재발급 받습니다.",
        request=TokenRefreshRequestSerializer,
        responses={200: "Token refresh 성공"},
    )
    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token") or request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "no refresh token"}, status=status.HTTP_400_BAD_REQUEST
            )

        # 회전(rotation): 제출된 refresh 토큰을 검증한 뒤 블랙리스트에 올리고, 새 refresh +
        # access 토큰을 발급해 쿠키를 교체한다. 탈취된 토큰의 재사용 창을 좁힌다
        # (SIMPLE_JWT ROTATE_REFRESH_TOKENS/BLACKLIST_AFTER_ROTATION 정책과 일치).
        try:
            old_token = RefreshToken(refresh_token)  # 생성 시 서명·만료·블랙리스트 검증
        except TokenError:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )

        user = User.objects.filter(id=old_token.get("user_id")).first()
        if user is None:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            old_token.blacklist()  # token_blacklist 앱 사용 시 재사용 차단
        except AttributeError:
            pass  # 블랙리스트 앱 미설치 환경 방어

        new_refresh = RefreshToken.for_user(user)
        response = Response({"detail": "token refreshed"}, status=status.HTTP_200_OK)
        _set_auth_cookies(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="로그아웃",
        description="사용자를 로그아웃 시킵니다.",
        request=LogoutRequestSerializer,
        responses={201: "No Content", 400: "Bad Request", 401: "unauthorized"},
    )
    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token") or request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "no refresh token"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_token = RefreshToken(refresh_token)
            new_token.verify()
            new_token.blacklist()
        except Exception:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )

        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class MeView(APIView):
    # 하이드레이트용: 미로그인(쿠키 없음/만료)이면 401 을 직접 반환하므로 공개로 둔다.
    permission_classes = [AllowAny]

    @extend_schema(
        summary="현재 로그인 유저 조회",
        description="쿠키의 access_token 기준으로 현재 로그인한 사용자를 조회합니다.",
        responses={200: UserSerializer, 401: "Unauthorized"},
    )
    def get(self, request):
        access_token = request.COOKIES.get("access_token")
        if not access_token:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            validated_token = AccessToken(access_token)
            user = User.objects.get(id=validated_token["user_id"])
        except (KeyError, TokenError, User.DoesNotExist):
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class OnboardingCompleteView(APIView):
    @extend_schema(
        summary="온보딩 완료",
        description="현재 로그인 유저의 온보딩 상태를 완료(onboarded=True)로 표시합니다.",
        request=None,
        responses={200: UserSerializer, 401: "Unauthorized"},
    )
    def post(self, request):
        error = login_required_response(request)
        if error:
            return error

        user = request.user
        user.onboarded = True
        user.save(update_fields=["onboarded"])
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class InterestListView(APIView):
    @extend_schema(
        summary="관심사 목록 조회",
        description="로그인한 사용자의 관심사 목록을 조회합니다.",
        responses={200: InterestSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        error = login_required_response(request)
        if error:
            return error

        interests = Interest.objects.filter(user_id=request.user).order_by(
            "-priority", "-created_at"
        )
        serializer = InterestSerializer(interests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="관심사 생성",
        description="로그인한 사용자의 관심사를 생성합니다.",
        request=InterestSerializer,
        responses={201: InterestSerializer, 400: "Bad Request", 401: "Unauthorized"},
    )
    def post(self, request):
        error = login_required_response(request)
        if error:
            return error

        serializer = InterestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interest = serializer.save(user_id=request.user)
        return Response(InterestSerializer(interest).data, status=status.HTTP_201_CREATED)


class InterestDetailView(APIView):
    def get_interest(self, request, interest_id):
        return get_object_or_404(Interest, id=interest_id, user_id=request.user)

    @extend_schema(
        summary="관심사 수정",
        description="로그인한 사용자의 관심사를 수정합니다.",
        request=InterestSerializer,
        responses={200: InterestSerializer, 400: "Bad Request", 401: "Unauthorized", 404: "Not Found"},
    )
    def put(self, request, interest_id):
        error = login_required_response(request)
        if error:
            return error

        interest = self.get_interest(request, interest_id)
        serializer = InterestSerializer(interest, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="관심사 삭제",
        description="로그인한 사용자의 관심사를 삭제합니다.",
        responses={204: "No Content", 401: "Unauthorized", 404: "Not Found"},
    )
    def delete(self, request, interest_id):
        error = login_required_response(request)
        if error:
            return error

        interest = self.get_interest(request, interest_id)
        interest.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
