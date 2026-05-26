const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Types ──

export interface Theme {
  name: string;
  description: string;
  importance: number;
}

export interface ConceptualDomain {
  name: string;
  scope: string;
  weight: number;
  key_terms: string[];
}

export interface RootConcept {
  name: string;
  definition: string;
}

export interface GlobalUnderstanding {
  document_summary: string;
  major_themes: Theme[];
  conceptual_domains: ConceptualDomain[];
  root_concepts: RootConcept[];
  educational_structure: string;
  learning_flow: string;
}

export interface Concept {
  id: string;
  label: string;
  summary: string;
  confidence: number;
  concept_type: "foundation" | "mechanism" | "process" | "application" | "abstraction" | "derived";
  abstraction_level: "root" | "branch" | "leaf";
  educational_role: "central" | "supporting" | "detail";
  importance: number;
  parent_id: string | null;
  children_ids: string[];
  domain: string;
  theme: string;
  prerequisite_labels: string[];
}

export interface Relationship {
  id: string;
  source_id: string;
  target_id: string;
  source_label: string;
  target_label: string;
  relationship_type: string;
  strength: number;
  reasoning: string;
  cross_domain: boolean;
}

export interface HubConcept {
  concept_id: string;
  label: string;
  hub_score: number;
  degree: number;
  cross_domain_edges: number;
}

export interface GraphNode {
  id: string;
  label: string;
  summary: string;
  concept_type: string;
  abstraction_level: string;
  educational_role: string;
  importance: number;
  domain: string;
  theme: string;
  hub_score: number;
  is_hub: boolean;
  parent_id: string | null;
  children_ids: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  strength: number;
  hierarchy_edge: boolean;
  cross_domain: boolean;
  reasoning: string;
}

export interface GraphData {
  nodes: { data: GraphNode; position: { x: number; y: number } }[];
  edges: { data: GraphEdge }[];
  hub_concept_ids: string[];
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  char_count: number;
  text: string;
  text_truncated: boolean;
  global_understanding: GlobalUnderstanding;
  concepts: Concept[];
  relationships?: Relationship[];
  hub_concepts?: HubConcept[];
  graph?: GraphData;
}

export interface DocumentStatus {
  id: string;
  filename: string;
  status: "pending" | "processing" | "ready" | "error";
  progress: number;
  stage: string | null;
  error: string | null;
}

// ── API methods ──

const UPLOAD_TIMEOUT_MS = 300_000; // 5 minutes for large PDFs with many chunks

export async function uploadDocument(
  file: File,
  onProgress?: (message: string) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    const res = await fetch(`${API_URL}/upload`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Upload failed: ${body}`);
    }
    const { job_id } = await res.json();
    
    if (onProgress) onProgress("Initializing...");

    return await new Promise<UploadResponse>((resolve, reject) => {
      const es = new EventSource(`${API_URL}/stream/${job_id}`);
      
      const cleanup = () => {
        es.close();
        clearTimeout(timer);
      };

      es.addEventListener("progress", (e) => {
        if (onProgress) onProgress(e.data);
      });

      es.addEventListener("complete", (e) => {
        cleanup();
        try {
          const raw = JSON.parse(e.data);
          
          // Validate and normalize critical fields
          const validated: UploadResponse = {
            document_id: String(raw.document_id ?? ""),
            filename: String(raw.filename ?? ""),
            char_count: Number(raw.char_count ?? 0),
            text: String(raw.text ?? ""),
            text_truncated: Boolean(raw.text_truncated ?? false),
            global_understanding: raw.global_understanding && typeof raw.global_understanding === "object"
              ? raw.global_understanding
              : { document_summary: "", major_themes: [], conceptual_domains: [], root_concepts: [], educational_structure: "", learning_flow: "" },
            concepts: Array.isArray(raw.concepts) ? raw.concepts : [],
            relationships: Array.isArray(raw.relationships) ? raw.relationships : [],
            hub_concepts: Array.isArray(raw.hub_concepts) ? raw.hub_concepts : [],
            graph: raw.graph && raw.graph.nodes ? raw.graph : undefined,
          };
          resolve(validated);
        } catch (err) {
          reject(new Error("Failed to parse completion result"));
        }
      });

      es.addEventListener("error", (e: any) => {
        cleanup();
        reject(new Error(e.data || "Stream disconnected or failed"));
      });
      
      es.addEventListener("ping", () => {
        // Just keeping connection alive
      });
    });
    
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        "Request timed out after 5 minutes. The document may be too large or the API is slow."
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function getStatus(docId: string): Promise<DocumentStatus> {
  return request(`/status/${docId}`);
}

export function getGraph(docId: string): Promise<GraphData> {
  return request(`/graph/${docId}`);
}

export function searchConcepts(query: string): Promise<{ id: string; label: string }[]> {
  return request(`/concepts?q=${encodeURIComponent(query)}`);
}

export function streamStatus(
  docId: string,
  onEvent: (data: DocumentStatus) => void,
  onError?: (err: Event) => void
): EventSource {
  const es = new EventSource(`${API_URL}/stream/${docId}`);
  es.onmessage = (event) => {
    const data = JSON.parse(event.data) as DocumentStatus;
    onEvent(data);
  };
  if (onError) es.onerror = onError;
  return es;
}
