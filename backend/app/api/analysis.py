"""H2Brain - Real Data Analysis API

Endpoints for hydrogen vehicle trip analysis:
- Vehicle list, trip list, trip detail
- Anomaly detection, factor analysis, driving behaviors
- Trip benchmarking, auto report generation, CSV upload
"""

import json
import os
import tempfile

import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response

from ..data_processor import get_processor

router = APIRouter()


def _json_response(data) -> Response:
    """Serialize data with numpy type support."""

    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [convert(v) for v in obj]
        return obj

    return Response(
        content=json.dumps(convert(data), ensure_ascii=False),
        media_type="application/json",
    )


@router.get("/analysis/vehicles", tags=["真实数据分析"])
def analysis_vehicles():
    """获取真实数据车辆列表"""
    processor = get_processor()
    return _json_response(processor.get_vehicles())


@router.get("/analysis/trips/{vehicle_id}", tags=["真实数据分析"])
def analysis_trips(vehicle_id: str):
    """获取指定车辆的行程列表"""
    processor = get_processor()
    trips = processor.get_trips(vehicle_id)
    if not trips:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found")
    return _json_response(trips)


@router.get("/analysis/trip/{vehicle_id}/{trip_id}", tags=["真实数据分析"])
def analysis_trip_detail(vehicle_id: str, trip_id: int):
    """获取指定行程的详细分析数据（含路况/车况/变载/异常/驾驶行为/因子分析）"""
    processor = get_processor()
    detail = processor.get_trip_detail(vehicle_id, trip_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"Trip {trip_id} of {vehicle_id} not found"
        )
    return _json_response(detail)


@router.get("/analysis/benchmark/{vehicle_id}", tags=["真实数据分析"])
def analysis_benchmark(vehicle_id: str):
    """获取同类行程氢耗对标分析"""
    processor = get_processor()
    benchmark = processor.get_benchmark(vehicle_id)
    return _json_response(benchmark)


@router.get("/analysis/report/{vehicle_id}/{trip_id}", tags=["真实数据分析"])
def analysis_report(vehicle_id: str, trip_id: int):
    """一键生成行程分析报告"""
    processor = get_processor()
    report = processor.get_report(vehicle_id, trip_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"Trip {trip_id} of {vehicle_id} not found"
        )
    return _json_response(report)


@router.post("/analysis/upload", tags=["真实数据分析"])
async def analysis_upload(file: UploadFile = File(...)):
    """上传CSV车辆数据文件并自动分析"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        processor = get_processor()
        result = processor.process_uploaded_csv(tmp_path)
        return _json_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        os.unlink(tmp_path)
