"""
pages/2_🕸️_Graph_Viewer.py — Interactive Knowledge Graph Visualization
"""
import sys
from pathlib import Path
from collections import Counter
import pandas as pd
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.api_client import get_graph, health_check

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Graph Viewer — Doc-Graph-AI",
    page_icon="🕸️",
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
    margin-bottom: 0.2rem;
}
.stat-card {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2A2A4A; border-radius: 12px;
    padding: 1.1rem; text-align: center;
}
.stat-num   { font-size: 2.1rem; font-weight: 700; color: #6C63FF; }
.stat-label { font-size: 0.8rem; color: #7A7A9A; margin-top: 0.2rem; }

.type-badge {
    display: inline-block;
    padding: 0.25rem 0.65rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 0.2rem 0.3rem 0.2rem 0;
    color: #FFFFFF;
}
.legend-box {
    background: #141426;
    border: 1px solid #2A2A4A;
    border-radius: 10px;
    padding: 0.75rem 1.2rem;
    margin-bottom: 1rem;
}
.status-ok  { color: #48BB78; font-weight: 600; }
.status-err { color: #FC8181; font-weight: 600; }
.empty-box {
    background: linear-gradient(135deg, #1A1A2E, #0D0D1A);
    border: 1px dashed #3D3D6B;
    border-radius: 14px;
    padding: 3rem 2rem;
    text-align: center;
    color: #9A9AB0;
    margin: 2rem 0;
}
</style>
""", unsafe_allow_html=True)

# ── Color Palette for Entity Types ───────────────────────────────────────────
TYPE_COLORS = {
    "Person": "#4A90D9",        # Sky Blue
    "Organization": "#E67E22",  # Warm Orange
    "Product": "#2ECC71",       # Emerald Green
    "Technology": "#9B59B6",    # Purple
    "Location": "#E74C3C",      # Coral Red
    "Concept": "#1ABC9C",       # Turquoise
    "Entity": "#6C63FF",        # Default Violet
}
DEFAULT_NODE_COLOR = "#6C63FF"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧠 Doc-Graph-AI")
    st.markdown("---")
    st.page_link("app.py",                      label="🏠 Home")
    st.page_link("pages/1_📄_Upload.py",        label="📄 Upload & Build")
    st.page_link("pages/2_🕸️_Graph_Viewer.py", label="🕸️ Graph Viewer")
    st.page_link("pages/3_💬_Chat.py",          label="💬 Ask Questions")
    st.markdown("---")

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

# ── Title & Header ────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">🕸️ Knowledge Graph Viewer</div>', unsafe_allow_html=True)
st.markdown("Interactive visual exploration of entities and relationships extracted from your documents.")
st.markdown("---")

# ── Controls Bar ──────────────────────────────────────────────────────────────
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 1])

with ctrl_col1:
    current_doc_id = st.session_state.get("document_id")
    filter_options = ["All Documents"]
    if current_doc_id:
        filter_options.append(f"Current Document ({current_doc_id[:8]}...)")
    
    selected_filter = st.selectbox(
        "Scope",
        options=filter_options,
        index=0,
        help="Select whether to view the whole database graph or only the active uploaded document.",
    )

with ctrl_col2:
    search_query = st.text_input(
        "🔍 Search Node Name",
        placeholder="Filter nodes by keyword...",
    ).strip().lower()

with ctrl_col3:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    refresh_clicked = st.button("🔄 Refresh Graph", use_container_width=True)

# Determine document_id filter
filter_doc_id = current_doc_id if selected_filter.startswith("Current Document") else None

# ── Fetch Graph Data ──────────────────────────────────────────────────────────
with st.spinner("Fetching knowledge graph from Neo4j..."):
    graph_res = get_graph(document_id=filter_doc_id)

if "error" in graph_res:
    st.error(f"❌ Failed to fetch graph: {graph_res['error']}")
    st.stop()

raw_nodes = graph_res.get("nodes", [])
raw_edges = graph_res.get("edges", [])

# Handle empty state
if not raw_nodes:
    st.markdown("""
    <div class="empty-box">
        <div style="font-size: 3rem; margin-bottom: 0.5rem;">🕸️</div>
        <h3>No Knowledge Graph Data Found</h3>
        <p>There are no entities or relationships in Neo4j yet.</p>
    </div>
    """, unsafe_allow_html=True)
    col_up, _ = st.columns([1, 3])
    with col_up:
        if st.button("📄 Upload a PDF to Build Graph →", type="primary", use_container_width=True):
            st.switch_page("pages/1_📄_Upload.py")
    st.stop()

# ── Entity Type Filter ────────────────────────────────────────────────────────
all_types = sorted(list({n.get("type", "Entity") for n in raw_nodes}))
type_counts = Counter(n.get("type", "Entity") for n in raw_nodes)

selected_types = st.multiselect(
    "Filter by Entity Type",
    options=all_types,
    default=all_types,
    help="Toggle entity types to show or hide from the graph visualization.",
)

# Filter nodes based on selected types and search query
filtered_nodes = [
    n for n in raw_nodes
    if n.get("type", "Entity") in selected_types
    and (not search_query or search_query in n.get("label", "").lower())
]
filtered_node_ids = {n["id"] for n in filtered_nodes}

# Filter edges to only those connecting visible nodes
filtered_edges = [
    e for e in raw_edges
    if e.get("source") in filtered_node_ids and e.get("target") in filtered_node_ids
]

# ── Stat Cards ────────────────────────────────────────────────────────────────
s1, s2, s3, s4 = st.columns(4)
with s1:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-num">{len(filtered_nodes)}</div>
        <div class="stat-label">Displayed Entities</div>
    </div>""", unsafe_allow_html=True)
with s2:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-num">{len(filtered_edges)}</div>
        <div class="stat-label">Displayed Relationships</div>
    </div>""", unsafe_allow_html=True)
with s3:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-num">{len(selected_types)}</div>
        <div class="stat-label">Active Entity Types</div>
    </div>""", unsafe_allow_html=True)
with s4:
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-num">{len(raw_nodes)}</div>
        <div class="stat-label">Total in Database</div>
    </div>""", unsafe_allow_html=True)

st.markdown("")

# ── Color Legend ──────────────────────────────────────────────────────────────
legend_html = '<div class="legend-box"><b>Legend:</b> &nbsp;'
for ent_type in all_types:
    color = TYPE_COLORS.get(ent_type, DEFAULT_NODE_COLOR)
    count = type_counts[ent_type]
    legend_html += (
        f'<span class="type-badge" style="background-color: {color};">'
        f'{ent_type} ({count})</span> '
    )
legend_html += '</div>'
st.markdown(legend_html, unsafe_allow_html=True)

# ── Tabs: Visual Graph & Tabular Data ─────────────────────────────────────────
tab_graph, tab_nodes, tab_edges = st.tabs(["🕸️ Interactive Graph", "📋 Entities Table", "🔗 Relationships Table"])

with tab_graph:
    if not filtered_nodes:
        st.warning("No nodes match the selected entity types or search filter.")
    else:
        # Build agraph Nodes and Edges
        agraph_nodes = []
        for n in filtered_nodes:
            node_id = str(n.get("id"))
            node_label = str(n.get("label", node_id))
            node_type = str(n.get("type", "Entity"))
            node_color = TYPE_COLORS.get(node_type, DEFAULT_NODE_COLOR)

            agraph_nodes.append(
                Node(
                    id=node_id,
                    label=node_label,
                    title=f"<b>{node_label}</b><br>Type: {node_type}",
                    color=node_color,
                    size=22,
                    shape="dot",
                )
            )

        agraph_edges = []
        for e in filtered_edges:
            src = str(e.get("source"))
            tgt = str(e.get("target"))
            rel = str(e.get("label", ""))
            agraph_edges.append(
                Edge(
                    source=src,
                    target=tgt,
                    label=rel,
                    color="#4F5275",
                )
            )

        # agraph Config
        config = Config(
            width=1100,
            height=650,
            directed=True,
            physics=True,
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor="#F39C12",
            collapsible=False,
        )

        try:
            selected_node = agraph(nodes=agraph_nodes, edges=agraph_edges, config=config)
            if selected_node:
                st.info(f"Selected Entity: **{selected_node}**")
        except Exception as e:
            st.error(f"Error rendering interactive graph view: {e}")
            st.info("You can view the full entities and relationship list in the tabs above.")

with tab_nodes:
    if filtered_nodes:
        df_nodes = pd.DataFrame(filtered_nodes)
        df_nodes = df_nodes.rename(columns={"label": "Name", "type": "Entity Type", "id": "Identifier"})
        st.dataframe(df_nodes, use_container_width=True, hide_index=True)
    else:
        st.write("No entities to show.")

with tab_edges:
    if filtered_edges:
        df_edges = pd.DataFrame(filtered_edges)
        df_edges = df_edges.rename(columns={"source": "Source Entity", "label": "Relationship", "target": "Target Entity"})
        st.dataframe(df_edges, use_container_width=True, hide_index=True)
    else:
        st.write("No relationships to show for the current filters.")
