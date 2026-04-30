from __future__ import annotations

from uav.llm_control.safety.action_gate import ActionGateConfig


def a_stage_sim_dry_run_profile() -> ActionGateConfig:
    return ActionGateConfig(
        profile_name="a-stage-sim-dry-run",
        allowed_topics=(
            "/goal",
            "/move_base_simple/goal",
            "/back_trigger",
            "/px4ctrl/takeoff_land",
        ),
        allowed_intents=("move_relative", "return_home", "takeoff", "land"),
        allowed_localization_sources=("sim", "lio", "vio"),
        max_goal_distance_m=1.0,
        max_execution_timeout_s=3.0,
    )


def b_stage_bench_profile() -> ActionGateConfig:
    return ActionGateConfig(
        profile_name="b-stage-bench",
        allowed_topics=("/goal", "/back_trigger"),
        allowed_intents=("move_relative", "return_home"),
        allowed_localization_sources=("lio", "vio"),
        max_goal_distance_m=0.5,
        max_execution_timeout_s=2.0,
    )


def c_stage_real_profile() -> ActionGateConfig:
    return ActionGateConfig(
        profile_name="c-stage-real",
        allowed_topics=("/goal",),
        allowed_intents=("move_relative",),
        allowed_localization_sources=("lio", "vio"),
        max_goal_distance_m=0.3,
        max_execution_timeout_s=1.0,
    )
