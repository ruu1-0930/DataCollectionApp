"""Explicit 009/010 gate. Enabling controls must never silently skip missing schema."""
from sqlalchemy import inspect
from config import db
from services.data_management_scope import ManagementPreview, ManagementOperation, ManagementItem, ManagementAuditBridge
from services.data_export import ExportInventory, ExportGrant


def require_management_schema():
    inspector = inspect(db.engine)
    for model in (ManagementPreview, ManagementOperation, ManagementItem, ManagementAuditBridge, ExportInventory, ExportGrant):
        table = model.__table__
        if (not inspector.has_table(table.name)
                or not set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}):
            raise RuntimeError('data_management_requires_migrations_009_010')
