"""
登录对话框
支持二维码登录和手机号登录
"""
import asyncio
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox,
    QProgressBar, QGroupBox, QFormLayout, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QPixmap, QFont

from api.qqmusic import QQMusicAPI


class LoginWorker(QThread):
    """登录工作线程"""

    login_success = pyqtSignal(dict)  # 登录成功信号
    login_failed = pyqtSignal(str)    # 登录失败信号
    status_update = pyqtSignal(str)   # 状态更新信号
    qr_generated = pyqtSignal(str)    # 二维码生成信号

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
                try:
                    if event_type == "qr_generated":
                        # 确保传递字符串类型
                        qr_path = str(data) if data else ""
                        self.qr_generated.emit(qr_path)
                    elif event_type == "scanned":
                        self.status_update.emit(str(data))
                    elif event_type == "waiting":
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

            success, qr_path, error_msg = loop.run_until_complete(
                self.adapter.login_with_qr(self.login_type, login_callback)
            )

            if not success and error_msg:
                self.login_failed.emit(error_msg)

        except Exception as e:
            self.login_failed.emit(f"二维码登录错误: {str(e)}")
        finally:
            loop.close()

    def _phone_login(self):
        """手机号登录"""
        try:
            self.status_update.emit("正在发送验证码...")

            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            success = loop.run_until_complete(
                self.adapter.login_with_phone(self.phone, self.country_code)
            )

            if success:
                user_info = self.adapter.get_user_info()
                self.login_success.emit(user_info)
            else:
                self.login_failed.emit("手机号登录失败")

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
        self.worker.qr_generated.connect(self.show_qr)
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

    def show_qr(self, qr_path: str):
        """显示二维码"""
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


class PhoneLoginWidget(QWidget):
    """手机号登录组件"""

    def __init__(self, adapter: QQMusicAPI):
        super().__init__()
        self.adapter = adapter
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 手机号输入
        form_group = QGroupBox("手机号登录")
        form_layout = QFormLayout()

        self.country_combo = QComboBox()
        self.country_combo.addItems(["+86 (中国)", "+1 (美国)", "+44 (英国)"])
        form_layout.addRow("国家/地区:", self.country_combo)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("请输入手机号")
        form_layout.addRow("手机号:", self.phone_edit)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # 状态显示
        self.status_label = QLabel("请输入手机号")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 按钮
        button_layout = QHBoxLayout()
        self.login_btn = QPushButton("发送验证码")
        self.login_btn.clicked.connect(self.start_phone_login)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_login)
        self.cancel_btn.setEnabled(False)

        button_layout.addWidget(self.login_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        layout.addStretch()
        self.setLayout(layout)

    def start_phone_login(self):
        """开始手机号登录"""
        phone_text = self.phone_edit.text().strip()
        if not phone_text:
            QMessageBox.warning(self, "输入错误", "请输入手机号")
            return

        try:
            phone = int(phone_text)
        except ValueError:
            QMessageBox.warning(self, "输入错误", "手机号格式不正确")
            return

        # 获取国家代码
        country_text = self.country_combo.currentText()
        country_code = 86  # 默认中国
        if "+1" in country_text:
            country_code = 1
        elif "+44" in country_text:
            country_code = 44

        if self.worker and self.worker.isRunning():
            return

        self.worker = LoginWorker(self.adapter)
        self.worker.set_phone_login(phone, country_code)

        # 连接信号
        self.worker.status_update.connect(self.update_status)
        self.worker.login_success.connect(self.on_login_success)
        self.worker.login_failed.connect(self.on_login_failed)

        # 更新UI状态
        self.login_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.worker.start()

    def cancel_login(self):
        """取消登录"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.reset_ui()

    def reset_ui(self):
        """重置UI状态"""
        self.login_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("请输入手机号")

    def update_status(self, status: str):
        """更新状态"""
        self.status_label.setText(status)

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

        # 选项卡
        self.tab_widget = QTabWidget()

        # 二维码登录选项卡
        self.qr_widget = QRLoginWidget(self.adapter)
        self.tab_widget.addTab(self.qr_widget, "二维码登录")

        # 手机号登录选项卡
        self.phone_widget = PhoneLoginWidget(self.adapter)
        self.tab_widget.addTab(self.phone_widget, "手机号登录")

        layout.addWidget(self.tab_widget)

        # 底部按钮
        button_layout = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def on_login_success(self, user_info: dict):
        """登录成功回调"""
        self.user_info = user_info
        QMessageBox.information(self, "登录成功",
                                f"欢迎! 用户ID: {user_info.get('musicid', 'Unknown')}")
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
