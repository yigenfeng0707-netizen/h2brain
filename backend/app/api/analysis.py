"""氢智行 H2Brain - 真实数据分析接口

基于 T05 官方数据包遥测的行程分析：
- 车辆列表、行程列表、行程详情
- 异常检测、影响因素归因、驾驶行为分析
- 同类行程氢耗对标、一键生成报告、CSV 上传
"""

import json
import tempfile

import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response

from ..data_processor import get_processor
from ..value_analysis import compute_value_analysis
from ..validation import validate_trip_segmentation

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
        raise HTTPException(status_code=404, detail=f"未找到车辆 {vehicle_id} 的行程数据")
    return _json_response(trips)


@router.get("/analysis/trip/{vehicle_id}/{trip_id}", tags=["真实数据分析"])
def analysis_trip_detail(vehicle_id: str, trip_id: int):
    """获取指定行程的详细分析数据（含路况/车况/变载/异常/驾驶行为/因子分析）"""
    processor = get_processor()
    detail = processor.get_trip_detail(vehicle_id, trip_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"未找到车辆 {vehicle_id} 的行程 {trip_id}"
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
            status_code=404, detail=f"未找到车辆 {vehicle_id} 的行程 {trip_id}"
        )
    return _json_response(report)


@router.post("/analysis/upload", tags=["真实数据分析"])
async def analysis_upload(file: UploadFile = File(...)):
    """上传CSV车辆数据文件并自动分析"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

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
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/analysis/thresholds", tags=["真实数据分析"])
def get_thresholds():
    """获取当前阈值配置"""
    processor = get_processor()
    return _json_response(processor.get_thresholds())


@router.post("/analysis/thresholds/calibrate", tags=["真实数据分析"])
def calibrate_thresholds():
    """基于实际遥测数据标定阈值参数"""
    processor = get_processor()
    result = processor.calibrate_thresholds()

    # Apply calibrated thresholds
    if result.get("calibrated"):
        processor.apply_calibrated_thresholds(result["calibrated"])

    return _json_response(
        {
            "status": "ok",
            "calibrated": result.get("calibrated", {}),
            "report": result.get("report", ""),
            "stats": result.get("stats", {}),
            "current_thresholds": processor.get_thresholds(),
        }
    )


@router.get("/analysis/value", tags=["真实数据分析"])
def get_value_analysis():
    """基于真实车队数据计算经济效益与碳减排（含公式与参数说明）"""
    processor = get_processor()
    vehicles = processor.get_vehicles()
    all_trips = []
    for v in vehicles:
        vid = v.get("vehicle_id")
        if vid:
            all_trips.extend(processor.get_trips(vid))
    result = compute_value_analysis(vehicles, all_trips)
    return _json_response(result)


@router.get("/analysis/validation", tags=["真实数据分析"])
def get_validation_report(vehicle_id: str = "V2"):
    """校验自动行程切分与人工记录的一致性

    将算法输出与 T05 数据包中的官方手工记录表
    （"测试车辆2#手工行程及工况记录表.xlsx"）逐行程比对，
    输出行程数匹配、里程偏差、单车行程 MAPE 与工况分类吻合率。
    """
    try:
        result = validate_trip_segmentation(vehicle_id)
        return _json_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"校验失败: {str(e)}")
