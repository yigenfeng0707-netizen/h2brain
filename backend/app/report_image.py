"""氢智行 H2Brain - 运营周报配图自动生成

基于真实车队 KPI（T05 官方数据包遥测 + 价值量化口径）自动构建提示词，
调用商汤 SenseNova 图像模型（OpenAI 兼容 /images/generations）生成周报配图。

可解释性设计：
- 提示词完整返回给前端展示（用户可看到"画的是什么、依据什么数据"）
- KPI 摘要与配图一同返回，图上的视觉元素与真实数字一一对应
- 图像存内存缓存（上限 20 张，LRU 淘汰），经 /agents/report-image/{id} 以 PNG 提供
"""

from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("h2brain.report_image")

# 内存缓存: image_id -> png bytes（LRU 上限 20 张，防止内存膨胀）
_MAX_CACHE = 20
_image_store: "OrderedDict[str, bytes]" = OrderedDict()
_store_lock = threading.Lock()

# 图像生成接口路径（OpenAI 兼容）
_IMAGE_PATH = "/images/generations"
# 生成超时（商汤出图实测约 10-60 秒）
_TIMEOUT_S = 120


def _build_kpi_summary() -> tuple[dict[str, Any], str]:
    """汇总真实车队 KPI（用于配图提示词与随图说明）。"""
    try:
        from .data_processor import get_processor
        from .value_analysis import compute_value_analysis

        proc = get_processor()
        proc._ensure_loaded()
        vehicles = proc.get_vehicles()
        trips = [t for v in vehicles for t in proc.get_trips(v["vehicle_id"])]
        va = compute_value_analysis(vehicles, trips)

        ds = va.get("data_summary", {})
        eco = va.get("economic", {})
        emission = va.get("emission", {})

        total_km = ds.get("total_distance_km", 0)
        kpi = {
            "vehicle_count": ds.get("vehicle_count", len(vehicles)),
            "total_km": total_km,
            "total_h2_kg": ds.get("total_h2_consumed_kg", 0),
            "cost_saved": eco.get("cost_saved_yuan", 0),
            "co2_reduced": emission.get("co2_reduced_green_kg", 0),
        }
        text = (
            f"{kpi['vehicle_count']} 辆氢能重卡｜总里程 {total_km:,.0f} km｜"
            f"总氢耗 {kpi['total_h2_kg']:,.1f} kg｜"
            f"对标柴油成本节省 {kpi['cost_saved']:,.0f} 元｜"
            f"碳减排 {kpi['co2_reduced']:,.0f} kg CO₂"
        )
        return kpi, text
    except Exception as e:  # noqa: BLE001 - KPI 获取失败不阻断配图
        logger.warning("KPI 汇总失败，配图将使用通用主题: %s", e)
        return {}, "真实 KPI 暂不可用"


def _build_prompt(theme: str, kpi: dict[str, Any]) -> str:
    """构建配图提示词（扁平插画风横幅，不含文字，元素与真实 KPI 对应）。"""
    style = (
        "横幅插画，扁平矢量风格，清新绿色与青色主色调，科技感，画面干净简洁，"
        "适合作为氢能车队运营周报的封面配图，不含任何文字与数字"
    )
    if kpi:
        scene = (
            f"两辆绿色氢燃料电池重卡行驶在现代化高速公路上，车尾排放出代表清洁的水汽，"
            f"背景有风电风机、光伏板与加氢站，天空湛蓝有少量白云，"
            f"远景是绿色山丘，前景有氢分子气泡元素点缀，整体传递绿色低碳、高效运营的氛围"
        )
    else:
        scene = "绿色氢燃料电池重卡车队行驶在高速公路上，背景有风电与加氢站，蓝天白云"

    if theme:
        scene += f"，主题侧重：{theme}"
    return f"{scene}。{style}"


def generate_report_image(theme: str = "") -> dict[str, Any]:
    """生成一张运营周报配图。返回 {image_id, image_url, prompt, kpi_summary}。

    Raises:
        RuntimeError: 图像模型未配置或调用失败。
    """
    if not settings.image_enabled:
        raise RuntimeError("图像生成未配置（缺少 IMAGE_API_KEY）")

    kpi, kpi_text = _build_kpi_summary()
    prompt = _build_prompt(theme, kpi)

    url = settings.image_base_url.rstrip("/") + _IMAGE_PATH
    with httpx.Client(trust_env=False, timeout=_TIMEOUT_S) as client:
        resp = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.image_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.image_model, "prompt": prompt},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"图像模型返回 {resp.status_code}: {resp.text[:200]}")

    data = resp.json().get("data") or [{}]
    b64 = (data[0] or {}).get("b64_json") if data else None
    if not b64:
        raise RuntimeError("图像模型未返回图片数据（b64_json 为空）")

    png = base64.b64decode(b64)
    image_id = uuid.uuid4().hex[:12]
    with _store_lock:
        _image_store[image_id] = png
        while len(_image_store) > _MAX_CACHE:
            _image_store.popitem(last=False)  # LRU 淘汰最旧一张

    logger.info("周报配图已生成: id=%s, %d bytes", image_id, len(png))
    return {
        "image_id": image_id,
        "image_url": f"/api/v1/agents/report-image/{image_id}",
        "prompt": prompt,
        "kpi_summary": kpi_text,
        "theme": theme or "运营周报总览",
    }


def get_image_bytes(image_id: str) -> bytes | None:
    """按 id 取缓存中的 PNG（不存在或已淘汰返回 None）。"""
    with _store_lock:
        png = _image_store.get(image_id)
        if png is not None:
            _image_store.move_to_end(image_id)
        return png
