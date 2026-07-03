"""alert 앱 전용 throttle.

테스트 발송 엔드포인트는 사용자가 등록한 주소(config.address / webhook)로 실제
메일/슬랙을 보낸다. 인증된 본인 채널만 대상이라 위험은 낮지만, 임의 수신자에게
반복 발송하는 증폭 악용을 막기 위해 사용자당 가벼운 빈도 제한을 둔다.

rate/scope 를 클래스에 직접 지정하므로 settings 의 DEFAULT_THROTTLE_RATES 에
의존하지 않는다(다른 앱/설정을 건드리지 않기 위함). 캐시는 Django 기본
LocMemCache 로 충분하다(프로세스 단위 가벼운 제한).
"""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class TestSendRateThrottle(UserRateThrottle):
    """테스트 발송: 사용자당 분당 소수 회로 제한한다(429 초과 시)."""

    # 다른 throttle 과 캐시 버킷이 섞이지 않도록 전용 scope 를 쓴다.
    scope = "alert_test_send"
    rate = "6/min"
