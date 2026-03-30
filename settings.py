import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5004
WHISPER_MODEL_NAME = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
FFMPEG_TIMEOUT_SECONDS = 600

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
