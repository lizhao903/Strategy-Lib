"""因子可视化：在 notebook 里直接调用。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd


def plot_ic_timeseries(ic: pd.Series, title: str = "IC", ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(12, 4))
    ax.bar(ic.index, ic.values, width=1.0, color="steelblue", alpha=0.6)
    ax.plot(ic.index, ic.rolling(60).mean(), color="crimson", lw=1.5, label="60d MA")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title(f"{title}  mean={ic.mean():.4f}  ICIR={ic.mean() / ic.std():.2f}")
    ax.legend()
    return ax


def plot_ic_decay(decay_df: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    ax.plot(decay_df.index, decay_df["ic_mean"], "o-", label="IC")
    ax.plot(decay_df.index, decay_df["rank_ic_mean"], "s--", label="Rank IC")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("Forward period")
    ax.set_ylabel("Mean IC")
    ax.set_title("IC Decay")
    ax.legend()
    return ax


def plot_quantile_cumret(cum: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(12, 5))
    for col in cum.columns:
        if col == "LongShort":
            ax.plot(cum.index, cum[col], lw=2, color="black", label=col)
        else:
            ax.plot(cum.index, cum[col], lw=1, label=col)
    ax.set_yscale("log")
    ax.set_title("Quantile Cumulative Returns")
    ax.legend()
    return ax
