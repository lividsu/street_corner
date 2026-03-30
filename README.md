# Street Corner

Street Corner is a Flask + FFmpeg music video generator. Upload an audio file and a cover image, process lyrics (LRC/TXT), optionally auto-align timestamps, and export an MP4 file.

## Features

- Audio + cover upload with drag-and-drop support
- Lyrics input via LRC or plain TXT
- Automatic timestamp splitting for plain TXT lyrics
- Auto alignment powered by faster-whisper, outputs LRC
- Landscape (1920x1080) and portrait (1080x1920) video layouts
- Background modes: `fill` and `blur`
- Optional song title and artist overlay
- Async generation jobs with status polling and download endpoint
- Bilingual UI support (English / Chinese)

## Tech Stack

- Python
- Flask
- FFmpeg / FFprobe (system executables)
- faster-whisper

## Requirements

- Python 3.x
- `ffmpeg` and `ffprobe` must be installed and available in PATH
- On Windows, a CJK-capable font is recommended for lyric rendering

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Start the server

```bash
python app.py
```

Default URL:

```text
http://127.0.0.1:5004
```

### 3) One-click start on Windows

```bash
run.bat
```

## Workflow

1. Upload an audio file and a cover image.
2. Provide lyrics (upload LRC/TXT, or paste text).
3. Choose video orientation and background mode.
4. Optionally set song title and artist.
5. Generate and download when the job is complete.

## Lyrics Processing

- For LRC input: original timestamps are preserved.
- For TXT input: timestamps are evenly distributed across total audio duration.
- Use auto-align to refine per-line timing using whisper transcription.

## API Overview

- `POST /generate` - Submit a video generation job
- `GET /status/<job_id>` - Query job status
- `GET /download/<job_id>` - Download generated MP4
- `POST /align_lyrics` - Auto-align lyrics and return LRC

## API Examples

```bash
curl -X POST "http://127.0.0.1:5004/generate" \
  -F "audio=@test_audio.mp3" \
  -F "cover=@test_cover.jpg" \
  -F "lyrics=Hello world" \
  -F "lang=en"
```

```bash
curl "http://127.0.0.1:5004/status/<job_id>"
```

```bash
curl -O "http://127.0.0.1:5004/download/<job_id>"
```

```bash
curl -X POST "http://127.0.0.1:5004/align_lyrics" \
  -F "audio=@test_audio.mp3" \
  -F "lyrics_text=Hello world"
```

## Project Structure

- `app.py` - Backend entry and route layer
- `settings.py` - Centralized runtime configuration
- `i18n.py` - Locale normalization and message lookup
- `job_store.py` - Thread-safe job status store
- `lyrics.py` - Lyric parsing, alignment tokenization, ASS building
- `media.py` - FFprobe metadata and FFmpeg rendering helpers
- `aligner.py` - Whisper transcription and lyric alignment flow
- `generator.py` - Background generation worker orchestration
- `templates/index.html` - Frontend page
- `requirements.txt` - Python dependencies
- `run.bat` - Windows startup script
- `uploads/` - Runtime output directory (git-ignored)

## Notes

- Max request size is 500 MB.
- Video rendering depends on local FFmpeg availability.
- If lyric text is not rendered correctly, adjust font settings in `lyrics.py` and `media.py`.
