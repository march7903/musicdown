import os
import re

import json

from utils.logger import logger


def ms_to_timestamp(ms):
    """将毫秒转换为LRC格式的时间戳 [mm:ss.sss]"""
    seconds, ms = divmod(int(ms), 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


def timestamp_to_ms(timestamp):
    """将LRC格式的时间戳转换为毫秒"""
    if not timestamp:
        return 0
    try:
        minute, second = timestamp.split(':')
        return int(minute) * 60 * 1000 + int(float(second) * 1000)
    except:
        return 0


def parse_json_to_lrc(json_file, output_dir="lrc_output"):
    """将JSON文件转换为LRC格式，整合原文、翻译和罗马音"""
    try:
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 获取歌词信息
        lyric_xml = data.get("lyric", "")
        trans = data.get("trans", "")
        roma = data.get("roma", "")

        # 从XML中提取LyricContent
        match = re.search(r'LyricContent="([^"]+)"', lyric_xml)
        if not match:
            logger.warning(f"无法从XML中提取歌词内容: {json_file}")
            return

        lyric_content = match.group(1).replace(
            "\\r\\n", "\n").replace("\\n", "\n")

        # 提取标题信息
        headers = []
        for line in lyric_content.split("\n"):
            if re.match(r'\[(ti|ar|al|by|offset):', line):
                headers.append(line)

        # 存储所有行信息，包括原文、翻译和罗马音
        all_lines = []

        # 解析原文歌词行
        line_pattern = r'\[(\d+),(\d+)\](.*?)(?=\n\[|$)'
        line_matches = re.findall(line_pattern, lyric_content, re.DOTALL)

        for line_start, line_duration, line_content in line_matches:
            # 跳过头部信息行
            if re.search(r'\[(ti|ar|al|by|offset):', line_content):
                continue

            # 计算行的开始和结束时间戳
            start_ms = int(line_start)
            end_ms = start_ms + int(line_duration)
            start_timestamp = ms_to_timestamp(start_ms)
            end_timestamp = ms_to_timestamp(end_ms)

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
                    word_timestamp = ms_to_timestamp(int(word_start))
                    line_text += f"[{word_timestamp}]{word}"

                # 添加行结束时间戳
                line_text += f"[{end_timestamp}]"

                all_lines.append((start_ms, line_text, 'original'))

        # 解析罗马音行 - XML格式
        if roma:
            # 尝试从XML中提取LyricContent
            roma_match = re.search(r'LyricContent="([^"]+)"', roma)
            if roma_match:
                roma_content = roma_match.group(1).replace(
                    "\\r\\n", "\n").replace("\\n", "\n")

                # 使用与原文歌词相同的处理方式
                roma_line_matches = re.findall(
                    line_pattern, roma_content, re.DOTALL)

                for line_start, line_duration, line_content in roma_line_matches:
                    # 跳过头部信息行
                    if re.search(r'\[(ti|ar|al|by|offset):', line_content):
                        continue

                    # 计算行的开始和结束时间戳
                    start_ms = int(line_start)
                    end_ms = start_ms + int(line_duration)
                    start_timestamp = ms_to_timestamp(start_ms)
                    end_timestamp = ms_to_timestamp(end_ms)

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
                            word_timestamp = ms_to_timestamp(int(word_start))
                            line_text += f"[{word_timestamp}]{word}"

                        # 添加行结束时间戳
                        line_text += f"[{end_timestamp}]"

                        all_lines.append((start_ms, line_text, 'roma'))
            else:
                # 如果不是XML格式，尝试使用旧的处理方式
                roma_pattern = r'\[(\d\d:\d\d\.\d\d)\](.*?)(?=\n\[|$)'
                roma_matches = re.findall(roma_pattern, roma, re.DOTALL)

                # 为每个罗马音行添加结束时间戳
                for i, (time_str, content) in enumerate(roma_matches):
                    # 过滤空行和注释行
                    content = content.strip()
                    if not content or content.startswith('//'):
                        continue

                    start_ms = timestamp_to_ms(time_str)

                    # 使用下一行的开始时间作为当前行的结束时间，如果是最后一行，使用一个较大的值
                    if i < len(roma_matches) - 1:
                        end_ms = timestamp_to_ms(roma_matches[i + 1][0])
                    else:
                        # 假设最后一行的持续时间为5秒
                        end_ms = start_ms + 5000

                    end_timestamp = ms_to_timestamp(end_ms)
                    line_text = f"[{time_str}]{content}[{end_timestamp}]"

                    all_lines.append((start_ms, line_text, 'roma'))

        # 解析翻译行
        if trans:
            trans_pattern = r'\[(\d\d:\d\d\.\d\d)\](.*?)(?=\n\[|$)'
            trans_matches = re.findall(trans_pattern, trans, re.DOTALL)

            # 为每个翻译行添加结束时间戳
            for i, (time_str, content) in enumerate(trans_matches):
                # 过滤空行和注释行
                content = content.strip()
                if not content or content.startswith('//'):
                    continue

                start_ms = timestamp_to_ms(time_str)

                # 使用下一行的开始时间作为当前行的结束时间，如果是最后一行，使用一个较大的值
                if i < len(trans_matches) - 1:
                    end_ms = timestamp_to_ms(trans_matches[i + 1][0])
                else:
                    # 假设最后一行的持续时间为5秒
                    end_ms = start_ms + 5000

                end_timestamp = ms_to_timestamp(end_ms)
                line_text = f"[{time_str}]{content}[{end_timestamp}]"

                all_lines.append((start_ms, line_text, 'trans'))

        # 首先按时间戳排序所有行
        all_lines.sort(key=lambda x: x[0])

        # 使用类型优先级对相同时间戳的行进行再排序
        sorted_lines = []
        current_time = -1
        temp_lines = {}

        for time_ms, line_text, line_type in all_lines:
            # 过滤空行和注释行，检查时间戳后面的内容
            match = re.search(r'\[\d\d:\d\d\.\d\d\](.*?)(?=\[|$)', line_text)
            if match:
                content = match.group(1).strip()
                if not content or content.startswith('//'):
                    continue

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

        # 构建输出文件名
        base_name = os.path.basename(json_file)
        output_file = os.path.join(
            output_dir, base_name.replace(".json", ".lrc"))

        # 写入LRC文件
        with open(output_file, 'w', encoding='utf-8') as f:
            # 写入头部信息
            for header in headers:
                if header.endswith("\n") or header.endswith("\r") or header.endswith("\r\n"):
                    f.write(header)
                else:
                    f.write(header + "\n")

            # 写入排序后的所有行，过滤空行和注释行
            for _, line_text, _ in sorted_lines:
                # 最后一次检查确保不写入空行或注释行
                match = re.search(
                    r'\[\d\d:\d\d\.\d\d\](.*?)(?=\[|$)', line_text)
                if match:
                    content = match.group(1).strip()
                    if not content or content.startswith('//'):
                        continue
                f.write(line_text + "\n")

        logger.info(f"成功转换: {output_file}")

    except Exception as e:
        logger.error(f"处理文件时出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    json_files = "json\lyrics_parser_word_by_word_older.json"
    logger.info(f"处理文件: {json_files}")


    parse_json_to_lrc(json_files)


if __name__ == "__main__":
    main()
