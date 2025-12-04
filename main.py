from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
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
import asyncio
import threading
import time
import requests
from typing import Optional
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="GPT-SoVITS音频处理API", version="1.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置存储路径
BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "voice_and_output"
STORAGE_DIR.mkdir(exist_ok=True)

# GPT-SoVITS配置
GPT_SOVITS_API_URL = "http://127.0.0.1:9880"  # GPT-SoVITS API地址
GPT_SOVITS_DIR = Path(r"C:/Users/24021/Desktop/GPT-SoVITS-main")  # 修改为您的实际路径
SCRIPT1_PATH = GPT_SOVITS_DIR / "script1.py"  # script1.py路径


class TextRequest(BaseModel):
    text: str
    ref_audio_path: str  # 改为必填字段
    language: str = "zh"


class AudioResponse(BaseModel):
    filename: str
    message: str
    created_at: str
    output_path: str = None


class ProcessingTask(BaseModel):
    task_id: str
    status: str
    text: str
    ref_audio: str
    output_file: str = None
    created_at: str
    completed_at: str = None
    error: str = None


# 任务存储
processing_tasks = {}


def check_gpt_sovits_api():
    """检查GPT-SoVITS API是否可用"""
    try:
        # 尝试访问一个存在的端点，比如 /tts 或 /control
        response = requests.get(f"{GPT_SOVITS_API_URL}/control", params={"command": "restart"}, timeout=2)
        # 或者直接检查服务是否在运行
        # response = requests.get(f"{GPT_SOVITS_API_URL}", timeout=2)
        return True if response.status_code < 500 else False
    except requests.exceptions.ConnectionError:
        logger.warning("无法连接到GPT-SoVITS API")
        return False
    except Exception as e:
        logger.warning(f"检查GPT-SoVITS API时出错: {e}")
        return False


def start_gpt_sovits_api():
    """启动GPT-SoVITS API服务"""
    try:
        # 检查API是否已在运行
        if check_gpt_sovits_api():
            logger.info("GPT-SoVITS API已在运行")
            return True

        # 启动API
        api_script = GPT_SOVITS_DIR / "api_v2.py"
        if api_script.exists():
            logger.info("正在启动GPT-SoVITS API...")
            # 这里可以启动子进程，但为了简单，我们假设API已手动启动
            return True
        else:
            logger.error(f"找不到api_v2.py: {api_script}")
            return False
    except Exception as e:
        logger.error(f"启动GPT-SoVITS API失败: {e}")
        return False


def run_script1(text: str, ref_audio_path: str, task_id: str):
    """直接调用GPT-SoVITS API生成音频"""
    try:
        GPT_SOVITS_API = "http://127.0.0.1:9880"

        # 构建请求参数
        params = {
            "text": text,
            "text_lang": "zh",
            "ref_audio_path": ref_audio_path,
            "prompt_lang": "zh",
            "prompt_text": "",
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut5",
            "batch_size": 1,
            "speed_factor": 1.0,
            "media_type": "wav"
        }

        logger.info(f"调用GPT-SoVITS API: {params}")

        # 调用API
        response = requests.get(f"{GPT_SOVITS_API}/tts", params=params, timeout=300)

        if response.status_code == 200:
            # 保存音频文件
            output_dir = Path(__file__).parent / "voice_and_output"
            output_dir.mkdir(exist_ok=True)

            # 生成唯一文件名
            unique_name = f"output_{task_id}.wav"
            unique_path = output_dir / unique_name

            # 保存音频文件
            with open(unique_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"音频文件已保存: {unique_path}, 大小: {os.path.getsize(unique_path)} bytes")

            processing_tasks[task_id].status = "completed"
            processing_tasks[task_id].output_file = str(unique_path)
            processing_tasks[task_id].completed_at = datetime.now().isoformat()

            return str(unique_path)
        else:
            try:
                error_info = response.json()
                error_msg = f"GPT-SoVITS API调用失败: {error_info.get('message', '未知错误')}"
            except:
                error_msg = f"GPT-SoVITS API调用失败，状态码: {response.status_code}"
            raise Exception(error_msg)

    except Exception as e:
        logger.error(f"调用GPT-SoVITS API失败: {e}")
        processing_tasks[task_id].status = "failed"
        processing_tasks[task_id].error = str(e)
        processing_tasks[task_id].completed_at = datetime.now().isoformat()
        raise

@app.get("/")
async def root():
    """根端点"""
    return {
        "message": "GPT-SoVITS音频处理API服务运行中",
        "status": "ok",
        "gpt_sovits_api_available": check_gpt_sovits_api()
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    gpt_sovits_status = "available" if check_gpt_sovits_api() else "unavailable"

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "storage_dir": str(STORAGE_DIR),
        "gpt_sovits_status": gpt_sovits_status,
        "endpoints": {
            "upload": "/upload",
            "process": "/process",
            "files": "/files"
        }
    }

