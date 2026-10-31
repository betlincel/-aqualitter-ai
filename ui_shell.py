"""Native Streamlit navigation, visual tokens, and session-only UI continuity."""

import html
import streamlit as st

PAGES = ("Genel Bakış", "Görüntü Analizi", "Gözlem Haritası", "Temizlik Rotası", "Çevresel Etki")

STYLE = """
<style>
:root { --aqua-green:#68dba9; --aqua-border:#334155; }
.stApp { background:#0b1326; color:#dae2fd; }
.block-container { max-width:1560px; padding:2rem 2.5rem 4rem; }
[data-testid="stHeader"] { background:rgba(11,19,38,.94); }
[data-testid="stSidebar"] { background:#131b2e; border-right:1px solid #2d3449; }
[data-testid="stSidebar"] > div:first-child { padding-top:1.6rem; }
[data-testid="stSidebar"] [role="radiogroup"] { gap:.45rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding:.8rem .9rem; border:1px solid transparent; border-radius:8px; width:100%;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background:rgba(104,219,169,.15); border-color:#3a7860; color:#85f8c4;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#222a3d; }
h1,h2,h3 { letter-spacing:-.025em; color:#edf3ff; }
h1 { font-size:2.1rem!important; font-weight:700!important; }
[data-testid="stCaptionContainer"] { color:#b3c0cf; }
[data-testid="stMetric"] {
  background:linear-gradient(125deg,#171f33,#131b2e); border:1px solid #2d3449;
  border-radius:12px; padding:1.1rem 1.2rem; min-height:128px;
}
[data-testid="stMetricValue"] {
  color:#85f8c4; font-variant-numeric:tabular-nums; font-size:clamp(1.05rem,1.5vw,1.9rem);
}
[data-testid="stMetricLabel"] { color:#bccac0; }
[data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] > div {
  border-color:#2d3449!important; border-radius:12px;
}
[data-testid="stFileUploader"] { border-radius:12px; }
.aqua-brand { display:flex; align-items:center; gap:12px; margin-bottom:18px; }
.aqua-mark { background:#68dba9; color:#003825; font-weight:900; font-size:25px;
  border-radius:9px; width:42px; height:42px; display:grid; place-items:center; }
.aqua-brand strong { font-size:23px; letter-spacing:-.04em; }
.aqua-brand small { display:block; color:#a3b7bc; font-size:12px; margin-top:2px; }
.aqua-eyebrow { font-size:12px; letter-spacing:.12em; color:#68dba9; margin-bottom:4px; }
.aqua-badge { display:inline-block; border:1px solid #3a7860; background:#123b32;
  color:#85f8c4; border-radius:20px; padding:4px 10px; font-size:12px; margin-bottom:12px; }
.aqua-note { color:#bccac0; line-height:1.7; }
@media(max-width:850px) { .block-container { padding:1rem 1rem 3rem; } }
</style>
"""


def preserve_ui_values():
    """Detach inactive-page controls from Streamlit's widget cleanup.

    Buttons and file-uploader objects are deliberately excluded. Upload bytes have
    a separate session-only copy, so photos never need a disk file or Git entry.
    """
    prefixes = (
        "review_label_", "review_decision_", "record_type_", "observation_date_",
        "location_method_", "latitude_", "longitude_", "marine_route_", "marine_visit_order_",
    )
    exact = {"active_page", "analysis_threshold", "map_edit_observation_id",
             "observation_map_layer", "marine_fuel_consumption"}
    for key in list(st.session_state):
        if key in exact or key.startswith(prefixes):
            st.session_state[key] = st.session_state[key]


def go_to(page):
    st.session_state['active_page'] = page


def shell():
    st.markdown(STYLE, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(
            '<div class="aqua-brand"><div class="aqua-mark">A</div>'
            '<div><strong>AquaLitter</strong><small>Kıyı gözlem ve temizlik planı</small></div></div>',
            unsafe_allow_html=True,
        )
        page = st.radio("Bölümler", PAGES, key='active_page', label_visibility='collapsed')
        st.divider()
        st.caption("TRABZON ÇALIŞMA BÖLGESİ")
        st.caption("Gerçek gözlemler ve senaryolar ayrı planlanır. Konum kullanıcı tarafından belirtilir.")
        st.markdown('<span class="aqua-badge">Yerel model · Kullanıcı onayı</span>', unsafe_allow_html=True)
    st.markdown('<div class="aqua-eyebrow">TRABZON KIYILARI / AQUALITTER</div>', unsafe_allow_html=True)
    st.title(page)
    return page


def context_badge(text):
    st.markdown(f'<span class="aqua-badge">{html.escape(text)}</span>', unsafe_allow_html=True)


def capture_upload(widget_key):
    uploaded = st.session_state.get(widget_key)
    if uploaded is None:
        st.session_state.pop('active_photo', None)
    else:
        st.session_state['active_photo'] = {'name': uploaded.name, 'bytes': uploaded.getvalue()}


def clear_photo():
    st.session_state.pop('active_photo', None)
    st.session_state['photo_upload_generation'] = st.session_state.get('photo_upload_generation', 0) + 1
