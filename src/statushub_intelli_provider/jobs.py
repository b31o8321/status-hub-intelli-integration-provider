from dataclasses import dataclass


@dataclass(frozen=True)
class JobDefinition:
    job_type: str
    title: str
    default_summary: str


JOB_DEFINITIONS = [
    JobDefinition(
        job_type="prepare-sprint-iteration",
        title="迭代需求整理",
        default_summary="整理集成需求、人工补充项、point、优先级和需求池状态待同步项",
    ),
    JobDefinition(
        job_type="daily-feedback-defect-triage",
        title="每日反馈缺陷分析",
        default_summary="分析缺陷反馈并提醒 Owner 排查，同时提醒本周进行中集成需求更新进度",
    ),
    JobDefinition(
        job_type="production-log-analysis",
        title="生产日志分析",
        default_summary="分析生产集成错误日志，单独沉淀降噪和修复需求",
    ),
]

JOB_TYPES = {job.job_type for job in JOB_DEFINITIONS}
