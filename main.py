from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
import logging
import subprocess
import json
import time
from typing import List, Dict
import sys
import queue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 添加文件日志处理器
def setup_file_logger():
    """设置文件日志处理器"""
    # 创建logs目录
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    # 创建日志文件，按日期命名
    log_filename = logs_dir / f"gpt_sovits_{datetime.now().strftime('%Y%m%d')}.log"

    # 创建文件处理器
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # 设置文件日志格式
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # 添加到logger
    logger.addHandler(file_handler)

    return log_filename


def log_with_timestamp(message: str, level: str = "INFO", task_id: str = None):
    """
    带时间戳的日志记录函数

    Args:
        message: 日志消息
        level: 日志级别 (INFO, DEBUG, WARNING, ERROR)
        task_id: 任务ID（可选）
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    prefix = f"[{timestamp}]"

    if task_id:
        prefix += f" [任务: {task_id}]"

    log_message = f"{prefix} {message}"

    if level == "INFO":
        logger.info(log_message)
    elif level == "DEBUG":
        logger.debug(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    elif level == "ERROR":
        logger.error(log_message)

    # 同时在控制台输出
    print(f"{timestamp} - {level} - {message}")


app = FastAPI(title="GPT-SoVITS顺序语音API", version="3.2.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置存储路径
BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "voice_and_output"
STORAGE_DIR.mkdir(exist_ok=True)

# 脚本路径 - 确保 script1.py 在同一目录下
SCRIPT_PATH = BASE_DIR / "script1.py"

# 设置日志文件
log_file_path = setup_file_logger()
logger.info(f"日志文件已创建: {log_file_path}")


class TextRequest(BaseModel):
    text: str
    ref_audio_path: str
    language: str = "zh"
    sequential: bool = True  # 顺序生成


# 句子管理类
class SentenceManager:
    def __init__(self):
        self.tasks = {}  # task_id -> task_info
        import concurrent.futures
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)  # 单线程确保顺序

    def create_task(self, task_id: str, sentences: List[str], ref_audio_path: str):
        """创建新任务"""
        self.tasks[task_id] = {
            'task_id': task_id,
            'sentences': sentences,
            'ref_audio_path': ref_audio_path,
            'total_sentences': len(sentences),
            'completed_count': 0,
            'current_index': 0,
            'status': 'processing',
            'start_time': time.time(),
            'sentence_status': ['waiting'] * len(sentences),
            'audio_data': [None] * len(sentences),
            'audio_paths': [None] * len(sentences),
            'callback_queue': queue.Queue()
        }
        return self.tasks[task_id]

    def update_sentence_status(self, task_id: str, sentence_index: int, status: str, audio_data=None, audio_path=None):
        """更新句子状态"""
        if task_id not in self.tasks:
            return

        task = self.tasks[task_id]
        task['sentence_status'][sentence_index] = status

        if status == 'completed':
            task['audio_data'][sentence_index] = audio_data
            task['audio_paths'][sentence_index] = audio_path
            task['completed_count'] += 1

    def get_task(self, task_id: str):
        """获取任务信息"""
        return self.tasks.get(task_id)

    def mark_task_completed(self, task_id: str):
        """标记任务完成"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = 'completed'

    def get_task_status(self, task_id: str):
        """获取任务状态"""
        task = self.get_task(task_id)
        if not task:
            return None

        return {
            'task_id': task_id,
            'status': task['status'],
            'total_sentences': task['total_sentences'],
            'completed_count': task['completed_count'],
            'current_index': task['current_index'],
            'elapsed_time': time.time() - task['start_time'],
            'sentence_statuses': task['sentence_status'],
            'audio_files': [
                {
                    'sentence_index': i,
                    'filename': Path(path).name if path else None,
                    'file_path': path,
                    'status': task['sentence_status'][i]
                }
                for i, path in enumerate(task['audio_paths'])
                if path
            ]
        }

    def cleanup(self, task_id: str):
        """清理任务资源"""
        if task_id in self.tasks:
            del self.tasks[task_id]


