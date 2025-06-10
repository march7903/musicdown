import asyncio
import json
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QIcon, QTextCursor
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QGridLayout,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QProgressBar, QPushButton,
                             QRadioButton, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, QTextEdit,
                             QMenuBar, QMenu)

from api.qqmusic import QQMusicAPI
from downloader.music_downloader import MusicDownloader
from utils.menum import SearchType
from utils.config import config


class WorkerThread(QThread):
    """工作线程，处理异步任务"""
    update_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)  # 当前进度, 总进度

    def __init__(self, task_type, api=None, downloader=None, params=None):
        super().__init__()
        self.task_type = task_type
        self.api = api
        self.downloader = downloader
        self.params = params or {}

    async def run_task(self):
        try:
            if self.task_type == "search_song":
                result = await self.api.search(
                    self.params["query"],
                    self.params.get("limit", 20),
                    self.params.get("page", 1)
                )
                self.update_signal.emit(
                    {"type": "search_result", "data": result})

            elif self.task_type == "search_album":
                result = await self.api.search_album(
                    self.params["query"],
                    self.params.get("limit", 20),
                    self.params.get("page", 1)
                )
                self.update_signal.emit(
                    {"type": "search_result", "data": result})

            elif self.task_type == "get_album_songs":
                result = await self.api.album_detail(self.params["album_mid"])
                self.update_signal.emit(
                    {"type": "album_songs", "data": result})

            elif self.task_type == "search_playlist":
                result = await self.api.search_playlist(
                    self.params["query"],
                    self.params.get("limit", 20),
                    self.params.get("page", 1)
                )
                self.update_signal.emit(
                    {"type": "search_result", "data": result})

            elif self.task_type == "get_playlist":
                result = await self.api.playlist_detail(self.params["disstid"])
                self.update_signal.emit(
                    {"type": "playlist_songs", "data": result})

            elif self.task_type == "download_song":
                song_info = self.params["song_info"]
                filetype = self.params["filetype"]
                download_dir = self.params.get("download_dir")
                cookie = self.params.get("cookie", "")
                print(f"cookie: {cookie}")
                result = await self.downloader.download_song(song_info, download_dir, filetype, cookie)

                self.update_signal.emit({
                    "type": "download_complete",
                    "data": {
                        "success": result is not None,
                        "path": str(result) if result else None,
                        "song_name": song_info["name"],
                        "singer": song_info["singer"]
                    }
                })

            elif self.task_type == "download_multiple":
                songs = self.params["songs"]
                filetype = self.params["filetype"]
                download_dir = self.params.get("download_dir")
                cookie = self.params.get("cookie", "")
                total = len(songs)

                for i, song_info in enumerate(songs):
                    self.progress_signal.emit(i, total)
                    result = await self.downloader.download_song(song_info, download_dir, filetype, cookie)
                    self.update_signal.emit({
                        "type": "download_progress",
                        "data": {
                            "current": i + 1,
                            "total": total,
                            "success": result is not None,
                            "path": str(result) if result else None,
                            "song_name": song_info["name"],
                            "singer": song_info["singer"]
                        }
                    })

                self.update_signal.emit({"type": "download_all_complete"})

            elif self.task_type == "get_playlist_from_link":
                # 暂时不支持从链接获取歌单功能
                self.update_signal.emit({
                    "type": "playlist_link_result",
                    "data": {"code": -1, "error": "暂不支持从链接获取歌单功能"}
                })

            elif self.task_type == "search_and_download":
                # 先搜索歌曲
                query = f"{self.params['song_name']} {self.params['singer_name']}"
                search_result = await self.api.search(
                    query,
                    1,    # 限制为1个结果
                    1     # 页码
                )

                if not search_result or not search_result.get("songs") or len(search_result["songs"]) == 0:
                    self.update_signal.emit({
                        "type": "download_complete",
                        "data": {
                            "success": False,
                            "path": None,
                            "song_name": self.params["song_name"],
                            "singer": self.params["singer_name"]
                        }
                    })
                    return

                # 下载找到的歌曲
                song_info = search_result["songs"][0]
                filetype = self.params["filetype"]
                download_dir = self.params.get("download_dir")
                cookie = self.params.get("cookie", "")

                result = await self.downloader.download_song(song_info, download_dir, filetype, cookie)

                self.update_signal.emit({
                    "type": "download_complete",
                    "data": {
                        "success": result is not None,
                        "path": str(result) if result else None,
                        "song_name": self.params["song_name"],
                        "singer": self.params["singer_name"]
                    }
                })

            elif self.task_type == "batch_search_and_download":
                songs = self.params["songs"]
                filetype = self.params["filetype"]
                download_dir = self.params.get("download_dir")
                cookie = self.params.get("cookie", "")
                total = len(songs)

                for i, song in enumerate(songs):
                    self.progress_signal.emit(i, total)

                    # 搜索歌曲
                    query = f"{song['name']} {song['artist']}"
                    search_result = await self.api.search(
                        query,
                        1,    # 限制为1个结果
                        1     # 页码
                    )

                    success = False
                    path = None

                    if search_result and search_result.get("songs") and len(search_result["songs"]) > 0:
                        # 下载找到的歌曲
                        song_info = search_result["songs"][0]
                        result = await self.downloader.download_song(song_info, download_dir, filetype, cookie)
                        success = result is not None
                        path = str(result) if result else None

                    self.update_signal.emit({
                        "type": "download_progress",
                        "data": {
                            "current": i + 1,
                            "total": total,
                            "success": success,
                            "path": path,
                            "song_name": song["name"],
                            "singer": song["artist"]
                        }
                    })

                self.update_signal.emit({"type": "download_all_complete"})

            elif self.task_type == "search_playlist_link_songs":
                songs = self.params["songs"]
                detailed_songs = []
                total = len(songs)

                for i, song_str in enumerate(songs):
                    self.progress_signal.emit(i, total)

                    # 解析歌曲字符串：歌曲名 - 歌手名
                    parts = song_str.split(" - ", 1)
                    song_name = parts[0].strip() if len(
                        parts) > 0 else song_str
                    artist_name = parts[1].strip() if len(parts) > 1 else ""

                    # 构建搜索查询
                    query = f"{song_name} {artist_name}"

                    # 搜索歌曲
                    search_result = await self.api.search(
                        query,
                        1,    # 限制为1个结果
                        1     # 页码
                    )

                    # 获取第一个匹配结果
                    song_info = None
                    if search_result and search_result.get("songs") and len(search_result["songs"]) > 0:
                        song_info = search_result["songs"][0]

                    detailed_songs.append(song_info)

                self.update_signal.emit({
                    "type": "playlist_link_songs_details",
                    "data": detailed_songs
                })

            elif self.task_type == "search_playlist_link_songs_one_by_one":
                songs = self.params["songs"]
                total = len(songs)

                # 定义单个歌曲搜索的异步函数
                async def search_single_song(index, song_str):
                    # 解析歌曲字符串：歌曲名 - 歌手名
                    parts = song_str.split(" - ", 1)
                    song_name = parts[0].strip() if len(
                        parts) > 0 else song_str
                    artist_name = parts[1].strip() if len(parts) > 1 else ""

                    # 构建搜索查询
                    query = f"{song_name} {artist_name}"

                    # 搜索歌曲
                    search_result = await self.api.search(
                        query,
                        1,    # 限制为1个结果
                        1     # 页码
                    )

                    # 获取第一个匹配结果
                    song_info = None
                    if search_result and search_result.get("songs") and len(search_result["songs"]) > 0:
                        song_info = search_result["songs"][0]

                    # 发送单首歌曲搜索结果
                    self.update_signal.emit({
                        "type": "single_song_search_result",
                        "index": index,  # 歌曲在列表中的索引
                        "song_info": song_info,  # 歌曲信息
                        "total": total,  # 总数
                        "current": index + 1  # 当前进度（仅用于显示）
                    })
                    return song_info

                # 创建所有搜索任务
                tasks = [search_single_song(i, song_str)
                         for i, song_str in enumerate(songs)]

                # 控制并发数量，防止过多并发请求
                concurrent_limit = 5  # 同时最多5个请求
                completed = 0

                # 分批并发执行搜索任务
                while completed < len(tasks):
                    batch = tasks[completed:completed+concurrent_limit]
                    await asyncio.gather(*batch)
                    completed += len(batch)
                    self.progress_signal.emit(completed, total)

                # 所有搜索完成后发送完成信号
                self.update_signal.emit({
                    "type": "playlist_link_search_complete",
                    "total": total
                })

        except Exception as e:
            self.error_signal.emit(str(e))

    def run(self):
        print(f"Starting new thread for task: {self.task_type}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_task())
        except Exception as e:
            print(f"Error in thread: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 不要关闭事件循环，仅清理它
            loop.run_until_complete(loop.shutdown_asyncgens())
        print(f"Thread completed for task: {self.task_type}")


class QQMusicDownloaderGUI(QMainWindow):
    """QQ音乐下载器GUI"""

    def __init__(self):
        super().__init__()
        self.api = QQMusicAPI()
        self.downloader = MusicDownloader()

        # 设置配置文件路径
        self.config_dir = Path(sys.argv[0]).parent
        self.config_file = self.config_dir / "config.json"

        # 存储搜索结果
        self.search_results = []
        self.album_songs = []
        self.playlist_songs = []

        # 设置下载路径
        self.download_path = str(Path.home() / "Downloads")

        # 默认音质设置
        self._saved_quality = "320"  # 添加默认音质设置

        # 存储当前活动的工作线程
        self.current_worker = None

        # 初始化日志显示区域
        self.log_text = None

        # 加载配置
        self.load_config()

        # 初始化UI，应该放在所有属性初始化之后
        self.initUI()

        # 注册日志处理器
        self.setup_logger()

    def initUI(self):
        """初始化UI"""
        self.setWindowTitle("QQ音乐下载器")
        self.setWindowIcon(QIcon("ui/icon.ico"))
        self.setGeometry(100, 100, 700, 400)

        # 创建菜单栏
        self.create_menu_bar()

        # 主布局
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        # 搜索部分
        search_layout = QHBoxLayout()

        # 搜索类型选择
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["单曲搜索", "专辑搜索", "歌单搜索"])
        search_layout.addWidget(QLabel("搜索类型:"))
        search_layout.addWidget(self.search_type_combo)

        # 搜索框和按钮
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索...")
        self.search_input.returnPressed.connect(self.search)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.search)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)

        main_layout.addLayout(search_layout)

        # 选项卡组件
        self.tabs = QTabWidget()

        # 搜索结果标签页
        self.search_tab = QWidget()
        search_tab_layout = QVBoxLayout(self.search_tab)

        # 搜索结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(
            ["", "歌曲名", "歌手", "专辑", "时长", "操作"])
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.result_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)

        search_tab_layout.addWidget(self.result_table)

        # 批量下载按钮
        batch_download_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all_songs)

        self.batch_download_btn = QPushButton("批量下载选中歌曲")
        self.batch_download_btn.clicked.connect(self.batch_download)

        batch_download_layout.addWidget(self.select_all_btn)
        batch_download_layout.addWidget(self.batch_download_btn)
        batch_download_layout.addStretch()

        search_tab_layout.addLayout(batch_download_layout)

        # 下载设置标签页
        self.settings_tab = QWidget()
        settings_layout = QGridLayout(self.settings_tab)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 添加顶部对齐

        # 下载路径设置
        settings_layout.addWidget(
            QLabel("下载保存路径:"), 0, 0, Qt.AlignmentFlag.AlignTop)
        self.path_input = QLineEdit(self.download_path)
        self.path_input.setReadOnly(True)
        settings_layout.addWidget(
            self.path_input, 0, 1, Qt.AlignmentFlag.AlignTop)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_path)
        settings_layout.addWidget(
            self.browse_btn, 0, 2, Qt.AlignmentFlag.AlignTop)

        # 添加Cookie设置
        settings_layout.addWidget(
            QLabel("QQ音乐Cookie:"), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("输入QQ音乐Cookie以下载高品质音乐...")
        # 设置保存的cookie
        if hasattr(self, '_saved_cookie'):
            self.cookie_input.setText(self._saved_cookie)
            del self._saved_cookie
        settings_layout.addWidget(
            self.cookie_input, 2, 1, 1, 2, Qt.AlignmentFlag.AlignTop)

        # 添加cookie值变化的事件处理
        self.cookie_input.textChanged.connect(self.save_config)

        # 音质选择
        settings_layout.addWidget(
            QLabel("下载音质:"), 1, 0, Qt.AlignmentFlag.AlignTop)
        quality_layout = QHBoxLayout()
        quality_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.quality_m4a = QRadioButton("M4A")
        self.quality_128 = QRadioButton("MP3 128kbps")
        self.quality_320 = QRadioButton("MP3 320kbps")
        self.quality_flac = QRadioButton("FLAC")
        self.quality_ATMOS_51 = QRadioButton("臻品音质2.0")
        self.quality_ATMOS_2 = QRadioButton("臻品全景声2.0")
        self.quality_MASTER = QRadioButton("臻品母带2.0")

        # 根据保存的设置选择音质
        quality_map = {
            "m4a": self.quality_m4a,
            "128": self.quality_128,
            "320": self.quality_320,
            "flac": self.quality_flac,
            "ATMOS_51": self.quality_ATMOS_51,
            "ATMOS_2": self.quality_ATMOS_2,
            "MASTER": self.quality_MASTER,
        }
        selected_quality = quality_map.get(
            self._saved_quality, self.quality_320)
        selected_quality.setChecked(True)

        # 添加音质变化的事件处理
        for radio in [
            self.quality_m4a,
            self.quality_128,
            self.quality_320,
            self.quality_flac,
            self.quality_ATMOS_51,
            self.quality_ATMOS_2,
            self.quality_MASTER,
        ]:
            radio.toggled.connect(self.save_config)

        quality_layout.addWidget(self.quality_m4a)
        quality_layout.addWidget(self.quality_128)
        quality_layout.addWidget(self.quality_320)
        quality_layout.addWidget(self.quality_flac)
        quality_layout.addWidget(self.quality_ATMOS_51)
        quality_layout.addWidget(self.quality_ATMOS_2)
        quality_layout.addWidget(self.quality_MASTER)
        quality_layout.addStretch()

        settings_layout.addLayout(quality_layout, 1, 1, 1, 2)

        # 下载记录标签
        self.download_tab = QWidget()
        download_layout = QVBoxLayout(self.download_tab)

        self.download_table = QTableWidget()
        self.download_table.setColumnCount(4)
        self.download_table.setHorizontalHeaderLabels(
            ["歌曲名", "歌手", "状态", "保存路径"])
        self.download_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.download_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self.download_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)

        download_layout.addWidget(self.download_table)

        # 下载进度
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("总体进度:"))
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        download_layout.addLayout(progress_layout)

        # 添加标签页到选项卡
        self.tabs.addTab(self.search_tab, "搜索结果")
        self.tabs.addTab(self.settings_tab, "下载设置")
        self.tabs.addTab(self.download_tab, "下载记录")

        # 添加歌单链接下载选项卡
        self.playlist_link_tab = QWidget()
        playlist_link_layout = QVBoxLayout(self.playlist_link_tab)

        # 歌单链接输入区域
        link_input_layout = QHBoxLayout()
        link_input_layout.addWidget(QLabel("歌单链接:"))
        self.playlist_link_input = QLineEdit()
        self.playlist_link_input.setPlaceholderText("输入QQ音乐歌单链接...")
        self.playlist_link_input.returnPressed.connect(
            self.get_playlist_from_link)
        link_input_layout.addWidget(self.playlist_link_input)

        self.get_playlist_btn = QPushButton("获取歌单")
        self.get_playlist_btn.clicked.connect(self.get_playlist_from_link)
        link_input_layout.addWidget(self.get_playlist_btn)

        playlist_link_layout.addLayout(link_input_layout)

        # 歌单信息区域
        self.playlist_info_label = QLabel("歌单信息: ")
        playlist_link_layout.addWidget(self.playlist_info_label)

        # 歌单歌曲列表
        self.playlist_link_table = QTableWidget()
        self.playlist_link_table.setColumnCount(6)
        self.playlist_link_table.setHorizontalHeaderLabels(
            ["", "歌曲名", "歌手", "专辑", "时长", "操作"])
        self.playlist_link_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.playlist_link_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.playlist_link_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.playlist_link_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)

        playlist_link_layout.addWidget(self.playlist_link_table)

        # 批量下载按钮
        batch_download_layout = QHBoxLayout()
        self.select_all_link_btn = QPushButton("全选")
        self.select_all_link_btn.clicked.connect(
            self.select_all_playlist_link_songs)

        self.batch_download_link_btn = QPushButton("批量下载选中歌曲")
        self.batch_download_link_btn.clicked.connect(
            self.batch_download_from_link)

        batch_download_layout.addWidget(self.select_all_link_btn)
        batch_download_layout.addWidget(self.batch_download_link_btn)
        batch_download_layout.addStretch()

        playlist_link_layout.addLayout(batch_download_layout)

        self.tabs.addTab(self.playlist_link_tab, "歌单链接下载")

        # 添加新的日志选项卡
        self.log_tab = QWidget()
        log_layout = QVBoxLayout(self.log_tab)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_text.setStyleSheet("font-family: Courier, monospace;")

        log_layout.addWidget(self.log_text)

        # 清除日志按钮
        clear_log_btn = QPushButton("清除日志")
        clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_log_btn)

        self.tabs.addTab(self.log_tab, "下载日志")

        main_layout.addWidget(self.tabs)

        self.setCentralWidget(main_widget)

    def setup_logger(self):
        """设置日志处理器，将日志消息发送到UI"""

        class UILogHandler(QObject, logging.Handler):
            # 在类级别定义信号
            log_signal = pyqtSignal(str)

            def __init__(self, ui_instance):
                QObject.__init__(self)
                logging.Handler.__init__(self)
                self.ui = ui_instance
                # 连接信号到更新函数
                self.log_signal.connect(
                    self.ui.update_log, Qt.ConnectionType.QueuedConnection
                )

            def emit(self, record):
                msg = self.format(record)
                # 使用信号发送日志消息
                self.log_signal.emit(msg)

        # 创建并添加UI日志处理器
        ui_handler = UILogHandler(self)
        formatter = logging.Formatter(
            '[%(levelname)s] %(asctime)s - %(message)s')
        ui_handler.setFormatter(formatter)

        # 添加到logger
        from utils.logger import logger
        logger.add_handler(ui_handler)

    def update_log(self, message):
        """更新日志显示区域"""
        if self.log_text:
            self.log_text.append(message)
            # 自动滚动到底部
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)

    def clear_log(self):
        """清除日志显示"""
        if self.log_text:
            self.log_text.clear()

    def get_selected_quality(self) -> str:
        """获取选择的音质"""
        if self.quality_m4a.isChecked():
            return "m4a"
        elif self.quality_128.isChecked():
            return "128"
        elif self.quality_320.isChecked():
            return "320"
        elif self.quality_flac.isChecked():
            return "flac"
        elif self.quality_ATMOS_51.isChecked():
            return "ATMOS_51"
        elif self.quality_ATMOS_2.isChecked():
            return "ATMOS_2"
        elif self.quality_MASTER.isChecked():
            return "MASTER"
        return "320"  # 默认

    @pyqtSlot()
    def search(self):
        """执行搜索"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return

        search_type_index = self.search_type_combo.currentIndex()
        self.result_table.setRowCount(0)  # 清空表格

        # 每次都创建新的工作线程
        if search_type_index == 0:  # 单曲搜索
            worker = WorkerThread(
                "search_song", api=self.api, params={"query": query})
        elif search_type_index == 1:  # 专辑搜索
            worker = WorkerThread(
                "search_album", api=self.api, params={"query": query})
        elif search_type_index == 2:  # 歌单搜索
            worker = WorkerThread(
                "search_playlist", api=self.api, params={"query": query})

        # 连接信号
        worker.update_signal.connect(self.handle_worker_update)
        worker.error_signal.connect(self.handle_worker_error)

        # 保存引用以防止垃圾回收
        self.current_worker = worker
        worker.start()

    @pyqtSlot(dict)
    def handle_worker_update(self, data):
        """处理工作线程的更新信号"""
        update_type = data["type"]

        # 特殊处理下载完成的情况，因为它没有data字段
        if update_type == "download_all_complete":
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "下载完成", "所有选中的歌曲已下载完成！")
            return

        update_data = data["data"]

        if update_type == "search_result":
            self.display_search_results(update_data)

        elif update_type == "album_songs":
            self.album_songs = update_data["songList"]
            self.display_album_songs(update_data)

        elif update_type == "playlist_songs":
            self.playlist_songs = update_data["songs"]
            self.display_playlist_songs(update_data)

        elif update_type == "download_complete":
            self.update_download_record(update_data)

        elif update_type == "download_progress":
            self.update_download_progress(update_data)

    @pyqtSlot(str)
    def handle_worker_error(self, error_msg):
        """处理工作线程的错误信号"""
        QMessageBox.critical(self, "错误", f"发生错误: {error_msg}")

    @pyqtSlot(int, int)
    def handle_progress_update(self, current, total):
        """处理下载进度更新"""
        progress = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)

    def display_search_results(self, result):
        """显示搜索结果"""
        if self.search_type_combo.currentIndex() == 0:  # 单曲
            self.search_results = result["songs"]

            self.result_table.setColumnCount(6)
            self.result_table.setHorizontalHeaderLabels(
                ["", "歌曲名", "歌手", "专辑", "时长", "操作"])

            self.result_table.setRowCount(len(self.search_results))
            for i, song in enumerate(self.search_results):
                # 复选框（用于批量选择）
                checkbox = QTableWidgetItem()
                checkbox.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                checkbox.setCheckState(Qt.CheckState.Unchecked)
                self.result_table.setItem(i, 0, checkbox)

                # 歌曲信息
                self.result_table.setItem(i, 1, QTableWidgetItem(song["name"]))
                self.result_table.setItem(i, 2, QTableWidgetItem(
                    ", ".join([s["name"] for s in song["singer"]])))
                self.result_table.setItem(
                    i, 3, QTableWidgetItem(song["album"]["name"]))

                # 时长
                duration = song.get("interval", 0)
                minutes, seconds = divmod(duration, 60)
                self.result_table.setItem(
                    i, 4, QTableWidgetItem(f"{minutes:02d}:{seconds:02d}"))

                # 下载按钮
                download_btn = QPushButton("下载")
                download_btn.clicked.connect(lambda checked, song_index=i: self.download_song(
                    self.search_results[song_index]))
                self.result_table.setCellWidget(i, 5, download_btn)

        elif self.search_type_combo.currentIndex() == 1:  # 专辑
            self.search_results = result["albums"]
            self.result_table.setColumnCount(4)
            self.result_table.setHorizontalHeaderLabels(
                ["专辑名", "歌手", "发行时间", "操作"])

            self.result_table.setRowCount(len(self.search_results))
            for i, album in enumerate(self.search_results):
                # 兼容新旧API的字段名
                album_name = album.get("albumName") or album.get(
                    "name") or album.get("album_name") or "未知专辑"
                singer_name = album.get("singerName") or album.get(
                    "singer_name") or "未知歌手"
                if isinstance(album.get("singer"), list) and album["singer"]:
                    singer_name = ", ".join([s.get("name", s) if isinstance(
                        s, dict) else str(s) for s in album["singer"]])
                elif isinstance(album.get("singer"), dict):
                    singer_name = album["singer"].get("name", "未知歌手")

                public_time = album.get("publicTime") or album.get(
                    "public_time") or album.get("time") or ""
                album_mid = album.get("albumMID") or album.get(
                    "album_mid") or album.get("mid") or ""

                self.result_table.setItem(i, 0, QTableWidgetItem(album_name))
                self.result_table.setItem(i, 1, QTableWidgetItem(singer_name))
                self.result_table.setItem(i, 2, QTableWidgetItem(public_time))

                view_btn = QPushButton("查看歌曲")
                view_btn.clicked.connect(
                    lambda checked, album_mid=album_mid: self.get_album_songs(album_mid))
                self.result_table.setCellWidget(i, 3, view_btn)

        elif self.search_type_combo.currentIndex() == 2:  # 歌单
            self.search_results = result["playlists"]
            self.result_table.setColumnCount(4)
            self.result_table.setHorizontalHeaderLabels(
                ["歌单名", "创建者", "歌曲数量", "操作"])

            self.result_table.setRowCount(len(self.search_results))
            for i, playlist in enumerate(self.search_results):
                # 兼容新旧API的字段名
                playlist_name = playlist.get("dissname") or playlist.get(
                    "name") or playlist.get("title") or "未知歌单"

                # 处理创建者信息
                creator_name = "未知创建者"
                if playlist.get("creator"):
                    if isinstance(playlist["creator"], dict):
                        creator_name = playlist["creator"].get("name", "未知创建者")
                    else:
                        creator_name = str(playlist["creator"])
                elif playlist.get("creator_name"):
                    creator_name = playlist["creator_name"]

                # 处理歌曲数量
                song_count = playlist.get("song_count") or playlist.get(
                    "songnum") or playlist.get("total") or 0

                # 处理歌单ID
                playlist_id = playlist.get("dissid") or playlist.get(
                    "id") or playlist.get("disstid") or 0

                self.result_table.setItem(
                    i, 0, QTableWidgetItem(playlist_name))
                self.result_table.setItem(i, 1, QTableWidgetItem(creator_name))
                self.result_table.setItem(
                    i, 2, QTableWidgetItem(str(song_count)))

                view_btn = QPushButton("查看歌曲")
                view_btn.clicked.connect(
                    lambda checked, disstid=int(playlist_id): self.get_playlist(disstid))
                self.result_table.setCellWidget(i, 3, view_btn)

    def get_album_songs(self, album_mid):
        """获取专辑歌曲"""
        self.current_worker = WorkerThread("get_album_songs", api=self.api, params={
            "album_mid": album_mid})
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.start()

    def display_album_songs(self, album_data):
        """显示专辑歌曲"""
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(
            ["", "歌曲名", "歌手", "专辑", "时长", "操作"])

        # 修正: 从songList获取歌曲列表而非songs
        songs = album_data["songList"]
        self.result_table.setRowCount(len(songs))

        # 获取专辑名称 (从当前显示的专辑列表或album_data中)
        album_name = "未知专辑"
        for album in self.search_results:
            if album.get("albumMID") == album_data.get("albumMid"):
                album_name = album.get("albumName", "未知专辑")
                break

        # 添加下载专辑所有歌曲的按钮
        album_download_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all_songs)

        # 添加批量下载选中歌曲按钮
        self.batch_download_btn = QPushButton("批量下载选中歌曲")
        self.batch_download_btn.clicked.connect(self.batch_download)

        self.download_album_btn = QPushButton("下载专辑所有歌曲")
        self.download_album_btn.clicked.connect(
            lambda: self.batch_download(songs))

        album_download_layout.addWidget(self.select_all_btn)
        album_download_layout.addWidget(self.batch_download_btn)
        album_download_layout.addWidget(self.download_album_btn)
        album_download_layout.addStretch()

        # 在显示歌曲列表前添加下载专辑按钮
        layout = self.search_tab.layout()
        if layout.count() > 1:
            # 移除原有的批量下载布局
            old_layout = layout.itemAt(1).layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()

            # 删除旧布局
            layout.removeItem(old_layout)

        # 添加新布局
        layout.addLayout(album_download_layout)

        # 执行原有的歌曲列表填充代码
        for i, song in enumerate(songs):
            # 复选框
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                              Qt.ItemFlag.ItemIsEnabled)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.result_table.setItem(i, 0, checkbox)

            # 歌曲信息
            self.result_table.setItem(i, 1, QTableWidgetItem(song["name"]))
            self.result_table.setItem(i, 2, QTableWidgetItem(
                ", ".join([s["name"] for s in song["singer"]])))
            self.result_table.setItem(i, 3, QTableWidgetItem(album_name))

            # 时长
            duration = song.get("interval", 0)
            minutes, seconds = divmod(duration, 60)
            self.result_table.setItem(
                i, 4, QTableWidgetItem(f"{minutes:02d}:{seconds:02d}"))

            # 下载按钮
            download_btn = QPushButton("下载")
            download_btn.clicked.connect(
                lambda checked, song_index=i: self.download_song(songs[song_index]))
            self.result_table.setCellWidget(i, 5, download_btn)

    def get_playlist(self, disstid: int):
        """获取歌单歌曲"""
        self.current_worker = WorkerThread(
            "get_playlist", api=self.api, params={"disstid": disstid})
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.start()

    def display_playlist_songs(self, playlist_data):
        """显示歌单歌曲"""
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(
            ["", "歌曲名", "歌手", "专辑", "时长", "操作"])

        songs = playlist_data["songs"]
        self.result_table.setRowCount(len(songs))

        for i, song in enumerate(songs):
            # 复选框
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                              Qt.ItemFlag.ItemIsEnabled)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.result_table.setItem(i, 0, checkbox)

            # 歌曲信息
            self.result_table.setItem(i, 1, QTableWidgetItem(song["name"]))
            self.result_table.setItem(i, 2, QTableWidgetItem(
                ", ".join([s["name"] for s in song["singer"]])))
            self.result_table.setItem(
                i, 3, QTableWidgetItem(song["album"]["name"]))

            # 时长
            duration = song.get("interval", 0)
            minutes, seconds = divmod(duration, 60)
            self.result_table.setItem(
                i, 4, QTableWidgetItem(f"{minutes:02d}:{seconds:02d}"))

            # 下载按钮
            download_btn = QPushButton("下载")
            download_btn.clicked.connect(
                lambda checked, song_index=i: self.download_song(songs[song_index]))
            self.result_table.setCellWidget(i, 5, download_btn)

    def download_song(self, song_info):
        """下载单首歌曲"""
        filetype = self.get_selected_quality()
        # 只有当用户输入了cookie时才使用用户的cookie
        cookie = self.cookie_input.text().strip() or None

        # 使用用户设置的下载路径
        download_dir = Path(self.download_path)

        # 切换到下载记录标签页
        self.tabs.setCurrentIndex(2)

        # 添加下载记录
        row = self.download_table.rowCount()
        self.download_table.setRowCount(row + 1)

        self.download_table.setItem(
            row, 0, QTableWidgetItem(song_info["name"]))
        self.download_table.setItem(row, 1, QTableWidgetItem(
            ", ".join([s["name"] for s in song_info["singer"]])))
        self.download_table.setItem(row, 2, QTableWidgetItem("正在下载..."))
        self.download_table.setItem(row, 3, QTableWidgetItem(""))

        # 启动下载线程
        self.current_worker = WorkerThread(
            "download_song",
            downloader=self.downloader,
            params={
                "song_info": song_info,
                "filetype": filetype,
                "download_dir": download_dir,
                "cookie": cookie  # 如果是None，会使用默认cookie
            }
        )
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.start()

    def select_all_songs(self):
        """全选/取消全选歌曲"""
        if self.result_table.rowCount() == 0:
            return

        # 检查当前是否已经全选
        all_checked = True
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item and item.checkState() != Qt.CheckState.Checked:
                all_checked = False
                break

        # 设置新的状态
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked

        # 更新所有复选框状态
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                item.setCheckState(new_state)

        # 刷新表格视图
        self.result_table.update()

    def batch_download(self, songs=None):
        """批量下载选中的歌曲或指定的歌曲列表"""
        selected_songs = []
        # 只有当用户输入了cookie时才使用用户的cookie
        cookie = self.cookie_input.text().strip() or None

        # 获取表格中当前显示的歌曲
        if songs:
            # 如果提供了歌曲列表，直接使用
            selected_songs = songs
        else:
            # 否则，按原来的逻辑查找选中的歌曲
            current_songs = []
            search_type = self.search_type_combo.currentIndex()

            if search_type == 0:  # 单曲搜索
                current_songs = self.search_results
            elif search_type == 1 and self.album_songs:  # 专辑歌曲
                current_songs = self.album_songs
            elif search_type == 2 and self.playlist_songs:  # 歌单歌曲
                current_songs = self.playlist_songs

            # 收集选中的歌曲
            for row in range(self.result_table.rowCount()):
                item = self.result_table.item(row, 0)
                if item and item.checkState() == Qt.CheckState.Checked and row < len(current_songs):
                    selected_songs.append(current_songs[row])

        if not selected_songs:
            QMessageBox.warning(self, "提示", "请选择要下载的歌曲")
            return

        # 切换到下载记录标签页
        self.tabs.setCurrentIndex(2)

        # 重置进度条
        self.progress_bar.setValue(0)

        # 添加下载记录
        start_row = self.download_table.rowCount()
        self.download_table.setRowCount(start_row + len(selected_songs))

        for i, song in enumerate(selected_songs):
            row = start_row + i
            self.download_table.setItem(row, 0, QTableWidgetItem(song["name"]))
            self.download_table.setItem(row, 1, QTableWidgetItem(
                ", ".join([s["name"] for s in song["singer"]])))
            self.download_table.setItem(row, 2, QTableWidgetItem("等待下载..."))
            self.download_table.setItem(row, 3, QTableWidgetItem(""))

        # 使用用户设置的下载路径
        download_dir = Path(self.download_path)

        # 启动批量下载线程
        filetype = self.get_selected_quality()
        self.current_worker = WorkerThread(
            "download_multiple",
            downloader=self.downloader,
            params={
                "songs": selected_songs,
                "filetype": filetype,
                "download_dir": download_dir,
                "cookie": cookie  # 如果是None，会使用默认cookie
            }
        )
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.progress_signal.connect(
            self.handle_progress_update)
        self.current_worker.start()

    def update_download_record(self, data):
        """更新下载记录"""
        for row in range(self.download_table.rowCount()):
            song_name_item = self.download_table.item(row, 0)
            singer_item = self.download_table.item(row, 1)
            status_item = self.download_table.item(row, 2)

            if (song_name_item and song_name_item.text() == data["song_name"] and
                    singer_item and status_item and status_item.text() in ["正在下载...", "等待下载..."]):

                # 更新状态和路径
                if data["success"]:
                    self.download_table.setItem(
                        row, 2, QTableWidgetItem("下载成功"))
                    self.download_table.setItem(
                        row, 3, QTableWidgetItem(data["path"]))
                else:
                    self.download_table.setItem(
                        row, 2, QTableWidgetItem("下载失败"))

                break

    def update_download_progress(self, data):
        """更新批量下载进度"""
        # 更新进度条
        progress = int(data["current"] / data["total"] * 100)
        self.progress_bar.setValue(progress)

        # 更新下载记录
        for row in range(self.download_table.rowCount()):
            song_name_item = self.download_table.item(row, 0)
            singer_item = self.download_table.item(row, 1)
            status_item = self.download_table.item(row, 2)

            if (song_name_item and song_name_item.text() == data["song_name"] and
                    singer_item and status_item and status_item.text() == "等待下载..."):

                # 更新状态和路径
                if data["success"]:
                    self.download_table.setItem(
                        row, 2, QTableWidgetItem("下载成功"))
                    self.download_table.setItem(
                        row, 3, QTableWidgetItem(data["path"]))
                else:
                    self.download_table.setItem(
                        row, 2, QTableWidgetItem("下载失败"))

                break

    def browse_path(self):
        """浏览并选择下载保存路径"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择下载保存位置", self.download_path)
        if dir_path:
            self.download_path = dir_path
            self.path_input.setText(dir_path)
            self.save_config()  # 保存配置

    def load_config(self):
        """加载配置文件"""
        try:
            # 确保配置目录存在
            self.config_dir.mkdir(parents=True, exist_ok=True)

            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.loads(f.read())
                    # 只读取需要的配置，不影响其他配置
                    self.download_path = config.get(
                        'download_path', str(Path.home() / "Downloads"))
                    saved_cookie = config.get('cookie', '')
                    self._saved_quality = config.get('quality', '320')

                    if hasattr(self, 'cookie_input'):  # 如果UI已经初始化
                        self.cookie_input.setText(saved_cookie)
                    else:  # 如果UI还没初始化，保存cookie以供后续使用
                        self._saved_cookie = saved_cookie
        except Exception as e:
            print(f"加载配置文件失败: {e}")

    def save_config(self):
        """保存配置文件"""
        try:
            # 首先读取现有配置
            existing_config = {}
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    existing_config = json.loads(f.read())

            # 更新需要保存的配置项
            existing_config.update({
                'download_path': self.download_path,
                'cookie': self.cookie_input.text().strip(),
                'quality': self.get_selected_quality()
            })

            # 保存完整配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")

    async def search_song_for_download(self, song_name, singer_name):
        """搜索单首歌曲用于下载"""
        query = f"{song_name} {singer_name}"
        result = await self.api.search(
            query,
            1,    # 限制为1个结果
            1     # 页码
        )
        if result and result.get("songs") and len(result["songs"]) > 0:
            return result["songs"][0]
        return None

    def get_playlist_from_link(self):
        """从链接获取歌单"""
        link = self.playlist_link_input.text().strip()
        if not link:
            QMessageBox.warning(self, "提示", "请输入歌单链接")
            return

        # 启动线程获取歌单
        self.current_worker = WorkerThread(
            "get_playlist_from_link",
            api=self.api,
            params={"url": link}
        )
        self.current_worker.update_signal.connect(
            self.handle_playlist_link_result)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.start()

    @pyqtSlot(dict)
    def handle_playlist_link_result(self, data):
        """处理歌单链接获取结果"""
        if data["type"] != "playlist_link_result":
            return

        playlist_data = data["data"]
        if playlist_data["code"] != 1:
            QMessageBox.warning(
                self, "错误", f"获取歌单失败: {playlist_data.get('error', '未知错误')}")
            return

        # 更新歌单信息标签
        playlist_name = playlist_data["data"]["name"]
        songs_count = playlist_data["data"]["songs_count"]
        self.playlist_info_label.setText(
            f"歌单信息: {playlist_name} (共{songs_count}首歌曲)")

        # 保存原始歌曲列表
        self.playlist_link_original_songs = playlist_data["data"]["songs"]

        # 启动搜索获取详细信息
        self.search_playlist_songs_details()

    def search_playlist_songs_details(self):
        """搜索歌单中的歌曲详细信息"""
        if not hasattr(self, 'playlist_link_original_songs') or not self.playlist_link_original_songs:
            return

        # 清空并准备表格
        self.playlist_link_table.clearContents()
        self.playlist_link_table.setRowCount(
            len(self.playlist_link_original_songs))

        # 初始化歌单歌曲详细信息存储
        self.playlist_link_songs = [None] * \
            len(self.playlist_link_original_songs)

        # 设置所有行为"获取详细信息中..."状态
        for i in range(len(self.playlist_link_original_songs)):
            # 在第一个单元格显示搜索状态
            status_item = QTableWidgetItem("获取详细信息中...")
            status_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.playlist_link_table.setItem(i, 1, status_item)
            self.playlist_link_table.setSpan(i, 1, 1, 4)  # 横向合并单元格

        # 禁用获取歌单按钮
        self.get_playlist_btn.setEnabled(False)

        # 启动批量搜索线程
        self.current_worker = WorkerThread(
            "search_playlist_link_songs_one_by_one",
            api=self.api,
            params={
                "songs": self.playlist_link_original_songs
            }
        )
        self.current_worker.update_signal.connect(
            self.handle_single_song_search_result)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.progress_signal.connect(
            self.handle_progress_update)
        self.current_worker.start()

    @pyqtSlot(dict)
    def handle_single_song_search_result(self, data):
        """处理单首歌曲搜索结果"""
        if data["type"] != "single_song_search_result":
            return

        index = data["index"]
        song_info = data["song_info"]
        total_count = data["total"]

        # 保存搜索结果到列表中
        self.playlist_link_songs[index] = song_info

        # 由于是并发执行，不再使用current_count作为进度
        # 而是使用已完成的搜索数量计算进度
        completed_count = sum(
            1 for s in self.playlist_link_songs if s is not None)
        self.progress_bar.setValue(int(completed_count / total_count * 100))

        # 移除行合并
        self.playlist_link_table.setSpan(index, 1, 1, 1)

        if song_info:
            # 复选框
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                              Qt.ItemFlag.ItemIsEnabled)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.playlist_link_table.setItem(index, 0, checkbox)

            # 歌曲信息
            self.playlist_link_table.setItem(
                index, 1, QTableWidgetItem(song_info["name"]))
            self.playlist_link_table.setItem(index, 2, QTableWidgetItem(
                ", ".join([s["name"] for s in song_info["singer"]])))
            self.playlist_link_table.setItem(
                index, 3, QTableWidgetItem(song_info["album"]["name"]))

            # 时长
            duration = song_info.get("interval", 0)
            minutes, seconds = divmod(duration, 60)
            self.playlist_link_table.setItem(
                index, 4, QTableWidgetItem(f"{minutes:02d}:{seconds:02d}"))

            # 下载按钮
            download_btn = QPushButton("下载")
            download_btn.clicked.connect(
                lambda checked, song_index=index: self.download_playlist_link_song(song_index))
            self.playlist_link_table.setCellWidget(index, 5, download_btn)
        else:
            # 搜索失败时显示"未找到"
            self.playlist_link_table.setItem(index, 1, QTableWidgetItem("未找到"))

        # 如果所有歌曲都已搜索完成，启用获取歌单按钮
        if completed_count == total_count:
            self.get_playlist_btn.setEnabled(True)

    def download_playlist_link_song(self, song_index):
        """下载单首歌曲（从歌单链接）- 使用已搜索到的详细信息"""
        if not hasattr(self, 'playlist_link_songs') or song_index >= len(self.playlist_link_songs):
            return

        song_info = self.playlist_link_songs[song_index]
        if not song_info:
            QMessageBox.warning(self, "提示", "无法下载，搜索失败")
            return

        filetype = self.get_selected_quality()
        cookie = self.cookie_input.text().strip() or None
        download_dir = Path(self.download_path)

        # 切换到下载记录标签页
        self.tabs.setCurrentIndex(2)

        # 添加下载记录
        row = self.download_table.rowCount()
        self.download_table.setRowCount(row + 1)

        self.download_table.setItem(
            row, 0, QTableWidgetItem(song_info["name"]))
        self.download_table.setItem(row, 1, QTableWidgetItem(
            ", ".join([s["name"] for s in song_info["singer"]])))
        self.download_table.setItem(row, 2, QTableWidgetItem("正在下载..."))
        self.download_table.setItem(row, 3, QTableWidgetItem(""))

        # 启动下载线程
        self.current_worker = WorkerThread(
            "download_song",
            downloader=self.downloader,
            params={
                "song_info": song_info,
                "filetype": filetype,
                "download_dir": download_dir,
                "cookie": cookie
            }
        )
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.start()

    def batch_download_from_link(self):
        """批量下载选中的歌曲（从歌单链接）"""
        if not hasattr(self, 'playlist_link_songs'):
            QMessageBox.warning(self, "提示", "请先获取歌单")
            return

        selected_songs = []
        for row in range(self.playlist_link_table.rowCount()):
            item = self.playlist_link_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                song_info = self.playlist_link_songs[row]
                if song_info:  # 确保搜索成功
                    selected_songs.append(song_info)

        if not selected_songs:
            QMessageBox.warning(self, "提示", "请选择要下载的歌曲")
            return

        # 切换到下载记录标签页
        self.tabs.setCurrentIndex(2)

        # 重置进度条
        self.progress_bar.setValue(0)

        # 添加下载记录
        start_row = self.download_table.rowCount()
        self.download_table.setRowCount(start_row + len(selected_songs))

        for i, song in enumerate(selected_songs):
            row = start_row + i
            self.download_table.setItem(row, 0, QTableWidgetItem(song["name"]))
            self.download_table.setItem(row, 1, QTableWidgetItem(
                ", ".join([s["name"] for s in song["singer"]])))
            self.download_table.setItem(row, 2, QTableWidgetItem("等待下载..."))
            self.download_table.setItem(row, 3, QTableWidgetItem(""))

        # 启动批量下载线程
        filetype = self.get_selected_quality()
        cookie = self.cookie_input.text().strip() or None
        download_dir = Path(self.download_path)

        self.current_worker = WorkerThread(
            "download_multiple",
            downloader=self.downloader,
            params={
                "songs": selected_songs,
                "filetype": filetype,
                "download_dir": download_dir,
                "cookie": cookie
            }
        )
        self.current_worker.update_signal.connect(self.handle_worker_update)
        self.current_worker.error_signal.connect(self.handle_worker_error)
        self.current_worker.progress_signal.connect(
            self.handle_progress_update)
        self.current_worker.start()

    def select_all_playlist_link_songs(self):
        """全选/取消全选歌单链接中的歌曲"""
        if self.playlist_link_table.rowCount() == 0:
            return

        # 检查当前是否已经全选
        all_checked = True
        for row in range(self.playlist_link_table.rowCount()):
            item = self.playlist_link_table.item(row, 0)
            if item and item.checkState() != Qt.CheckState.Checked:
                all_checked = False
                break

        # 设置新的状态
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked

        # 更新所有复选框状态
        for row in range(self.playlist_link_table.rowCount()):
            item = self.playlist_link_table.item(row, 0)
            if item:
                item.setCheckState(new_state)

        # 刷新表格视图
        self.playlist_link_table.update()

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 账户菜单
        account_menu = menubar.addMenu('账户')

        # 登录动作
        login_action = account_menu.addAction('登录')
        login_action.triggered.connect(self.show_login_dialog)

        # 登出动作
        logout_action = account_menu.addAction('登出')
        logout_action.triggered.connect(self.logout)

        # 用户信息动作
        user_info_action = account_menu.addAction('用户信息')
        user_info_action.triggered.connect(self.show_user_info)

        account_menu.addSeparator()

        # API设置动作
        api_settings_action = account_menu.addAction('API设置')
        api_settings_action.triggered.connect(self.show_api_settings)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助')

        about_action = help_menu.addAction('关于')
        about_action.triggered.connect(self.show_about)

        # 更新菜单状态
        self.update_menu_status()

    def update_menu_status(self):
        """更新菜单状态"""
        # 检查是否支持登录功能
        has_login_support = hasattr(self.api, 'is_logged_in')

        # 这里可以根据登录状态更新菜单项的可用性
        if has_login_support:
            try:
                is_logged_in = self.api.is_logged_in()
                # 可以根据登录状态启用/禁用相关菜单项
                print(f"登录状态: {'已登录' if is_logged_in else '未登录'}")
            except Exception as e:
                print(f"检查登录状态时出错: {e}")
                is_logged_in = False

    def show_login_dialog(self):
        """显示登录对话框"""
        try:
            from ui.login_dialog import LoginDialog

            # 检查是否支持登录功能
            if not hasattr(self.api, 'login_with_qr'):
                QMessageBox.information(
                    self, "提示",
                    "当前API不支持登录功能。\n请在API设置中启用新版API。"
                )
                return

            dialog = LoginDialog(self.api, self)
            if dialog.exec() == dialog.DialogCode.Accepted:
                user_info = dialog.get_user_info()
                if user_info.get('logged_in'):
                    QMessageBox.information(
                        self, "登录成功",
                        f"欢迎! 用户ID: {user_info.get('musicid', 'Unknown')}"
                    )
                    self.update_menu_status()

        except ImportError as e:
            QMessageBox.warning(
                self, "错误",
                f"无法加载登录对话框: {str(e)}\n请确保已安装相关依赖。"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "错误",
                f"登录过程中发生错误: {str(e)}"
            )

    def logout(self):
        """登出"""
        try:
            if hasattr(self.api, 'logout'):
                self.api.logout()
                QMessageBox.information(self, "提示", "已成功登出")
                self.update_menu_status()
            else:
                QMessageBox.information(self, "提示", "当前API不支持登出功能")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"登出失败: {str(e)}")

    def show_user_info(self):
        """显示用户信息"""
        try:
            if hasattr(self.api, 'get_user_info'):
                user_info = self.api.get_user_info()
                if user_info.get('logged_in'):
                    info_text = f"""
用户信息:
- 用户ID: {user_info.get('musicid', 'Un known')}
- UIN: {user_info.get('uin', 'Unknown')}
- 登录状态: 已登录
                    """.strip()
                else:
                    info_text = "当前未登录"

                QMessageBox.information(self, "用户信息", info_text)
            else:
                QMessageBox.information(self, "提示", "当前API不支持用户信息查询")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取用户信息失败: {str(e)}")

    def show_api_settings(self):
        """显示API设置对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("API设置")
        dialog.setFixedSize(300, 150)

        layout = QVBoxLayout()

        # 自动登录选项
        auto_login_cb = QCheckBox("启动时自动登录")
        auto_login_cb.setChecked(config.AUTO_LOGIN)
        layout.addWidget(auto_login_cb)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 保存设置
            config.set_login_config(
                auto_login=auto_login_cb.isChecked()
            )

            QMessageBox.information(self, "提示", "设置已保存，重启程序后生效")

    def show_about(self):
        """显示关于对话框"""
        about_text = """
QQ音乐下载器 v2.0

基于QQMusicApi库重构，支持：
- 歌曲搜索和下载
- 专辑和歌单下载
- 多种音质选择
- 用户登录功能
- 批量下载

开发者: alien
        """.strip()

        QMessageBox.about(self, "关于", about_text)
