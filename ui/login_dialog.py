"""
登录对话框
支持二维码登录和手机号登录
"""
import asyncio
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QMessageBox,
    QProgressBar, QGroupBox, QFormLayout, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QFont

from api.qqmusic import QQMusicAPI


class LoginWorker(QThread):
    """登录工作线程"""

    login_success = pyqtSignal(dict)  # 登录成功信号
    login_failed = pyqtSignal(str)    # 登录失败信号
    status_update = pyqtSignal(str)   # 状态更新信号
    qr_generated = pyqtSignal(bytes)  # 二维码生成信号（字节数据）

    def __init__(self, adapter: QQMusicAPI):
        super().__init__()
        self.adapter = adapter
        self.login_type = "QQ"
        self.phone = None
        self.country_code = 86
        self.method = "qr"  # qr 或 phone

    def set_qr_login(self, login_type: str):
        """设置二维码登录参数"""
        self.method = "qr"
        self.login_type = login_type

    def set_phone_login(self, phone: int, country_code: int = 86):
        """设置手机号登录参数"""
        self.method = "phone"
        self.phone = phone
        self.country_code = country_code

    def run(self):
        """执行登录"""
        try:
            if self.method == "qr":
                self._qr_login()
            elif self.method == "phone":
                self._phone_login()
        except Exception as e:
            self.login_failed.emit(f"登录过程中发生错误: {str(e)}")

    def _qr_login(self):
        """二维码登录"""
        try:
            self.status_update.emit("正在生成二维码...")

            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 定义回调函数
            def login_callback(event_type, data):
                self._handle_login_callback(event_type, data)

            success, _, error_msg = loop.run_until_complete(
                self.adapter.login_with_qr(self.login_type, login_callback)
            )

            if not success and error_msg:
                self.login_failed.emit(error_msg)

        except Exception as e:
            self.login_failed.emit(f"二维码登录错误: {str(e)}")
        finally:
            loop.close()

    def _handle_login_callback(self, event_type, data):
        """处理登录回调事件"""
        try:
            if event_type == "qr_generated":
                # data 现在是二维码的字节数据
                self.qr_generated.emit(data)
            elif event_type == "waiting_scan":
                self.status_update.emit(str(data))
            elif event_type == "waiting_confirm":
                self.status_update.emit(str(data))
            elif event_type == "login_success":
                user_info = self.adapter.get_user_info()
                self.login_success.emit(user_info)
            elif event_type == "timeout":
                self.login_failed.emit(str(data))
            elif event_type == "error":
                self.login_failed.emit(str(data))
        except Exception as e:
            print(f"回调处理错误: {e}")
            self.login_failed.emit(f"回调处理错误: {str(e)}")

    def _phone_login(self):
        """手机号登录"""
        try:
            self.status_update.emit("正在发送验证码...")

            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            success, error_msg = loop.run_until_complete(
                self.adapter.login_with_phone(self.phone, self.country_code)
            )

            if success:
                user_info = self.adapter.get_user_info()
                self.login_success.emit(user_info)
            else:
                self.login_failed.emit(error_msg or "手机号登录失败")

        except Exception as e:
            self.login_failed.emit(f"手机号登录错误: {str(e)}")
        finally:
            loop.close()


