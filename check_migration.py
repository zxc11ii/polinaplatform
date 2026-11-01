"""Verify an existing database migrates without changing accounts or attempt history."""
import importlib.util
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

source=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('studio',Path(__file__).with_name('server.py'))
studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
with tempfile.TemporaryDirectory() as tmp:
    studio.ROOT=Path(tmp);studio.DB=studio.ROOT/'data'/'migration.sqlite'
    studio.DB.parent.mkdir()
    original=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    before={table:original.execute('SELECT * FROM '+table).fetchall() for table in ('users','attempts','assignments','materials','lessons')}
    destination=sqlite3.connect(studio.DB);original.backup(destination);destination.close();original.close()
    studio.initialize();studio.initialize()
    with studio.connect() as db:
        for table,rows in before.items():
            actual=db.execute('SELECT * FROM '+table).fetchall()
            assert len(actual)>=len(rows),table
            # All old columns are retained in their original order, new columns appended.
            if table!='attempts' and rows:
                actual_by_id={r['id']:tuple(r)[:len(rows[0])] for r in actual}
                assert all(actual_by_id[r[0]]==r for r in rows),table
        for old in before['attempts']:
            migrated=db.execute('SELECT * FROM attempts WHERE id=?',(old[0],)).fetchone()
            assert tuple(migrated)[:len(old)]==old
            assert migrated['number']==(old[9] if len(old)>9 else 1)
            assert migrated['snapshot']
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    print('Migration OK: accounts, passwords, tasks, materials, lessons and attempts preserved; repeat initialization OK.')
