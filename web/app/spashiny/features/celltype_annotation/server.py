# Extracted from /app/app/ST-SM.py. Feature: celltype_annotation; ordered phases preserve original initialization.
from spashiny._shared import runtime_globals as _spashiny_globals


def _install_0(_spashiny_ctx):

    @_spashiny_ctx.render.text
    def txt_celltype():
        adata = _spashiny_ctx.adata_obj()
        if adata is None:
            return "No data available"
        if "celltype1" not in adata.obs:
            return (
                "No existing clustering/annotation column was found; no C0 grouping was invented."
            )
        return str(adata.obs["celltype1"].value_counts())

    _spashiny_ctx.txt_celltype = txt_celltype


def _install_1(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.adata_obj)
    def _init_annotation_table():
        adata = _spashiny_ctx.adata_obj()
        if adata is None:
            return
        if "celltype1" not in adata.obs.columns:
            return
        clusters = sorted(adata.obs["celltype1"].astype(str).unique().tolist())
        if _spashiny_ctx.annotation_source_identity.get() is not adata:
            current_labels = {}
            if "celltype_ST_SM" in adata.obs:
                for cluster, group in adata.obs.groupby("celltype1", observed=True):
                    values = group["celltype_ST_SM"].dropna().astype(str).unique()
                    if len(values) == 1:
                        current_labels[str(cluster)] = values[0]
            _spashiny_ctx.annotation_df.set(
                _spashiny_ctx.pd.DataFrame(
                    {
                        "cluster": clusters,
                        "celltype_ST_SM": [current_labels.get(c) for c in clusters],
                    }
                )
            )
            _spashiny_ctx.annotation_source_identity.set(adata)
            return
        current_df = _spashiny_ctx.annotation_df()
        if current_df.empty:
            init_df = _spashiny_ctx.pd.DataFrame(
                {"cluster": clusters, "celltype_ST_SM": [None] * len(clusters)}
            )
            _spashiny_ctx.annotation_df.set(init_df)
        else:
            old_map = dict(zip(current_df["cluster"], current_df["celltype_ST_SM"]))
            init_df = _spashiny_ctx.pd.DataFrame(
                {"cluster": clusters, "celltype_ST_SM": [old_map.get(c, None) for c in clusters]}
            )
            _spashiny_ctx.annotation_df.set(init_df)

    _spashiny_ctx._init_annotation_table = _init_annotation_table


def _install_2(_spashiny_ctx):

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_add_annotation)
    def _add_annotation():
        df = _spashiny_ctx.annotation_df()
        cluster = _spashiny_ctx.input.cluster_to_annotate()
        label = _spashiny_ctx.input.annotation_text()
        if df.empty:
            _spashiny_ctx.ui.notification_show("No clusters available for annotation", type="error")
            return
        if not cluster:
            _spashiny_ctx.ui.notification_show("Please select a cluster", type="error")
            return
        if not label or str(label).strip() == "":
            _spashiny_ctx.ui.notification_show("Please enter a cell type annotation", type="error")
            return
        label = str(label).strip()
        df.loc[df["cluster"] == cluster, "celltype_ST_SM"] = label
        _spashiny_ctx.annotation_df.set(df.copy())
        _spashiny_ctx.ui.notification_show(f"Annotation updated: {cluster} {label}", type="message")

    _spashiny_ctx._add_annotation = _add_annotation

    @_spashiny_ctx.reactive.Effect
    @_spashiny_ctx.reactive.event(_spashiny_ctx.input.btn_create_celltype)
    def _create_celltype_column():
        if not _spashiny_ctx._downstream_click_guard(
            "btn_create_celltype", "Create celltype_ST_SM Column"
        ):
            return
        adata = _spashiny_ctx.adata_obj()
        df = _spashiny_ctx.annotation_df()
        if adata is None:
            _spashiny_ctx.ui.notification_show("Please load data first", type="error")
            return
        if "celltype1" not in adata.obs.columns:
            _spashiny_ctx.ui.notification_show("Cluster column 'celltype1' not found", type="error")
            return
        if df.empty:
            _spashiny_ctx.ui.notification_show("No annotation table found", type="error")
            return
        _spashiny_ctx.ui.update_action_button("btn_create_celltype", disabled=True)
        _spashiny_ctx.ui.modal_show(
            _spashiny_ctx.ui.modal(
                _spashiny_ctx.ui.div(
                    _spashiny_ctx.ui.h4("Updating celltype annotation..."),
                    _spashiny_ctx.ui.p("Please wait, this may take a few seconds."),
                    _spashiny_ctx.ui.br(),
                    _spashiny_ctx.ui.tags.div(class_="spinner-border text-primary"),
                ),
                easy_close=False,
                footer=None,
            )
        )
        df["cluster"] = df["cluster"].astype(str)
        adata.obs["celltype1"] = adata.obs["celltype1"].astype(str)
        ann_map = {
            k: v for k, v in zip(df["cluster"], df["celltype_ST_SM"]) if _spashiny_ctx.pd.notna(v)
        }
        print("Effective annotation map:", ann_map)
        if "celltype_ST_SM" in adata.obs.columns:
            adata.obs.drop(columns=["celltype_ST_SM"], inplace=True)
        new_col = adata.obs["celltype1"].map(ann_map)
        new_col = new_col.fillna(adata.obs["celltype1"])
        adata.obs["celltype_ST_SM"] = new_col.astype("category")
        _spashiny_ctx.adata_obj.set(adata)
        _spashiny_ctx.ui.modal_remove()
        _spashiny_ctx.ui.update_action_button("btn_create_celltype", disabled=False)
        _spashiny_ctx.ui.notification_show(
            f"celltype_ST_SM updated ({len(ann_map)} annotations applied)", type="message"
        )

    _spashiny_ctx._create_celltype_column = _create_celltype_column

    @_spashiny_ctx.render.text
    def txt_annotation_preview():
        adata = _spashiny_ctx.adata_obj()
        if adata is None:
            return "No data loaded"
        if "celltype_ST_SM" not in adata.obs.columns:
            return "celltype_ST_SM column has not been created yet"
        return str(adata.obs["celltype_ST_SM"].value_counts())

    _spashiny_ctx.txt_annotation_preview = txt_annotation_preview


