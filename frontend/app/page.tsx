"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { uploadDocument, getDocument, type UploadResponse, type GraphNode, type GraphEdge, type GraphData } from "@/lib/api";
import { graphToMarkdown, downloadText } from "@/lib/export";
import KnowledgeCanvas, { type CanvasControls } from "@/components/canvas/KnowledgeCanvas";
import ConceptPanel from "@/components/panels/ConceptPanel";
import UploadPanel from "@/components/panels/UploadPanel";
import SearchPalette from "@/components/panels/SearchPalette";
import HUD from "@/components/hud/HUD";

type AppState = "awaiting" | "processing" | "exploring";

export default function KnowledgeNavigator() {
  const [appState, setAppState] = useState<AppState>("awaiting");
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Focus state
  const [focusedNode, setFocusedNode] = useState<GraphNode | null>(null);
  const [focusedEdges, setFocusedEdges] = useState<GraphEdge[]>([]);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  // Search state
  const [searchOpen, setSearchOpen] = useState(false);

  // Canvas controls (zoom/fit) exposed to the HUD.
  const canvasControlsRef = useRef<CanvasControls | null>(null);

  // ── Enter a fully-processed graph ──
  const enterGraph = useCallback((data: UploadResponse) => {
    setResult(data);
    setGraphData(data.graph ?? null);
    setFileName(data.filename || null);
    setAppState("exploring");
  }, []);

  // ── Upload handler ──
  const handleUpload = useCallback(async (file: File) => {
    setFileName(file.name);
    setAppState("processing");
    setError(null);
    setFocusedNode(null);
    setFocusedEdges([]);
    setFocusedNodeId(null);
    setProgressMessage(null);

    try {
      const data = await uploadDocument(file, (msg) => {
        setProgressMessage(msg);
      });
      if (data.graph?.nodes?.length) {
        enterGraph(data);
        // Make the processed graph shareable / reload-safe.
        if (data.document_id) {
          window.history.replaceState(null, "", `?doc=${data.document_id}`);
        }
      } else {
        setError("No concepts could be extracted from this document. Try a denser, text-based PDF.");
        setAppState("awaiting");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while processing the document.");
      setAppState("awaiting");
    }
  }, [enterGraph]);

  // ── Restore a shared/previously-processed graph from ?doc=<id> ──
  useEffect(() => {
    const docId = new URLSearchParams(window.location.search).get("doc");
    if (!docId) return;

    let cancelled = false;
    setAppState("processing");
    setProgressMessage("Loading saved graph…");

    getDocument(docId)
      .then((data) => {
        if (cancelled) return;
        if (data.graph?.nodes?.length) {
          enterGraph(data);
        } else {
          setError("This saved graph is empty or could not be loaded.");
          setAppState("awaiting");
        }
      })
      .catch(() => {
        if (cancelled) return;
        setError("Couldn't find that saved graph. It may have been removed.");
        window.history.replaceState(null, "", window.location.pathname);
        setAppState("awaiting");
      });

    return () => { cancelled = true; };
  }, [enterGraph]);

  // ── Node focus handler ──
  const handleNodeFocus = useCallback((node: GraphNode | null, edges: GraphEdge[]) => {
    setFocusedNode(node);
    setFocusedEdges(edges);
    setFocusedNodeId(node?.id ?? null);
  }, []);

  // ── Navigate to a concept ──
  const navigateToConcept = useCallback((nodeId: string) => {
    if (!graphData) return;
    const nodeEntry = graphData.nodes.find((n) => n.data.id === nodeId);
    if (!nodeEntry) return;

    const connectedEdges = graphData.edges
      .filter((e) => e.data.source === nodeId || e.data.target === nodeId)
      .map((e) => e.data);

    setFocusedNode(nodeEntry.data);
    setFocusedEdges(connectedEdges);
    setFocusedNodeId(nodeId);
  }, [graphData]);

  // ── Export current graph as Markdown ──
  const handleExport = useCallback(() => {
    if (!result) return;
    const base = (result.filename || "knowledge-map").replace(/\.pdf$/i, "");
    downloadText(`${base}.md`, graphToMarkdown(result));
  }, [result]);

  // ── Copy a shareable link to this graph ──
  const handleCopyLink = useCallback(() => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(window.location.href).catch(() => {});
    }
  }, []);

  // ── Dismiss focus ──
  const dismissFocus = useCallback(() => {
    setFocusedNode(null);
    setFocusedEdges([]);
    setFocusedNodeId(null);
  }, []);

  // ── Upload new ──
  const handleUploadNew = useCallback(() => {
    setAppState("awaiting");
    setGraphData(null);
    setResult(null);
    setFocusedNode(null);
    setFocusedEdges([]);
    setFocusedNodeId(null);
    setFileName(null);
    setError(null);
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (appState === "exploring") {
          setSearchOpen((v) => !v);
        }
      }
      if (e.key === "Escape") {
        if (searchOpen) {
          setSearchOpen(false);
        } else if (focusedNode) {
          dismissFocus();
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [appState, searchOpen, focusedNode, dismissFocus]);

  // ── Search items ──
  const searchItems = graphData?.nodes.map((n) => ({
    id: n.data.id,
    label: n.data.label,
    domain: n.data.domain,
    concept_type: n.data.concept_type,
  })) ?? [];

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#0c0e14" }}>
      {/* ── Clean Obsidian-style background ── */}
      <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 0 }} />

      {/* ── Knowledge Canvas ── */}
      {graphData && appState === "exploring" && (
        <div className="absolute inset-0" style={{ zIndex: 5 }}>
          <KnowledgeCanvas
            graphData={graphData}
            onNodeFocus={handleNodeFocus}
            focusedNodeId={focusedNodeId}
            controlsRef={canvasControlsRef}
          />
        </div>
      )}

      {/* ── Upload Panel ── */}
      <UploadPanel
        visible={appState === "awaiting" || appState === "processing"}
        isProcessing={appState === "processing"}
        progressMessage={progressMessage}
        serverError={error}
        onUpload={handleUpload}
      />

      {/* ── HUD ── */}
      {appState === "exploring" && (
        <HUD
          filename={fileName}
          nodeCount={graphData?.nodes.length ?? 0}
          edgeCount={graphData?.edges.length ?? 0}
          controlsRef={canvasControlsRef}
          onUploadNew={handleUploadNew}
          onExport={handleExport}
          onCopyLink={handleCopyLink}
          shareEnabled={!!result?.document_id}
        />
      )}

      {/* ── Concept Panel ── */}
      {appState === "exploring" && (
        <ConceptPanel
          node={focusedNode}
          edges={focusedEdges}
          onNavigate={navigateToConcept}
          onDismiss={dismissFocus}
        />
      )}

      {/* ── Search Palette ── */}
      <SearchPalette
        visible={searchOpen}
        items={searchItems}
        onSelect={navigateToConcept}
        onClose={() => setSearchOpen(false)}
      />

      {/* ── Processing overlay shimmer ── */}
      {appState === "processing" && (
        <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 2 }}>
          <div className="absolute inset-0 opacity-30" style={{
            background: "radial-gradient(ellipse 50% 50% at 50% 50%, rgba(74,222,128,0.06) 0%, transparent 60%)",
            animation: "breathe 3s ease-in-out infinite",
          }} />
        </div>
      )}
    </div>
  );
}
