import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Union, Callable, Optional
from urllib.parse import urljoin, unquote

import httpx

logger = logging.getLogger(__name__)

class AiServer:
    API_PATH = "internal/api"
    REGISTER_API = API_PATH + "/register"
    HEARTBEAT_API = API_PATH + "/heartbeat"
    DOWNLOAD_DATASET_API = API_PATH + "/file"

    FILE_CHUNK_SIZE = 1024 * 1024

    def __init__(self, platform_url: str):
        logger.info("platform_url: %s", platform_url)
        AiServer._check_str_param(platform_url)

        self._platformUrl = platform_url

    @staticmethod
    def _check_str_param(param: str):
        if param is None or param.strip() == "":
            raise ValueError(f"{param} is invalid")

    @staticmethod
    def _check_int_param(param: int):
        if param is None or param <= 0:
            raise ValueError(f"{param} is invalid")

    @property
    def platform_url(self):
        return self._platformUrl

    @platform_url.setter
    def platform_url(self, value: str):
        AiServer._check_str_param(value)
        self._platformUrl = value

    @staticmethod
    def _send_request(url: str,
                      response_handler: Callable[[Optional[httpx.Response], Optional[dict],
                                                  Optional[dict]], bool | str | None],
                      method: str = "POST",
                      params: dict = None,
                      json_data: dict = None,
                      headers: dict = None,
                      extra: dict = None,
                      timeout: float = 5.0) -> bool:
        if headers is None:
            headers = {"Content-Type": "application/json; charset=UTF-8"}
        headers["from"] = "Y"

        try:
            response = httpx.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            if method == "GET":
                return response_handler(response, params, extra)
            else:
                return response_handler(response, json_data, extra)
        except httpx.HTTPStatusError as e:
            logger.error("HTTP 错误: %s - %s", e.response.status_code, e.response.text)
            return False
        except httpx.RequestError as e:
            logger.error("请求错误", exc_info=True)
            return False
        except Exception as e:
            logger.error("未知错误: ", exc_info=True)
            return False

    @staticmethod
    def _handle_http_ok_response(response: Optional[httpx.Response],
                                 payload: Optional[dict],
                                 extra: Optional[dict]) -> bool:
        if response is None:
            logger.error("response is None")
            return False

        response_data = response.json()
        if response_data.get("code") == 0:
            logger.warning("请求成功: %s", response_data.get("data"))
            return True
        else:
            logger.error("请求失败 (code: %s): {%s}",
                          response_data.get('code'), response_data.get('msg'))
            return False

    def _get_register_url(self):
        return urljoin(self._platformUrl, AiServer.REGISTER_API)

    def _register(self, port: int, description: str, params: str):
        AiServer._check_str_param(description)
        AiServer._check_str_param(params)
        self._check_int_param(port)

        payload = {
            "server": str(port),
            "description": description,
            "params": params
        }
        headers = {"Content-Type": "application/json; charset=UTF-8"}

        return AiServer._send_request(
            url=self._get_register_url(),
            response_handler=AiServer._handle_http_ok_response,
            method="POST",
            json_data=payload,
            headers=headers,
            timeout=5.0)

    def _get_heartbeat_url(self):
        return urljoin(self._platformUrl, AiServer.HEARTBEAT_API)

    def heartbeat(self, port: int):
        self._check_int_param(port)
        params = {
            "port": port
        }

        return self._send_request(
            url=self._get_heartbeat_url(),
            response_handler=AiServer._handle_http_ok_response,
            method="GET",
            params=params,
            timeout=5.0)

    def _get_dataset_url(self):
        return urljoin(self._platformUrl, AiServer.DOWNLOAD_DATASET_API)

    def _get_create_dataset_file(self, dataset_dir: str, filename: str) -> str:
        dataset_dir_path = Path(dataset_dir)
        file_path = dataset_dir_path / filename
        return file_path.as_posix()

    @staticmethod
    def _get_filename_from_content_disposition(content_disposition) -> str | None:
        logger.info("content_disposition: %s", content_disposition)
        if not content_disposition:
            return None
        filename = None

        filename_star_pattern = r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)"
        filename_star_match = re.search(filename_star_pattern, content_disposition, re.IGNORECASE)
        if filename_star_match:
            encoded_filename = filename_star_match.group(1).strip()
            encoded_filename = encoded_filename.strip('"')
            try:
                filename = unquote(encoded_filename)
                return filename
            except Exception as e:
                logger.error("解码filename*参数失败", exc_info=True)

        filename_pattern = r'filename\s*=\s*"([^"]+)"'
        filename_match = re.search(filename_pattern, content_disposition, re.IGNORECASE)
        if not filename_match:
            filename_pattern2 = r'filename\s*=\s*([^;]+)'
            filename_match = re.search(filename_pattern2, content_disposition, re.IGNORECASE)
        if filename_match:
            encoded_filename = filename_match.group(1).strip()
            encoded_filename = encoded_filename.strip('"')
            try:
                filename = unquote(encoded_filename)
            except Exception as e:
                logger.error("解码filename*参数失败", exc_info=True)
                filename = encoded_filename
        return filename

    @staticmethod
    def _get_default_dataset_filename(payload: dict) -> str:
        dataset_id = payload.get("datasetId")
        if not dataset_id:
            raise ValueError("dataset_id is none")

        label_id = payload.get("labelId")
        if not label_id:
            raise ValueError("label_id is none")
        return f"{dataset_id}_{label_id}.json"

    def _handle_dataset_download_response(self, response: Optional[httpx.Response],
                                          payload: Optional[dict],
                                          extra: Optional[dict]) -> str | bool:
        if response is None:
            logger.error("response is None")
            return False

        # content_disposition = response.headers.get('Content-Disposition', '')
        # file_name = AiServer._get_filename_from_content_disposition(content_disposition)
        # if file_name is None:
        file_name = AiServer._get_default_dataset_filename(payload)
        save_file = self._get_create_dataset_file(extra["dataset_dir"], file_name)

        with open(save_file, 'wb') as f:
            for chunk in response.iter_bytes(chunk_size=AiServer.FILE_CHUNK_SIZE):
                f.write(chunk)
        return save_file

    @staticmethod
    def _handle_dataset_response(response: Optional[httpx.Response],
                                 payload: Optional[dict],
                                 extra: Optional[dict]) -> str:
        if response is None:
            print("response is None")
            raise ValueError("response is none")

        return response.json()

    def _download_dataset(self, dataset_id: int, label_id: int, dataset_dir: str):
        AiServer._check_int_param(dataset_id)
        AiServer._check_int_param(label_id)

        params = {
            "datasetId": dataset_id,
            "labelId": label_id
        }
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        return AiServer._send_request(
            url=self._get_dataset_url(),
            response_handler=self._handle_dataset_download_response,
            method="GET",
            params=params,
            headers=headers,
            extra={"dataset_dir": dataset_dir},
            timeout=5.0)

    def register_server(self, port: int, description: str, params: str, max_retries: int = 30):
        for i in range(max_retries):
            ret = self._register(port=port, description=description, params=params)
            if ret:
                return ret
            else:
                logger.info("register_server retry %d", i)
                time.sleep(1)
        return False

    def download_dataset(self, dataset_id: int, label_id: int,
                         dataset_dir: str,
                         max_retries: int = 15):
        for i in range(max_retries):
            ret = self._download_dataset(dataset_id=dataset_id, label_id=label_id, dataset_dir=dataset_dir)
            if ret:
                return ret
            else:
                logger.info("download_dataset retry %d", i)
                time.sleep(1)
        return False