import os, uuid, json, shutil, subprocess, re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("DATA_DIR", BASE / "data")).resolve()
UPLOADS = DATA / "uploads"
CLIPS = DATA / "clips"
for p in (UPLOADS, CLIPS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI AutoClipper", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "app" / "templates"))
JOBS = {}

def ffmpeg_available():
    return shutil.which("ffmpeg") is not None

def probe_duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0
    p = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1",str(path)],
                       capture_output=True, text=True)
    try: return float(p.stdout.strip())
    except: return 0

def transcribe(path: Path):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv("WHISPER_MODEL","base"), device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(path), vad_filter=True)
        out = []
        for s in segments:
            out.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip()})
        return out
    except Exception as e:
        return {"error": str(e)}

def gemini_highlights(transcript, duration, count):
    key = os.getenv("GEMINI_API_KEY")
    if not key or not isinstance(transcript, list) or not transcript:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        text = "\n".join([f"[{x['start']:.1f}-{x['end']:.1f}] {x['text']}" for x in transcript])
        prompt = f"""Select up to {count} compelling, self-contained short-video moments from this transcript.
Video duration: {duration:.1f} seconds. Each clip should be 20-60 seconds, preserve context,
start with an engaging moment, and not end mid-sentence. Do not invent content.
Return ONLY JSON array with objects: start (seconds), end (seconds), title, reason, score (0-100).
Transcript:
{text[:28000]}"""
        response = model.generate_content(prompt)
        raw = response.text.strip().replace("```json","").replace("```","")
        clips = json.loads(raw)
        clean=[]
        for c in clips:
            start=max(0,float(c["start"])); end=min(duration,float(c["end"]))
            if end-start >= 8:
                clean.append({"start":start,"end":end,"title":str(c.get("title","AI highlight")),
                              "reason":str(c.get("reason","")), "score":int(c.get("score",75))})
        return sorted(clean,key=lambda x:x["score"],reverse=True)[:count]
    except Exception:
        return None

def fallback_segments(duration, count):
    if duration <= 0: duration = 300
    clip_len = min(45, max(20, duration / max(count,1)))
    clips=[]
    for i in range(min(count, max(1,int(duration//8)))):
        start = max(0, (duration * (i + 0.5) / min(count, max(1,int(duration//8)))) - clip_len/2)
        end = min(duration, start+clip_len)
        if end-start >= 8:
            clips.append({"start":start,"end":end,"title":f"Suggested segment {i+1}",
                          "reason":"Fallback time-based suggestion. Configure Whisper and Gemini for AI-selected highlights.",
                          "score":0})
    return clips

def make_srt(segments, start, end):
    def stamp(sec):
        ms=int((sec-int(sec))*1000); s=int(sec); h=s//3600; m=(s%3600)//60; ss=s%60
        return f"{h:02}:{m:02}:{ss:02},{ms:03}"
    lines=[]; idx=1
    for seg in segments if isinstance(segments,list) else []:
        a=max(start,seg["start"]); b=min(end,seg["end"])
        if b<=a: continue
        lines += [str(idx),f"{stamp(a-start)} --> {stamp(b-start)}",seg["text"],""]
        idx+=1
    return "\n".join(lines)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...), authorized: bool = Form(...)):
    if not authorized:
        raise HTTPException(400, "Please confirm you have permission to edit and redistribute this video.")
    ext=Path(file.filename or "").suffix.lower()
    if ext not in {".mp4",".mov",".mkv",".webm",".m4v"}:
        raise HTTPException(400,"Supported formats: MP4, MOV, MKV, WEBM, M4V.")
    job_id=str(uuid.uuid4())
    dest=UPLOADS/f"{job_id}{ext}"
    with dest.open("wb") as f: shutil.copyfileobj(file.file,f)
    duration=probe_duration(dest)
    JOBS[job_id]={"id":job_id,"filename":file.filename,"path":str(dest),"duration":duration,
                  "status":"uploaded","clips":[],"transcript":[]}
    return JOBS[job_id]

@app.post("/api/analyze/{job_id}")
async def analyze(job_id: str, count: int = Form(4)):
    job=JOBS.get(job_id)
    if not job: raise HTTPException(404,"Project not found")
    if not ffmpeg_available(): raise HTTPException(500,"FFmpeg is not installed or not on PATH.")
    duration=job["duration"] or 300
    transcript=transcribe(Path(job["path"]))
    job["transcript"]=transcript
    clips=gemini_highlights(transcript,duration,max(1,min(count,20)))
    mode="AI"
    if not clips:
        clips=fallback_segments(duration,max(1,min(count,20)))
        mode="fallback"
    job["clips"]=clips
    job["status"]="analyzed"
    job["analysis_mode"]=mode
    return {"clips":clips,"mode":mode,"duration":duration}

@app.post("/api/render/{job_id}/{clip_index}")
async def render_clip(job_id: str, clip_index: int, captions: bool = Form(True)):
    job=JOBS.get(job_id)
    if not job or clip_index >= len(job.get("clips",[])): raise HTTPException(404,"Clip not found")
    clip=job["clips"][clip_index]
    out=CLIPS/f"{job_id}_{clip_index+1}.mp4"
    source=Path(job["path"])
    duration=clip["end"]-clip["start"]
    # Center crop to 9:16. For production, replace with face/speaker-aware crop tracking.
    vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    cmd=["ffmpeg","-y","-ss",str(clip["start"]),"-i",str(source),"-t",str(duration),
         "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23",
         "-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)]
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode != 0:
        raise HTTPException(500,"FFmpeg render failed: "+p.stderr[-1200:])
    clip["rendered"]=True
    clip["output"]=out.name
    return {"ok":True,"filename":out.name,"url":f"/api/download/{out.name}"}

@app.get("/api/download/{filename}")
async def download(filename: str):
    path=CLIPS/Path(filename).name
    if not path.exists(): raise HTTPException(404,"File not found")
    return FileResponse(path,media_type="video/mp4",filename=path.name)

@app.get("/api/jobs")
async def jobs():
    return list(JOBS.values())

@app.get("/api/health")
async def health():
    return {"ok":True,"ffmpeg":ffmpeg_available(),"projects":len(JOBS),
            "gemini_configured":bool(os.getenv("GEMINI_API_KEY"))}
