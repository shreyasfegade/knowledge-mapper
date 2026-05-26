"use client";

import type { GraphNode, GraphEdge } from "@/lib/api";

const TYPE_META: Record<string, { label: string; cls: string }> = {
  foundation:  { label: "Foundation",  cls: "type-badge-foundation" },
  mechanism:   { label: "Mechanism",   cls: "type-badge-mechanism" },
  process:     { label: "Process",     cls: "type-badge-process" },
  application: { label: "Application", cls: "type-badge-application" },
  abstraction: { label: "Abstraction", cls: "type-badge-abstraction" },
  derived:     { label: "Derived",     cls: "type-badge-derived" },
};

const EDGE_LABEL_COLORS: Record<string, string> = {
  prerequisite_of: "#50c888",
  depends_on: "#5090e0",
  causes: "#e06070",
  influences: "#e0b040",
  enables: "#40c0d8",
  specializes: "#9878e0",
  contrasts_with: "#e09040",
  derived_from: "#7078e0",
  part_of: "#40b8a0",
  applies_to: "#50a8e0",
  transforms_into: "#d868b0",
  semantically_linked: "#7880a0",
  hierarchy: "#505070",
};

interface ConceptPanelProps {
  node: GraphNode | null;
  edges: GraphEdge[];
  onNavigate: (nodeId: string) => void;
  onDismiss: () => void;
}

export default function ConceptPanel({ node, edges, onNavigate, onDismiss }: ConceptPanelProps) {
  if (!node) return null;

  const typeMeta = TYPE_META[node.concept_type] || TYPE_META.abstraction;
  const imp = Math.round(node.importance * 100);

  // Separate edges into meaningful vs hierarchy
  const semanticEdges = edges.filter((e) => !e.hierarchy_edge);
  const displayEdges = semanticEdges.length > 0 ? semanticEdges : edges.slice(0, 8);

  return (
    <div className="absolute bottom-6 left-6 z-40 w-[340px] max-h-[60vh] overflow-hidden animate-crystallize">
      <div className="glass-panel overflow-hidden">
        {/* Header */}
        <div className="px-5 pt-4 pb-3 border-b border-white/[0.04]">
          <div className="flex items-center gap-2 mb-2">
            <span className={`type-badge ${typeMeta.cls}`}>{typeMeta.label}</span>
            {node.is_hub && (
              <span className="type-badge" style={{
                color: "#e0b040",
                borderColor: "rgba(220,170,50,0.25)",
                background: "rgba(220,170,50,0.08)",
              }}>Hub</span>
            )}
            <span className="ml-auto text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
              {node.abstraction_level}
            </span>
          </div>

          <h3 className="text-[15px] font-semibold leading-snug" style={{ color: "var(--text-bright)" }}>
            {node.label}
          </h3>

          <p className="mt-2 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {node.summary}
          </p>

          {/* Importance + Domain */}
          <div className="mt-3 flex items-center gap-3">
            <div className="flex-1">
              <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "var(--void-surface)" }}>
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ width: `${imp}%`, background: "var(--accent)" }}
                />
              </div>
            </div>
            <span className="text-[10px] font-mono tabular-nums" style={{ color: "var(--text-muted)" }}>
              {imp}%
            </span>
          </div>

          <div className="mt-2 text-[10px]" style={{ color: "var(--text-muted)" }}>
            {node.domain}
            {node.educational_role && (
              <span className="ml-2" style={{
                color: node.educational_role === "central" ? "#60c080" :
                       node.educational_role === "supporting" ? "var(--text-secondary)" : "var(--text-muted)"
              }}>
                · {node.educational_role}
              </span>
            )}
          </div>
        </div>

        {/* Connections */}
        {displayEdges.length > 0 && (
          <div className="px-5 py-3 max-h-[30vh] overflow-y-auto">
            <div className="text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
              Connections · {displayEdges.length}
            </div>
            <div className="space-y-1">
              {displayEdges.map((edge) => {
                const isSource = edge.source === node.id;
                const connectedId = isSource ? edge.target : edge.source;
                const rtype = edge.relationship_type.replace(/_/g, " ");
                const rcolor = EDGE_LABEL_COLORS[edge.relationship_type] || EDGE_LABEL_COLORS.semantically_linked;

                return (
                  <button
                    key={edge.id}
                    onClick={() => onNavigate(connectedId)}
                    className="w-full text-left flex flex-col gap-1 rounded-lg px-3 py-2
                               transition-colors duration-200 group"
                    style={{
                      background: "rgba(10,12,24,0.4)",
                      border: "1px solid rgba(40,44,68,0.15)",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = "rgba(90,109,212,0.25)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = "rgba(40,44,68,0.15)";
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[9px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
                        style={{
                          color: rcolor,
                          background: `${rcolor}15`,
                          border: `1px solid ${rcolor}30`,
                        }}
                      >
                        {rtype}
                      </span>
                      <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                        {isSource ? "→" : "←"}
                      </span>
                      {edge.cross_domain && (
                        <span className="text-[9px] ml-auto shrink-0" style={{ color: "rgba(220,170,50,0.5)" }}>
                          cross
                        </span>
                      )}
                    </div>
                    {edge.reasoning && (
                      <p className="text-[11px] leading-snug line-clamp-2 pl-0.5" style={{ color: "var(--text-secondary)" }}>
                        {edge.reasoning}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-5 py-2.5 border-t border-white/[0.03]">
          <button
            onClick={onDismiss}
            className="text-[10px] uppercase tracking-wider transition-colors duration-200"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"; }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
