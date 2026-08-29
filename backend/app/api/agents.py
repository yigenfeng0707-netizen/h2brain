"""H2Brain - Agent Display & Execution API

Provides six hydrogen-energy intelligent agents:
- Static metadata for display
- Execution endpoint that routes to the ReAct engine
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..schemas import ReactRequest

logger = logging.getLogger("h2brain.api.agents")

router = APIRouter()

AGENTS_DATA = [
    {
        "key": "hydrogen_opt",
        "name": "氢耗优化智能体",
        "icon": "H2",
        "metric": "28 个行程全覆盖分析",
        "desc": "基于车辆载荷、路况（多维证据矩阵分类）、驾驶行为的氢耗多维分析，输出可解释的百公里氢耗异常成因与节能建议（数据来源：T05 官方数据包真实遥测）。",
        "capabilities": [
            "行程级氢耗监测与异常识别（偏离度阈值法）",
            "基于工况分类的分段氢耗对标分析",
            "驾驶行为评分与节能驾驶建议",
            "历史氢耗趋势分析与车辆间对比",
        ],
        "tech": "LLM 推理 + 多维证据矩阵工况分类",
        "scenario": "hydrogen_optimization",
    },
    {
        "key": "route_plan",
        "name": "路径规划智能体",
        "icon": "路",
        "metric": "安全续航圈推演",
        "desc": "结合加氢站分布、剩余氢量与订单目的地，规划安全经济的运输路线，确保车辆不因缺氢停驶（调度沙盘推演演示）。",
        "capabilities": [
            "基于剩余氢量的安全续航圈计算",
            "多站点路线优化与途中加氢推荐",
            "行程成本预估（距离×氢耗×氢价）",
            "多订单串联路线优化",
        ],
        "tech": "Haversine 距离 + 续航圈 + 多站点优化",
        "scenario": "route_planning",
    },
    {
        "key": "station_dispatch",
        "name": "加氢站调度智能体",
        "icon": "站",
        "metric": "Erlang C 排队等待预测",
        "desc": "监测各加氢站排队状态，基于排队论模型预测等待时间，智能推荐最优加氢站点（调度沙盘推演演示）。",
        "capabilities": [
            "加氢站实时排队与等待时间预测",
            "动态分流与错峰调度建议",
            "氢价对比与加氢成本优化",
            "储氢量预警与补货建议",
        ],
        "tech": "M/M/c Erlang C 排队论 + 多因子评分",
        "scenario": "station_dispatch",
    },
    {
        "key": "fleet_manage",
        "name": "车队管理智能体",
        "icon": "队",
        "metric": "五维多目标匹配评分",
        "desc": "统一车队运力调度，基于订单需求与车辆状态进行订单-车辆智能匹配，最大化车队利用率（调度沙盘推演演示）。",
        "capabilities": [
            "车队运力实时画像",
            "订单-车辆智能匹配（氢量/距离/效用/成本/负载）",
            "司机换班方案优化",
            "空驶治理与回程货源匹配",
        ],
        "tech": "五维多目标加权评分 + 贪心分配",
        "scenario": "fleet_management",
    },
    {
        "key": "cost_analysis",
        "name": "成本分析智能体",
        "icon": "¥",
        "metric": "对标柴油成本节省测算",
        "desc": "氢能重卡全链路成本拆解（燃料、维护），对标同级柴油重卡计算成本节省，公式与参数全程透明可解释。",
        "capabilities": [
            "单车成本核算（公式：氢耗×氢价 + 里程×维护单价）",
            "氢价波动对运营成本的敏感性分析",
            "维护成本预测",
            "TCO 全生命周期对标与优化路径",
        ],
        "tech": "成本测算模型 + LLM 归因分析",
        "scenario": "cost_analysis",
    },
    {
        "key": "fuelcell_health",
        "name": "燃料电池健康智能体",
        "icon": "康",
        "metric": "健康评分 0-100 + 寿命预测",
        "desc": "基于电堆电压、温度、衰减速率等多维真实遥测数据，评估燃料电池健康状态并预测剩余使用寿命。",
        "capabilities": [
            "全功率段极化曲线采样分析",
            "热应力分析（进出口温差）",
            "效率分析（功率 vs 氢耗）",
            "衰减趋势预测与剩余寿命（RUL）估计",
            "健康评分（0-100）与维护建议",
        ],
        "tech": "极化曲线分析 + 线性 RUL 预测",
        "scenario": "fuelcell_health",
    },
]

# Map agent key -> scenario for ReAct engine
AGENT_SCENARIO_MAP = {a["key"]: a["scenario"] for a in AGENTS_DATA}


class AgentExecRequest(BaseModel):
    """Request body for agent execution."""

    query: str = Field(..., description="User question for the agent")
    vehicle_plate: str | None = Field(
        None, description="Target vehicle plate (optional)"
    )
    context: dict | None = Field(None, description="Additional context (optional)")


class ReportImageRequest(BaseModel):
    """运营周报配图生成请求。"""

    theme: str | None = Field(None, description="配图主题侧重（可选），如 '碳减排'")


@router.post("/agents/report-image", tags=["Agents"])
def generate_report_image(req: ReportImageRequest):
    """生成运营周报配图（商汤 SenseNova 图像模型 + 真实 KPI 提示词）。

    返回 image_url（前端 <img> 直接引用）、完整提示词与 KPI 摘要，保证可解释性。
    """
    if not settings.image_enabled:
        raise HTTPException(status_code=503, detail="图像生成未配置（缺少 IMAGE_API_KEY）")
    try:
        from ..report_image import generate_report_image as _gen

        return _gen(req.theme or "")
    except Exception as e:  # noqa: BLE001
        logger.error("周报配图生成失败: %s", e)
        raise HTTPException(status_code=502, detail=f"配图生成失败: {e}")


@router.get("/agents/report-image/{image_id}", tags=["Agents"])
def get_report_image(image_id: str):
    """按 id 获取已生成的周报配图（PNG 二进制）。"""
    from fastapi.responses import Response

    from ..report_image import get_image_bytes

    png = get_image_bytes(image_id)
    if png is None:
        raise HTTPException(status_code=404, detail="配图不存在或已过期，请重新生成")
    return Response(content=png, media_type="image/png")


@router.get("/agents", tags=["Agents"])
def list_agents():
    """List all six agents"""
    # Add LLM status to each agent
    result = []
    for a in AGENTS_DATA:
        agent_info = dict(a)
        agent_info["llm_enabled"] = settings.llm_enabled
        result.append(agent_info)
    return result


@router.get("/agents/{agent_key}", tags=["Agents"])
def get_agent(agent_key: str):
    """Get agent details"""
    for a in AGENTS_DATA:
        if a["key"] == agent_key:
            agent_info = dict(a)
            agent_info["llm_enabled"] = settings.llm_enabled
            return agent_info
    raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")


@router.post("/agents/{agent_key}/execute", tags=["Agents"])
def execute_agent(agent_key: str, req: AgentExecRequest):
    """Execute an agent with a user query.

    Routes to the ReAct engine with the appropriate scenario.
    When LLM is configured, performs real LLM reasoning;
    otherwise returns offline sample results.
    """
    if agent_key not in AGENT_SCENARIO_MAP:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    scenario = AGENT_SCENARIO_MAP[agent_key]

    # Build ReactRequest
    react_req = ReactRequest(
        scenario=scenario,
        query=req.query,
        vehicle_plate=req.vehicle_plate,
        context=req.context,
    )

    if settings.llm_enabled:
        try:
            from ..react_engine import ReactEngine

            engine = ReactEngine(react_req)
            result = engine.run()
            return {
                "agent_key": agent_key,
                "agent_name": next(
                    a["name"] for a in AGENTS_DATA if a["key"] == agent_key
                ),
                "llm_enabled": True,
                "result": result,
            }
        except Exception as e:
            logger.error(
                "Agent '%s' LLM execution failed, falling back to offline: %s",
                agent_key,
                e,
            )

    # Offline fallback
    from .react import _react_offline

    result = _react_offline(react_req)
    return {
        "agent_key": agent_key,
        "agent_name": next(a["name"] for a in AGENTS_DATA if a["key"] == agent_key),
        "llm_enabled": False,
        "result": result,
    }


@router.post("/agents/{agent_key}/execute/stream", tags=["Agents"])
def execute_agent_stream(agent_key: str, req: AgentExecRequest):
    """Execute an agent with SSE streaming (immune to gateway/axios timeouts).

    Events:
      {"type": "step", "index": N, "thought": ..., "action": ..., "observation": ...}
      {"type": "final", "answer": ..., "scenario": ...}
      {"type": "error", "message": ...}
      [DONE]
    """
    if agent_key not in AGENT_SCENARIO_MAP:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    scenario = AGENT_SCENARIO_MAP[agent_key]
    react_req = ReactRequest(
        scenario=scenario,
        query=req.query,
        vehicle_plate=req.vehicle_plate,
        context=req.context,
    )

    def event_generator():
        if not settings.llm_enabled:
            err = {"type": "error", "message": "LLM 未配置"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        try:
            import queue
            import threading

            from ..react_engine import ReactEngine

            engine = ReactEngine(react_req)
            # ReAct 循环耗时可能数分钟 (多次 LLM 调用+重试),
            # 在后台线程执行, 主协程每 5s 发 SSE 心跳防止网关/浏览器空闲断连
            q: "queue.Queue[dict | None]" = queue.Queue()

            def _worker():
                try:
                    for ev in engine.run_stream():
                        q.put(ev)
                except Exception as e:  # noqa: BLE001
                    logger.error("Agent '%s' stream failed: %s", agent_key, e)
                    q.put({"type": "error", "message": f"推理失败: {e}"})
                finally:
                    q.put(None)  # 结束哨兵

            threading.Thread(target=_worker, daemon=True).start()

            import time as _time

            while True:
                try:
                    ev = q.get(timeout=5.0)
                except queue.Empty:
                    # 心跳: SSE 注释行, 前端自动忽略, 但保活连接
                    yield ": ping\n\n"
                    continue
                if ev is None:
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:  # noqa: BLE001 - top-level guard for the stream
            logger.error("Agent '%s' stream failed: %s", agent_key, e)
            err = {"type": "error", "message": f"推理失败: {e}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
