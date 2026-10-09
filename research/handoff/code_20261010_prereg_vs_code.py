"""Blind definition audit: metadata counts and explicitly requested spec hashes only.

No repository modules imported; no score/price/return/IC/CI values selected.
Run from any directory: python research/handoff/code_20261010_prereg_vs_code.py
"""
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[2]


def literal(node, env):
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [literal(x, env) for x in node.elts]
        return tuple(values) if isinstance(node, ast.Tuple) else set(values) if isinstance(node, ast.Set) else values
    if isinstance(node, ast.Dict):
        return {literal(k, env): literal(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -literal(node.operand, env)
    raise ValueError('Nonliteral expression excluded')


def constants(filename):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
    env = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = literal(node.value, env)
            except (ValueError, KeyError, TypeError):
                pass
    return env


def spec_digest(env, mid, track):
    if track == 'lowvol':
        m = env['MODELS'][mid]
        payload = dict(factors=[(f, env['FACTORS'][f]) for f in m['factors']],
                       universe=list(m['uni']), method='cross_sectional_pct_rank_sum_v1')
    else:
        payload = dict(factors=[(f, *env['FACTORS'][f]) for f in env['MODELS'][mid]],
                       universe=env['GUARD_SPEC'],
                       method='wu_pct_rank_sum_v1(core_required,aux_nan=0.5,whole_universe_single_rank)')
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    if now.weekday() < 5 and dt.time(20, 10) <= now.time().replace(tzinfo=None) < dt.time(22, 30):
        raise SystemExit('Restricted hours: skipped before reading repository or DB')
    result = {'checked_kst': now.isoformat(), 'tracks': {}, 'models': {}}
    low = constants('lowvol_score.py')
    wu = constants('wu_score.py')
    v3 = constants('v3_rescore.py')
    reg = constants('checkup.py')['REG_DATE']
    with readonly(ROOT / 'history.db') as con, readonly(ROOT.parent / 'dh-q7m3k-data/ohlcv.db') as ocon:
        for track, table, env in [('lowvol', 'lowvol_scores', low), ('wu', 'wu_scores', wu), ('v3', 'v3_scores', v3)]:
            ids = [r[0] for r in con.execute(f'SELECT DISTINCT model_id FROM {table} ORDER BY model_id')]
            denom = con.execute(f'SELECT COUNT(DISTINCT model_id) FROM {table}').fetchone()[0]
            result['tracks'][track] = dict(distinct_model_id=denom, ids=ids,
                retired_ids_present=sorted(set(ids) & env['RETIRED']),
                retired_ids_missing=sorted(env['RETIRED'] - set(ids)))
        dates = [str(r[0]) for r in ocon.execute('SELECT DISTINCT date FROM daily_ohlcv ORDER BY date')]
        didx = {d: i for i, d in enumerate(dates)}
        counts = [(str(r), n) for r, n in con.execute('SELECT run_id, COUNT(*) FROM stage1_oversold GROUP BY run_id')]
        median_count = statistics.median(n for _, n in counts)
        partial = {r for r, n in counts if n < median_count * .30}
        double = set()
        for table in ['v3_scores', 'lowvol_scores', 'wu_scores']:
            for rid, mid, lo, hi in con.execute(f'SELECT run_id, model_id, MIN(frozen_at), MAX(frozen_at) FROM {table} GROUP BY run_id, model_id'):
                if lo and hi and (dt.datetime.fromisoformat(hi) - dt.datetime.fromisoformat(lo)).total_seconds() >= 3600:
                    double.add(str(rid))
        result['metadata'] = dict(last_price_date=dates[-1], partial_runs=sorted(partial), double_runs=sorted(double))

        def anchor(rid):
            if rid in didx:
                return didx[rid]
            d = dt.datetime.strptime(rid, '%Y%m%d')
            for k in range(1, 6):
                p = (d - dt.timedelta(days=k)).strftime('%Y%m%d')
                if p in didx:
                    return didx[p]
            return None

        for mid, base, track, table, env in [('lv_e', 'lv_b', 'lowvol', 'lowvol_scores', low), ('sv_b', 'sv_a', 'wu', 'wu_scores', wu)]:
            runs = [str(r[0]) for r in con.execute(f'SELECT DISTINCT run_id FROM {table} WHERE model_id=? AND run_id>=? ORDER BY run_id', (mid, reg[mid]))]
            cand = {}
            for rid in runs:
                t = anchor(rid)
                if rid not in partial | double and t is not None:
                    cand.setdefault(t, []).append(rid)
            keep = [min([r for r in rr if r in didx] or rr) for rr in cand.values()]
            sets = {}
            for model in [mid, base]:
                sets[model] = {(str(r), m, t) for r, m, t in con.execute(f'SELECT run_id, market, ticker FROM {table} WHERE model_id=? AND run_id>=?', (model, reg[mid])) if str(r) in keep}
            hashes = [r[0] for r in con.execute(f'SELECT DISTINCT spec_hash FROM {table} WHERE model_id=? AND run_id>=? ORDER BY spec_hash', (mid, reg[mid]))]
            result['models'][mid] = dict(reg_date=reg[mid], first_oos_run=runs[0] if runs else None,
                price_date_difference=len(dates)-1-didx[reg[mid]], price_dates_inclusive=sum(d >= reg[mid] for d in dates),
                price_dates_without_kept_run=[d for d in dates if d >= reg[mid] and d not in keep],
                effective_anchors=len(keep), date_closed_h20_anchors=sum(anchor(r)+1+20 < len(dates) for r in keep),
                calculated_spec_hash=spec_digest(env, mid, track), stored_oos_spec_hashes=hashes,
                paired_universe_rows=len(sets[mid] & sets[base]), model_only_universe_rows=len(sets[mid] - sets[base]),
                reference_only_universe_rows=len(sets[base] - sets[mid]),
                run_20260911_in_kept='20260911' in keep)
        result['models']['ls_t1'] = {'registered_model_id_in_source': 'ls_t1', 'denominator_in_code': 1,
            'db_distinct_model_id': 'not available: large_final has no model_id', 'spec_hash': 'not registered'}
        result['models']['ls_t1']['model_id_column_present'] = 'model_id' in [r[1] for r in con.execute('PRAGMA table_info(large_final)')]
        result['models']['ls_t1']['latest_universe_tickers'] = con.execute('SELECT COUNT(DISTINCT ticker) FROM large_final WHERE run_id=(SELECT MAX(run_id) FROM large_final)').fetchone()[0]
        result['models']['lv_e']['upstream_stage3_rows_30_to_40_oos'] = con.execute('SELECT COUNT(*) FROM stage3_final WHERE run_id>=? AND oversold_score>=30 AND oversold_score<40', (reg['lv_e'],)).fetchone()[0]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
