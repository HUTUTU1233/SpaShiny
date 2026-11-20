"""Storage/API compatibility only; no changes to native scientific formulas."""
from contextlib import contextmanager
from threading import RLock

_LOCK = RLock()


@contextmanager
def pandas_legacy_api():
    """Restore removed pandas append/nonzero APIs for one native call.

    SpatialMETA 0.0.3.0 calls these pandas<2 APIs. concat reproduces append's
    semantics; patches are removed in finally. Nothing is written to vendor code.
    """
    import pandas as pd
    added_append = not hasattr(pd.DataFrame, "append")
    added_nonzero = not hasattr(pd.Series, "nonzero")
    with _LOCK:
        if added_append:
            def append(frame, other, ignore_index=False, verify_integrity=False, sort=False):
                if isinstance(other, dict):
                    other = pd.DataFrame([other])
                elif isinstance(other, pd.Series):
                    other = other.to_frame().T
                return pd.concat([frame, other], ignore_index=ignore_index,
                                 verify_integrity=verify_integrity, sort=sort)
            pd.DataFrame.append = append
        if added_nonzero:
            pd.Series.nonzero = lambda series: series.to_numpy().nonzero()
        try:
            yield
        finally:
            if added_append:
                delattr(pd.DataFrame, "append")
            if added_nonzero:
                delattr(pd.Series, "nonzero")
