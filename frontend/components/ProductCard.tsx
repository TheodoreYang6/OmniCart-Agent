import { Product } from "@/lib/types";

interface Props {
  product: Product;
  displayScore?: number;
  risks?: string[];
  rank?: number;
}

const SCENARIO_LABELS: Record<string, string> = {
  commute: "通勤", business_trip: "出差", flight: "飞机",
  travel: "旅行", outdoor: "户外", gaming: "游戏", desk: "桌面",
  emergency: "应急",
};

export default function ProductCard({ product, displayScore, risks, rank }: Props) {
  const scoreColor =
    displayScore !== undefined
      ? displayScore >= 7.5
        ? "from-emerald-400 to-emerald-500"
        : displayScore >= 5
          ? "from-amber-400 to-amber-500"
          : "from-red-400 to-red-500"
      : "from-zinc-300 to-zinc-400";

  const scoreBg =
    displayScore !== undefined
      ? displayScore >= 7.5
        ? "bg-emerald-50 text-emerald-700"
        : displayScore >= 5
          ? "bg-amber-50 text-amber-700"
          : "bg-red-50 text-red-700"
      : "bg-zinc-50 text-zinc-500";

  return (
    <div className="group rounded-2xl border border-zinc-100 bg-white p-5
                    shadow-sm hover:shadow-lg hover:border-zinc-200
                    transition-all duration-300">
      {/* 排名 + 标题行 */}
      <div className="flex items-start gap-3">
        {rank !== undefined && (
          <span className="flex-shrink-0 w-7 h-7 rounded-full bg-zinc-100
                           flex items-center justify-center text-xs font-bold text-zinc-500">
            {rank}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm text-zinc-800 leading-snug line-clamp-2">
            {product.title}
          </h3>
          <p className="text-xs text-zinc-400 mt-1">{product.brand}</p>
        </div>
        {/* 评分徽章 */}
        {displayScore !== undefined && (
          <div className={`flex-shrink-0 flex flex-col items-center px-3 py-2 rounded-xl ${scoreBg}`}>
            <span className="text-xl font-bold leading-none">{displayScore}</span>
            <span className="text-[9px] mt-0.5">/10分</span>
          </div>
        )}
      </div>

      {/* 评分条 */}
      {displayScore !== undefined && (
        <div className="mt-3 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${scoreColor} transition-all`}
            style={{ width: `${(displayScore / 10) * 100}%` }}
          />
        </div>
      )}

      {/* 规格 */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
        {product.specs.capacity && (
          <span className="flex items-center gap-1">
            <span className="text-zinc-300">容量</span> {product.specs.capacity}
          </span>
        )}
        {product.specs.wired_power && (
          <span className="flex items-center gap-1">
            <span className="text-zinc-300">功率</span> {product.specs.wired_power}
          </span>
        )}
        {product.specs.weight && (
          <span className="flex items-center gap-1">
            <span className="text-zinc-300">重量</span> {product.specs.weight}
          </span>
        )}
      </div>

      {/* 接口 */}
      {product.specs.ports.length > 0 && (
        <div className="mt-2 flex gap-1">
          {product.specs.ports.map((port) => (
            <span key={port} className="text-[10px] px-2 py-0.5 rounded-md bg-zinc-50 text-zinc-500 font-mono border border-zinc-100">
              {port}
            </span>
          ))}
        </div>
      )}

      {/* 场景 + 标签 */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {product.scenarios.slice(0, 3).map((s) => (
          <span key={s} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">
            {SCENARIO_LABELS[s] || s}
          </span>
        ))}
        {product.tags.slice(0, 3).map((tag) => (
          <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-50 text-zinc-500 border border-zinc-100">
            {tag.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {/* 价格 */}
      <div className="mt-4 flex items-center justify-between pt-3 border-t border-zinc-50">
        <span className="text-lg font-bold text-zinc-900">
          ¥{product.price}
        </span>
        {product.stock_status !== "in_stock" && (
          <span className="text-xs text-orange-500 font-medium">库存紧张</span>
        )}
      </div>

      {/* 风险提示 */}
      {risks && risks.length > 0 && (
        <div className="mt-3 rounded-lg bg-red-50/50 px-3 py-2 text-[11px] text-red-600 leading-relaxed">
          {risks.join(" · ")}
        </div>
      )}
    </div>
  );
}
