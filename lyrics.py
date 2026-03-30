import re
import unicodedata


def is_lrc(text: str) -> bool:
    return bool(re.search(r"\[\d+:\d+[.:]\d+\]", text))


def normalize_lyric_text(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def parse_lrc(text: str) -> list[dict]:
    lines = []
    pat = re.compile(r"\[(\d+):(\d+)[.:](\d+)\](.*)")
    bracket_tag = re.compile(r"\[[^\[\]]*\]")
    for raw in text.splitlines():
        m = pat.match(raw.strip())
        if not m:
            continue
        mm, ss, frac, content = m.groups()
        t = int(mm) * 60 + int(ss) + int(frac) / (100 if len(frac) <= 2 else 1000)
        content = re.sub(r"\[\d+:\d+[.:]\d+\]", "", content).strip()
        content = normalize_lyric_text(bracket_tag.sub("", content))
        if content:
            lines.append({"time": t, "text": content})
    return sorted(lines, key=lambda x: x["time"])


def parse_plain(text: str, duration: float) -> list[dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    interval = duration / (len(lines) + 1)
    return [{"time": (i + 1) * interval, "text": line} for i, line in enumerate(lines)]


def clean_lyric_lines(raw_text: str) -> list[str]:
    lines = []
    time_tag = re.compile(r"\[\d{1,2}:\d{1,2}(?:[.:]\d{1,3})?\]")
    meta_tag = re.compile(r"^\[[a-zA-Z]+:.*\]$")
    bracket_tag = re.compile(r"\[[^\[\]]*\]")
    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or meta_tag.match(line):
            continue
        line = time_tag.sub("", line).strip()
        line = normalize_lyric_text(bracket_tag.sub("", line))
        if line:
            lines.append(line)
    return lines


def normalize_for_align(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    return t.replace("’", "'").replace("‘", "'").replace("`", "'")


def tokenize_for_align(text: str) -> list[tuple[str, int]]:
    t = normalize_for_align(text)
    tokens: list[tuple[str, int]] = []
    word = []
    word_start = -1
    for idx, ch in enumerate(t):
        if ch.isascii() and (ch.isalnum() or ch == "'"):
            if not word:
                word_start = idx
            word.append(ch)
            continue
        if word:
            token = "".join(word).strip("'")
            if token:
                tokens.append((token, word_start))
            word = []
            word_start = -1
        cat = unicodedata.category(ch)
        if ch.isspace() or cat.startswith("P") or cat.startswith("S"):
            continue
        tokens.append((ch, idx))
    if word:
        token = "".join(word).strip("'")
        if token:
            tokens.append((token, word_start))
    return tokens


def dominant_language_hint(lines: list[str], locale: str) -> str | None:
    zh_count = 0
    ja_kana_count = 0
    en_count = 0
    for line in lines:
        for ch in line:
            if "\u4e00" <= ch <= "\u9fff":
                zh_count += 1
            elif "\u3040" <= ch <= "\u30ff" or "\uff66" <= ch <= "\uff9f":
                ja_kana_count += 1
            elif ("a" <= ch.lower() <= "z"):
                en_count += 1
    if zh_count == 0 and ja_kana_count == 0 and en_count == 0:
        if locale == "zh":
            return "zh"
        if locale == "ja":
            return "ja"
        return "en"
    if ja_kana_count > 0:
        return "ja"
    if zh_count > 0 and en_count > 0:
        ratio = max(zh_count, en_count) / max(1, min(zh_count, en_count))
        if ratio < 2.2:
            return None
    return "zh" if zh_count >= en_count else "en"


def token_time(start: float, end: float, pos: int, total_len: int) -> float:
    if end <= start or total_len <= 1:
        return start
    frac = min(1.0, max(0.0, pos / (total_len - 1)))
    return start + (end - start) * frac


def get_layout(w: int, h: int) -> dict:
    is_portrait = h > w
    if is_portrait:
        cover_box = int(w * 0.7)
        cover_x = (w - cover_box) // 2
        cover_y = int(h * 0.15)
        title_y = cover_y + cover_box + int(h * 0.05)
        artist_y = title_y + int(h * 0.045)
        lyric_top = artist_y + int(h * 0.06)
        lyric_x = w // 2
        title_x_expr = "(w-tw)/2"
        artist_x_expr = "(w-tw)/2"
        font_size = 64
    else:
        cover_box = int(h * 0.6)
        cover_x = int(w * 0.15)
        cover_y = (h - cover_box) // 2
        text_center_x = int(cover_x + cover_box + (w - (cover_x + cover_box)) / 2)
        title_y = int(h * 0.25)
        artist_y = title_y + int(h * 0.06)
        lyric_top = artist_y + int(h * 0.10)
        lyric_x = text_center_x
        title_x_expr = f"{text_center_x}-(tw/2)"
        artist_x_expr = f"{text_center_x}-(tw/2)"
        font_size = 60

    return {
        "cover_box": cover_box,
        "cover_x": cover_x,
        "cover_y": cover_y,
        "title_y": title_y,
        "artist_y": artist_y,
        "lyric_top": lyric_top,
        "lyric_x": lyric_x,
        "title_x_expr": title_x_expr,
        "artist_x_expr": artist_x_expr,
        "font_size": font_size
    }


def build_ass(
    lyrics: list[dict],
    duration: float,
    w: int,
    h: int,
    layout: dict,
    song_title: str = "",
    artist: str = "",
) -> str:
    font_size = layout["font_size"]
    margin_v = int(h * 0.05)
    font = "Microsoft YaHei"
    lyric_top = layout["lyric_top"]
    lyric_x = layout["lyric_x"]
    side_margin = int(w * 0.03)
    max_row_width = max(
        int(w * 0.3),
        int(2 * min(max(0, lyric_x - side_margin), max(0, w - lyric_x - side_margin)))
    )

    def fmt(s: float) -> str:
        hh = int(s // 3600)
        mm = int((s % 3600) // 60)
        ss = s % 60
        return f"{hh}:{mm:02d}:{ss:05.2f}"

    def esc_ass(t: str) -> str:
        return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    def char_units(ch: str) -> int:
        return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1

    def wrap_ass_text(text: str, row_font_size: int) -> str:
        max_units = max(10, int(max_row_width / max(1.0, row_font_size * 0.52)))
        chunks = []
        token_pat = re.compile(r"[A-Za-z0-9']+|\s+|.", re.UNICODE)

        def push_token(current: list[str], used: int, token: str) -> tuple[list[str], int]:
            token_units = sum(char_units(c) for c in token)
            if token.isspace():
                if current and used + token_units <= max_units:
                    current.append(token)
                    used += token_units
                return current, used
            if token_units <= max_units:
                current.append(token)
                used += token_units
                return current, used
            for ch in token:
                ch_units = char_units(ch)
                if current and used + ch_units > max_units:
                    chunks.append("".join(current).rstrip())
                    current = []
                    used = 0
                current.append(ch)
                used += ch_units
            return current, used

        for part in text.splitlines() or [""]:
            if not part:
                chunks.append("")
                continue
            current = []
            used = 0
            for token in token_pat.findall(part):
                token_units = sum(char_units(c) for c in token)
                if current and not token.isspace() and used + token_units > max_units:
                    chunks.append("".join(current).rstrip())
                    current = []
                    used = 0
                    token = token.lstrip()
                current, used = push_token(current, used, token)
            if current:
                chunks.append("".join(current).rstrip())
        return "\\N".join(esc_ass(x) for x in chunks)

    header_rows = []
    if song_title.strip():
        header_rows.append({"kind": "title", "text": song_title.strip()})
    if artist.strip():
        header_rows.append({"kind": "artist", "text": artist.strip()})
    full_rows = header_rows + [{"kind": "lyric", "text": lyr["text"]} for lyr in lyrics]

    events = []
    is_portrait = h > w
    context_lines = 6 if is_portrait else 5

    for i, lyr in enumerate(lyrics):
        start = lyr["time"]
        end = lyrics[i + 1]["time"] if i + 1 < len(lyrics) else duration
        if end <= start:
            continue
        current_idx = len(header_rows) + i
        start_i = max(0, current_idx - context_lines)
        end_i = min(len(full_rows), current_idx + context_lines + 1)
        rows = []
        for j in range(start_i, end_i):
            item = full_rows[j]
            dist = abs(j - current_idx)
            if dist == 0:
                scale, alpha = 1.0, "00"
            elif dist == 1:
                scale, alpha = 0.9, "45"
            elif dist == 2:
                scale, alpha = 0.8, "78"
            elif dist == 3:
                scale, alpha = 0.7, "9A"
            elif dist == 4:
                scale, alpha = 0.6, "B4"
            elif dist == 5:
                scale, alpha = 0.5, "CC"
            elif dist == 6:
                scale, alpha = 0.4, "E0"
            else:
                scale, alpha = 0.4, "F0"

            if item["kind"] == "title":
                base_size = int(font_size * 1.05)
                bold = 1
            elif item["kind"] == "artist":
                base_size = int(font_size * 0.82)
                bold = 0
            else:
                base_size = font_size
                bold = 1 if dist == 0 else 0

            txt = wrap_ass_text(item["text"], int(base_size * scale))
            style = f"{{\\b{bold}\\fs{int(base_size * scale)}\\c&HFFFFFF&\\alpha&H{alpha}&}}"
            rows.append(style + txt)
        block = f"{{\\an8\\pos({lyric_x},{lyric_top})}}" + "\\N".join(rows)
        events.append(f"Dialogue: 0,{fmt(start)},{fmt(end)},Default,,0,0,0,,{block}")

    return (
        f"[Script Info]\n"
        f"ScriptType: v4.00+\n"
        f"PlayResX: {w}\n"
        f"PlayResY: {h}\n"
        f"ScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        f"BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        f"BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,&H00000000,"
        f"&HA0000000,0,0,0,0,100,100,2,0,1,2,0,8,20,20,{margin_v},1\n\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(events)
    )
