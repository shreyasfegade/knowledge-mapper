"use client";

import { useState, useRef, useEffect, type DragEvent } from "react";
import { getExamples, getHealth, type ExampleSummary } from "@/lib/api";

interface UploadPanelProps {
  visible: boolean;
  isProcessing: boolean;
  progressMessage?: string | null;
  serverError?: string | null;
  onUpload: (file: File, apiKey?: string) => void;
  onLoadExample: (docId: string) => void;
}

const API_KEY_STORAGE = "km_api_key";

export default function UploadPanel({
  visible,
  isProcessing,
  progressMessage,
  serverError,
  onUpload,
  onLoadExample,
}: UploadPanelProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  const [serverHasKey, setServerHasKey] = useState<boolean | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [showKeyField, setShowKeyField] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load examples + backend capability, and restore any saved key.
  useEffect(() => {
    getExamples().then((r) => setExamples(r.examples || [])).catch(() => setExamples([]));
    getHealth().then((h) => setServerHasKey(h.server_has_key)).catch(() => setServerHasKey(null));
    try {
      const saved = localStorage.getItem(API_KEY_STORAGE);
      if (saved) { setApiKey(saved); setShowKeyField(true); }
    } catch {}
  }, []);

  if (!visible) return null;

  const shownError = serverError ?? error;
  // A key is only required for uploading your own PDF when the server has none.
  const keyRequired = serverHasKey === false;

  const persistKey = (v: string) => {
    setApiKey(v);
    try {
      if (v.trim()) localStorage.setItem(API_KEY_STORAGE, v.trim());
      else localStorage.removeItem(API_KEY_STORAGE);
    } catch {}
  };

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    if (keyRequired && !apiKey.trim()) {
      setError("Add your own API key below to process a PDF — or explore an example, which needs no key.");
      setShowKeyField(true);
      return;
    }
    setError(null);
    onUpload(file, apiKey.trim() || undefined);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center overflow-y-auto py-8 animate-fade-in">
      <div className="glass-panel w-full max-w-lg mx-4 overflow-hidden animate-crystallize">
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
            Turn a PDF into a living map of how its ideas connect. Explore an example, or upload your own.
          </p>
        </div>

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
            <>
              {/* ── Example gallery (instant, zero-key) ── */}
              {examples.length > 0 && (
                <div className="mb-5">
                  <p className="text-[11px] font-medium uppercase tracking-wider mb-2.5" style={{ color: "var(--text-muted)" }}>
                    Explore an example — no key needed
                  </p>
                  <div className="flex flex-col gap-2">
                    {examples.map((ex) => (
                      <button
                        key={ex.id}
                        onClick={() => onLoadExample(ex.id)}
                        className="group text-left rounded-xl px-4 py-3 transition-all duration-200"
                        style={{ background: "var(--void-raised)", border: "1px solid var(--glass-border)" }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(123,143,248,0.3)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--glass-border)"; }}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{ex.title}</span>
                          <span className="text-[11px] shrink-0" style={{ color: "var(--text-ghost)" }}>
                            {ex.node_count} concepts · {ex.edge_count} links
                          </span>
                        </div>
                        {ex.domains?.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {ex.domains.map((d) => (
                              <span key={d} className="text-[10px] rounded-full px-2 py-0.5"
                                    style={{ color: "var(--text-muted)", background: "var(--void-surface)", border: "1px solid var(--glass-border)" }}>
                                {d}
                              </span>
                            ))}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Divider ── */}
              {examples.length > 0 && (
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-px flex-1" style={{ background: "var(--glass-border)" }} />
                  <span className="text-[11px]" style={{ color: "var(--text-ghost)" }}>or upload your own</span>
                  <div className="h-px flex-1" style={{ background: "var(--glass-border)" }} />
                </div>
              )}

              {/* ── Drop zone ── */}
              <div
                onDrop={onDrop}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onClick={() => fileInputRef.current?.click()}
                className="cursor-pointer rounded-xl p-8 text-center transition-all duration-300"
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
                  Text-based PDF · up to 50 MB{keyRequired ? " · needs an API key" : ""}
                </p>
              </div>

              {/* ── Bring-your-own-key ── */}
              <div className="mt-3">
                {!showKeyField ? (
                  <button onClick={() => setShowKeyField(true)}
                          className="text-xs transition-colors"
                          style={{ color: "var(--text-muted)" }}>
                    {keyRequired ? "Add your API key to upload →" : "Use your own API key →"}
                  </button>
                ) : (
                  <div className="rounded-lg p-3" style={{ background: "var(--void-raised)", border: "1px solid var(--glass-border)" }}>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => persistKey(e.target.value)}
                      placeholder="DeepSeek / OpenAI-compatible API key"
                      spellCheck={false}
                      autoComplete="off"
                      className="w-full rounded-md px-3 py-2 text-sm outline-none"
                      style={{ background: "var(--void-surface)", border: "1px solid var(--glass-border)", color: "var(--text-primary)" }}
                    />
                    <p className="text-[11px] mt-2 leading-relaxed" style={{ color: "var(--text-ghost)" }}>
                      Stored only in your browser and sent solely with your upload — never logged.
                      {keyRequired
                        ? " The public demo has no shared key, so uploading your own PDF needs one. Examples always work without a key."
                        : ""}
                    </p>
                  </div>
                )}
              </div>

              {shownError && (
                <div className="mt-3 rounded-lg px-4 py-3 text-sm flex items-start gap-2.5"
                     style={{ color: "#e87a86", background: "rgba(220,50,80,0.06)", border: "1px solid rgba(220,50,80,0.15)" }}>
                  <svg className="h-4 w-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                  </svg>
                  <span className="leading-relaxed">{shownError}</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
