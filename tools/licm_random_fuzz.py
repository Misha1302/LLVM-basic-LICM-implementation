#!/usr/bin/env python3
import argparse
import difflib
import json
import random
import subprocess
import sys
from pathlib import Path


def run(cmd, timeout=180):
    print('+', ' '.join(map(str, cmd)), flush=True)
    p = subprocess.run([str(x) for x in cmd], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    if p.stdout:
        print(p.stdout, end='')
    if p.stderr:
        print(p.stderr, end='', file=sys.stderr)
    if p.returncode:
        raise RuntimeError(f'command failed ({p.returncode}): {cmd}')
    return p


def execute(path: Path):
    p = subprocess.run([str(path)], text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=45)
    return p.returncode, p.stdout, p.stderr


def generate_source(seed: int, integer_cases: int,
                    pointer_cases: int, float_cases: int) -> tuple[str, int]:
    rng = random.Random(seed)
    out = [r'''#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned long long ull;

''']
    calls = []
    cid = 0

    def emit_int(kind: str, k: int, c1: int, c2: int, sh: int,
                 safe_a: str, safe_b: str, bad_a: str, bad_b: str,
                 zero_trip: bool, loop_kind: str):
        nonlocal cid
        name = f'case_i_{cid:05d}'
        if kind == 'add':
            dangerous = f'int x = a + {k};'
        elif kind == 'sub':
            dangerous = f'int x = a - {k};'
        elif kind == 'mul':
            dangerous = f'int x = a * {k};'
        elif kind == 'neg':
            dangerous = 'int x = -a;'
        elif kind == 'shl':
            dangerous = 'int x = a << b;'
        elif kind == 'shr':
            dangerous = 'int x = a >> b;'
        elif kind == 'ushl':
            dangerous = 'int x = (int)((unsigned)a << b);'
        elif kind == 'abs':
            dangerous = 'int x = abs(a);'
        elif kind == 'divm1':
            dangerous = 'int x = a / -1;'
        elif kind == 'div3':
            dangerous = 'int x = a / 3;'
        elif kind == 'remm1':
            dangerous = 'int x = a % -1;'
        else:
            raise AssertionError(kind)

        body = f'''            {dangerous}\n            unsigned u = (unsigned)x;\n            unsigned v = (u * {c1}u + {c2}u) ^ (u >> {sh});\n            unsigned w = (v & 1u) ? (v ^ 0x9e3779b9u) : (v + 0x7f4a7c15u);\n            if ((w & 7u) == 3u)\n                r ^= (ull)w + (unsigned)i;\n            else\n                r = r * 257u + (ull)w + (unsigned)i;'''

        if loop_kind == 'for':
            loop = f'''    for (int i = 0; i < n; ++i) {{\n        if (gate) {{\n{body}\n        }} else {{\n            r += (unsigned)i;\n        }}\n    }}'''
        elif loop_kind == 'while':
            loop = f'''    int i = 0;\n    while (i < n) {{\n        if (gate) {{\n{body}\n        }} else {{\n            r += (unsigned)i;\n        }}\n        ++i;\n    }}'''
        elif loop_kind == 'nested':
            loop = f'''    for (int outer = 0; outer < n; ++outer) {{\n        if (gate) {{\n            for (int i = 0; i < 3; ++i) {{\n{body}\n            }}\n        }} else {{\n            r += (unsigned)outer;\n        }}\n    }}'''
        else:
            raise AssertionError(loop_kind)

        out.append(f'''static ull {name}(int a, int b, int gate, int n)\n{{\n    ull r = 0x123456789abcdefULL;\n{loop}\n    return r;\n}}\n\n''')

        if zero_trip:
            dormant = f'{bad_a}, {bad_b}, 1, 0'
        else:
            dormant = f'{bad_a}, {bad_b}, 0, {rng.randint(1, 9)}'
        safe_n = rng.randint(1, 9)
        calls.append(
            f'    printf("I{cid:05d}:%llu:%llu\\n", '
            f'{name}({safe_a}, {safe_b}, 1, {safe_n}), '
            f'{name}({dormant}));')
        cid += 1

    kinds = ['add', 'sub', 'mul', 'neg', 'shl', 'shr', 'ushl',
             'abs', 'divm1', 'div3', 'remm1']
    for _ in range(integer_cases):
        kind = rng.choice(kinds)
        k = rng.choice([1, 2, 3, 5, 7, 17, 31, 127, 1024, 65535])
        c1 = rng.choice([3, 5, 17, 33, 257, 65537])
        c2 = rng.randrange(1, 1 << 16)
        sh = rng.randrange(1, 16)
        zero_trip = rng.randrange(4) == 0
        loop_kind = rng.choice(['for', 'while', 'nested'])

        if kind == 'add':
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MAX', '3'
        elif kind == 'sub':
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MIN', '3'
        elif kind == 'mul':
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MAX', '3'
        elif kind == 'neg':
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MIN', '3'
        elif kind in ('shl', 'shr', 'ushl'):
            safe_a, safe_b = '123', str(rng.randrange(0, 8))
            bad_a, bad_b = '123', rng.choice(['32', '33', '63'])
        elif kind == 'abs':
            safe_a, safe_b, bad_a, bad_b = '-123', '3', 'INT_MIN', '3'
        elif kind in ('divm1', 'remm1'):
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MIN', '3'
        else:
            safe_a, safe_b, bad_a, bad_b = '123', '3', 'INT_MAX', '3'

        emit_int(kind, k, c1, c2, sh, safe_a, safe_b, bad_a, bad_b,
                 zero_trip, loop_kind)

    # Plain pointer arithmetic.  Invalid NULL arithmetic only appears in a
    # dormant branch or zero-trip loop.
    for pidx in range(pointer_cases):
        name = f'case_p_{pidx:05d}'
        off = rng.randrange(1, 64)
        c = rng.randrange(1, 1 << 16)
        loop_kind = rng.choice(['for', 'while'])
        if loop_kind == 'for':
            loop = f'''    for (int i = 0; i < n; ++i) {{\n        if (gate) {{\n            int *q = p + off;\n            uintptr_t u = (uintptr_t)q;\n            uintptr_t v = (u ^ (uintptr_t){c}) + (uintptr_t)(i + 1);\n            r = r * 131u + (ull)v;\n        }} else {{\n            r += (unsigned)i;\n        }}\n    }}'''
        else:
            loop = f'''    int i = 0;\n    while (i < n) {{\n        if (gate) {{\n            int *q = p + off;\n            uintptr_t u = (uintptr_t)q;\n            uintptr_t v = (u ^ (uintptr_t){c}) + (uintptr_t)(i + 1);\n            r = r * 131u + (ull)v;\n        }} else {{\n            r += (unsigned)i;\n        }}\n        ++i;\n    }}'''
        out.append(f'''static ull {name}(int *p, ptrdiff_t off, int gate, int n)\n{{\n    ull r = 7;\n{loop}\n    return r;\n}}\n\n''')
        if rng.randrange(3) == 0:
            dormant = f'NULL, {off}, 1, 0'
        else:
            dormant = f'NULL, {off}, 0, {rng.randint(1, 9)}'
        calls.append(
            f'    printf("P{pidx:05d}:%llu:%llu\\n", '
            f'{name}(storage, {off}, 1, {rng.randint(1, 7)}), '
            f'{name}({dormant}));')

    # Plain floating-to-integer conversions.  Invalid conversions are dormant.
    for fidx in range(float_cases):
        name = f'case_f_{fidx:05d}'
        target = rng.choice(['int', 'unsigned', 'long long'])
        bad = rng.choice(['NAN', 'INFINITY', '-INFINITY', '1.0e300', '-1.0e300'])
        c1 = rng.choice([3, 5, 17, 257])
        out.append(f'''static ull {name}(double a, int gate, int n)\n{{\n    ull r = 11;\n    for (int i = 0; i < n; ++i) {{\n        if (gate) {{\n            {target} x = ({target})a;\n            ull u = (ull)x;\n            ull v = (u * {c1}u + 0x12345u) ^ (u >> 7);\n            r = r * 33u + v + (unsigned)i;\n        }} else {{\n            r += (unsigned)i;\n        }}\n    }}\n    return r;\n}}\n\n''')
        if rng.randrange(3) == 0:
            dormant = f'{bad}, 1, 0'
        else:
            dormant = f'{bad}, 0, {rng.randint(1, 9)}'
        calls.append(
            f'    printf("F{fidx:05d}:%llu:%llu\\n", '
            f'{name}(123.75, 1, {rng.randint(1, 7)}), '
            f'{name}({dormant}));')

    out.append('int main(void)\n{\n    int storage[128] = {0};\n')
    out.extend(c + '\n' for c in calls)
    out.append('    return 0;\n}\n')
    src = ''.join(out)
    if '__asm__' in src or 'asm(' in src or 'llvm.' in src:
        raise AssertionError('forbidden low-level construct in generated C')
    return src, integer_cases + pointer_cases + float_cases


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
    source, case_count = generate_source(args.seed, args.integer_cases,
                                         args.pointer_cases, args.float_cases)
    src = out / 'corpus.c'
    src.write_text(source)

    input_ll = out / 'input.ll'
    baseline_ll = out / 'baseline.ll'
    transformed_ll = out / 'transformed.ll'
    run([args.clang, '-std=c17', '-O0', '-Xclang', '-disable-O0-optnone',
         '-S', '-emit-llvm', src, '-o', input_ll])
    run([args.opt, '-passes=mem2reg,loop-simplify', '-verify-each', '-S',
         input_ll, '-o', baseline_ll])
    run([args.opt, f'-load-pass-plugin={args.plugin}',
         '-passes=mem2reg,loop-simplify,LicmOptimizationPass', '-verify-each',
         '-S', input_ll, '-o', transformed_ll])

    before = baseline_ll.read_text().splitlines(keepends=True)
    after = transformed_ll.read_text().splitlines(keepends=True)
    diff = list(difflib.unified_diff(before, after, fromfile='baseline.ll',
                                     tofile='transformed.ll', n=1))
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
        b = out / f'baseline_{level[1:]}'
        t = out / f'transformed_{level[1:]}'
        run([args.clang, level, baseline_ll, '-lm', '-o', b])
        run([args.clang, level, transformed_ll, '-lm', '-o', t])
        rb = execute(b)
        rt = execute(t)
        same = rb == rt
        summary['runs'][level] = {
            'same': same,
            'baseline_returncode': rb[0],
            'transformed_returncode': rt[0],
            'baseline_stderr': rb[2],
            'transformed_stderr': rt[2],
        }
        if not same:
            mismatch = True
            bl = rb[1].splitlines()
            tl = rt[1].splitlines()
            first = None
            for idx in range(max(len(bl), len(tl))):
                bv = bl[idx] if idx < len(bl) else '<EOF>'
                tv = tl[idx] if idx < len(tl) else '<EOF>'
                if bv != tv:
                    first = {'line': idx + 1, 'baseline': bv, 'transformed': tv}
                    break
            summary['runs'][level]['first_output_difference'] = first
            (out / f'baseline_stdout_{level[1:]}.txt').write_text(rb[1])
            (out / f'transformed_stdout_{level[1:]}.txt').write_text(rt[1])

    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print('\n=== RANDOM FUZZ SUMMARY ===')
    print(json.dumps(summary, indent=2))
    if mismatch:
        print('DIFFERENTIAL MISMATCH FOUND', file=sys.stderr)
        return 2
    print('No runtime mismatch found in randomized plain-C corpus.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
