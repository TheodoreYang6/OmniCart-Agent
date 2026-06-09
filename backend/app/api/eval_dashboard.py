"""Evaluation Dashboard — 交互式 HTML 评测面板 (Chart.js)"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniCart Agent — Evaluation Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.header{background:#1e293b;padding:20px 32px;border-bottom:1px solid #334155}
.header h1{font-size:24px;color:#38bdf8}
.header span{color:#94a3b8;font-size:14px}
.container{max-width:1400px;margin:0 auto;padding:24px}
.toolbar{display:flex;gap:12px;margin-bottom:24px;align-items:center}
.btn{padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;transition:all .2s}
.btn-primary{background:#38bdf8;color:#0f172a}
.btn-primary:hover{background:#7dd3fc}
.btn-secondary{background:#334155;color:#e2e8f0}
.btn-secondary:hover{background:#475569}
.btn:disabled{opacity:.5;cursor:not-allowed}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:24px}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card-label{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px}
.card-value{font-size:32px;font-weight:700;margin:8px 0}
.card-sub{font-size:13px;color:#64748b}
.green{color:#4ade80}
.red{color:#f87171}
.yellow{color:#fbbf24}
.blue{color:#38bdf8}
.charts{display:grid;grid-template-columns:2fr 1fr;gap:24px;margin-bottom:24px}
.chart-box{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.chart-box h3{font-size:16px;margin-bottom:16px;color:#cbd5e1}
.chart-box canvas{max-height:350px}
.table-box{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155;overflow-x:auto}
.table-box h3{font-size:16px;margin-bottom:16px;color:#cbd5e1}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 12px;border-bottom:2px solid #334155;font-size:12px;color:#94a3b8;text-transform:uppercase}
td{padding:10px 12px;border-bottom:1px solid #1e293b;font-size:14px}
tr:hover{background:#0f172a}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.badge-pass{background:#065f46;color:#4ade80}
.badge-fail{background:#7f1d1d;color:#f87171}
.loading{text-align:center;padding:60px;color:#64748b;font-size:16px}
.footer{text-align:center;padding:24px;color:#475569;font-size:12px}
.history{margin-top:24px}
</style>
</head>
<body>
<div class="header">
    <h1>OmniCart Agent <span>Evaluation Dashboard</span></h1>
</div>
<div class="container">
    <div class="toolbar">
        <button class="btn btn-primary" onclick="runEval('default')" id="btn-run">▶ 运行评测</button>
        <button class="btn btn-secondary" onclick="runEval('chunked')" id="btn-chunked">🧩 分块评测</button>
        <button class="btn btn-secondary" onclick="loadHistory()">📋 刷新历史</button>
        <select id="aggregation" style="padding:10px;border-radius:8px;background:#334155;color:#e2e8f0;border:none">
            <option value="max_score">聚合: Max Score</option>
            <option value="weighted">聚合: Weighted</option>
        </select>
        <span id="status" style="color:#64748b;font-size:14px"></span>
    </div>

    <div class="cards">
        <div class="card">
            <div class="card-label">通过率</div>
            <div class="card-value green" id="pass-rate">--</div>
            <div class="card-sub" id="pass-detail"></div>
        </div>
        <div class="card">
            <div class="card-label">平均延迟</div>
            <div class="card-value blue" id="avg-latency">--</div>
            <div class="card-sub" id="p95-latency"></div>
        </div>
        <div class="card">
            <div class="card-label">品类准确率</div>
            <div class="card-value yellow" id="cat-acc">--</div>
            <div class="card-sub">Expected vs Actual</div>
        </div>
        <div class="card">
            <div class="card-label">平均商品数</div>
            <div class="card-value" id="avg-prod" style="color:#c084fc">--</div>
            <div class="card-sub">per query</div>
        </div>
        <div class="card">
            <div class="card-label">Recall@10</div>
            <div class="card-value blue" id="recall-10">--</div>
            <div class="card-sub">Avg relevant found</div>
        </div>
        <div class="card">
            <div class="card-label">MRR</div>
            <div class="card-value yellow" id="mrr">--</div>
            <div class="card-sub">Mean Reciprocal Rank</div>
        </div>
        <div class="card">
            <div class="card-label">NDCG@10</div>
            <div class="card-value green" id="ndcg">--</div>
            <div class="card-sub">Normalized DCG</div>
        </div>
    </div>

    <div class="charts">
        <div class="chart-box">
            <h3>Per-Query Results</h3>
            <canvas id="chart-query"></canvas>
        </div>
        <div class="chart-box">
            <h3>Category Accuracy</h3>
            <canvas id="chart-category"></canvas>
        </div>
    </div>

    <div class="table-box">
        <h3>Query Details</h3>
        <table><thead><tr>
            <th>Query</th><th>Category</th><th>Match</th><th>Products</th><th>Latency</th><th>Recall@10</th><th>MRR</th><th>Status</th>
        </tr></thead><tbody id="table-body"><tr><td colspan="8" class="loading">点击"运行评测"开始</td></tr></tbody></table>
    </div>

    <div class="history table-box">
        <h3>Historical Runs</h3>
        <table><thead><tr>
            <th>Run ID</th><th>Time</th><th>Pass Rate</th><th>Avg Latency</th><th>Cat Accuracy</th><th>Products</th>
        </tr></thead><tbody id="history-body"><tr><td colspan="6" class="loading">Loading...</td></tr></tbody></table>
    </div>
</div>
<div class="footer">OmniCart Agent · ByteDance Agent Challenge · V2</div>

<script>
let queryChart, catChart;

function initCharts() {
    const ctx1 = document.getElementById('chart-query').getContext('2d');
    queryChart = new Chart(ctx1, {
        type: 'bar',
        data: {labels:[],datasets:[
            {label:'Latency (ms)',data:[],backgroundColor:'#38bdf8',yAxisID:'y'},
            {label:'Products Found',data:[],backgroundColor:'#4ade80',yAxisID:'y1'}
        ]},
        options:{
            responsive:true,
            scales:{
                y:{type:'linear',position:'left',title:{display:true,text:'Latency (ms)'},grid:{color:'#334155'}},
                y1:{type:'linear',position:'right',title:{display:true,text:'Products'},grid:{display:false}}
            },
            plugins:{legend:{labels:{color:'#e2e8f0'}}}
        }
    });

    const ctx2 = document.getElementById('chart-category').getContext('2d');
    catChart = new Chart(ctx2, {
        type: 'doughnut',
        data:{labels:[],datasets:[{data:[],backgroundColor:['#38bdf8','#4ade80','#fbbf24','#f87171']}]},
        options:{plugins:{legend:{labels:{color:'#e2e8f0'}}}}
    });
}

async function runEval(method) {
    const btn = document.getElementById(method === 'chunked' ? 'btn-chunked' : 'btn-run');
    const otherBtn = document.getElementById(method === 'chunked' ? 'btn-run' : 'btn-chunked');
    const status = document.getElementById('status');
    btn.disabled = true; otherBtn.disabled = true;
    btn.textContent = '⏳ Running...';
    const agg = document.getElementById('aggregation').value;
    status.textContent = 'Evaluating golden queries (' + method + ', ' + agg + ')...';

    try {
        const url = '/api/eval/run?method=' + method + '&aggregation=' + agg;
        const resp = await fetch(url, {method:'POST'});
        const data = await resp.json();
        renderResults(data);
        status.textContent = 'Done [' + method + ']: ' + data.run_id;
        await loadHistory();
    } catch(e) {
        status.textContent = 'Error: ' + e.message;
    }
    btn.disabled = false; otherBtn.disabled = false;
    btn.textContent = method === 'chunked' ? '🧩 分块评测' : '▶ 运行评测';
}

function renderResults(data) {
    document.getElementById('pass-rate').textContent = (data.pass_rate*100).toFixed(0) + '%';
    document.getElementById('pass-detail').textContent = data.passed + '/' + data.total + ' passed';
    document.getElementById('avg-latency').textContent = data.avg_latency_ms + 'ms';
    document.getElementById('p95-latency').textContent = 'P95: ' + (data.p95_latency_ms||0) + 'ms';
    document.getElementById('cat-acc').textContent = (data.category_accuracy*100).toFixed(0) + '%';
    document.getElementById('avg-prod').textContent = data.avg_products;
    document.getElementById('recall-10').textContent = data.avg_recall_at_10 != null ? (data.avg_recall_at_10*100).toFixed(0)+'%' : 'N/A';
    document.getElementById('mrr').textContent = data.avg_mrr != null ? data.avg_mrr.toFixed(3) : 'N/A';
    document.getElementById('ndcg').textContent = data.avg_ndcg_at_10 != null ? data.avg_ndcg_at_10.toFixed(3) : 'N/A';

    const details = data.details || [];
    const shortQuery = q => q.length > 18 ? q.slice(0,16)+'...' : q;
    queryChart.data.labels = details.map(d => shortQuery(d.query));
    queryChart.data.datasets[0].data = details.map(d => d.latency_ms || 0);
    queryChart.data.datasets[1].data = details.map(d => d.product_count || 0);
    queryChart.update();

    const cats = {};
    details.forEach(d => {
        const c = d.expected_category || 'unknown';
        cats[c] = (cats[c]||0) + 1;
    });
    catChart.data.labels = Object.keys(cats);
    catChart.data.datasets[0].data = Object.values(cats);
    catChart.update();

    const tbody = document.getElementById('table-body');
    tbody.innerHTML = details.map(d => `
        <tr>
            <td title="${d.query}">${shortQuery(d.query)}</td>
            <td>${d.expected_category||'--'}</td>
            <td>${d.category_match?'✅':'❌'}</td>
            <td>${d.product_count||0}</td>
            <td>${d.latency_ms||0}ms</td>
            <td>${d.recall_at_10 != null ? (d.recall_at_10*100).toFixed(0)+'%' : '--'}</td>
            <td>${d.mrr != null ? d.mrr.toFixed(3) : '--'}</td>
            <td><span class="badge ${d.passed?'badge-pass':'badge-fail'}">${d.passed?'PASS':'FAIL'}</span></td>
        </tr>
    `).join('');
}

async function loadHistory() {
    try {
        const resp = await fetch('/api/eval/results?limit=20');
        const data = await resp.json();
        const tbody = document.getElementById('history-body');
        if (!data.runs.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No runs yet</td></tr>';
            return;
        }
        tbody.innerHTML = data.runs.map(r => `
            <tr>
                <td><a href="/api/eval/results/${r.run_id}" target="_blank" style="color:#38bdf8">${r.run_id}</a></td>
                <td>${(r.timestamp||'').slice(0,19)}</td>
                <td style="color:#4ade80">${(r.pass_rate*100).toFixed(0)}%</td>
                <td>${r.avg_latency_ms}ms</td>
                <td>${(r.category_accuracy*100).toFixed(0)}%</td>
                <td>${r.avg_products}</td>
            </tr>
        `).join('');
    } catch(e) {}
}

initCharts();
loadHistory();
</script>
</body>
</html>"""


@router.get("/eval", response_class=HTMLResponse)
async def eval_dashboard():
    """评测仪表盘主页"""
    return HTMLResponse(DASHBOARD_HTML)
