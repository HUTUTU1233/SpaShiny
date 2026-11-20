# Shared application chrome, navigation, global assets and styles.
from spashiny._shared import runtime_globals as _spashiny_globals

app_ui = _spashiny_globals.ui.page_fluid(
    _spashiny_globals.ui.HTML(_spashiny_globals.top_nav_style_css),
    _spashiny_globals.ui.HTML(_spashiny_globals.custom_css),
    _spashiny_globals.ui.tags.script(
        src="/js/session_lifecycle.js?v=river_unified_session_recovery_20261102_r3"
    ),
    _spashiny_globals.ui.tags.script(
        src="/js/native_dash_diagnostics.js?v=prod_20261019_native_dash_v1"
    ),
    _spashiny_globals.ui.tags.script(
        src="/js/r2_multipart_upload.js?v=prod_20261023_upload_capacity_r2"
    ),
    _spashiny_globals.ui.tags.script(src="/js/upload_english_ui.js?v=20261109-v1", defer=True),
    _spashiny_globals.ui.tags.script(src="/js/knn_upload.js?v=prod_20261027_knn_complete_r19"),
    _spashiny_globals.ui.tags.script(src="/js/job_queue.js?v=prod_20261017_example_vector_v1"),
    _spashiny_globals.ui.tags.script(
        src="/js/river_progress.js?v=river_release_20261102_artifacts_v3"
    ),
    _spashiny_globals.ui.tags.script(
        """
(function () {
  function applyAlignmentImageUpdate(message) {
    const images = (message && message.images) || {};
    Object.keys(images).forEach(function (plotId) {
      const slot = document.getElementById(plotId);
      if (!slot || !slot.classList || !slot.classList.contains('alignment-worker-image-slot')) {
        return;
      }
      const item = images[plotId] || {};
      const height = slot.getAttribute('data-height') || '430px';
      if (item.url) {
        const alt = item.alt || plotId;
        const existingImg = slot.querySelector('img');
        if (existingImg && existingImg.getAttribute('data-spashiny-source') === item.url) {
          if (existingImg.getAttribute('alt') !== alt) existingImg.setAttribute('alt', alt);
          return;
        }
        // <img> cannot carry the tab-only analysis header. Fetch the signed
        // artifact with the current tab scope, then display only its Blob URL.
        const token = sessionStorage.getItem('spashiny.session.token') || '';
        const analysis = sessionStorage.getItem('spashiny.analysis.session.id') || '';
        if (!token || !analysis) {
          slot.textContent = 'Analysis session is initializing. Retrying image authorization...';
          scheduleAlignmentImageRefreshRetry();
          return;
        }
        slot.style.padding = '16px';
        slot.textContent = 'Loading image...';
        fetch(item.url, { credentials: 'same-origin', headers: {
          'X-SpaShiny-Session': token,
          'X-SpaShiny-Analysis-Session': analysis
        }}).then(function (response) {
          if (!response.ok) throw new Error('artifact authorization failed (' + response.status + ')');
          return response.blob();
        }).then(function (blob) {
          const objectUrl = URL.createObjectURL(blob);
          const prior = slot.querySelector('img');
          if (prior && prior.dataset.spashinyObjectUrl) URL.revokeObjectURL(prior.dataset.spashinyObjectUrl);
          slot.style.padding = '0';
          slot.innerHTML = '<img alt="' + alt.replace(/"/g, '&quot;') + '" ' +
            'data-spashiny-source="' + item.url.replace(/"/g, '&quot;') + '" ' +
            'data-spashiny-object-url="' + objectUrl + '" src="' + objectUrl + '" ' +
            'style="max-width:100%; max-height:' + height + '; width:auto; height:auto; display:block; margin:0 auto; object-fit:contain;">';
        }).catch(function (err) {
          slot.style.padding = '16px';
          slot.textContent = 'Image preview is unavailable: ' + (err && err.message ? err.message : 'authorization failed');
        });
      } else {
        slot.style.padding = '16px';
        slot.textContent = item.message || 'No image is available yet.';
      }
    });
    window.__spashinyAlignmentImageRefreshAttempts = 0;
  }

  function registerAlignmentImageHandler() {
    if (window.__spashinyAlignmentImageHandlerRegistered) {
      return true;
    }
    if (!window.Shiny || typeof window.Shiny.addCustomMessageHandler !== 'function') {
      return false;
    }
    window.Shiny.addCustomMessageHandler('alignment_image_update', applyAlignmentImageUpdate);
    window.__spashinyAlignmentImageHandlerRegistered = true;
    return true;
  }

  function requestAlignmentImageRefresh() {
    if (!window.Shiny || typeof window.Shiny.setInputValue !== 'function') {
      scheduleAlignmentImageRefreshRetry();
      return;
    }
    const slots = Array.from(document.querySelectorAll('.alignment-worker-image-slot'));
    if (!slots.length) {
      return;
    }
    const slotIds = slots.map(function (slot) { return slot.id || ''; }).join('|');
    const slotState = slots.map(function (slot) {
      const img = slot.querySelector('img');
      return (slot.id || '') + ':' + (img ? (img.getAttribute('src') || '') : (slot.textContent || '').slice(0, 80));
    }).join('|');
    const unresolved = slots.some(function (slot) {
      return !slot.querySelector('img') && /Loading image|Analysis session|Step4|Please run|render/i.test(slot.textContent || '');
    });
    const signature = slotIds + '::' + slotState;
    const now = Date.now();
    if (!slotIds) {
      return;
    }
    if (
      signature === window.__spashinyAlignmentImageSlotSignature &&
      (now - Number(window.__spashinyAlignmentImageLastRefreshAt || 0)) < 900
    ) {
      if (unresolved) {
        scheduleAlignmentImageRefreshRetry();
      }
      return;
    }
    if (!unresolved && signature === window.__spashinyAlignmentImageCompletedSignature) {
      return;
    }
    window.__spashinyAlignmentImageSlotSignature = signature;
    window.__spashinyAlignmentImageLastRefreshAt = now;
    window.__spashinyAlignmentImageRefreshAttempts = Number(window.__spashinyAlignmentImageRefreshAttempts || 0) + 1;
    window.Shiny.setInputValue('alignment_image_refresh_request', {
      slots: slotIds,
      state: slotState,
      attempt: window.__spashinyAlignmentImageRefreshAttempts,
      nonce: Date.now() + '-' + Math.random().toString(16).slice(2)
    }, { priority: 'event' });
    if (unresolved && window.__spashinyAlignmentImageRefreshAttempts < 12) {
      scheduleAlignmentImageRefreshRetry();
    } else if (!unresolved) {
      window.__spashinyAlignmentImageCompletedSignature = signature;
      window.__spashinyAlignmentImageRefreshAttempts = 0;
    }
  }

  function scheduleAlignmentImageRefreshRetry() {
    clearTimeout(window.__spashinyAlignmentImageRefreshTimer);
    if (Number(window.__spashinyAlignmentImageRefreshAttempts || 0) >= 12) {
      return;
    }
    window.__spashinyAlignmentImageRefreshTimer = setTimeout(function () {
      registerAlignmentImageHandler();
      requestAlignmentImageRefresh();
    }, 1250);
  }

  function installAlignmentImageBridge() {
    registerAlignmentImageHandler();
    requestAlignmentImageRefresh();
    if (window.__spashinyAlignmentImageObserverInstalled || !document.body || typeof MutationObserver === 'undefined') {
      return;
    }
    window.__spashinyAlignmentImageObserverInstalled = true;
    const observer = new MutationObserver(function (mutations) {
      const touchesAlignmentSlot = mutations.some(function (mutation) {
        const nodes = Array.from(mutation.addedNodes || []).concat(Array.from(mutation.removedNodes || []));
        return nodes.some(function (node) {
          if (!node || node.nodeType !== 1) return false;
          if (node.matches && node.matches('.alignment-worker-image-slot')) return true;
          if (node.querySelector && node.querySelector('.alignment-worker-image-slot')) return true;
          return Boolean(node.parentElement && node.parentElement.closest('.alignment-worker-image-slot'));
        });
      });
      if (!touchesAlignmentSlot) return;
      clearTimeout(window.__spashinyAlignmentImageRefreshTimer);
      window.__spashinyAlignmentImageRefreshTimer = setTimeout(function () {
        registerAlignmentImageHandler();
        requestAlignmentImageRefresh();
      }, 250);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (!registerAlignmentImageHandler()) {
    let attempts = 0;
    const timer = setInterval(function () {
      attempts += 1;
      if (registerAlignmentImageHandler() || attempts >= 20) {
        clearInterval(timer);
      }
    }, 250);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installAlignmentImageBridge, { once: true });
  } else {
    installAlignmentImageBridge();
  }
})();
    """
    ),
    _spashiny_globals.ui.tags.div(
        _spashiny_globals.ui.tags.button(
            _spashiny_globals.ui.tags.div("SpaShiny", class_="brand-title"),
            _spashiny_globals.ui.tags.div(
                _spashiny_globals.ui.tags.img(
                    src="/Wang_lab.png", class_="brand-logo-img", alt="Wang Lab"
                ),
                class_="brand-image-box",
            ),
            id="show_home",
            type="button",
            class_="brand-block brand-home-btn action-button",
        ),
        _spashiny_globals.ui.tags.div(
            _spashiny_globals.nav_dropdown(
                "Data Preparation / Preprocessing",
                _spashiny_globals.nav_btn("show_sm_prep", "SM Upload"),
                _spashiny_globals.nav_btn("show_st_prep", "ST Upload"),
                _spashiny_globals.nav_btn("show_sm_QC", "SM QC"),
                _spashiny_globals.nav_btn("show_st_QC", "ST QC"),
            ),
            _spashiny_globals.nav_dropdown(
                "Spatial Integration",
                _spashiny_globals.nav_btn("show_stsm_alignment", "ST-SM Alignment"),
                _spashiny_globals.nav_btn("show_stsm_reassignment", "KNN Reassignment"),
                _spashiny_globals.nav_btn("VIT_SM_ST", "Single-sample ST-SM Integration"),
                _spashiny_globals.nav_btn("VHIT_SM_ST", "Multi-sample ST-SM Integration"),
                _spashiny_globals.nav_btn("HIT_SM", "Multi-sample SM Integration"),
            ),
            _spashiny_globals.nav_dropdown(
                "River", _spashiny_globals.nav_btn("show_river_module", "River ST")
            ),
            _spashiny_globals.nav_dropdown(
                "Downstream Analysis",
                _spashiny_globals.nav_btn("show_downstream_marker", "Marker Analysis"),
                _spashiny_globals.nav_btn("show_dash_plotly", "Dash Plotly"),
                _spashiny_globals.nav_btn(
                    "show_enrichment_module",
                    (
                        "Enrichment Analysis"
                        if _spashiny_globals.SPASHINY_R_FEATURES_ENABLED
                        or _spashiny_globals.SPASHINY_CPU_ENRICHMENT_ENABLED
                        else "Enrichment Analysis (Disabled)"
                    ),
                ),
                _spashiny_globals.nav_btn("show_metabolite_annotation", "Metabolite Annotation"),
            ),
            class_="nav-menu-area",
        ),
        class_="top-navbar",
    ),
    _spashiny_globals.ui.output_ui("ssh_top_status"),
    _spashiny_globals.ui.tags.button(
        "New Analysis",
        id="spashiny-new-analysis",
        type="button",
        class_="new-analysis-fab action-button",
    ),
    _spashiny_globals.ui.output_ui("main_content"),
    _spashiny_globals.ui.HTML(
        """
    <script>
    document.addEventListener("DOMContentLoaded", function () {
        const dropdowns = document.querySelectorAll(".menu-dropdown");
        const itemButtons = document.querySelectorAll(".dropdown-item-btn");

        dropdowns.forEach((dropdown) => {
            const trigger = dropdown.querySelector(".menu-trigger");

            trigger.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();

                dropdowns.forEach((d) => {
                    if (d !== dropdown) d.classList.remove("open");
                });

                dropdown.classList.toggle("open");
            });
        });

        document.addEventListener("click", function () {
            dropdowns.forEach((d) => d.classList.remove("open"));
        });

        itemButtons.forEach((btn) => {
            btn.addEventListener("click", function (e) {
                e.stopPropagation();
                itemButtons.forEach((b) => b.classList.remove("is-selected"));
                btn.classList.add("is-selected");

                if (btn.id && window.Shiny && typeof window.Shiny.setInputValue === "function") {
                    window.Shiny.setInputValue(btn.id, Date.now(), { priority: "event" });
                }

                const parentDropdown = btn.closest(".menu-dropdown");
                if (parentDropdown) {
                    parentDropdown.classList.remove("open");
                }
            });
        });
    });

    Shiny.addCustomMessageHandler("trigger_download", function(message) {
        var el = document.getElementById(message.id);
        if (el) el.click();
    });
    </script>
    """
    ),
    title="SpaShiny",
)
