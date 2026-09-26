"""Read-only source audit on temporary copies; never print private strategies or use APIs."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.noah_strategy_ir import NoahStrategyIR


def run(folder):
    files = sorted(Path(folder).glob('*_private.json'))
    if not files:
        raise SystemExit('No strategy stores found')
    result = Counter()
    reasons = Counter()
    with tempfile.TemporaryDirectory(prefix='noah-v47-strategy-') as directory:
        for source in files:
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            original = json.loads(source.read_text())
            target = Path(directory) / source.name
            shutil.copy2(source, target)
            pipeline = CustomStrategyPipeline(storage_path=target)
            for key, versions in original['strategies'].items():
                for old in versions:
                    current = pipeline.get_version(key, old['version_id'])
                    # Load must not rewrite source intent or historical evidence.
                    for field in ('rules','execution_validation','paper_validation','source_reference'):
                        assert current.get(field) == old.get(field), field
                    readiness = pipeline.paper_execution_readiness(current)
                    result['total'] += 1
                    result['ready' if readiness['ready'] else 'needs_source_clarification'] += 1
                    reasons.update(readiness.get('reasons') or [])
                    for level in range(1, 6):
                        if current.get('strategy_ir') and NoahStrategyIR.validate(current['strategy_ir'])['valid']:
                            projected = NoahStrategyIR.project(current['strategy_ir'], level)
                            assert projected['level'] == level
                            result['level_projections'] += 1
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            result['original_stores_unchanged'] += 1
    print(json.dumps({'counts':dict(result),'blocking_reasons':dict(reasons),'source_mutations':0,'real_orders':0},ensure_ascii=False))


if __name__ == '__main__':
    run(sys.argv[1])
