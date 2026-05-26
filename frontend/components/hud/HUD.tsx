"use client";

import { useRef } from "react";

interface HUDProps {
  filename: string | null;
  nodeCount: number;
  edgeCount: number;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  onUploadNew: () => void;
}

export default function HUD({ filename, nodeCount, edgeCount, canvasRef, onUploadNew }: HUDProps) {
  const getCanvas = () => (canvasRef.current as any)?._knowledgeCanvas;

  return (
    <>
      {/* Top-left: document info */}
      {filename && (
        <div className="absolute top-5 left-5 z-30 glass-panel-subtle px-4 py-2.5 flex items-center gap-3 animate-fade-in-up">
          <svg className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--accent)" }}
               fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
          <span className="text-xs font-medium truncate max-w-[200px]" style={{ color: "var(--text-primary)" }}>
            {filename}
          </span>
          <span className="text-[10px] font-mono tabular-nums" style={{ color: "var(--text-muted)" }}>
            {nodeCount}c · {edgeCount}l
          </span>
        </div>
      )}

      {/* Top-right: upload new */}
      {filename && (
        <div className="absolute top-5 right-5 z-30 animate-fade-in-up">
          <button
            onClick={onUploadNew}
            className="glass-panel-subtle px-3 py-2 flex items-center gap-2 transition-all duration-200 group"
            style={{ cursor: "pointer" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "rgba(90,109,212,0.3)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "rgba(40,44,68,0.25)";
            }}
          >
            <svg className="h-3.5 w-3.5" style={{ color: "var(--text-secondary)" }}
                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>New</span>
          </button>
        </div>
      )}

      {/* Bottom-right: zoom controls */}
      {filename && (
        <div className="absolute bottom-6 right-6 z-30 glass-panel-subtle flex flex-col gap-0.5 p-1 animate-fade-in-up">
          {[
            { icon: "+", label: "Zoom in", fn: () => getCanvas()?.zoomIn() },
            { icon: "−", label: "Zoom out", fn: () => getCanvas()?.zoomOut() },
            { icon: "⊙", label: "Fit view", fn: () => getCanvas()?.fitView() },
          ].map(({ icon, label, fn }) => (
            <button
              key={label}
              onClick={fn}
              title={label}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-sm transition-colors duration-200"
              style={{ color: "var(--text-secondary)" }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.color = "var(--accent)";
                (e.currentTarget as HTMLElement).style.background = "rgba(123,143,248,0.08)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
                (e.currentTarget as HTMLElement).style.background = "transparent";
              }}
            >
              {icon}
            </button>
          ))}
        </div>
      )}

      {/* Bottom center: keyboard hint */}
      {filename && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 animate-fade-in" style={{ animationDelay: "1s" }}>
          <div className="text-[10px] flex items-center gap-1.5" style={{ color: "var(--text-ghost)" }}>
            <kbd className="px-1.5 py-0.5 rounded text-[9px]" style={{
              background: "var(--void-surface)",
              border: "1px solid var(--glass-border)",
            }}>⌘K</kbd>
            <span>Search</span>
          </div>
        </div>
      )}
    </>
  );
}
