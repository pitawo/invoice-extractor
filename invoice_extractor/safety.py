"""API キーの取り扱い。キーは環境変数からだけ読み、文字列化しても伏せ字になる箱に入れる。"""
import os
import re

ENV_KEY = "ANTHROPIC_API_KEY"
_KEY_LIKE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|dummy-key-[A-Za-z0-9_\-]+")


class ConfigError(Exception):
    pass


class Secret:
    """print / f-string / repr / 例外メッセージに混ざっても値が出ない。値を取り出す場所は reveal() の1箇所だけ。"""

    __slots__ = ("_v",)

    def __init__(self, value):
        object.__setattr__(self, "_v", value)

    def reveal(self):
        return self._v

    def __repr__(self):
        return "Secret(***)"

    __str__ = __repr__

    def __format__(self, spec):
        return "***"

    def __setattr__(self, k, v):
        raise AttributeError("immutable")


def load_key(env=None):
    env = os.environ if env is None else env
    v = env.get(ENV_KEY, "").strip()
    if not v:
        raise ConfigError(f"環境変数 {ENV_KEY} が設定されていません（値はここに表示しません）")
    return Secret(v)


def redact(text, key=None):
    """文字列から、キーそのものとキーらしい文字列を取り除く。外に出す文字列は必ずこれを通す。"""
    text = str(text)
    if key is not None:
        v = key.reveal() if isinstance(key, Secret) else str(key)
        if v:
            text = text.replace(v, "***")
    return _KEY_LIKE.sub("***", text)
