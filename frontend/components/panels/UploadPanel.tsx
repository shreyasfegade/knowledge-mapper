"use client";

import { useState, useRef, type DragEvent } from "react";

interface UploadPanelProps {
  visible: boolean;
  isProcessing: boolean;
  progressMessage?: string | null;
  serverError?: string | null;
  onUpload: (file: File) => void;
}

export default function UploadPanel({ visible, isProcessing, progressMessage, serverError, onUpload }: UploadPanelProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!visible) return null;

  // A server-side failure takes precedence over a stale local validation message.
  const shownError = serverError ?? error;

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    setError(null);
    onUpload(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center animate-fade-in">
      <div className="glass-panel w-full max-w-md mx-4 overflow-hidden animate-crystallize">
        {/* Header */}
        <div className="px-8 pt-8 pb-2 text-center">
          <div className="mx-auto mb-5 flex h-10 w-10 items-center justify-center rounded-xl animate-float"
               style={{ background: "var(--accent-soft)", border: "1px solid rgba(123,143,248,0.15)" }}>
            <svg className="h-5 w-5" style={{ color: "var(--accent)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text-bright)" }}>
            Knowledge Mapper
          </h1>
          <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Upload educational content to explore a living topology of knowledge.
          </p>
        </div>

        {/* Drop zone */}
        <div className="px-8 pb-8 pt-4">
          {isProcessing ? (
            <div className="rounded-xl p-10 text-center" style={{ background: "var(--void-raised)", border: "1px solid var(--glass-border)" }}>
              <div className="mx-auto h-8 w-8 rounded-full border-2 animate-spin mb-4"
                   style={{ borderColor: "rgba(123,143,248,0.15)", borderTopColor: "var(--accent)" }} />
              <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {progressMessage || "Analyzing document structure..."}
              </p>
              <p className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
                Extracting concepts and inferring relationships
              </p>
              <p className="text-[11px] mt-3" style={{ color: "var(--text-ghost)" }}>
                Typically 10–30 seconds, depending on document length
              </p>
            </div>
          ) : (
            <div
              onDrop={onDrop}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onClick={() => fileInputRef.current?.click()}
              className="cursor-pointer rounded-xl p-10 text-center transition-all duration-300"
              style={{
                background: dragging ? "rgba(123,143,248,0.04)" : "var(--void-raised)",
                border: `1px solid ${dragging ? "rgba(123,143,248,0.3)" : "var(--glass-border)"}`,
                boxShadow: dragging ? "0 0 40px rgba(123,143,248,0.08)" : "none",
              }}
            >
              <input ref={fileInputRef} type="file" accept=".pdf" className="hidden"
                     onChange={() => { const f = fileInputRef.current?.files?.[0]; if (f) handleFile(f); }} />

              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl"
                   style={{ background: "var(--void-surface)", border: "1px solid var(--glass-border)" }}>
                <svg className="h-5 w-5" style={{ color: "var(--text-muted)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M7 16a4 4 0 0 1-.88-7.903A5 5 0 1 1 15.9 6L16 6a5 5 0 0 1 1 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                Drop a PDF here, or <span style={{ color: "var(--accent)" }} className="font-medium">browse files</span>
              </p>
              <p className="text-xs mt-1" style={{ color: "var(--text-ghost)" }}>
                PDF only · Up to 50 MB
              </p>
            </div>
          )}

          {shownError && !isProcessing && (
            <div className="mt-3 rounded-lg px-4 py-3 text-sm flex items-start gap-2.5"
                 style={{ color: "#e87a86", background: "rgba(220,50,80,0.06)", border: "1px solid rgba(220,50,80,0.15)" }}>
              <svg className="h-4 w-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
              </svg>
              <span className="leading-relaxed">{shownError}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
