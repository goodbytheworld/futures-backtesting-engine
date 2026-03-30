"""
Walk-forward validation report models and formatting helpers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional

import numpy as np


def estimated_dsr(
    sharpe: float,
    n_trials: int,
    trial_std: float,
) -> float:
    """Estimates a DSR-style probability that performance exceeds noise."""
    if n_trials < 2 or trial_std <= 1e-6:
        return 0.5

    expected_max_sr = trial_std * math.sqrt(2 * math.log(n_trials))
    if expected_max_sr == 0:
        return 0.0

    z_score = (sharpe - expected_max_sr) / trial_std
    return 0.5 * (1 + math.erf(z_score / math.sqrt(2)))


@dataclass
class FoldResult:
    """Results from a single walk-forward fold."""

    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: Dict[str, Any]
    is_score: float
    oos_score: float
    n_trials: int
    trial_std: float
    oos_stats: Dict[str, Any]
    is_stats: Dict[str, Any] = field(default_factory=dict)
    oos_rejection_reason: Optional[str] = None
    oos_min_trades_required: int = 0

    @property
    def degradation(self) -> float:
        """Returns relative performance decay from IS to OOS."""
        if self.is_score <= 0.0:
            return -1.0
        return (self.oos_score - self.is_score) / self.is_score

    @property
    def dsr_probability(self) -> float:
        """Returns the fold-level DSR-style confidence estimate."""
        return estimated_dsr(self.is_score, self.n_trials, self.trial_std)

    @property
    def is_failed(self) -> bool:
        """Returns whether the fold failed in-sample quality gates."""
        return self.is_score <= 0.0

    @property
    def is_win_rate(self) -> float:
        """Returns the in-sample win rate when present."""
        return float(self.is_stats.get("win_rate", 0.0))

    @property
    def oos_win_rate(self) -> float:
        """Returns the out-of-sample win rate when present."""
        return float(self.oos_stats.get("win_rate", 0.0))

    @property
    def win_rate_degradation(self) -> float:
        """Returns relative win-rate drift from IS to OOS."""
        if self.is_failed or self.is_win_rate <= 0.0:
            return 0.0
        return (self.oos_win_rate - self.is_win_rate) / self.is_win_rate

    @property
    def oos_expected_value(self) -> float:
        """Returns a simple OOS expected-value proxy per trade."""
        if self.is_failed:
            return 0.0
        win_rate = self.oos_win_rate
        avg_win = float(self.oos_stats.get("avg_win", 0.0))
        avg_loss_abs = abs(float(self.oos_stats.get("avg_loss", 0.0)))
        return win_rate * avg_win - (1 - win_rate) * avg_loss_abs


@dataclass
class WFVReport:
    """Aggregated walk-forward results with skeptic-style robustness checks."""

    symbol: str
    strategy_name: str
    n_folds: int
    fold_results: List[FoldResult]
    median_oos_score: float = 0.0
    median_degradation: float = 0.0
    avg_dsr: float = 0.0
    candidate_params: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "FAIL"
    warnings: List[str] = field(default_factory=list)
    pass_min_profitable_folds: int = 3
    warn_min_profitable_folds: int = 2
    pass_min_consecutive_profitable_folds: int = 2
    warn_min_consecutive_profitable_folds: int = 1
    min_sharpe_per_fold: float = 0.0
    total_wfo_time_sec: float = 0.0
    avg_fold_time_sec: float = 0.0
    avg_trial_time_sec: float = 0.0

    def compute(self) -> None:
        """Computes aggregate statistics, warnings, and candidate parameters."""
        if not self.fold_results:
            return

        self.median_oos_score = float(np.median([f.oos_score for f in self.fold_results]))
        self.median_degradation = float(np.median([f.degradation for f in self.fold_results]))
        self.avg_dsr = float(np.mean([f.dsr_probability for f in self.fold_results]))
        self._analyze_robustness()
        self._select_candidate_params()

    def _analyze_robustness(self) -> None:
        """Applies the report verdict rules and populates warnings."""
        profitable_folds = self._count_quality_profitable_folds(self.min_sharpe_per_fold)
        consecutive_profitable = self._max_consecutive_quality_profitable_folds(
            self.min_sharpe_per_fold
        )

        if self.median_degradation < -0.50:
            self.warnings.append(
                f"Severe Overfitting: Median decay is {self.median_degradation:.0%}"
            )
        if self.avg_dsr < 0.5:
            self.warnings.append(
                f"Low Significance: DSR {self.avg_dsr:.2f} implies results "
                "indistinguishable from noise."
            )

        win_rate_degradations = [
            fold.win_rate_degradation
            for fold in self.fold_results
            if not fold.is_failed and fold.is_win_rate > 0.0
        ]
        if win_rate_degradations:
            median_wr_degradation = float(np.median(win_rate_degradations))
            if median_wr_degradation < -0.20:
                self.warnings.append(
                    f"WinRate Drift RED: median IS->OOS degradation {median_wr_degradation:+.1%}"
                )
            elif median_wr_degradation < -0.10:
                self.warnings.append(
                    f"WinRate Drift YELLOW: median IS->OOS degradation {median_wr_degradation:+.1%}"
                )

            oos_wr_std = float(
                np.std([fold.oos_win_rate for fold in self.fold_results if not fold.is_failed])
            )
            if oos_wr_std > 0.10:
                self.warnings.append(
                    f"Unstable OOS WinRate: fold std is {oos_wr_std:.1%} (possible regime/overfit mix)."
                )

        negative_ev_folds = sum(
            1
            for fold in self.fold_results
            if not fold.is_failed and fold.oos_expected_value < 0.0
        )
        if negative_ev_folds > 0:
            self.warnings.append(
                f"Negative OOS EV in {negative_ev_folds}/{len(self.fold_results)} folds."
            )

        low_sample_rejections = [
            fold
            for fold in self.fold_results
            if fold.oos_rejection_reason
            and "Insufficient OOS trades" in fold.oos_rejection_reason
        ]
        if low_sample_rejections:
            self.warnings.append(
                "Low OOS sample size in "
                f"{len(low_sample_rejections)}/{len(self.fold_results)} folds "
                "(score rejected by trade-count gate)."
            )

        if (
            profitable_folds >= self.pass_min_profitable_folds
            and consecutive_profitable >= self.pass_min_consecutive_profitable_folds
            and self.median_degradation > -0.40
            and self.avg_dsr > 0.6
        ):
            self.verdict = "PASS"
        elif (
            profitable_folds >= self.warn_min_profitable_folds
            and consecutive_profitable >= self.warn_min_consecutive_profitable_folds
            and self.median_degradation > -0.60
        ):
            self.verdict = "WARNING"
        else:
            self.verdict = "FAIL"

    def _count_quality_profitable_folds(self, min_sharpe: float) -> int:
        """Counts positive OOS folds that satisfy the minimum Sharpe gate."""
        return sum(
            1
            for fold in self.fold_results
            if fold.oos_score > 0.0
            and float(fold.oos_stats.get("sharpe_ratio", 0.0)) >= min_sharpe
        )

    def _max_consecutive_quality_profitable_folds(self, min_sharpe: float) -> int:
        """Returns the longest streak of profitable, quality-qualified folds."""
        max_streak = 0
        current_streak = 0
        for fold in self.fold_results:
            is_quality_profitable = (
                fold.oos_score > 0.0
                and float(fold.oos_stats.get("sharpe_ratio", 0.0)) >= min_sharpe
            )
            if is_quality_profitable:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak

    def _select_candidate_params(self) -> None:
        """Builds a consensus parameter candidate from robust folds only."""
        robust_folds = [fold for fold in self.fold_results if fold.oos_score > 0]
        if not robust_folds:
            return

        first_params = robust_folds[0].best_params
        consensus: Dict[str, Any] = {}
        for key, sample_value in first_params.items():
            all_values = [
                fold.best_params.get(key)
                for fold in robust_folds
                if fold.best_params.get(key) is not None
            ]
            if not all_values:
                continue
            if isinstance(sample_value, (int, float)) and not isinstance(sample_value, bool):
                median_value = np.median(all_values)
                consensus[key] = (
                    int(round(median_value))
                    if isinstance(sample_value, int)
                    else float(median_value)
                )
            else:
                consensus[key] = Counter(all_values).most_common(1)[0][0]
        self.candidate_params = consensus


def format_human_report(report: WFVReport) -> str:
    """Formats the analyst-facing terminal report for walk-forward results."""

    def bar(score: float, max_score: float = 2.0, width: int = 10) -> str:
        if score < 0:
            return "FAIL".ljust(width)
        normalized = min(1.0, score / max_score)
        filled = int(normalized * width)
        return ("#" * filled + "." * (width - filled)).ljust(width)

    def column(text: object, width: int = 10, align: str = "<") -> str:
        return f"{str(text):{align}{width}}"

    lines: List[str] = []
    lines.append(f"\n\n{'=' * 80}")
    lines.append(f" WFV AUDIT REPORT: {report.strategy_name} @ {report.symbol}")
    lines.append(f"{'=' * 80}")
    lines.append("\n[EXECUTIVE SUMMARY]")
    lines.append(f"  Verdict:        {report.verdict}")
    lines.append(f"  Median OOS:     {report.median_oos_score:.4f} (Composite Score)")
    lines.append(f"  Perf Decay:     {report.median_degradation:+.1%} (IS -> OOS)")
    lines.append(
        f"  Skeptic Confidence (DSR): {report.avg_dsr:.0%} (Prob. Skill > Noise)"
    )
    lines.append("\n[COMPUTATIONAL PROFILE]")
    lines.append(f"  Total WFO Runtime: {report.total_wfo_time_sec / 60:.1f} mins")
    lines.append(f"  Average Fold Time: {report.avg_fold_time_sec:.1f} secs")
    lines.append(f"  Average Trial Time: {report.avg_trial_time_sec:.3f} secs")

    if report.warnings:
        lines.append("\n[RISK FLAGS]")
        for warning in report.warnings:
            lines.append(f"  ! {warning}")

    header = (
        f"{column('Fold', 4)} | "
        f"{column('Period', 22)} | "
        f"{column('IS Score', 8)} | "
        f"{column('OOS Score', 9)} | "
        f"{column('Decay', 7)} | "
        f"{column('WR IS', 6)} | "
        f"{column('WR OOS', 7)} | "
        f"{column('WR d', 7)} | "
        f"{column('Visual', 12)} | "
        f"{column('DD%', 6)}"
    )
    lines.append("\n[FOLD ANALYSIS]")
    lines.append(header)
    lines.append("-" * len(header))

    for fold in report.fold_results:
        decay_str = "CRASH" if fold.degradation < -0.5 else f"{fold.degradation:+.0%}"
        drawdown_str = f"{fold.oos_stats.get('max_drawdown', 0):.1f}"
        if fold.is_failed:
            is_wr, oos_wr, wr_delta = "n/a", "n/a", "n/a"
        else:
            is_wr = f"{fold.is_win_rate:.0%}"
            oos_wr = f"{fold.oos_win_rate:.0%}"
            wr_delta = f"{fold.win_rate_degradation:+.0%}"
        lines.append(
            f"{column(fold.fold_id, 4)} | "
            f"{column(f'{fold.test_start}..', 22)} | "
            f"{column(f'{fold.is_score:.2f}', 8)} | "
            f"{column(f'{fold.oos_score:.2f}', 9)} | "
            f"{column(decay_str, 7)} | "
            f"{column(is_wr, 6)} | "
            f"{column(oos_wr, 7)} | "
            f"{column(wr_delta, 7)} | "
            f"{column(bar(fold.oos_score, 1.5), 12)} | "
            f"{column(drawdown_str, 6)}"
        )

    rejection_details = [
        fold
        for fold in report.fold_results
        if fold.oos_rejection_reason and not fold.is_failed
    ]
    if rejection_details:
        lines.append("\n[REJECTION DIAGNOSTICS]")
        for fold in rejection_details:
            lines.append(f"  Fold {fold.fold_id}: {fold.oos_rejection_reason}")

    if report.candidate_params:
        lines.append("\n[CANDIDATE PARAMETERS]")
        lines.append(f"  {report.candidate_params}")
    else:
        lines.append("\n[NO CANDIDATE PARAMETERS] Strategy failed stability checks.")

    lines.append(f"{'=' * 80}\n")
    return "\n".join(lines)
