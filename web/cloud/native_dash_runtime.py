"""Process-local, owner/analysis-scoped hosting of SpatialMETA's native Dash UI.

No database schema, analysis algorithm or SpatialMETA source is changed here.
Only immutable component bundles are exempt from the per-viewer data capability.
"""
from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field


_lock = threading.RLock()
_constructor_lock = threading.Lock()
_viewers: dict[str, "NativeViewer"] = {}
_logger = logging.getLogger(__name__)


@dataclass
class NativeViewer:
    viewer_id: str
    owner_id: str
    analysis_id: str
    scope_id: str
    port: int
    feature: str
    html: str = field(repr=False)
    capability: str = field(repr=False)
    server: object = field(repr=False)
    thread: threading.Thread = field(repr=False)
    wrapper: object = field(repr=False)

    @property
    def prefix(self):
        return f"/native-dash/{self.viewer_id}/"


def get_viewer(viewer_id):
    with _lock:
        return _viewers.get(str(viewer_id))


def authorized(viewer, owner_id, analysis_id, capability):
    return bool(
        viewer and owner_id and analysis_id and capability
        and viewer.owner_id == owner_id and viewer.analysis_id == analysis_id
        and hmac.compare_digest(viewer.capability, str(capability))
    )


def is_component_asset(path, method):
    """These installed JS bundles contain no layout, expression or user state."""
    return bool(
        method in {"GET", "HEAD"}
        and path.startswith("_dash-component-suites/")
        and ".." not in path and "\\" not in path
    )


def close_scope(scope_id):
    with _lock:
        targets = [v for v in _viewers.values() if v.scope_id == scope_id]
        for v in targets:
            _viewers.pop(v.viewer_id, None)
    for v in targets:
        v.server.shutdown()
        v.server.server_close()
        v.thread.join(timeout=2)


def close_viewer(viewer_id):
    with _lock:
        viewer = _viewers.pop(str(viewer_id), None)
    if viewer:
        viewer.server.shutdown()
        viewer.server.server_close()
        viewer.thread.join(timeout=2)


def _nodes(value):
    if isinstance(value, (list, tuple)):
        for child in value:
            yield from _nodes(child)
    elif hasattr(value, "to_plotly_json"):
        yield value
        yield from _nodes(getattr(value, "children", None))


def repair_native_layout(app):
    """Compatibility only: two native loading-wrapper Divs share an unused ID."""
    nodes = list(_nodes(app.layout))
    ids = [getattr(n, "id", None) for n in nodes]
    duplicates = {k: n for k, n in Counter(x for x in ids if isinstance(x, str)).items() if n > 1}
    if duplicates and duplicates != {"transparent-loader-wrapper-2": 2}:
        raise RuntimeError("Unexpected duplicate IDs in native SpatialMETA Dash layout.")
    if duplicates:
        # This Div ID is not referenced by any native callback. Never rename
        # graph/control IDs, which are the original callback contract.
        callbacks = json.dumps(app.callback_map, default=str)
        if "transparent-loader-wrapper-2" in callbacks:
            raise RuntimeError("Native callback references the duplicate wrapper ID.")
        matches = [n for n in nodes if getattr(n, "id", None) == "transparent-loader-wrapper-2"]
        matches[1].id = "spashiny-native-trajectory-loader-wrapper"


def _bridge(prefix, analysis_id, capability):
    # HTML is delivered over this Shiny session, never in a URL or access log.
    # Native Dash's fetches carry both explicit tab scope and an independent
    # random per-viewer capability. No global analysis cookie is trusted.
    values = json.dumps([prefix, analysis_id, capability]).replace("<", "\\u003c")
    return """<script>(function(){
      'use strict'; const cfg=VALUES, original=window.fetch;
      const origin=new URL(document.baseURI).origin;
      window.fetch=function(input,options){
        const address=typeof input==='string'?input:input.url;
        const url=new URL(address,document.baseURI);
        if(url.origin===origin&&url.pathname.startsWith(cfg[0])){
          options=Object.assign({},options||{});
          const headers=new Headers(options.headers||(input&&input.headers)||{});
          headers.set('X-SpaShiny-Analysis-Session',cfg[1]);
          headers.set('X-SpaShiny-Dash-Capability',cfg[2]);
          options.headers=headers; options.credentials='same-origin';
        }
        return original.call(this,input,options);
      };
    })();</script>""".replace("VALUES", values)


