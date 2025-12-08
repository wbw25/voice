import requests
import json
import argparse
import os
import sys
from pathlib import Path
import shutil
import uuid
from io import BytesIO
import traceback

# 设置固定的输出目录
FIXED_OUTPUT_DIR = Path(r"C:\Users\24021\Desktop\backend\voice_and_output")


# 如果选择利用script1.py直接生成的话，修改路径如下
# ROOT_DIR = Path(__file__).parent  获取当前脚本所在目录的父目录（根目录）
# FIXED_OUTPUT_DIR = ROOT_DIR

class GPTSoVITSClientV2:
    """GPT-SoVITS API客户端类 (v2版本)"""

    def __init__(self, base_url="http://127.0.0.1:9880", output_dir=None):
        """
        初始化客户端

        Args:
            base_url: API服务地址，默认 http://127.0.0.1:9880
            output_dir: 输出目录，如果为None则使用固定目录
        """
        self.base_url = base_url.rstrip('/')
        self.tts_endpoint = "/tts"
        self.control_endpoint = "/control"
        self.set_gpt_weights_endpoint = "/set_gpt_weights"
        self.set_sovits_weights_endpoint = "/set_sovits_weights"
        self.set_refer_audio_endpoint = "/set_refer_audio"

        # 设置输出目录
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = FIXED_OUTPUT_DIR

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def check_connection(self, timeout=5):
        """检查API服务是否可用"""
        try:
            response = requests.get(f"{self.base_url}{self.tts_endpoint}", timeout=timeout)
            return True
        except requests.exceptions.ConnectionError:
            return False
        except requests.exceptions.RequestException:
            return False

    def text_to_speech(self, text, text_lang, ref_audio_path, **kwargs):
        """
        文本转语音主方法

        Args:
            text: 要合成的文本
            text_lang: 文本语言，如 "zh", "en", "ja", "ko" 等
            ref_audio_path: 参考音频路径
            **kwargs: 其他可选参数

        Returns:
            audio_data: 音频字节数据
        """
        # 基本参数
        params = {
            "text": text,
            "text_lang": text_lang.lower() if text_lang else "zh",
            "ref_audio_path": ref_audio_path,
            "prompt_text": kwargs.get("prompt_text", ""),
            "prompt_lang": kwargs.get("prompt_lang", text_lang.lower() if text_lang else "zh"),
        }

        # 可选参数
        optional_params = {
            "top_k": kwargs.get("top_k", 5),
            "top_p": kwargs.get("top_p", 1.0),
            "temperature": kwargs.get("temperature", 1.0),
            "text_split_method": kwargs.get("text_split_method", "cut5"),
            "batch_size": kwargs.get("batch_size", 1),
            "batch_threshold": kwargs.get("batch_threshold", 0.75),
            "speed_factor": kwargs.get("speed_factor", 1.0),
            "fragment_interval": kwargs.get("fragment_interval", 0.3),
            "seed": kwargs.get("seed", -1),
            "media_type": kwargs.get("media_type", "wav"),
            "streaming_mode": kwargs.get("streaming_mode", False),
            "parallel_infer": kwargs.get("parallel_infer", True),
            "repetition_penalty": kwargs.get("repetition_penalty", 1.35),
            "split_bucket": kwargs.get("split_bucket", True)
        }

        # 添加可选参数（过滤掉None值）
        for key, value in optional_params.items():
            if value is not None:
                params[key] = value

        try:
            response = requests.get(f"{self.base_url}{self.tts_endpoint}", params=params, timeout=300)

            if response.status_code == 200:
                return response.content
            else:
                try:
                    error_info = response.json()
                    error_msg = f"语音合成失败: {error_info.get('message', '未知错误')}"
                    if "Exception" in error_info:
                        error_msg += f"\n异常详情: {error_info['Exception']}"
                except:
                    error_msg = f"语音合成失败，HTTP状态码: {response.status_code}"
                raise Exception(error_msg)

        except requests.exceptions.Timeout:
            raise Exception("请求超时，GPT-SoVITS服务响应时间过长")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")

    def save_audio(self, audio_data, output_filename=None):
        """
        保存音频数据到指定目录

        Args:
            audio_data: 音频字节数据
            output_filename: 输出文件名，如果为None则生成唯一名称

        Returns:
            保存的文件路径
        """
        if output_filename is None:
            # 生成唯一文件名
            output_filename = f"output_{uuid.uuid4().hex[:8]}.wav"

        output_path = self.output_dir / output_filename

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 直接写入WAV文件
            with open(output_path, 'wb') as f:
                f.write(audio_data)

            return str(output_path)

        except Exception as e:
            raise Exception(f"保存音频失败: {e}")

    def save_as_default_output(self, audio_data, task_id=None):
        """
        保存音频为output.wav，并创建一个带任务ID的副本

        Args:
            audio_data: 音频字节数据
            task_id: 任务ID（可选）

        Returns:
            (output_path, unique_path): 默认输出路径和唯一路径
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 生成默认输出路径
        default_output_path = self.output_dir / "output.wav"

        try:
            # 保存为默认output.wav
            with open(default_output_path, 'wb') as f:
                f.write(audio_data)

            # 如果提供了task_id，创建一个唯一命名的副本
            if task_id:
                unique_filename = f"output_{task_id}.wav"
                unique_path = self.output_dir / unique_filename
                shutil.copy2(default_output_path, unique_path)
                return str(default_output_path), str(unique_path)

            return str(default_output_path), None

        except Exception as e:
            raise Exception(f"保存音频失败: {e}")


def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description="GPT-SoVITS API客户端 (v2版本) - 定制版")
    parser.add_argument("--url", default="http://127.0.0.1:9880", help="API服务地址")
    parser.add_argument("--text", required=True, help="要合成的文本")
    parser.add_argument("--text-lang", default="zh", help="文本语言，如 zh, en, ja, ko")
    parser.add_argument("--ref-audio", required=True, help="参考音频文件路径")
    parser.add_argument("--prompt-text", default="", help="参考音频文本")
    parser.add_argument("--prompt-lang", help="参考音频语言，默认与文本语言相同")
    parser.add_argument("--output-dir", default=str(FIXED_OUTPUT_DIR),
                        help=f"输出目录，默认: {FIXED_OUTPUT_DIR}")
    parser.add_argument("--output-name", help="输出文件名，默认生成唯一名称")
    parser.add_argument("--task-id", help="任务ID，用于生成唯一命名的副本")
    parser.add_argument("--top-k", type=int, default=5, help="top_k参数")
    parser.add_argument("--top-p", type=float, default=1.0, help="top_p参数")
    parser.add_argument("--temperature", type=float, default=1.0, help="temperature参数")
    parser.add_argument("--speed", type=float, default=1.0, help="语速因子")
    parser.add_argument("--method", default="cut5", help="文本切分方法")
    parser.add_argument("--clean-old", action="store_true", help="清理旧的output.wav文件")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 创建客户端
    client = GPTSoVITSClientV2(base_url=args.url, output_dir=args.output_dir)

    # 检查连接
    if not client.check_connection():
        result = {
            "status": "error",
            "message": "无法连接到GPT-SoVITS API服务，请确保api_v2.py正在运行"
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # 清理旧文件（如果需要）
    if args.clean_old:
        try:
            output_path = Path(args.output_dir) / "output.wav"
            if output_path.exists():
                backup_name = f"output_backup_{uuid.uuid4().hex[:8]}.wav"
                backup_path = Path(args.output_dir) / backup_name
                shutil.move(output_path, backup_path)
        except:
            pass

    # 进行TTS合成
    try:
        # 准备参数
        kwargs = {
            "prompt_text": args.prompt_text,
            "prompt_lang": args.prompt_lang if args.prompt_lang else args.text_lang,
            "top_k": args.top_k,
            "top_p": args.top_p,
            "temperature": args.temperature,
            "speed_factor": args.speed,
            "text_split_method": args.method
        }

        if args.verbose:
            print(f"文本: {args.text[:100]}...")
            print(f"参考音频: {args.ref_audio}")
            print(f"参数: {kwargs}")

        # 合成语音
        audio_data = client.text_to_speech(
            text=args.text,
            text_lang=args.text_lang,
            ref_audio_path=args.ref_audio,
            **kwargs
        )

        # 保存音频
        if args.task_id:
            # 保存为output.wav并创建带任务ID的副本
            default_path, unique_path = client.save_as_default_output(audio_data, args.task_id)

            # 返回JSON格式的结果供后端解析
            result = {
                "status": "success",
                "message": "语音合成成功",
                "default_output": default_path,
                "unique_output": unique_path,
                "task_id": args.task_id,
                "audio_size": len(audio_data)
            }

            if args.verbose:
                result.update({
                    "text": args.text,
                    "ref_audio": args.ref_audio,
                    "parameters": kwargs
                })

            print(json.dumps(result, indent=2))

        else:
            # 保存为指定名称或默认名称
            output_path = client.save_audio(audio_data, args.output_name)

            result = {
                "status": "success",
                "message": "语音合成成功",
                "output_path": output_path,
                "audio_size": len(audio_data)
            }

            if args.verbose:
                result.update({
                    "text": args.text,
                    "ref_audio": args.ref_audio,
                    "parameters": kwargs
                })

            print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }

        if args.verbose:
            error_result["traceback"] = traceback.format_exc()

        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()