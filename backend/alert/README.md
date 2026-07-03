# alert — 멀티채널 알림 발송

## 개요

`alert` 는 AI 가 선별한 추천 공지를 사용자의 활성 채널로 내보낸다. 사용자는 채널(`AlertChannel`)을 등록하고, 디스패처가 **미발송(`notified_at IS NULL`) + 추천 여부(`is_recommended=true`)** 인 `InboxNotice` 를 사용자별로 묶어 이메일·슬랙으로 보낸 뒤, 결과를 `AlertLog` 로 남기고 `notified_at` 을 갱신해 중복 발송을 막는다. 발송은 (a) 채널 연동 시 확인 메시지, (b) 사이트 동기화 후 신규 추천분(비차단, best-effort), (c) 1시간 주기 스케줄러 등 세 시점에서 발생한다. `AlertLog` 는 추천 공지만 기록되므로, 자동으로 권장 공지 발송 이력을 나타낸다. 견고성(NFR-3)이 설계의 중심이다 — 한 채널의 실패가 다른 채널을, 한 사용자의 오류가 전체 루프를 멈추지 않는다. 발송기는 공통 인터페이스(`send`/`send_test`/`send_connected`)를 가지며, 새 채널은 발송기를 하나 추가하고 레지스트리에 등록하는 것만으로 확장된다(NFR-4).

## 구성

| 파일 | 역할 |
| --- | --- |
| `models.py` | `AlertChannel`(`type`·`config`(JSON)·`is_active`), `AlertLog`(`inbox_notice_id`·`channel_id`·`status`·`error`·`sent_at`) |
| `senders.py` | `BaseSender`와 `EmailSender`(HTML+텍스트)·`SlackSender`(Block Kit), `SENDER_REGISTRY`/`get_sender`, `alert_item_from_inbox`, 채널 생성 직후 연동 확인의 비블로킹 발송(`send_channel_connected_async`) |
| `service.py` | `dispatch_pending` 오케스트레이션(`_pending_queryset`·`_group_by_user`·사용자/채널 단위 격리) |
| `serializers.py` | `AlertChannelSerializer`(슬랙 webhook SSRF 검증·이메일 형식 검증), 생성/테스트 응답 시리얼라이저 |
| `throttling.py` | `TestSendRateThrottle`(테스트 발송 사용자당 6/min) |
| `views.py` | 채널 CRUD·테스트 발송·발송 로그 API |
| `urls.py` | `/api/alert-channels/...`, `/api/alert-logs/` |
| `management/commands/dispatch_alerts.py` | `manage.py dispatch_alerts` — 발송 진입점 |

## 흐름 · 사용법

사용자가 채널을 등록하면 생성 응답은 즉시 201 로 돌아오고, 연동 확인 메시지는 백그라운드 스레드에서 비블로킹으로 발송된다(SMTP 왕복을 기다리다 "추가" 버튼이 무한 로딩되는 것을 방지). 파이프라인 끝단에서 디스패처가 미발송 공지를 사용자별로 묶어 활성 채널마다 보낸다.

| 메서드 · 경로 | 설명 |
| --- | --- |
| `GET /api/alert-channels/` | 내 알림 채널 목록 |
| `POST /api/alert-channels/` | 채널 생성(응답에 `confirmation` = 연동 확인 발송의 best-effort 상태) |
| `PATCH /api/alert-channels/<id>/` | 채널 부분 수정 |
| `DELETE /api/alert-channels/<id>/` | 채널 삭제 |
| `POST /api/alert-channels/<id>/test/` | 등록 주소/웹훅으로 테스트 발송(사용자당 rate-limit) |
| `GET /api/alert-logs/` | 내 발송 로그(`?status=`·`?inbox_notice_id=` 필터) |

발송 명령:

```bash
python manage.py dispatch_alerts                    # 전체 미발송분
python manage.py dispatch_alerts --user alice --limit 50
python manage.py dispatch_alerts --dry-run          # 발송 대상만 미리보기
```

채널 `config` 계약: 이메일 `{"address": "..."}`(없으면 회원 `user.email` 로 폴백), 슬랙 `{"webhook_url": "https://hooks.slack.com/services/..."}`.

## 유의사항

- **발송 대상 선택**: 디스패처는 `notified_at IS NULL AND is_recommended=true` 인 행만 선택해 발송한다. 임계값 미만(`is_recommended=false`)으로 판정된 공지는 저장되지만 알림 대상이 아니다.
- **중복 방지**는 `InboxNotice.notified_at` 으로 한다. 부분 실패(일부 채널만 실패)여도 `notified_at` 은 갱신한다 — 성공한 채널로의 중복 발송을 피하기 위한 의도된 at-most-once 선택이며, 실패 채널은 재시도하지 않고 `AlertLog` 에 사유를 남긴다.
- **채널 타입은 email·slack 이 실제 발송된다.** 모델의 `ChannelType` 에는 `kakao` 값이 있으나 대응 발송기가 없어(`get_sender`→None) 디스패처가 조용히 건너뛴다(향후 확장용 예약값). 카카오 알림톡은 템플릿 사전 승인 리드타임 때문에 현재 범위에서 제외돼 있다.
- **보안**: 슬랙 webhook 은 SSRF 방지를 위해 `https://hooks.slack.com` 호스트로만 제한한다. 테스트 발송은 실제 메일/슬랙을 쏘므로 사용자당 빈도 제한(6/min)을 둔다.
- **이메일 백엔드 기본값은 콘솔 출력**이라 SMTP 자격 증명 없이도 데모/테스트가 된다. 실제 발송은 `.env` 에서 `EMAIL_BACKEND=...smtp.EmailBackend` 로 바꾼다. 587(STARTTLS)이 막히는 망에서는 465(SSL, `EMAIL_USE_SSL=True`)로 전환한다.
- 발송기는 절대 예외를 호출자에게 던지지 않고 `(ok, error)` 로 반환한다. 새 채널 추가는 `BaseSender` 상속 + `SENDER_REGISTRY` 등록으로 끝난다.
