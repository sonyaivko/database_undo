import sys 
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib as mpl

mpl.rcParams["font.family"] = "serif"

COLOR_FD = "#1D3557"       
COLOR_NAIVE = "#E63946"   
COLOR_LOG = "#2A9D8F"      
COLOR_UNDO = "#E76F51"  
COLOR_BASELINE = "#6C757D"   
COLOR_TREND = "#1D3557"
COLOR_LIKELY_REAL = "#1D3557"
COLOR_LIKELY_NOISE = "#A8B5C4"

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)
dataset = sys.argv[1]

sweep = pd.read_csv(f"local_fd_sweep_results_{dataset}.csv")
agg = sweep.groupby("batch_size").agg(
    discovery_time=("discovery_time", "mean"), log_time=("log_time", "mean"),
    undo_time=("undo_time", "mean"), naive_undo_time=("naive_undo_time", "mean"),
    plain_delete_time=("plain_delete_time", "mean"),
    fd_bytes=("fd_bytes", "mean"), naive_bytes=("naive_bytes", "mean"),
).reset_index()

agg["combined_log_time"] = agg.discovery_time + agg.log_time

rules = pd.read_csv(f"rule_bytes_saved_{dataset}.csv").sort_values("bytes_saved", ascending=False)

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

# Panel 1: storage, LINEAR scale
ax = axes[0, 0]
ax.plot(agg.batch_size, agg.fd_bytes, "o-", color=COLOR_FD, label="local FD-patch")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", color=COLOR_NAIVE, label="naive")
ax.set_xlabel("batch size"); ax.set_ylabel("storage (bytes)")
ax.set_title(f"Storage: local FD-patch vs naive {dataset}")
ax.legend(); ax.grid(alpha=0.3)

# Panel 2: runtime breakdown 
ax = axes[0, 1]
ax.plot(agg.batch_size, agg.combined_log_time * 1000, "o-", color=COLOR_LOG, label="log (discovery + per-row logging)")
ax.plot(agg.batch_size, agg.undo_time * 1000, "o-", color=COLOR_UNDO, label="undo")
ax.plot(agg.batch_size, agg.naive_undo_time * 1000, "s--", color=COLOR_NAIVE, alpha=0.7, label="naive undo ")
ax.plot(agg.batch_size, agg.plain_delete_time * 1000, "s:", color=COLOR_BASELINE,
         label="plain DELETE ")
ax.set_ylim(bottom=0)
ax.set_xlabel("batch size"); ax.set_ylabel("time (ms)")
ax.set_title("Runtime analysis")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# Panel 3: compression trend
ax = axes[1, 0]
ax.plot(agg.batch_size, agg.fd_bytes / agg.naive_bytes, "o-", color=COLOR_TREND)
ax.set_xscale("log")
ax.set_xlabel("batch size"); ax.set_ylabel("storage ratio ")
ax.set_title("Storage compression trend (FD-patch / naive)")
ax.grid(alpha=0.3)

# Panel 4: bytes saved per rule, ranked
ax = axes[1, 1]
bar_colors = [COLOR_LIKELY_REAL if r else COLOR_LIKELY_NOISE for r in rules["likely_real"]]

ax.bar(range(len(rules)), rules["bytes_saved"], color=bar_colors)
ax.set_xlabel("rule (ranked by bytes saved)"); ax.set_ylabel("bytes saved")
ax.set_title(f"Bytes saved per rule, ranked ({dataset})")
ax.set_xticks([])
legend_handles = [
    mpatches.Patch(color=COLOR_LIKELY_REAL, label="likely real"),
    mpatches.Patch(color=COLOR_LIKELY_NOISE, label="probable noise"),
]
ax.legend(handles=legend_handles, fontsize=9)
ax.grid(alpha=0.3, axis="y")
 
total_all = rules["bytes_saved"].sum()
total_real = rules.loc[rules["likely_real"], "bytes_saved"].sum()
gap = total_all - total_real
pct_real = 100 * total_real / total_all if total_all else 0
ax.text(0.98, 0.85,
        f"Total: {total_all:,} bytes\nLikely real: {total_real:,} ({pct_real:.0f}%)\n"
        f"Uncertain: {gap:,} ({100-pct_real:.0f}%)",
        transform=ax.transAxes, ha="right", va="top", fontsize=8,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="0.7"))
 
plt.tight_layout()
plt.savefig(f"local_fd_sweep_plot_{dataset}.png", dpi=150)
print(f"saved local_fd_sweep_plot_{dataset}.png")
 