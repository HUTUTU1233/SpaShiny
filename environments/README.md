# Separate runtimes

The Web, CPU, Control, Alignment, GPU and original-Python River runtimes are separate environments. The `.observed.txt` files record installed distribution names and versions.
They are inventories, not portable lock files. Do not concatenate them and run one `pip install -r`: CUDA/PyTorch/PyG native wheels, the frozen River Python 3.8 environment, and system dependencies must be reconstructed and tested separately.

Web/CPU/Control/Alignment/watchdog: Python 3.11.15.
GPU worker: Python 3.10.14. Original-Python River: Python 3.8.20.
SpatialMETA and other external packages are dependencies, not reimplemented or vendored wholesale.
