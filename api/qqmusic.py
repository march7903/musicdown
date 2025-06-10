"""
QQ音乐API统一封装
使用qqmusic-api-python库提供统一的音乐数据接口
"""
import asyncio
import json
from typing import Dict, List, Optional
from pathlib import Path

try:
    from qqmusic_api import search, song, album, songlist, lyric, login
    from qqmusic_api.utils.credential import Credential
    from qqmusic_api.login import (
        QRLoginType, QRCodeLoginEvents, PhoneLoginEvents,
        get_qrcode, check_qrcode, send_authcode, phone_authorize
    )
    QQMUSIC_API_AVAILABLE = True
except ImportError:
    QQMUSIC_API_AVAILABLE = False
    print("警告: qqmusic-api-python 未安装")

from utils.logger import logger


class QQMusicAPI:
    """QQ音乐API统一封装类"""

    def __init__(self):
        if not QQMUSIC_API_AVAILABLE:
            raise ImportError(
                "qqmusic-api-python 库未安装，请先安装: pip install qqmusic-api-python")

        self.credential: Optional[Credential] = None
        self.credential_file = Path("credential.json")
        self._load_credential_basic()

    def _load_credential_basic(self):
        """同步读取凭证（不判断有效期）"""
        if self.credential_file.exists():
            try:
                with open(self.credential_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.credential = Credential.from_cookies_dict(data)
                    logger.info(
                        f"已加载本地登录凭证: {getattr(self.credential, 'musicid', None)}")
            except Exception as e:
                logger.error(f"加载登录凭证失败: {e}")
                self.credential = None

    async def validate_credential(self):
        """异步校验并自动刷新凭证，无法刷新时清理"""
        if not self.credential:
            return False

        try:
            if await self.credential.is_expired():
                logger.warning("凭证已过期，尝试自动刷新...")
                if await self.credential.can_refresh():
                    await self.credential.refresh()
                    self.save_credential(self.credential)
                    logger.info("凭证刷新成功！")
                    return True
                else:
                    logger.warning("凭证无法刷新，已清除")
                    self.credential = None
                    if self.credential_file.exists():
                        self.credential_file.unlink()
                    return False
            else:
                logger.info("凭证有效")
                return True
        except Exception as e:
            logger.error(f"校验凭证时出错: {e}")
            self.credential = None
            if self.credential_file.exists():
                self.credential_file.unlink()
            return False

    async def is_logged_in(self) -> bool:
        """异步判断登录状态，并保证凭证有效"""
        return await self.validate_credential()

    def save_credential(self, credential: Credential):
        """保存登录凭证"""
        self.credential = credential
        try:
            data = credential.as_dict()
            with open(self.credential_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"登录凭证已保存: {credential.musicid}")
        except Exception as e:
            logger.error(f"保存登录凭证失败: {e}")

    def logout(self):
        """退出登录"""
        self.credential = None
        if self.credential_file.exists():
            self.credential_file.unlink()
        logger.info("登录凭证已清除")

    async def search(self, keyword: str, limit: int = 10, page: int = 1) -> Dict:
        """搜索歌曲
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            page: 页码
            
        Returns:
            搜索结果字典
        """
        try:
            result = await search.search_by_type(
                keyword=keyword,
                search_type=search.SearchType.SONG,
                page=page,
                num=limit
            )
            with open("json/search_song_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            return {
                "code": 0,
                "songs": result if isinstance(result, list) else [],
                "total": len(result) if isinstance(result, list) else 0
            }
        except Exception as e:
            logger.error(f"搜索歌曲失败: {e}")
            return {"code": -1, "songs": [], "total": 0, "error": str(e)}

    async def song_detail(self, song_mid: str) -> Dict:
        """获取歌曲详细信息
        
        Args:
            song_mid: 歌曲MID
            
        Returns:
            歌曲详细信息
        """
        try:
            result = await song.get_song_detail(song_mid)
            return {"code": 0, "data": result}
        except Exception as e:
            logger.error(f"获取歌曲详情失败: {e}")
            return {"code": -1, "data": None, "error": str(e)}

    async def song_url(self, song_mid: str, quality: str = "128") -> Dict:
        """获取歌曲下载链接
        
        Args:
            song_mid: 歌曲MID
            quality: 音质 (128/320/flac/ATMOS_51/ATMOS_2/MASTER等)
            
        Returns:
            下载链接信息
        """
        try:
            # 质量映射到SongFileType枚举
            quality_map = {
                'm4a': song.SongFileType.ACC_192,
                '128': song.SongFileType.MP3_128,
                '320': song.SongFileType.MP3_320,
                'flac': song.SongFileType.FLAC,
                'ATMOS_51': song.SongFileType.ATMOS_51,
                'ATMOS_2': song.SongFileType.ATMOS_2,
                'MASTER': song.SongFileType.MASTER,
                'ogg': song.SongFileType.OGG_320
            }

            file_type = quality_map.get(quality, song.SongFileType.MP3_128)
            result = await song.get_song_urls([song_mid], file_type, credential=self.credential)
            with open("json/song_url_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)

            if isinstance(result, dict) and song_mid in result:
                url = result[song_mid]
                return {
                    'code': 0 if url else -1,
                    'url': url
                }
            else:
                return {'code': -1, 'url': ''}
        except Exception as e:
            logger.error(f"获取歌曲URL失败: {e}")
            return {'code': -1, 'url': '', 'error': str(e)}

    async def search_album(self, keyword: str, limit: int = 10, page: int = 1) -> Dict:
        """搜索专辑
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            page: 页码
            
        Returns:
            专辑搜索结果
        """
        try:
            result = await search.search_by_type(
                keyword=keyword,
                search_type=search.SearchType.ALBUM,
                page=page,
                num=limit
            )
            with open("json/search_album_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            return {
                "code": 0,
                "albums": result if isinstance(result, list) else [],
                "total": len(result) if isinstance(result, list) else 0
            }
        except Exception as e:
            logger.error(f"搜索专辑失败: {e}")
            return {"code": -1, "albums": [], "total": 0, "error": str(e)}

    async def album_detail(self, album_mid: str) -> Dict:
        """获取专辑详细信息
        
        Args:
            album_mid: 专辑MID
            
        Returns:
            专辑详细信息和歌曲列表
        """
        try:
            result = await album.get_song(album_mid, num=100, page=1)
            with open("json/album_detail_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            return {
                "code": 0,
                "songs": result if isinstance(result, list) else [],
                "songList": result if isinstance(result, list) else [],
                "total": len(result) if isinstance(result, list) else 0
            }
        except Exception as e:
            logger.error(f"获取专辑详情失败: {e}")
            return {"code": -1, "songs": [], "songList": [], "total": 0, "error": str(e)}

    async def search_playlist(self, keyword: str, limit: int = 10, page: int = 1) -> Dict:
        """搜索歌单
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            page: 页码
            
        Returns:
            歌单搜索结果
        """
        try:
            result = await search.search_by_type(
                keyword=keyword,
                search_type=search.SearchType.SONGLIST,
                page=page,
                num=limit
            )
            with open("json/search_playlist_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            return {
                "code": 0,
                "playlists": result if isinstance(result, list) else [],
                "total": len(result) if isinstance(result, list) else 0
            }
        except Exception as e:
            logger.error(f"搜索歌单失败: {e}")
            return {"code": -1, "playlists": [], "total": 0, "error": str(e)}

    async def playlist_detail(self, playlist_id: int) -> Dict:
        """获取歌单详细信息
        
        Args:
            playlist_id: 歌单ID
            
        Returns:
            歌单详细信息和歌曲列表
        """
        try:
            result = await songlist.get_songlist(playlist_id, dirid=0)
            return {
                "code": 0,
                "songs": result if isinstance(result, list) else [],
                "songList": result if isinstance(result, list) else [],
                "total": len(result) if isinstance(result, list) else 0
            }
        except Exception as e:
            logger.error(f"获取歌单详情失败: {e}")
            return {"code": -1, "songs": [], "songList": [], "total": 0, "error": str(e)}

    async def get_lyrics(self, song_mid: str) -> Dict:
        """获取歌词
        
        Args:
            song_mid: 歌曲MID
            
        Returns:
            歌词信息
        """
        try:
            result = await lyric.get_lyric(song_mid)
            with open("json/lyric_result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            if isinstance(result, dict):
                return {
                    "code": 0,
                    "lyric": result.get("lyric", ""),
                    "trans": result.get("trans", ""),
                    "roma": result.get("roma", "")
                }
            else:
                return {
                    "code": 0,
                    "lyric": str(result) if result else "",
                    "trans": "",
                    "roma": ""
                }
        except Exception as e:
            logger.error(f"获取歌词失败: {e}")
            return {"code": -1, "lyric": "", "trans": "", "roma": "", "error": str(e)}

    # 登录相关方法
    async def login_with_qr(self, login_type: str = "QQ", callback=None) -> tuple:
        """二维码登录

        Args:
            login_type: 登录类型 ("QQ" 或 "WX")
            callback: 回调函数

        Returns:
            (成功状态, 二维码数据, 错误信息)
        """
        try:
            qr_type = QRLoginType.QQ if login_type.upper() == "QQ" else QRLoginType.WX
            qr = await get_qrcode(qr_type)

            # 直接传递二维码字节数据，不保存到文件
            logger.info("二维码已生成，准备显示")

            if callback:
                callback("qr_generated", qr.data)

            # 轮询检查登录状态
            max_attempts = 60  # 最多检查60次，约2分钟
            attempt = 0
            last_status = None

            while attempt < max_attempts:
                try:
                    event, credential = await check_qrcode(qr)

                    if event == QRCodeLoginEvents.DONE:
                        self.save_credential(credential)
                        if callback:
                            callback("login_success", credential)
                        return True, qr.data, ""

                    elif event == QRCodeLoginEvents.TIMEOUT:
                        error_msg = "二维码已过期"
                        logger.error(error_msg)
                        if callback:
                            callback("timeout", error_msg)
                        return False, qr.data, error_msg

                    elif event == QRCodeLoginEvents.REFUSE:
                        error_msg = "用户拒绝登录"
                        logger.error(error_msg)
                        if callback:
                            callback("error", error_msg)
                        return False, qr.data, error_msg

                    elif event == QRCodeLoginEvents.SCAN:
                        if last_status != "scan":
                            logger.info("二维码已扫描，等待手机确认登录")
                            if callback:
                                callback("scanned", "二维码已扫描，请在手机上确认登录")
                            last_status = "scan"
                        await asyncio.sleep(2)

                    elif event == QRCodeLoginEvents.CONF:
                        if last_status != "conf":
                            logger.info("已扫码，等待确认登录")
                            if callback:
                                callback("waiting_confirm", "已扫码，等待手机确认登录")
                            last_status = "conf"
                        await asyncio.sleep(2)

                    else:
                        await asyncio.sleep(1)

                    attempt += 1

                except Exception as e:
                    logger.error(f"检查二维码状态时出错: {e}")
                    await asyncio.sleep(2)
                    attempt += 1

            error_msg = "登录超时，请重试"
            if callback:
                callback("timeout", error_msg)
            return False, qr.data, error_msg

        except Exception as e:
            error_msg = f"二维码登录失败: {e}"
            logger.error(error_msg)
            if callback:
                callback("error", error_msg)
            return False, b"", error_msg

    async def login_with_phone(self, phone: int, country_code: int = 86, callback=None) -> tuple:
        """手机号登录

        Args:
            phone: 手机号
            country_code: 国家代码
            callback: 回调函数

        Returns:
            (成功状态, 错误信息)
        """
        try:
            # 发送验证码
            if callback:
                callback("sending_code", "正在发送验证码...")

            event, info = await send_authcode(phone, country_code)

            if event == PhoneLoginEvents.CAPTCHA:
                error_msg = f"需要验证，访问链接: {info}"
                logger.error(error_msg)
                if callback:
                    callback("captcha_required", error_msg)
                return False, error_msg

            elif event == PhoneLoginEvents.FREQUENCY:
                error_msg = "操作过于频繁，请稍后再试"
                logger.error(error_msg)
                if callback:
                    callback("frequency_limit", error_msg)
                return False, error_msg

            logger.info("验证码已发送")
            if callback:
                callback("code_sent", "验证码已发送，请输入验证码")

            # 这里需要通过回调获取验证码
            if callback:
                auth_code = callback("get_auth_code", "请输入验证码")
                if not auth_code:
                    return False, "未输入验证码"
            else:
                # 命令行环境的备用方案
                auth_code = input("请输入验证码: ").strip()

            # 执行登录
            if callback:
                callback("authorizing", "正在验证...")

            credential = await phone_authorize(phone, int(auth_code), country_code)
            self.save_credential(credential)

            if callback:
                callback("login_success", credential)
            return True, ""

        except Exception as e:
            error_msg = f"手机号登录失败: {e}"
            logger.error(error_msg)
            if callback:
                callback("error", error_msg)
            return False, error_msg

    def get_user_info(self) -> Optional[Dict]:
        """获取用户信息"""
        if self.credential:
            return {
                'musicid': self.credential.musicid,
                'uin': getattr(self.credential, 'uin', ''),
                'logged_in': True
            }
        return {'logged_in': False}
