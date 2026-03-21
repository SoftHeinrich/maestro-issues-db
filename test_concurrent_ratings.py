"""
Comprehensive concurrent rating submission test suite.

Tests:
1. Sequential baseline
2. Concurrent different students (3 threads)
3. Concurrent same student, different questions (6 threads)
4. High-concurrency stress (20+ threads)
5. Rapid-fire bursts (multiple waves)
6. Mixed read/write (tasks fetch + rating submit simultaneously)
7. Duplicate submission (same student, same question, same time)
8. Invalid submissions under load (bad student ID, bad task)
9. Data integrity (verify actual solution content, not just counts)
10. File corruption resilience (read file after heavy writes)
"""

import json
import requests
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://maestro.localhost:4269/issues-db-api"
VERIFY_SSL = False

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PASS = 0
FAIL = 0


def record(name, passed):
    global PASS, FAIL
    if passed:
        PASS += 1
        print(f"  [{name}] PASS")
    else:
        FAIL += 1
        print(f"  [{name}] FAIL")


def get_student_tasks(student_id: str, password: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/experiment/tasks",
        json={"MtrNo": student_id, "password": password},
        verify=VERIFY_SSL,
    )
    resp.raise_for_status()
    return resp.json()


def submit_rating(student_id: str, task_name: str, question_key: str,
                  query: str, issue_ids: list, timeout: float = 30) -> requests.Response:
    ratings = [{"issue_id": iid, "rating": "3"} for iid in issue_ids]
    payload = {
        "matriculationNumber": student_id,
        "taskId": task_name,
        "questionKey": question_key,
        "searchQuery": query,
        "ratings": ratings,
    }
    return requests.post(
        f"{BASE_URL}/experiment/submit-ratings",
        json=payload,
        verify=VERIFY_SSL,
        timeout=timeout,
    )


def get_solution_counts(student_ids: list) -> dict:
    counts = {}
    for sid in student_ids:
        try:
            data = get_student_tasks(sid, sid)
            total = 0
            for task in data.get("tasks", []):
                for qkey, sols in (task.get("solutions") or {}).items():
                    if isinstance(sols, list):
                        total += len(sols)
            counts[sid] = total
        except Exception as e:
            counts[sid] = f"error: {e}"
    return counts


def get_full_solutions(student_id: str) -> dict:
    """Return {taskName: {questionKey: [solutions]}}."""
    data = get_student_tasks(student_id, student_id)
    result = {}
    for task in data.get("tasks", []):
        tn = task["taskName"]
        result[tn] = {}
        for qkey, sols in (task.get("solutions") or {}).items():
            result[tn][qkey] = sols if isinstance(sols, list) else []
    return result


def clean_test_data():
    """Reset test student solutions to empty."""
    for sid in ["test001", "test002", "test003"]:
        try:
            # Submit a dummy then we'll clean via direct container call
            pass
        except Exception:
            pass
    # Clean via the container
    import subprocess
    subprocess.run([
        "docker", "exec", "issues-db-api", "python3", "-c",
        "import json\n"
        "with open('/python-docker/app/experiment_data.json') as f:\n"
        "    data = json.load(f)\n"
        "for sid in ['test001','test002','test003']:\n"
        "    if sid in data['student_data']:\n"
        "        for task in data['student_data'][sid]['tasks']:\n"
        "            task['solutions'] = {}\n"
        "with open('/python-docker/app/experiment_data.json','w') as f:\n"
        "    json.dump(data, f, indent=2)\n"
    ], capture_output=True)


def get_all_student_tasks():
    """Return {sid: [(taskName, questionKey), ...]} for test students."""
    result = {}
    for sid in ["test001", "test002", "test003"]:
        data = get_student_tasks(sid, sid)
        pairs = []
        for task in data["tasks"]:
            for qkey in task["questions"]:
                pairs.append((task["taskName"], qkey))
        result[sid] = pairs
    return result


