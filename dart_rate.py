# -*- coding: utf-8 -*-
"""
dart_rate.py — DART 호출 속도 상한 (한 프로세스 안 모든 스레드 합산)
====================================================================
왜: 2단계(공시 조회)가 2스레드로 쉬지 않고 호출해, DART 응답이 빠른 날엔 분당 1,000건을
넘는다. 그런 날마다 직후 3단계에서 약 60분 접속이 끊겼다.
  실측(logs/auto_run_*, 2026-08-24~10-02 자동 배치 26회):
    끊긴 11일  = KOSDAQ 2단계 분당 985~1,078건
    안 끊긴 15일 = 분당 890건 이하 14일 + 1,013건(총 929건이라 1분 창 안 1,000건 미만) 1일
  → '1분에 약 1,000건' 문턱으로 추정(DART 공식 문구는 직접 확인 못 함).

무엇: 실제 네트워크 호출 직전에 wait() 를 부르면, 호출 사이 최소 간격(60/상한 초)을
전 스레드 합산으로 지킨다. 호출 내용·순서·응답 처리에는 관여하지 않는다 → 결과 불변, 시간만 조금 는다.

상한: DART_MAX_PER_MIN (기본 600 = 끊긴 날 최저 985의 약 60%. 2단계→3단계처럼 프로세스가
바뀌는 경계의 1분 창도 600 안쪽으로 유지). 0 이하면 끔(기존 동작).
"""
import os
import time
import threading

MAX_PER_MIN = float(os.environ.get("DART_MAX_PER_MIN", "600"))

_LOCK = threading.Lock()
_next_ok = 0.0


def wait():
    """다음 DART 호출 전에 부른다. 기다린 초를 돌려준다(진단용)."""
    global _next_ok
    if MAX_PER_MIN <= 0:
        return 0.0
    gap = 60.0 / MAX_PER_MIN
    with _LOCK:
        now = time.monotonic()
        start = max(now, _next_ok)
        _next_ok = start + gap
    delay = start - now
    if delay > 0:
        time.sleep(delay)
    return delay
