#!/usr/bin/env python3
import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path


def run(cmd, *, cwd=None, timeout=120, check=True):
    print('+', ' '.join(map(str, cmd)), flush=True)
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if p.stdout:
        print(p.stdout, end='')
    if p.stderr:
        print(p.stderr, end='', file=sys.stderr)
    if check and p.returncode != 0:
        raise RuntimeError(f'command failed ({p.returncode}): {cmd}')
    return p


def generate_corpus() -> str:
    parts = [r'''#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define U64(x) ((unsigned long long)(x))
''']
    calls = []
    case_id = 0

    def add_case(params, body, safe_args, dormant_args):
        nonlocal case_id
        name = f'case_{case_id:04d}'
        parts.append(f'''\nstatic unsigned long long {name}({params})\n{{\n{body}\n}}\n''')
        calls.append(
            f'    printf("{case_id:04d}:%llu:%llu\\n", '
            f'{name}({safe_args}), {name}({dormant_args}));'
        )
        case_id += 1

    # Signed-overflow-producing expressions in conditional loop blocks.
    # The dormant call chooses inputs for which evaluating the expression would
    # be UB in C, but gate == 0 means the source program never evaluates it.
    for k in [1, 2, 3, 7, 17, 127, 1024, 65535]:
        add_case(
            'int a, int gate',
            f'''    unsigned long long r = 0;\n    for (int i = 0; i < 9; ++i) {{\n        if (gate) {{\n            int x = a + {k};\n            int y = (x ^ 0x13579bdf) + 3;\n            r = r * 131u + (unsigned)y + (unsigned)i;\n        }}\n    }}\n    return r;''',
            '31, 1', f'INT_MAX, 0')

    for k in [1, 2, 5, 19, 257, 4096]:
        add_case(
            'int a, int gate',
            f'''    unsigned long long r = 17;\n    for (int i = 0; i < 7; ++i) {{\n        if (gate) {{\n            int x = a - {k};\n            int y = x * 3 + 1;\n            r ^= (unsigned)y + (unsigned)i;\n        }}\n    }}\n    return r;''',
            '10000, 1', 'INT_MIN, 0')

    for k in [2, 3, 5, 9, 31, 257]:
        add_case(
            'int a, int gate',
            f'''    unsigned long long r = 3;\n    for (int i = 0; i < 6; ++i) {{\n        if (gate) {{\n            int x = a * {k};\n            int y = x - 11;\n            r = r * 33u + (unsigned)y + (unsigned)i;\n        }}\n    }}\n    return r;''',
            '123, 1', 'INT_MAX, 0')

    add_case(
        'int a, int gate',
        '''    unsigned long long r = 0;\n    for (int i = 0; i < 8; ++i) {\n        if (gate) {\n            int x = -a;\n            int y = x ^ 0x2468ace;\n            r += (unsigned)y + (unsigned)i;\n        }\n    }\n    return r;''',
        '1234, 1', 'INT_MIN, 0')

    # Invalid shifts, again only in the dormant branch for the dangerous call.
    for signedness in ['int', 'unsigned']:
        for op in ['<<', '>>']:
            for bad in [32, 33, 63]:
                add_case(
                    f'{signedness} a, int shift, int gate',
                    f'''    unsigned long long r = 0;\n    for (int i = 0; i < 5; ++i) {{\n        if (gate) {{\n            {signedness} x = a {op} shift;\n            {signedness} y = x ^ ({signedness})0x55aa55aaU;\n            r += (unsigned)y + (unsigned)i;\n        }}\n    }}\n    return r;''',
                    '123, 3, 1', f'123, {bad}, 0')

    # FP -> integer conversions: out-of-range/NaN values are only supplied when
    # the containing branch is not executed in the source program.
    for ty, safe, bad in [
        ('int', '123.75', '1.0e300'),
        ('int', '-123.75', 'NAN'),
        ('unsigned', '123.75', '-1.0e300'),
        ('long long', '123456.5', '1.0e300'),
    ]:
        add_case(
            'double a, int gate',
            f'''    unsigned long long r = 9;\n    for (int i = 0; i < 7; ++i) {{\n        if (gate) {{\n            {ty} x = ({ty})a;\n            unsigned long long y = (unsigned long long)x ^ 0x12345678ULL;\n            r = r * 17u + y + (unsigned)i;\n        }}\n    }}\n    return r;''',
            f'{safe}, 1', f'{bad}, 0')

    # Pointer arithmetic that would be invalid for the dormant NULL case.
    for off in [1, 2, 7, 1024]:
        add_case(
            'int *p, ptrdiff_t off, int gate',
            '''    unsigned long long r = 0;\n    for (int i = 0; i < 6; ++i) {\n        if (gate) {\n            int *q = p + off;\n            uintptr_t v = (uintptr_t)q;\n            uintptr_t w = v ^ (uintptr_t)0x1234;\n            r ^= (unsigned long long)w + (unsigned)i;\n        }\n    }\n    return r;''',
            f'(int[2048]){{0}}, {off}, 1', f'NULL, {off}, 0')

    # Standard C abs/labs/llabs.  Clang normally lowers these to LLVM intrinsics.
    # INT_MIN-like inputs are only used when gate == 0.
    add_case(
        'int a, int gate',
        '''    unsigned long long r = 0;\n    for (int i = 0; i < 8; ++i) {\n        if (gate) {\n            int x = abs(a);\n            r += (unsigned)x + (unsigned)i;\n        }\n    }\n    return r;''',
        '-123, 1', 'INT_MIN, 0')
    add_case(
        'long a, int gate',
        '''    unsigned long long r = 0;\n    for (int i = 0; i < 8; ++i) {\n        if (gate) {\n            long x = labs(a);\n            r += (unsigned long long)x + (unsigned)i;\n        }\n    }\n    return r;''',
        '-123L, 1', 'LONG_MIN, 0')
    add_case(
        'long long a, int gate',
        '''    unsigned long long r = 0;\n    for (int i = 0; i < 8; ++i) {\n        if (gate) {\n            long long x = llabs(a);\n            r += (unsigned long long)x + (unsigned)i;\n        }\n    }\n    return r;''',
        '-123LL, 1', 'LLONG_MIN, 0')

    # Short-circuit and nested conditional CFG shapes.
    for k in [1, 7, 31, 255]:
        add_case(
            'int a, int gate',
            f'''    unsigned long long r = 0;\n    for (int i = 0; i < 10; ++i) {{\n        if (gate && (a + {k}) > 0) {{\n            int x = (a + {k}) * 3;\n            r += (unsigned)x + (unsigned)i;\n        }}\n    }}\n    return r;''',
            '10, 1', 'INT_MAX, 0')

    # Nested loops: invariant for inner loop, and potentially poison when the
    # outer guard is false.
    for k in [1, 3, 17, 1024]:
        add_case(
            'int a, int gate',
            f'''    unsigned long long r = 0;\n    for (int i = 0; i < 4; ++i) {{\n        if (gate) {{\n            for (int j = 0; j < 5; ++j) {{\n                int x = a + {k};\n                int y = x ^ i;\n                r += (unsigned)y + (unsigned)j;\n            }}\n        }}\n    }}\n    return r;''',
            '100, 1', 'INT_MAX, 0')

    # Zero-trip loops: the loop body contains operations that would be UB for
    # the dormant arguments, but n == 0 means the source never evaluates them.
    for k in [1, 17, 1024, 65535]:
        add_case(
            'int a, int n',
            f'''    unsigned long long r = 0;\n    for (int i = 0; i < n; ++i) {{\n        int x = a + {k};\n        int y = x * 3;\n        r += (unsigned)y + (unsigned)i;\n    }}\n    return r;''',
            '10, 5', 'INT_MAX, 0')

    # Conditional VLA: stresses alloca/stacksave handling.  A non-positive VLA
    # size is only provided for a branch that is not executed.
    for safe_n, bad_n in [(4, 0), (8, -1), (16, 0)]:
        add_case(
            'int n, int gate',
            '''    unsigned long long r = 0;\n    for (int i = 0; i < 3; ++i) {\n        if (gate) {\n            int a[n];\n            a[0] = i + 11;\n            r += (unsigned)a[0];\n        }\n    }\n    return r;''',
            f'{safe_n}, 1', f'{bad_n}, 0')

    # Standard math operations.  Most of these should be rejected by the pass
    # when the call may observe errno/fenv; including them checks that the
    # verifier remains conservative around ordinary libc calls.
    for fn, safe, dormant in [
        ('fabs', '-3.5', 'NAN'),
        ('floor', '3.75', 'NAN'),
        ('ceil', '3.25', 'NAN'),
        ('trunc', '-3.75', 'NAN'),
        ('sqrt', '9.0', '-1.0'),
    ]:
        add_case(
            'double a, int gate',
            f'''    unsigned long long r = 0;\n    for (int i = 0; i < 4; ++i) {{\n        if (gate) {{\n            double x = {fn}(a);\n            double y = x + 7.0;\n            r += (unsigned long long)(y * 16.0) + (unsigned)i;\n        }}\n    }}\n    return r;''',
            f'{safe}, 1', f'{dormant}, 0')

    # A few branch-heavy combinations using only ordinary C operators.
    for k in [1, 2, 17, 127, 4095]:
        add_case(
            'int a, int b, int gate',
            f'''    unsigned long long r = 1;\n    for (int i = 0; i < 11; ++i) {{\n        if (gate) {{\n            int x = a + {k};\n            int y = (b & 1) ? (x * 3) : (x - 9);\n            int z = (y > b) ? (y ^ b) : (y + b);\n            r = r * 257u + (unsigned)z + (unsigned)i;\n        }} else {{\n            r += (unsigned)i;\n        }}\n    }}\n    return r;''',
            '100, 7, 1', 'INT_MAX, 7, 0')

    parts.append('\nint main(void)\n{\n    int dummy[4096] = {0};\n    (void)dummy;\n')
    parts.extend(call + '\n' for call in calls)
    parts.append('    return 0;\n}\n')
    source = ''.join(parts)
    if '__asm__' in source or 'asm(' in source or 'llvm.' in source:
        raise AssertionError('corpus accidentally contains forbidden low-level constructs')
    return source


