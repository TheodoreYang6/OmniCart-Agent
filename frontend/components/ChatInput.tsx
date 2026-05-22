"use client";

import { useRef, useState } from "react";

interface Props {
  onSend: (query: string, imageUrl?: string) => void;
  onUpload?: (file: File) => Promise<{ image_url: string }>;
  disabled?: boolean;
}

const QUICK_EXAMPLES = [
  "适合iPhone的磁吸充电宝",
  "出差给MacBook和手机充电",
  "200元以内最轻便的充电宝",
  "坐飞机可以带的充电宝推荐",
];

export default function ChatInput({ onSend, onUpload, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((query.trim() || imageUrl) && !disabled && !uploading) {
      onSend(query.trim() || "帮我看看这个商品", imageUrl || undefined);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !onUpload) return;
    setUploading(true);
    try {
      const result = await onUpload(file);
      setImageUrl(result.image_url);
    } catch {
      // ignore
    } finally {
      setUploading(false);
    }
  };

  const clearImage = () => {
    setImageUrl(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const canSubmit = (query.trim() || imageUrl) && !disabled && !uploading;

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="relative">
        <div
          className={`flex flex-col rounded-2xl border-2 bg-white transition-all duration-200 overflow-hidden
            ${focused ? "border-blue-400 shadow-lg shadow-blue-100" : "border-zinc-200"}`}
        >
          {/* 图片预览 */}
          {imageUrl && (
            <div className="px-5 pt-4 flex items-start gap-3">
              <div className="relative group">
                <img
                  src={`http://127.0.0.1:8006${imageUrl}`}
                  alt="上传预览"
                  className="w-20 h-20 object-cover rounded-xl border border-zinc-200"
                />
                <button
                  type="button"
                  onClick={clearImage}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white
                             text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100
                             transition-opacity hover:bg-red-600"
                >
                  ✕
                </button>
              </div>
              <span className="text-xs text-zinc-400">商品截图已上传</span>
            </div>
          )}

          {/* 输入框 */}
          <div className="flex items-center gap-2 px-4 py-3">
            {/* 上传按钮 */}
            {onUpload && (
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={disabled || uploading}
                  className="flex-shrink-0 w-9 h-9 rounded-xl bg-zinc-50 border border-zinc-200
                             flex items-center justify-center text-zinc-400
                             hover:bg-blue-50 hover:border-blue-200 hover:text-blue-500
                             disabled:opacity-30 transition-colors"
                  title="上传商品截图"
                >
                  {uploading ? (
                    <span className="w-3.5 h-3.5 border-2 border-zinc-300 border-t-blue-500 rounded-full animate-spin" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  )}
                </button>
              </>
            )}

            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              placeholder={imageUrl ? "补充文字描述（可选）..." : "描述你的购物需求，或上传商品截图..."}
              className="flex-1 py-1.5 text-sm bg-transparent
                         placeholder:text-zinc-400 focus:outline-none
                         disabled:opacity-40"
              disabled={disabled}
            />
            <button
              type="submit"
              disabled={!canSubmit}
              className="flex-shrink-0 px-5 py-2 rounded-xl bg-blue-500 text-sm font-semibold text-white
                         hover:bg-blue-600 active:scale-95
                         disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-blue-500
                         transition-all duration-200"
            >
              {disabled ? (
                <span className="flex items-center gap-2">
                  <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  分析中
                </span>
              ) : (
                "查询"
              )}
            </button>
          </div>
        </div>
      </form>

      {/* 快捷示例 */}
      <div className="flex flex-wrap gap-2">
        <span className="text-[11px] text-zinc-400 pt-0.5">试试：</span>
        {QUICK_EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQuery(ex);
              if (!disabled) onSend(ex);
            }}
            disabled={disabled}
            className="text-[11px] px-3 py-1.5 rounded-full bg-white border border-zinc-200
                       text-zinc-500 hover:text-blue-600 hover:border-blue-300 hover:bg-blue-50
                       disabled:opacity-30 transition-colors"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
