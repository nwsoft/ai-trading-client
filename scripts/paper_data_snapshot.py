"""Stopped-engine backup and preservation evidence; never restore over user data."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sqlite3,tempfile
from contextlib import closing
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def inventory(root):
    result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('snapshot_symlink_rejected')
        if path.is_file():
            if len(result)>=32768:raise ValueError('snapshot_file_budget')
            result[path.relative_to(root).as_posix()]={'size':path.stat().st_size,'sha256':sha(path)}
    return result


def database_evidence(path):
    # Only staging/backup DBs are opened. No source DB/WAL/SHM is modified.
    conn=sqlite3.connect(path)
    try:
        integrity=conn.execute('PRAGMA integrity_check').fetchall()
        if integrity!=[('ok',)]:raise ValueError('snapshot_database_integrity_failed')
        tables={}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            identifier='"'+name.replace('"','""')+'"'
            rows=[]
            for values in conn.execute('SELECT * FROM '+identifier):
                safe=[{'bytes':v.hex()} if isinstance(v,bytes) else v for v in values]
                rows.append(hashlib.sha256(json.dumps(safe,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
            rows.sort()
            tables[name]={'count':len(rows),'row_hashes':rows,'rows_sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
        return {'integrity_check':'ok','user_version':conn.execute('PRAGMA user_version').fetchone()[0],'tables':tables}
    finally:conn.close()


def snapshot(source:Path,destination:Path,*,stopped:bool):
    source,destination=source.resolve(),destination.resolve()
    if not stopped:raise ValueError('snapshot_engine_stop_required')
    if not source.is_dir() or destination.exists():raise ValueError('snapshot_path_invalid')
    if source==destination or source in destination.parents:raise ValueError('snapshot_destination_inside_source')
    before=inventory(source)
    if sum(v['size'] for v in before.values())>64*1024**3:raise ValueError('snapshot_size_budget')
    destination.mkdir(parents=True,mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='noah-snapshot-stage-',dir=destination.parent) as stage_dir:
            stage=Path(stage_dir)/'data';shutil.copytree(source,stage)
            if before!=inventory(source) or before!=inventory(stage):raise ValueError('snapshot_source_changed_retry_after_stop')
            target=destination/'data';shutil.copytree(stage,target)
            dbs={}
            for relative in before:
                original=stage/relative
                # Closing the staged DB may checkpoint/delete its WAL/SHM.
                if relative.endswith(('-wal','-shm')) and relative[:-4] in dbs:
                    continue
                with original.open('rb') as stream:is_db=stream.read(16)==b'SQLite format 3\x00'
                if not is_db:continue
                dbs[relative]=database_evidence(original)
                # Fold copied WAL state into a standalone SQLite backup.
                # Close both handles before replace: Windows cannot rename an
                # open SQLite database, and WAL companions must be checkpointed.
                with closing(sqlite3.connect(original)) as old,closing(sqlite3.connect(str(target/relative)+'.snapshot')) as new:
                    old.backup(new)
                replaced=Path(str(target/relative)+'.snapshot');replaced.replace(target/relative)
                for suffix in ['-wal','-shm']:
                    Path(str(target/relative)+suffix).unlink(missing_ok=True)
                if database_evidence(target/relative)!=dbs[relative]:
                    raise ValueError('snapshot_database_rows_changed')
            if inventory(source)!=before:raise ValueError('snapshot_source_changed_retry_after_stop')
            result={'source':str(source),'stopped_assertion_required':True,'source_files':before,'backup_files':inventory(target),'databases':dbs,'source_unchanged':True,'restored_over_source':False}
            (destination/'snapshot-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            return result
    except BaseException:
        # Preserve partial backup for diagnosis, but never mark it accepted.
        (destination/'SNAPSHOT_FAILED.txt').write_text('Incomplete backup; do not use as an accepted restore point.\n')
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);p.add_argument('--stopped',action='store_true');a=p.parse_args()
    result=snapshot(a.source,a.destination,stopped=a.stopped)
    print(json.dumps({'accepted':True,'manifest':str(a.destination/'snapshot-manifest.json'),'files':len(result['source_files']),'databases':len(result['databases']),'source_unchanged':True}))
