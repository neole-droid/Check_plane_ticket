# Check_plane_ticket

대한항공(KE)·아시아나(OZ) 마일리지 항공권 잔여석을 달력으로 보는 대시보드 (초안 v0.1)

## 설치
```bash
pip install -r requirements.txt
playwright install chromium
```

## 사용
```bash
python award_dashboard.py demo        # 샘플 데이터로 index.html 생성
python award_dashboard.py collect KE  # 대한항공: 브라우저에서 로그인·검색 → 응답 자동 저장
python award_dashboard.py collect OZ  # 아시아나
python award_dashboard.py build       # data/awards.json → index.html
```

## 남은 작업 (TODO)
- [ ] DevTools로 마일리지 검색 API URL 확인 → `response_pattern` 수정
- [ ] `data/raw/*.json` 구조 확인 → `parse_response()` 매핑 작성
- [ ] 검색 폼 자동 입력(구간·날짜 순회)
- [ ] 원하는 좌석 발견 시 알림

## 주의
- 아시아나는 2026년 12월 법인 통합 이후 사이트 구조가 바뀔 수 있음
- 잔여석은 수집 시점 기준. 예약 전 사이트에서 재확인
- `browser_profile/`에는 로그인 세션이 저장되므로 절대 커밋하지 말 것
