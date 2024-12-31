import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import json
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm
import hashlib
import time


class photographDownload:
    def __init__(self):
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('download.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        # 设置请求会话
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.URL = "https://photo.baidu.com/youai/file/v2/download"
        self.json_path = Path("./json/")  # 存储图片元数据的路径
        self.save_path = Path("./photograph/")  # 存储下载图片的路径
        self.clienttype = None
        self.bdstoken = None
        self.failed_photos = set()  # 存储下载失败的照片文件名
        self.download_history = Path("./download_history.json")  # 下载历史文件
        self.failed_downloads = Path("./failed_downloads.json")  # 保存下载失败文件的记录
        self.max_workers = 32  # 并发下载数
        self.chunk_size = 1024 * 512  # 下载块大小
        self.max_file_size = 100 * 1024 * 1024  # 最大文件大小限制(100MB)

        # 创建必要的目录
        self.save_path.mkdir(parents=True, exist_ok=True)
        self.json_path.mkdir(parents=True, exist_ok=True)

        # 加载下载历史和失败记录
        self.failed_history = self.load_failed_downloads()
        self.history = self.load_download_history()

    def load_download_history(self):
        """加载下载历史记录"""
        self.logger.info("加载load_download_history")
        try:
            if self.download_history.exists():
                with open(self.download_history, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    return history
            return {}
        except Exception as e:
            self.logger.error(f"加载下载历史失败: {e}")
            return {}

    def load_failed_downloads(self):
        """加载下载失败文件记录"""
        self.logger.info("加载load_failed_downloads")
        try:
            if self.failed_downloads.exists():
                with open(self.failed_downloads, 'r', encoding='utf-8') as f:
                    failed_history = json.load(f)
                    return failed_history
            return {}
        except Exception as e:
            self.logger.error(f"加载失败文件记录失败: {e}")
            return {}

    def save_download_history(self):
        """保存下载历史记录"""
        try:
            with open(self.download_history, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存下载历史失败: {e}")

    def save_failed_downloads(self):
        """保存失败的文件记录"""
        try:
            with open(self.failed_downloads, 'w', encoding='utf-8') as f:
                json.dump(self.failed_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存失败文件记录失败: {e}")

    def validate_config(self, config):
        """验证配置信息"""
        required_fields = ["clienttype", "bdstoken", "Cookie"]
        return all(field in config and config[field] for field in required_fields)

    def load_config(self):
        """加载并验证配置文件"""
        try:
            settings_path = Path("settings.json")
            if not settings_path.exists():
                raise FileNotFoundError("配置文件 settings.json 不存在")

            with open(settings_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if not self.validate_config(config):
                raise ValueError("配置文件中的字段不完整或格式错误")

            return config
        except json.JSONDecodeError as e:
            self.logger.error(f"配置文件格式不正确: {str(e)}")
            sys.exit(1)

    def check_auth(self):
        """检查认证信息"""
        try:
            config = self.load_config()
            self.clienttype = config["clienttype"]
            self.bdstoken = config["bdstoken"]
            self.headers["Cookie"] = config["Cookie"]

            # 验证认证信息
            params = {
                "clienttype": self.clienttype,
                "bdstoken": self.bdstoken,
                "fsid": "test"
            }
            response = self.session.get(self.URL, params=params, headers=self.headers)
            response.raise_for_status()

            if "error_code" in response.json():
                raise ValueError("认证信息无效")
        except Exception as e:
            self.logger.error(f"认证检查失败: {str(e)}")
            sys.exit(1)

    def calculate_file_hash(self, filepath):
        """计算文件的MD5哈希值"""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def download_with_resume(self, url, filepath, file_size=None):
        """支持断点续传的下载函数"""
        headers = self.headers.copy()
        mode = 'ab'

        if filepath.exists():
            current_size = filepath.stat().st_size
            if file_size and current_size >= file_size:
                return True
            headers["Range"] = f"bytes={current_size}-"
        else:
            current_size = 0
            mode = 'wb'

        try:
            with self.session.get(url, headers=headers, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0)) + current_size

                if total_size > self.max_file_size:
                    raise ValueError(f"文件大小超过限制: {total_size} > {self.max_file_size}")

                with open(filepath, mode) as f:
                    with tqdm(
                        total=total_size,
                        initial=current_size,
                        unit='iB',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=filepath.name
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            if chunk:
                                size = f.write(chunk)
                                pbar.update(size)
            return True
        except Exception as e:
            self.logger.error(f"下载失败 {filepath.name}: {str(e)}")
            return False

    def validate_downloaded_file(self, file_id, save_path):
        """校验下载的文件完整性"""
        if not save_path.exists():
            return False
        if file_id in self.history:
            expected_hash = self.history[file_id].get('hash')
            if self.calculate_file_hash(save_path) == expected_hash:
                return True
        return False

    def download_single_photo(self, date, filename, fsid):
        """下载单张照片"""
        try:
            # 安全过滤文件名
            safe_filename = Path(filename).name
            save_path = self.save_path / date / safe_filename
            file_id = f"{date}_{safe_filename}_{fsid}"

            # 检查是否已下载并验证完整性
            if self.validate_downloaded_file(file_id, save_path):
                self.logger.info(f"文件已下载且验证通过: {safe_filename}")
                return True

            # 创建保存目录
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 获取下载链接
            params = {
                "clienttype": self.clienttype,
                "bdstoken": self.bdstoken,
                "fsid": fsid
            }
            response = self.session.get(self.URL, params=params, headers=self.headers)
            response.raise_for_status()

            r_json = response.json()
            if "error_code" in r_json:
                raise Exception(f"获取下载链接失败: {r_json.get('error_msg')}")

            # 下载文件
            if self.download_with_resume(r_json['dlink'], save_path):
                # 计算文件哈希值并记录下载历史
                file_hash = self.calculate_file_hash(save_path)
                self.history[file_id] = {
                    "timestamp": time.time(),
                    "hash": file_hash,
                    "date": date,
                    "filename": safe_filename,
                    "fsid": fsid,
                    "size": save_path.stat().st_size
                }

                # 立即保存下载历史到文件
                self.save_download_history()

                # 删除失败记录文件中的该文件
                if file_id in self.failed_history:
                    del self.failed_history[file_id]
                    self.save_failed_downloads()

                self.logger.info(f"成功下载并保存记录: {safe_filename}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"处理文件 {filename} 失败: {str(e)}")
            #self.failed_photos.append(filename)

            # 将文件记录到失败下载文件
            if file_id not in self.failed_history:
                self.failed_history[file_id] = {
                    "date": date,
                    "filename": filename,
                    "fsid": fsid
                }
                self.save_failed_downloads()

            return False

    def download_photos(self):
        """并发下载所有照片"""
        try:
            files = list(self.json_path.glob("*.json"))
            total_files = len(files)

            if total_files == 0:
                self.logger.warning("没有找到要下载的文件")
                return

            self.logger.info(f"总文件数: {total_files}")
            self.logger.info(f"正在检查需要下载的文件")
            # 优先下载失败文件
            pending_files = []
            for file in files:
                try:
                    with open(file, 'r', encoding="utf-8") as f:
                        json_data = json.load(f)

                    date = json_data["extra_info"]["date_time"][:10].replace(':', '-')
                    filename = json_data["path"][12:]
                    fsid = json_data["fsid"]
                    file_id = f"{date}_{Path(filename).name}_{fsid}"

                    # 如果文件未下载或已经失败，加入待下载列表
                    if file_id in self.failed_history:
                        pending_files.append((file, date, filename, fsid))
                    elif not self.validate_downloaded_file(file_id, self.save_path / date / Path(filename).name):
                        pending_files.append((file, date, filename, fsid))
                except Exception as e:
                    self.logger.error(f"处理文件 {file.name} 元数据失败: {str(e)}")

            self.logger.info(f"待下载文件数: {len(pending_files)}")

            retries = 0
            max_retries = 5

            while retries < max_retries and pending_files:
                failed_files = []
                self.logger.info(f"第 {retries + 1} 次尝试下载，待处理文件: {len(pending_files)}")

                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = [
                        executor.submit(self.download_single_photo, date, filename, fsid)
                        for _, date, filename, fsid in pending_files
                    ]
                    with tqdm(total=len(futures), desc=f"重试 {retries + 1} 进度") as pbar:
                        for future, file in zip(as_completed(futures), pending_files):
                            _, date, filename, fsid = file
                            try:
                                if not future.result():
                                    failed_files.append(file)
                            except Exception as e:
                                self.logger.error(f"文件 {filename} 下载失败: {str(e)}")
                                failed_files.append(file)
                            finally:
                                pbar.update(1)

                pending_files = failed_files
                retries += 1

            if pending_files:
                self.logger.warning(f"以下文件在最大重试次数 ({max_retries}) 后仍然下载失败：")
                for _, _, filename, _ in pending_files:
                    self.logger.warning(f"- {filename}")
                    self.failed_photos.add(filename)
        finally:
            self.save_download_history()
            self.save_failed_downloads()

    def print_summary(self):
        """打印下载总结"""
        total_files = len(list(self.json_path.glob("*.json")))

        successful = total_files - len(self.failed_photos)

        self.logger.info(f"\n下载完成摘要:")
        self.logger.info(f"总文件数: {total_files}")
        self.logger.info(f"成功下载: {successful}")
        self.logger.info(f"失败文件数: {len(self.failed_photos)}")

        if self.failed_photos:
            self.logger.info("\n失败的文件:")
            for filename in self.failed_photos:
                self.logger.info(f"- {filename}")

    def start(self):
        """启动下载流程"""
        try:
            self.logger.info("开始下载流程")
            self.check_auth()
            self.download_photos()
            self.print_summary()
        except KeyboardInterrupt:
            self.logger.warning("\n下载被用户中断")
            self.save_download_history()
            self.save_failed_downloads()
            self.print_summary()
            sys.exit(0)
        except Exception as e:
            self.logger.error(f"下载过程发生错误: {str(e)}")
            self.save_download_history()
            self.save_failed_downloads()
            self.print_summary()
            sys.exit(1)


if __name__ == "__main__":
    baidu_photo = photographDownload()
    baidu_photo.start()
