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
        default_summary="整理集成需求、人工补充项、point 和优先级，产出迭代需求文档",
    ),
    JobDefinition(
        job_type="daily-feedback-defect-triage",
        title="每日反馈缺陷分析",
        default_summary="按反馈内容所属模块归类缺陷并分配 Owner 排查",
    ),
    JobDefinition(
        job_type="track-sprint-demand-progress",
        title="迭代进度追踪",
        default_summary="对照迭代需求和需求表状态，生成待人工确认的回填清单",
    ),
    JobDefinition(
        job_type="production-log-analysis",
        title="生产日志分析",
        default_summary="分析生产集成错误日志，单独沉淀降噪和修复需求",
    ),
]

JOB_TYPES = {job.job_type for job in JOB_DEFINITIONS}

