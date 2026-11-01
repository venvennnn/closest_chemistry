from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from app.config import get_settings
from app.services.storage import get_bytes, put_bytes, new_key

YOU_CAM_FILE = "/s2s/v2.0/file"
YOU_CAM_TASK = "/s2s/v2.0/task/cloth-v4"


class YouCamError(RuntimeError):
    def __init__(self, message: str, reconcile: bool = False):
        super().__init__(message)
        self.reconcile = reconcile


def request_digest(**parts: Any) -> str:
    joined = "|".join(f"{key}={parts[key]}" for key in sorted(parts))
    return hashlib.sha256(joined.encode()).hexdigest()


class YouCamAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.youcam_api_key}",
            "Content-Type": "application/json",
        }

    def ensure_ready(self, category: str) -> None:
        missing = self.settings.missing_youcam()
        if missing:
            raise YouCamError(missing)
        if category not in self.settings.youcam_category_list:
            raise YouCamError(
                f"Category {category} is not live-verified. Enabled: "
                f"{', '.join(self.settings.youcam_category_list) or '(none)'}. "
                "Official docs conflict on lower-body product-only references; "
                "those stay disabled until consented live inputs succeed."
            )

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.youcam_base_url.rstrip("/"), timeout=30.0)

    def upload_file(self, data: bytes, filename: str, content_type: str) -> str:
        with self._client() as client:
            created = client.post(
                YOU_CAM_FILE,
                headers=self._headers(),
                json={"files": [{"content_type": content_type, "file_name": filename, "file_size": len(data)}]},
            )
            if created.status_code in {401, 403}:
                raise YouCamError(
                    "YouCam rejected the file session (401/403). Check YOU_CAM_API_KEY and account/region access."
                )
            if created.status_code >= 400:
                raise YouCamError(f"YouCam file API returned {created.status_code}.")
            body = created.json().get("data", {}).get("files", [{}])[0]
            file_id = body.get("file_id")
            requests = body.get("requests") or []
            if not file_id or not requests:
                raise YouCamError("YouCam file API omitted file_id or upload URL.", reconcile=True)
            upload = requests[0]
            put = httpx.request(
                upload.get("method", "PUT"),
                upload["url"],
                headers=upload.get("headers") or {"Content-Type": content_type},
                content=data,
                timeout=60.0,
            )
            if put.status_code >= 400:
                raise YouCamError("Presigned upload failed.", reconcile=True)
            return file_id

    def create_task(self, src_file_id: str, ref_file_id: str, category: str) -> str:
        with self._client() as client:
            response = client.post(
                YOU_CAM_TASK,
                headers=self._headers(),
                json={
                    "src_file_id": src_file_id,
                    "ref_file_id": ref_file_id,
                    "garment_category": category,
                    "filter_multi_person": "normal",
                },
            )
            if response.status_code == 429:
                raise YouCamError("YouCam rate-limited the task create. Retry-After must be honoured by the worker.")
            if response.status_code >= 400:
                raise YouCamError(f"YouCam task create returned {response.status_code}.", reconcile=True)
            task_id = response.json().get("data", {}).get("task_id")
            if not task_id:
                raise YouCamError("YouCam omitted task_id. Reconcile before resubmitting.", reconcile=True)
            return task_id

    def poll_task(self, task_id: str) -> dict[str, Any]:
        deadline = time.time() + self.settings.youcam_poll_timeout_seconds
        last_status = "unknown"
        while time.time() < deadline:
            with self._client() as client:
                response = client.get(f"{YOU_CAM_TASK}/{task_id}", headers=self._headers())
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After") or self.settings.youcam_poll_interval_seconds)
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                raise YouCamError(f"YouCam poll returned {response.status_code}.")
            payload = response.json().get("data", {})
            last_status = payload.get("task_status") or payload.get("status") or "unknown"
            if last_status == "success":
                return payload
            if last_status in {"error", "failed"}:
                raise YouCamError(payload.get("error") or "YouCam task failed.")
            time.sleep(self.settings.youcam_poll_interval_seconds)
        raise YouCamError(f"YouCam task {task_id[:8]}… timed out (last status {last_status}).")

    def copy_result(self, owner_id: str, result_url: str) -> tuple[str, bytes]:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(result_url)
            if response.status_code >= 400:
                raise YouCamError("Could not copy the YouCam result before the provider URL expired.")
            data = response.content
        key = put_bytes(owner_id, new_key("tryon", "jpg"), data, "image/jpeg")
        return key, data

    def run_single(
        self,
        owner_id: str,
        source_bytes: str | bytes,
        reference_bytes: bytes,
        category: str,
        source_mime: str = "image/jpeg",
        reference_mime: str = "image/jpeg",
    ) -> dict[str, Any]:
        self.ensure_ready(category)
        src_bytes = source_bytes if isinstance(source_bytes, bytes) else get_bytes(source_bytes)
        src_id = self.upload_file(src_bytes, "source.jpg", source_mime)
        ref_id = self.upload_file(reference_bytes, "reference.jpg", reference_mime)
        task_id = self.create_task(src_id, ref_id, category)
        payload = self.poll_task(task_id)
        url = (payload.get("results") or {}).get("url")
        if not url:
            raise YouCamError("YouCam success payload omitted a result URL.")
        storage_key, data = self.copy_result(owner_id, url)
        return {
            "provider_task_id": task_id,
            "storage_key": storage_key,
            "bytes": data,
            "raw_status": payload.get("task_status"),
            "units_estimated": self.settings.youcam_unit_cost,
        }
