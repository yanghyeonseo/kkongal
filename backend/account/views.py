from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from account.request_serializers import SignInRequestSerializer, SignUpRequestSerializer, TokenRefreshRequestSerializer, LogoutRequestSerializer
from .models import Interest
from .serializers import InterestSerializer, UserSerializer

User = get_user_model()

def generate_token_in_serialized_data(user):
    token = RefreshToken.for_user(user)
    refresh_token, access_token = str(token), str(token.access_token)
    serialized_data = UserSerializer(user).data
    serialized_data["token"] = {"access": access_token, "refresh": refresh_token}
    return serialized_data

def set_token_on_response_cookie(user, status_code):
    token = RefreshToken.for_user(user)
    serialized_data = UserSerializer(user).data
    res = Response(serialized_data, status=status_code)
    # res.set_cookie("refresh_token", value=str(token), httponly=True)
    # res.set_cookie("access_token", value=str(token.access_token), httponly=True)
    res.set_cookie("refresh_token", value=str(token))
    res.set_cookie("access_token", value=str(token.access_token))
    return res

class SignUpView(APIView):
    @extend_schema(
        summary="회원가입",
        description="회원가입을 진행합니다.",
        request=SignUpRequestSerializer,
        responses={201: "JWT Token 발급", 400: "Bad Request"},
    )
    def post(self, request):
        user_serializer = UserSerializer(data=request.data)
        if user_serializer.is_valid(raise_exception=True):
            user = user_serializer.save()
            user.set_password(request.data.get("password"))
            user.save()

            # token 추가 & cookie에 담기
            return set_token_on_response_cookie(user, status_code=status.HTTP_201_CREATED)
        return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SignInView(APIView):
    @extend_schema(
        summary="로그인",
        description="로그인을 진행합니다.",
        request=SignInRequestSerializer,
        responses={200: UserSerializer, 404: "Not Found", 400: "Bad Request"},
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response(
                {"message": "missing fields ['username', 'password'] in body"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = User.objects.get(username=username)
            if not user.check_password(password):
                return Response(
                    {"message": "Password is incorrect"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            ## token 추가
            return set_token_on_response_cookie(user, status_code=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response(
                {"message": "User does not exist"}, status=status.HTTP_404_NOT_FOUND
            )
        
class TokenRefreshView(APIView):
    @extend_schema(
        summary="토큰 재발급",
        description="access 토큰을 재발급 받습니다.",
        request=TokenRefreshRequestSerializer,
        responses={200: "Token refresh 성공"},
    )
    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token") or request.data.get("refresh")
        
        #### 1
        if not refresh_token:
            return Response(
                {"detail": "no refresh token"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
        #### 2
            new_token = RefreshToken(refresh_token)
            new_token.verify()
        except:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )
            
        #### 3
        new_access_token = str(new_token.access_token)
        response = Response({"detail": "token refreshed"}, status=status.HTTP_200_OK)
        # response.set_cookie("access_token", value=str(new_access_token), httponly=True)
        response.set_cookie("access_token", value=str(new_access_token))
        return response
    
class LogoutView(APIView):
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

        except:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )
        
        res = Response(status=status.HTTP_204_NO_CONTENT)
        res.delete_cookie("access_token")
        res.delete_cookie("refresh_token")
        return res


class MeView(APIView):
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

        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InterestListView(APIView):
    @extend_schema(
        summary="관심사 목록 조회",
        description="로그인한 사용자의 관심사 목록을 조회합니다.",
        responses={200: InterestSerializer(many=True), 401: "Unauthorized"},
    )
    def get(self, request):
        ## 토큰을 통해 담긴 유저 정보 받아오기
        author = request.user
        ## 인증 여부 확인
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        interests = Interest.objects.filter(user_id=author).order_by("-priority", "-created_at")
        serializer = InterestSerializer(interests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="관심사 생성",
        description="로그인한 사용자의 관심사를 생성합니다.",
        request=InterestSerializer,
        responses={201: InterestSerializer, 400: "Bad Request", 401: "Unauthorized"},
    )
    def post(self, request):
        ## 토큰을 통해 담긴 유저 정보 받아오기
        author = request.user
        ## 인증 여부 확인
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = InterestSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            interest = serializer.save(user_id=author)
            return Response(InterestSerializer(interest).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        ## 토큰을 통해 담긴 유저 정보 받아오기
        author = request.user
        ## 인증 여부 확인
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        interest = self.get_interest(request, interest_id)
        serializer = InterestSerializer(interest, data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="관심사 삭제",
        description="로그인한 사용자의 관심사를 삭제합니다.",
        responses={204: "No Content", 401: "Unauthorized", 404: "Not Found"},
    )
    def delete(self, request, interest_id):
        ## 토큰을 통해 담긴 유저 정보 받아오기
        author = request.user
        ## 인증 여부 확인
        if not author.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        interest = self.get_interest(request, interest_id)
        interest.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
