import sys 
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib as mpl

mpl.rcParams["font.family"] = "serif"

# size up for poster 
mpl.rcParams["font.size"] = 13
TITLE_SIZE = 17
LABEL_SIZE = 15
LEGEND_SIZE = 13
TICK_SIZE = 12
ANNOTATION_SIZE = 12

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

fig, axes = plt.subplots(2, 2, figsize=(15, 11))

# Panel 1: storage,
ax = axes[0, 0]
ax.plot(agg.batch_size, agg.fd_bytes, "o-", color=COLOR_FD, linewidth=2, markersize=8, label="local FD-patch")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", color=COLOR_NAIVE, linewidth=2, markersize=8, label="naive")
ax.set_xlabel("batch size", fontsize=LABEL_SIZE); ax.set_ylabel("storage (bytes)", fontsize=LABEL_SIZE)
ax.set_title(f"Storage: local FD-patch vs naive {dataset}", fontsize=TITLE_SIZE)
ax.legend(fontsize=LEGEND_SIZE)
ax.tick_params(labelsize=TICK_SIZE)
ax.grid(alpha=0.3)


# Panel 2: runtime breakdown 
ax = axes[0, 1]
ax.plot(agg.batch_size, agg.combined_log_time * 1000, "o-", color=COLOR_LOG, linewidth=2, markersize=8, label="log")
ax.plot(agg.batch_size, agg.undo_time * 1000, "o-", color=COLOR_UNDO, linewidth=2, markersize=8, label="undo")
ax.plot(agg.batch_size, agg.naive_undo_time * 1000, "s--", color=COLOR_NAIVE, linewidth=2, markersize=8, alpha=0.7, label="naive undo ")
ax.plot(agg.batch_size, agg.plain_delete_time * 1000, "s:", color=COLOR_BASELINE, linewidth=2, markersize=8, 
         label="plain DELETE ")
ax.set_ylim(bottom=0)
ax.set_xlabel("batch size", fontsize=LABEL_SIZE); ax.set_ylabel("time (ms)", fontsize=LABEL_SIZE)
ax.set_title("Runtime analysis", fontsize=TITLE_SIZE)
ax.legend(fontsize=LEGEND_SIZE)
ax.tick_params(labelsize=TICK_SIZE)
ax.grid(alpha=0.3)


# Panel 3: compression trend
ax = axes[1, 0]
ax.plot(agg.batch_size, agg.fd_bytes / agg.naive_bytes, "o-", color=COLOR_TREND, linewidth=2, markersize=8)
ax.set_xscale("log")
ax.set_xlabel("batch size", fontsize=LABEL_SIZE); ax.set_ylabel("storage ratio", fontsize=LABEL_SIZE)
ax.set_title("Storage compression trend (FD-patch / naive)", fontsize=TITLE_SIZE)
ax.tick_params(labelsize=TICK_SIZE)
ax.grid(alpha=0.3)

# Panel 4: bytes saved per rule, ranked
ax = axes[1, 1]
bar_colors = [COLOR_LIKELY_REAL if r else COLOR_LIKELY_NOISE for r in rules["likely_real"]]

ax.bar(range(len(rules)), rules["bytes_saved"], color=bar_colors)
ax.set_xlabel("rule", fontsize=LABEL_SIZE); ax.set_ylabel("bytes saved", fontsize=LABEL_SIZE)
ax.set_title(f"Bytes saved per rule, ranked ({dataset})", fontsize=TITLE_SIZE)
ax.set_xticks([])
ax.tick_params(axis="y", labelsize=TICK_SIZE)

legend_handles = [
    mpatches.Patch(color=COLOR_LIKELY_REAL, label="likely real"),
    mpatches.Patch(color=COLOR_LIKELY_NOISE, label="probable noise"),
]
ax.legend(handles=legend_handles, fontsize=LEGEND_SIZE)
ax.grid(alpha=0.3, axis="y")
 
total_all = rules["bytes_saved"].sum()
total_real = rules.loc[rules["likely_real"], "bytes_saved"].sum()
gap = total_all - total_real
pct_real = 100 * total_real / total_all if total_all else 0
ax.text(0.98, 0.85,
        f"Total: {total_all:,} ",
        transform=ax.transAxes, ha="right", va="top", fontsize=ANNOTATION_SIZE,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="0.7"))
 
plt.tight_layout()
plt.savefig(f"local_fd_sweep_plot_{dataset}.png", dpi=150)
print(f"saved local_fd_sweep_plot_{dataset}.png")
 