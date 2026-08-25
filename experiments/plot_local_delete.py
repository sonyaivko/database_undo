import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

mpl.rcParams["font.family"] = "Liberation Serif"

COLOR_FD = "#1D3557"       
COLOR_NAIVE = "#E63946"   
COLOR_LOG = "#2A9D8F"      
COLOR_UNDO = "#E76F51"     
COLOR_TREND = "#1D3557"
COLOR_LIKELY_REAL = "#1D3557"
COLOR_LIKELY_NOISE = "#A8B5C4"

sweep = pd.read_csv("local_fd_sweep_results.csv")
agg = sweep.groupby("batch_size").agg(
    discovery_time=("discovery_time", "mean"), log_time=("log_time", "mean"),
    undo_time=("undo_time", "mean"), naive_undo_time=("naive_undo_time", "mean"),
    fd_bytes=("fd_bytes", "mean"), naive_bytes=("naive_bytes", "mean"),
).reset_index()

agg["combined_log_time"] = agg.discovery_time + agg.log_time

rules = pd.read_csv("rule_bytes_saved.csv").sort_values("bytes_saved", ascending=True)

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

# Panel 1: storage, LINEAR scale
ax = axes[0, 0]
ax.plot(agg.batch_size, agg.fd_bytes, "o-", color=COLOR_FD, label="local FD-patch")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", color=COLOR_NAIVE, label="naive")
ax.set_xlabel("batch size"); ax.set_ylabel("storage (bytes)")
ax.set_title("Storage: local FD-patch vs naive")
ax.legend(); ax.grid(alpha=0.3)

# Panel 2: runtime breakdown 
ax = axes[0, 1]
ax.plot(agg.batch_size, agg.combined_log_time * 1000, "o-", color=COLOR_LOG, label="log")
ax.plot(agg.batch_size, agg.undo_time * 1000, "o-", color=COLOR_UNDO, label="undo")
ax.plot(agg.batch_size, agg.naive_undo_time * 1000, "s--", color=COLOR_NAIVE, alpha=0.6, label="naive undo ")
ax.set_xscale("log"); ax.set_yscale("log")
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
labels = [f"{t} <- {s}" for t, s in zip(rules["target_column"], rules["source_columns"])]
ax.barh(labels, rules["bytes_saved"], color=bar_colors)
ax.set_xlabel("bytes saved")
ax.set_title("Bytes saved per rule, ranked")
ax.tick_params(axis="y", labelsize=8)
ax.grid(alpha=0.3, axis="x")

plt.tight_layout()
plt.savefig("local_fd_sweep_plot.png", dpi=150)
print("saved local_fd_sweep_plot.png")