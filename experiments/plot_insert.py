import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("insert_sweep_results.csv")
agg = df.groupby("batch_size").agg(
    box_bytes=("box_bytes", "mean"), naive_bytes=("naive_bytes", "mean"),
    box_log_time=("box_log_time", "mean"), naive_log_time=("naive_log_time", "mean"),
    box_undo_time=("box_undo_time", "mean"), naive_undo_time=("naive_undo_time", "mean"),
    actual_data_bytes=("actual_data_bytes", "mean"),
).reset_index()

fig, axes = plt.subplots(2, 2, figsize=(13, 10))

# graph 1: absolute storage, both methods
ax = axes[0, 0]
ax.plot(agg.batch_size, agg.box_bytes, "o-", label="box-based (logInsertion)")
ax.plot(agg.batch_size, agg.naive_bytes, "s-", label="naive (PK list)")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows)"); ax.set_ylabel("log storage (bytes)")
ax.set_title("Storage overhead: box vs naive")
ax.legend(); ax.grid(alpha=0.3)

# graph 2: absolute time, both methods, for logging and undoing
ax = axes[0, 1]
ax.plot(agg.batch_size, agg.box_log_time * 1000, "o-", color="C0", label="box: log")
ax.plot(agg.batch_size, agg.box_undo_time * 1000, "o--", color="C0", alpha=0.6, label="box: undo")
ax.plot(agg.batch_size, agg.naive_log_time * 1000, "s-", color="C1", label="naive: log")
ax.plot(agg.batch_size, agg.naive_undo_time * 1000, "s--", color="C1", alpha=0.6, label="naive: undo")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows)"); ax.set_ylabel("time (ms)")
ax.set_title("Runtime overhead: box vs naive (log + undo)")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# graph 3: relative ratio, storage and both time measures
ax = axes[1, 0]
ax.plot(agg.batch_size, agg.box_bytes / agg.naive_bytes, "o-", color="darkgreen",
         label="storage ratio (box/naive)")
ax.plot(agg.batch_size, agg.box_log_time / agg.naive_log_time, "^-", color="darkred",
         label="log time ratio (box/naive)")
ax.plot(agg.batch_size, agg.box_undo_time / agg.naive_undo_time, "v-", color="purple",
         label="undo time ratio (box/naive)")
ax.axhline(1.0, color="gray", linestyle="--", linewidth=1, label="break-even")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows)"); ax.set_ylabel("ratio (box / naive)")
ax.set_title("Relative cost: below 1.0 = box wins, above = naive wins")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

# graph 4: overhead  
ax = axes[1, 1]
ax.plot(agg.batch_size, 100 * agg.box_bytes / agg.actual_data_bytes, "o-",
         label="box overhead (% of real data)")
ax.plot(agg.batch_size, 100 * agg.naive_bytes / agg.actual_data_bytes, "s-",
         label="naive overhead (% of real data)")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("batch size (rows)"); ax.set_ylabel("log size as % of actual row data")
ax.set_title("Overhead relative to the real inserted data")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("insert_sweep_plot.png", dpi=150)
print("saved insert_sweep_plot.png")