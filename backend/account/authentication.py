"""쿠키/헤더 기반 JWT 인증.

프론트엔드는 로그인 시 백엔드가 내려주는 `access_token` 쿠키를 `credentials: "include"`
로 전송한다. SimpleJWT 기본 `JWTAuthentication` 은 `Authorization: Bearer` 헤더만 읽으므로
쿠키 폴백을 추가한다.

중요: **만료/무효 토큰은 예외를 던지지 않고 '비인증(None)'으로 처리한다.**
그렇지 않으면 브라우저에 남은 stale 토큰(쿠키 또는 헤더) 하나 때문에 인증 단계에서
401 이 발생해 로그인/회원가입 같은 공개 엔드포인트까지 막혀버린다(로그인 자체가 불가능).
비인증으로 흘려보내면 공개 뷰는 정상 동작하고, 보호 뷰는 권한 단계에서 적절히 401 을 낸다.
"""

from __future__ import annotations

import logging

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger("account")


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 1) Authorization 헤더 우선, 없으면 access_token 쿠키.
        raw_token = None
        header = self.get_header(request)
        if header is not None:
            try:
                raw_token = self.get_raw_token(header)
            except Exception:
                raw_token = None
        if raw_token is None:
            raw_token = request.COOKIES.get("access_token") or None
        if not raw_token:
            return None

        # 2) 토큰 검증 실패(만료/무효)는 절대 예외로 전파하지 않는다 → 비인증 처리.
        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
        except (InvalidToken, TokenError):
            return None
        except Exception as exc:  # 방어: 어떤 인증 오류도 401 을 강제하지 않는다.
            logger.debug("cookie jwt auth skipped: %r", exc)
            return None

        return (user, validated_token)