def _install_3(_spashiny_ctx):

    def build_marker_celltype_figure():
        res = _spashiny_ctx.marker_res()
        if not res:
            return None
        joint_adata = res.get("adata")
        gene_df = res.get("gene_df")
        met_df = res.get("met_df")
        actual_cats = res.get("actual_cats", [])
        color_map = res.get("palette", {})
        if joint_adata is None or "celltype_ST_SM_clean" not in joint_adata.obs.columns:
            return None
        current_labels = joint_adata.obs["celltype_ST_SM_clean"].astype(str).str.strip()
        current_labels = (
            current_labels.replace("", _spashiny_globals.np.nan)
            .replace("nan", _spashiny_globals.np.nan)
            .replace("None", _spashiny_globals.np.nan)
        )
        current_labels = current_labels.fillna("Unknown")
        if not actual_cats:
            actual_cats = _spashiny_ctx.pd.unique(current_labels).tolist()
        joint_adata.obs["celltype_ST_SM_clean"] = _spashiny_ctx.pd.Categorical(
            current_labels, categories=actual_cats, ordered=True
        )
        if not color_map:
            base_colors = [
                "#4A6BA0",
                "#9DBCED",
                "#28497F",
                "#4A8BD1",
                "#522188",
                "#7A58A5",
                "#BB94ED",
                "#AC4EDD",
                "#C58DE2",
                "#9DE86D",
                "#499E12",
                "#097A39",
                "#00C67F",
                "#6CE0AB",
                "#9DCEA2",
                "#597C5C",
                "#005908",
                "#EA4E00",
                "#EF915E",
                "#E5BE1C",
                "#4F46E5",
                "#14B8A6",
                "#F43F5E",
                "#84CC16",
                "#F59E0B",
                "#06B6D4",
                "#8B5CF6",
                "#10B981",
                "#EF4444",
                "#A855F7",
            ]
            color_map = {c: base_colors[i % len(base_colors)] for i, c in enumerate(actual_cats)}
        joint_adata.uns["celltype_ST_SM_clean_colors"] = [
            color_map.get(c, "#CCCCCC") for c in actual_cats
        ]
        top_n = 5
        all_vars = set(joint_adata.var_names)
        ST_marker_feature_list = []
        SM_marker_feature_list = []
        for col in actual_cats:
            if not gene_df.empty and col in gene_df.columns:
                valid_genes = [
                    g
                    for g in gene_df[col].head(top_n).tolist()
                    if _spashiny_ctx.pd.notna(g)
                    and str(g).strip() != ""
                    and (str(g) != "nan")
                    and (g in all_vars)
                ]
            else:
                valid_genes = []
            if not met_df.empty and col in met_df.columns:
                valid_mets = [
                    m
                    for m in met_df[col].head(top_n).tolist()
                    if _spashiny_ctx.pd.notna(m)
                    and str(m).strip() != ""
                    and (str(m) != "nan")
                    and (m in all_vars)
                ]
            else:
                valid_mets = []
            ST_marker_feature_list.append(valid_genes)
            SM_marker_feature_list.append(valid_mets)
        if not any(ST_marker_feature_list) and (not any(SM_marker_feature_list)):
            return None
        from plot_runtime import native_marker_figure

        return native_marker_figure(
            _spashiny_globals.smt.pl.plot_marker_gene_metabolite,
            joint_adata,
            groupby="celltype_ST_SM_clean",
            palette=color_map,
            ST_marker_feature_list=ST_marker_feature_list,
            SM_marker_feature_list=SM_marker_feature_list,
        )

    _spashiny_ctx.build_marker_celltype_figure = build_marker_celltype_figure


_STEPS = (_install_0, _install_1, _install_2, _install_3)


def server(_spashiny_ctx, step=0):
    return _STEPS[step](_spashiny_ctx)
