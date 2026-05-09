"""
beta_utils.py — shared Beta-distribution helpers used by the eval harness.

Conformal calibration in production lives in the Go advisor; for paper-side
analysis we use the Beta-Bernoulli credible interval as an approximation.
The two coincide asymptotically; differences in finite samples are
explored in the paper appendix.
"""
from __future__ import annotations

import math
from typing import Tuple


def prior_pseudocounts(confidence_pct: float) -> Tuple[float, float]:
    """Map a confidence percentage from MOA-1b to (alpha, beta) pseudocounts.

    Implements the mapping in eq:prior-from-confidence of the paper:
        alpha = max(1, round(c / 5))
        beta  = max(1, round((100 - c) / 5))
    """
    c = max(0.0, min(100.0, float(confidence_pct)))
    alpha = max(1, round(c / 5))
    beta = max(1, round((100 - c) / 5))
    return float(alpha), float(beta)


def beta_credible_interval(n_success: int, n_failure: int,
                           alpha: float = 0.05) -> Tuple[float, float]:
    """Equal-tailed (1-alpha) credible interval for a Beta posterior with
    flat Beta(1,1) prior plus observed (n_success, n_failure).

    Pure-Python Newton-on-CDF; no SciPy dependency.
    """
    a = 1.0 + n_success
    b = 1.0 + n_failure
    return (
        _beta_quantile(alpha / 2.0, a, b),
        _beta_quantile(1.0 - alpha / 2.0, a, b),
    )


def _beta_pdf(x: float, a: float, b: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return 0.0
    log_pdf = (a - 1) * math.log(x) + (b - 1) * math.log(1 - x) \
        - _logbeta(a, b)
    return math.exp(log_pdf)


def _logbeta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _beta_cdf(x: float, a: float, b: float) -> float:
    """Regularised incomplete-Beta function via continued-fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        a * math.log(x) + b * math.log(1 - x) - _logbeta(a, b)
    )
    if x < (a + 1) / (a + b + 2):
        return bt * _beta_cf(x, a, b) / a
    return 1.0 - bt * _beta_cf(1 - x, b, a) / b


def _beta_cf(x: float, a: float, b: float, max_iter: int = 200,
             eps: float = 3e-7) -> float:
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            return h
    return h


def _beta_quantile(p: float, a: float, b: float,
                   tol: float = 1e-7, max_iter: int = 100) -> float:
    """Bisection on the regularised-incomplete-Beta CDF."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        c = _beta_cdf(mid, a, b)
        if abs(c - p) < tol:
            return mid
        if c < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
