from telegram.ext import Application, ApplicationBuilder
from telegram import Update
import importlib
import sys
import os
from pathlib import Path

from utils.logger import logger

# 确保可以导入项目根目录的模块
current_dir = Path(__file__).parent
logger.debug(current_dir)
project_root = current_dir.parent
sys.path.insert(0, str(project_root))

from utils.config import config



class QQMusicBot:
    def __init__(self):
        # 使用自定义API地址
        self.app = (ApplicationBuilder()
                    .token(config.BOT_TOKEN)
                    .base_url(config.API_BASE_URL)  # 使用配置中的自定义API地址
                    .build())

        # 注册所有命令和回调
        self._register_handlers()

    def _register_handlers(self):
        # 注册命令
        commands_dir = Path(__file__).parent / "commands"
        for file in commands_dir.glob("*.py"):
            if file.name != "__init__.py":
                module_name = f"tgbot.commands.{file.stem}"
                module = importlib.import_module(module_name)
                if hasattr(module, "register"):
                    module.register(self.app)

        # 注册回调
        callbacks_dir = Path(__file__).parent / "callbacks"
        for file in callbacks_dir.glob("*.py"):
            if file.name != "__init__.py":
                module_name = f"tgbot.callbacks.{file.stem}"
                module = importlib.import_module(module_name)
                if hasattr(module, "register"):
                    module.register(self.app)

    def run(self):
        logger.info("QQ音乐Telegram机器人启动中...")
        self.app.run_polling()


if __name__ == "__main__":
    bot = QQMusicBot()
    bot.run()
