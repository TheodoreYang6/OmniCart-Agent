import { RecommendResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8006";

export async function postRecommend(query: string, imageUrl?: string): Promise<RecommendResponse> {
  const resp = await fetch(`${BASE}/api/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_query: query, image_url: imageUrl || null }),
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function uploadImage(file: File): Promise<{
  file_id: string;
  filename: string;
  image_url: string;
  size_bytes: number;
  content_type: string;
}> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || `Upload failed: ${resp.status}`);
  }
  return resp.json();
}

export async function getHealth(): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/api/health`);
  return resp.json();
}
