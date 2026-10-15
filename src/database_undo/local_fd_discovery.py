"""
Per-batch FD discovery
"""
import json
import random
from collections import Counter


def _byte_size(value):
    return len(json.dumps(value, default=str))


def _group_by(sample, source_cols, target_col):
    groups = {}
    for row in sample:
        key = tuple(row[c] for c in source_cols)
        groups.setdefault(key, []).append(row[target_col])
    return groups


def _mode_and_coverage(sample, source_cols, target_col):
    groups = _group_by(sample, source_cols, target_col)
    mapping = {key: Counter(b_vals).most_common(1)[0][0] for key, b_vals in groups.items()}
    correct = sum(1 for row in sample
                  if mapping.get(tuple(row[c] for c in source_cols)) == row[target_col])
    coverage = correct / len(sample) if sample else 0.0
    return mapping, coverage


def _depends_on(col, target, rules, seen=None):
    if seen is None:
        seen = set()
    if col in seen:
        return False  # already checked this branch, avoid infinite loop
    seen.add(col)
    if col not in rules:
        return False
    for src in rules[col]["source"]:
        if src == target:
            return True
        if _depends_on(src, target, rules, seen):
            return True
    return False


def _creates_cycle(source_cols, target_col, rules):
    """cycle prevention
    returns True if any column in source_cols already depends on
    target_col from a previously chosen rule"""
    for src in source_cols:
        if src == target_col or _depends_on(src, target_col, rules):
            return True
    return False


def _build_predictor_set(sample, all_cols, target, rules, min_group_size, target_coverage,
                          max_predictors=4):
    """greedily grow a set of source columns for one target, adding
    whichever column most improves coverage each step, until
    target_coverage is hit, no more improvement is found, or groups get
    too small to trust."""
    chosen = []
    best_coverage = 0.0
    best_mapping = {}
    while len(chosen) < max_predictors:
        step_best = None  # (coverage, col, mapping)
        for col in all_cols:
            if col == target or col in chosen:
                continue
            trial_cols = chosen + [col]
            if _creates_cycle(trial_cols, target, rules):
                continue
            groups = _group_by(sample, trial_cols, target)
            if not groups or len(sample) / len(groups) < min_group_size:
                continue  # too small
            mapping, coverage = _mode_and_coverage(sample, trial_cols, target)
            if step_best is None or coverage > step_best[0]:
                step_best = (coverage, col, mapping)

        if step_best is None or step_best[0] <= best_coverage + 1e-9:
            break  # no column improves things further
        best_coverage, added_col, best_mapping = step_best
        chosen.append(added_col)
        if best_coverage >= target_coverage:
            break
    return chosen, best_mapping, best_coverage


def discover_rules(batch_rows, pk_cols, sample_size=300, min_group_size=20.0,
                    min_coverage_to_accept=0.5, target_coverage=0.8,
                    baseline_margin_for_confidence=0.1, constant_threshold=0.98,
                    max_predictors=4):
    """Returns {target_col: {"source": [...], "mapping": {...},
    "coverage": f, "baseline": f, "likely_real": bool,
    "rows_free": int, "rows_patched": int,
    "bytes_saved": int, "bytes_still_needed": int}}.

    "likely_real" is a confidence LABEL, not a filter.
     true if the rule beats the target's baseline."""
    if not batch_rows:
        return {}

    all_cols = [c for c in batch_rows[0].keys() if c not in pk_cols]
    sample = batch_rows if len(batch_rows) <= sample_size else random.sample(batch_rows, sample_size)

    rules = {}
    remaining = set(all_cols)

    for col in list(remaining):
        vals = [row[col] for row in batch_rows]
        mode_val, count = Counter(vals).most_common(1)[0]
        if count / len(vals) >= constant_threshold:
            rules[col] = {"source": [], "mapping": {(): mode_val},
                          "coverage": count / len(vals), "baseline": count / len(vals),
                          "likely_real": True}
            remaining.discard(col)

    # Process biggest-storage-impact columns first
    avg_size = {col: sum(_byte_size(row[col]) for row in batch_rows) / len(batch_rows)
                for col in remaining}
    processing_order = sorted(remaining, key=lambda c: (-avg_size[c], c))

    for target in processing_order:
        target_vals = [row[target] for row in sample]
        baseline = Counter(target_vals).most_common(1)[0][1] / len(target_vals)

        chosen_cols, mapping, coverage = _build_predictor_set(
            sample, all_cols, target, rules, min_group_size, target_coverage, max_predictors)

        if not chosen_cols or coverage < min_coverage_to_accept:
            continue  # nothing found

        # Rebuild the mapping from the full batch (if sample size < batch)
        full_mapping, full_coverage = _mode_and_coverage(batch_rows, chosen_cols, target)
        rules[target] = {
            "source": chosen_cols, "mapping": full_mapping,
            "coverage": full_coverage, "baseline": baseline,
            "likely_real": (full_coverage - baseline) >= baseline_margin_for_confidence,
        }

    # Storage-savings estimate per rule, in bytes
    for target, rule in rules.items():
        bytes_saved, bytes_still_needed, n_free, n_patched = 0, 0, 0, 0
        for row in batch_rows:
            key = tuple(row[c] for c in rule["source"])
            value_bytes = _byte_size(row[target])
            if rule["mapping"].get(key) == row[target]:
                bytes_saved += value_bytes
                n_free += 1
            else:
                bytes_still_needed += value_bytes
                n_patched += 1
        rule["rows_free"] = n_free
        rule["rows_patched"] = n_patched
        rule["bytes_saved"] = bytes_saved
        rule["bytes_still_needed"] = bytes_still_needed

    return rules