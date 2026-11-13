from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import product

from app.domain import Intensity, OptimizerResult, SessionCandidate, SessionPlan
from app.planning.load_adapter import SyntheticLoadAdapter
from app.planning.world import WorldSnapshot


class ConstraintOptimizer:
    """CP-SAT scheduler with a deterministic branch-and-bound fallback.

    OR-Tools is the intended production backend. The fallback exists so the repository
    remains executable in constrained/offline development environments.
    """

    def __init__(self, load_adapter: SyntheticLoadAdapter):
        self.load_adapter = load_adapter

    def solve(
        self,
        candidates: dict[str, list[SessionCandidate]],
        world: WorldSnapshot,
        parent_sessions: list[SessionPlan] | None = None,
    ) -> OptimizerResult:
        try:
            from ortools.sat.python import cp_model  # type: ignore
        except Exception:
            return self._solve_fallback(candidates, world, parent_sessions or [])
        return self._solve_cpsat(candidates, world, parent_sessions or [], cp_model)

    @staticmethod
    def _overlap(a: SessionCandidate, b: SessionCandidate) -> bool:
        return a.start_time < b.end_time and b.start_time < a.end_time

    def _candidate_hard_valid(self, candidate: SessionCandidate, world: WorldSnapshot) -> bool:
        match_start = datetime.fromisoformat(world.match['start_time'])
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        if candidate.start_time >= match_start:
            return False
        if candidate.intensity == Intensity.HIGH:
            if match_start - candidate.end_time < timedelta(hours=self.load_adapter.config.high_intensity_match_buffer_hours):
                return False
        if candidate.intensity == Intensity.MODERATE and candidate.intended_load >= self.load_adapter.config.moderate_buffer_min_load:
            if match_start - candidate.end_time < timedelta(hours=self.load_adapter.config.moderate_match_buffer_hours):
                return False
        return True

    def _churn_cost(self, candidate: SessionCandidate, parent_by_key: dict[str, SessionPlan]) -> int:
        # Penalize changes to an existing session so replanning favors schedule stability.
        parent = parent_by_key.get(candidate.logical_key)
        if not parent:
            return 0
        cost = 0
        if candidate.start_time != parent.start_time:
            cost += 50
        if candidate.session_type != parent.session_type:
            cost += 40
        if candidate.facility != parent.facility:
            cost += 30
        cost += abs(candidate.intended_load - parent.intended_load) // 5
        return cost

    def _solve_fallback(
        self,
        candidates: dict[str, list[SessionCandidate]],
        world: WorldSnapshot,
        parent_sessions: list[SessionPlan],
    ) -> OptimizerResult:
        keys = list(candidates)
        for key in keys:
            if not candidates[key]:
                return OptimizerResult(
                    status='INFEASIBLE',
                    conflicts=[f'NO_CANDIDATE:{key}'],
                    backend='deterministic_fallback',
                )
        parent_by_key = {s.logical_key: s for s in parent_sessions}
        best: tuple[int, list[SessionCandidate]] | None = None

        # Candidate sets are intentionally small in the MVP. Branch-and-bound avoids
        # adopting a fake "AI scheduler" while OR-Tools is unavailable in this runtime.
        def search(idx: int, chosen: list[SessionCandidate], cost: int) -> None:
            nonlocal best
            if best is not None and cost >= best[0]:
                return
            if idx == len(keys):
                plan = [
                    SessionPlan(
                        logical_key=c.logical_key,
                        session_type=c.session_type,
                        start_time=c.start_time,
                        duration_minutes=c.duration_minutes,
                        intended_load=c.intended_load,
                        intensity=c.intensity,
                        facility=c.facility,
                    ) for c in chosen
                ]
                load_eval = self.load_adapter.evaluate(world.gps.get('history', []), plan, datetime.fromisoformat(world.match['start_time']))
                if load_eval.feasible:
                    best = (cost, list(chosen))
                return
            key = keys[idx]
            for cand in candidates[key]:
                if not self._candidate_hard_valid(cand, world):
                    continue
                if any(self._overlap(cand, prior) for prior in chosen):
                    continue
                incremental = cand.preference_cost + self._churn_cost(cand, parent_by_key)
                search(idx + 1, chosen + [cand], cost + incremental)

        search(0, [], 0)
        if best is None:
            return OptimizerResult(
                status='INFEASIBLE',
                conflicts=['NO_COMBINATION_SATISFIES_HARD_CONSTRAINTS'],
                backend='deterministic_fallback',
            )
        _, selected = best
        selected = sorted(selected, key=lambda c: c.start_time)
        return OptimizerResult(
            status='FEASIBLE',
            sessions=[
                SessionPlan(
                    logical_key=c.logical_key,
                    session_type=c.session_type,
                    start_time=c.start_time,
                    duration_minutes=c.duration_minutes,
                    intended_load=c.intended_load,
                    intensity=c.intensity,
                    facility=c.facility,
                ) for c in selected
            ],
            objective_value=best[0],
            backend='deterministic_fallback',
        )

    def _solve_cpsat(self, candidates, world, parent_sessions, cp_model) -> OptimizerResult:
        model = cp_model.CpModel()
        parent_by_key = {s.logical_key: s for s in parent_sessions}
        vars_by_key: dict[str, list[tuple[SessionCandidate, object]]] = {}

        for key, items in candidates.items():
            valid = [c for c in items if self._candidate_hard_valid(c, world)]
            if not valid:
                return OptimizerResult(status='INFEASIBLE', conflicts=[f'NO_CANDIDATE:{key}'], backend='ortools_cp_sat')
            pairs = []
            for idx, c in enumerate(valid):
                var = model.NewBoolVar(f'{key}_{idx}')
                pairs.append((c, var))
            # Each logical session needs exactly one time/type option, not every candidate.
            model.Add(sum(var for _, var in pairs) == 1)
            vars_by_key[key] = pairs

        # Pairwise no-overlap constraints for candidate pairs that overlap in time.
        flat = [(key, c, v) for key, pairs in vars_by_key.items() for c, v in pairs]
        for i in range(len(flat)):
            key_a, a, va = flat[i]
            for j in range(i + 1, len(flat)):
                key_b, b, vb = flat[j]
                if key_a != key_b and self._overlap(a, b):
                    model.Add(va + vb <= 1)

        # Daily and rolling-load constraints are linear in candidate-selection variables.
        all_days = sorted({c.start_time.date() for _, c, _ in flat})
        for day in all_days:
            expr = [c.intended_load * v for _, c, v in flat if c.start_time.date() == day]
            if expr:
                model.Add(sum(expr) <= self.load_adapter.config.max_daily_load)

        for day in all_days:
            window_end = day + timedelta(days=6)
            expr = [c.intended_load * v for _, c, v in flat if day <= c.start_time.date() <= window_end]
            history_load = sum(
                int(item['load']) for item in world.gps.get('history', [])
                if day <= datetime.fromisoformat(item['date']).date() <= window_end
            )
            if expr:
                model.Add(sum(expr) + history_load <= self.load_adapter.config.max_rolling_7d_load)

        objective_terms = []
        for key, pairs in vars_by_key.items():
            for c, var in pairs:
                cost = c.preference_cost + self._churn_cost(c, parent_by_key)
                objective_terms.append(cost * var)
        model.Minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        # Bound request latency; a feasible solution is usable even without an optimality proof.
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            name = {
                cp_model.INFEASIBLE: 'INFEASIBLE',
                cp_model.MODEL_INVALID: 'MODEL_INVALID',
                cp_model.UNKNOWN: 'UNKNOWN',
            }.get(status, 'UNKNOWN')
            return OptimizerResult(status=name, conflicts=['CP_SAT_NO_FEASIBLE_PLAN'], backend='ortools_cp_sat')

        selected = []
        for _, pairs in vars_by_key.items():
            for c, var in pairs:
                if solver.Value(var):
                    selected.append(c)
        selected.sort(key=lambda c: c.start_time)
        return OptimizerResult(
            status='OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE',
            sessions=[SessionPlan(**c.model_dump(exclude={'preference_cost'})) for c in selected],
            objective_value=int(solver.ObjectiveValue()),
            backend='ortools_cp_sat',
        )
