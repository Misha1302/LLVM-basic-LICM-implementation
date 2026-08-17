import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = Path(__file__).resolve().parent

PLUGIN = PROJECT_ROOT / "cmake-build-debug" / "LicmOptimizationPass.so"


def run(
        args: Sequence[str],
        *,
        check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=10,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed:\n"
            f"{' '.join(args)}\n\n"
            f"stdout:\n{result.stdout}\n\n"
            f"stderr:\n{result.stderr}"
        )

    return result


def run_clang(input_c: Path, output_ll: Path) -> None:
    run([
        "clang",
        "-O0",
        "-Xclang",
        "-disable-O0-optnone",
        "-S",
        "-emit-llvm",
        str(input_c.resolve()),
        "-o",
        str(output_ll.resolve()),
    ])


def run_opt(
        input_ll: Path,
        output_ll: Path,
        passes: Sequence[str],
        *,
        load_plugin: bool,
) -> None:
    command = ["opt"]

    if load_plugin:
        command.append(f"-load-pass-plugin={PLUGIN.resolve()}")

    command.extend([
        f"-passes={','.join(passes)}",
        "-verify-each",
        "-S",
        str(input_ll.resolve()),
        "-o",
        str(output_ll.resolve()),
    ])

    run(command)


def run_lli(input_ll: Path) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "lli",
            str(input_ll.resolve()),
        ],
        check=False,
    )


def run_diff(before: Path, after: Path) -> str:
    result = run(
        [
            "diff",
            "-u",
            str(before.resolve()),
            str(after.resolve()),
        ],
        check=False,
    )

    return result.stdout


def assert_same_behavior(
        baseline: Path,
        optimized: Path,
) -> None:
    before = run_lli(baseline)
    after = run_lli(optimized)

    if before.returncode != after.returncode:
        raise AssertionError(
            "Different exit codes:\n"
            f"before: {before.returncode}\n"
            f"after:  {after.returncode}"
        )

    if before.stdout != after.stdout:
        raise AssertionError(
            "Different stdout:\n"
            f"before:\n{before.stdout}\n"
            f"after:\n{after.stdout}"
        )

    if before.stderr != after.stderr:
        raise AssertionError(
            "Different stderr:\n"
            f"before:\n{before.stderr}\n"
            f"after:\n{after.stderr}"
        )


def assert_expected_transformation(
        test_dir: Path,
        baseline: Path,
        optimized: Path,
) -> None:
    expect_path = test_dir / "expect.txt"

    if not expect_path.exists():
        raise AssertionError(f"expect.txt was not found on {expect_path}")

    expectation = expect_path.read_text().strip().upper()

    before = baseline.read_text()
    after = optimized.read_text()

    changed = before != after

    match expectation:
        case "CHANGE":
            if not changed:
                raise AssertionError("LICM was expected to change IR, but IR remained unchanged")
        case "NO_CHANGE":
            if changed:
                raise AssertionError("LICM was NOT expected to change IR, but IR was changed")
        case _:
            raise ValueError(f"Unknown expectation in {expect_path}: {expectation!r}")


def run_test(test_dir: Path) -> None:
    source = test_dir / "test.c"

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)

        source_ll = test_dir / "source.ll"
        baseline_ll = test_dir / "baseline.ll"
        optimized_ll = test_dir / "optimized.ll"

        # C -> LLVM IR
        run_clang(source, source_ll)

        # LLVM IR without our LICM
        run_opt(
            source_ll,
            baseline_ll,
            ["mem2reg", "loop-simplify"],
            load_plugin=False,
        )

        # LLVM IR with our LICM
        run_opt(
            source_ll,
            optimized_ll,
            ["mem2reg", "loop-simplify", "LicmOptimizationPass"],
            load_plugin=True,
        )

        # Semantic correctness
        assert_same_behavior(baseline_ll, optimized_ll)

        # Did LICM perform the transformation we expected?
        assert_expected_transformation(test_dir, baseline_ll, optimized_ll, )


def main() -> None:
    if not PLUGIN.exists():
        raise FileNotFoundError(f"Plugin not found: {PLUGIN}")

    tests = sorted(path.parent for path in TESTS_ROOT.glob("*/test.c"))

    if not tests:
        raise RuntimeError(f"No tests found in {TESTS_ROOT}")

    passed = 0

    for test_dir in tests:
        name = test_dir.name

        try:
            run_test(test_dir)

        except Exception as error:
            print(f"[FAIL] {name}")
            print(error)
            print()

        else:
            print(f"[PASS] {name}")
            passed += 1

    print()
    print(f"{passed}/{len(tests)} tests passed")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
