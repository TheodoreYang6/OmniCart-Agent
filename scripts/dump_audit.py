import json

with open('data/audit_prompts.log', 'r', encoding='utf-8') as f:
    content = f.read()

entries = []
for block in content.split('\n---\n'):
    block = block.strip()
    if block:
        try:
            entries.append(json.loads(block))
        except Exception:
            pass

lines = [f'Total: {len(entries)} entries', '=' * 60]
for e in entries[-5:]:
    lines.append(f"Time: {e['time']} | Query: {e['query'][:80]}")
    lines.append(f"Intent: {e.get('intent', '')} | Category: {e.get('category', '')}")
    for c in e.get('candidates', []):
        lines.append(f"  {c['id']} | {c['brand']} {c['title'][:40]} | Y{c['price']} | rerank={c['reranker']} | {c['score']}")
    lines.append(f"Prompt first 300 chars: {e['prompt'][:300]}")
    lines.append('---')

with open('audit_report.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('Written to audit_report.txt')
