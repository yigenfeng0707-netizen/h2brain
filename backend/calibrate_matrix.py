# -*- coding: utf-8 -*-
"""用官方手工记录表 ground truth 校准证据矩阵阈值:
对每条手工记录 (日期+起止+工况类别), 切片 V2 遥测, 提取 7 维特征 → 按类别统计分布"""
import sys
sys.path.insert(0, r"D:\APPs\未来能源黑客松\h2brain\backend")

import numpy as np
import pandas as pd
from app.data_processor import get_processor
from app import road_classifier as rc

# 1. 手工记录
fx = r"D:\APPs\未来能源黑客松\T05_数据包\T05_氢能车辆运营智能分析与决策助手数据包\测试车辆2#手工行程及工况记录表.xlsx"
raw = pd.read_excel(fx, sheet_name=0, header=None, skiprows=3)
manual = raw[[0, 1, 2, 4, 34]].copy()
manual.columns = ["date", "start", "end", "km", "cond"]
manual = manual[manual["date"].notna() & manual["cond"].notna()]
manual = manual[~manual["cond"].isin(["工况类别", "/"])]
manual["date"] = pd.to_datetime(manual["date"])
manual["km"] = pd.to_numeric(manual["km"], errors="coerce")
print(f"有效记录: {len(manual)} 条")

# 2. V2 全量遥测
proc = get_processor()
proc._ensure_loaded()
df_all = proc._vehicle_data["V2"].copy()
print(f"V2 遥测: {len(df_all)} 行, {df_all['timestamp'].iloc[0]} ~ {df_all['timestamp'].iloc[-1]}")

# 3. 逐记录切片提特征
recs = []
for _, r in manual.iterrows():
    try:
        t0 = pd.Timestamp(f"{r['date'].date()} {r['start']}")
        t1 = pd.Timestamp(f"{r['date'].date()} {r['end']}")
        if t1 <= t0:  # 跨午夜
            t1 += pd.Timedelta(days=1)
        mask = (df_all["timestamp"] >= t0) & (df_all["timestamp"] < t1)
        sub = df_all[mask]
        if len(sub) < 30:
            continue
        fdf = rc.extract_window_features(sub)
        if fdf.empty:
            continue
        recs.append(
            {
                "cond": r["cond"],
                "km": r["km"],
                "n_win": len(fdf),
                "speed_mean": fdf["speed_mean"].mean(),
                "speed_p85": fdf["speed_p85"].mean(),
                "speed_std": fdf["speed_std"].mean(),
                "stop_ratio": fdf["stop_ratio"].mean(),
                "accel_ratio": fdf["accel_ratio"].mean(),
                "power_cv": fdf["power_cv"].mean(),
                "power_mean": fdf["power_mean"].mean(),
            }
        )
    except Exception as e:
        continue

cal = pd.DataFrame(recs)
print(f"\n切片成功: {len(cal)} 条")
print("\n=== 官方工况类别的真实特征分布 (均值 [P25~P75]) ===")
for cond, g in cal.groupby("cond"):
    print(f"\n--- {cond} ({len(g)} 条记录) ---")
    for feat in ["speed_mean", "speed_p85", "speed_std", "stop_ratio", "accel_ratio", "power_cv", "power_mean"]:
        v = g[feat]
        print(f"  {feat:12s}: mean={v.mean():7.2f}  P25={v.quantile(0.25):7.2f}  P75={v.quantile(0.75):7.2f}  P10={v.quantile(0.10):7.2f}  P90={v.quantile(0.90):7.2f}")

# 4. 均速核验 (里程/时长 vs 遥测均速)
print("\n=== 均速核验 ===")
for cond, g in cal.groupby("cond"):
    valid = g[g["km"] > 5]
    if len(valid):
        print(f"{cond}: 遥测均速 mean={valid['speed_mean'].mean():.1f} km/h")
