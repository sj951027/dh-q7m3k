"""Record and verify the first permitted opening of Claude event results."""
import hashlib
import json
from code_20261110_event_common import OUT,ROOT,meta,now

saved=json.loads((OUT/'event_blind_saved.json').read_text(encoding='utf-8'))
for name, expected in saved['files'].items():
    assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==expected,name
marker=OUT/'event_unblind_access.json'
if not marker.exists():
    meta('event_unblind_access',dict(blind_completed=saved['completed'],verified_before_opening=True,
                                    first_opening_at=now(),allowed_paths=['research/EVENT_AFTER_RESULT_20261110.md','research/out_event_after/','research/event_after_20261110.py']))
print(marker.read_text(encoding='utf-8'))
