import { ScoreBreakdown as SB } from "@/lib/types";

interface Props {
  breakdown: SB;
  productName: string;
}

const DIMENSIONS: { key: keyof SB; label: string; positive: boolean }[] = [
  { key: "budget_fit", label: "预算匹配", positive: true },
  { key: "scenario_fit", label: "场景匹配", positive: true },
  { key: "spec_match", label: "参数匹配", positive: true },
  { key: "review_confidence", label: "评论可信", positive: true },
  { key: "visual_similarity", label: "视觉相似", positive: true },
  { key: "availability_score", label: "可购买性", positive: true },
  { key: "risk_penalty", label: "风险惩罚", positive: false },
];

export default function ScoreBreakdownPanel({ breakdown, productName }: Props) {
  return (
    <div className="rounded-xl border border-zinc-100 bg-white p-4">
      <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
        评分明细 · {productName}
      </h4>
      <div className="space-y-2.5">
        {DIMENSIONS.map(({ key, label, positive }) => {
          const value = breakdown[key];
          const pct = Math.round(value * 100);
          const barColor = positive
            ? value >= 0.7 ? "bg-emerald-400" : value >= 0.4 ? "bg-amber-400" : "bg-red-400"
            : value <= 0.2 ? "bg-emerald-400" : value <= 0.5 ? "bg-amber-400" : "bg-red-400";
          const textColor = positive
            ? value >= 0.7 ? "text-emerald-600" : value >= 0.4 ? "text-amber-600" : "text-red-600"
            : value <= 0.2 ? "text-emerald-600" : value <= 0.5 ? "text-amber-600" : "text-red-600";

          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-16 text-[11px] text-zinc-500 shrink-0">{label}</span>
              <div className="flex-1 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className={`text-[11px] font-mono font-medium w-8 text-right ${textColor}`}>
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
