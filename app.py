import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import re
import json
import uuid
import threading
import subprocess
from collections import Counter
import difflib
import unicodedata

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

jobs: dict = {}  # job_id -> status dict
whisper_model = None

MESSAGES = {
    "en": {
        "getting_audio_duration": "Reading audio duration...",
        "processing_lyrics": "Processing lyrics...",
        "rendering_video": "Rendering video (this may take a few minutes)...",
        "ffmpeg_error": "FFmpeg error",
        "done": "Done!",
        "upload_audio": "Please upload an audio file",
        "recognize_failed": "Recognition failed: {error}",
        "upload_audio_image": "Please upload audio and cover image",
        "queued": "Waiting in queue...",
        "file_not_found": "File not found",
        "started": "Music Video Tool started -> http://localhost:5004",
    },
    "zh": {
        "getting_audio_duration": "获取音频时长…",
        "processing_lyrics": "处理歌词…",
        "rendering_video": "渲染视频（可能需要几分钟）…",
        "ffmpeg_error": "FFmpeg 出错",
        "done": "完成！",
        "upload_audio": "请上传音频文件",
        "recognize_failed": "识别失败: {error}",
        "upload_audio_image": "请上传音频和封面图片",
        "queued": "等待处理…",
        "file_not_found": "文件不存在",
        "started": "音乐视频工具已启动 -> http://localhost:5004",
    },
}


def normalize_locale(locale: str | None) -> str:
    if locale and locale.lower().startswith("zh"):
        return "zh"
    return "en"


def tr(locale: str, key: str, **kwargs) -> str:
    value = MESSAGES.get(locale, MESSAGES["en"]).get(key, key)
    if kwargs:
        return value.format(**kwargs)
    return value

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        # Use small or base model. base is usually a good balance of speed/accuracy
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return whisper_model


# ─── Lyrics helpers ──────────────────────────────────────────────────────────

def is_lrc(text: str) -> bool:
    return bool(re.search(r"\[\d+:\d+[.:]\d+\]", text))


def parse_lrc(text: str) -> list[dict]:
    lines = []
    pat = re.compile(r"\[(\d+):(\d+)[.:](\d+)\](.*)")
    for raw in text.splitlines():
        m = pat.match(raw.strip())
        if not m:
            continue
        mm, ss, frac, content = m.groups()
        t = int(mm) * 60 + int(ss) + int(frac) / (100 if len(frac) <= 2 else 1000)
        content = re.sub(r"\[\d+:\d+[.:]\d+\]", "", content).strip()
        if content:
            lines.append({"time": t, "text": content})
    return sorted(lines, key=lambda x: x["time"])


def parse_plain(text: str, duration: float) -> list[dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    interval = duration / (len(lines) + 1)
    return [{"time": (i + 1) * interval, "text": line} for i, line in enumerate(lines)]


# ─── FFmpeg helpers ───────────────────────────────────────────────────────────

def get_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 180.0


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
        for part in text.splitlines() or [""]:
            if not part:
                chunks.append("")
                continue
            current = []
            used = 0
            for ch in part:
                u = char_units(ch)
                if current and used + u > max_units:
                    chunks.append("".join(current))
                    current = [ch]
                    used = u
                else:
                    current.append(ch)
                    used += u
            if current:
                chunks.append("".join(current))
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


def build_vf(w: int, h: int, has_lyrics: bool, bg_mode: str, layout: dict, ass_name: str = "subtitles.ass") -> tuple[str, str, bool]:
    if bg_mode == "blur":
        scale_bg = f"scale={w}:{h}:force_original_aspect_ratio=increase"
        crop_bg = f"crop={w}:{h}"
        blur = "gblur=sigma=60"
        cover_box = layout["cover_box"]
        cover_x = layout["cover_x"]
        cover_y = layout["cover_y"]
        vf = (
            f"[0:v]split=2[bg_in][cover_in];"
            f"[bg_in]{scale_bg},{crop_bg},{blur},"
            f"scale=w='iw*(1.05+0.03*sin(2*PI*t*0.02))':h='ih*(1.05+0.03*sin(2*PI*t*0.02))':eval=frame,"
            f"crop={w}:{h},eq=saturation=1.12:brightness=-0.1[bg];"
            f"[cover_in]scale={cover_box}:{cover_box}:force_original_aspect_ratio=decrease[cover];"
            f"[bg][cover]overlay=x={cover_x}:y={cover_y}[comp]"
        )
        if has_lyrics:
            vf += f";[comp]ass={ass_name}[v0]"
            return vf, "v0", True
        return vf, "comp", True
    else:
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}"
        )
        if has_lyrics:
            vf += f",ass={ass_name}"
        return vf, "", False


def run_ffmpeg(
    session_dir: str,
    audio_name: str,
    image_name: str,
    w: int,
    h: int,
    has_lyrics: bool,
    bg_mode: str,
    song_title: str,
    artist: str,
    layout: dict,
    out_name: str = "output.mp4",
    ass_name: str = "subtitles.ass"
) -> tuple[bool, str]:
    vf, label, is_complex = build_vf(w, h, has_lyrics, bg_mode, layout, ass_name)

    def esc_drawtext(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
        )

    drawtext_filters = []
    if song_title and not has_lyrics:
        safe = esc_drawtext(song_title)
        title_y = layout["title_y"]
        title_x = layout["title_x_expr"]
        fontsize = int(layout["font_size"] * 1.05)
        drawtext_filters.append(
            f"drawtext=fontfile='C\\:/Windows/Fonts/msyhbd.ttc':"
            f"text='{safe}':fontsize={fontsize}:fontcolor=white:"
            f"x={title_x}:y={title_y}:shadowcolor=black@0.65:shadowx=2:shadowy=2"
        )
    if artist and not has_lyrics:
        safe = esc_drawtext(artist)
        artist_y = layout["artist_y"]
        artist_x = layout["artist_x_expr"]
        fontsize = int(layout["font_size"] * 0.82)
        drawtext_filters.append(
            f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':"
            f"text='{safe}':fontsize={fontsize}:fontcolor=white@0.84:"
            f"x={artist_x}:y={artist_y}:shadowcolor=black@0.55:shadowx=2:shadowy=2"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "30", "-i", image_name,
        "-i", audio_name,
    ]

    if is_complex:
        current = label
        for idx, flt in enumerate(drawtext_filters, 1):
            nxt = f"vt{idx}"
            vf += f";[{current}]{flt}[{nxt}]"
            current = nxt
        cmd += [
            "-filter_complex", vf,
            "-map", f"[{current}]",
            "-map", "1:a",
        ]
    else:
        if drawtext_filters:
            vf += "," + ",".join(drawtext_filters)
        cmd += ["-vf", vf]

    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_name,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=600, cwd=session_dir,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0, result.stderr[-3000:]


# ─── Background generation worker ────────────────────────────────────────────

def generate_worker(job_id: str, session_dir: str, params: dict):
    try:
        locale = normalize_locale(params.get("locale"))
        jobs[job_id] = {"status": "processing", "progress": 15, "msg": tr(locale, "getting_audio_duration")}

        audio_name = params["audio_name"]
        image_name = params["image_name"]
        lyrics_text = params["lyrics_text"]
        modes = params.get("mode", "landscape").split(",")
        bg_mode = params["bg_mode"]
        song_title = params["song_title"]
        artist = params["artist"]

        duration = get_duration(os.path.join(session_dir, audio_name))

        jobs[job_id] = {"status": "processing", "progress": 30, "msg": tr(locale, "processing_lyrics")}

        has_lyrics = bool(lyrics_text.strip())
        
        generated_files = []
        for i, mode in enumerate(modes):
            w, h = (1080, 1920) if mode == "portrait" else (1920, 1080)
            layout = get_layout(w, h)
            
            ass_name = f"subtitles_{mode}.ass"
            if has_lyrics:
                lyrics = parse_lrc(lyrics_text) if is_lrc(lyrics_text) else parse_plain(lyrics_text, duration)
                ass = build_ass(lyrics, duration, w, h, layout, song_title, artist)
                with open(os.path.join(session_dir, ass_name), "w", encoding="utf-8") as f:
                    f.write(ass)

            progress_base = 30 + int(i / len(modes) * 60)
            jobs[job_id] = {"status": "processing", "progress": progress_base, "msg": tr(locale, "rendering_video") + f" ({mode})"}

            out_name = f"output_{mode}.mp4"
            ok, stderr = run_ffmpeg(session_dir, audio_name, image_name, w, h, has_lyrics, bg_mode, song_title, artist, layout, out_name, ass_name)

            if not ok:
                jobs[job_id] = {"status": "error", "msg": tr(locale, "ffmpeg_error"), "detail": stderr}
                return
            generated_files.append(out_name)

        jobs[job_id] = {"status": "done", "progress": 100, "msg": tr(locale, "done"), "files": generated_files}

    except Exception as exc:
        jobs[job_id] = {"status": "error", "msg": str(exc)}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/align_lyrics", methods=["POST"])
