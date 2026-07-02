"""쿠키 기반 JWT 인증.

프론트엔드는 로그인 시 백엔드가 내려주는 `access_token` 쿠키를 `credentials: "include"`
로 전송한다. 그런데 SimpleJWT 의 기본 `JWTAuthentication` 은 `Authorization: Bearer`
헤더만 읽으므로 쿠키만으로는 인증이 되지 않는다. 이 클래스는 헤더가 없을 때
`access_token` 쿠키로 폴백하여, 쿠키 기반 프론트 흐름이 그대로 인증되도록 한다.
헤더(Bearer)도 계속 지원하므로 외부 서비스/도구 연동에도 영향이 없다.
"""

from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            raw_token = request.COOKIES.get("access_token")
            if not raw_token:
                return None
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        return super().authenticate(request)