def start_viewer(adata, feature, owner_id, analysis_id, scope_id, closed):
    """Called in a background thread, not while holding Shiny's reactive lock."""
    import dash
    import numpy as np
    import spatialmeta as smt
    from scipy import sparse
    from werkzeug.serving import WSGIRequestHandler, make_server

    if not owner_id or not analysis_id or closed.is_set():
        raise ValueError("An active owner and analysis are required for SpatialMETA Dash.")
    if feature not in adata.var_names or not adata.var_names.is_unique:
        raise ValueError("Choose a uniquely named feature from this analysis input.")
    if "normalized" not in adata.layers:
        raise ValueError("SpatialMETA Dash requires the input's existing layers['normalized']; no data was normalized or fabricated.")
    values = adata.layers["normalized"][:, list(adata.var_names).index(feature)]
    values = values.toarray().ravel() if sparse.issparse(values) else np.asarray(values).ravel()
    if not np.isfinite(values).all() or values.size < 2 or np.ptp(values) == 0:
        raise ValueError(f"Feature '{feature}' has constant or invalid values. Choose another feature for native Dash's expression distribution.")

    viewer_id = uuid.uuid4().hex
    prefix = f"/native-dash/{viewer_id}/"
    capability = secrets.token_urlsafe(32)
    # Native initialization adds scaled image metadata. Isolate that change
    # from the user's original loaded/Marker/correlation object.
    wrapper = smt.pl.Wrapper(adata.copy())
    original_dash = dash.Dash

    class PrefixedDash(original_dash):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("requests_pathname_prefix", prefix)
            kwargs.setdefault("routes_pathname_prefix", prefix)
            super().__init__(*args, **kwargs)

    with _constructor_lock:
        dash.Dash = PrefixedDash
        try:
            app = wrapper.to_plotly(init_feature=feature)
        finally:
            dash.Dash = original_dash
    repair_native_layout(app)
    app.index_string = app.index_string.replace("{%metas%}", "{%metas%}" + _bridge(prefix, analysis_id, capability))
    client = app.server.test_client()
    response = client.get(prefix)
    if response.status_code != 200:
        raise RuntimeError(f"Native SpatialMETA Dash startup returned HTTP {response.status_code}.")
    if client.get(prefix + "_dash-dependencies").status_code != 200:
        raise RuntimeError("Native SpatialMETA Dash callbacks did not initialize.")
    html = response.get_data(as_text=True)

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass

    # Bind atomically to an OS-assigned loopback port, never probe-and-release
    # 8050 or expose this listener outside the existing Web namespace.
    server = make_server("127.0.0.1", 0, app.server, threaded=True, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, name="spashiny-native-dash", daemon=True)
    thread.start()
    viewer = NativeViewer(viewer_id, owner_id, analysis_id, scope_id, server.server_port,
                          feature, html, capability, server, thread, wrapper)
    try:
        if closed.is_set():
            raise RuntimeError("The analysis page closed while native Dash was starting.")
        close_scope(scope_id)
        with _lock:
            if closed.is_set():
                raise RuntimeError("The analysis page closed while native Dash was starting.")
            _viewers[viewer_id] = viewer
    except BaseException:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        raise
    _logger.info("SPASHINY_NATIVE_DASH_READY analysis=%s viewer=%s callbacks=%d", analysis_id, viewer_id, len(app.callback_map))
    return {"html": html, "viewer_id": viewer_id, "feature": feature, "analysis_id": analysis_id,
            "data_id": id(adata)}
