# -*- coding: utf-8 -*-
"""
dart_cache_util.py — DART 응답용 경량 파일 캐시 (D2-②)
=====================================================
고정된 (corp_code·연도·보고서코드·fs_div) 재무 응답은 정정공시 전엔 안 변하므로
안전하게 캐시할 수 있다. 같은 날 재실행/다음 날 실행 시 DART 호출을 크게 줄인다.

설계 원칙(이상 없이):
  * '미스'일 때 동작은 기존 네트워크 경로와 100% 동일 → 캐시는 가속일 뿐 결과 불변.
  * 적중 시에는 *예전에 API가 준 바로 그 응답*을 그대로 돌려줌(결과 동일성 보장).
  * 끄기: 환경변수 DART_NO_CACHE=1  (그러면 항상 네트워크).
  * 보관 위치: DART_CACHE_DIR (기본 dart_cache).  하위 폴더로 종류 구분.
  * 원자적 쓰기(tmp→os.replace) + 스레드 안전.  값은 JSON 직렬화 가능해야 함.

이 모듈은 '얼마나 오래 캐시할지(TTL)'를 강요하지 않는다 — 호출 측이 상태에 따라
TTL 을 직접 판단한다(예: 정상 응답은 길게, '데이터 없음'은 짧게).
"""
import os
import json
import time
import hashlib
import threading
from pathlib import Path

_WRITE_LOCK = threading.Lock()


def enabled() -> bool:
    """DART_NO_CACHE=1 이면 비활성(항상 네트워크)."""
    return os.environ.get("DART_NO_CACHE", "0") not in ("1", "true", "True", "yes")


def _root() -> Path:
    return Path(os.environ.get("DART_CACHE_DIR", "dart_cache"))


def _paths(subdir: str, key_parts):
    raw = "||".join(str(p) for p in key_parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    d = _root() / subdir
    return d, d / f"{h}.json", raw


def get_with_age(subdir: str, key_parts):
    """(value, age_seconds) 반환. 없으면/오류면 None. TTL 판단은 호출 측이 한다."""
    if not enabled():
        return None
    _, fp, _ = _paths(subdir, key_parts)
    try:
        if not fp.exists():
            return None
        age = time.time() - fp.stat().st_mtime
        with open(fp, "r", encoding="utf-8") as f:
            rec = json.load(f)
        return rec["v"], age
    except Exception:
        return None


def put(subdir: str, key_parts, value) -> None:
    """value(JSON 직렬화 가능)를 원자적으로 저장. 실패해도 조용히 무시(가속일 뿐)."""
    if not enabled():
        return
    d, fp, raw = _paths(subdir, key_parts)
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"k": raw, "ts": time.time(), "v": value}, f, ensure_ascii=False)
        with _WRITE_LOCK:
            os.replace(tmp, fp)   # 원자적 교체
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def clear(subdir: str = None) -> int:
    """캐시 비우기. subdir 지정 시 해당 종류만. 삭제 개수 반환."""
    base = _root() / subdir if subdir else _root()
    n = 0
    if base.exists():
        for p in base.rglob("*.json"):
            try:
                p.unlink(); n += 1
            except Exception:
                pass
    return n