# 全局句子管理器
sentence_manager = SentenceManager()


def split_text_by_sentences(text: str) -> List[str]:
    """改进的文本分割函数，正确处理数字+点的情况，包括小数点"""
    import re

    # 首先处理小数点：将数字中的小数点替换为特殊标记
    # 匹配模式：数字 + 点 + 数字（例如：3.14、6.98、0.5）
    text = re.sub(r'(\d+)\.(\d+)', r'\1[DOT]\2', text)

    # 处理序数点：匹配模式：数字 + 点 + 非数字（例如：1.、2.、3.等）
    text = re.sub(r'(\d+)\.(\s|$)', r'\1\2', text)

    # 先按标点分割
    sentences = []
    buffer = []

    # 定义句子结束符
    sentence_end_chars = {'。', '！', '？', '；', '.', '!', '?', ';', '…'}

    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        # 检查是否是省略号
        if char == '.' and i + 2 < length and text[i + 1] == '.' and text[i + 2] == '.':
            buffer.append('...')
            i += 3  # 跳过三个点
            continue

        buffer.append(char)

        # 检查是否是句子结束
        if char in sentence_end_chars:
            # 再次检查是否是数字+点的情况
            if char == '.' and buffer:
                # 检查除当前点外的所有字符
                temp_str = ''.join(buffer[:-1])
                if temp_str.strip().isdigit():
                    # 删除数字后面的点
                    buffer.pop()
                    i += 1
                    continue

            # 检查后面是否有括号或其他可能不是句子结束的情况
            is_real_end = True
            if i + 1 < length:
                next_char = text[i + 1]
                # 如果后面是右括号、右引号等，可能是句子结束
                if next_char in ['）', '」', '》', '】', ')', ']', '}']:
                    is_real_end = True
                # 如果后面是小写字母或数字，可能不是句子结束
                elif next_char.islower() or next_char.isdigit():
                    is_real_end = False
                # 如果后面是空格或换行，可能是句子结束
                elif next_char in [' ', '\n', '\t']:
                    # 再检查空格后面是什么
                    j = i + 2
                    while j < length and text[j] in [' ', '\n', '\t']:
                        j += 1
                    if j < length and text[j].islower():
                        is_real_end = False

            if is_real_end:
                sentence = ''.join(buffer).strip()
                if sentence:
                    sentences.append(sentence)
                buffer = []

        i += 1

    # 处理最后一句
    if buffer:
        # 最后检查数字+点的情况
        if buffer and buffer[-1] == '.':
            temp_str = ''.join(buffer[:-1])
            if temp_str.strip().isdigit():
                buffer.pop()  # 删除数字后的点

        sentence = ''.join(buffer).strip()
        if sentence:
            sentences.append(sentence)

    # 清理空句子
    sentences = [s for s in sentences if s.strip()]

    # 合并过短的句子
    merged_sentences = []
    temp_buffer = []

    for sentence in sentences:
        # 如果句子包含标点，先检查是否需要合并
        if len(sentence) < 10 and sentence != sentences[-1]:
            # 检查句子是否以句子结束符结尾
            if sentence and sentence[-1] not in sentence_end_chars:
                temp_buffer.append(sentence)
                continue

        if temp_buffer:
            temp_buffer.append(sentence)
            merged = ''.join(temp_buffer)
            merged_sentences.append(merged)
            temp_buffer = []
        else:
            merged_sentences.append(sentence)

    # 处理剩余的缓冲区
    if temp_buffer:
        merged = ''.join(temp_buffer)
        merged_sentences.append(merged)

    # 恢复小数点标记为汉字"点"
    final_sentences = []
    for sentence in merged_sentences:
        # 将 [DOT] 替换为汉字"点"
        sentence = sentence.replace('[DOT]', '点')
        final_sentences.append(sentence)

    logger.info(f"将文本切分为 {len(final_sentences)} 个句子")
    for idx, sentence in enumerate(final_sentences):
        logger.debug(f"句子 {idx + 1}: {sentence[:50]}{'...' if len(sentence) > 50 else ''}")

    return final_sentences


