import os
from pathlib import Path
from typing import Dict, Optional, Union

from mutagen import File
from mutagen.asf import ASF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from api.qqmusic import QQMusicAPI
from downloader.downloader import DownloadManager
from utils.formatters import format_singers, get_file_path, parse_lrc_lyrics
from utils.logger import logger


class MusicDownloader:
    """音乐下载器，处理歌曲下载、封面和歌词嵌入、重命名等功能"""

    def __init__(self):
        self.qq_music_api = QQMusicAPI()  # 使用新的统一API
        self.download_manager = DownloadManager()
        self.log = logger.log_progress

    async def download_song(self, song_info: Dict, download_dir: Path, filetype: str = 'm4a', cookie: str = None) -> Optional[Path]:
        """下载歌曲并处理封面、歌词等

        Args:
            song_info: 歌曲信息字典
            download_dir: 下载目录
            filetype: 文件类型 ('m4a'/'128'/'320'/'flac/ATMOS_51/ATMOS_2/MASTER')
            cookie: QQ音乐Cookie (可选，如果使用新API且已登录则自动使用凭证)

        Returns:
            处理完成的文件路径，失败则返回None
        """
        song_name = song_info["name"]
        singers = format_singers(song_info["singer"])
        self.log(f"开始下载歌曲: {song_name} - {singers}")

        try:
            # 确保下载目录存在
            if not download_dir.exists():
                self.log(f"下载目录不存在，正在创建: {download_dir}")
                download_dir.mkdir(parents=True, exist_ok=True)

            # 1. 获取歌曲URL
            self.log("正在获取下载链接...")

            # 使用新的统一API获取下载链接
            use_credential = await self.qq_music_api.is_logged_in()
            if use_credential:
                self.log("使用登录凭证获取下载链接...")
            else:
                self.log("未登录状态，尝试获取免费下载链接...")
                self.log("登录凭据无效或已过期，如遇下载受限请重新登录。", level="WARNING")

            song_url_result = await self.qq_music_api.song_url(song_info['mid'], quality=filetype)

            if song_url_result['code'] == -1 or not song_url_result.get('url'):
                error_msg = "无法获取歌曲下载链接，可能原因："
                if not use_credential and not cookie:
                    error_msg += "\n- 未登录且未提供Cookie（建议通过菜单栏登录）"
                if filetype in ["320", "flac", "ATMOS_51", "ATMOS_2", "MASTER"]:
                    error_msg += f"\n- 当前音质（{filetype}）可能需要VIP权限"
                error_msg += "\n- 歌曲可能有版权限制"
                if use_credential:
                    error_msg += "\n- 当前账户可能没有该歌曲的下载权限"
                self.log(error_msg)
                return None

            # 2. 下载歌曲
            song_url = song_url_result["url"]
            temp_filepath = await get_file_path(song_info, song_url, download_dir)
            self.log(f"准备下载歌曲到: {temp_filepath.name}")

            download_success = await self.download_manager.download_with_progress(
                song_url, temp_filepath
            )
            if not download_success:
                self.log("下载歌曲失败，请检查网络连接或重试")
                return None
            self.log("歌曲文件下载完成")

            # 3. 下载专辑封面
            self.log("正在获取专辑封面...")
            album_mid = song_info['album']['mid']
            cover_path = await self.download_manager.download_album_cover(album_mid, download_dir)
            if cover_path:
                self.log("专辑封面下载完成")
            else:
                self.log("警告: 未能下载专辑封面，将继续处理音频文件")

            # 4. 下载歌词
            self.log("正在获取歌词...")
            try:
                lyrics_result = await self.qq_music_api.get_lyrics(song_info["mid"])
                if lyrics_result['code'] == 0:
                    lrc_lyrics = parse_lrc_lyrics(lyrics_result)
                    if not lrc_lyrics:
                        self.log("警告: 未找到歌词或歌词格式不正确")
                else:
                    self.log("警告: 获取歌词失败")
                    lrc_lyrics = ""
            except Exception as e:
                self.log(f"获取歌词时出错: {str(e)}")
                lrc_lyrics = ""

            # 5. 添加封面和歌词到音频文件
            self.log("正在处理音频文件元数据...")
            processed_filepath = await self._add_cover_and_lyrics(
                temp_filepath,
                cover_path,
                lrc_lyrics
            )

            # 6. 清理临时文件
            try:
                if temp_filepath != processed_filepath and temp_filepath.exists():
                    self.log("清理临时音频文件...")
                    os.remove(temp_filepath)
                if cover_path and cover_path.exists():
                    self.log("清理临时封面文件...")
                    os.remove(cover_path)
            except Exception as e:
                self.log(f"清理临时文件时出现警告: {str(e)}")
                # 继续执行，因为临时文件清理失败不影响主要功能

            # 7. 完成处理
            quality_str = {
                "m4a": "标准品质",
                "128": "标准品质",
                "320": "高品质",
                "flac": "无损品质",
                "ATMOS_51": "臻品音质2.0",
                "ATMOS_2": "臻品全景声2.0",
                "MASTER": "臻品母带2.0",
            }.get(filetype, filetype)

            file_size = processed_filepath.stat().st_size
            size_str = f"{file_size / 1024 / 1024:.1f}MB"

            self.log(
                f"下载完成: {processed_filepath.name}\n"
                f"音质: {quality_str}\n"
                f"大小: {size_str}"
            )
            return processed_filepath

        except Exception as e:
            self.log(f"处理歌曲时出错: {str(e)}")
            # 确保出错时也清理临时文件
            try:
                if "temp_filepath" in locals() and temp_filepath.exists():
                    os.remove(temp_filepath)
                if "cover_path" in locals() and cover_path and cover_path.exists():
                    os.remove(cover_path)
            except Exception:
                pass  # 清理失败不影响错误处理
            return None

    async def _add_cover_and_lyrics(self, filepath: Path,
                                    cover_path: Optional[Path], lyrics: str) -> Path:
        """只添加封面和歌词到音频文件

        Args:
            filepath: 临时文件路径
            cover_path: 封面文件路径
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        # 读取封面数据
        cover_data = None
        if cover_path and cover_path.exists():
            with open(cover_path, 'rb') as f:
                cover_data = f.read()

        try:
            # 使用mutagen.File获取文件对象
            audio = File(filepath)

            if audio is None:
                self.log(f"不支持的音频文件格式: {filepath}")
                return filepath

            # 根据文件类型处理元数据，只添加封面和歌词
            if isinstance(audio, MP3):
                processed_path = self._add_to_mp3(
                    filepath, audio, cover_data, lyrics)
            elif isinstance(audio, MP4):
                processed_path = self._add_to_mp4(
                    filepath, audio, cover_data, lyrics)
            elif isinstance(audio, FLAC):
                processed_path = self._add_to_flac(
                    filepath, audio, cover_data, lyrics)
            elif isinstance(audio, (OggVorbis, OggOpus)):
                processed_path = self._add_to_ogg(
                    filepath, audio, cover_data, lyrics)
            elif isinstance(audio, ASF):
                processed_path = self._add_to_asf(
                    filepath, audio, cover_data, lyrics)
            else:
                self.log(f"未能识别的音频文件类型: {type(audio).__name__}")
                processed_path = filepath

            # 重命名文件（根据自身元数据）
            return self._rename_file(processed_path)

        except Exception as e:
            self.log(f"处理音频文件时出错: {str(e)}")
            return filepath

    def _add_to_mp3(self, filepath: Path, audio: MP3,
                    cover_data: Optional[bytes], lyrics: str) -> Path:
        """向MP3文件添加封面和歌词

        Args:
            filepath: 文件路径
            audio: MP3对象
            cover_data: 封面数据
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        try:
            # 确保有ID3标签
            if audio.tags is None:
                audio.add_tags()

            # 只添加封面
            if cover_data:
                audio.tags.add(APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,  # 封面
                    desc='Cover',
                    data=cover_data
                ))

            # 只添加歌词
            if lyrics:
                audio.tags.add(USLT(
                    encoding=3,
                    lang='chi',
                    desc='Lyrics',
                    text=lyrics
                ))

            audio.save()
            return filepath

        except Exception as e:
            self.log(f"向MP3添加封面和歌词时出错: {str(e)}")
            return filepath

    def _add_to_mp4(self, filepath: Path, audio: MP4,
                    cover_data: Optional[bytes], lyrics: str) -> Path:
        """向MP4/M4A文件添加封面和歌词

        Args:
            filepath: 文件路径
            audio: MP4对象
            cover_data: 封面数据
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        try:
            # 只添加封面
            if cover_data:
                audio['covr'] = [
                    MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

            # 只添加歌词
            if lyrics:
                audio['\xa9lyr'] = [lyrics]

            audio.save()
            return filepath

        except Exception as e:
            self.log(f"向MP4/M4A添加封面和歌词时出错: {str(e)}")
            return filepath

    def _add_to_flac(self, filepath: Path, audio: FLAC,
                     cover_data: Optional[bytes], lyrics: str) -> Path:
        """向FLAC文件添加封面和歌词

        Args:
            filepath: 文件路径
            audio: FLAC对象
            cover_data: 封面数据
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        try:
            # 只添加歌词
            if lyrics:
                audio['LYRICS'] = lyrics

            # 只添加封面
            if cover_data:
                picture = Picture()
                picture.type = 3  # 封面图片类型
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = cover_data

                # 清除旧的图片
                audio.clear_pictures()
                # 添加新图片
                audio.add_picture(picture)

            audio.save()
            return filepath

        except Exception as e:
            self.log(f"向FLAC添加封面和歌词时出错: {str(e)}")
            return filepath

    def _add_to_ogg(self, filepath: Path, audio: Union[OggVorbis, OggOpus],
                    cover_data: Optional[bytes], lyrics: str) -> Path:
        """向OGG文件添加封面和歌词

        Args:
            filepath: 文件路径
            audio: OggVorbis或OggOpus对象
            cover_data: 封面数据
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        try:
            # 只添加歌词
            if lyrics:
                audio['LYRICS'] = lyrics

            # OGG封面嵌入比较复杂，需要Base64编码等处理
            # 这里简化处理，实际可能需要更复杂的逻辑

            audio.save()
            return filepath

        except Exception as e:
            self.log(f"向OGG添加封面和歌词时出错: {str(e)}")
            return filepath

    def _add_to_asf(self, filepath: Path, audio: ASF,
                    cover_data: Optional[bytes], lyrics: str) -> Path:
        """向ASF/WMA文件添加封面和歌词

        Args:
            filepath: 文件路径
            audio: ASF对象
            cover_data: 封面数据
            lyrics: 歌词文本

        Returns:
            处理后的文件路径
        """
        try:
            # 只添加歌词
            if lyrics:
                audio['WM/Lyrics'] = lyrics

            # 添加封面(如果支持)
            if cover_data:
                audio['WM/Picture'] = cover_data

            audio.save()
            return filepath

        except Exception as e:
            self.log(f"向ASF/WMA添加封面和歌词时出错: {str(e)}")
            return filepath

    def _rename_file(self, filepath: Path) -> Path:
        """根据音频文件自身元数据重命名文件

        Args:
            filepath: 原文件路径

        Returns:
            新文件路径
        """
        artist = None
        title = None

        try:
            # 使用File获取音频文件对象
            audio = File(filepath)

            if audio is None:
                raise Exception("不支持的音频文件格式")

            # 根据文件类型获取元数据
            if isinstance(audio, MP3):
                if audio.tags:
                    # 尝试读取标题
                    if 'TIT2' in audio.tags:
                        title = str(audio.tags['TIT2'])
                    # 尝试读取艺术家
                    if 'TPE1' in audio.tags:
                        artist = str(audio.tags['TPE1'])

            elif isinstance(audio, MP4):
                # 尝试读取标题
                if '\xa9nam' in audio:
                    title = audio['\xa9nam'][0]
                # 尝试读取艺术家
                if '\xa9ART' in audio:
                    artist = audio['\xa9ART'][0]

            elif isinstance(audio, FLAC):
                # FLAC格式
                if 'TITLE' in audio:
                    title = audio['TITLE'][0]
                if 'ARTIST' in audio:
                    artist = audio['ARTIST'][0]

            elif isinstance(audio, (OggVorbis, OggOpus)):
                # OGG格式
                if 'TITLE' in audio:
                    title = audio['TITLE'][0]
                if 'ARTIST' in audio:
                    artist = audio['ARTIST'][0]

            elif isinstance(audio, ASF):
                # ASF/WMA格式
                if 'Title' in audio:
                    title = str(audio['Title'][0])
                if 'Author' in audio:
                    artist = str(audio['Author'][0])

            # 如果没有获取到元数据，则使用原文件名
            if not artist or not title:
                self.log("无法从音频元数据获取信息，保留原文件名")
                return filepath

            # 移除文件名中的非法字符
            safe_artist = self._sanitize_filename(artist)
            safe_title = self._sanitize_filename(title)

            new_filename = f"{safe_title} - {safe_artist}{filepath.suffix}"
            new_filepath = filepath.parent / new_filename

            # 如果文件已存在，添加(1)、(2)等后缀
            counter = 1
            while new_filepath.exists():
                new_filename = f"{safe_title} - {safe_artist} ({counter}){filepath.suffix}"
                new_filepath = filepath.parent / new_filename
                counter += 1

            self.log(f"根据元数据重命名文件: {new_filepath.name}")
            os.rename(filepath, new_filepath)
            return new_filepath

        except Exception as e:
            self.log(f"根据元数据重命名文件时出错: {str(e)}，保留原文件名")
            return filepath

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """移除文件名中的非法字符

        Args:
            filename: 原文件名

        Returns:
            处理后的文件名
        """
        # 移除Windows文件系统中的非法字符
        illegal_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        for char in illegal_chars:
            filename = filename.replace(char, '')
        return filename.strip()
