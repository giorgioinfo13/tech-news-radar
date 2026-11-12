"""Store only bounded accounting values, never provider payloads or reader identities."""

from sqlalchemy.orm import Session

from app.models import AIBriefJob, AIBriefUsage

TOKEN_FIELDS = ("counted_tokens", "input_tokens", "output_tokens", "thought_tokens", "total_tokens")


def record_usage(session: Session, job: AIBriefJob, metrics: dict | None = None) -> None:
    usage = session.get(AIBriefUsage, job.id)
    if usage is None:
        usage = AIBriefUsage(id=job.id, usage_validated=False)
        session.add(usage)
    for name in (
        "started_at",
        "edition_at",
        "finished_at",
        "dispatched_at",
        "lease_until",
        "model",
        "status",
        "error_code",
        "reserved_nano_usd",
    ):
        setattr(usage, name, getattr(job, name))
    if metrics is None or usage.usage_validated:
        return
    for name in TOKEN_FIELDS:
        value = metrics.get(name)
        if type(value) is int and 0 <= value <= 10_000_000:
            setattr(usage, name, value)
    # The adapter supplies this marker only after all model/usage checks pass.
    if metrics.get("usage_validated") == 1 and all(
        getattr(usage, name) is not None for name in TOKEN_FIELDS
    ):
        cost = metrics.get("estimated_nano_usd")
        if type(cost) is int and 0 <= cost <= job.reserved_nano_usd:
            usage.usage_validated = True
            usage.estimated_nano_usd = cost
