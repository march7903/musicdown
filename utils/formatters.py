import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from utils.config import config
from utils.logger import logger


def format_singers(singers: List[Dict]) -> str:
    """格式化歌手列表为字符串"""
    return " ".join([singer['name'] for singer in singers])


def clean_html_tags(text: str) -> str:
    """清理文本中的HTML标签

    Args:
        text: 包含HTML标签的文本

    Returns:
        清理后的纯文本
    """
    if not text:
        return text

    # 移除HTML标签，保留标签内的文本内容
    clean_text = re.sub(r'<[^>]+>', '', text)

    # 清理多余的空白字符
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return clean_text


def format_interval(interval: int) -> str:
    minutes = interval // 60  # 计算分钟
    seconds = interval % 60  # 计算剩余秒数
    duration = f"{minutes}:{seconds:02d}"  # 格式化成 mm:ss
    return duration


def get_audio_extension(url: str) -> str:
    """获取音频文件扩展名"""
    ext = Path(urlparse(url).path).suffix.lower()

    valid_extensions = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"}
    if ext not in valid_extensions:
        ext = ".mp3"  # 默认值

    return ext


async def get_file_path(selected_song: Dict, song_url: str, download_dir: Path = config.DOWNLOADS_DIR):
    """获取下载文件路径"""
    ext = get_audio_extension(song_url)
    filename = f"{selected_song['name']}-{format_singers(selected_song['singer'])}{ext}"
    safe_filename = "".join(
        c for c in filename if c.isalnum() or c in " -_.").strip()
    filepath = f"{download_dir}/{safe_filename}"

    return Path(filepath)


