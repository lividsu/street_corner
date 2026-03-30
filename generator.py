import os

from i18n import normalize_locale, tr
from job_store import JobStore
from lyrics import build_ass, get_layout, is_lrc, parse_lrc, parse_plain
from media import get_duration, run_ffmpeg


def generate_worker(job_store: JobStore, job_id: str, session_dir: str, params: dict):
    try:
        locale = normalize_locale(params.get("locale"))
        job_store.set(job_id, {"status": "processing", "progress": 15, "msg": tr(locale, "getting_audio_duration")})

        audio_name = params["audio_name"]
        image_name = params["image_name"]
        lyrics_text = params["lyrics_text"]
        modes = params.get("mode", "landscape").split(",")
        bg_mode = params["bg_mode"]
        song_title = params["song_title"]
        artist = params["artist"]

        duration = get_duration(os.path.join(session_dir, audio_name))
        job_store.set(job_id, {"status": "processing", "progress": 30, "msg": tr(locale, "processing_lyrics")})

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
            job_store.set(job_id, {"status": "processing", "progress": progress_base, "msg": tr(locale, "rendering_video") + f" ({mode})"})

            out_name = f"output_{mode}.mp4"
            ok, stderr = run_ffmpeg(session_dir, audio_name, image_name, w, h, has_lyrics, bg_mode, song_title, artist, layout, out_name, ass_name)
            if not ok:
                job_store.set(job_id, {"status": "error", "msg": tr(locale, "ffmpeg_error"), "detail": stderr})
                return
            generated_files.append(out_name)

        job_store.set(job_id, {"status": "done", "progress": 100, "msg": tr(locale, "done"), "files": generated_files})
    except Exception as exc:
        job_store.set(job_id, {"status": "error", "msg": str(exc)})