# ===========================================================================
# Test 1: Sequential baseline
# ===========================================================================
def test_01_sequential():
    print("=" * 70)
    print("TEST 1: Sequential submissions (baseline)")
    print("=" * 70)

    students = ["test001", "test002", "test003"]
    before = get_solution_counts(students)

    ok = True
    for sid in students:
        data = get_student_tasks(sid, sid)
        task = data["tasks"][0]
        resp = submit_rating(sid, task["taskName"],
                             list(task["questions"].keys())[0],
                             f"seq-{sid}", ["SEQ-1"])
        if resp.status_code != 200:
            print(f"  {sid}: HTTP {resp.status_code}")
            ok = False

    after = get_solution_counts(students)
    for sid in students:
        expected = (before[sid] if isinstance(before[sid], int) else 0) + 1
        actual = after[sid] if isinstance(after[sid], int) else 0
        if actual != expected:
            ok = False
            print(f"  {sid}: expected {expected}, got {actual}")

    record("sequential_baseline", ok)
    print()


# ===========================================================================
# Test 2: Concurrent different students
# ===========================================================================
def test_02_concurrent_different_students():
    print("=" * 70)
    print("TEST 2: Concurrent submissions — 3 different students")
    print("=" * 70)

    students = ["test001", "test002", "test003"]
    before = get_solution_counts(students)

    submissions = []
    for sid in students:
        data = get_student_tasks(sid, sid)
        task = data["tasks"][0]
        submissions.append((sid, task["taskName"],
                            list(task["questions"].keys())[0]))

    barrier = threading.Barrier(len(submissions))
    errors = []

    def go(sid, tn, qk):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"conc-diff-{sid}", ["CD-1"])
            if r.status_code != 200:
                errors.append(f"{sid}: HTTP {r.status_code}")
        except Exception as e:
            errors.append(f"{sid}: {e}")

    threads = [threading.Thread(target=go, args=s) for s in submissions]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)
    after = get_solution_counts(students)

    ok = len(errors) == 0
    for sid in students:
        expected = (before[sid] if isinstance(before[sid], int) else 0) + 1
        actual = after[sid] if isinstance(after[sid], int) else 0
        if actual != expected:
            ok = False
            print(f"  {sid}: expected {expected}, got {actual}")

    if errors:
        for e in errors: print(f"  ERROR: {e}")
    record("concurrent_different_students", ok)
    print()


# ===========================================================================
# Test 3: Concurrent same student, different questions
# ===========================================================================
def test_03_concurrent_same_student():
    print("=" * 70)
    print("TEST 3: Concurrent — same student, 6 different questions")
    print("=" * 70)

    sid = "test001"
    before = get_solution_counts([sid])
    all_tq = get_all_student_tasks()[sid][:6]

    barrier = threading.Barrier(len(all_tq))
    errors = []

    def go(tn, qk):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"conc-same-{qk}", ["CS-1"])
            if r.status_code != 200:
                errors.append(f"{qk}: HTTP {r.status_code}")
        except Exception as e:
            errors.append(f"{qk}: {e}")

    threads = [threading.Thread(target=go, args=(tn, qk)) for tn, qk in all_tq]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)
    after = get_solution_counts([sid])
    expected = (before[sid] if isinstance(before[sid], int) else 0) + len(all_tq)
    actual = after[sid] if isinstance(after[sid], int) else 0
    ok = actual == expected and len(errors) == 0

    if not ok:
        print(f"  expected {expected}, got {actual}, errors: {errors}")
    record("concurrent_same_student", ok)
    print()


