import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("delete_sweep_results.csv")
agg = df.groupby("batch_size").agg(
    fd_log_time=("fd_log_time", "mean"), fd_undo_time=("fd_undo_time", "mean"),
    fd_bytes=("fd_bytes", "mean"),
    naive_log_time=("naive_log_time", "mean"), naive_undo_time=("naive_undo_time", "mean"),
    naive_bytes=("naive_bytes", "mean"),
).reset_index()

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

ax = axes[0, 0]
ax.plot(agg.batch_size, agg.fd_bytes, "o-", label="FD-patch")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", label="naive (full row image)")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows deleted)"); ax.set_ylabel("log storage (bytes)")
ax.set_title("Storage: FD-patch vs naive")
ax.legend(); ax.grid(alpha=0.3)

ax = axes[0, 1]
ax.plot(agg.batch_size, agg.fd_log_time, "o-", color="C0", label="FD-patch: log")
ax.plot(agg.batch_size, agg.fd_undo_time, "o--", color="C0", alpha=0.6, label="FD-patch: undo")
ax.plot(agg.batch_size, agg.naive_log_time, "s-", color="C1", label="naive: log")
ax.plot(agg.batch_size, agg.naive_undo_time, "s--", color="C1", alpha=0.6, label="naive: undo")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows deleted)"); ax.set_ylabel("time (s)")
ax.set_title("Runtime: FD-patch vs naive (log + undo)")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

ax = axes[1, 0]
ax.plot(agg.batch_size, agg.fd_bytes / agg.naive_bytes, "o-", color="darkgreen", label="storage ratio")
ax.plot(agg.batch_size, agg.fd_log_time / agg.naive_log_time, "^-", color="darkred", label="log time ratio")
ax.plot(agg.batch_size, agg.fd_undo_time / agg.naive_undo_time, "v-", color="purple", label="undo time ratio")
ax.axhline(1.0, color="gray", linestyle="--", linewidth=1, label="break-even")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows deleted)"); ax.set_ylabel("ratio (FD-patch / naive)")
ax.set_title("Relative cost")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# The key diagnostic panel: per-row cost, log vs undo. Flat = healthy scaling,
# climbing = a real algorithmic problem (the exclude_pks NOT-IN clause growing
# with batch size), not just "more rows take more time."
ax = axes[1, 1]
ax.plot(agg.batch_size, agg.fd_log_time / agg.batch_size * 1000, "o-", color="darkred",
         label="log: ms/row ")
ax.plot(agg.batch_size, agg.fd_undo_time / agg.batch_size * 1000, "v-", color="purple",
         label="undo: ms/row ")
ax.set_xscale("log")
ax.set_xlabel("batch size (rows deleted)"); ax.set_ylabel("per-row cost (ms)")
ax.set_title("Per-row cost")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("delete_sweep_plot.png", dpi=150)
print("saved delete_sweep_plot.png")