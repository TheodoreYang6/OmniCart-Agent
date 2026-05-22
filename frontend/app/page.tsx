"use client";

import { useState } from "react";
import ChatInput from "@/components/ChatInput";
import ProductCard from "@/components/ProductCard";
import ScoreBreakdownPanel from "@/components/ScoreBreakdown";
import { postRecommend, uploadImage } from "@/lib/api";
import { RecommendResponse } from "@/lib/types";

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RecommendResponse | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);

  const handleSend = async (query: string, imageUrl?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await postRecommend(query, imageUrl);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file: File) => {
    const result = await uploadImage(file);
    setUploadedImageUrl(result.image_url);
    return result;
  };

  const decisionMap = new Map(
    (data?.decision_results || []).map((d) => [d.product_id, d])
  );

  const hasResults = data && !loading;

  return (
    <div className="flex flex-col min-h-full">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-zinc-200/60 bg-white/70 backdrop-blur-xl">
        <div className="mx-auto max-w-4xl px-5 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600
                            flex items-center justify-center text-white font-bold text-sm">
              O
            </div>
            <div>
              <h1 className="text-sm font-bold text-zinc-800">OmniCart Agent</h1>
              <p className="text-[10px] text-zinc-400">购物决策助手 · V0</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-zinc-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            后端 {data ? "已连接" : "就绪"}
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-4xl px-5 py-8 space-y-6">
        {/* 输入区 */}
        <ChatInput onSend={handleSend} onUpload={handleUpload} disabled={loading} />

        {/* 错误 */}
        {error && (
          <div className="rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {/* 加载骨架 */}
        {loading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-20 rounded-xl bg-white border border-zinc-100" />
            <div className="grid gap-4 sm:grid-cols-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-48 rounded-2xl bg-white border border-zinc-100" />
              ))}
            </div>
          </div>
        )}

        {/* 空状态 — 未查询时显示 */}
        {!hasResults && !loading && !error && (
          <div className="text-center py-16">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-50 to-blue-100
                            flex items-center justify-center text-3xl">
              🔍
            </div>
            <h2 className="text-lg font-bold text-zinc-700">智能购物决策助手</h2>
            <p className="text-sm text-zinc-400 mt-2 max-w-md mx-auto leading-relaxed">
              输入你的购物需求，OmniCart Agent 会在 35 款充电宝中
              为你匹配最合适的商品，并用可解释的评分告诉你为什么推荐。
            </p>
          </div>
        )}

        {/* 结果区 */}
        {hasResults && (
          <>
            {/* 已上传图片 + 视觉解析结果 */}
            {uploadedImageUrl && (
              <div className="flex items-start gap-4 rounded-xl bg-white border border-zinc-100 p-4">
                <img
                  src={`http://127.0.0.1:8006${uploadedImageUrl}`}
                  alt="商品截图"
                  className="w-20 h-20 object-cover rounded-lg border border-zinc-100 shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-zinc-700 mb-2">商品截图解析结果</p>
                  {data?.visual_result && data.visual_result.confidence > 0 ? (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      {data.visual_result.product_name && (
                        <div><span className="text-zinc-400">商品：</span><span className="text-zinc-700">{data.visual_result.product_name}</span></div>
                      )}
                      {data.visual_result.brand && (
                        <div><span className="text-zinc-400">品牌：</span><span className="text-zinc-700">{data.visual_result.brand}</span></div>
                      )}
                      {data.visual_result.capacity && (
                        <div><span className="text-zinc-400">容量：</span><span className="text-zinc-700">{data.visual_result.capacity}</span></div>
                      )}
                      {data.visual_result.power && (
                        <div><span className="text-zinc-400">功率：</span><span className="text-zinc-700">{data.visual_result.power}</span></div>
                      )}
                      {data.visual_result.price && (
                        <div><span className="text-zinc-400">价格：</span><span className="text-zinc-700">¥{data.visual_result.price}</span></div>
                      )}
                      {data.visual_result.ports.length > 0 && (
                        <div><span className="text-zinc-400">接口：</span><span className="text-zinc-700">{data.visual_result.ports.join("、")}</span></div>
                      )}
                      <div><span className="text-zinc-400">置信度：</span>
                        <span className={data.visual_result.confidence >= 0.7 ? "text-emerald-600" : "text-amber-600"}>
                          {(data.visual_result.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-400">图片已上传，但未识别到商品信息（可能是非商品图片或截图不清晰）</p>
                  )}
                </div>
              </div>
            )}

            {/* 推荐摘要 */}
            <div className="rounded-2xl bg-white border border-zinc-100 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-blue-50 to-transparent px-5 py-3 border-b border-zinc-50">
                <h2 className="text-xs font-semibold text-blue-600 uppercase tracking-wide">
                  推荐结果 · {data.products.length} 件商品
                </h2>
              </div>
              <div className="px-5 py-4">
                <p className="text-sm text-zinc-700 whitespace-pre-line leading-relaxed">
                  {data.answer}
                </p>
              </div>
            </div>

            {/* 商品卡片网格 */}
            {data.products.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                  商品列表
                </h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  {data.products.map((product, idx) => {
                    const decision = decisionMap.get(product.product_id);
                    return (
                      <ProductCard
                        key={product.product_id}
                        product={product}
                        displayScore={decision?.display_score}
                        risks={
                          decision?.risk_factors?.length
                            ? decision.risk_factors
                            : undefined
                        }
                        rank={idx + 1}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {/* 评分明细 */}
            {data.decision_results.length > 0 && (
              <details className="group">
                <summary className="text-xs font-semibold text-zinc-400 uppercase tracking-wide cursor-pointer hover:text-zinc-600 transition-colors">
                  查看评分明细 →
                </summary>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  {data.decision_results.map((dr) => {
                    const product = data.products.find(
                      (p) => p.product_id === dr.product_id
                    );
                    return (
                      <ScoreBreakdownPanel
                        key={dr.product_id}
                        breakdown={dr.score_breakdown}
                        productName={product?.title || dr.product_id}
                      />
                    );
                  })}
                </div>
              </details>
            )}

            {/* Agent Trace */}
            {data.trace_steps.length > 0 && (
              <details className="group">
                <summary className="text-xs font-semibold text-zinc-400 uppercase tracking-wide cursor-pointer hover:text-zinc-600 transition-colors">
                  Agent Trace · {data.trace_steps.length} 步
                </summary>
                <div className="mt-3 rounded-xl bg-white border border-zinc-100 overflow-hidden">
                  {data.trace_steps.map((step, i) => (
                    <div
                      key={step.step_id}
                      className="flex items-center gap-3 px-4 py-2.5 text-xs
                                 border-b border-zinc-50 last:border-0
                                 hover:bg-zinc-50/50 transition-colors"
                    >
                      <span className="w-6 h-6 rounded-full bg-zinc-100 flex items-center justify-center text-[10px] font-mono text-zinc-400">
                        {i + 1}
                      </span>
                      <span className="font-medium text-zinc-600">{step.agent_name}</span>
                      <span className="text-zinc-400">{step.action}</span>
                      <span className="text-zinc-300 ml-auto">{step.output_summary}</span>
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        step.status === "success" ? "bg-emerald-400" : "bg-red-400"
                      }`} />
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Session Info */}
            <div className="text-center text-[10px] text-zinc-300 pb-8">
              Session {data.session_id}
              {data.fallback_status && Object.keys(data.fallback_status).length > 0 && (
                <> · Fallback: V0 keyword</>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
