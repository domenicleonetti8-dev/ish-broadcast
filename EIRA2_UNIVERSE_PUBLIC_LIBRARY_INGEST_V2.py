from __future__ import annotations

from EIRA2_UNIVERSE_PUBLIC_LIBRARY_INGEST_V1 import TARGET, NEW as _V1_NEW

_OLD = 'INSERT OR REPLACE INTO ingest_receipts VALUES(?,?,?,?,?,?)'
_NEW_SQL = (
    'INSERT OR REPLACE INTO ingest_receipts('
    'receipt_id,source_name,operation,started_unix,completed_unix,status,details_json'
    ') VALUES(?,?,?,?,?,?,?)'
)

if _V1_NEW.count(_OLD) != 2:
    raise RuntimeError(f'unexpected_ingest_receipt_contract_count:{_V1_NEW.count(_OLD)}')

NEW = _V1_NEW.replace(_OLD, _NEW_SQL)

if _OLD in NEW:
    raise RuntimeError('legacy_six_placeholder_contract_remains')
if NEW.count(_NEW_SQL) != 2:
    raise RuntimeError('seven_column_contract_not_installed_twice')

compile(NEW, TARGET, 'exec')

if __name__ == '__main__':
    print('EIRA2_UNIVERSE_PUBLIC_LIBRARY_INGEST_V2=PASS')
    print(f'TARGET={TARGET}')
    print('INGEST_RECEIPT_COLUMNS=7')
    print('INGEST_RECEIPT_PLACEHOLDERS=7')
