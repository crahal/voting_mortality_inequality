"""Run every notebook cell using this Python environment, then check result hashes."""

import sys
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

import verify_results

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "src/analysis.ipynb"
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]

    def progress(cell, cell_index, **kwargs):
        if cell.cell_type == "code":
            print(f"Executing cell {cell_index + 1}/{len(notebook.cells)}: {cell.id}", flush=True)

    try:
        NotebookClient(
            notebook, km=manager, timeout=1200, allow_errors=False,
            resources={"metadata": {"path": str(path.parent)}}, on_cell_start=progress,
        ).execute()
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    verify_results.main([])
    verify_results.verify_exported_robustness()
    nbformat.write(notebook, path)
    print("PASS: every notebook cell executed and correlation/p-value/N hashes match.")


if __name__ == "__main__":
    main()
