from fastapi import FastAPI, Request, Response, Depends
from fastapi.responses import (
    HTMLResponse,
    StreamingResponse,
    FileResponse,
    RedirectResponse,
    JSONResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio
import io

import sys
# 确保可以导入项目根目录的模块
if __name__ == "__main__":
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.qqmusic import QQMusicAPI
from downloader.music_downloader import MusicDownloader
from utils.config import config
from utils.formatters import format_singers, format_interval, clean_html_tags

app = FastAPI(title="Music Downloader Web")
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

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


def get_available_formats(song: dict) -> str:
    """Return human readable available audio formats"""
    if not song.get("file"):
        return "未知"
    file_info = song["file"]
    available = []
    format_map = {
        "size_48aac": "M4A 48k",
        "size_96aac": "M4A 96k",
        "size_192aac": "M4A 192k",
        "size_128mp3": "MP3 128k",
        "size_320mp3": "MP3 320k",
        "size_96ogg": "OGG 96k",
        "size_192ogg": "OGG 192k",
        "size_flac": "FLAC",
    }

    for key, name in format_map.items():
        if file_info.get(key, 0) > 0:
            available.append(name)

    size_new = file_info.get("size_new", [])
    if len(size_new) >= 6:
        if size_new[0] > 0:
            available.append("母带")
        if size_new[1] > 0:
            available.append("全景声")
        if size_new[2] > 0:
            available.append("臻品音质")

    return ", ".join(available) if available else "无可用格式"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not await qq_api.is_logged_in():
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "use_light_mode": config.LIGHT_DOWNLOAD_MODE},
    )


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
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "songs": [],
                "use_light_mode": config.LIGHT_DOWNLOAD_MODE,
            },
        )
    result = await qq_api.search(q, limit=20, page=1)
    songs = []
    for s in result.get("songs", []):
        songs.append({
            "name": clean_html_tags(s.get("name", "")),
            "mid": s.get("mid", ""),
            "singers": format_singers(s.get("singer", [])),
            "album_name": clean_html_tags(s.get("album", {}).get("name", "")),
            "duration": format_interval(s.get("interval", 0)),
            "formats": get_available_formats(s),
        })
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "songs": songs,
            "query": q,
            "use_light_mode": config.LIGHT_DOWNLOAD_MODE,
        },
    )


@app.get("/download")
async def download(mid: str, name: str, singer: str, album: str):
    song_info = {
        "mid": mid,
        "name": name,
        "singer": [{"name": singer}],
        "album": {"name": album, "mid": ""},
    }
    if config.LIGHT_DOWNLOAD_MODE:
        song_url_result = await qq_api.song_url(song_info["mid"], config.DEFAULT_QUALITY)
        if song_url_result.get("code") == 0 and song_url_result.get("url"):
            return RedirectResponse(song_url_result["url"])
        return JSONResponse({"error": "Cannot fetch song URL"}, status_code=500)
    path = await music_downloader.download_song(
        song_info, Path("downloads"), config.DEFAULT_QUALITY
    )
    if not path:
        return JSONResponse({"error": "Download failed"}, status_code=500)
    return FileResponse(path, filename=path.name)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