# ===========================================================================
# Test 4: High concurrency stress — 20 threads
# ===========================================================================
def test_04_stress_20():
    print("=" * 70)
    print("TEST 4: Stress — 20 concurrent submissions across 3 students")
    print("=" * 70)

    students = ["test001", "test002", "test003"]
    before = get_solution_counts(students)

    # Build submission list: cycle through students and their questions
    all_tq = get_all_student_tasks()
    submissions = []
    for sid in students:
        for tn, qk in all_tq[sid]:
            submissions.append((sid, tn, qk))

    # Take 20
    to_submit = submissions[:20]
    per_student = defaultdict(int)
    for sid, _, _ in to_submit:
        per_student[sid] += 1

    print(f"  Submitting {len(to_submit)} ({dict(per_student)})")

    barrier = threading.Barrier(len(to_submit))
    errors = []
    lock = threading.Lock()

    def go(sid, tn, qk, idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"stress20-{idx}", [f"S20-{idx}"])
            if r.status_code != 200:
                with lock:
                    errors.append(f"{sid}/{qk}: HTTP {r.status_code} {r.text[:100]}")
        except Exception as e:
            with lock:
                errors.append(f"{sid}/{qk}: {e}")

    threads = [threading.Thread(target=go, args=(s, t, q, i))
               for i, (s, t, q) in enumerate(to_submit)]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(1)
    after = get_solution_counts(students)

    ok = True
    for sid in students:
        expected = (before[sid] if isinstance(before[sid], int) else 0) + per_student[sid]
        actual = after[sid] if isinstance(after[sid], int) else 0
        if actual != expected:
            ok = False
            print(f"  {sid}: expected {expected}, got {actual}")

    if errors:
        ok = False
        for e in errors[:5]:
            print(f"  ERROR: {e}")

    record("stress_20_threads", ok)
    print()


# ===========================================================================
# Test 5: Rapid-fire bursts — 5 waves of 5 concurrent
# ===========================================================================
def test_05_burst_waves():
    print("=" * 70)
    print("TEST 5: Burst waves — 5 waves of 5 concurrent submissions")
    print("=" * 70)

    sid = "test001"
    before = get_solution_counts([sid])
    all_tq = get_all_student_tasks()[sid]

    total_submitted = 0
    errors = []

    for wave in range(5):
        tq = all_tq[:5]
        barrier = threading.Barrier(len(tq))

        def go(tn, qk, w):
            barrier.wait()
            try:
                r = submit_rating(sid, tn, qk, f"wave{w}-{qk}", [f"W{w}-1"])
                if r.status_code != 200:
                    errors.append(f"wave{w}/{qk}: HTTP {r.status_code}")
            except Exception as e:
                errors.append(f"wave{w}/{qk}: {e}")

        threads = [threading.Thread(target=go, args=(tn, qk, wave))
                   for tn, qk in tq]
        for t in threads: t.start()
        for t in threads: t.join()
        total_submitted += len(tq)
        time.sleep(0.1)  # Small gap between waves

    time.sleep(0.5)
    after = get_solution_counts([sid])
    expected = (before[sid] if isinstance(before[sid], int) else 0) + total_submitted
    actual = after[sid] if isinstance(after[sid], int) else 0
    ok = actual == expected and len(errors) == 0

    if not ok:
        print(f"  expected {expected}, got {actual}, errors: {len(errors)}")
        for e in errors[:3]:
            print(f"  ERROR: {e}")
    record("burst_waves", ok)
    print()


