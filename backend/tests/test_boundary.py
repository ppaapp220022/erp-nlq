from pathlib import Path

import nlq


def test_public_api_is_only_generate_and_execute():
    # 화면과 API는 이 두 함수만 쓴다. 다른 DB 경로가 공개되면 신뢰 경계가 깨진다.
    functions = {name for name in nlq.__all__ if callable(getattr(nlq, name)) and name.islower()}
    assert functions == {"generate", "execute"}


def test_ask_only_composes_generate_and_execute():
    # 자기 수정(nlq/ask.py)은 generate()와 execute()만 부른다. DB 드라이버나 guard를 직접 쓰지 않는다.
    from nlq import ask

    source = Path(ask.__file__).read_text()
    assert "psycopg" not in source and "nlq.guard" not in source
    assert "from nlq.execute import execute" in source
