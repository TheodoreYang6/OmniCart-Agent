/**
 * OmniCart 后端数据类型定义。
 *
 * 严格对齐后端 FastAPI schema 与安卓端 OmniCartApi.kt / RecommendResponse.kt。
 * 使用后端返回的 snake_case 字段名，避免转换层出错。
 */

// ---- 商品 ----

export interface Sku {
  sku_id: string
  properties?: Record<string, string>
  price: number
}

export interface FaqItem {
  question: string
  answer: string
}

export interface ReviewItem {
  nickname: string
  rating: number
  content: string
}

export interface RagKnowledge {
  marketing_description?: string
  official_faq?: FaqItem[]
  user_reviews?: ReviewItem[]
}

export interface Product {
  product_id: string
  title: string
  brand: string
  category: string
  sub_category: string
  price: number
  image_urls: string[]
  skus?: Sku[] | null
  rag_knowledge?: RagKnowledge | null
  description?: string
  // 列表接口附带字段
  avg_rating?: number
  review_count?: number
  // 检索层折叠掉的同款变体数（同款不同条目，见后端 _dedupe_variants）
  variant_count?: number
  variant_product_ids?: string[]
  // true = 该商品未被自然语言回答引用（回答只讲前几款）
  beyond_answer?: boolean
}

export interface ProductListResponse {
  total: number
  page: number
  page_size: number
  items: Product[]
}

export interface ReviewSummary {
  avg_rating: number
  positive_count: number
  negative_count: number
  risk_tags: string[]
  total_count: number
}

export interface ProductDetail {
  product_id: string
  title: string
  brand: string
  category: string
  sub_category: string
  price: number
  image_urls: string[]
  skus: Sku[]
  marketing_description: string
  official_faq: FaqItem[]
  user_reviews: ReviewItem[]
  review_summary?: ReviewSummary | null
}

// ---- 决策 / 证据 / 追踪 ----

export interface ComponentScore {
  score: number
  weight?: number
  reason?: string
  [k: string]: unknown
}

export interface DecisionResult {
  product_id: string
  final_score: number
  display_score: number
  component_scores?: Record<string, ComponentScore> | null
  evidence_ids: string[]
  risk_factors: string[]
  // 好评率正向信号（如 "12 条评价 92% 好评"），优先于 risk 展示
  positive_signal?: string
  recommendation_reason: string
  llm_relevance?: number
  llm_reasoning?: string
  llm_verdict?: string
  recommendation_level: string
  evidence_confidence: number
  support_evidence_ids: string[]
}

export interface EvidenceItem {
  evidence_id: string
  source_type: string
  source_id: string
  product_id?: string | null
  content: string
  modality: string
  confidence: number
}

export interface TraceStepItem {
  step_id: string
  agent_name: string
  action: string
  input_summary: string
  output_summary: string
  latency_ms: number
  status: string
}

// ---- 推荐请求 / 响应 ----

export interface RecommendRequest {
  user_query: string
  image_url?: string | null
  demo_mode?: boolean
  session_id?: string
  user_id?: string
  conversation_id?: string
}

export interface RecommendResponse {
  session_id: string
  conversation_id: string
  answer: string
  products: Product[]
  decision_results: DecisionResult[]
  evidence_list: EvidenceItem[]
  trace_steps: TraceStepItem[]
  harness_report?: Record<string, unknown> | null
  visual_result?: Record<string, unknown> | null
  fallback_status?: Record<string, unknown> | null
  retrieval_plan?: Record<string, unknown> | null
  sufficiency_report?: Record<string, unknown> | null
  constraints?: Record<string, unknown> | null
  used_memories?: Array<Record<string, unknown>> | null
  blocked_memories?: Array<Record<string, unknown>> | null
  memory_trace?: Record<string, unknown> | null
  target_product_analysis?: Record<string, unknown> | null
  alternative_products?: Array<Record<string, unknown>> | null
  comparison_table?: Record<string, unknown> | null
  cross_category?: Array<Record<string, unknown>> | null
  timing?: Record<string, unknown> | null
  needs_clarification?: boolean
  clarification_question?: string
  clarification_options?: Array<Record<string, unknown>> | null
  shop_action?: boolean
  actions?: Array<Record<string, unknown>> | null
}

// ---- 约束引导式推荐 ----