# ===========================================================================
# Test 6: Mixed read + write — tasks fetch and submit simultaneously
# ===========================================================================
def test_06_mixed_read_write():
    print("=" * 70)
    print("TEST 6: Mixed read/write — concurrent reads + writes")
    print("=" * 70)

    students = ["test001", "test002", "test003"]
    before = get_solution_counts(students)

    all_tq = get_all_student_tasks()
    errors = []
    read_errors = []
    write_count = 0
    lock = threading.Lock()

    # 5 writers + 10 readers simultaneously
    barrier = threading.Barrier(15)

    def writer(sid, tn, qk, idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"mixed-w-{idx}", [f"MW-{idx}"])
            if r.status_code != 200:
                with lock:
                    errors.append(f"write {sid}/{qk}: HTTP {r.status_code}")
        except Exception as e:
            with lock:
                errors.append(f"write {sid}/{qk}: {e}")

    def reader(sid, idx):
        barrier.wait()
        try:
            data = get_student_tasks(sid, sid)
            if "tasks" not in data:
                with lock:
                    read_errors.append(f"read {sid}: no tasks in response")
        except Exception as e:
            with lock:
                read_errors.append(f"read {sid}: {e}")

    threads = []
    # 5 writers
    write_subs = []
    for sid in students:
        tn, qk = all_tq[sid][0]
        write_subs.append((sid, tn, qk))
    # Add 2 more for test001
    for i in range(2):
        tn, qk = all_tq["test001"][i + 1]
        write_subs.append(("test001", tn, qk))

    for i, (sid, tn, qk) in enumerate(write_subs):
        threads.append(threading.Thread(target=writer, args=(sid, tn, qk, i)))

    # 10 readers
    for i in range(10):
        sid = students[i % 3]
        threads.append(threading.Thread(target=reader, args=(sid, i)))

    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)
    after = get_solution_counts(students)

    ok = len(errors) == 0 and len(read_errors) == 0
    per_student = defaultdict(int)
    for sid, _, _ in write_subs:
        per_student[sid] += 1

    for sid in students:
        expected = (before[sid] if isinstance(before[sid], int) else 0) + per_student[sid]
        actual = after[sid] if isinstance(after[sid], int) else 0
        if actual != expected:
            ok = False
            print(f"  {sid}: expected {expected}, got {actual}")

    if errors: print(f"  Write errors: {errors[:3]}")
    if read_errors: print(f"  Read errors: {read_errors[:3]}")
    record("mixed_read_write", ok)
    print()


# ===========================================================================
# Test 7: Duplicate submissions — same student, same question, same time
# ===========================================================================
def test_07_duplicate_submissions():
    print("=" * 70)
    print("TEST 7: Duplicate — 5 threads submit same student+question")
    print("=" * 70)

    sid = "test001"
    before = get_solution_counts([sid])
    data = get_student_tasks(sid, sid)
    task = data["tasks"][0]
    tn = task["taskName"]
    qk = list(task["questions"].keys())[0]

    n = 5
    barrier = threading.Barrier(n)
    statuses = []
    lock = threading.Lock()

    def go(idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"dup-{idx}", [f"DUP-{idx}"])
            with lock:
                statuses.append(r.status_code)
        except Exception as e:
            with lock:
                statuses.append(f"error: {e}")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)
    after = get_solution_counts([sid])

    expected = (before[sid] if isinstance(before[sid], int) else 0) + n
    actual = after[sid] if isinstance(after[sid], int) else 0

    # All 5 should succeed (duplicates are allowed — appended to solutions list)
    all_200 = all(s == 200 for s in statuses)
    ok = actual == expected and all_200

    if not ok:
        print(f"  expected {expected}, got {actual}")
        print(f"  statuses: {statuses}")

    record("duplicate_submissions", ok)
    print()


