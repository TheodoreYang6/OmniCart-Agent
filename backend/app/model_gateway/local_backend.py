"""本地模型后端 —— Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B 离线加载。

平移自 semantic_cache_poc/local_backend.py，作为 LocalModelProvider 的推理底座：
- embed_texts(texts) -> list[list[float]]   : Qwen3-Embedding-0.6B (sentence-transformers, L2 归一化)
- rerank_logits(query, docs) -> list[float]  : Qwen3-Reranker-0.6B (yes/no 对数几率，越大越相关)
- status() -> dict                           : 就绪自检

设计要点（与网关其余部分一致）:
- torch / sentence-transformers / transformers 全部**函数内懒加载**，模块顶层零重依赖，
  保证 mock / api 模式导入本文件不触发 torch。
- 模型懒加载 + 进程级单例，首次调用才载入权重，避免不用时占内存。
- 权重根目录来自 config.MODELS_DIR（环境变量 OMNICART_MODELS_DIR），
  兜底 SC_MODEL_DIR，再兜底本包下 models/ 目录。
"""

from __future__ import annotations

import os

# Qwen3-Reranker 官方判定模板（与 ModelScope 权重配套）
_RR_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    "based on the Query and the Instruct provided. Note that the answer can "
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_RR_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_RR_INSTRUCT = "Given a web search query, retrieve relevant passages that answer the query"

# Qwen3-Embedding 查询侧 instruct 前缀（文档侧不加，保证非对称编码质量）
_EMB_QUERY_PROMPT = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"
)

_emb_model = None  # SentenceTransformer 单例
_rr = None         # (tokenizer, model, false_id, true_id, device) 单例
_bge = None        # (tokenizer, model, device) 单例 — bge-reranker-v2-m3 cross-encoder

import threading

_emb_lock = threading.Lock()   # V6: 单例首载加锁（并发首调曾触发 4 份模型重复加载互踩）
_encode_lock = threading.Lock()  # encode 串行：单卡/MPS 上并发前向无收益且会互相拖慢


def _model_dir() -> str:
    """解析本地模型权重根目录（config > 环境变量 > 本包内 models/）。"""
    d = os.environ.get("OMNICART_MODELS_DIR") or os.environ.get("SC_MODEL_DIR") or ""
    if not d:
        try:
            from app.core.config import MODELS_DIR

            d = MODELS_DIR or ""
        except Exception:
            d = ""
    if not d:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    return d


def emb_path() -> str:
    return os.path.join(_model_dir(), "Qwen3-Embedding-0.6B")


def rr_path() -> str:
    return os.path.join(_model_dir(), "Qwen3-Reranker-0.6B")


def bge_path() -> str:
    return os.path.join(_model_dir(), "bge-reranker-v2-m3")


def _use_bge() -> bool:
    """精排模型选择：OMNICART_RERANKER=qwen3 强制回退；默认 bge 权重存在即用
    bge（cross-encoder 一次前向出分，比 0.6B CausalLM 快一个量级）。
    检查具体权重文件而非目录，避免下载未完成时误判。"""
    if os.environ.get("OMNICART_RERANKER", "").lower() == "qwen3":
        return False
    return os.path.isfile(os.path.join(bge_path(), "model.safetensors"))


def active_reranker_name() -> str:
    """当前实际生效的精排模型名（供可观测日志展示，避免静态字符串误标）。"""
    return "bge-reranker-v2-m3" if _use_bge() else "Qwen3-Reranker-0.6B"


def _device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_emb():
    global _emb_model
    if _emb_model is None:
        with _emb_lock:  # 双重检查：并发首调只加载一份权重
            if _emb_model is None:
                from sentence_transformers import SentenceTransformer

                _emb_model = SentenceTransformer(emb_path(), device=_device())
    return _emb_model


def _load_rr():
    global _rr
    if _rr is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dev = _device()
        tok = AutoTokenizer.from_pretrained(rr_path(), padding_side="left")
        # fp16 推理：yes/no logits 差值对半精度不敏感，MPS/CUDA 上约提速 2x；纯 CPU 保持 fp32
        dtype = torch.float16 if dev in ("mps", "cuda") else torch.float32
        model = (
            AutoModelForCausalLM.from_pretrained(rr_path(), torch_dtype=dtype)
            .to(dev)
            .eval()
        )
        false_id = tok.convert_tokens_to_ids("no")
        true_id = tok.convert_tokens_to_ids("yes")
        _rr = (tok, model, false_id, true_id, dev)
    return _rr