def generate_sentence_with_script(sentence: str, ref_audio_path: str, task_id: str, sentence_index: int):
    """使用script1.py直接生成单个句子的音频"""
    try:
        # 记录开始生成句子
        send_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_with_timestamp(
            f"开始生成句子 {sentence_index} (长度: {len(sentence)} 字符)",
            "INFO",
            task_id
        )

        log_with_timestamp(f"句子 {sentence_index} 发送到script1.py时间: {send_time}", "INFO", task_id)
        log_with_timestamp(f"句子 {sentence_index} 完整内容: {sentence}", "DEBUG", task_id)

        # 生成唯一的任务ID用于这个句子
        sub_task_id = f"{task_id}_s{sentence_index}"

        # 构建命令 - 直接调用script1.py
        cmd = [
            sys.executable,  # 使用当前的Python解释器
            str(SCRIPT_PATH),
            "--text", sentence,
            "--text-lang", "zh",
            "--ref-audio", ref_audio_path,
            "--task-id", sub_task_id,
            "--top-k", "5",
            "--top-p", "1.0",
            "--temperature", "1.0",
            "--speed", "1.0",
            "--clean-old"  # 清理旧的output.wav文件
        ]

        log_with_timestamp(f"执行命令: {' '.join(cmd[:10])}...", "INFO", task_id)

        # 执行命令并计时
        cmd_start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=180  # 增加到180秒超时
        )

        # 记录命令执行时间
        cmd_time = time.time() - cmd_start_time
        log_with_timestamp(f"script1.py执行耗时: {cmd_time:.2f}秒", "INFO", task_id)

        if result.returncode != 0:
            error_msg = f"script1.py执行失败: {result.stderr}"
            log_with_timestamp(f"句子 {sentence_index} 生成失败: {error_msg}", "ERROR", task_id)
            raise Exception(f"生成失败: {result.stderr}")

        # 解析输出（JSON格式）
        audio_file = None
        try:
            # 获取最后一行JSON输出
            output_lines = result.stdout.strip().split('\n')
            json_line = None

            # 从最后一行开始找JSON
            for line in reversed(output_lines):
                line = line.strip()
                if line and (line.startswith('{') and line.endswith('}')):
                    json_line = line
                    break

            if json_line:
                output_json = json.loads(json_line)
                log_with_timestamp(f"script1.py返回JSON状态: {output_json.get('status')}", "DEBUG", task_id)

                # 检查返回状态
                if output_json.get("status") == "success":
                    # 从返回中获取文件路径
                    unique_output = output_json.get("unique_output")
                    default_output = output_json.get("default_output")
                    output_path = output_json.get("output_path")

                    # 优先使用unique_output，如果没有则使用default_output或output_path
                    if unique_output and Path(unique_output).exists():
                        audio_file = Path(unique_output)
                    elif default_output and Path(default_output).exists():
                        audio_file = Path(default_output)
                    elif output_path and Path(output_path).exists():
                        audio_file = Path(output_path)
                    else:
                        log_with_timestamp(f"JSON中未找到有效文件路径", "WARNING", task_id)
                else:
                    error_msg = output_json.get('message', '未知错误')
                    raise Exception(f"script1.py返回错误: {error_msg}")
            else:
                log_with_timestamp("script1.py未返回有效的JSON输出", "WARNING", task_id)

        except json.JSONDecodeError as e:
            log_with_timestamp(f"无法解析script1.py输出为JSON: {e}", "WARNING", task_id)
            log_with_timestamp(f"原始输出最后100字符: {result.stdout[-100:]}", "DEBUG", task_id)
        except Exception as e:
            log_with_timestamp(f"解析script1.py输出失败: {e}", "ERROR", task_id)

        # 如果通过JSON没找到文件，尝试查找生成的音频文件
        if audio_file is None or not audio_file.exists():
            output_dir = Path("C:\\Users\\24021\\Desktop\\GPT-SoVITS-main")

            # 尝试多个可能的文件名
            possible_files = [
                output_dir / f"output_{sub_task_id}.wav",
                output_dir / "output.wav",
                STORAGE_DIR / f"output_{sub_task_id}.wav",
                STORAGE_DIR / "output.wav"
            ]

            for file_path in possible_files:
                if file_path.exists():
                    audio_file = file_path
                    log_with_timestamp(f"找到音频文件: {audio_file}", "INFO", task_id)
                    break

        # 检查音频文件是否存在
        if audio_file is None or not audio_file.exists():
            error_msg = f"未找到生成的音频文件"
            log_with_timestamp(error_msg, "ERROR", task_id)

            # 列出目录内容以帮助调试
            try:
                output_dir = Path("C:\\Users\\24021\\Desktop\\GPT-SoVITS-main")
                if output_dir.exists():
                    files = list(output_dir.glob("*.wav"))
                    log_with_timestamp(f"GPT-SoVITS目录中的wav文件: {[f.name for f in files[:10]]}", "DEBUG", task_id)

                if STORAGE_DIR.exists():
                    files = list(STORAGE_DIR.glob("*.wav"))
                    log_with_timestamp(f"存储目录中的wav文件: {[f.name for f in files[:10]]}", "DEBUG", task_id)
            except Exception as e:
                log_with_timestamp(f"无法列出目录内容: {e}", "ERROR", task_id)

            raise Exception(error_msg)

        # 读取音频数据
        with open(audio_file, 'rb') as f:
            audio_data = f.read()

        # 记录生成成功
        success_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        total_time = time.time() - cmd_start_time
        log_with_timestamp(
            f"✓ 句子 {sentence_index} 生成成功，文件大小: {len(audio_data)} bytes",
            "INFO",
            task_id
        )
        log_with_timestamp(f"句子 {sentence_index} 生成成功时间: {success_time}", "INFO", task_id)
        log_with_timestamp(f"句子 {sentence_index} 总耗时: {total_time:.2f}秒", "INFO", task_id)
        log_with_timestamp(f"音频文件位置: {audio_file}", "INFO", task_id)

        # 更新句子状态
        sentence_manager.update_sentence_status(
            task_id,
            sentence_index,
            'completed',
            audio_data=audio_data,
            audio_path=str(audio_file)
        )

        return audio_data, str(audio_file)

    except subprocess.TimeoutExpired:
        log_with_timestamp(f"句子 {sentence_index} 生成超时（超过180秒）", "ERROR", task_id)
        sentence_manager.update_sentence_status(task_id, sentence_index, 'error')
        return None, None
    except Exception as e:
        log_with_timestamp(f"句子 {sentence_index} 生成失败: {e}", "ERROR", task_id)
        sentence_manager.update_sentence_status(task_id, sentence_index, 'error')
        return None, None


