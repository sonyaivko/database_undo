import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
 
mpl.rcParams["font.family"] = "serif"
mpl.rcParams["font.size"] = 13
 
# graphs 1-3: forced single-split sweep
df = pd.read_csv("insert_sweep_results.csv")
df = df[df.correctness_ok]
agg = df.groupby("batch_size").agg(
    box_log_time=("box_log_time", "mean"), naive_log_time=("naive_log_time", "mean"),
    box_undo_time=("box_undo_time", "mean"), naive_undo_time=("naive_undo_time", "mean"),
    box_bytes=("box_bytes", "mean"), naive_bytes=("naive_bytes", "mean"),
    plain_insert_time=("plain_insert_time", "mean"),
).reset_index()
 
 
fig, axes = plt.subplots(2, 2, figsize=(15, 11))
 
# graph 1: storage, forced single split
ax = axes[0, 0]
ax.plot(agg.batch_size, agg.box_bytes, "o-", color="#1D3557", linewidth=2, markersize=8, label="box (1 split)")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", color="#E63946", linewidth=2, markersize=8, label="naive")
ax.set_xlabel("batch size", fontsize=15)
ax.set_ylabel("storage (bytes)", fontsize=15)
ax.set_title("Storage: bounding box vs naive", fontsize=16)
ax.legend(fontsize=12); ax.tick_params(labelsize=12)
ax.grid(alpha=0.3)
 
# graph 2: runtime, forced single split
ax = axes[0, 1]
ax.plot(agg.batch_size, agg.box_log_time * 1000, "o-", color="#2A9D8F", linewidth=2, markersize=8, label="box: log")
ax.plot(agg.batch_size, agg.box_undo_time * 1000, "o--", color="#2A9D8F", alpha=0.6, linewidth=2, markersize=8, label="box: undo")
ax.plot(agg.batch_size, agg.naive_log_time * 1000, "s-", color="#E76F51", linewidth=2, markersize=8, label="naive: log")
ax.plot(agg.batch_size, agg.naive_undo_time * 1000, "s--", color="#E76F51", alpha=0.6, linewidth=2, markersize=8, label="naive: undo")
ax.plot(agg.batch_size, agg.plain_insert_time * 1000, "^:", color="#6C757D", linewidth=2, markersize=8, label="plain INSERT")
ax.set_ylim(bottom=0)
ax.set_xlabel("batch size", fontsize=15)
ax.set_ylabel("time (ms)", fontsize=15)
ax.set_title("Runtime analysis", fontsize=16)
ax.legend(fontsize=11); ax.tick_params(labelsize=12)
ax.grid(alpha=0.3)
 
# Panel 3: visualization of the box structure itself -- illustrative,
# using clean/legible numbers (matching the earlier Scenario A test) rather
# than this sweep's actual numbers, which span millions of c_id units
# (necessary for correctness -- fresh territory must sit far from old
# data) and would render as two invisible dots with an empty gap between,
# not a useful diagram.
import matplotlib.patches as mpatches
 
ax = axes[1, 0]
OLD_COLOR = "#A8B5C4"
BOX_COLORS = ["#1D3557", "#E63946"]
 
old_range = (1, 300)
reclaimed = (50, 64)
fresh = (400, 414)
 
ax.plot([old_range[0], old_range[1]], [0, 0], color=OLD_COLOR, linewidth=8,
        solid_capstyle="butt", label="old data", zorder=1)
ax.plot([reclaimed[0], reclaimed[1]], [1, 1], color="black", linewidth=3,
        solid_capstyle="round", zorder=3, label="batch ")
ax.plot([fresh[0], fresh[1]], [1, 1], color="black", linewidth=3, solid_capstyle="round", zorder=3)
 
for i, (lo, hi) in enumerate([reclaimed, fresh]):
    rect = mpatches.Rectangle((lo, -0.4), hi - lo, 1.8, linewidth=1.5,
                                edgecolor=BOX_COLORS[i], facecolor=BOX_COLORS[i], alpha=0.15, zorder=2)
    ax.add_patch(rect)
    ax.text((lo + hi) / 2, 1.6, f"box {i}", ha="center", fontsize=11, color=BOX_COLORS[i])
 
ax.axvline(232, color="gray", linestyle=":", linewidth=1)
ax.text(232, -0.9, "split here\n", ha="center", fontsize=9, color="gray")
 
ax.set_ylim(-1.2, 2.2)
ax.set_yticks([])
ax.set_xlabel("c_id", fontsize=15)
ax.set_title("What a box looks like: 1 split", fontsize=16)
ax.legend(loc="upper right", fontsize=11)
ax.tick_params(labelsize=12)
ax.grid(alpha=0.2, axis="x")
 
# Panel 4: storage ratio vs LEAF SIZE directly 
leaf = pd.read_csv("leaf_size_sweep.csv")
leaf = leaf[leaf.n_boxes == 1]  
leaf["ratio"] = leaf.box_bytes / leaf.naive_bytes
BREAK_EVEN_SIZE = 27.5  # empirical crossing, interpolated from this exact data
 
ax = axes[1, 1]
ax.plot(leaf["size"], leaf.ratio, "o-", color="#1D3557", linewidth=2, markersize=8)
ax.axvline(BREAK_EVEN_SIZE, color="#E63946", linestyle=":", linewidth=1.5,
           label=f"~{BREAK_EVEN_SIZE:.0f} rows")
ax.set_ylim(0, leaf.ratio.max() * 1.1)
ax.set_xlabel("cluster size ", fontsize=15)
ax.set_ylabel("storage ratio (box / naive)", fontsize=15)
ax.set_title("Leaf size vs storage ratio", fontsize=16)
ax.legend(fontsize=11); ax.tick_params(labelsize=12)
ax.grid(alpha=0.3)
 
plt.tight_layout()
plt.savefig("insert_sweep_plot.png", dpi=150)
print("saved insert_sweep_plot.png")