def _load_bge():
    global _bge
    if _bge is None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        dev = _device()
        tok = AutoTokenizer.from_pretrained(bge_path())
        dtype = torch.float16 if dev in ("mps", "cuda") else torch.float32
        model = (
            AutoModelForSequenceClassification.from_pretrained(bge_path(), torch_dtype=dtype)
            .to(dev)
            .eval()
        )
        _bge = (tok, model, dev)
    return _bge


def embed_texts(texts, batch_size: int = 32, is_query: bool = False) -> list[list[float]]:
    """批量嵌入，返回 list[list[float]]（L2 归一化，1024 维）。

    is_query=True 时对查询加官方 instruct 前缀（文档侧不加），保证非对称检索质量。
    """
    if not texts:
        return []
    model = _load_emb()
    kwargs = dict(
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    if is_query:
        kwargs["prompt"] = _EMB_QUERY_PROMPT
    with _encode_lock:  # 同一设备上串行前向，避免多线程互踩
        vecs = model.encode(list(texts), **kwargs)
    return [v.tolist() for v in vecs]


def _fmt(query: str, doc: str) -> str:
    return (
        f"{_RR_PREFIX}<Instruct>: {_RR_INSTRUCT}\n"
        f"<Query>: {query}\n<Document>: {doc}{_RR_SUFFIX}"
    )


def rerank_logits(query: str, documents: list[str], batch_size: int = 8) -> list[float]:
    """(query, 每个 doc) 的相关性分（越大越相关，无界 logit，适用 sigmoid 归一）。

    默认使用 bge-reranker-v2-m3（cross-encoder，单前向出分）；权重缺失或
    OMNICART_RERANKER=qwen3 时回退 Qwen3-Reranker-0.6B（yes/no log-odds）。
    两者分数语义一致：顺序与输入一致，调用方 sigmoid 后得 [0,1] 相关度。
    """
    if not documents:
        return []
    if _use_bge():
        return _rerank_logits_bge(query, documents, batch_size)
    return _rerank_logits_qwen3(query, documents, batch_size)


def _rerank_logits_bge(query: str, documents: list[str], batch_size: int = 16) -> list[float]:
    """bge-reranker-v2-m3：(query, doc) 对进 cross-encoder，单 logit 相关分。"""
    import torch

    tok, model, dev = _load_bge()
    out: list[float] = []
    for i in range(0, len(documents), batch_size):
        chunk = documents[i : i + batch_size]
        pairs = [[query, d] for d in chunk]
        enc = tok(
            pairs, padding=True, truncation=True, max_length=512, return_tensors="pt"
        ).to(dev)
        with torch.no_grad():
            logits = model(**enc).logits.view(-1)
        out.extend(float(x) for x in logits)
    return out


def _rerank_logits_qwen3(query: str, documents: list[str], batch_size: int = 8) -> list[float]:
    """Qwen3-Reranker-0.6B：yes/no 对数几率(log-odds)，越大越相关。"""
    import torch

    tok, model, false_id, true_id, dev = _load_rr()
    out: list[float] = []
    for i in range(0, len(documents), batch_size):
        chunk = documents[i : i + batch_size]
        prompts = [_fmt(query, d) for d in chunk]
        # max_length 512：文档已在 RerankFusion 瘦身到 ~400 字符，512 token 足够覆盖；
        # attention 计算量随序列长平方增长，相比 1024 提速显著
        enc = tok(
            prompts, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(dev)
        with torch.no_grad():
            logits = model(**enc).logits[:, -1, :]  # 最后位置的下一 token logits
        for row in logits:
            yes = float(row[true_id])
            no = float(row[false_id])
            out.append(yes - no)  # log-odds
    return out


def status() -> dict:
    """检查模型目录是否就绪并可推理。"""
    ep, rp = emb_path(), rr_path()
    rr_ok = os.path.isdir(rp) or os.path.isdir(bge_path())
    if not (os.path.isdir(ep) and rr_ok):
        return {"ok": False, "error": f"模型目录缺失: {_model_dir()}（需含 Qwen3-Embedding-0.6B + 精排模型）"}
    try:
        v = embed_texts(["连接测试"])
        return {"ok": True, "dim": len(v[0]), "device": _device(), "models_dir": _model_dir(),
                "reranker": "bge-reranker-v2-m3" if _use_bge() else "Qwen3-Reranker-0.6B"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"本地模型加载/推理失败: {e}"}


__all__ = ["embed_texts", "rerank_logits", "status", "emb_path", "rr_path", "bge_path"]
