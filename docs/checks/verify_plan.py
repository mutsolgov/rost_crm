"""Check planning arithmetic, dependency graph and requirement coverage.

Standard-library-only checks of planning artifacts, not application tests.
Run from any directory: python outputs/checks/verify_plan.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "planning"
plan = (ROOT / "02-development-plan.md").read_text(encoding="utf-8")
acceptance = (ROOT / "03-acceptance-scenarios.md").read_text(encoding="utf-8")


def references(value, prefix):
    result = set()
    pattern = rf"\b{prefix}(\d{{2}})(?:[–-](?:{prefix})?(\d{{2}}))?"
    for match in re.finditer(pattern, value):
        start = int(match.group(1))
        end = int(match.group(2) or start)
        assert end >= start, f"Reversed range: {match.group(0)}"
        result.update(f"{prefix}{number:02d}" for number in range(start, end + 1))
    return result


tasks = {}
for line in plan.splitlines():
    if not re.match(r"^\| B\d{2} \|", line):
        continue
    columns = [column.strip() for column in line.split("|")[1:-1]]
    assert len(columns) == 6, line
    task_id = columns[0]
    assert task_id not in tasks, task_id
    bounds = re.fullmatch(r"(\d+)[–-](\d+)", columns[4])
    assert bounds, f"Invalid estimate: {task_id}"
    low, high = map(int, bounds.groups())
    assert 0 < low <= high
    tasks[task_id] = {
        "dependencies": references(columns[2], "B"),
        "estimate": (low, high),
    }

assert set(tasks) == {f"B{i:02d}" for i in range(1, 41)}
for task_id, task in tasks.items():
    assert task_id not in task["dependencies"], f"Self dependency: {task_id}"
    assert task["dependencies"] <= set(tasks), f"Missing dependency: {task_id}"

done, active = set(), set()


def visit(task_id):
    assert task_id not in active, f"Dependency cycle at {task_id}"
    if task_id in done:
        return
    active.add(task_id)
    for dependency in tasks[task_id]["dependencies"]:
        visit(dependency)
    active.remove(task_id)
    done.add(task_id)


for task_id in tasks:
    visit(task_id)


def total(ids):
    return tuple(sum(tasks[task_id]["estimate"][i] for task_id in ids) for i in (0, 1))


stages = [
    (1, 4, (11, 19)), (5, 10, (15, 27)), (11, 21, (34, 57)),
    (22, 29, (26, 47)), (30, 36, (22, 37)), (37, 40, (13, 22)),
]
for first, last, expected in stages:
    assert total({f"B{i:02d}" for i in range(first, last + 1)}) == expected
assert total(tasks) == (121, 209)

demo = references("B01–B18, B20–B26, B34–B36, B39", "B")
pilot_ready = demo | references("B19, B27–B33, B37", "B")
pilot_done = pilot_ready | {"B38"}
for name, ids, expected in [
    ("D", demo, (85, 145)),
    ("P-ready", pilot_ready, (114, 197)),
    ("P-done", pilot_done, (118, 204)),
    ("O", set(tasks), (121, 209)),
]:
    assert total(ids) == expected, (name, total(ids), expected)
    missing = {d for t in ids for d in tasks[t]["dependencies"] if d not in ids}
    assert not missing, f"Gate {name} missing dependencies: {missing}"
    print(f"PASS gate {name}: {len(ids)} tasks, {expected[0]}-{expected[1]} person-days")

required = {f"R{i:02d}" for i in range(1, 30)}
case_ids = set(re.findall(r"^### (AC\d{2})\.", acceptance, flags=re.MULTILINE))
assert case_ids == {f"AC{i:02d}" for i in range(1, 31)}
for document, prefix, allowed in [(plan, "B", set(tasks)), (acceptance, "AC", case_ids)]:
    mappings = {}
    for line in document.splitlines():
        match = re.match(r"^\| (R\d{2})(?: — [^|]*)? \| ([^|]+)\|", line)
        if match:
            requirement, targets = match.groups()
            assert requirement not in mappings, f"Duplicate coverage: {requirement}"
            mappings[requirement] = references(targets, prefix)
            assert mappings[requirement] and mappings[requirement] <= allowed
    assert set(mappings) == required, f"Incomplete {prefix} coverage"

for document in ROOT.glob("*.md"):
    text = document.read_text(encoding="utf-8")
    assert "\ufffd" not in text, f"Invalid text encoding: {document.name}"
    assert text.count("```") % 2 == 0, f"Unclosed code block: {document.name}"

print("PASS: 40 tasks, no dependency cycles, all stage totals match.")
print("PASS: R01-R29 mapped to existing tasks and 30 acceptance scenarios.")