# ===========================================================================
# Test 8: Invalid submissions under load
# ===========================================================================
def test_08_invalid_under_load():
    print("=" * 70)
    print("TEST 8: Invalid submissions mixed with valid under load")
    print("=" * 70)

    sid = "test001"
    before = get_solution_counts([sid])
    data = get_student_tasks(sid, sid)
    task = data["tasks"][0]
    tn = task["taskName"]
    qk = list(task["questions"].keys())[0]

    barrier = threading.Barrier(8)
    results = {}
    lock = threading.Lock()

    def valid_submit(idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"valid-{idx}", [f"V-{idx}"])
            with lock:
                results[f"valid-{idx}"] = r.status_code
        except Exception as e:
            with lock:
                results[f"valid-{idx}"] = f"error: {e}"

    def invalid_submit_bad_student(idx):
        barrier.wait()
        try:
            r = submit_rating("nonexistent999", tn, qk, f"bad-student-{idx}", ["X-1"])
            with lock:
                results[f"bad-student-{idx}"] = r.status_code
        except Exception as e:
            with lock:
                results[f"bad-student-{idx}"] = f"error: {e}"

    def invalid_submit_bad_task(idx):
        barrier.wait()
        try:
            r = submit_rating(sid, "FakeTask999", qk, f"bad-task-{idx}", ["X-1"])
            with lock:
                results[f"bad-task-{idx}"] = r.status_code
        except Exception as e:
            with lock:
                results[f"bad-task-{idx}"] = f"error: {e}"

    def invalid_submit_wrong_password(idx):
        barrier.wait()
        try:
            r = requests.post(
                f"{BASE_URL}/experiment/tasks",
                json={"MtrNo": sid, "password": "wrong"},
                verify=VERIFY_SSL,
            )
            with lock:
                results[f"wrong-pw-{idx}"] = r.status_code
        except Exception as e:
            with lock:
                results[f"wrong-pw-{idx}"] = f"error: {e}"

    threads = []
    # 4 valid
    for i in range(4):
        threads.append(threading.Thread(target=valid_submit, args=(i,)))
    # 2 bad student
    for i in range(2):
        threads.append(threading.Thread(target=invalid_submit_bad_student, args=(i,)))
    # 1 bad task
    threads.append(threading.Thread(target=invalid_submit_bad_task, args=(0,)))
    # 1 wrong password
    threads.append(threading.Thread(target=invalid_submit_wrong_password, args=(0,)))

    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)
    after = get_solution_counts([sid])

    # 4 valid should succeed, invalids should fail without corrupting data
    expected = (before[sid] if isinstance(before[sid], int) else 0) + 4
    actual = after[sid] if isinstance(after[sid], int) else 0

    valid_ok = all(results.get(f"valid-{i}") == 200 for i in range(4))
    bad_student_ok = all(results.get(f"bad-student-{i}") == 400 for i in range(2))
    bad_task_ok = results.get("bad-task-0") == 400
    wrong_pw_ok = results.get("wrong-pw-0") == 401
    count_ok = actual == expected

    ok = valid_ok and bad_student_ok and bad_task_ok and wrong_pw_ok and count_ok

    if not ok:
        print(f"  counts: expected {expected}, got {actual}")
        print(f"  results: {results}")
        print(f"  valid_ok={valid_ok} bad_student_ok={bad_student_ok} "
              f"bad_task_ok={bad_task_ok} wrong_pw_ok={wrong_pw_ok}")

    record("invalid_under_load", ok)
    print()


# ===========================================================================
# Test 9: Data integrity — verify solution content, not just counts
# ===========================================================================
def test_09_data_integrity():
    print("=" * 70)
    print("TEST 9: Data integrity — verify solution content after concurrent writes")
    print("=" * 70)

    sid = "test001"
    data = get_student_tasks(sid, sid)
    task = data["tasks"][0]
    tn = task["taskName"]
    qk = list(task["questions"].keys())[0]

    # Record solutions before
    before_sols = get_full_solutions(sid)
    before_count = len(before_sols.get(tn, {}).get(qk, []))

    n = 8
    barrier = threading.Barrier(n)
    errors = []
    lock = threading.Lock()

    # Each thread uses a unique query and issue_id
    def go(idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"integrity-query-{idx}",
                              [f"INTEG-{idx}-A", f"INTEG-{idx}-B"])
            if r.status_code != 200:
                with lock:
                    errors.append(f"{idx}: HTTP {r.status_code}")
        except Exception as e:
            with lock:
                errors.append(f"{idx}: {e}")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.5)

    # Verify each submission's content is present
    after_sols = get_full_solutions(sid)
    solutions = after_sols.get(tn, {}).get(qk, [])
    new_solutions = solutions[before_count:]

    # Check we have all n new solutions
    count_ok = len(new_solutions) == n

    # Check each unique query is present
    queries_found = {s["searchQuery"] for s in new_solutions}
    expected_queries = {f"integrity-query-{i}" for i in range(n)}
    queries_ok = expected_queries.issubset(queries_found)

    # Check each solution has correct issue IDs
    content_ok = True
    for sol in new_solutions:
        q = sol["searchQuery"]
        idx_str = q.split("-")[-1]
        expected_ids = {f"INTEG-{idx_str}-A", f"INTEG-{idx_str}-B"}
        actual_ids = {r["issue_id"] for r in sol["ratings"]}
        if expected_ids != actual_ids:
            content_ok = False
            print(f"  Mismatch for {q}: expected {expected_ids}, got {actual_ids}")

    ok = count_ok and queries_ok and content_ok and len(errors) == 0

    if not ok:
        print(f"  count_ok={count_ok} (expected {n}, got {len(new_solutions)})")
        print(f"  queries_ok={queries_ok}")
        if not queries_ok:
            print(f"    missing: {expected_queries - queries_found}")
        print(f"  content_ok={content_ok}")
        if errors:
            print(f"  errors: {errors}")

    record("data_integrity", ok)
    print()


