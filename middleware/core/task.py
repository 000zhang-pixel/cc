"""
Standard Task object passed from Poller → Dispatcher → Handler.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Task:
    task_type: str          # e.g. "content_generation", "material_analysis"
    table_id: str           # Feishu table ID
    record_id: str          # Feishu record ID
    payload: dict           # snapshot of key fields at detection time
    created_at: datetime = field(default_factory=datetime.now)


# Task type constants
TASK_CONTENT_GENERATION = "content_generation"
TASK_MATERIAL_MIGRATION = "material_migration"
TASK_PUBLISH_RECORD_CREATE = "publish_record_create"
TASK_PUBLISH = "publish"
TASK_MATERIAL_ANALYSIS = "material_analysis"