def _ms_to_timestamp(ms):
    """将毫秒转换为LRC格式的时间戳 [mm:ss.sss]"""
    seconds, ms = divmod(int(ms), 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


def _timestamp_to_ms(timestamp):
    """将LRC格式的时间戳转换为毫秒"""
    if not timestamp:
        return 0
    try:
        minute, second = timestamp.split(':')
        return int(minute) * 60 * 1000 + int(float(second) * 1000)
    except:
        return 0


def parse_word_by_word_lyrics(lyrics_data: Dict, isTrans: bool = False, isRoma: bool = False) -> str:
    """解析逐字歌词数据，转换为LRC格式
    
    Args:
        lyrics_data: 逐字歌词数据字典
        isTrans: 是否包含翻译歌词
        isRoma: 是否包含罗马音歌词

    Returns:
        LRC格式的歌词字符串
    """
    lyric = lyrics_data.get("lyric", "")
    trans = lyrics_data.get("trans", "")
    roma = lyrics_data.get("roma", "")

    all_lines = []

    headers = _parse_headers(lyric)
    lrc_original = _parse_wbw_lyrics(lyric, "original")
    lrc_trans = _parse_wbw_lyrics(trans, "trans")
    lrc_roma = _parse_wbw_lyrics(roma, "roma")

    all_lines.extend(lrc_original)
    if isTrans:
        all_lines.extend(lrc_trans)
    if isRoma:
        all_lines.extend(lrc_roma)

    all_lines.sort(key=lambda x: x[0])

    # 使用类型优先级对相同时间戳的行进行再排序
    sorted_lines = []
    current_time = -1
    temp_lines = {}

    for time_ms, line_text, line_type in all_lines:
        # 如果时间戳改变，处理之前收集的行
        if time_ms != current_time and current_time != -1:
            # 按照roma、original、trans的顺序添加
            for type_name in ['roma', 'original', 'trans']:
                if type_name in temp_lines:
                    sorted_lines.append(
                        (current_time, temp_lines[type_name], type_name))
            temp_lines = {}

        # 更新当前时间戳和临时存储
        current_time = time_ms
        temp_lines[line_type] = line_text

    # 处理最后一组
    if temp_lines:
        for type_name in ['roma', 'original', 'trans']:
            if type_name in temp_lines:
                sorted_lines.append(
                    (current_time, temp_lines[type_name], type_name))

    lrc_content = ""
    for header in headers:
        if header.endswith("\n") or header.endswith("\r") or header.endswith("\r\n"):
            lrc_content += header
        else:
            lrc_content += header + "\n"
    for _, line_text, _ in sorted_lines:
        lrc_content += line_text + "\n"

    return lrc_content


def _parse_wbw_lyrics(lyric_str: str, lyric_type: str) -> list[tuple[int, str, str]]:
    """解析歌词数据，转换为LRC格式"""
    lines = []
    # 判断是否为XML格式
    if lyric_str.startswith("<?xml"):
        # 从XML中提取LyricContent
        match = re.search(r'LyricContent="([^"]+)"', lyric_str)
        if not match:
            logger.warning(f"无法从XML中提取歌词内容: {lyric_str}")
            return

        lyric_content = match.group(1).replace(
            "\\r\\n", "\n").replace("\\n", "\n")

        # 提取标题信息
        headers = []
        for line in lyric_content.split("\n"):
            if re.match(r'\[(ti|ar|al|by|offset):', line):
                headers.append(line)
        # 解析歌词行
        line_pattern = r'\[(\d+),(\d+)\](.*?)(?=\n\[|$)'
        line_matches = re.findall(line_pattern, lyric_content, re.DOTALL)
        for line_start, line_duration, line_content in line_matches:
            # 跳过头部信息行
            if re.search(r'\[(ti|ar|al|by|offset):', line_content):
                continue

            # 计算行的开始和结束时间戳
            start_ms = int(line_start)
            end_ms = start_ms + int(line_duration)
            start_timestamp = _ms_to_timestamp(start_ms)
            end_timestamp = _ms_to_timestamp(end_ms)

            # 提取单词及其时间戳
            word_pattern = r'([^\(\)]+)\((\d+),(\d+)\)'
            word_matches = re.findall(word_pattern, line_content)

            if word_matches:
                # 创建整行的内容，行的第一个词使用行的开始时间戳
                line_text = f"[{start_timestamp}]"

                # 添加第一个词（不添加单独的时间戳）
                first_word, _, _ = word_matches[0]
                line_text += first_word

                # 添加后续的词（每个都有自己的时间戳）
                for word, word_start, word_duration in word_matches[1:]:
                    word_timestamp = _ms_to_timestamp(int(word_start))
                    line_text += f"[{word_timestamp}]{word}"

                # 添加行结束时间戳
                line_text += f"[{end_timestamp}]"

                lines.append((start_ms, line_text, lyric_type))

        return lines

    else:
        pattern = r'\[(\d\d:\d\d\.\d\d)\](.*?)(?=\n\[|$)'
        matches = re.findall(pattern, lyric_str, re.DOTALL)

        for i, (time_str, content) in enumerate(matches):
            # 过滤空行和注释行
            content = content.strip()
            if not content or content.startswith('//'):
                continue

            start_ms = _timestamp_to_ms(time_str)

            # 使用下一行的开始时间作为当前行的结束时间，如果是最后一行，使用一个较大的值
            if i < len(matches) - 1:
                end_ms = _timestamp_to_ms(matches[i + 1][0])
            else:
                # 假设最后一行的持续时间为5秒
                end_ms = start_ms + 5000

            end_timestamp = _ms_to_timestamp(end_ms)
            line_text = f"[{time_str}]{content}[{end_timestamp}]"

            lines.append((start_ms, line_text, lyric_type))

        return lines


def _parse_headers(lyric_str: str) -> list[str]:
    """解析歌词头部信息"""
    headers = []
    for line in lyric_str.split("\n"):
        if re.match(r'\[(ti|ar|al|by|offset):', line):
            headers.append(line)
    return headers


def parse_lrc_lyrics(lyric_data: Dict):
    """解析LRC歌词数据"""
    lyric = lyric_data.get("lyric", "")
    trans = lyric_data.get("trans", "")

    headers = _parse_headers(lyric)
    original_lines = _parse_lyric_lines(lyric)
    translate_lines = _parse_lyric_lines(trans)

    lyrics_content = []

    for header in headers:
        if header.endswith("\n") or header.endswith("\r") or header.endswith("\r\n"):
            lyrics_content.append(header)
        else:
            lyrics_content.append(header + "\n")

    for time_tag, original in original_lines.items():
        lyrics_content.append(f"{time_tag}{original}")
        if time_tag in translate_lines:
            if translate_lines[time_tag].startswith("//") or not translate_lines[time_tag]:
                continue
            lyrics_content.append(f"{time_tag}{translate_lines[time_tag]}")

    return "\n".join(lyrics_content)


def _parse_lyric_lines(lyric: str):
    """解析歌词行"""
    lines = {}
    for line in lyric.split('\n'):
        if line.strip() and '[' in line:
            try:
                time_tag = line[line.find('['):line.find(']') + 1]
                content = line[line.find(']') + 1:].strip()
                if content:
                    lines[time_tag] = content
            except:
                continue
    return lines
