"""
pages/1_📄_Upload.py — Upload PDF & Build Knowledge Graph
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.api_client import upload_pdf, build_graph

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Upload — Doc-Graph-AI",
    page_icon="📄",
    layout="wide",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu { visibility: hidden; } header { visibility: hidden; } footer { visibility: hidden; }

.page-title {
    font-size: 2.2rem; font-weight: 700;
    background: linear-gradient(135deg, #6C63FF, #48CAE4);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.step-header {
    font-size: 1rem; font-weight: 600; color: #9A9AB0;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-bottom: 0.5rem;
}
.stat-card {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2A2A4A; border-radius: 14px;
    padding: 1.4rem; text-align: center;
}
.stat-num   { font-size: 2.5rem; font-weight: 700; color: #6C63FF; }
.stat-label { font-size: 0.85rem; color: #7A7A9A; margin-top: 0.3rem; }

.success-banner {
    background: linear-gradient(135deg, #1A3A1A, #0D1F0D);
    border: 1px solid #48BB78; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin: 1rem 0;
    color: #48BB78; font-weight: 500;
}
.error-banner {
    background: linear-gradient(135deg, #3A1A1A, #1F0D0D);
    border: 1px solid #FC8181; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin: 1rem 0;
    color: #FC8181; font-weight: 500;
}
.doc-id-box {
    background: #0D0D1A; border: 1px solid #2A2A4A; border-radius: 8px;
    padding: 0.6rem 1rem; font-family: monospace;
    font-size: 0.85rem; color: #9A9AB0; word-break: break-all;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧠 Doc-Graph-AI")
    st.markdown("---")
    st.page_link("app.py",                          label="🏠 Home")
    st.page_link("pages/1_📄_Upload.py",            label="📄 Upload & Build")
    st.page_link("pages/2_🕸️_Graph_Viewer.py",     label="🕸️ Graph Viewer")
    st.page_link("pages/3_💬_Chat.py",              label="💬 Ask Questions")

# ── Title ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">📄 Upload & Build</div>', unsafe_allow_html=True)
st.markdown("Upload a PDF document and extract its knowledge graph into Neo4j.")
st.markdown("---")

# ── Session state ─────────────────────────────────────────────────────────────
# Store document_id between the upload step and the build step.
if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "upload_filename" not in st.session_state:
    st.session_state.upload_filename = None
if "build_result" not in st.session_state:
    st.session_state.build_result = None

# ── Step 1: Upload ────────────────────────────────────────────────────────────
st.markdown('<div class="step-header">Step 1 — Choose your PDF</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    label="Drop a PDF file here, or click to browse",
    type=["pdf"],
    help="Text-based PDFs only (not scanned images). Max 50 MB.",
)

col_upload, col_info = st.columns([1, 2])

with col_upload:
    upload_btn = st.button(
        "⬆️  Upload PDF",
        disabled=(uploaded_file is None),
        use_container_width=True,
        type="primary",
    )

with col_info:
    if uploaded_file:
        size_mb = uploaded_file.size / 1024 / 1024
        st.info(f"**{uploaded_file.name}** · {size_mb:.2f} MB")

if upload_btn and uploaded_file:
    with st.spinner("Uploading PDF..."):
        result = upload_pdf(uploaded_file.read(), uploaded_file.name)

    if "error" in result:
        st.markdown(
            f'<div class="error-banner">❌ Upload failed: {result["error"]}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.session_state.document_id      = result["document_id"]
        st.session_state.upload_filename  = result["filename"]
        st.session_state.build_result     = None  # reset if re-uploading
        st.markdown(
            f'<div class="success-banner">'
            f'✅ <b>{result["filename"]}</b> uploaded successfully!<br>'
            f'{result["message"]}'
            f'</div>',
            unsafe_allow_html=True,
        )

# Show document_id if we have one
if st.session_state.document_id:
    st.markdown("**Document ID:**")
    st.markdown(
        f'<div class="doc-id-box">{st.session_state.document_id}</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── Step 2: Build Graph ───────────────────────────────────────────────────────
st.markdown('<div class="step-header">Step 2 — Build Knowledge Graph</div>', unsafe_allow_html=True)

if st.session_state.document_id is None:
    st.info("👆 Upload a PDF first to enable graph building.")
else:
    st.markdown(
        f"Ready to extract entities and relationships from "
        f"**{st.session_state.upload_filename}** and store them in Neo4j."
    )

    build_btn = st.button(
        "🕸️  Build Knowledge Graph",
        use_container_width=False,
        type="primary",
        disabled=(st.session_state.document_id is None),
    )

    if build_btn:
        with st.spinner(
            "🤖 Extracting entities and relationships with Gemini… "
            "This may take 1–3 minutes for large documents."
        ):
            result = build_graph(st.session_state.document_id)

        st.session_state.build_result = result

    # Show build result
    if st.session_state.build_result:
        res = st.session_state.build_result

        if "error" in res:
            st.markdown(
                f'<div class="error-banner">❌ Graph build failed: {res["error"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="success-banner">'
                f'✅ Knowledge graph built successfully!<br>'
                f'{res.get("message", "")}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Stats
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-num">{res.get("nodes_merged", 0)}</div>
                    <div class="stat-label">Entities (Nodes)</div>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-num">{res.get("relationships_merged", 0)}</div>
                    <div class="stat-label">Relationships (Edges)</div>
                </div>""", unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-num">{res.get("chunks_processed", 0)}</div>
                    <div class="stat-label">Text Chunks Processed</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🕸️ View Graph →", use_container_width=True, type="primary"):
                    st.switch_page("pages/2_🕸️_Graph_Viewer.py")
            with col_b:
                if st.button("💬 Ask Questions →", use_container_width=True):
                    st.switch_page("pages/3_💬_Chat.py")