class QRLoginWidget(QWidget):
    """二维码登录组件"""

    def __init__(self, adapter: QQMusicAPI):
        super().__init__()
        self.adapter = adapter
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 登录方式选择
        type_group = QGroupBox("登录方式")
        type_layout = QHBoxLayout()

        self.login_type_combo = QComboBox()
        self.login_type_combo.addItems(["QQ", "微信"])
        type_layout.addWidget(QLabel("选择登录方式:"))
        type_layout.addWidget(self.login_type_combo)
        type_layout.addStretch()

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # 二维码显示区域
        qr_group = QGroupBox("二维码")
        qr_layout = QVBoxLayout()

        self.qr_label = QLabel("点击下方按钮生成二维码")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet(
            "border: 1px solid gray; background-color: #f0f0f0;")
        qr_layout.addWidget(self.qr_label)

        qr_group.setLayout(qr_layout)
        layout.addWidget(qr_group)

        # 状态显示
        self.status_label = QLabel("准备就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 按钮
        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("生成二维码")
        self.generate_btn.clicked.connect(self.generate_qr)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_login)
        self.cancel_btn.setEnabled(False)

        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def generate_qr(self):
        """生成二维码"""
        if self.worker and self.worker.isRunning():
            return

        login_type = self.login_type_combo.currentText()
        if login_type == "微信":
            login_type = "WX"

        self.worker = LoginWorker(self.adapter)
        self.worker.set_qr_login(login_type)

        # 连接信号
        self.worker.status_update.connect(self.update_status)
        self.worker.qr_generated.connect(self.show_qr_from_data)
        self.worker.login_success.connect(self.on_login_success)
        self.worker.login_failed.connect(self.on_login_failed)

        # 更新UI状态
        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条

        self.worker.start()

    def cancel_login(self):
        """取消登录"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.reset_ui()

    def reset_ui(self):
        """重置UI状态"""
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("准备就绪")
        self.qr_label.setText("点击下方按钮生成二维码")

    def update_status(self, status: str):
        """更新状态"""
        self.status_label.setText(status)

    def show_qr_from_data(self, qr_data: bytes):
        """从字节数据显示二维码"""
        try:
            if qr_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(qr_data):
                    scaled_pixmap = pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                    self.qr_label.setPixmap(scaled_pixmap)
                    self.status_label.setText("请使用手机扫描二维码")
                    print("二维码已从内存加载并显示")
                else:
                    self.status_label.setText("二维码加载失败")
                    print("无法从字节数据加载二维码图片")
            else:
                self.status_label.setText("二维码数据为空")
                print("二维码数据为空")
        except Exception as e:
            self.status_label.setText(f"显示二维码时出错: {str(e)}")
            print(f"显示二维码时出错: {e}")

    def show_qr(self, qr_path: str):
        """显示二维码（兼容旧版本，从文件路径加载）"""
        try:
            qr_file = Path(qr_path)
            if qr_file.exists():
                pixmap = QPixmap(str(qr_file))
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                    self.qr_label.setPixmap(scaled_pixmap)
                    self.status_label.setText("请使用手机扫描二维码")
                    print(f"二维码已显示: {qr_path}")
                else:
                    self.status_label.setText("二维码加载失败")
                    print(f"无法加载二维码图片: {qr_path}")
            else:
                self.status_label.setText("二维码文件不存在")
                print(f"二维码文件不存在: {qr_path}")
        except Exception as e:
            self.status_label.setText(f"显示二维码时出错: {str(e)}")
            print(f"显示二维码时出错: {e}")

    def on_login_success(self, user_info: dict):
        """登录成功"""
        self.reset_ui()
        self.status_label.setText(
            f"登录成功! 用户ID: {user_info.get('musicid', 'Unknown')}")

        # 通知父窗口
        if hasattr(self.parent(), 'on_login_success'):
            self.parent().on_login_success(user_info)

    def on_login_failed(self, error: str):
        """登录失败"""
        self.reset_ui()
        self.status_label.setText(f"登录失败: {error}")
        QMessageBox.warning(self, "登录失败", error)


class LoginDialog(QDialog):
    """登录对话框"""

    def __init__(self, adapter: QQMusicAPI, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.user_info = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("QQ音乐登录")
        self.setFixedSize(450, 600)

        layout = QVBoxLayout()

        # 标题
        title_label = QLabel("QQ音乐登录")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 只保留二维码登录
        self.qr_widget = QRLoginWidget(self.adapter)
        layout.addWidget(self.qr_widget)

        # 底部按钮
        button_layout = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # 连接二维码登录成功信号，登录成功后自动关闭窗口
        self.qr_widget_login_success_connected = False
        self.qr_widget_generate_qr_orig = self.qr_widget.generate_qr

        def generate_qr_with_connect():
            result = self.qr_widget_generate_qr_orig()
            if self.qr_widget.worker and not self.qr_widget_login_success_connected:
                self.qr_widget.worker.login_success.connect(
                    self.on_login_success)
                self.qr_widget_login_success_connected = True
            return result
        self.qr_widget.generate_qr = generate_qr_with_connect

    def on_login_success(self, user_info):
        self.user_info = user_info
        self.accept()

    def get_user_info(self) -> dict:
        """获取用户信息"""
        return self.user_info or {}


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    adapter = QQMusicAPI()
    dialog = LoginDialog(adapter)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        print("登录成功:", dialog.get_user_info())
    else:
        print("登录取消")

    sys.exit()
