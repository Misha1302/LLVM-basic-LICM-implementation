#!/usr/bin/env python3
import argparse
import difflib
import json
from pathlib import Path

from licm_random_fuzz import execute, generate_source, run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clang', default='clang-22')
    ap.add_argument('--opt', default='opt-22')
    ap.add_argument('--plugin', required=True)
    ap.add_argument('--out', default='fuzz-random-out')
    ap.add_argument('--seed', type=lambda x: int(x, 0), default=0xC0FFEE)
    ap.add_argument('--integer-cases', type=int, default=1200)
    ap.add_argument('--pointer-cases', type=int, default=200)
    ap.add_argument('--float-cases', type=int, default=200)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source, case_count = generate_source(
        args.seed,
        args.integer_cases,
        args.pointer_cases,
        args.float_cases,
    )

    # The original randomized harness mixed absolute stack addresses into the
    # observable result. Baseline/transformed are separate processes, so ASLR
    # made those outputs differ even when the programs were semantically
    # equivalent. Keep the pointer tests, but normalize the observable value to
    # an offset within the same array object.
    source = source.replace(
        'uintptr_t u = (uintptr_t)q;',
        'uintptr_t u = (uintptr_t)(q - p);',
    )

    src = out / 'corpus.c'
    src.write_text(source)

    input_ll = out / 'input.ll'
    baseline_ll = out / 'baseline.ll'
    transformed_ll = out / 'transformed.ll'

    run([
        args.clang, '-std=c17', '-O0', '-Xclang', '-disable-O0-optnone',
        '-S', '-emit-llvm', src, '-o', input_ll,
    ])
    run([
        args.opt, '-passes=mem2reg,loop-simplify', '-verify-each', '-S',
        input_ll, '-o', baseline_ll,
    ])
    run([
        args.opt, f'-load-pass-plugin={args.plugin}',
        '-passes=mem2reg,loop-simplify,LicmOptimizationPass', '-verify-each',
        '-S', input_ll, '-o', transformed_ll,
    ])

    before = baseline_ll.read_text().splitlines(keepends=True)
    after = transformed_ll.read_text().splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        before,
        after,
        fromfile='baseline.ll',
        tofile='transformed.ll',
        n=1,
    ))
    (out / 'ir.diff').write_text(''.join(diff))

    summary = {
        'seed': args.seed,
        'case_count': case_count,
        'ir_changed': bool(diff),
        'ir_diff_lines': len(diff),
        'runs': {},
    }
    mismatch = False

    for level in ['-O0', '-O2']:
        baseline_exe = out / f'baseline_{level[1:]}'
        transformed_exe = out / f'transformed_{level[1:]}'
        run([args.clang, level, baseline_ll, '-lm', '-o', baseline_exe])
        run([args.clang, level, transformed_ll, '-lm', '-o', transformed_exe])

        baseline = execute(baseline_exe)
        transformed = execute(transformed_exe)
        same = baseline == transformed
        summary['runs'][level] = {
            'same': same,
            'baseline_returncode': baseline[0],
            'transformed_returncode': transformed[0],
            'baseline_stderr': baseline[2],
            'transformed_stderr': transformed[2],
        }

        if not same:
            mismatch = True
            baseline_lines = baseline[1].splitlines()
            transformed_lines = transformed[1].splitlines()
            first = None
            for index in range(max(len(baseline_lines), len(transformed_lines))):
                b = baseline_lines[index] if index < len(baseline_lines) else '<EOF>'
                t = transformed_lines[index] if index < len(transformed_lines) else '<EOF>'
                if b != t:
                    first = {
                        'line': index + 1,
                        'baseline': b,
                        'transformed': t,
                    }
                    break
            summary['runs'][level]['first_output_difference'] = first
            (out / f'baseline_stdout_{level[1:]}.txt').write_text(baseline[1])
            (out / f'transformed_stdout_{level[1:]}.txt').write_text(transformed[1])

    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print('\n=== RANDOM FUZZ V2 SUMMARY ===')
    print(json.dumps(summary, indent=2))

    if mismatch:
        print('DIFFERENTIAL MISMATCH FOUND')
        return 2

    print('No runtime mismatch found in randomized plain-C corpus.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
