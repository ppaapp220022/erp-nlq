import nlq


def test_public_api_is_only_generate_and_execute():
    # 화면과 API는 이 두 함수만 쓴다. 다른 DB 경로가 공개되면 신뢰 경계가 깨진다.
    functions = {name for name in nlq.__all__ if callable(getattr(nlq, name)) and name.islower()}
    assert functions == {"generate", "execute"}
