#!/usr/bin/env python3
"""Time the bundled demo suite at several concurrency levels.

Calls the model for real with the cache off, so every level costs a full suite
of provider calls.

    uv run python scripts/bench_concurrency.py --model openai/gpt-4o-mini --repeat 3
"""

import argparse
import asyncio
import csv
from pathlib import Path
import time

from voicetest.container import create_container
from voicetest.demo import get_demo_agent
from voicetest.demo import get_demo_tests
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services import build_app_services


async def bench(
    model: str, levels: list[int], repeat: int, max_turns: int, out: Path | None
) -> None:
    svc = build_app_services(create_container())
    graph = await svc.agents.import_agent(get_demo_agent())
    cases = [TestCase.model_validate(t) for t in get_demo_tests()] * repeat

    rows = []
    baseline = None
    print(f"{len(cases)} tests, {model}, max_turns={max_turns}")
    print(f"{'concurrency':>11} {'wall_s':>8} {'speedup':>8} {'mean_test_s':>12} {'errors':>7}")
    for level in levels:
        options = RunOptions(
            agent_model=model,
            simulator_model=model,
            judge_model=model,
            max_turns=max_turns,
            concurrency=level,
            no_cache=True,
        )
        start = time.monotonic()
        run = await svc.test_execution.run_tests(graph, cases, options)
        wall = time.monotonic() - start
        baseline = baseline or wall
        mean_test = sum(r.duration_ms for r in run.results) / len(run.results) / 1000
        errors = sum(1 for r in run.results if r.status == "error")
        row = {
            "concurrency": level,
            "wall_s": round(wall, 1),
            "speedup": round(baseline / wall, 2),
            "mean_test_s": round(mean_test, 1),
            "errors": errors,
        }
        rows.append(row)
        print(
            f"{level:>11} {row['wall_s']:>8} {row['speedup']:>8} "
            f"{row['mean_test_s']:>12} {errors:>7}"
        )

    if out:
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--repeat", type=int, default=2, help="Copies of the 8 demo tests")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    asyncio.run(bench(args.model, args.levels, args.repeat, args.max_turns, args.out))


if __name__ == "__main__":
    main()
