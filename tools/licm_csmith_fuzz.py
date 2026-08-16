#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd, *, timeout=120, check=True, stdout=None):
    p = subprocess.run(
        [str(x) for x in cmd],
        text=True,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(map(str, cmd))}\n{p.stderr}"
        )
    return p


def execute(path: Path, timeout=5):
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
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures = []
    transformed_programs = 0

    for seed in range(args.first_seed, args.first_seed + args.count):
        case = out / f'seed-{seed:06d}'
        case.mkdir(parents=True, exist_ok=True)
        source = case / 'test.c'
        input_ll = case / 'input.ll'
        baseline_ll = case / 'baseline.ll'
        transformed_ll = case / 'transformed.ll'

        with source.open('w') as f:
            generated = run([
                args.csmith,
                '--seed', str(seed),
                '--no-packed-struct',
                '--no-volatiles',
            ], timeout=30, stdout=f)
        if generated.stderr:
            (case / 'csmith.stderr').write_text(generated.stderr)

        try:
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
                transformed_programs += 1

            seed_result = {'seed': seed, 'runs': {}}
            mismatch = False
            for level in ['-O0', '-O2']:
                baseline_exe = case / f'baseline_{level[1:]}'
                transformed_exe = case / f'transformed_{level[1:]}'
                run([args.clang, level, baseline_ll, '-o', baseline_exe], timeout=60)
                run([args.clang, level, transformed_ll, '-o', transformed_exe], timeout=60)

                baseline = execute(baseline_exe)
                transformed = execute(transformed_exe)
                same = baseline == transformed
                seed_result['runs'][level] = {
                    'same': same,
                    'baseline': baseline,
                    'transformed': transformed,
                }
                if not same:
                    mismatch = True

            if mismatch:
                failures.append(seed_result)
                (case / 'mismatch.json').write_text(json.dumps(seed_result, indent=2))
                print(f'MISMATCH seed={seed}', flush=True)
                break
            else:
                # Keep the source and a tiny status, discard large intermediate
                # files for successful cases to keep CI artifacts manageable.
                (case / 'ok.json').write_text(json.dumps({'seed': seed, 'same': True}))
                input_ll.unlink(missing_ok=True)
                baseline_ll.unlink(missing_ok=True)
                transformed_ll.unlink(missing_ok=True)
                for exe in case.glob('baseline_*'):
                    exe.unlink(missing_ok=True)
                for exe in case.glob('transformed_*'):
                    exe.unlink(missing_ok=True)

        except subprocess.TimeoutExpired as exc:
            failures.append({'seed': seed, 'infrastructure_timeout': str(exc)})
            print(f'TIMEOUT seed={seed}: {exc}', file=sys.stderr)
            break
        except Exception as exc:
            failures.append({'seed': seed, 'infrastructure_error': str(exc)})
            print(f'ERROR seed={seed}: {exc}', file=sys.stderr)
            break

        if seed % 10 == 0:
            print(f'checked through seed {seed}', flush=True)

    summary = {
        'first_seed': args.first_seed,
        'requested_count': args.count,
        'checked_count': (
            args.count if not failures else
            max(0, failures[0].get('seed', args.first_seed) - args.first_seed + 1)
        ),
        'programs_whose_ir_changed': transformed_programs,
        'failures': failures,
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)

    if failures:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
