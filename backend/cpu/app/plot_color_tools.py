from __future__ import annotations

import re
from copy import deepcopy
import pickle

from shiny import ui


COLOR_PRESETS = {
    "default": {
        "label": "SpaShiny teal-orange",
        "primary": "#157B9B",
        "secondary": "#7799CC",
        "accent": "#FF7F0E",
        "low": "#157B9B",
        "mid": "#FFFFFF",
        "high": "#FF7F0E",
    },
    "ocean": {
        "label": "Ocean teal",
        "primary": "#0E7490",
        "secondary": "#14B8A6",
        "accent": "#F59E0B",
        "low": "#083344",
        "mid": "#ECFEFF",
        "high": "#14B8A6",
    },
    "berry": {
        "label": "Berry rose",
        "primary": "#9F1239",
        "secondary": "#DB2777",
        "accent": "#F97316",
        "low": "#4C0519",
        "mid": "#FFF1F2",
        "high": "#E11D48",
    },
    "forest": {
        "label": "Forest green",
        "primary": "#166534",
        "secondary": "#65A30D",
        "accent": "#CA8A04",
        "low": "#14532D",
        "mid": "#F7FEE7",
        "high": "#84CC16",
    },
    "mono": {
        "label": "Clean monochrome",
        "primary": "#111827",
        "secondary": "#64748B",
        "accent": "#94A3B8",
        "low": "#111827",
        "mid": "#F8FAFC",
        "high": "#64748B",
    },
}

FIXED_COLORS = {
    "": "Custom / picker",
    "#157B9B": "SpaShiny teal",
    "#7799CC": "Soft blue",
    "#FF7F0E": "Orange",
    "#E11D48": "Rose",
    "#7C3AED": "Violet",
    "#059669": "Green",
    "#111827": "Graphite",
}


def default_color_settings() -> dict:
    return deepcopy(COLOR_PRESETS["default"])