# ===========================================================================
# Test 10: File corruption resilience — heavy writes then verify readability
# ===========================================================================
def test_10_corruption_resilience():
    print("=" * 70)
    print("TEST 10: Corruption resilience — 30 rapid writes then verify file")
    print("=" * 70)

    students = ["test001", "test002", "test003"]
    all_tq = get_all_student_tasks()

    n = 30
    barrier = threading.Barrier(n)
    statuses = []
    lock = threading.Lock()

    submissions = []
    i = 0
    while len(submissions) < n:
        for sid in students:
            for tn, qk in all_tq[sid]:
                submissions.append((sid, tn, qk))
                if len(submissions) >= n:
                    break
            if len(submissions) >= n:
                break

    def go(sid, tn, qk, idx):
        barrier.wait()
        try:
            r = submit_rating(sid, tn, qk, f"corrupt-test-{idx}", [f"CT-{idx}"])
            with lock:
                statuses.append((sid, r.status_code))
        except Exception as e:
            with lock:
                statuses.append((sid, f"error: {e}"))

    threads = [threading.Thread(target=go, args=(s, t, q, i))
               for i, (s, t, q) in enumerate(submissions)]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(1)

    # Verify file is still readable — multiple reads in a row
    read_ok = True
    for _ in range(5):
        for sid in students:
            try:
                data = get_student_tasks(sid, sid)
                if "tasks" not in data:
                    read_ok = False
                    print(f"  {sid}: missing 'tasks' in response")
            except Exception as e:
                read_ok = False
                print(f"  {sid}: read failed: {e}")

    all_200 = all(s == 200 for _, s in statuses if isinstance(s, int))
    http_errors = [(sid, s) for sid, s in statuses if s != 200]
    if http_errors:
        print(f"  HTTP errors: {http_errors[:5]}")

    ok = read_ok and all_200
    record("corruption_resilience", ok)
    print()


# ===========================================================================
# Main
# ===========================================================================
if __name__ == "__main__":
    print()
    print("=" * 70)
    print("COMPREHENSIVE CONCURRENT RATING TEST SUITE")
    print("=" * 70)
    print()

    clean_test_data()
    time.sleep(0.5)

    test_01_sequential()
    test_02_concurrent_different_students()
    test_03_concurrent_same_student()
    test_04_stress_20()
    test_05_burst_waves()

    # Clean before remaining tests to keep counts manageable
    clean_test_data()
    time.sleep(0.5)

    test_06_mixed_read_write()
    test_07_duplicate_submissions()
    test_08_invalid_under_load()

    clean_test_data()
    time.sleep(0.5)

    test_09_data_integrity()
    test_10_corruption_resilience()

    # Final cleanup
    clean_test_data()

    print()
    print("=" * 70)
    print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} tests")
    print("=" * 70)
    if FAIL > 0:
        print("SOME TESTS FAILED — see details above")
    else:
        print("ALL TESTS PASSED")
