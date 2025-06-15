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
import os

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

# 应用启动事件


@app.on_event("startup")
async def startup_event():
    # 启动时异步验证凭证
    await qq_api.validate_credential()
    global login_status
    if await qq_api.is_logged_in():
        login_status = "success"


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
        qq_api.credential = data
    elif event in {"timeout", "refused", "error"}:
        login_status = event


def get_available_formats(song: dict) -> dict:
    """Return available audio formats with their keys and human readable names"""
    if not song.get("file"):
        return {"readable": "未知", "formats": []}

    file_info = song["file"]
    available = []
    format_map = {
        "size_48aac": {"name": "M4A 48k", "quality": "m4a", "ext": "m4a"},
        "size_96aac": {"name": "M4A 96k", "quality": "m4a", "ext": "m4a"},
        "size_192aac": {"name": "M4A 192k", "quality": "m4a", "ext": "m4a"},
        "size_128mp3": {"name": "MP3 128k", "quality": "128", "ext": "mp3"},
        "size_320mp3": {"name": "MP3 320k", "quality": "320", "ext": "mp3"},
        "size_96ogg": {"name": "OGG 96k", "quality": "ogg", "ext": "ogg"},
        "size_192ogg": {"name": "OGG 192k", "quality": "ogg", "ext": "ogg"},
        "size_flac": {"name": "FLAC", "quality": "flac", "ext": "flac"},
    }

    for key, info in format_map.items():
        if file_info.get(key, 0) > 0:
            available.append(info)

    size_new = file_info.get("size_new", [])
    if len(size_new) >= 6:
        if size_new[0] > 0:
            available.append({"name": "母带", "quality": "sq", "ext": "flac"})
        if size_new[1] > 0:
            available.append(
                {"name": "全景声", "quality": "dolby", "ext": "flac"})
        if size_new[2] > 0:
            available.append({"name": "臻品音质", "quality": "hi", "ext": "flac"})

    readable = ", ".join([fmt["name"]
                         for fmt in available]) if available else "无可用格式"
    return {"readable": readable, "formats": available}


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
    # 如果已经登录，直接重定向到首页
    if await qq_api.is_logged_in():
        return RedirectResponse("/")

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
    # 如果登录成功，确保凭证已正确加载
    if login_status == "success":
        await qq_api.validate_credential()
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
        formats_data = get_available_formats(s)
        songs.append({
            "name": clean_html_tags(s.get("name", "")),
            "mid": s.get("mid", ""),
            "singers": format_singers(s.get("singer", [])),
            "album_name": clean_html_tags(s.get("album", {}).get("name", "")),
            "duration": format_interval(s.get("interval", 0)),
            "formats": formats_data["readable"],
            "available_formats": formats_data["formats"],
        })
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "songs": songs,
            "query": q,
            "use_light_mode": config.LIGHT_DOWNLOAD_MODE,
            "default_quality": config.DEFAULT_QUALITY,
        },
    )


@app.get("/download")
async def download(mid: str, name: str, singer: str, album: str, quality: str = None):
    song_info = {
        "mid": mid,
        "name": name,
        "singer": [{"name": singer}],
        "album": {"name": album, "mid": ""},
    }

    # 如果未指定音质，使用默认音质
    quality = quality or config.DEFAULT_QUALITY

    # 创建自定义文件名 "标题-歌手"
    custom_filename = f"{name}-{singer}"

    # 轻量下载模式
    if config.LIGHT_DOWNLOAD_MODE:
        song_url_result = await qq_api.song_url(song_info["mid"], quality)
        if song_url_result.get("code") == 0 and song_url_result.get("url"):
            # 无法直接修改浏览器下载的文件名，因为这里是重定向
            return RedirectResponse(song_url_result["url"])
        return JSONResponse({"error": "Cannot fetch song URL"}, status_code=500)

    # 完整下载模式
    path = await music_downloader.download_song(
        song_info, Path("downloads"), quality
    )
    if not path:
        return JSONResponse({"error": "Download failed"}, status_code=500)

    # 获取文件扩展名
    file_ext = os.path.splitext(path.name)[1]
    # 设置自定义文件名，保留原扩展名
    custom_filename = f"{custom_filename}{file_ext}"

    return FileResponse(path, filename=custom_filename)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
