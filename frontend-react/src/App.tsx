import React, { useState, useEffect, useMemo, useRef } from 'react'
import {
  Network,
  UploadCloud,
  MessageSquare,
  RefreshCw,
  Search,
  FileText,
  Terminal,
  Database,
  Server,
  Layers,
  ArrowRight,
  ExternalLink,
  Info
} from 'lucide-react'
import NoteGraph, { type Note } from '@/components/ui/note-graph'
import type { ForceLink } from '@/components/ui/note-graph-utils/use-force-graph'
import NoteGraphDemo from '@/components/ui/demo'

// ── Types ──────────────────────────────────────────────────────────────────────
type BackendNode = { id: string; label: string; type: string }
type BackendEdge = { source: string; target: string; label: string }
type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  cypher?: string
  graph_results?: Record<string, unknown>[]
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'graph' | 'upload' | 'chat' | 'demo'>('graph')
  const [systemStatus, setSystemStatus] = useState<{ api: boolean; neo4j: boolean; checking: boolean }>({
    api: false,
    neo4j: false,
    checking: true,
  })

  // Graph state
  const [graphData, setGraphData] = useState<{ nodes: BackendNode[]; edges: BackendEdge[] }>({
    nodes: [],
    edges: [],
  })
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [selectedNote, setSelectedNote] = useState<Note | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  const [useSampleVault, setUseSampleVault] = useState(false)

  // Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [building, setBuilding] = useState(false)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [buildStats, setBuildStats] = useState<{
    nodes: number
    relationships: number
    chunks: number
  } | null>(null)

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Health Check ─────────────────────────────────────────────────────────────
  const checkHealth = async () => {
    try {
      const res = await fetch('/health')
      if (res.ok) {
        const data = await res.json()
        setSystemStatus({ api: true, neo4j: Boolean(data.neo4j), checking: false })
      } else {
        setSystemStatus({ api: false, neo4j: false, checking: false })
      }
    } catch {
      setSystemStatus({ api: false, neo4j: false, checking: false })
    }
  }

  useEffect(() => {
    checkHealth()
    fetchGraph()
    const timer = setInterval(checkHealth, 15000)
    return () => clearInterval(timer)
  }, [])

  // ── Fetch Graph Data ─────────────────────────────────────────────────────────
  const fetchGraph = async () => {
    setLoadingGraph(true)
    try {
      const res = await fetch('/api/graph')
      if (res.ok) {
        const data = await res.json()
        setGraphData({
          nodes: data.nodes || [],
          edges: data.edges || [],
        })
        const allGroups = Array.from(new Set((data.nodes || []).map((n: BackendNode) => n.type))) as string[]
        setSelectedGroups(allGroups)
      }
    } catch (err) {
      console.error('Failed to fetch graph data:', err)
    } finally {
      setLoadingGraph(false)
    }
  }

  // ── Convert Graph Data to NoteGraph schema ───────────────────────────────────
  const { notes, links } = useMemo(() => {
    const rawNodes = graphData.nodes
    const rawEdges = graphData.edges

    const filteredNodes = rawNodes.filter((n) => {
      const matchesGroup = selectedGroups.length === 0 || selectedGroups.includes(n.type)
      const matchesSearch = !searchQuery || n.label.toLowerCase().includes(searchQuery.toLowerCase())
      return matchesGroup && matchesSearch
    })

    const visibleIds = new Set(filteredNodes.map((n) => n.id))

    const mappedNotes: Note[] = filteredNodes.map((n) => ({
      id: n.id,
      title: n.label,
      group: n.type,
    }))

    const mappedLinks: ForceLink[] = rawEdges
      .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
      }))

    return { notes: mappedNotes, links: mappedLinks }
  }, [graphData, selectedGroups, searchQuery])

  const availableGroups = useMemo(() => {
    return Array.from(new Set(graphData.nodes.map((n) => n.type)))
  }, [graphData.nodes])

  // ── Handle File Upload ───────────────────────────────────────────────────────
  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return

    setUploading(true)
    setUploadMessage(null)
    setBuildStats(null)

    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      if (res.ok && data.document_id) {
        setUploadedDocId(data.document_id)
        setUploadMessage(`Uploaded "${data.filename}" successfully! Ready to extract entities and build graph.`)
      } else {
        setUploadMessage(`Upload failed: ${data.detail || 'Unknown error'}`)
      }
    } catch (err: unknown) {
      setUploadMessage(`Upload error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setUploading(false)
    }
  }

  // ── Trigger Build Graph ──────────────────────────────────────────────────────
  const handleBuildGraph = async () => {
    if (!uploadedDocId) return

    setBuilding(true)
    setUploadMessage('Analyzing document with Gemini, extracting entities & relationships, writing to Neo4j...')

    try {
      const res = await fetch(`/api/build-graph/${uploadedDocId}`, {
        method: 'POST',
      })
      const data = await res.json()

      if (res.ok) {
        setBuildStats({
          nodes: data.nodes_merged,
          relationships: data.relationships_merged,
          chunks: data.chunks_processed,
        })
        setUploadMessage('Knowledge graph built successfully!')
        fetchGraph()
      } else {
        setUploadMessage(`Build failed: ${data.detail || 'Error processing document'}`)
      }
    } catch (err: unknown) {
      setUploadMessage(`Build error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBuilding(false)
    }
  }

  // ── Handle Chat Query ────────────────────────────────────────────────────────
  const handleSendMessage = async (queryText?: string) => {
    const text = queryText || chatInput
    if (!text.trim() || chatLoading) return

    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: text }]
    setMessages(newMessages)
    setChatInput('')
    setChatLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      const data = await res.json()

      if (res.ok) {
        setMessages([
          ...newMessages,
          {
            role: 'assistant',
            content: data.answer,
            cypher: data.cypher,
            graph_results: data.graph_results,
          },
        ])
      } else {
        setMessages([
          ...newMessages,
          {
            role: 'assistant',
            content: `Error: ${data.detail || 'Could not query the knowledge graph'}`,
          },
        ])
      }
    } catch (err: unknown) {
      setMessages([
        ...newMessages,
        {
          role: 'assistant',
          content: `Network error: ${err instanceof Error ? err.message : String(err)}`,
        },
      ])
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans selection:bg-blue-600/30">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <header className="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="size-9 rounded-lg bg-zinc-800 border border-zinc-700/60 flex items-center justify-center text-blue-400 font-bold">
              <Network className="size-5" />
            </div>
            <div>
              <div className="font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
                Doc-Graph-AI
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-400">
                  React + NoteGraph
                </span>
              </div>
              <p className="text-xs text-zinc-400">Knowledge Graph Reasoning</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 p-1 rounded-xl">
            <button
              onClick={() => setActiveTab('graph')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'graph'
                  ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
              }`}
            >
              <Network className="size-3.5" />
              Graph Viewer
            </button>
            <button
              onClick={() => setActiveTab('upload')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'upload'
                  ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
              }`}
            >
              <UploadCloud className="size-3.5" />
              Upload & Build
            </button>
            <button
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'chat'
                  ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
              }`}
            >
              <MessageSquare className="size-3.5" />
              Ask Questions
            </button>
            <button
              onClick={() => setActiveTab('demo')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'demo'
                  ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
              }`}
            >
              <Layers className="size-3.5" />
              Vault Demo
            </button>
          </nav>

          {/* System Status Indicators */}
          <div className="flex items-center gap-3 text-xs text-zinc-400">
            <div className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
              <Server className="size-3 text-zinc-400" />
              <span>API:</span>
              <span
                className={`size-2 rounded-full ${
                  systemStatus.api ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
            </div>
            <div className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
              <Database className="size-3 text-zinc-400" />
              <span>Neo4j:</span>
              <span
                className={`size-2 rounded-full ${
                  systemStatus.neo4j ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
            </div>
          </div>
        </div>
      </header>

      {/* ── Main Content Area ────────────────────────────────────────────────── */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 flex flex-col">
        {/* TAB 1: GRAPH VIEWER */}
        {activeTab === 'graph' && (
          <div className="space-y-4 flex-1 flex flex-col">
            {/* Control Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 border border-zinc-800/80 p-3 rounded-xl">
              <div className="flex items-center gap-3 flex-1 min-w-[240px]">
                <div className="relative flex-1 max-w-sm">
                  <Search className="size-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Filter nodes by name..."
                    className="w-full bg-zinc-900 border border-zinc-700/60 rounded-lg pl-9 pr-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-blue-500"
                  />
                </div>

                {/* Group Toggles */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {availableGroups.map((group) => {
                    const active = selectedGroups.includes(group)
                    return (
                      <button
                        key={group}
                        onClick={() => {
                          setSelectedGroups((prev) =>
                            prev.includes(group) ? prev.filter((g) => g !== group) : [...prev, group]
                          )
                        }}
                        className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
                          active
                            ? 'bg-zinc-800 border-zinc-600 text-zinc-200'
                            : 'bg-zinc-900/50 border-zinc-800 text-zinc-500'
                        }`}
                      >
                        {group}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setUseSampleVault(!useSampleVault)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
                    useSampleVault
                      ? 'bg-blue-600/10 border-blue-500/40 text-blue-400'
                      : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {useSampleVault ? 'Using Sample Data' : 'Live DB Mode'}
                </button>
                <button
                  onClick={fetchGraph}
                  disabled={loadingGraph}
                  className="flex items-center gap-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
                >
                  <RefreshCw className={`size-3.5 ${loadingGraph ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>
            </div>

            {/* NoteGraph Canvas Card */}
            <div className="relative flex-1 bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-4 flex flex-col justify-between overflow-hidden min-h-[540px]">
              {useSampleVault ? (
                <NoteGraphDemo />
              ) : notes.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                  <div className="size-12 rounded-2xl bg-zinc-800/80 border border-zinc-700/60 flex items-center justify-center text-zinc-400 mb-3">
                    <Network className="size-6 text-zinc-500" />
                  </div>
                  <h3 className="text-base font-semibold text-zinc-200">No Knowledge Graph Data Found</h3>
                  <p className="text-xs text-zinc-400 max-w-sm mt-1 mb-4">
                    Upload a PDF document to extract named entities and relationships into Neo4j.
                  </p>
                  <button
                    onClick={() => setActiveTab('upload')}
                    className="flex items-center gap-2 text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-2 rounded-lg transition-all"
                  >
                    Go to Upload & Ingest
                    <ArrowRight className="size-3.5" />
                  </button>
                </div>
              ) : (
                <>
                  <NoteGraph
                    notes={notes}
                    links={links}
                    selectedId={selectedNote?.id}
                    onSelect={(n) => setSelectedNote(n)}
                    height={520}
                    className="w-full"
                    showAllLabels={notes.length < 25}
                  />

                  {/* Bottom Stats & Selected Details */}
                  <div className="mt-3 pt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs text-zinc-400">
                    <div className="flex items-center gap-4">
                      <span>
                        <strong className="text-zinc-200 font-semibold">{notes.length}</strong> Entities
                      </span>
                      <span>
                        <strong className="text-zinc-200 font-semibold">{links.length}</strong> Relationships
                      </span>
                      <span>
                        <strong className="text-zinc-200 font-semibold">{availableGroups.length}</strong> Types
                      </span>
                    </div>

                    {selectedNote && (
                      <div className="flex items-center gap-2 bg-zinc-800/90 border border-zinc-700/80 px-3 py-1 rounded-lg text-zinc-200">
                        <Info className="size-3.5 text-blue-400" />
                        <span>
                          Selected: <strong>{selectedNote.title}</strong>{' '}
                          <span className="text-zinc-400 text-[11px]">({selectedNote.group || 'Entity'})</span>
                        </span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: UPLOAD & BUILD */}
        {activeTab === 'upload' && (
          <div className="max-w-2xl mx-auto w-full py-6 space-y-6">
            <div className="text-center space-y-1.5">
              <h2 className="text-2xl font-bold tracking-tight text-zinc-100">Document Ingestion Pipeline</h2>
              <p className="text-xs text-zinc-400">
                Upload text-based PDF documents. PyMuPDF parses the text, Gemini extracts entities and relationships, and Neo4j builds the graph.
              </p>
            </div>

            {/* Step 1: Upload Card */}
            <div className="bg-zinc-900/60 border border-zinc-800 p-5 rounded-2xl space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-zinc-800">
                <span className="size-6 rounded-full bg-blue-500/10 border border-blue-500/40 text-blue-400 flex items-center justify-center text-xs font-bold">
                  1
                </span>
                <h3 className="text-sm font-semibold text-zinc-200">Select & Upload PDF</h3>
              </div>

              <form onSubmit={handleFileUpload} className="space-y-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="pdf-upload-input"
                />

                <label
                  htmlFor="pdf-upload-input"
                  className="border-2 border-dashed border-zinc-800 hover:border-zinc-700 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer transition-colors bg-zinc-900/30 text-center"
                >
                  <FileText className="size-8 text-zinc-500 mb-2" />
                  <span className="text-xs text-zinc-300 font-medium">
                    {selectedFile ? selectedFile.name : 'Click to select a PDF or drag here'}
                  </span>
                  <span className="text-[11px] text-zinc-500 mt-1">
                    Text-based PDF up to 50 MB
                  </span>
                </label>

                <button
                  type="submit"
                  disabled={!selectedFile || uploading}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 rounded-lg text-xs transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {uploading ? <RefreshCw className="size-3.5 animate-spin" /> : <UploadCloud className="size-3.5" />}
                  {uploading ? 'Uploading...' : 'Upload PDF'}
                </button>
              </form>
            </div>

            {/* Step 2: Build Card */}
            <div className="bg-zinc-900/60 border border-zinc-800 p-5 rounded-2xl space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-zinc-800">
                <span className="size-6 rounded-full bg-blue-500/10 border border-blue-500/40 text-blue-400 flex items-center justify-center text-xs font-bold">
                  2
                </span>
                <h3 className="text-sm font-semibold text-zinc-200">Build Knowledge Graph</h3>
              </div>

              <p className="text-xs text-zinc-400">
                Extracts entities and relationships using Gemini 1.5 Flash and writes MERGE queries to Neo4j.
              </p>

              <button
                onClick={handleBuildGraph}
                disabled={!uploadedDocId || building}
                className="w-full bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-100 font-medium py-2 rounded-lg text-xs transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {building ? <RefreshCw className="size-3.5 animate-spin" /> : <Network className="size-3.5" />}
                {building ? 'Processing with Gemini & Neo4j...' : 'Build Knowledge Graph'}
              </button>

              {uploadMessage && (
                <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-300">
                  {uploadMessage}
                </div>
              )}

              {buildStats && (
                <div className="grid grid-cols-3 gap-3 pt-2">
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-center">
                    <div className="text-xl font-bold text-blue-400">{buildStats.nodes}</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5">Entities (Nodes)</div>
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-center">
                    <div className="text-xl font-bold text-blue-400">{buildStats.relationships}</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5">Relationships (Edges)</div>
                  </div>
                  <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-center">
                    <div className="text-xl font-bold text-blue-400">{buildStats.chunks}</div>
                    <div className="text-[11px] text-zinc-500 mt-0.5">Text Chunks</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: ASK QUESTIONS (CHAT) */}
        {activeTab === 'chat' && (
          <div className="max-w-4xl mx-auto w-full flex-1 flex flex-col justify-between py-2">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
              {messages.length === 0 ? (
                <div className="text-center py-12 space-y-4">
                  <div className="size-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mx-auto">
                    <MessageSquare className="size-6 text-zinc-500" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-base font-semibold text-zinc-200">Ask Your Knowledge Graph</h3>
                    <p className="text-xs text-zinc-400 max-w-md mx-auto">
                      Natural language questions are translated into Cypher queries by Gemini, executed against Neo4j, and returned as grounded answers.
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2 justify-center max-w-lg mx-auto pt-2">
                    {[
                      'What people and organizations are in the graph?',
                      'Which technologies or products were mentioned?',
                      'Summarize the key connections found in the document',
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() => handleSendMessage(q)}
                        className="text-xs bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 px-3 py-1.5 rounded-lg transition-all text-left"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex flex-col ${
                      msg.role === 'user' ? 'items-end' : 'items-start'
                    }`}
                  >
                    <div
                      className={`max-w-2xl rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-blue-600 text-white'
                          : 'bg-zinc-900 border border-zinc-800 text-zinc-200'
                      }`}
                    >
                      {msg.content}

                      {/* Cypher Query and Raw Records details for transparency */}
                      {msg.cypher && (
                        <div className="mt-3 pt-2.5 border-t border-zinc-800 space-y-2">
                          <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-400">
                            <Terminal className="size-3 text-zinc-500" />
                            <span>Executed Cypher:</span>
                          </div>
                          <pre className="bg-zinc-950 p-2.5 rounded-lg text-[11px] font-mono text-blue-300 overflow-x-auto border border-zinc-800/80">
                            {msg.cypher}
                          </pre>
                        </div>
                      )}

                      {msg.graph_results && msg.graph_results.length > 0 && (
                        <div className="mt-2 text-[11px] text-zinc-400">
                          <span>Graph Results: </span>
                          <span className="font-mono text-zinc-300">{msg.graph_results.length} record(s)</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Input Bar */}
            <div className="relative">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder="Ask a question about the graph (e.g. Who created GPT-4?)..."
                disabled={chatLoading}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 pr-24 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={!chatInput.trim() || chatLoading}
                className="absolute right-2 top-1/2 -translate-y-1/2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium px-3.5 py-1.5 rounded-lg transition-all disabled:opacity-50"
              >
                {chatLoading ? 'Thinking...' : 'Send'}
              </button>
            </div>
          </div>
        )}

        {/* TAB 4: COMPONENT DEMO */}
        {activeTab === 'demo' && (
          <div className="space-y-4 flex-1 flex flex-col">
            <div className="bg-zinc-900/60 border border-zinc-800 p-4 rounded-xl flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-zinc-200">Interactive NoteGraph Component Demo</h3>
                <p className="text-xs text-zinc-400">
                  Exact demo vault showing force layout, hub sizing by degree, orphan perimeter rings, and neighbourhood hover focus.
                </p>
              </div>
              <span className="text-xs font-mono text-zinc-500 bg-zinc-900 border border-zinc-800 px-2.5 py-1 rounded-md">
                @/components/ui/note-graph.tsx
              </span>
            </div>

            <div className="flex-1 bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-4 flex items-center justify-center overflow-hidden min-h-[520px]">
              <NoteGraphDemo />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
