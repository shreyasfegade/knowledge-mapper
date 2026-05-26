"use client";

import { useState, useRef, useEffect, useCallback } from "react";

interface SearchResult {
  id: string;
  label: string;
  domain: string;
  concept_type: string;
}

interface SearchPaletteProps {
  visible: boolean;
  items: SearchResult[];
  onSelect: (id: string) => void;
  onClose: () => void;
}

export default function SearchPalette({ visible, items, onSelect, onClose }: SearchPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query.trim()
    ? items.filter((item) =>
        item.label.toLowerCase().includes(query.toLowerCase()) ||
        item.domain.toLowerCase().includes(query.toLowerCase())
      )
    : items.slice(0, 12);

  useEffect(() => {
    if (visible) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [visible]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      onSelect(filtered[selectedIndex].id);
      onClose();
    }
  }, [filtered, selectedIndex, onSelect, onClose]);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}
      style={{ background: "rgba(5,5,8,0.6)" }}
    >
      <div
        className="glass-panel w-full max-w-md mx-4 overflow-hidden animate-crystallize"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="px-4 py-3 border-b" style={{ borderColor: "rgba(40,44,68,0.2)" }}>
          <div className="flex items-center gap-3">
            <svg className="h-4 w-4 shrink-0" style={{ color: "var(--text-muted)" }}
                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
            <input
              ref={inputRef}
              type="text"
              placeholder="Search concepts…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-transparent outline-none text-sm"
              style={{ color: "var(--text-bright)" }}
            />
            <kbd className="text-[10px] px-1.5 py-0.5 rounded" style={{
              color: "var(--text-ghost)",
              background: "var(--void-surface)",
              border: "1px solid var(--glass-border)",
            }}>ESC</kbd>
          </div>
        </div>

        {/* Results */}
        <div className="max-h-[40vh] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              No concepts found
            </div>
          ) : (
            filtered.slice(0, 10).map((item, i) => (
              <button
                key={item.id}
                onClick={() => { onSelect(item.id); onClose(); }}
                className="w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors duration-100"
                style={{
                  background: i === selectedIndex ? "rgba(123,143,248,0.06)" : "transparent",
                }}
                onMouseEnter={() => setSelectedIndex(i)}
              >
                <div className="h-2 w-2 rounded-full shrink-0" style={{
                  background: item.concept_type === "foundation" ? "#4040c8" :
                              item.concept_type === "mechanism" ? "#1a7a3a" :
                              item.concept_type === "process" ? "#1a6880" :
                              item.concept_type === "application" ? "#7a5010" :
                              item.concept_type === "abstraction" ? "#5828a8" :
                              "#882040",
                }} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: "var(--text-bright)" }}>
                    {item.label}
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {item.domain}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
