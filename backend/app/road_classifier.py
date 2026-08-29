"""H2Brain - 多维证据矩阵路况分类器 (Multi-Dimensional Evidence Matrix Road Classifier)

v2.1: 阈值按官方《测试车辆2#手工行程及工况记录表》ground truth 校准,
工况体系对齐官方四分类: 平原高速 / 国道工况 / 山区国道 / 综合工况。

校准方法 (2026-08-29, 108 条官方记录切片反标定):
将手工表每条记录 (日期+起止时间+工况类别) 映射到 V2 遥测切片,
提取 7 维特征后按类别统计 P10-P90 分位 → 得到各类的真实特征区间。

官方 ground truth 实测分布 (关键发现):
- 平原高速: 均速 66-74 km/h, 停车占比 0.02, 平均功率 95 kW (2 条)
- 山区国道: 均速 31-35 km/h, 停车占比 0.15, 平均功率 120 kW (2 条)
  → 核心判别式 = 低速 + 高功率 (持续爬坡), 而非功率波动!
- 国道工况: 均速 26-52 km/h, 停车占比 0.29, 平均功率 69 kW (49 条)
- 综合工况: 速度高度异质 (13-60 km/h), 停车占比 0.44, 功率 14 kW (55 条)
- speed_std / power_cv / accel_ratio 在本数据集几乎无区分度 (均≈0),
  权重相应下调; 判别主力 = 速度水平 + 停车占比 + 功率水平。

方法论:
1. 特征提取: 滑动窗口 (60s 窗 / 30s 步长) 7 维特征
2. 证据矩阵: 每类对每特征定义 [期望下限, 期望上限] 与权重 (校准值)
3. 评分决策: 加权得分最高者为窗口类别; 输出逐特征证据明细
4. 平滑: 5 窗中值滤波 + 300s 最短段 + 段级重分类
5. 官方映射: 6 个工程类别映射到官方 4 工况 (怠速/场区-装卸 归入 综合工况)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 特征窗口参数
# ---------------------------------------------------------------------------
WINDOW_SEC = 60   # 滑动窗口 60 秒
STEP_SEC = 30     # 步长 30 秒 (50% 重叠)
MIN_SEGMENT_SEC = 300  # 最终段最短时长 5 分钟 (低于真实路况变化的物理粒度)
SMOOTH_WIDTH = 5  # 中值滤波宽度 (前后各 2 窗口投票)

# ---------------------------------------------------------------------------
# 证据矩阵定义 (v2.1 官方校准版)
# 区间 = 官方手工记录 ground truth 的 P10-P90 实测分布 (适当放宽边界)
# 权重 = 按特征实测区分度分配 (速度/停车/功率为主, 波动类特征降权)
# ---------------------------------------------------------------------------
EVIDENCE_MATRIX: dict[str, dict[str, tuple[tuple[float, float], float]]] = {
    "平原高速": {
        "speed_mean": ((58.0, 95.0), 0.32),    # 官方实测 66-74
        "speed_p85": ((62.0, 100.0), 0.22),    # 官方实测 68-75
        "speed_std": ((0.0, 8.0), 0.05),
        "stop_ratio": ((0.0, 0.05), 0.18),     # 官方实测 0.02
        "accel_ratio": ((0.0, 0.05), 0.03),
        "power_cv": ((0.0, 0.25), 0.07),
        "power_mean": ((40.0, 170.0), 0.13),   # 官方实测 62-129
    },
    "国道工况": {
        "speed_mean": ((18.0, 62.0), 0.32),    # 官方实测 26-52
        "speed_p85": ((22.0, 68.0), 0.20),     # 官方实测 28-55
        "speed_std": ((0.0, 8.0), 0.05),
        "stop_ratio": ((0.0, 0.12), 0.18),     # 行进中国道窗口停车少
        "accel_ratio": ((0.0, 0.06), 0.03),
        "power_cv": ((0.0, 0.30), 0.07),
        "power_mean": ((5.0, 130.0), 0.15),    # 官方实测 41-94
    },
    "山区国道": {
        "speed_mean": ((22.0, 42.0), 0.22),    # 官方实测 31-35
        "speed_p85": ((26.0, 48.0), 0.12),     # 官方实测 32-36
        "speed_std": ((0.0, 10.0), 0.05),
        "stop_ratio": ((0.05, 0.30), 0.10),    # 官方实测 0.12-0.19
        "accel_ratio": ((0.0, 0.08), 0.03),
        "power_cv": ((0.0, 0.30), 0.05),
        "power_mean": ((25.0, 220.0), 0.43),   # 官方实测 34-206, 低速高功率=爬坡, 最高权重
    },
    "综合工况": {
        "speed_mean": ((0.0, 55.0), 0.25),     # 官方实测高度异质 13-60
        "speed_p85": ((0.0, 65.0), 0.15),
        "speed_std": ((0.0, 12.0), 0.05),
        "stop_ratio": ((0.15, 1.0), 0.30),     # 官方实测 0.44 — 核心证据
        "accel_ratio": ((0.0, 0.10), 0.03),
        "power_cv": ((0.0, 1.0), 0.05),
        "power_mean": ((0.0, 80.0), 0.17),     # 官方实测 0-43
    },
    "场区-装卸": {
        "speed_mean": ((4.0, 22.0), 0.25),
        "speed_p85": ((8.0, 30.0), 0.12),
        "speed_std": ((0.0, 10.0), 0.05),
        "stop_ratio": ((0.08, 0.60), 0.30),    # 频繁停车 (倒车/等待/装卸)
        "accel_ratio": ((0.0, 0.20), 0.05),
        "power_cv": ((0.0, 0.8), 0.05),
        "power_mean": ((2.0, 60.0), 0.18),
    },
    "怠速": {
        "speed_mean": ((0.0, 3.5), 0.38),
        "speed_p85": ((0.0, 6.0), 0.17),
        "speed_std": ((0.0, 3.0), 0.05),
        "stop_ratio": ((0.70, 1.0), 0.25),     # 几乎全程静止
        "accel_ratio": ((0.0, 0.05), 0.02),
        "power_cv": ((0.0, 1.5), 0.03),
        "power_mean": ((0.0, 45.0), 0.10),     # 可能驻车发电
    },
}

# 工程类别 → 官方四工况映射 (怠速/场区-装卸 归入 综合工况)
OFFICIAL_CONDITION_MAP = {
    "平原高速": "平原高速",
    "国道工况": "国道工况",
    "山区国道": "山区国道",
    "综合工况": "综合工况",
    "场区-装卸": "综合工况",
    "怠速": "综合工况",
}

FEATURE_LABELS = {
    "speed_mean": "平均速度",
    "speed_p85": "P85巡航速度",
    "speed_std": "速度波动",
    "stop_ratio": "停车占比",
    "accel_ratio": "加减速活跃度",
    "power_cv": "功率波动系数",
    "power_mean": "平均功率",
}

FEATURE_UNITS = {
    "speed_mean": "km/h",
    "speed_p85": "km/h",
    "speed_std": "km/h",
    "stop_ratio": "",
    "accel_ratio": "",
    "power_cv": "",
    "power_mean": "kW",
}

ROAD_COLORS = {
    "平原高速": "#2196F3",
    "国道工况": "#4CAF50",
    "山区国道": "#9C27B0",
    "综合工况": "#FF9800",
    "场区-装卸": "#E91E63",
    "怠速": "#F44336",
}


# ---------------------------------------------------------------------------
# 特征提取
# ---------------------------------------------------------------------------

def extract_window_features(df: pd.DataFrame) -> pd.DataFrame:
    """按滑动窗口提取 7 维特征。

    df 需含: timestamp, speed, stack_power (data_processor 已换算)
    返回: 每窗口一行, 含 t_start / t_end + 7 特征
    """
    n = len(df)
    if n < 5:
        return pd.DataFrame()

    ts = df["timestamp"].values
    speeds = df["speed"].values.astype(float)
    powers = df["stack_power"].values.astype(float)

    # 采样间隔 (取中位数, 抗异常)
    if n >= 2:
        dts = np.diff(ts).astype("timedelta64[ms]").astype(float) / 1000.0
        dt_med = float(np.median(dts[dts > 0])) if (dts > 0).any() else 1.0
    else:
        dt_med = 1.0
    dt_med = max(dt_med, 0.1)

    win_pts = max(int(WINDOW_SEC / dt_med), 5)
    step_pts = max(int(STEP_SEC / dt_med), 2)

    rows = []
    for start in range(0, n, step_pts):
        end = min(start + win_pts, n)
        if end - start < min(5, win_pts // 3):
            break
        seg_speed = speeds[start:end]
        seg_power = powers[start:end]

        speed_mean = float(np.mean(seg_speed))
        speed_p85 = float(np.percentile(seg_speed, 85)) if len(seg_speed) >= 3 else speed_mean
        speed_std = float(np.std(seg_speed))
        stop_ratio = float(np.mean(seg_speed < 3.0))

        # 加速度活跃度: |dv/dt| > 0.5 m/s² 的占比
        if len(seg_speed) >= 2:
            acc = np.diff(seg_speed) / 3.6 / max(dt_med, 0.1)
            accel_ratio = float(np.mean(np.abs(acc) > 0.5))
        else:
            accel_ratio = 0.0

        power_mean = float(np.mean(seg_power))
        power_std = float(np.std(seg_power))
        power_cv = power_std / power_mean if power_mean > 1e-3 else (0.0 if power_std < 1.0 else 2.0)

        rows.append(
            {
                "t_start": pd.Timestamp(ts[start]),
                "t_end": pd.Timestamp(ts[end - 1]),
                "speed_mean": speed_mean,
                "speed_p85": speed_p85,
                "speed_std": speed_std,
                "stop_ratio": stop_ratio,
                "accel_ratio": accel_ratio,
                "power_cv": power_cv,
                "power_mean": power_mean,
            }
        )
        if end >= n:
            break

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 证据评分
# ---------------------------------------------------------------------------

def _feature_score(value: float, lo: float, hi: float) -> float:
    """特征落入期望区间的程度: 区间内=1.0, 越界线性衰减 (距离/区间宽), 下限 0。"""
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1e-6)
    if value < lo:
        dist = (lo - value) / max(width, lo * 0.5 + 1.0)
    else:
        dist = (value - hi) / max(width, hi * 0.5 + 1.0)
    return max(0.0, 1.0 - dist)


def score_window(features: dict) -> dict:
    """对单窗口评分, 返回 {类别: {score, confidence, evidence:[...]}} 全量明细。"""
    results = {}
    for road, evdefs in EVIDENCE_MATRIX.items():
        total_w = 0.0
        score = 0.0
        evidence = []
        for feat, ((lo, hi), w) in evdefs.items():
            v = float(features.get(feat, 0.0))
            s = _feature_score(v, lo, hi)
            score += s * w
            total_w += w
            evidence.append(
                {
                    "feature": feat,
                    "feature_label": FEATURE_LABELS[feat],
                    "unit": FEATURE_UNITS[feat],
                    "value": round(v, 3),
                    "expected_low": lo,
                    "expected_high": hi,
                    "match": bool(s >= 0.999),
                    "partial": bool(0.3 <= s < 0.999),
                    "score": round(s, 3),
                    "weight": w,
                }
            )
        results[road] = {
            "score": round(score, 4),
            "confidence": round(score / total_w, 4) if total_w > 0 else 0.0,
            "evidence": evidence,
        }
    return results


def classify_windows(feat_df: pd.DataFrame) -> list[dict]:
    """逐窗口分类 + 3 点中值滤波平滑。返回窗口判定序列。"""
    if feat_df.empty:
        return []

    window_results = []
    for _, row in feat_df.iterrows():
        feature_dict = {
            k: float(row[k])
            for k in ["speed_mean", "speed_p85", "speed_std", "stop_ratio",
                      "accel_ratio", "power_cv", "power_mean"]
        }
        scores = score_window(feature_dict)
        best = max(scores, key=lambda r: scores[r]["score"])
        window_results.append(
            {
                "t_start": row["t_start"],
                "t_end": row["t_end"],
                "road_type": best,
                "confidence": scores[best]["confidence"],
                "class_scores": {r: scores[r]["score"] for r in scores},
                "evidence": scores[best]["evidence"],
            }
        )

    # 中值滤波 (类别众数投票, SMOOTH_WIDTH 宽度): 消除孤立误判窗口
    if len(window_results) >= SMOOTH_WIDTH:
        half = SMOOTH_WIDTH // 2
        smoothed = list(window_results)
        for i in range(len(window_results)):
            lo = max(0, i - half)
            hi = min(len(window_results), i + half + 1)
            neigh = [window_results[j]["road_type"] for j in range(lo, hi)]
            majority = max(set(neigh), key=neigh.count)
            if neigh.count(majority) > (hi - lo) / 2:
                smoothed[i]["road_type"] = majority
        window_results = smoothed

    return window_results


# ---------------------------------------------------------------------------
# 段合并与证据汇总
# ---------------------------------------------------------------------------

def merge_windows_to_segments(windows: list[dict]) -> list[dict]:
    """相邻同类窗口合并为段; <60s 碎段并入邻段; 汇总段级证据与判据描述。"""
    if not windows:
        return []

    segments = []
    cur = {
        "road_type": windows[0]["road_type"],
        "t_start": windows[0]["t_start"],
        "t_end": windows[0]["t_end"],
        "confidences": [windows[0]["confidence"]],
        "evidence_acc": list(windows[0]["evidence"]),
    }
    for w in windows[1:]:
        if w["road_type"] == cur["road_type"]:
            cur["t_end"] = w["t_end"]
            cur["confidences"].append(w["confidence"])
            cur["evidence_acc"].extend(w["evidence"])
        else:
            segments.append(cur)
            cur = {
                "road_type": w["road_type"],
                "t_start": w["t_start"],
                "t_end": w["t_end"],
                "confidences": [w["confidence"]],
                "evidence_acc": list(w["evidence"]),
            }
    segments.append(cur)

    # 碎段合并 (< MIN_SEGMENT_SEC 并入时长更长的邻段; 多轮直到稳定)
    changed = True
    while changed and len(segments) > 1:
        changed = False
        for i in range(len(segments)):
            dur = (segments[i]["t_end"] - segments[i]["t_start"]).total_seconds()
            if dur >= MIN_SEGMENT_SEC:
                continue
            # 选更长邻段并入
            prev_ok = i > 0
            next_ok = i < len(segments) - 1
            prev_dur = (
                (segments[i - 1]["t_end"] - segments[i - 1]["t_start"]).total_seconds()
                if prev_ok else -1
            )
            next_dur = (
                (segments[i + 1]["t_end"] - segments[i + 1]["t_start"]).total_seconds()
                if next_ok else -1
            )
            if not prev_ok and not next_ok:
                break
            target = i - 1 if prev_dur >= next_dur else i + 1
            # 合并方向: 目标段吸收本段的时间范围与证据
            seg = segments.pop(i)
            t = segments[target] if target < i else segments[target - 1]
            t["t_start"] = min(t["t_start"], seg["t_start"])
            t["t_end"] = max(t["t_end"], seg["t_end"])
            t["confidences"].extend(seg["confidences"])
            t["evidence_acc"].extend(seg["evidence_acc"])
            changed = True
            break

    # 按时间排序并强制边界连续
    segments.sort(key=lambda s: s["t_start"])
    for i in range(1, len(segments)):
        segments[i]["t_start"] = segments[i - 1]["t_end"]

    # 相邻同类段合并 (碎段吸收可能隔开同类段)
    if len(segments) > 1:
        combined = [segments[0]]
        for seg in segments[1:]:
            if seg["road_type"] == combined[-1]["road_type"]:
                combined[-1]["t_end"] = seg["t_end"]
                combined[-1]["confidences"].extend(seg["confidences"])
                combined[-1]["evidence_acc"].extend(seg["evidence_acc"])
            else:
                combined.append(seg)
        segments = combined
    merged = segments

    # 输出结构化段
    out = []
    for seg in merged:
        dur_s = (seg["t_end"] - seg["t_start"]).total_seconds()
        if dur_s < 10:
            continue
        # 段级证据: 对各特征取窗口均值
        feat_summary = {}
        for e in seg["evidence_acc"]:
            f = e["feature"]
            if f not in feat_summary:
                feat_summary[f] = {"sum": 0.0, "n": 0, "match_cnt": 0, "def": e}
            feat_summary[f]["sum"] += e["value"]
            feat_summary[f]["n"] += 1
            if e["match"]:
                feat_summary[f]["match_cnt"] += 1

        agg_features = {
            f: agg["sum"] / agg["n"] for f, agg in feat_summary.items()
        }

        # 段级重分类: 用聚合特征重新评分 (修正碎段吸收带来的类别失真)
        rescored = score_window(agg_features)
        best = max(rescored, key=lambda r: rescored[r]["score"])
        road_type = best

        evidence_list = []
        final_matrix = EVIDENCE_MATRIX[road_type]
        for f, agg in feat_summary.items():
            e = agg["def"]
            # 期望区间取最终类别的矩阵定义 (而非窗口原始类别的旧区间)
            (exp_lo, exp_hi) = final_matrix[f][0] if f in final_matrix else (e["expected_low"], e["expected_high"])
            evidence_list.append(
                {
                    "feature": f,
                    "feature_label": e["feature_label"],
                    "unit": e["unit"],
                    "value": round(agg["sum"] / agg["n"], 2),
                    "expected_low": exp_lo,
                    "expected_high": exp_hi,
                    "expected": f"[{exp_lo}, {exp_hi}]{e['unit']}",
                    "match_ratio": round(agg["match_cnt"] / agg["n"], 2),
                }
            )

        # 主导证据 = 权重×匹配率 最高的 3 个特征
        weights = {f: next(
            (ev[1] for feat, ev in EVIDENCE_MATRIX[road_type].items() if feat == f)
            , 0.0) for f in feat_summary}
        top = sorted(
            evidence_list,
            key=lambda e: -weights.get(e["feature"], 0) * e["match_ratio"],
        )[:3]
        verdict_parts = []
        for e in top:
            if e["match_ratio"] >= 0.5:
                verdict_parts.append(
                    f"{e['feature_label']}{e['value']}{e['unit']}(期望{e['expected']})"
                )
        verdict = f"判定为「{road_type}」的依据: " + (
            "; ".join(verdict_parts) if verdict_parts else "多特征综合评分最高"
        )

        out.append(
            {
                "road_type": road_type,
                "official_condition": OFFICIAL_CONDITION_MAP.get(road_type, road_type),
                "start_time": seg["t_start"].isoformat(),
                "end_time": seg["t_end"].isoformat(),
                "duration_sec": round(dur_s, 1),
                "confidence": round(rescored[best]["confidence"], 3),
                "class_scores": {r: round(rescored[r]["score"], 3) for r in rescored},
                "evidence": evidence_list,
                "verdict": verdict,
                "color": ROAD_COLORS.get(road_type, "#999999"),
            }
        )
    return out


def classify_road_conditions_v2(trip: pd.DataFrame) -> list[dict]:
    """主入口: 行程 DataFrame → 多维证据矩阵路况段列表。

    返回段结构与旧版兼容 (road_type/start_time/end_time/duration...),
    并新增 confidence / evidence / verdict 可解释性字段。
    """
    feat_df = extract_window_features(trip)
    if feat_df.empty:
        return []
    windows = classify_windows(feat_df)
    segments = merge_windows_to_segments(windows)

    # 从行程原始数据补齐段级运营指标 (兼容旧接口字段)
    trip_sorted = trip.reset_index(drop=True)
    mile = trip_sorted["mileage"].values
    h2cum = trip_sorted["h2_consumed_cum"].values
    speed = trip_sorted["speed"].values
    power = trip_sorted["stack_power"].values

    for seg in segments:
        st = pd.Timestamp(seg["start_time"])
        en = pd.Timestamp(seg["end_time"])
        i0 = int(trip_sorted["timestamp"].searchsorted(st, side="left"))
        i1 = int(trip_sorted["timestamp"].searchsorted(en, side="right"))
        i0 = max(0, min(i0, len(mile) - 1))
        i1 = max(i0 + 1, min(i1, len(mile)))
        n = i1 - i0
        if n < 1:
            continue
        distance = max(0.0, float(mile[i1 - 1]) - float(mile[i0]))
        h2_used = max(0.0, float(h2cum[i1 - 1]) - float(h2cum[i0]))
        moving = speed[i0:i1] > 1
        avg_speed = float(speed[i0:i1][moving].mean()) if moving.any() else 0.0
        power_mean = float(power[i0:i1].mean())
        load_changes = int((np.abs(np.diff(power[i0:i1])) > 20).sum())

        seg["start_time"] = st.strftime("%m-%d %H:%M")
        seg["end_time"] = en.strftime("%m-%d %H:%M")
        seg["start_iso"] = st.isoformat()
        seg["end_iso"] = en.isoformat()
        seg["duration_h"] = round(seg["duration_sec"] / 3600, 2)
        seg["distance_km"] = round(distance, 1)
        seg["avg_speed"] = round(avg_speed, 1)
        seg["h2_consumed_kg"] = round(h2_used, 2)
        seg["h2_per_100km"] = round(h2_used / distance * 100, 2) if distance > 0.1 else 0
        seg["stack_power_kw"] = round(power_mean, 1)
        seg["load_changes"] = load_changes
    return segments


def explain_methodology() -> dict:
    """算法方法论自述 (供前端展示与评委答辩)。"""
    return {
        "name": "多维证据矩阵路况识别",
        "version": "2.1 (官方手工记录表 ground truth 校准)",
        "window": f"{WINDOW_SEC}s 窗口 / {STEP_SEC}s 步长 (50% 重叠) + {SMOOTH_WIDTH} 窗口中值平滑 + {MIN_SEGMENT_SEC}s 最短段",
        "features": [
            {"key": k, "label": v, "unit": FEATURE_UNITS[k]}
            for k, v in FEATURE_LABELS.items()
        ],
        "classes": list(EVIDENCE_MATRIX.keys()),
        "official_classes": ["平原高速", "国道工况", "山区国道", "综合工况"],
        "rationale": (
            "每类工况对 7 维特征定义期望区间与权重, 窗口特征落入区间即证据成立; "
            "加权得分最高者为判定类别。v2.1 阈值区间取自官方《测试车辆2#手工行程及"
            "工况记录表》108 条 ground truth 记录的遥测切片反标定 (P10-P90 实测分布), "
            "工况体系对齐官方四分类: 平原高速(均速66-74km/h)/国道工况(26-52)/"
            "山区国道(31-35, 低速+高功率120kW=爬坡判别式)/综合工况(停驻占比0.44)。"
            "每个路段输出逐特征匹配明细与判定依据, 实现完全可解释。"
        ),
        "calibration": (
            "校准数据: 108 条官方手工记录 × V2 遥测切片; 校准发现 "
            "speed_std/power_cv/accel_ratio 区分度弱 (实测均≈0), 权重下调, "
            "判别主力为速度水平+停车占比+功率水平。"
        ),
        "vs_old": (
            "旧版仅用速度滚动均值+波动率双指标; v2 引入 7 维证据矩阵; "
            "v2.1 用官方 ground truth 校准区间与权重, 并输出官方四工况映射字段。"
        ),
    }
