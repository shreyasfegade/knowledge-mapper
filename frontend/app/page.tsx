"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { uploadDocument, type UploadResponse, type GraphNode, type GraphEdge, type GraphData } from "@/lib/api";
import KnowledgeCanvas from "@/components/canvas/KnowledgeCanvas";
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

  // Focus state
  const [focusedNode, setFocusedNode] = useState<GraphNode | null>(null);
  const [focusedEdges, setFocusedEdges] = useState<GraphEdge[]>([]);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  // Search state
  const [searchOpen, setSearchOpen] = useState(false);

  // Canvas ref for HUD controls
  const canvasElRef = useRef<HTMLCanvasElement | null>(null);

  // ── Upload handler ──
  const handleUpload = useCallback(async (file: File) => {
    setFileName(file.name);
    setAppState("processing");
    setFocusedNode(null);
    setFocusedEdges([]);
    setFocusedNodeId(null);
    setProgressMessage(null);

    try {
      const data = await uploadDocument(file, (msg) => {
        setProgressMessage(msg);
      });
      setResult(data);
      if (data.graph?.nodes?.length) {
        setGraphData(data.graph);
        setAppState("exploring");
      } else {
        // No graph data — show error state but stay in processing
        setAppState("awaiting");
      }
    } catch (err) {
      console.error("Upload failed:", err);
      setAppState("awaiting");
    }
  }, []);

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

  // ── Capture canvas ref ──
  const captureCanvasRef = useCallback((el: HTMLCanvasElement | null) => {
    canvasElRef.current = el;
  }, []);

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
          />
        </div>
      )}

      {/* ── Upload Panel ── */}
      <UploadPanel
        visible={appState === "awaiting" || appState === "processing"}
        isProcessing={appState === "processing"}
        progressMessage={progressMessage}
        onUpload={handleUpload}
      />

      {/* ── HUD ── */}
      {appState === "exploring" && (
        <HUD
          filename={fileName}
          nodeCount={graphData?.nodes.length ?? 0}
          edgeCount={graphData?.edges.length ?? 0}
          canvasRef={canvasElRef}
          onUploadNew={handleUploadNew}
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