def process_sentences_sequential(text: str, ref_audio_path: str, task_id: str):
    """顺序处理所有句子 - 逐个生成"""
    try:
        # 切分句子
        sentences = split_text_by_sentences(text)
        log_with_timestamp(f"任务 {task_id} 开始处理 {len(sentences)} 个句子", "INFO", task_id)

        # 创建任务
        task_info = sentence_manager.create_task(task_id, sentences, ref_audio_path)

        # 顺序生成每个句子
        for i, sentence in enumerate(sentences):
            # 更新为处理中状态
            sentence_manager.update_sentence_status(task_id, i, 'processing')

            # 记录进度
            progress = (i / len(sentences)) * 100 if len(sentences) > 0 else 0
            log_with_timestamp(f"开始处理句子 {i + 1}/{len(sentences)} (进度: {progress:.1f}%)", "INFO", task_id)

            # 生成当前句子
            audio_data, audio_path = generate_sentence_with_script(
                sentence, ref_audio_path, task_id, i
            )

            if audio_data:
                # 计算当前进度
                current_progress = ((i + 1) / len(sentences)) * 100
                log_with_timestamp(f"✓ 句子 {i} 完成，进度: {current_progress:.1f}%", "INFO", task_id)

        # 标记任务完成
        sentence_manager.mark_task_completed(task_id)
        log_with_timestamp(f"✓ 任务 {task_id} 所有句子处理完成", "INFO", task_id)

        # 记录总耗时
        total_time = time.time() - task_info['start_time']
        log_with_timestamp(f"任务总耗时: {total_time:.2f}秒", "INFO", task_id)
        log_with_timestamp(f"平均每句子耗时: {total_time / len(sentences):.2f}秒", "INFO", task_id)

    except Exception as e:
        log_with_timestamp(f"任务 {task_id} 处理失败: {e}", "ERROR", task_id)
        sentence_manager.cleanup(task_id)