export interface GuideRequest {
  user_query: string
  session_id?: string
  user_id?: string
  conversation_id?: string
  category?: string
  sub_category?: string
  concern?: string
  budget_max?: number | null
  budget_min?: number | null
  round_num?: number
}

export interface GuideOption {
  label: string
  value: string
  dim: string // sub_category | concern | budget | category
}

export interface GuideResponse {
  session_id: string
  conversation_id: string
  answer: string
  should_recommend: boolean
  options: GuideOption[]
  locked_category: string
  locked_sub_category: string
  locked_concern: string
  budget_max?: number | null
  budget_min?: number | null
  products: Product[]
  decision_results: DecisionResult[]
  evidence_list: EvidenceItem[]
  trace_steps: TraceStepItem[]
}

// ---- 认证 ----

export interface AuthResponse {
  user_id: string
  username: string
  token: string
  email?: string
  phone?: string
  avatar_url?: string
  error?: string | null
}

// ---- 购物车 ----

export interface CartItem {
  cart_item_id: string
  user_id: string
  product_id: string
  sku_id?: string | null
  sku_label: string
  title: string
  brand: string
  price: number
  image_url: string
  quantity: number
  selected: boolean
}

export interface CartResponse {
  user_id: string
  session_id?: string
  conversation_id?: string
  items: CartItem[]
  total_price: number
  total_count: number
}

export interface AddToCartRequest {
  product_id: string
  sku_id?: string | null
  quantity?: number
}

export interface UpdateCartRequest {
  quantity?: number | null
  selected?: boolean | null
}

// ---- 结算 / 订单 ----

export interface CheckoutRequest {
  user_id?: string
  item_ids?: string[]
  session_id?: string
  conversation_id?: string
}

export interface CheckoutResponse {
  order_id: string
  user_id: string
  items: CartItem[]
  total_price: number
  status: string
  message: string
  error?: string
}

export interface OrderItem {
  cart_item_id: string
  product_id: string
  title: string
  brand: string
  price: number
  image_url: string
  quantity: number
  sku_label: string
}

export interface Order {
  order_id: string
  user_id: string
  items: OrderItem[]
  total_price: number
  status: string
  created_at: string
}

export interface OrderListResponse {
  user_id: string
  orders: Order[]
  count: number
}

// ---- 地址 ----

export interface Address {
  address_id: string
  user_id: string
  name: string
  phone: string
  province: string
  city: string
  district: string
  detail: string
  is_default: boolean
}

export interface AddressListResponse {
  addresses: Address[]
}

export interface AddressCreateRequest {
  name: string
  phone: string
  province?: string
  city?: string
  district?: string
  detail?: string
  is_default?: boolean
}

export type AddressUpdateRequest = Partial<AddressCreateRequest>

// ---- 对话历史 ----

export interface ConversationItem {
  conversation_id: string
  session_id: string
  title?: string | null
  status?: string | null
  last_message?: string | null
  context_snapshot?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface ConversationListResponse {
  user_id: string
  count: number
  conversations: ConversationItem[]
}

export interface ConversationMessage {
  message_id: string
  role: string
  content: string
  image_url?: string | null
  product_refs: string[]
  evidence_refs: string[]
  created_at: string
}

export interface ConversationMessagesResponse {
  conversation_id: string
  count: number
  messages: ConversationMessage[]
  products?: Record<string, Record<string, unknown>> | null
}

// ---- 偏好条目 (V3) ----

export interface PreferenceEntry {
  entry_id: string
  user_id: string
  raw_text: string
  category: string
  sub_category: string
  brands: string[]
  scenarios: string[]
  budget_min?: number | null
  budget_max?: number | null
  avoid_tags: string[]
  must_tags: string[]
  enabled: boolean
  created_at: string
}

export interface PreferenceEntriesResponse {
  user_id: string
  entries: PreferenceEntry[]
  count: number
}

export interface ParseResultResponse {
  ok: boolean
  parsed?: PreferenceEntry | null
  error?: string | null
}

export interface PreferenceSaveResultResponse {
  ok: boolean
  entry?: PreferenceEntry | null
  error?: string | null
}

// ---- 上传 / 语音 ----

export interface UploadResponse {
  file_id: string
  filename: string
  image_url: string
  size_bytes: number
  content_type: string
}

export interface TranscribeResponse {
  text: string
  fallback: boolean
  latency_ms?: number
}

// ---- 通用 ----

export interface OkResponse {
  ok: boolean
}

export interface HealthResponse {
  status: string
  service: string
  version: string
}
