"""gunicorn 설정 — 프로덕션 WSGI 서버.

실행:  .venv/bin/gunicorn -c gunicorn.conf.py kkongal.wsgi:application
(systemd 유닛 deploy/kkongal.service 이 이 설정으로 gunicorn 을 띄운다.)
"""

# nginx 가 앞단에서 TLS 종료·정적 파일을 처리하고, 이 소켓으로 리버스 프록시한다.
bind = "127.0.0.1:8000"

# ── worker 수는 1로 고정한다(임의로 늘리지 말 것) ─────────────────────────────
# sources/sync_jobs.py 의 인메모리 동기화 워커(스레드)와 Django LocMem 캐시가
# 프로세스 로컬이라, worker 를 늘리면 동기화 작업이 중복되고 캐시가 조각난다.
# 동시성은 스레드로 확보한다. worker 를 2 이상으로 올리려면 먼저 공유 캐시(Redis)와
# 외부 작업 러너를 도입해야 한다.
workers = 1
threads = 4
timeout = 120

# 로그를 stdout/stderr 로 보낸다(systemd/journald 가 수집).
accesslog = "-"
errorlog = "-"