def execute(path: Path):
    p = subprocess.run([str(path)], text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=30)
    return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clang', default='clang-22')
    ap.add_argument('--opt', default='opt-22')
    ap.add_argument('--plugin', required=True)
    ap.add_argument('--out', default='fuzz-out')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    src = out / 'corpus.c'
    src.write_text(generate_corpus())

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
                                     tofile='transformed.ll', n=3))
    (out / 'ir.diff').write_text(''.join(diff))

    results = {'ir_changed': bool(diff), 'ir_diff_lines': len(diff), 'runs': {}}
    mismatch = False

    for level in ['-O0', '-O2']:
        base_exe = out / f'baseline_{level[1:]}'
        pass_exe = out / f'transformed_{level[1:]}'
        run([args.clang, level, baseline_ll, '-lm', '-o', base_exe])
        run([args.clang, level, transformed_ll, '-lm', '-o', pass_exe])
        rb = execute(base_exe)
        rt = execute(pass_exe)
        same = rb == rt
        results['runs'][level] = {'same': same, 'baseline': rb, 'transformed': rt}
        if not same:
            mismatch = True
            b_lines = rb['stdout'].splitlines()
            t_lines = rt['stdout'].splitlines()
            first = None
            for i, (b, t) in enumerate(zip(b_lines, t_lines)):
                if b != t:
                    first = {'line': i + 1, 'baseline': b, 'transformed': t}
                    break
            if first is None and len(b_lines) != len(t_lines):
                first = {'line': min(len(b_lines), len(t_lines)) + 1,
                         'baseline': '<EOF>' if len(b_lines) <= len(t_lines) else b_lines[len(t_lines)],
                         'transformed': '<EOF>' if len(t_lines) <= len(b_lines) else t_lines[len(b_lines)]}
            results['runs'][level]['first_output_difference'] = first

    (out / 'summary.json').write_text(json.dumps(results, indent=2))
    print('\n=== SUMMARY ===')
    print(json.dumps({
        'ir_changed': results['ir_changed'],
        'ir_diff_lines': results['ir_diff_lines'],
        'O0_same': results['runs']['-O0']['same'],
        'O2_same': results['runs']['-O2']['same'],
    }, indent=2))

    if mismatch:
        print('DIFFERENTIAL MISMATCH FOUND', file=sys.stderr)
        return 2
    print('No runtime mismatch found in this deterministic plain-C corpus.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
