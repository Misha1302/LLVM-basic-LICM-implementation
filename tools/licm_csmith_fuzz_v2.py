#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd, *, timeout=120, stdout=None):
    p = subprocess.run(
        [str(x) for x in cmd],
        text=True,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(map(str, cmd))}\n{p.stderr}"
        )
    return p


def execute(path: Path, timeout=3):
    p = subprocess.run(
        [str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return {
        'returncode': p.returncode,
        'stdout': p.stdout,
        'stderr': p.stderr,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clang', default='clang-22')
    ap.add_argument('--opt', default='opt-22')
    ap.add_argument('--csmith', default='csmith')
    ap.add_argument('--csmith-include', default='/usr/include/csmith')
    ap.add_argument('--plugin', required=True)
    ap.add_argument('--out', default='csmith-out')
    ap.add_argument('--first-seed', type=int, default=1)
    ap.add_argument('--count', type=int, default=100)
    ap.add_argument('--runtime-timeout', type=float, default=3.0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    checked = 0
    skipped_slow = []
    changed = 0
    failures = []

    for seed in range(args.first_seed, args.first_seed + args.count):
        case = out / f'seed-{seed:06d}'
        case.mkdir(parents=True, exist_ok=True)
        source = case / 'test.c'
        input_ll = case / 'input.ll'
        baseline_ll = case / 'baseline.ll'
        transformed_ll = case / 'transformed.ll'
        baseline_exe = case / 'baseline_O2'
        transformed_exe = case / 'transformed_O2'

        try:
            with source.open('w') as f:
                run([
                    args.csmith,
                    '--seed', str(seed),
                    '--no-packed-struct',
                    '--no-volatiles',
                ], timeout=30, stdout=f)

            run([
                args.clang,
                '-std=c99',
                '-O0',
                '-Xclang', '-disable-O0-optnone',
                '-I', args.csmith_include,
                '-S', '-emit-llvm',
                source,
                '-o', input_ll,
            ], timeout=60)

            run([
                args.opt,
                '-passes=mem2reg,loop-simplify',
                '-verify-each',
                '-S', input_ll,
                '-o', baseline_ll,
            ], timeout=60)

            run([
                args.opt,
                f'-load-pass-plugin={args.plugin}',
                '-passes=mem2reg,loop-simplify,LicmOptimizationPass',
                '-verify-each',
                '-S', input_ll,
                '-o', transformed_ll,
            ], timeout=60)

            if baseline_ll.read_bytes() != transformed_ll.read_bytes():
                changed += 1

            run([args.clang, '-O2', baseline_ll, '-o', baseline_exe], timeout=60)
            run([args.clang, '-O2', transformed_ll, '-o', transformed_exe], timeout=60)

            try:
                baseline = execute(baseline_exe, timeout=args.runtime_timeout)
            except subprocess.TimeoutExpired:
                skipped_slow.append(seed)
                (case / 'skipped.json').write_text(json.dumps({
                    'seed': seed,
                    'reason': 'baseline runtime timeout',
                }))
                for path in [input_ll, baseline_ll, transformed_ll, baseline_exe, transformed_exe]:
                    path.unlink(missing_ok=True)
                continue

            try:
                transformed = execute(transformed_exe, timeout=args.runtime_timeout)
            except subprocess.TimeoutExpired as exc:
                failure = {
                    'seed': seed,
                    'kind': 'transformed_runtime_timeout',
                    'baseline': baseline,
                    'timeout': args.runtime_timeout,
                    'error': str(exc),
                }
                failures.append(failure)
                (case / 'mismatch.json').write_text(json.dumps(failure, indent=2))
                print(f'MISMATCH seed={seed}: transformed timed out while baseline completed')
                break

            checked += 1
            if baseline != transformed:
                failure = {
                    'seed': seed,
                    'kind': 'output_mismatch',
                    'baseline': baseline,
                    'transformed': transformed,
                }
                failures.append(failure)
                (case / 'mismatch.json').write_text(json.dumps(failure, indent=2))
                print(f'MISMATCH seed={seed}')
                break

            (case / 'ok.json').write_text(json.dumps({'seed': seed, 'same': True}))
            for path in [input_ll, baseline_ll, transformed_ll, baseline_exe, transformed_exe]:
                path.unlink(missing_ok=True)

        except Exception as exc:
            failure = {
                'seed': seed,
                'kind': 'infrastructure_error',
                'error': str(exc),
            }
            failures.append(failure)
            (case / 'error.json').write_text(json.dumps(failure, indent=2))
            print(f'ERROR seed={seed}: {exc}', file=sys.stderr)
            break

        if seed % 10 == 0:
            print(
                f'progress seed={seed} checked={checked} '
                f'skipped_slow={len(skipped_slow)} changed={changed}',
                flush=True,
            )

    summary = {
        'first_seed': args.first_seed,
        'requested_count': args.count,
        'checked_fast_programs': checked,
        'skipped_slow_count': len(skipped_slow),
        'skipped_slow_seeds': skipped_slow,
        'programs_whose_ir_changed': changed,
        'failures': failures,
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)

    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
