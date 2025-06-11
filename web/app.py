from fastapi import FastAPI, Request, Response, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio
import io

from api.qqmusic import QQMusicAPI
from downloader.music_downloader import MusicDownloader
from utils.config import config

app = FastAPI(title="Music Downloader Web")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

qq_api = QQMusicAPI()
music_downloader = MusicDownloader()

qr_bytes = b""
login_status = "not_started"
login_task: asyncio.Task | None = None


def login_callback(event: str, data):
    global qr_bytes, login_status
    if event == "qr_generated":
        qr_bytes = data
        login_status = "waiting_scan"
    elif event == "waiting_scan":
        login_status = "waiting_scan"
    elif event == "waiting_confirm":
        login_status = "waiting_confirm"
    elif event == "login_success":
        login_status = "success"
    elif event in {"timeout", "refused", "error"}:
        login_status = event


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not await qq_api.is_logged_in():
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    global login_task, login_status
    if login_task is None or login_task.done():
        login_status = "starting"
        login_task = asyncio.create_task(qq_api.login_with_qr(callback=login_callback))
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login/qrcode")
async def login_qrcode():
    if qr_bytes:
        return StreamingResponse(io.BytesIO(qr_bytes), media_type="image/png")
    return Response(status_code=404)


@app.get("/login/status")
async def login_status_api():
    return {"status": login_status, "user": qq_api.get_user_info()}


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    if not q:
        return templates.TemplateResponse("search.html", {"request": request, "songs": []})
    result = await qq_api.search(q, limit=20, page=1)
    songs = result.get("songs", [])
    return templates.TemplateResponse("search.html", {"request": request, "songs": songs})


@app.get("/download/{mid}")
async def download(mid: str):
    detail = await qq_api.song_detail(mid)
    if detail.get("code") != 0:
        return JSONResponse({"error": "Song not found"}, status_code=404)
    song_info = detail.get("data")
    path = await music_downloader.download_song(song_info, Path("downloads"), config.DEFAULT_QUALITY)
    if not path:
        return JSONResponse({"error": "Download failed"}, status_code=500)
    return FileResponse(path, filename=path.name)

