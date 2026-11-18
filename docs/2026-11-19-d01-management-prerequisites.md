# D01 / D02 management schema and server configuration gate

The management master flag stays `SARCOGAIT_DATA_MANAGEMENT_ENABLED=false` by default. Both single-record deletion (D01) and export/backup (D02) require migrations 009 and 010. 009-only is deliberately unsupported: enabling the flag with missing tables or columns fails startup with `data_management_requires_migrations_009_010`; no missing-table fallback is introduced.

Before any separately authorized production rollout, apply `back/migrations/010_data_export.sql` once using the existing controlled migration procedure, and retain the schema receipt for both `data_export_inventory` and `data_export_grant` (including their foreign key). This change does not execute a migration. The local synthetic SQLite gate is not a MySQL migration acceptance result.

Configure `SARCOGAIT_WORKBENCH_URL` on B to the reachable WB BFF base URL, without embedded credentials, query or fragment. This is a required server setting when management is enabled; browser input cannot supply it. The existing Agent URL is still required for Agent operations. Do not write bearer tokens or patient payloads to logs.

B freezes all known intersecting export bindings, across all owners/states, into the delete preview hash and operation. A patient-wide export, a selected record, or a package containing an affected snapshot/session intersects; disjoint packages remain. Begin rechecks under the existing patient lock and rejects changed previews; the resulting fence blocks new exports and revokes selected download grants. The package's own scope hash is retained separately from the delete scope hash.

After Agent cleanup commits `agent_purged`, B calls WB `/api/data-bundles/purge` outside its transaction. WB reauthorizes through the existing B operation endpoint and removes only frozen server-created package IDs. B requires a receipt matching the operation ID, delete scope hash, completed flag and exact frozen count, including zero. Timeout, storage failure or mismatched receipt leaves the same fenced operation retryable. Only after success does B delete grant/inventory rows and clinical dependencies; backend transaction failure also resumes the same operation and repeats idempotent WB cleanup.

The operation contract now requires `export_files`, explicitly `[]` when empty, in B/WB/Agent. Deploy these contract changes together while controls remain disabled; there is no compatibility default for older operation payloads. Completed receipts retain only package IDs/patient IDs/hashes plus the existing minimal operation metadata, rather than filesystem paths or clinical payloads. Patient-wide deletion remains rejected.

Local verification (run from the B repository):

```powershell
& back/.venv/Scripts/python.exe -m pytest back/tests/test_d01_bundle_closure.py back/tests/test_data_management_enablement.py -q --tb=short --disable-warnings
```

The focused tests use synthetic SQLite and stub remote Agent/WB responses; WB storage and its actual FastAPI purge route are tested in A. They do not establish live MySQL, production, APK, model, or full Agent memory-closure acceptance. The controller's D01 report records the exact results and remaining G4 coverage.