@app.post("/upload", response_model=AudioResponse)
async def upload_audio(file: UploadFile = File(...)):
    """
    上传WAV音频文件作为参考音频
    """
    try:
        # 检查文件类型
        if not file.filename.lower().endswith('.wav'):
            raise HTTPException(status_code=400, detail="只支持WAV格式文件")

        # 生成唯一文件名（保留原始文件名便于识别）
        original_name = Path(file.filename).stem
        unique_filename = f"{original_name}_{uuid.uuid4().hex[:8]}.wav"
        file_path = STORAGE_DIR / unique_filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"参考音频已保存: {file_path}")

        return AudioResponse(
            filename=unique_filename,
            message=f"参考音频上传成功",
            created_at=datetime.now().isoformat(),
            output_path=str(file_path)
        )

    except Exception as e:
        logger.error(f"上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.post("/process", response_model=dict)
async def process_text(request: TextRequest, background_tasks: BackgroundTasks):
    """
    处理文本并生成音频文件
    """
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="文本内容不能为空")

        # 检查参考音频文件是否存在
        ref_audio_path = Path(request.ref_audio_path)
        if not ref_audio_path.exists():
            # 先在当前存储目录查找
            stored_path = STORAGE_DIR / ref_audio_path.name
            if stored_path.exists():
                ref_audio_path = stored_path
            else:
                raise HTTPException(status_code=404, detail=f"参考音频文件不存在: {request.ref_audio_path}")

        # 生成任务ID
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # 创建任务记录
        task = ProcessingTask(
            task_id=task_id,
            status="processing",
            text=request.text,
            ref_audio=str(ref_audio_path),
            created_at=datetime.now().isoformat()
        )

        processing_tasks[task_id] = task

        # 在后台运行音频生成
        background_tasks.add_task(
            run_script1,
            text=request.text,
            ref_audio_path=str(ref_audio_path),
            task_id=task_id
        )

        return {
            "task_id": task_id,
            "status": "started",
            "message": "音频生成任务已开始",
            "created_at": task.created_at,
            "check_status_url": f"/task/{task_id}/status",
            "ref_audio": str(ref_audio_path)  # 返回实际使用的路径
        }

    except Exception as e:
        logger.error(f"处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = processing_tasks[task_id]

    response = {
        "task_id": task.task_id,
        "status": task.status,
        "text": task.text,
        "ref_audio": task.ref_audio,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "error": task.error
    }

    if task.status == "completed" and task.output_file:
        response["output_file"] = task.output_file
        response["download_url"] = f"/audio/{Path(task.output_file).name}"

    return response


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """
    获取生成的音频文件
    """
    file_path = STORAGE_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="无效的文件路径")

    # 检查文件大小
    file_size = file_path.stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=500, detail="音频文件为空")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(file_size)
        }
    )


@app.get("/files")
async def list_files():
    """
    列出所有音频文件
    """
    files = []
    for file_path in STORAGE_DIR.glob("*.wav"):
        stats = file_path.stat()
        files.append({
            "filename": file_path.name,
            "path": str(file_path),
            "size": stats.st_size,
            "created_at": datetime.fromtimestamp(stats.st_ctime).isoformat(),
            "is_output": "output_" in file_path.name,
            "is_uploaded": "output_" not in file_path.name
        })

    # 按创建时间排序（最新的在前面）
    files.sort(key=lambda x: x["created_at"], reverse=True)

    return {"files": files, "count": len(files)}


@app.delete("/audio/{filename}")
async def delete_audio(filename: str):
    """删除音频文件"""
    try:
        file_path = STORAGE_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        file_path.unlink()

        logger.info(f"已删除文件: {filename}")

        return {"message": f"文件 {filename} 已删除", "success": True}

    except Exception as e:
        logger.error(f"删除文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@app.get("/cleanup")
async def cleanup_old_files(days: int = 7):
    """清理旧文件"""
    try:
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        deleted_files = []

        for file_path in STORAGE_DIR.glob("*"):
            if file_path.is_file():
                file_age = time.time() - file_path.stat().st_ctime
                if file_age > cutoff_time:
                    file_path.unlink()
                    deleted_files.append(file_path.name)

        return {
            "message": f"已清理 {len(deleted_files)} 个文件",
            "deleted_files": deleted_files,
            "success": True
        }

    except Exception as e:
        logger.error(f"清理文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")


# 启动时检查GPT-SoVITS API
@app.on_event("startup")
async def startup_event():
    logger.info("启动GPT-SoVITS音频处理API...")
    logger.info(f"存储目录: {STORAGE_DIR}")
    logger.info(f"GPT-SoVITS目录: {GPT_SOVITS_DIR}")

    # 检查GPT-SoVITS API
    if check_gpt_sovits_api():
        logger.info("✓ GPT-SoVITS API可用")
    else:
        logger.warning("⚠ GPT-SoVITS API不可用，请确保已启动api_v2.py")
        logger.info(f"请手动启动: python {GPT_SOVITS_DIR}/api_v2.py")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )