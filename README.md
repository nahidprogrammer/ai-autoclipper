# AI AutoClipper (early prototype)

A small FastAPI prototype for uploading videos you own or are explicitly authorized to edit, suggesting candidate segments, rendering vertical 9:16 MP4 clips, and downloading them.

## Current capabilities
- Upload MP4, MOV, MKV, WEBM, and M4V videos.
- Probe video duration with FFmpeg/ffprobe.
- Suggest time ranges. If Whisper and Gemini are configured and available, the prototype attempts transcript-based highlight selection; otherwise it uses simple time-based fallback suggestions.
- Render vertical 9:16 MP4 clips with FFmpeg.
- Download rendered clips.

## Not implemented yet
- No automatic YouTube, Instagram, or TikTok publishing/OAuth.
- No production authentication, multi-user isolation, background job queue, or cloud object storage.
- No reliable face tracking or animated/burned-in subtitles in this prototype.
- AI highlight selection is not guaranteed; configure and test Whisper/Gemini before relying on it.

## Run locally
Requires Python 3.11+ and FFmpeg/ffprobe.

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Deploy with Docker
The included Dockerfile installs FFmpeg and runs the FastAPI app. A platform must support Docker web services. Set the start command through the Dockerfile's CMD.

For Render, create a **Web Service**, connect this GitHub repository, and choose the Docker runtime. Add a persistent disk mounted at `/var/data` and set `DATA_DIR=/var/data` if you want uploaded videos and clips to survive restarts/redeploys. Render's free web services do not support persistent disks and have limited memory, so use free hosting only for a basic deployment check, not dependable video processing. Review the host's current pricing before enabling paid resources.

## Environment variables
- `DATA_DIR`: where uploads and clips are stored (default: `./data`).
- `GEMINI_API_KEY`: optional API key for Gemini transcript-based highlight selection.
- `WHISPER_MODEL`: optional faster-whisper model name (default: `base`).

## Important
Only process videos you own or have explicit permission to edit and republish. Publicly viewable YouTube videos are not automatically licensed for downloading or reuse. This prototype does not download videos from YouTube.
