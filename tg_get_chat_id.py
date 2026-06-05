#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg_get_chat_id.py — 텔레그램 그룹/채널의 chat_id 찾기
=====================================================
봇을 그룹(또는 채널)에 넣은 뒤 이 스크립트를 돌리면, 봇이 최근에 본
모든 대화방의 chat_id를 출력한다. 그 음수 숫자를 .env 의
TELEGRAM_CHAT_ID 에 넣으면 notify_telegram.py 가 그 방으로 보낸다.
(notify_telegram.py 는 코드 수정 없이 chat_id만 바꾸면 됨.)

사용 순서:
  1) 봇을 단톡방에 초대한다. (채널이면 봇을 '관리자'로 추가)
  2) 그 방에서 봇에게 명령을 한 번 보낸다:  /start@<봇유저네임>
     (봇 privacy mode가 켜져 있어도 '명령'은 전달돼서 chat_id를 잡을 수 있다.
      채널이면 채널에 글을 하나 올리면 된다.)
  3) python tg_get_chat_id.py
  4) 출력된 chat_id(그룹/채널은 보통 -100... 으로 시작하는 음수)를 .env 에 복사.

환경변수: TELEGRAM_BOT_TOKEN (.env 또는 셸에 설정)
"""
import os
import sys


def _load_dotenv():
    """가벼운 .env 로더 (python-dotenv 없어도 동작). 이미 있는 환경변수는 안 덮음."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    _load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN 이 없어. .env 나 환경변수에 먼저 넣어줘.")
        sys.exit(1)
    try:
        import requests
    except ImportError:
        print("requests 가 필요해:  pip install requests")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        data = requests.get(url, timeout=15).json()
    except Exception as e:
        print(f"호출 실패: {e}")
        sys.exit(1)

    if not data.get("ok"):
        print(f"텔레그램 오류: {data}")
        sys.exit(1)

    seen = {}   # chat_id -> (type, name)
    for upd in data.get("result", []):
        for key in ("message", "channel_post", "edited_message",
                    "my_chat_member", "chat_member"):
            obj = upd.get(key)
            if not obj:
                continue
            chat = obj.get("chat") or {}
            cid = chat.get("id")
            if cid is None:
                continue
            name = (chat.get("title")
                    or " ".join(filter(None, [chat.get("first_name"),
                                              chat.get("last_name")]))
                    or chat.get("username") or "")
            seen[cid] = (chat.get("type", "?"), name)

    if not seen:
        print("아직 보이는 대화방이 없어. 다음을 확인하고 다시 실행해줘:\n"
              "  - 봇을 그룹에 초대했는지\n"
              "  - 그룹에서 /start@<봇유저네임> 을 한 번 보냈는지\n"
              "  - (채널이면) 봇을 관리자로 넣고 글을 하나 올렸는지\n"
              "※ getUpdates 는 최근 항목만 보여주니, 방금 메시지를 보낸 직후에 "
              "바로 돌리는 게 좋아.")
        return

    print("봇이 본 대화방들:\n")
    for cid, (ctype, name) in seen.items():
        tag = "   ← 이 음수를 TELEGRAM_CHAT_ID 로" if str(cid).startswith("-") else ""
        print(f"  chat_id = {str(cid):<16}  type={ctype:<10}{name}{tag}")
    print("\n그룹/채널의 chat_id(보통 -100... 음수)를 .env 의 "
          "TELEGRAM_CHAT_ID 에 넣으면 끝.")


if __name__ == "__main__":
    main()
