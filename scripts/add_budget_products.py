#!/usr/bin/env python
"""Add 5 budget digital products (50-500 yuan) to fill the price gap."""
import json
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "ecommerce_agent_dataset" / "2_Digital_Electronics" / "data"

products = [
    {
        "product_id": "p_digital_026",
        "title": "QCY MeloBuds ANC 真无线降噪蓝牙耳机 40dB深度降噪 Hi-Res音质 30小时续航",
        "brand": "QCY",
        "category": "数码电子",
        "sub_category": "真无线耳机",
        "base_price": 199.0,
        "image_path": "2_数码电子/images/p_digital_026.jpg",
        "skus": [
            {"sku_id": "s_p_digital_026_1", "properties": {"颜色": "星空黑"}, "price": 199.0},
            {"sku_id": "s_p_digital_026_2", "properties": {"颜色": "云朵白"}, "price": 199.0},
        ],
        "rag_knowledge": {
            "marketing_description": "QCY MeloBuds ANC 是一款性价比极高的真无线降噪耳机。40dB深度主动降噪，Hi-Res Audio认证音质，搭载12mm大动圈单元，低音浑厚高音清亮。蓝牙5.4连接稳定，游戏模式延迟低至45ms。单次续航6小时，充电盒总续航30小时。IPX5防水防汗，运动无忧。适合学生党、通勤族、预算有限的音乐爱好者。",
            "official_faq": [
                {"question": "降噪效果如何？", "answer": "40dB主动降噪，地铁通勤环境噪音降低明显，日常使用完全够用。"},
                {"question": "续航多久？", "answer": "耳机单次6小时，搭配充电盒总续航30小时，支持快充15分钟使用2小时。"},
                {"question": "适合运动吗？", "answer": "IPX5防水等级，跑步健身出汗不担心，佩戴稳固不易掉落。"},
            ],
            "user_reviews": [
                {"nickname": "学生党小明", "rating": 5, "content": "199元买到40dB降噪太值了，音质比预期好很多，考研党图书馆必备！"},
                {"nickname": "通勤族小李", "rating": 4, "content": "地铁上用降噪效果不错，连接稳定，就是充电盒有点大。"},
                {"nickname": "数码控老王", "rating": 4, "content": "性价比之选，Hi-Res认证在这个价位很少见，推荐预算有限的朋友。"},
                {"nickname": "运动达人", "rating": 5, "content": "跑步戴着不掉的耳机终于找到了！防水也靠谱，出了汗擦擦就好。"},
            ],
        },
    },
    {
        "product_id": "p_digital_027",
        "title": "小米 Redmi Buds 6 真无线蓝牙耳机 半入耳式 AI降噪 长续航 适配小米/苹果/华为",
        "brand": "小米",
        "category": "数码电子",
        "sub_category": "真无线耳机",
        "base_price": 99.0,
        "image_path": "2_数码电子/images/p_digital_027.jpg",
        "skus": [
            {"sku_id": "s_p_digital_027_1", "properties": {"颜色": "白色"}, "price": 99.0},
            {"sku_id": "s_p_digital_027_2", "properties": {"颜色": "黑色"}, "price": 99.0},
        ],
        "rag_knowledge": {
            "marketing_description": "小米Redmi Buds 6是百元级半入耳式真无线耳机标杆。AI通话降噪，半入耳设计久戴不痛。蓝牙5.3快速连接，支持小米/苹果/华为全平台适配。13mm大动圈，低音增强调音，刷抖音看剧音质清晰。单次续航5小时，总续航24小时。Type-C充电接口，性价比极高，适合学生和轻度使用场景。",
            "official_faq": [
                {"question": "苹果手机能用吗？", "answer": "支持！蓝牙5.3协议全平台兼容，iPhone/安卓都能正常使用。"},
                {"question": "戴着舒服吗？", "answer": "半入耳式设计，单耳仅4.2g，长时间佩戴无压迫感，适合办公室全天使用。"},
                {"question": "通话质量怎么样？", "answer": "AI通话降噪，日常电话会议和微信语音清晰无杂音。"},
            ],
            "user_reviews": [
                {"nickname": "米粉小李子", "rating": 5, "content": "99块钱买到小米品质，连接我的红米手机秒配对，音质超出预期！"},
                {"nickname": "学生妹", "rating": 4, "content": "半入耳不痛这个太重要了，图书馆戴一下午没问题，白色颜值也高。"},
                {"nickname": "办公族", "rating": 3, "content": "音质够用，打电话清晰，就是没有降噪有点遗憾，但99元要啥自行车。"},
            ],
        },
    },
    {
        "product_id": "p_digital_028",
        "title": "Anker 安克 20000mAh 大容量充电宝 22.5W快充 PD双向 兼容苹果安卓 可上飞机",
        "brand": "Anker安克",
        "category": "数码电子",
        "sub_category": "移动电源",
        "base_price": 149.0,
        "image_path": "2_数码电子/images/p_digital_028.jpg",
        "skus": [
            {"sku_id": "s_p_digital_028_1", "properties": {"颜色": "黑色"}, "price": 149.0},
            {"sku_id": "s_p_digital_028_2", "properties": {"颜色": "白色"}, "price": 149.0},
        ],
        "rag_knowledge": {
            "marketing_description": "Anker 20000mAh大容量充电宝，22.5W PD快充，30分钟充iPhone至50%。20000mAh可充iPhone约4次，充安卓手机约3次。支持双向快充，自充也快。20000mAh符合航空携带标准（<100Wh），出差旅行可带上飞机。MultiProtect 12重安全保护，Anker全球知名充电品牌品质保障。LED电量显示，Type-C+双USB三口同时充。",
            "official_faq": [
                {"question": "能带上飞机吗？", "answer": "可以！20000mAh / 74Wh < 100Wh民航标准，可随身携带上飞机（不可托运）。"},
                {"question": "充iPhone要多久？", "answer": "22.5W PD快充，iPhone 15从0充到50%约30分钟，充满约1.5小时。"},
                {"question": "能充几次？", "answer": "20000mAh额定容量约12800mAh，可充iPhone约2.5-3次，安卓手机约2次。"},
            ],
            "user_reviews": [
                {"nickname": "出差党老张", "rating": 5, "content": "出差神器！20000mAh充手机+耳机一天都够用，22.5W快充真的快，飞机上也能带。"},
                {"nickname": "旅行爱好者", "rating": 4, "content": "容量大充电快，三口同时充很实用。就是有点重，适合放包里不太适合揣兜。"},
                {"nickname": "学生党", "rating": 5, "content": "149元买Anker品质很划算，宿舍停电时充手机+平板都没问题，自习室必备。"},
            ],
        },
    },
    {
        "product_id": "p_digital_029",
        "title": "倍思 Baseus 65W GaN氮化镓充电器 三口快充 Type-C+USB 兼容苹果安卓笔记本",
        "brand": "倍思",
        "category": "数码电子",
        "sub_category": "充电器/数据线",
        "base_price": 89.0,
        "image_path": "2_数码电子/images/p_digital_029.jpg",
        "skus": [
            {"sku_id": "s_p_digital_029_1", "properties": {"颜色": "白色"}, "price": 89.0},
            {"sku_id": "s_p_digital_029_2", "properties": {"颜色": "黑色"}, "price": 89.0},
        ],
        "rag_knowledge": {
            "marketing_description": "倍思65W GaN氮化镓充电器，三口快充（2×Type-C + 1×USB-A），可同时充手机+平板+耳机。65W大功率支持笔记本充电（MacBook Air/Pro均可）。GaN第三代半导体材料，体积比普通65W充电器小50%，重量仅120g，便于携带。智能功率分配，三口同时充时自动分配45W+20W。兼容PD3.0/QC4.0/PPS等主流快充协议，苹果/华为/小米/三星通用。",
            "official_faq": [
                {"question": "能充笔记本电脑吗？", "answer": "可以！65W PD输出支持MacBook Air/Pro、华为MateBook等轻薄本充电。"},
                {"question": "三口同时充功率怎么分？", "answer": "三口同时使用时，Type-C1输出45W，Type-C2+USB-A共享20W，智能动态分配。"},
                {"question": "发热严重吗？", "answer": "GaN芯片转化效率高发热低，满载65W工作温度约50°C，比传统硅充电器低10°C以上。"},
            ],
            "user_reviews": [
                {"nickname": "极简主义者", "rating": 5, "content": "一个充电器搞定手机+手表+耳机，出差包里少带三个头，GaN的真的小！"},
                {"nickname": "数码玩家", "rating": 4, "content": "65W充笔记本没问题，三口同时用也稳。白色款颜值高但容易脏。"},
                {"nickname": "学生", "rating": 5, "content": "89元买GaN三口快充太值了，宿舍插座少，一个顶三个，强烈推荐！"},
            ],
        },
    },
    {
        "product_id": "p_digital_030",
        "title": "漫步者 Edifier X3s 真无线蓝牙耳机 高通芯片 aptX高清音质 游戏低延迟 IP55防水",
        "brand": "漫步者",
        "category": "数码电子",
        "sub_category": "真无线耳机",
        "base_price": 169.0,
        "image_path": "2_数码电子/images/p_digital_030.jpg",
        "skus": [
            {"sku_id": "s_p_digital_030_1", "properties": {"颜色": "黑色"}, "price": 169.0},
            {"sku_id": "s_p_digital_030_2", "properties": {"颜色": "白色"}, "price": 169.0},
        ],
        "rag_knowledge": {
            "marketing_description": "漫步者Edifier X3s搭载高通QCC3040芯片，支持aptX高清音频解码，音质在同价位领先。蓝牙5.2连接稳定，游戏模式延迟低至60ms，吃鸡王者不卡顿。IP55防水防尘，运动出汗下雨都不怕。单次续航6小时，总续航24小时。Type-C快充，充电15分钟使用2小时。漫步者30年声学积累，品质有保障。",
            "official_faq": [
                {"question": "音质怎么样？", "answer": "aptX高清解码+漫步者调音，人声清晰低音不糊，169元价位音质天花板。"},
                {"question": "打游戏延迟高吗？", "answer": "游戏模式60ms低延迟，王者荣耀/和平精英音画同步，完全够用。"},
                {"question": "防水能游泳吗？", "answer": "IP55防溅水防汗，跑步健身淋雨都没问题，但不建议游泳或泡水。"},
            ],
            "user_reviews": [
                {"nickname": "耳机发烧友", "rating": 5, "content": "漫步者的调音确实有功力，aptX加成听歌细节比普通SBC好太多！"},
                {"nickname": "大学生", "rating": 4, "content": "169元高通芯+aptX，性价比无敌。就是充电盒塑料感强了点，但瑕不掩瑜。"},
                {"nickname": "运动达人", "rating": 5, "content": "IP55防水靠谱，跑了半年步淋过几次雨都没坏，戴着也稳。"},
            ],
        },
    },
]

for p in products:
    fp = DIR / f"{p['product_id']}.json"
    fp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created: {fp.name} - {p['title'][:30]}... | {p['base_price']}")

print(f"\nDone. Added {len(products)} budget digital products.")
