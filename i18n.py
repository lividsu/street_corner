from settings import MESSAGES


def normalize_locale(locale: str | None) -> str:
    if locale and locale.lower().startswith("zh"):
        return "zh"
    if locale and locale.lower().startswith("ja"):
        return "ja"
    return "en"


def tr(locale: str, key: str, **kwargs) -> str:
    value = MESSAGES.get(locale, MESSAGES["en"]).get(key, key)
    if kwargs:
        return value.format(**kwargs)
    return value
