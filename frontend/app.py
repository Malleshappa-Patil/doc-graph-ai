"""
app.py — Doc-Graph-AI Home Page
The main entry point for the Streamlit multi-page app.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from utils.api_client import health_check

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Doc-Graph-AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Hide Streamlit default header */
#MainMenu { visibility: hidden; }
header     { visibility: hidden; }
footer     { visibility: hidden; }

/* Gradient hero text */
.hero-title {
    font-size: 3.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #6C63FF 0%, #48CAE4 50%, #90E0EF 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.15;
    margin-bottom: 0.5rem;
}
.hero-sub {
    font-size: 1.2rem;
    color: #9A9AB0;
    margin-bottom: 2rem;
    font-weight: 300;
}

/* Feature cards */
.feature-card {
    background: linear-gradient(145deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2A2A4A;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    transition: border-color 0.3s ease, transform 0.2s ease;
}
.feature-card:hover {
    border-color: #6C63FF;
    transform: translateY(-2px);
}
.feature-icon { font-size: 2rem; margin-bottom: 0.75rem; }
.feature-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #E8E8F0;
    margin-bottom: 0.4rem;
}
.feature-desc { font-size: 0.9rem; color: #7A7A9A; line-height: 1.5; }

/* Status badge */
.status-ok  { color: #48BB78; font-weight: 600; }
.status-err { color: #FC8181; font-weight: 600; }

/* Pipeline step */
.pipeline-step {
    background: #1A1A2E;
    border-left: 3px solid #6C63FF;
    border-radius: 0 8px 8px 0;
    padding: 0.6rem 1rem;
    margin: 0.4rem 0;
    font-size: 0.9rem;
    color: #C8C8E0;
}

/* Stat box */
.stat-box {
    background: linear-gradient(135deg, #1A1A2E, #0D0D1A);
    border: 1px solid #2A2A4A;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    text-align: center;
}
.stat-num  { font-size: 2.2rem; font-weight: 700; color: #6C63FF; }
.stat-label{ font-size: 0.85rem; color: #7A7A9A; margin-top: 0.2rem; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧠 Doc-Graph-AI")
    st.markdown("---")
    st.markdown("**Navigation**")
    st.page_link("app.py",                          label="🏠 Home",         icon=None)
    st.page_link("pages/1_📄_Upload.py",            label="📄 Upload & Build",icon=None)
    st.page_link("pages/2_🕸️_Graph_Viewer.py",     label="🕸️ Graph Viewer", icon=None)
    st.page_link("pages/3_💬_Chat.py",              label="💬 Ask Questions", icon=None)

    st.markdown("---")
    # Live status check
    status = health_check()
    neo4j_ok = status.get("neo4j", False)
    api_ok   = status.get("status") == "ok"

    st.markdown("**System Status**")
    st.markdown(
        f"API &nbsp;&nbsp; {'<span class=\"status-ok\">● Online</span>' if api_ok else '<span class=\"status-err\">● Offline</span>'}",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"Neo4j {'<span class=\"status-ok\">● Connected</span>' if neo4j_ok else '<span class=\"status-err\">● Disconnected</span>'}",
        unsafe_allow_html=True,
    )

# ── Hero ──────────────────────────────────────────────────────────────────────
col_hero, col_img = st.columns([3, 2])

with col_hero:
    st.markdown('<div class="hero-title">Doc-Graph-AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Transform your PDF documents into an interactive<br>'
        'knowledge graph — then ask questions in plain English.</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📄 Upload PDF", use_container_width=True, type="primary"):
            st.switch_page("pages/1_📄_Upload.py")
    with c2:
        if st.button("🕸️ View Graph", use_container_width=True):
            st.switch_page("pages/2_🕸️_Graph_Viewer.py")
    with c3:
        if st.button("💬 Ask Questions", use_container_width=True):
            st.switch_page("pages/3_💬_Chat.py")

with col_img:
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #1A1A2E 0%, #0D0D1A 100%);
        border: 1px solid #2A2A4A;
        border-radius: 20px;
        padding: 2rem;
        text-align: center;
        font-size: 5rem;
        margin-top: 1rem;
    ">
        🧠<br>
        <span style="font-size:1rem; color:#7A7A9A;">Knowledge Graph Engine</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ── How it works ──────────────────────────────────────────────────────────────
st.markdown("### ⚡ How It Works")

steps = [
    "📄  **Upload** your PDF — the app accepts text-based PDFs up to 50 MB",
    "🔍  **Parse & chunk** — PyMuPDF extracts text, split into overlapping segments",
    "🤖  **Extract** — Gemini identifies entities (people, orgs, products…) and their relationships",
    "🕸️  **Build graph** — entities become nodes, relationships become edges in Neo4j",
    "💬  **Ask questions** — Gemini converts your question to Cypher, queries Neo4j, and answers",
]
for step in steps:
    st.markdown(f'<div class="pipeline-step">{step}</div>', unsafe_allow_html=True)

st.markdown("---")

# ── Feature cards ─────────────────────────────────────────────────────────────
st.markdown("### ✨ Features")

f1, f2, f3 = st.columns(3)

with f1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🤖</div>
        <div class="feature-title">Gemini-Powered Extraction</div>
        <div class="feature-desc">
            Google Gemini extracts named entities and relationships
            from any text-based PDF — people, companies, products,
            locations, and any domain-specific types.
        </div>
    </div>
    """, unsafe_allow_html=True)

with f2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🕸️</div>
        <div class="feature-title">Interactive Graph</div>
        <div class="feature-desc">
            Explore your knowledge graph visually. Nodes are
            color-coded by entity type. Filter by document,
            zoom in on clusters, and inspect relationships.
        </div>
    </div>
    """, unsafe_allow_html=True)

with f3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">💬</div>
        <div class="feature-title">Natural Language Q&A</div>
        <div class="feature-desc">
            Ask questions in plain English. Gemini generates
            the Cypher query, runs it on Neo4j, and gives
            you a clear answer — with full transparency.
        </div>
    </div>
    """, unsafe_allow_html=True)