@app.get("/")
async def root():
    """根端点"""
    log_with_timestamp("收到根端点请求")
    return {
        "message": "GPT-SoVITS顺序语音API",
        "version": "3.2.0",
        "features": ["顺序语音生成", "智能文本分割", "无缝播放衔接", "script1.py集成"],
        "status": "ready",
        "log_file": str(log_file_path)
    }


@app.post("/process")
async def process_text(request: TextRequest, background_tasks: BackgroundTasks):
    """
    处理文本并开始语音生成
    """
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="文本内容不能为空")

        # 检查参考音频文件
        ref_audio_path = Path(request.ref_audio_path)
        if not ref_audio_path.exists():
            stored_path = STORAGE_DIR / ref_audio_path.name
            if stored_path.exists():
                ref_audio_path = stored_path
            else:
                raise HTTPException(status_code=404, detail="参考音频文件不存在")

        # 检查script1.py是否存在
        if not SCRIPT_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail="script1.py不存在，请确保它在后端目录中"
            )

        # 生成任务ID
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # 记录前端请求
        receive_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_with_timestamp(
            f"接收到前端文本处理请求 - 文本长度: {len(request.text)} 字符, 参考音频: {ref_audio_path.name}",
            "INFO",
            task_id
        )
        log_with_timestamp(f"请求接收时间: {receive_time}", "INFO", task_id)

        # 记录文本内容预览
        text_preview = request.text[:100] + ("..." if len(request.text) > 100 else "")
        log_with_timestamp(f"处理文本内容预览: {text_preview}", "INFO", task_id)

        # 切分句子
        sentences = split_text_by_sentences(request.text)
        log_with_timestamp(f"文本切分为 {len(sentences)} 个句子", "INFO", task_id)

        # 在后台开始顺序处理
        background_tasks.add_task(
            process_sentences_sequential,
            text=request.text,
            ref_audio_path=str(ref_audio_path),
            task_id=task_id
        )

        log_with_timestamp(f"任务已开始后台处理，总句子数: {len(sentences)}", "INFO", task_id)

        return {
            "task_id": task_id,
            "status": "started",
            "message": "顺序语音生成已开始",
            "sentences_count": len(sentences),
            "sentences": sentences,
            "mode": "sequential",
            "created_at": datetime.now().isoformat(),
            "log_file": str(log_file_path)
        }

    except Exception as e:
        logger.error(f"处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@app.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务状态"""
    log_with_timestamp(f"获取任务状态请求: {task_id}", "INFO")
    status = sentence_manager.get_task_status(task_id)
    if not status:
        return {
            "task_id": task_id,
            "status": "not_found",
            "message": "任务不存在或已结束"
        }

    return status


@app.get("/task/{task_id}/audios")
async def get_task_audios(task_id: str):
    """获取任务的所有音频文件信息"""
    log_with_timestamp(f"获取任务音频列表请求: {task_id}", "INFO")
    task = sentence_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    audio_files = []

    for i in range(task['total_sentences']):
        if task['audio_paths'][i] and Path(task['audio_paths'][i]).exists():
            audio_path = task['audio_paths'][i]
            filename = Path(audio_path).name

            # 构建文件信息
            audio_info = {
                "sentence_index": i,
                "filename": filename,
                "sentence_text": task['sentences'][i] if i < len(task['sentences']) else f"句子 {i + 1}",
                "status": task['sentence_status'][i],
                "url": f"/audio/{task_id}/{filename}",
                "file_size": os.path.getsize(audio_path) if Path(audio_path).exists() else 0,
                "created_at": datetime.now().isoformat()
            }
            audio_files.append(audio_info)

    log_with_timestamp(f"返回任务 {task_id} 的 {len(audio_files)} 个音频文件信息", "INFO")

    return {
        "task_id": task_id,
        "total_sentences": task['total_sentences'],
        "completed_count": task['completed_count'],
        "status": task['status'],
        "audio_files": audio_files
    }


@app.get("/audio/{task_id}/{filename}")
async def serve_audio_file(task_id: str, filename: str):
    """提供生成的音频文件"""
    try:
        log_with_timestamp(f"音频文件请求: {filename} (任务: {task_id})", "INFO")

        # 首先在GPT-SoVITS输出目录查找
        gpt_output_dir = Path("C:\\Users\\24021\\Desktop\\GPT-SoVITS-main")
        file_path = gpt_output_dir / filename

        # 如果不在GPT目录，尝试在存储目录查找
        if not file_path.exists():
            file_path = STORAGE_DIR / filename

        # 如果还是找不到，尝试查找任务相关的文件
        if not file_path.exists():
            task = sentence_manager.get_task(task_id)
            if task:
                # 查找音频路径列表中的文件
                for audio_path in task['audio_paths']:
                    if audio_path and Path(audio_path).name == filename:
                        file_path = Path(audio_path)
                        break

        if file_path.exists() and file_path.is_file():
            log_with_timestamp(f"提供音频文件: {file_path}", "INFO")
            return FileResponse(
                file_path,
                media_type="audio/wav",
                filename=filename
            )

        log_with_timestamp(f"音频文件未找到: {filename}", "WARNING")
        raise HTTPException(status_code=404, detail="音频文件未找到")

    except Exception as e:
        log_with_timestamp(f"提供音频文件失败: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=f"文件服务错误: {str(e)}")


# 文件上传端点
@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    """上传WAV音频文件"""
    try:
        upload_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_with_timestamp(f"开始上传文件: {file.filename}", "INFO")

        if not file.filename.lower().endswith('.wav'):
            raise HTTPException(status_code=400, detail="只支持WAV格式文件")

        original_name = Path(file.filename).stem
        unique_filename = f"{original_name}_{uuid.uuid4().hex[:8]}.wav"
        file_path = STORAGE_DIR / unique_filename

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        upload_end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_with_timestamp(f"参考音频已保存: {file_path}", "INFO")
        log_with_timestamp(f"上传时间: {upload_start_time} -> {upload_end_time}", "INFO")
        log_with_timestamp(f"文件大小: {os.path.getsize(file_path)} bytes", "INFO")

        return {
            "filename": unique_filename,
            "original_name": original_name,
            "message": "参考音频上传成功",
            "created_at": datetime.now().isoformat(),
            "output_path": str(file_path),
            "file_size": os.path.getsize(file_path)
        }

    except Exception as e:
        log_with_timestamp(f"上传失败: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.on_event("startup")
async def startup_event():
    logger.info("启动GPT-SoVITS顺序语音API v3.2...")
    logger.info(f"存储目录: {STORAGE_DIR}")
    logger.info(f"脚本路径: {SCRIPT_PATH}")
    logger.info(f"日志文件: {log_file_path}")
    logger.info("模式: 直接调用script1.py生成音频")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )