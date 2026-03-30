import json
import subprocess

from settings import FFMPEG_TIMEOUT_SECONDS


def get_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 180.0


def get_audio_metadata(path: str) -> dict[str, str]:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
        tags = (data.get("format", {}).get("tags", {}) or {})
        tags_norm = {str(k).lower(): str(v).strip() for k, v in tags.items() if str(v).strip()}
        artist = tags_norm.get("artist") or tags_norm.get("album_artist") or tags_norm.get("albumartist") or ""
        title = tags_norm.get("title") or ""
        return {"title": title, "artist": artist}
    except Exception:
        return {"title": "", "artist": ""}


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
        timeout=FFMPEG_TIMEOUT_SECONDS, cwd=session_dir,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0, result.stderr[-3000:]
