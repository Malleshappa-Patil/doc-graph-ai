"""
pages/3_💬_Chat.py — Natural Language Knowledge Graph Q&A
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.api_client import chat, health_check

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Ask Questions — Doc-Graph-AI",
    page_icon="💬",
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
.suggestion-chip {
    display: inline-block;
    background: #1A1A2E;
    border: 1px solid #2A2A4A;
    border-radius: 18px;
    padding: 0.4rem 0.9rem;
    font-size: 0.85rem;
    color: #9A9AB0;
    margin: 0.2rem 0.2rem;
    cursor: pointer;
}
.suggestion-chip:hover {
    border-color: #6C63FF;
    color: #E8E8F0;
}
.reasoning-box {
    background: #111122;
    border: 1px solid #2A2A4A;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-top: 0.5rem;
}
.status-ok  { color: #48BB78; font-weight: 600; }
.status-err { color: #FC8181; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

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

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Title & Subtitle ──────────────────────────────────────────────────────────
st.markdown('<div class="page-title">💬 Ask Your Knowledge Graph</div>', unsafe_allow_html=True)
st.markdown("Ask natural language questions. Doc-Graph-AI converts your query into Cypher, searches Neo4j, and generates a grounded response.")
st.markdown("---")

# ── Session State for Messages ────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Suggested Questions ───────────────────────────────────────────────────────
if len(st.session_state.messages) == 0:
    st.markdown("**💡 Example Questions to Try:**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👥 What people and organizations are in the graph?", use_container_width=True):
            st.session_state.pending_query = "What people and organizations are in the graph?"
            st.rerun()
        if st.button("🏢 Which companies or institutions are connected to each other?", use_container_width=True):
            st.session_state.pending_query = "Which companies or institutions are connected to each other?"
            st.rerun()
    with col2:
        if st.button("🚀 What technologies or products were mentioned?", use_container_width=True):
            st.session_state.pending_query = "What technologies or products were mentioned?"
            st.rerun()
        if st.button("🔗 Summarize all key relationships found in the document", use_container_width=True):
            st.session_state.pending_query = "Summarize all key relationships found in the document"
            st.rerun()
    st.markdown("")

# ── Render Chat History ───────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # If this is an assistant message with Cypher / Graph reasoning details
        if msg.get("cypher") or msg.get("graph_results"):
            with st.expander("🔍 Inspect Reasoning (Cypher & Graph Data)", expanded=False):
                if msg.get("cypher"):
                    st.markdown("**Generated Cypher Query:**")
                    st.code(msg["cypher"], language="cypher")
                
                results = msg.get("graph_results")
                if results:
                    st.markdown(f"**Neo4j Records ({len(results)} matches):**")
                    try:
                        df = pd.DataFrame(results)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    except Exception:
                        st.json(results)
                else:
                    st.caption("No matching records returned by Neo4j for this query.")

# ── Handle Input ──────────────────────────────────────────────────────────────
user_input = None
if "pending_query" in st.session_state and st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None
else:
    user_input = st.chat_input("Ask a question about the graph (e.g. Who created GPT-4?)...")

if user_input:
    # 1. Display and record user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Query backend
    with st.chat_message("assistant"):
        with st.spinner("🤖 Translating to Cypher and querying Neo4j..."):
            response = chat(user_input)

        if "error" in response:
            error_msg = f"❌ **Error:** {response['error']}"
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg,
            })
        else:
            answer = response.get("answer", "No answer generated.")
            cypher_query = response.get("cypher", "")
            raw_results = response.get("graph_results", [])

            st.markdown(answer)

            # Show reasoning expander immediately
            with st.expander("🔍 Inspect Reasoning (Cypher & Graph Data)", expanded=False):
                if cypher_query:
                    st.markdown("**Generated Cypher Query:**")
                    st.code(cypher_query, language="cypher")
                if raw_results:
                    st.markdown(f"**Neo4j Records ({len(raw_results)} matches):**")
                    try:
                        df = pd.DataFrame(raw_results)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    except Exception:
                        st.json(raw_results)
                else:
                    st.caption("No matching records returned by Neo4j for this query.")

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "cypher": cypher_query,
                "graph_results": raw_results,
            })