def align_lyrics():
    locale = normalize_locale(request.form.get("locale"))
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": tr(locale, "upload_audio")}), 400
    
    text_lines = request.form.get("lyrics", "").strip().splitlines()
    text_lines = [l.strip() for l in text_lines if l.strip()]

    tmp_dir = os.path.join(UPLOAD_FOLDER, "tmp_align_" + str(uuid.uuid4()))
    os.makedirs(tmp_dir, exist_ok=True)
    audio_path = os.path.join(tmp_dir, secure_filename(audio_file.filename) or "audio.mp3")
    audio_file.save(audio_path)

    try:
        model = get_whisper_model()
        segments, _ = model.transcribe(audio_path, beam_size=5)
        whisper_segs = list(segments)
    except Exception as e:
        return jsonify({"error": tr(locale, "recognize_failed", error=str(e))}), 500
    finally:
        try:
            os.remove(audio_path)
            os.rmdir(tmp_dir)
        except:
            pass

    if not text_lines:
        lrc = ""
        for seg in whisper_segs:
            mm = int(seg.start // 60)
            ss = seg.start % 60
            lrc += f"[{mm:02d}:{ss:05.2f}]{seg.text.strip()}\n"
        return jsonify({"lrc": lrc})
        
    whisper_chars = []
    for seg in whisper_segs:
        for char in seg.text:
            if char.strip():
                whisper_chars.append({"char": char.lower(), "time": seg.start})
                
    user_chars = []
    for i, line in enumerate(text_lines):
        for char in line:
            if char.strip():
                user_chars.append({"char": char.lower(), "line_idx": i})
                
    sm = difflib.SequenceMatcher(None, [x["char"] for x in whisper_chars], [x["char"] for x in user_chars])
    
    line_times = {}
    for block in sm.get_matching_blocks():
        for i in range(block.size):
            w_idx = block.a + i
            u_idx = block.b + i
            line_idx = user_chars[u_idx]["line_idx"]
            time = whisper_chars[w_idx]["time"]
            if line_idx not in line_times:
                line_times[line_idx] = time
            else:
                line_times[line_idx] = min(line_times[line_idx], time)
                
    lrc = ""
    last_time = 0.0
    for i, line in enumerate(text_lines):
        t = line_times.get(i)
        if t is not None:
            last_time = t
        mm = int(last_time // 60)
        ss = last_time % 60
        lrc += f"[{mm:02d}:{ss:05.2f}]{line}\n"
        
    return jsonify({"lrc": lrc})


@app.route("/generate", methods=["POST"])
def generate():
    locale = normalize_locale(request.form.get("locale"))
    job_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_FOLDER, job_id)
    os.makedirs(session_dir)

    audio_file = request.files.get("audio")
    image_file = request.files.get("image")
    if not audio_file or not image_file:
        return jsonify({"error": tr(locale, "upload_audio_image")}), 400

    audio_ext = os.path.splitext(secure_filename(audio_file.filename))[1] or ".mp3"
    image_ext = os.path.splitext(secure_filename(image_file.filename))[1] or ".jpg"
    audio_name = f"audio{audio_ext}"
    image_name = f"cover{image_ext}"

    audio_file.save(os.path.join(session_dir, audio_name))
    image_file.save(os.path.join(session_dir, image_name))

    params = {
        "audio_name": audio_name,
        "image_name": image_name,
        "lyrics_text": request.form.get("lyrics", ""),
        "mode": request.form.get("mode", "landscape"),
        "bg_mode": request.form.get("bg_mode", "blur"),
        "song_title": request.form.get("song_title", ""),
        "artist": request.form.get("artist", ""),
        "locale": locale,
    }

    jobs[job_id] = {"status": "queued", "progress": 0, "msg": tr(locale, "queued")}
    t = threading.Thread(target=generate_worker, args=(job_id, session_dir, params), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>/<filename>")
def download(job_id: str, filename: str):
    # Only allow downloading output_landscape.mp4 or output_portrait.mp4
    if filename not in ("output_landscape.mp4", "output_portrait.mp4"):
        return tr("en", "file_not_found"), 404
        
    path = os.path.join(UPLOAD_FOLDER, job_id, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=filename)
    return tr("en", "file_not_found"), 404


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    import sys

    # Ensure UTF-8 output on Windows
    if sys.stdout.encoding != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    def _open():
        import time
        time.sleep(1.2)
        webbrowser.open("http://localhost:5004")

    threading.Thread(target=_open, daemon=True).start()
    print(tr("en", "started"))
    app.run(host="0.0.0.0", port=5004, debug=False)
