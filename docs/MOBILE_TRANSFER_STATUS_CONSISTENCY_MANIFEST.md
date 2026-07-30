# Patch manifest

## Runtime files

- `scripts/visionflow_hp_omen_transfer_day.py`
- `scripts/visionflow_transfer_media.py`
- `scripts/visionflow_project_closeout.py`
- `scripts/visionflow_transfer_readiness.py`
- `scripts/visionflow_hp_omen_restore.py`
- `scripts/visionflow_transfer_package.py`
- `scripts/visionflow_transfer_rehearsal.py`
- `scripts/visionflow_maintenance_presentation_gate.py`
- `scripts/visionflow_transfer_day_gate.py`
- `scripts/visionflow_cold_start_rehearsal.py`
- `scripts/visionflow_migration_handoff.py`

## Tests

- `scripts/tests/test_visionflow_project_closeout.py`

## Validation

- Python compilation: PASS
- Impacted unit tests: 131/131 PASS
- Legacy transfer-package key normalization: PASS
- New HP-target revalidation key propagation: PASS
- Database/Docker/network mutation: none
