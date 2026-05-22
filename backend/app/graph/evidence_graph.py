"""V1 Evidence Graph Lite — NetworkX 商品-参数-评论-证据图关系。

轻量实现，不依赖外部图数据库。用于：
- 展示证据引用链路（哪个证据支撑哪个推荐结论）
- 路径解释（为什么推荐 A 而不是 B）
- 风险传播（低分评论 → 风险标签 → 降分）
"""

from typing import Any, Optional

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class EvidenceGraph:
    """证据图 — V1 NetworkX 轻量实现。"""

    def __init__(self):
        self.graph = nx.DiGraph() if HAS_NETWORKX else None

    def add_product(self, product_id: str, attrs: dict | None = None):
        if not self.graph:
            return
        self.graph.add_node(product_id, type="product", **(attrs or {}))

    def add_evidence(self, evidence_id: str, attrs: dict | None = None):
        if not self.graph:
            return
        self.graph.add_node(evidence_id, type="evidence", **(attrs or {}))

    def add_review(self, review_id: str, attrs: dict | None = None):
        if not self.graph:
            return
        self.graph.add_node(review_id, type="review", **(attrs or {}))

    def add_risk_tag(self, tag: str, attrs: dict | None = None):
        if not self.graph:
            return
        self.graph.add_node(tag, type="risk_tag", **(attrs or {}))

    def link(self, from_id: str, to_id: str, relation: str = "supports"):
        if not self.graph:
            return
        self.graph.add_edge(from_id, to_id, relation=relation)

    def build_from_state(self, state: dict):
        """从 WorkflowState 构建证据图。"""
        if not self.graph:
            return

        products = state.get("retrieved_products", [])
        evidence = state.get("evidence_list", [])
        decisions = state.get("decision_results", [])

        for p in products:
            pid = p.get("product_id", "")
            self.add_product(pid, {"title": p.get("title", ""), "category": p.get("category", "")})

        for e in evidence:
            eid = e.get("evidence_id", "")
            pid = e.get("product_id", "")
            self.add_evidence(eid, {"source_type": e.get("source_type", ""), "content": str(e.get("content", ""))[:100]})
            if pid:
                self.link(eid, pid, "about")

        for d in decisions:
            pid = d.get("product_id", "")
            for eid in d.get("evidence_ids", []):
                self.link(eid, pid, "supports")
            for risk in d.get("risk_factors", []):
                self.add_risk_tag(risk)
                self.link(pid, risk, "has_risk")

    def get_evidence_path(self, from_id: str, to_id: str) -> list[str]:
        """获取两个节点之间的证据路径。"""
        if not self.graph:
            return []
        try:
            path = nx.shortest_path(self.graph, source=from_id, target=to_id)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_supporting_evidence(self, product_id: str) -> list[str]:
        """获取支撑某商品的所有证据 ID。"""
        if not self.graph:
            return []
        predecessors = list(self.graph.predecessors(product_id))
        return [n for n in predecessors if self.graph.nodes[n].get("type") == "evidence"]

    def get_risk_tags(self, product_id: str) -> list[str]:
        """获取某商品的风险标签。"""
        if not self.graph:
            return []
        successors = list(self.graph.successors(product_id))
        return [n for n in successors if self.graph.nodes[n].get("type") == "risk_tag"]

    def summary(self) -> dict:
        if not self.graph:
            return {"status": "networkx not installed", "nodes": 0, "edges": 0}
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "products": len([n for n, d in self.graph.nodes(data=True) if d.get("type") == "product"]),
            "evidence": len([n for n, d in self.graph.nodes(data=True) if d.get("type") == "evidence"]),
            "risk_tags": len([n for n, d in self.graph.nodes(data=True) if d.get("type") == "risk_tag"]),
        }

    def to_dict(self) -> dict:
        """导出为可序列化的字典（供前端可视化）。"""
        if not self.graph:
            return {"nodes": [], "edges": []}
        nodes = [{"id": n, **d} for n, d in self.graph.nodes(data=True)]
        edges = [{"from": u, "to": v, **d} for u, v, d in self.graph.edges(data=True)]
        return {"nodes": nodes, "edges": edges}
