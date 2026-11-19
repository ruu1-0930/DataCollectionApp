"""Explicit 009/010/011 gate for the management controls."""
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
    operation_columns = inspector.get_columns(ManagementOperation.__tablename__)
    indexes = inspector.get_indexes(ManagementItem.__tablename__)
    if (not next(column['nullable'] for column in operation_columns if column['name'] == 'record_id')
            or not any(index['column_names'] == ['table_name', 'row_id'] for index in indexes)):
        raise RuntimeError('data_management_requires_migration_011')
