export interface Product {
  product_id: string;
  title: string;
  brand: string;
  category: string;
  price: number;
  specs: {
    capacity: string | null;
    wired_power: string | null;
    wireless_power: string | null;
    ports: string[];
    weight: string | null;
    dimensions: string | null;
  };
  scenarios: string[];
  stock_status: string;
  tags: string[];
  description: string;
  score: number;
  evidence_ids: string[];
}

export interface ScoreBreakdown {
  budget_fit: number;
  scenario_fit: number;
  spec_match: number;
  review_confidence: number;
  visual_similarity: number;
  availability_score: number;
  risk_penalty: number;
}

export interface DecisionResult {
  product_id: string;
  final_score: number;
  display_score: number;
  score_breakdown: ScoreBreakdown;
  evidence_ids: string[];
  risk_factors: string[];
  recommendation_reason: string;
}

export interface TraceStep {
  step_id: string;
  agent_name: string;
  action: string;
  input_summary: string;
  output_summary: string;
  latency_ms: number;
  status: string;
}

export interface VisualEvidence {
  field: string;
  value: string;
  confidence: number;
  evidence_id: string;
}

export interface VisualResult {
  product_name: string | null;
  brand: string | null;
  price: number | null;
  capacity: string | null;
  power: string | null;
  ports: string[];
  highlights: string[];
  confidence: number;
  evidence_list: VisualEvidence[];
  raw_response: string;
  fallback_level: number;
}

export interface RecommendResponse {
  session_id: string;
  answer: string;
  products: Product[];
  evidence_list: Record<string, unknown>[];
  decision_results: DecisionResult[];
  trace_steps: TraceStep[];
  visual_result: VisualResult | null;
  skill_executions: unknown[];
  harness_report: Record<string, unknown>;
  fallback_status: Record<string, unknown>;
}