def normalize_color(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        text = "#" + text
    rgb_match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", text)
    comma_match = re.fullmatch(r"\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*", text)
    match = rgb_match or comma_match
    if match:
        values = [max(0, min(255, int(part))) for part in match.groups()]
        text = "#{:02X}{:02X}{:02X}".format(*values)
    try:
        from matplotlib.colors import is_color_like, to_hex

        if is_color_like(text):
            return to_hex(text).upper()
    except Exception:
        pass
    return fallback


def make_color_settings(primary=None, secondary=None, accent=None, low=None, mid=None, high=None) -> dict:
    base = default_color_settings()
    return {
        "label": "Custom",
        "primary": normalize_color(primary, base["primary"]),
        "secondary": normalize_color(secondary, base["secondary"]),
        "accent": normalize_color(accent, base["accent"]),
        "low": normalize_color(low, base["low"]),
        "mid": normalize_color(mid, base["mid"]),
        "high": normalize_color(high, base["high"]),
    }


def _as_visible_hex_values(value):
    try:
        import numpy as np
        from matplotlib.colors import to_hex, to_rgba
    except Exception:
        return []

    if value is None:
        return []

    if isinstance(value, str):
        try:
            rgba = to_rgba(value)
        except Exception:
            return []
        if len(rgba) >= 4 and rgba[3] <= 0.05:
            return []
        return [to_hex(rgba, keep_alpha=False).upper()]

    try:
        arr = np.asarray(value)
    except Exception:
        try:
            rgba = to_rgba(value)
        except Exception:
            return []
        if len(rgba) >= 4 and rgba[3] <= 0.05:
            return []
        return [to_hex(rgba, keep_alpha=False).upper()]

    if arr.size == 0:
        return []

    if arr.ndim == 1 and arr.shape[0] in (3, 4):
        rows = arr.reshape(1, arr.shape[0])
    elif arr.ndim >= 2 and arr.shape[-1] in (3, 4):
        rows = arr.reshape(-1, arr.shape[-1])
    else:
        try:
            rgba = to_rgba(value)
        except Exception:
            return []
        rows = np.asarray(rgba).reshape(1, -1)

    out = []
    for row in rows:
        if len(row) >= 4 and float(row[3]) <= 0.05:
            continue
        try:
            out.append(to_hex(tuple(row), keep_alpha=False).upper())
        except Exception:
            pass
    return out


def _first_visible_hex(value):
    values = _as_visible_hex_values(value)
    return values[0] if values else None


def _artist_hex(artist):
    getters = (
        "get_facecolor",
        "get_markerfacecolor",
        "get_color",
        "get_edgecolor",
        "get_markeredgecolor",
    )
    for getter_name in getters:
        getter = getattr(artist, getter_name, None)
        if getter is None:
            continue
        try:
            color = _first_visible_hex(getter())
        except Exception:
            color = None
        if color:
            return color
    return None


def _add_color_record(records, seen, color, label):
    color = normalize_color(color, "")
    if not color or color in seen:
        return
    seen.add(color)
    label = str(label or "").strip()
    if not label or label.startswith("_"):
        label = f"Color {len(records) + 1}"
    records.append({"label": label, "color": color})


def _add_color_values(records, seen, values, label_prefix, max_colors=128):
    colors = []
    for color in _as_visible_hex_values(values):
        if color not in colors:
            colors.append(color)
        if len(colors) > max_colors:
            return
    for color in colors:
        _add_color_record(records, seen, color, f"{label_prefix} {len(records) + 1}")


def _array_uses_colormap(array_value):
    if array_value is None:
        return False
    try:
        import numpy as np

        arr = np.asarray(array_value)
    except Exception:
        return False
    if arr.size == 0:
        return False
    return not (arr.ndim >= 3 and arr.shape[-1] in (3, 4))


def _colormap_triplet(cmap):
    try:
        from matplotlib.colors import to_hex

        return [
            to_hex(cmap(0.05), keep_alpha=False).upper(),
            to_hex(cmap(0.50), keep_alpha=False).upper(),
            to_hex(cmap(0.95), keep_alpha=False).upper(),
        ]
    except Exception:
        return ["#157B9B", "#FFFFFF", "#FF7F0E"]


def extract_color_spec_from_figure(fig, max_colors=128) -> dict:
    records = []
    seen = set()
    colormap = None

    if fig is None or not hasattr(fig, "axes"):
        return {"colors": [], "colormap": None}

    for ax in getattr(fig, "axes", []):
        try:
            legend = ax.get_legend()
        except Exception:
            legend = None
        if legend is not None:
            handles = getattr(legend, "legend_handles", None)
            if handles is None:
                handles = getattr(legend, "legendHandles", [])
            labels = [text.get_text() for text in getattr(legend, "texts", [])]
            for idx, handle in enumerate(handles):
                label = labels[idx] if idx < len(labels) else f"Legend {idx + 1}"
                _add_color_record(records, seen, _artist_hex(handle), label)

        for idx, line in enumerate(getattr(ax, "lines", [])):
            label = getattr(line, "get_label", lambda: "")()
            _add_color_record(records, seen, _artist_hex(line), label or f"Line {idx + 1}")

        for image in getattr(ax, "images", []):
            try:
                if _array_uses_colormap(image.get_array()):
                    colormap = colormap or _colormap_triplet(image.get_cmap())
            except Exception:
                pass

        for idx, collection in enumerate(getattr(ax, "collections", [])):
            uses_cmap = False
            try:
                uses_cmap = collection.get_array() is not None
            except Exception:
                uses_cmap = False
            if uses_cmap:
                try:
                    colormap = colormap or _colormap_triplet(collection.get_cmap())
                except Exception:
                    pass
                continue

            try:
                _add_color_values(records, seen, collection.get_facecolors(), f"Collection {idx + 1}", max_colors)
            except Exception:
                pass
            try:
                _add_color_values(records, seen, collection.get_edgecolors(), f"Collection edge {idx + 1}", max_colors)
            except Exception:
                pass

        for idx, patch in enumerate(getattr(ax, "patches", [])):
            if not getattr(patch, "get_visible", lambda: True)():
                continue
            _add_color_record(records, seen, _artist_hex(patch), f"Patch {idx + 1}")

    return {"colors": records[:max_colors], "colormap": colormap}


def expand_color_list(colors, count, fallback_colors=None):
    fallback_colors = fallback_colors or []
    cleaned = []
    for idx, color in enumerate(colors or []):
        fallback = fallback_colors[idx % len(fallback_colors)] if fallback_colors else "#157B9B"
        cleaned.append(normalize_color(color, fallback))
    if not cleaned:
        cleaned = [normalize_color(color, "#157B9B") for color in fallback_colors]
    if not cleaned:
        cleaned = ["#157B9B"]
    return [cleaned[idx % len(cleaned)] for idx in range(max(0, count))]


def preset_colors_for_count(preset_name, count):
    preset = COLOR_PRESETS.get(preset_name) or COLOR_PRESETS["default"]
    seed = [
        preset.get("primary"),
        preset.get("secondary"),
        preset.get("accent"),
        preset.get("low"),
        preset.get("high"),
    ]
    unique = []
    for color in seed:
        color = normalize_color(color, "#157B9B")
        if color not in unique:
            unique.append(color)
    return expand_color_list(unique, count, unique)


def preset_colormap(preset_name):
    preset = COLOR_PRESETS.get(preset_name) or COLOR_PRESETS["default"]
    return [
        normalize_color(preset.get("low"), "#157B9B"),
        normalize_color(preset.get("mid"), "#FFFFFF"),
        normalize_color(preset.get("high"), "#FF7F0E"),
    ]


def settings_from_color_spec(spec, colors=None, colormap=None, global_scope=False):
    spec = spec or {"colors": [], "colormap": None}
    base_colors = [normalize_color(item.get("color"), "#157B9B") for item in spec.get("colors", [])]
    settings = {
        "mode": "adaptive",
        "colors": expand_color_list(colors or base_colors, len(base_colors), base_colors),
        "colormap": [normalize_color(color, "#157B9B") for color in (colormap or spec.get("colormap") or [])],
    }
    if not global_scope:
        settings["base_colors"] = base_colors
    return settings


def figure_looks_empty(fig) -> bool:
    if fig is None or not hasattr(fig, "axes"):
        return True
    for ax in fig.axes:
        try:
            if ax.has_data():
                return False
        except Exception:
            pass
        if getattr(ax, "images", None) or getattr(ax, "collections", None) or getattr(ax, "lines", None):
            return False
        patches = [p for p in getattr(ax, "patches", []) if p.get_visible()]
        if patches:
            return False
    return True


def clone_figure(fig):
    if fig is None:
        return None
    try:
        return pickle.loads(pickle.dumps(fig))
    except Exception:
        return fig


def _rgba_with_original_alpha(target_hex, original):
    try:
        from matplotlib.colors import to_rgba

        original_rgba = to_rgba(original)
        target_rgba = list(to_rgba(target_hex))
        target_rgba[3] = original_rgba[3]
        return tuple(target_rgba)
    except Exception:
        return target_hex


def _map_color_value(value, color_map):
    hex_value = _first_visible_hex(value)
    target = color_map.get(hex_value)
    if not target:
        return value, False
    return _rgba_with_original_alpha(target, value), True


def _map_color_array(values, color_map):
    try:
        import numpy as np
        from matplotlib.colors import to_rgba

        arr = np.asarray(values)
        if arr.size == 0:
            return values, False
        if arr.ndim == 1 and arr.shape[0] in (3, 4):
            mapped, changed = _map_color_value(tuple(arr), color_map)
            return mapped, changed
        if not (arr.ndim >= 2 and arr.shape[-1] in (3, 4)):
            return values, False
        new_arr = arr.copy()
        changed = False
        flat = new_arr.reshape(-1, new_arr.shape[-1])
        for idx, row in enumerate(flat):
            hex_value = _first_visible_hex(tuple(row))
            target = color_map.get(hex_value)
            if not target:
                continue
            rgba = list(to_rgba(target))
            if len(row) >= 4:
                rgba[3] = row[3]
            flat[idx, : len(row)] = rgba[: len(row)]
            changed = True
        return new_arr, changed
    except Exception:
        return values, False


def apply_color_settings_to_figure(fig, settings: dict | None, spec: dict | None = None):
    if fig is None or not settings:
        return fig

    try:
        from matplotlib.colors import LinearSegmentedColormap
    except Exception:
        return fig

    if "colors" in settings or settings.get("mode") == "adaptive":
        spec = spec or extract_color_spec_from_figure(fig)
        spec_colors = [normalize_color(item.get("color"), "#157B9B") for item in spec.get("colors", [])]
        base_colors = settings.get("base_colors") or spec_colors
        base_colors = [normalize_color(color, "#157B9B") for color in base_colors]
        target_colors = expand_color_list(settings.get("colors"), len(base_colors), base_colors)
        color_map = {base: target for base, target in zip(base_colors, target_colors) if base and target}
        cmap_colors = settings.get("colormap") or []
        if not cmap_colors and spec.get("colormap"):
            cmap_colors = spec.get("colormap")
    else:
        primary = normalize_color(settings.get("primary"), "#157B9B")
        secondary = normalize_color(settings.get("secondary"), "#7799CC")
        accent = normalize_color(settings.get("accent"), "#FF7F0E")
        low = normalize_color(settings.get("low"), primary)
        mid = normalize_color(settings.get("mid"), "#FFFFFF")
        high = normalize_color(settings.get("high"), accent)
        target_colors = [primary, secondary, accent, low, high]
        color_map = {}
        cmap_colors = [low, mid, high]

    cmap = None
    if cmap_colors:
        cmap_colors = [normalize_color(color, "#157B9B") for color in cmap_colors]
        if len(cmap_colors) == 1:
            cmap_colors = [cmap_colors[0], cmap_colors[0]]
        cmap = LinearSegmentedColormap.from_list("spashiny_adjusted_palette", cmap_colors)

    for ax in getattr(fig, "axes", []):
        for image in getattr(ax, "images", []):
            if cmap is not None:
                try:
                    image.set_cmap(cmap)
                except Exception:
                    pass

        for line in getattr(ax, "lines", []):
            try:
                mapped, changed = _map_color_value(line.get_color(), color_map)
                if changed:
                    line.set_color(mapped)
            except Exception:
                pass
            for getter_name, setter_name in (
                ("get_markerfacecolor", "set_markerfacecolor"),
                ("get_markeredgecolor", "set_markeredgecolor"),
            ):
                try:
                    getter = getattr(line, getter_name)
                    setter = getattr(line, setter_name)
                    mapped, changed = _map_color_value(getter(), color_map)
                    if changed:
                        setter(mapped)
                except Exception:
                    pass

        for collection in getattr(ax, "collections", []):
            try:
                if cmap is not None and collection.get_array() is not None:
                    collection.set_cmap(cmap)
                    continue
            except Exception:
                pass

            try:
                mapped, changed = _map_color_array(collection.get_facecolors(), color_map)
                if changed:
                    collection.set_facecolors(mapped)
            except Exception:
                pass
            try:
                mapped, changed = _map_color_array(collection.get_edgecolors(), color_map)
                if changed:
                    collection.set_edgecolors(mapped)
            except Exception:
                pass

        patches = [patch for patch in getattr(ax, "patches", []) if patch.get_visible()]
        for patch in patches:
            try:
                mapped, changed = _map_color_value(patch.get_facecolor(), color_map)
                if changed:
                    patch.set_facecolor(mapped)
            except Exception:
                pass
            try:
                mapped, changed = _map_color_value(patch.get_edgecolor(), color_map)
                if changed:
                    patch.set_edgecolor(mapped)
            except Exception:
                pass

        try:
            legend = ax.get_legend()
            if legend is not None:
                handles = getattr(legend, "legend_handles", None)
                if handles is None:
                    handles = getattr(legend, "legendHandles", [])
                for handle in handles:
                    mapped_color = _artist_hex(handle)
                    target = color_map.get(mapped_color)
                    if not target:
                        continue
                    if hasattr(handle, "set_color"):
                        handle.set_color(target)
                    if hasattr(handle, "set_facecolor"):
                        handle.set_facecolor(target)
            if target_colors:
                ax.set_prop_cycle(color=target_colors)
        except Exception:
            pass

    try:
        fig.canvas.draw_idle()
    except Exception:
        pass
    return fig


def plot_output_with_palette(output_id: str, *args, **kwargs):
    return ui.div(
        ui.div(
            ui.input_action_button(
                f"palette_{output_id}",
                "Adjust Colors",
                class_="btn btn-outline-secondary btn-sm",
            ),
            style="display:flex; justify-content:flex-end; margin:0 0 8px 0;",
        ),
        ui.output_plot(output_id, *args, **kwargs),
        class_="plot-color-shell",
    )
