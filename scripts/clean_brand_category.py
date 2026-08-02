#!/usr/bin/env python
"""数据集品牌-品类合理性清洗（生成数据品牌随机分配的修复）。

问题：generate_1000_products.py 生成商品时品牌与子品类随机组合，
产生 "Bose手机" "戴森护垫" "格力锅具" "始祖鸟篮球" 等不合理商品，
演示/检索时暴露真实性问题。

策略：
- 不删商品（保 1000 件规模），按「子品类 → 合理品牌池」校验；
- 品牌不在池内 → 按 product_id 哈希从池内确定性重指派（可复现）；
- 同步替换 brand 字段 + JSON 全文（title/marketing/faq/reviews）中的旧品牌词；
- ASCII 品牌用词边界正则替换防误伤，中文品牌直接替换；
- 带同名图片的商品若品牌合理则天然跳过（避免图文不符）。

用法:
    python scripts/clean_brand_category.py           # dry-run 预览
    python scripts/clean_brand_category.py --apply   # 写回 JSON

清洗后需重建存储：
    python scripts/seed_postgresql.py && python scripts/reindex_all.py --recreate
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "ecommerce_agent_dataset"

# ================================================================
# 子品类 → 合理品牌池（池尽量宽以减少不必要改动；池外即重指派）
# ================================================================

# ---- 美妆护肤：彩妆池 / 护肤池（跨界品牌两池都放）----
_MAKEUP = ["完美日记", "花西子", "橘朵", "毛戈平", "MAC", "YSL", "迪奥", "阿玛尼",
           "纪梵希", "美宝莲", "卡姿兰", "稚优泉", "3CE", "NARS", "Tom Ford", "爱马仕",
           "兰蔻", "雅诗兰黛", "植村秀", "CPB", "黛珂", "资生堂", "unny", "方里",
           "娇兰", "SK-II", "倩碧", "Whoo后", "兰芝", "悦诗风吟", "芙清", "花知晓"]
_SKINCARE = ["兰蔻", "雅诗兰黛", "SK-II", "修丽可", "理肤泉", "薇诺娜", "珀莱雅",
             "欧莱雅", "巴黎欧莱雅", "资生堂", "科颜氏", "倩碧", "悦木之源", "OLAY",
             "玉兰油", "珂润", "雅漾", "自然堂", "百雀羚", "谷雨", "芳珂", "娇韵诗",
             "赫莲娜", "黛珂", "悦诗风吟", "兰芝", "相宜本草", "The Ordinary", "AHC",
             "CPB", "Whoo后", "珊珂", "安热沙", "薇姿", "城野医生", "娇兰", "迪奥",
             "爱马仕", "植村秀", "稚优泉", "花西子", "毛戈平", "完美日记"]
_SUNSCREEN = ["安热沙", "资生堂", "理肤泉", "薇诺娜", "珀莱雅", "巴黎欧莱雅",
              "欧莱雅", "雅漾", "相宜本草", "unny", "赫莲娜", "水宝宝"]

BEAUTY = {
    "口红": _MAKEUP, "唇釉": _MAKEUP, "眼影": _MAKEUP, "眼线": _MAKEUP,
    "眉笔": _MAKEUP, "散粉/蜜粉": _MAKEUP, "蜜粉": _MAKEUP, "气垫": _MAKEUP,
    "粉底液": _MAKEUP, "腮红": _MAKEUP, "高光/修容": _MAKEUP, "隔离/妆前": _MAKEUP,
    "精华": _SKINCARE, "面霜": _SKINCARE, "眼霜": _SKINCARE, "化妆水": _SKINCARE,
    "面膜": _SKINCARE, "洁面": _SKINCARE, "卸妆": _SKINCARE, "喷雾": _SKINCARE,
    "身体护理": _SKINCARE, "防晒": _SUNSCREEN,
    "套装": list(dict.fromkeys(_MAKEUP + _SKINCARE)),
}

# ---- 数码电子 ----
_AUDIO = ["索尼", "Bose", "JBL", "漫步者", "QCY", "森海塞尔", "华为", "小米", "OPPO"]
_PHONE = ["华为", "小米", "OPPO", "vivo", "荣耀", "红米", "一加", "三星", "realme"]
_CHARGE = ["Anker", "Anker安克", "倍思", "小米", "绿联", "罗马仕", "品胜"]
DIGITAL = {
    "手机": _PHONE, "智能手机": _PHONE + ["Apple 苹果", "苹果"],
    "平板电脑": ["华为", "小米", "三星", "联想", "荣耀", "vivo", "Apple 苹果", "苹果"],
    "笔记本电脑": ["联想", "华为", "戴尔", "惠普", "华硕", "小米", "Apple 苹果", "苹果"],
    "真无线耳机": _AUDIO + ["Apple 苹果", "苹果", "vivo", "荣耀"],
    "头戴式耳机": _AUDIO + ["苹果"],
    "蓝牙音箱": ["JBL", "Bose", "索尼", "小米", "漫步者", "哈曼卡顿"],
    "微单相机": ["索尼", "佳能", "尼康", "富士", "松下"],
    "电视": ["TCL", "海信", "小米", "索尼", "三星", "华为", "红米"],
    "显示器": ["戴尔", "TCL", "三星", "AOC", "飞利浦", "华硕", "小米", "海信"],
    "键盘": ["罗技", "雷蛇", "达尔优", "樱桃", "联想", "双飞燕"],
    "鼠标": ["罗技", "雷蛇", "达尔优", "联想", "双飞燕"],
    "路由器": ["TP-LINK", "华为", "小米", "华硕", "腾达", "网件"],
    "智能手表": ["华为", "小米", "OPPO", "荣耀", "佳明", "Apple 苹果", "苹果", "倍思"],
    "智能手环": ["华为", "小米", "OPPO", "荣耀", "三星"],
    "智能门锁": ["小米", "凯迪仕", "德施曼", "华为", "鹿客", "飞利浦"],
    "智能摄像头": ["小米", "萤石", "华为", "360", "TP-LINK", "乔安"],
    "充电宝": _CHARGE, "移动电源": _CHARGE, "充电器": _CHARGE, "充电器/数据线": _CHARGE,
    "台灯": ["小米", "飞利浦", "松下", "欧普", "雷士", "当贝"],
    "投影仪": ["极米", "当贝", "坚果", "爱普生", "飞利浦", "Anker"],
    "无人机": ["大疆", "道通", "哈博森"],
    "游戏机": ["任天堂", "索尼", "微软"],
    "电动牙刷": ["飞利浦", "欧乐B", "usmile", "素士", "小米", "红米", "荣耀"],
    "体脂秤": ["小米", "华为", "云麦", "有品", "香山"],
    "空气净化器": ["小米", "飞利浦", "美的", "352", "霍尼韦尔", "华为"],
}

# ---- 服饰运动 ----
_SPORT_SHOE = ["耐克", "Nike", "阿迪达斯", "Adidas", "李宁", "安踏", "特步", "361度",
               "匹克", "鸿星尔克", "斯凯奇", "New Balance", "美津浓", "亚瑟士", "HOKA",
               "彪马", "锐步", "斐乐", "乔丹"]
_CASUAL_SHOE = ["匡威", "Vans", "回力", "飞跃", "斯凯奇", "斐乐", "耐克", "阿迪达斯"]
_SPORT_WEAR = _SPORT_SHOE + ["优衣库", "迪卡侬", "露露乐蒙", "安德玛"]
_CASUAL_WEAR = ["ZARA", "优衣库", "UR", "ONLY", "Jack Jones", "海澜之家", "森马",
                "以纯", "太平鸟", "GAP"]
_OUTDOOR_WEAR = ["始祖鸟", "北面", "The North Face", "哥伦比亚", "探路者", "骆驼",
                 "凯乐石", "巴塔哥尼亚", "迪卡侬", "萨洛蒙", "迈乐", "波司登"]
CLOTHING = {
    "跑步鞋": _SPORT_SHOE, "篮球鞋": _SPORT_SHOE, "运动鞋": _SPORT_SHOE,
    "板鞋": _CASUAL_SHOE, "帆布鞋": _CASUAL_SHOE,
    "凉鞋": _CASUAL_SHOE + ["斯凯奇", "骆驼"], "拖鞋": _CASUAL_SHOE + ["优衣库"],
    "徒步鞋": _OUTDOOR_WEAR, "户外裤": _OUTDOOR_WEAR, "夹克": _OUTDOOR_WEAR + _CASUAL_WEAR,
    "羽绒服": ["波司登", "优衣库", "北面", "The North Face", "哥伦比亚", "探路者",
              "骆驼", "始祖鸟", "森马", "太平鸟"],
    "卫衣": _SPORT_WEAR + _CASUAL_WEAR, "短袖T恤": _SPORT_WEAR + _CASUAL_WEAR,
    "速干T恤": _SPORT_WEAR + ["迪卡侬", "探路者", "骆驼"],
    "运动裤": _SPORT_WEAR, "运动长裤": _SPORT_WEAR, "运动短裤": _SPORT_WEAR,
    "瑜伽裤": ["露露乐蒙", "Keep", "李宁", "迪卡侬", "安德玛", "耐克"],
    "内衣": ["优衣库", "耐克", "Nike", "安德玛", "彪马", "蕉内", "ubras"],
    "袜子": _SPORT_WEAR + _CASUAL_WEAR,
    "帽子": _SPORT_WEAR + _CASUAL_WEAR + ["北面"],
    "手套": _SPORT_WEAR + _OUTDOOR_WEAR,
    "围巾": _CASUAL_WEAR + ["优衣库", "无印良品"],
    "休闲裤": _CASUAL_WEAR + ["骆驼"], "牛仔裤": _CASUAL_WEAR + ["Levi's"],
    "长袖衬衫": _CASUAL_WEAR, "西装": _CASUAL_WEAR + ["雅戈尔", "海澜之家"],
    "连衣裙": ["ZARA", "优衣库", "UR", "ONLY", "太平鸟", "GAP"],
    "半身裙": ["ZARA", "优衣库", "UR", "ONLY", "太平鸟", "GAP"],
    "背包": ["Osprey", "The North Face", "北面", "哥伦比亚", "骆驼", "迪卡侬",
            "New Balance", "耐克", "小米"],
    "腰带": _CASUAL_WEAR + ["骆驼", "七匹狼"],
}

# ---- 食品生活 ----
_DRINK = ["农夫山泉", "百岁山", "依云", "百事", "可口可乐", "元气森林", "东鹏",
          "红牛", "东方树叶", "三得利", "怡宝"]
_DAIRY = ["伊利", "蒙牛", "光明", "金典", "纯甄", "三元", "君乐宝"]
_SNACK = ["三只松鼠", "百草味", "良品铺子", "洽洽", "旺旺", "乐事", "好丽友",
          "徐福记", "德芙", "费列罗", "奥利奥", "达利园", "王饱饱", "欧扎克", "西麦", "桂格"]
_COFFEE = ["雀巢", "星巴克", "瑞幸", "三顿半", "永璞", "隅田川"]
_STAPLE = ["金龙鱼", "鲁花", "十月稻田", "柴火大院", "燕之坊", "福临门"]
_INSTANT = ["康师傅", "统一", "日清", "今麦郎", "白象", "自嗨锅"]
FOOD = {
    "矿泉水": _DRINK, "碳酸饮料": _DRINK, "果汁": _DRINK + ["汇源", "味全"],
    "功能饮料": ["东鹏", "红牛", "战马", "尖叫", "外星人"],
    "茶饮": ["东方树叶", "元气森林", "三得利", "农夫山泉", "康师傅", "统一"],
    "茶叶": ["立顿", "中茶", "八马", "大益", "小罐茶"],
    "牛奶": _DAIRY, "酸奶": _DAIRY + ["安慕希", "乐纯"],
    "零食": _SNACK, "坚果": _SNACK, "坚果/零食": _SNACK, "果干": _SNACK,
    "海苔": ["波力", "美好时光", "四洲", "百草味", "三只松鼠"],
    "肉干": _SNACK + ["科尔沁", "棒棒娃"],
    "饼干": _SNACK + ["康师傅", "嘉顿"], "糖果": _SNACK + ["阿尔卑斯", "大白兔"],
    "巧克力": ["德芙", "费列罗", "好时", "士力架", "明治", "徐福记"],
    "蛋糕": ["达利园", "好丽友", "盼盼", "桃李", "康师傅"],
    "面包": ["桃李", "盼盼", "达利园", "曼可顿", "宾堡"],
    "麦片": ["桂格", "西麦", "王饱饱", "欧扎克", "卡乐比"],
    "咖啡": _COFFEE,
    "大米": _STAPLE, "面粉": _STAPLE + ["五得利"], "食用油": ["金龙鱼", "鲁花", "福临门", "胡姬花"],
    "方便面": _INSTANT, "方便食品": _INSTANT, "自热火锅": ["自嗨锅", "莫小仙", "海底捞", "小龙坎"],
    "罐头": ["梅林", "甘竹", "林家铺子", "古龙"],
    "蜂蜜": ["百花", "冠生园", "慈生堂"],
    "调味品": ["海天", "李锦记", "厨邦", "千禾", "太太乐"],
    "调味料": ["海天", "李锦记", "厨邦", "千禾", "太太乐", "王守义"],
}

# ---- 家居用品 ----
_COOKWARE = ["双立人", "Zwilling", "WMF", "菲仕乐", "Le Creuset", "Staub", "苏泊尔",
             "爱仕达", "康巴赫", "北鼎", "九阳", "美的"]
_HOME_TEXTILE = ["网易严选", "宜家", "MUJI无印良品", "水星家纺", "罗莱", "富安娜", "博洋"]
_STORAGE = ["宜家", "MUJI无印良品", "网易严选", "乐扣乐扣", "太力", "天马"]
_CUP = ["膳魔师", "虎牌", "象印", "乐扣乐扣", "康宁", "Corelle", "希诺", "富光"]
HOME = {
    "锅具": _COOKWARE, "厨房刀具": ["双立人", "Zwilling", "WMF", "张小泉", "十八子作"],
    "砧板": ["双立人", "张小泉", "苏泊尔", "摩飞", "宜家"],
    "餐具": ["康宁", "Corelle", "WMF", "双立人", "宜家", "MUJI无印良品", "网易严选"],
    "保温杯": _CUP, "水杯": _CUP,
    "床品四件套": _HOME_TEXTILE, "被子": _HOME_TEXTILE, "枕头": _HOME_TEXTILE,
    "毛巾": _HOME_TEXTILE + ["洁丽雅", "金号"], "窗帘": _HOME_TEXTILE,
    "地毯": _HOME_TEXTILE + ["大江"], "地垫": _HOME_TEXTILE + ["大江"],
    "沙发垫": _HOME_TEXTILE,
    "收纳盒": _STORAGE, "置物架": _STORAGE, "挂钩": _STORAGE + ["3M"],
    "衣架": _STORAGE, "晾衣架": _STORAGE + ["好太太", "恋衣"],
    "垃圾桶": _STORAGE + ["拓牛", "佳帮手"],
    "拖鞋": ["MUJI无印良品", "网易严选", "宜家", "朴西", "posee"],
    "台灯": ["欧普", "雷士", "飞利浦", "小米", "松下", "孩视宝"],
    "落地灯": ["欧普", "雷士", "飞利浦", "小米", "宜家"],
    "花瓶": ["宜家", "MUJI无印良品", "网易严选", "野兽派"],
    "香薰": ["野兽派", "观夏", "MUJI无印良品", "网易严选", "祖玛珑"],
}

# ---- 母婴用品 ----
_FEEDING = ["贝亲", "新安怡", "可么多么", "Comotomo", "NUK", "小白熊", "新贝",
            "babycare", "世喜", "布朗博士"]
_BABY_CARE = ["启初", "红色小象", "戴可思", "艾维诺", "Mustela", "妙思乐", "子初",
              "十月结晶", "babycare", "松达"]
_BABY_TRAVEL = ["好孩子", "Britax", "Cybex", "Maxi-Cosi", "Bugaboo", "Stokke", "babycare"]
_BABY_TOY = ["babycare", "费雪", "澳贝", "布鲁可", "好孩子"]
BABY = {
    "奶瓶": _FEEDING, "奶嘴": _FEEDING, "吸奶器": ["美德乐", "新贝", "小白熊", "贝亲", "babycare"],
    "温奶器": ["小白熊", "新贝", "babycare", "贝亲"],
    "儿童水杯": _FEEDING + ["膳魔师", "虎牌"], "儿童餐具": _FEEDING + ["好孩子"],
    "消毒柜": ["小白熊", "新贝", "babycare", "海尔", "美的"],
    "防溢乳垫": ["十月结晶", "子初", "贝亲", "开丽", "babycare"],
    "口水巾": ["全棉时代", "babycare", "贝亲", "大王", "好孩子"],
    "婴儿推车": _BABY_TRAVEL, "安全座椅": _BABY_TRAVEL,
    "婴儿床": ["好孩子", "babycare", "可优比", "蒂爱"],
    "宝宝沐浴露": _BABY_CARE, "婴儿润肤霜": _BABY_CARE,
    "婴儿洗衣液": _BABY_CARE + ["蓝月亮", "威露士"],
    "婴儿湿巾": ["大王", "好奇", "babycare", "全棉时代", "德佑", "子初"],
    "纸尿裤": ["帮宝适", "好奇", "大王", "尤妮佳", "花王", "babycare", "妙思乐"],
    "婴儿玩具": _BABY_TOY, "积木": ["乐高", "布鲁可", "babycare", "费雪"],
    "绘本": ["信谊", "蒲蒲兰", "接力出版社", "尚童"],
    "爬行垫": ["babycare", "曼龙", "帕克伦", "好奇"],
    "婴儿服": ["童泰", "好孩子", "babycare", "全棉时代", "英氏"],
    "孕妇装": ["十月结晶", "全棉时代", "孕味", "添香"],
    "学步鞋": ["基诺浦", "江博士", "卡特兔", "好孩子"],
    "宝宝辅食": ["嘉宝", "小皮", "英氏", "秋田满满", "艾维诺"],
}

# ---- 运动户外 ----
_OUTDOOR_GEAR = ["牧高笛", "探路者", "骆驼", "凯乐石", "哥伦比亚", "迪卡侬", "北面", "挪客"]
_FITNESS = ["迪卡侬", "李宁", "Keep", "悦步", "斯诺德"]
SPORTS = {
    "篮球": ["斯伯丁", "李宁", "威尔胜", "摩腾"],
    "足球": ["Adidas", "Nike", "世达", "摩腾", "李宁"],
    "网球拍": ["尤尼克斯", "威尔胜", "海德", "百保力"],
    "羽毛球拍": ["尤尼克斯", "李宁", "凯胜", "胜利"],
    "乒乓球拍": ["红双喜", "蝴蝶", "斯帝卡", "银河"],
    "帐篷": _OUTDOOR_GEAR, "睡袋": _OUTDOOR_GEAR, "登山杖": _OUTDOOR_GEAR,
    "户外背包": _OUTDOOR_GEAR + ["Osprey", "始祖鸟"],
    "登山鞋": _OUTDOOR_GEAR + ["始祖鸟", "萨洛蒙", "迈乐", "斯凯奇"],
    "冲锋衣": _OUTDOOR_GEAR + ["始祖鸟", "巴塔哥尼亚", "安踏", "李宁", "鸿星尔克"],
    "速干衣": _OUTDOOR_GEAR + ["始祖鸟", "巴塔哥尼亚", "安德玛", "李宁"],
    "骑行头盔": ["迪卡侬", "洛克兄弟", "闪电", "捷安特"],
    "骑行服": ["迪卡侬", "洛克兄弟", "捷安特", "森地客"],
    "哑铃": _FITNESS + ["海德"], "跳绳": _FITNESS + ["红双喜"],
    "拉力器": _FITNESS, "瑜伽垫": _FITNESS + ["露露乐蒙", "奥义"],
    "瑜伽裤": ["露露乐蒙", "Keep", "李宁", "迪卡侬", "暴走的萝莉"],
    "泳衣": ["速比涛", "英发", "李宁", "迪卡侬", "arena", "范德安"],
    "游泳镜": ["速比涛", "英发", "李宁", "迪卡侬", "arena"],
    "轮滑鞋": ["迪卡侬", "米高", "乐秀", "宝狮莱"],
    "滑板": ["迪卡侬", "沸点", "DBH", "Element"],
    "跑步鞋": _SPORT_SHOE + ["萨洛蒙", "HOKA"],
    "运动内衣": ["露露乐蒙", "Keep", "李宁", "迪卡侬", "安德玛", "耐克", "蕉内"],
}

# ---- 个护清洁 ----
_HAIR = ["海飞丝", "潘婷", "飘柔", "沙宣", "施华蔻", "多芬", "清扬", "欧莱雅"]
_ORAL = ["高露洁", "佳洁士", "黑人", "舒适达", "狮王", "云南白药", "冷酸灵"]
_APPLIANCE = ["飞利浦", "松下", "戴森", "博朗", "素士", "罗曼", "雷明顿", "Wahl",
              "直白", "飞科", "徕芬"]
_LAUNDRY = ["蓝月亮", "立白", "汰渍", "碧浪", "奥妙", "超能", "威露士", "滴露", "金纺"]
_HOUSE_CLEAN = ["威猛先生", "滴露", "威露士", "蓝月亮", "立白", "花王", "妙管家"]
PERSONAL = {
    "洗发水": _HAIR, "护发素": _HAIR, "柔顺剂": ["金纺", "蓝月亮", "立白", "奥妙", "当妮"],
    "牙膏": _ORAL, "牙刷": _ORAL + ["usmile"], "漱口水": _ORAL + ["李施德林", "参半"],
    "吹风机": _APPLIANCE, "卷发棒": _APPLIANCE, "直发器": _APPLIANCE,
    "剃须刀": ["飞利浦", "松下", "博朗", "飞科", "吉列", "小米"],
    "脱毛仪": ["Ulike", "飞利浦", "博朗", "慕金", "JOVS"],
    "卫生巾": ["苏菲", "护舒宝", "高洁丝", "七度空间", "ABC", "自由点"],
    "护垫": ["苏菲", "护舒宝", "高洁丝", "七度空间", "ABC"],
    "沐浴露": ["舒肤佳", "多芬", "六神", "力士", "狮王", "阿道夫"],
    "身体乳": ["凡士林", "多芬", "妮维雅", "百雀羚", "OLAY", "六神"],
    "洗手液": ["舒肤佳", "蓝月亮", "威露士", "滴露", "六神", "狮王"],
    "洗衣液": _LAUNDRY, "衣物除菌": ["滴露", "威露士", "蓝月亮", "立白"],
    "消毒液": ["滴露", "威露士", "蓝月亮", "84消毒液", "利尔康"],
    "除菌喷雾": ["滴露", "威露士", "花王", "立白"],
    "厨房清洁": _HOUSE_CLEAN, "玻璃清洁": _HOUSE_CLEAN, "地板清洁": _HOUSE_CLEAN,
    "马桶清洁": _HOUSE_CLEAN + ["洁厕灵", "威猛先生"],
}

POOLS = {
    "1_美妆护肤": BEAUTY, "2_数码电子": DIGITAL, "3_服饰运动": CLOTHING,
    "4_食品生活": FOOD, "5_家居用品": HOME, "6_母婴用品": BABY,
    "7_运动户外": SPORTS, "8_个护清洁": PERSONAL,
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def _brand_ok(brand: str, pool: list[str]) -> bool:
    """品牌在池内（宽松匹配：归一化后相等/包含均算合理）。"""
    b = _norm(brand)
    if not b:
        return False
    for p in pool:
        pn = _norm(p)
        if b == pn or pn in b or b in pn:
            return True
    return False


def _pick_brand(product_id: str, pool: list[str], old_brand: str) -> str:
    """按 product_id 哈希确定性选新品牌（可复现），尽量避开与旧品牌同名。"""
    h = int(hashlib.md5(product_id.encode()).hexdigest(), 16)
    for i in range(len(pool)):
        cand = pool[(h + i) % len(pool)]
        if _norm(cand) != _norm(old_brand):
            return cand
    return pool[h % len(pool)]


def _replace_brand_text(text: str, old: str, new: str) -> str:
    """全文替换品牌词：ASCII 品牌用词边界防误伤，中文品牌直接替换。"""
    if not old:
        return text
    if re.fullmatch(r"[\x00-\x7f]+", old):
        return re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])", new, text)
    return text.replace(old, new)


def clean(apply: bool) -> None:
    changed, kept, no_pool = [], 0, []
    for cat, pools in POOLS.items():
        data_dir = ROOT / cat / "data"
        if not data_dir.is_dir():
            continue
        for fp in sorted(data_dir.glob("*.json")):
            d = json.loads(fp.read_text(encoding="utf-8"))
            sub = d.get("sub_category", "")
            pool = pools.get(sub)
            if pool is None:
                no_pool.append(f"{cat}/{sub} ({d.get('product_id')})")
                continue
            brand = d.get("brand", "")
            if _brand_ok(brand, pool):
                kept += 1
                continue
            new_brand = _pick_brand(d.get("product_id", fp.stem), pool, brand)
            changed.append((d.get("product_id"), sub, brand, new_brand))
            if apply:
                raw = fp.read_text(encoding="utf-8")
                obj = json.loads(_replace_brand_text(raw, brand, new_brand))
                obj["brand"] = new_brand
                fp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")

    print(f"合理保留: {kept} | 待重指派: {len(changed)} | 无池子品类: {len(set(no_pool))}")
    if no_pool:
        print("\n[缺池子的子品类 — 需补映射]")
        for s in sorted(set(no_pool)):
            print(" ", s)
    print("\n[重指派明细（前 60 条）]")
    for pid, sub, old, new in changed[:60]:
        print(f"  {pid} [{sub}] {old} -> {new}")
    if len(changed) > 60:
        print(f"  ... 共 {len(changed)} 条")
    if apply:
        print("\n✅ 已写回 JSON。请重建存储：")
        print("  python scripts/seed_postgresql.py && python scripts/reindex_all.py --recreate")
    else:
        print("\n(dry-run，未写回；--apply 生效)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写回 JSON（默认 dry-run）")
    args = ap.parse_args()
    clean(apply=args.apply)
