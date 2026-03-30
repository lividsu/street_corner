import difflib

from faster_whisper import WhisperModel

from lyrics import (
    clean_lyric_lines,
    dominant_language_hint,
    normalize_for_align,
    token_time,
    tokenize_for_align,
)
from settings import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_NAME

whisper_model = None


def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )
    return whisper_model


def align_lyrics_text(audio_path: str, raw_lyrics: str, locale: str) -> str:
    text_lines = clean_lyric_lines(raw_lyrics)
    model = get_whisper_model()
    language_hint = dominant_language_hint(text_lines, locale)
    transcribe_kwargs = {"beam_size": 5, "word_timestamps": True}
    if language_hint:
        transcribe_kwargs["language"] = language_hint
    segments, _ = model.transcribe(audio_path, **transcribe_kwargs)
    whisper_segs = list(segments)

    if not text_lines:
        lrc = ""
        for seg in whisper_segs:
            mm = int(seg.start // 60)
            ss = seg.start % 60
            lrc += f"[{mm:02d}:{ss:05.2f}]{seg.text.strip()}\n"
        return lrc

    whisper_tokens = []
    for seg in whisper_segs:
        words = getattr(seg, "words", None) or []
        if words:
            for wd in words:
                w_text = getattr(wd, "word", "") or ""
                if not w_text.strip():
                    continue
                w_start = float(getattr(wd, "start", seg.start) or seg.start)
                w_end = float(getattr(wd, "end", seg.end) or seg.end or w_start)
                pairs = tokenize_for_align(w_text)
                total_len = max(1, len(normalize_for_align(w_text)))
                for tk, pos in pairs:
                    whisper_tokens.append(
                        {"token": tk, "time": token_time(w_start, w_end, pos, total_len)}
                    )
        else:
            s_text = seg.text or ""
            pairs = tokenize_for_align(s_text)
            total_len = max(1, len(normalize_for_align(s_text)))
            for tk, pos in pairs:
                whisper_tokens.append(
                    {"token": tk, "time": token_time(float(seg.start), float(seg.end), pos, total_len)}
                )

    user_tokens = []
    for i, line in enumerate(text_lines):
        for tk, _ in tokenize_for_align(line):
            user_tokens.append({"token": tk, "line_idx": i})

    if not whisper_tokens or not user_tokens:
        duration = max([float(getattr(s, "end", 0.0) or 0.0) for s in whisper_segs] + [0.0])
        duration = duration if duration > 1.0 else 180.0
        interval = duration / (len(text_lines) + 1)
        lrc = ""
        for i, line in enumerate(text_lines):
            t = (i + 1) * interval
            mm = int(t // 60)
            ss = t % 60
            lrc += f"[{mm:02d}:{ss:05.2f}]{line}\n"
        return lrc

    sm = difflib.SequenceMatcher(None, [x["token"] for x in whisper_tokens], [x["token"] for x in user_tokens], autojunk=False)

    line_matches: dict[int, list[float]] = {}
    for block in sm.get_matching_blocks():
        for i in range(block.size):
            w_idx = block.a + i
            u_idx = block.b + i
            line_idx = user_tokens[u_idx]["line_idx"]
            time = whisper_tokens[w_idx]["time"]
            line_matches.setdefault(line_idx, []).append(time)

    line_times: dict[int, float] = {}
    for line_idx, matches in line_matches.items():
        if not matches:
            continue
        ms = sorted(matches)
        pick = ms[min(len(ms) - 1, max(0, len(ms) // 4))]
        line_times[line_idx] = pick

    lrc = ""
    n = len(text_lines)
    duration = max([float(getattr(s, "end", 0.0) or 0.0) for s in whisper_segs] + [0.0])
    duration = duration if duration > 1.0 else 180.0
    default_gap = max(0.01, duration / (n + 1))
    resolved = [None] * n
    for idx, t in line_times.items():
        if 0 <= idx < n:
            resolved[idx] = max(0.0, min(duration, float(t)))

    anchors = [(i, t) for i, t in enumerate(resolved) if t is not None]
    if not anchors:
        for i in range(n):
            resolved[i] = (i + 1) * default_gap
    else:
        for i in range(n):
            if resolved[i] is not None:
                continue
            prev_anchor = None
            next_anchor = None
            for a_idx, a_t in anchors:
                if a_idx < i:
                    prev_anchor = (a_idx, a_t)
                if a_idx > i:
                    next_anchor = (a_idx, a_t)
                    break
            if prev_anchor and next_anchor:
                left_i, left_t = prev_anchor
                right_i, right_t = next_anchor
                step = (right_t - left_t) / max(1, right_i - left_i)
                resolved[i] = left_t + step * (i - left_i)
            elif prev_anchor:
                left_i, left_t = prev_anchor
                resolved[i] = left_t + default_gap * (i - left_i)
            elif next_anchor:
                right_i, right_t = next_anchor
                resolved[i] = max(0.0, right_t - default_gap * (right_i - i))
            else:
                resolved[i] = (i + 1) * default_gap

    for i in range(1, n):
        if resolved[i] <= resolved[i - 1]:
            resolved[i] = min(duration, resolved[i - 1] + 0.01)

    for i, line in enumerate(text_lines):
        t = max(0.0, min(duration, float(resolved[i] if resolved[i] is not None else (i + 1) * default_gap)))
        mm = int(t // 60)
        ss = t % 60
        lrc += f"[{mm:02d}:{ss:05.2f}]{line}\n"
    return lrc
