from api.qqmusic import QQMusicAPI
from telegram.ext import ContextTypes, CommandHandler, filters
from telegram import Update
import sys
from pathlib import Path

# 确保可以导入项目根目录的模块
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))


from tgbot.utils.message_builders import build_search_results_message
from utils.config import config
from utils.menum import SearchType

# 初始化QQ音乐API
qq_music_api = QQMusicAPI()


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 获取搜索关键词
    if not context.args:
        await update.message.reply_text("请输入要搜索的歌曲名，例如：/search 周杰伦 稻香")
        return

    query = " ".join(context.args)
    user_id = update.message.from_user.id

    # 显示搜索中消息
    status_message = await update.message.reply_text("🔍 正在搜索歌曲，请稍候...")

    try:
        # 调用API搜索歌曲
        search_result = await qq_music_api.search(query, limit=10, page=1)

        if search_result['code'] == -1 or not search_result.get('songs'):
            await status_message.edit_text("❌ 未找到相关歌曲，请尝试其他关键词。")
            return

        # 保存搜索结果到用户会话
        config.user_sessions[user_id] = {
            "search_results": search_result['songs'],
            "current_page": 1,
            "last_query": query
        }

        # 构建搜索结果消息和键盘
        text, keyboard = build_search_results_message(
            search_result['songs'])

        await status_message.edit_text(
            "🔍 搜索结果:",
            reply_markup=keyboard
        )

    except Exception as e:
        await status_message.edit_text(f"❌ 搜索出错: {str(e)}")


def register(app):
    app.add_handler(CommandHandler("search", search))
