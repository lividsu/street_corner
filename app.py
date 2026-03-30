import io
import os
import threading
import uuid
import webbrowser

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from aligner import align_lyrics_text
from generator import generate_worker
from i18n import normalize_locale, tr
from job_store import JobStore
from media import get_audio_metadata
from settings import MAX_CONTENT_LENGTH, SERVER_HOST, SERVER_PORT, UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
jobs = JobStore()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/align_lyrics", methods=["POST"])
def align_lyrics():
    locale = normalize_locale(request.form.get("locale"))
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": tr(locale, "upload_audio")}), 400
    tmp_dir = os.path.join(UPLOAD_FOLDER, "tmp_align_" + str(uuid.uuid4()))
    os.makedirs(tmp_dir, exist_ok=True)
    audio_path = os.path.join(tmp_dir, secure_filename(audio_file.filename) or "audio.mp3")
    audio_file.save(audio_path)
    try:
        lrc = align_lyrics_text(audio_path, request.form.get("lyrics", ""), locale)
        return jsonify({"lrc": lrc})
    except Exception as exc:
        return jsonify({"error": tr(locale, "recognize_failed", error=str(exc))}), 500
    finally:
        try:
            os.remove(audio_path)
            os.rmdir(tmp_dir)
        except:
            pass


@app.route("/audio_metadata", methods=["POST"])
def audio_metadata():
    locale = normalize_locale(request.form.get("locale"))
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": tr(locale, "upload_audio")}), 400
    tmp_dir = os.path.join(UPLOAD_FOLDER, "tmp_meta_" + str(uuid.uuid4()))
    os.makedirs(tmp_dir, exist_ok=True)
    safe_name = secure_filename(audio_file.filename) or "audio.mp3"
    audio_path = os.path.join(tmp_dir, safe_name)
    audio_file.save(audio_path)
    original_name = os.path.basename(audio_file.filename or "")
    song_title = os.path.splitext(original_name)[0].strip()
    artist = ""
    try:
        metadata = get_audio_metadata(audio_path)
        artist = metadata.get("artist", "")
        if not song_title:
            song_title = metadata.get("title", "")
    finally:
        try:
            os.remove(audio_path)
            os.rmdir(tmp_dir)
        except:
            pass
    return jsonify({"song_title": song_title, "artist": artist})


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
    audio_path = os.path.join(session_dir, audio_name)
    audio_file.save(audio_path)
    image_file.save(os.path.join(session_dir, image_name))
    metadata = get_audio_metadata(audio_path)
    original_name = os.path.basename(audio_file.filename or "")
    fallback_title = os.path.splitext(original_name)[0].strip() or metadata.get("title", "")
    song_title = request.form.get("song_title", "").strip() or fallback_title
    artist = request.form.get("artist", "").strip() or metadata.get("artist", "")
    params = {
        "audio_name": audio_name,
        "image_name": image_name,
        "lyrics_text": request.form.get("lyrics", ""),
        "mode": request.form.get("mode", "landscape"),
        "bg_mode": request.form.get("bg_mode", "blur"),
        "song_title": song_title,
        "artist": artist,
        "locale": locale,
    }
    jobs.set(job_id, {"status": "queued", "progress": 0, "msg": tr(locale, "queued")})
    t = threading.Thread(target=generate_worker, args=(jobs, job_id, session_dir, params), daemon=True)
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
    if filename not in ("output_landscape.mp4", "output_portrait.mp4"):
        return tr("en", "file_not_found"), 404
    path = os.path.join(UPLOAD_FOLDER, job_id, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=filename)
    return tr("en", "file_not_found"), 404


if __name__ == "__main__":
    if os.sys.stdout.encoding != "utf-8":
        os.sys.stdout = io.TextIOWrapper(os.sys.stdout.buffer, encoding="utf-8", errors="replace")

    def _open():
        import time
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{SERVER_PORT}")

    threading.Thread(target=_open, daemon=True).start()
    print(tr("en", "started"))
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
