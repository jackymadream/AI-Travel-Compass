#!/usr/bin/env python3
"""
Enrich countries_phase6.json with specialty interest tags and description cues
for better semantic search coverage. Run from repo root, then seed + embed.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "countries_phase6.json"

# iso -> { country_tags_add, city_slug -> tags_add, description_en_extra }
ENRICH: dict[str, dict] = {
    "JP": {
        "country_tags": ["anime", "pop-culture", "temples", "onsen"],
        "cities": {
            "tokyo": {
                "tags": ["anime", "manga", "pop-culture", "nightlife", "urban"],
                "en": " Tokyo is a global hub for anime, manga, and pop culture—from Akihabara to themed cafés and nightlife districts.",
                "zh-HK": " 東京是動漫與流行文化重鎮，秋葉原、主題咖啡與夜生活街區聞名。",
                "ja": " 東京はアニメ・マンガ・ポップカルチャーの拠点で、秋葉原やテーマカフェ、夜の街が充実しています。",
            },
            "kyoto": {
                "tags": ["temples", "culture", "onsen"],
                "en": " Kyoto offers temple pilgrimages, traditional streets, and nearby onsen escapes.",
                "zh-HK": " 京都以神社佛寺巡禮、古街與近郊溫泉見長。",
                "ja": " 京都は寺院巡り、古い町並み、近郊の温泉が魅力です。",
            },
            "osaka": {
                "tags": ["street-food", "food", "nightlife"],
                "en": " Osaka is famous for street food, lively nightlife, and approachable urban culture.",
                "zh-HK": " 大阪以街頭美食、熱鬧夜生活與親和都會文化聞名。",
                "ja": " 大阪は屋台グルメ、活気ある夜、親しみやすい都市文化で知られます。",
            },
        },
        "country_en": " Fans also chase anime and manga culture, onsen weekends, and temple towns beyond the big cities.",
        "country_zh": " 旅客亦可追尋動漫文化、溫泉假期與大城市以外的古寺小鎮。",
        "country_ja": " アニメ・マンガ文化、温泉、大都市以外の寺社巡りも人気です。",
    },
    "KR": {
        "country_tags": ["k-pop", "pop-culture", "street-food", "nightlife"],
        "cities": {
            "seoul": {
                "tags": ["k-pop", "pop-culture", "nightlife", "street-food", "urban"],
                "en": " Seoul pulses with K-pop, nightlife, and street-food alleys across Hongdae and Gangnam.",
                "zh-HK": " 首爾匯聚 K-pop、夜生活與弘大、江南一帶街頭美食。",
                "ja": " ソウルはK-POP、ナイトライフ、弘大や江南の屋台グルメが魅力です。",
            },
            "busan": {
                "tags": ["beach", "street-food", "nightlife"],
                "en": " Busan mixes beaches, seafood markets, and coastal nightlife.",
                "zh-HK": " 釜山結合海灘、海鮮市場與海濱夜生活。",
                "ja": " 釜山はビーチ、海鮮市場、海辺の夜が楽しめます。",
            },
        },
        "country_en": " South Korea stands out for K-pop, youth pop culture, and dense street-food scenes.",
        "country_zh": " 韓國以 K-pop、年輕流行文化與密集街頭美食見稱。",
        "country_ja": " 韓国はK-POP、若者文化、屋台グルメで際立ちます。",
    },
    "IS": {
        "country_tags": ["northern-lights", "nature", "adventure"],
        "cities": {
            "reykjavik": {
                "tags": ["northern-lights", "nature", "wellness"],
                "en": " Reykjavik is a base for northern lights hunts, hot pools, and wild nature day trips.",
                "zh-HK": " 雷克雅未克是追極光、溫泉與大自然日遊的基地。",
                "ja": " レイキャビクはオーロラ、温泉、自然デイトリップの拠点です。",
            },
            "vik": {
                "tags": ["northern-lights", "nature", "adventure"],
                "en": " Vík sits amid black-sand beaches and winter aurora-friendly skies.",
                "zh-HK": " 維克周圍是黑沙灘與適合冬季極光的天空。",
                "ja": " ヴィークは黒い砂浜と冬のオーロラ観測に適した空に囲まれます。",
            },
        },
        "country_en": " Iceland is a premier destination for northern lights, glaciers, and dramatic nature.",
        "country_zh": " 冰島是追極光、冰川與壯麗自然的首選。",
        "country_ja": " アイスランドはオーロラ、氷河、壮大な自然の定番です。",
    },
    "NO": {
        "country_tags": ["northern-lights", "hiking", "nature", "scenic"],
        "cities": {
            "oslo": {
                "tags": ["culture", "museums", "nature"],
                "en": " Oslo pairs museums and design with easy access to fjord and forest trails.",
                "zh-HK": " 奧斯陸結合博物館、設計，並方便前往峽灣與山林步道。",
                "ja": " オスロは美術館・デザインとフィヨルドや森のトレイルが近い街です。",
            },
            "bergen": {
                "tags": ["hiking", "scenic", "northern-lights"],
                "en": " Bergen is a gateway to fjord hiking and winter aurora trips further north.",
                "zh-HK": " 卑爾根是峽灣健行與更北極光行程的門戶。",
                "ja": " ベルゲンはフィヨルドハイクや北へのオーロラ旅の玄関口です。",
            },
        },
        "country_en": " Norway shines for fjord hiking, scenic railways, and northern lights in winter.",
        "country_zh": " 挪威以峽灣健行、風景鐵路與冬季極光著稱。",
        "country_ja": " ノルウェーはフィヨルドハイク、絶景鉄道、冬のオーロラが魅力です。",
    },
    "FI": {
        "country_tags": ["northern-lights", "nature", "wellness"],
        "cities": {
            "helsinki": {
                "tags": ["design", "culture", "urban"],
                "en": " Helsinki offers design culture, saunas, and Baltic waterfront walks.",
                "zh-HK": " 赫爾辛基以設計文化、桑拿與波羅的海濱步行見長。",
                "ja": " ヘルシンキはデザイン、サウナ、バルト海沿いの散策が楽しめます。",
            },
            "rovaniemi": {
                "tags": ["northern-lights", "nature", "adventure"],
                "en": " Rovaniemi is a Lapland base for northern lights and Arctic winter experiences.",
                "zh-HK": " 羅瓦涅米是拉普蘭追極光與北極冬季體驗的基地。",
                "ja": " ロヴァニエミはラップランドのオーロラと北極の冬体験の拠点です。",
            },
        },
        "country_en": " Finland is ideal for northern lights, sauna culture, and quiet nature escapes.",
        "country_zh": " 芬蘭適合追極光、桑拿文化與寧靜自然假期。",
        "country_ja": " フィンランドはオーロラ、サウナ、静かな自然に最適です。",
    },
    "CH": {
        "country_tags": ["hiking", "skiing", "mountains", "scenic"],
        "cities": {
            "zurich": {
                "tags": ["urban", "culture", "scenic"],
                "en": " Zurich mixes lake promenades with quick access to Alpine day trips.",
                "zh-HK": " 蘇黎世結合湖畔步道，並方便前往阿爾卑斯日遊。",
                "ja": " チューリッヒは湖畔散策とアルプス日帰りがしやすい街です。",
            },
            "interlaken": {
                "tags": ["hiking", "adventure", "mountains"],
                "en": " Interlaken is a hub for Alpine hiking, paragliding, and mountain railways.",
                "zh-HK": " 因特拉肯是阿爾卑斯健行、滑翔傘與登山鐵路樞紐。",
                "ja": " インターラーケンはアルプスハイク、パラグライダー、登山鉄道の拠点です。",
            },
            "geneva": {
                "tags": ["culture", "urban", "scenic"],
                "en": " Geneva offers lakeside walks and a cosmopolitan cultural scene.",
                "zh-HK": " 日內瓦提供湖畔散步與國際化文化氛圍。",
                "ja": " ジュネーブは湖畔散歩と国際的な文化が楽しめます。",
            },
        },
        "country_en": " Switzerland is built for Alpine hiking, skiing, and mountain scenery.",
        "country_zh": " 瑞士以阿爾卑斯健行、滑雪與山景聞名。",
        "country_ja": " スイスはアルプスハイク、スキー、山岳風景の定番です。",
    },
    "NZ": {
        "country_tags": ["hiking", "adventure", "nature", "scenic"],
        "cities": {
            "auckland": {
                "tags": ["urban", "nature", "islands"],
                "en": " Auckland spreads across harbors with island day trips and city hiking.",
                "zh-HK": " 奧克蘭跨港而立，適合島嶼日遊與城市健行。",
                "ja": " オークランドは湾に広がり、島日帰りや都市ハイキングに向きます。",
            },
            "queenstown": {
                "tags": ["adventure", "hiking", "skiing"],
                "en": " Queenstown is New Zealand’s adventure capital—hiking, skiing, and adrenaline sports.",
                "zh-HK": " 皇后鎮是紐西蘭冒險之都，健行、滑雪與極限運動齊全。",
                "ja": " クイーンズタウンはハイキング、スキー、アドベンチャーの聖地です。",
            },
            "wellington": {
                "tags": ["culture", "urban", "food"],
                "en": " Wellington packs craft culture, cafés, and windy coastal walks.",
                "zh-HK": " 威靈頓充滿文創、咖啡與海岸步行。",
                "ja": " ウェリントンはクラフト文化、カフェ、海岸散歩が魅力です。",
            },
        },
        "country_en": " New Zealand rewards hikers and adventure travelers with epic trails and scenery.",
        "country_zh": " 紐西蘭適合健行與冒險旅客，步道與風景壯麗。",
        "country_ja": " ニュージーランドはトレイルと絶景のアドベンチャー向けです。",
    },
    "ES": {
        "country_tags": ["food", "wine", "beach", "festivals"],
        "cities": {
            "barcelona": {
                "tags": ["architecture", "beach", "food", "nightlife"],
                "en": " Barcelona is known for Gaudí architecture, tapas, beaches, and nightlife.",
                "zh-HK": " 巴塞隆拿以高第建築、tapa、海灘與夜生活聞名。",
                "ja": " バルセロナはガウディ建築、タパス、ビーチ、夜遊びで知られます。",
            },
            "madrid": {
                "tags": ["museums", "food", "nightlife", "culture"],
                "en": " Madrid centers on museums, late-night dining, and lively plazas.",
                "zh-HK": " 馬德里以博物館、深夜用餐與熱鬧廣場為核心。",
                "ja": " マドリードは美術館、夜遅い食事、活気ある広場が中心です。",
            },
            "seville": {
                "tags": ["history", "festivals", "food", "culture"],
                "en": " Seville shines for historic quarters, flamenco, and Andalusian festivals.",
                "zh-HK": " 塞維利亞以古城區、佛朗明哥與安達盧西亞節慶著稱。",
                "ja": " セビリアは旧市街、フラメンコ、アンダルシアの祭りが魅力です。",
            },
        },
        "country_en": " Spain delivers tapas and wine culture, beaches, and regional festivals.",
        "country_zh": " 西班牙提供 tapa 與葡萄酒文化、海灘與地方節慶。",
        "country_ja": " スペインはタパスとワイン、ビーチ、地方の祭りが充実です。",
    },
    "IT": {
        "country_tags": ["food", "wine", "romance", "history", "art"],
        "cities": {
            "rome": {
                "tags": ["history", "museums", "food"],
                "en": " Rome layers ancient ruins, Vatican museums, and trattoria food culture.",
                "zh-HK": " 羅馬疊加古蹟、梵蒂岡博物館與義式小館飲食文化。",
                "ja": " ローマは古代遺跡、バチカンの美術館、トラットリア文化が重なります。",
            },
            "florence": {
                "tags": ["art", "museums", "wine", "romance"],
                "en": " Florence is an art and Renaissance capital with Tuscan wine day trips.",
                "zh-HK": " 佛羅倫斯是文藝復興藝術之都，可日遊托斯卡尼酒莊。",
                "ja": " フィレンツェはルネサンス芸術の都で、トスカーナのワイン日帰りも人気です。",
            },
            "venice": {
                "tags": ["romance", "culture", "architecture"],
                "en": " Venice is iconic for canals, lagoon islands, and romantic walks.",
                "zh-HK": " 威尼斯以運河、潟湖島嶼與浪漫步行聞名。",
                "ja": " ヴェネツィアは運河、ラグーンの島、ロマンチックな散歩が象徴です。",
            },
        },
        "country_en": " Italy pairs world-class food and wine with art cities and romance.",
        "country_zh": " 意大利結合頂級飲食美酒、藝術之城與浪漫氛圍。",
        "country_ja": " イタリアは食とワイン、芸術都市、ロマンスが揃います。",
    },
    "FR": {
        "country_tags": ["food", "wine", "romance", "museums", "culture"],
        "cities": {
            "paris": {
                "tags": ["museums", "romance", "food", "architecture"],
                "en": " Paris is defined by museums, café culture, wine bars, and romantic boulevards.",
                "zh-HK": " 巴黎以博物館、咖啡文化、葡萄酒吧與浪漫大道為特色。",
                "ja": " パリは美術館、カフェ文化、ワインバー、ロマンチックな大通りが象徴です。",
            },
            "lyon": {
                "tags": ["food", "wine", "culture"],
                "en": " Lyon is France’s gastronomic capital with wine country nearby.",
                "zh-HK": " 里昂是法國美食之都，鄰近葡萄酒產區。",
                "ja": " リヨンは美食の都で、近くにワイン産地もあります。",
            },
            "nice": {
                "tags": ["beach", "romance", "food"],
                "en": " Nice brings Mediterranean promenades, markets, and Provençal light.",
                "zh-HK": " 尼斯有地中海長廊、市集與普羅旺斯陽光。",
                "ja": " ニースは地中海の遊歩道、市場、プロヴァンスの光が魅力です。",
            },
        },
        "country_en": " France is synonymous with cuisine, wine, museums, and romantic city breaks.",
        "country_zh": " 法國代表美食、葡萄酒、博物館與浪漫短遊。",
        "country_ja": " フランスは食、ワイン、美術館、ロマンチックな都市旅の代名詞です。",
    },
    "TH": {
        "country_tags": ["street-food", "temples", "beach", "nightlife"],
        "cities": {
            "bangkok": {
                "tags": ["street-food", "temples", "nightlife", "urban"],
                "en": " Bangkok is legendary for street food, temples, and nightlife.",
                "zh-HK": " 曼谷以街頭美食、寺廟與夜生活聞名。",
                "ja": " バンコクは屋台グルメ、寺院、ナイトライフで有名です。",
            },
            "chiang-mai": {
                "tags": ["temples", "culture", "street-food", "nature"],
                "en": " Chiang Mai offers temple circuits, night markets, and mountain escapes.",
                "zh-HK": " 清邁提供寺廟巡禮、夜市與山林假期。",
                "ja": " チェンマイは寺院巡り、ナイトマーケット、山への退避が魅力です。",
            },
            "phuket": {
                "tags": ["beach", "diving", "nightlife"],
                "en": " Phuket is a beach and diving base with island boat days.",
                "zh-HK": " 普吉是海灘與潛水基地，適合跳島。",
                "ja": " プーケットはビーチとダイビング、島 Hopping の拠点です。",
            },
        },
        "country_en": " Thailand balances street food, temples, beaches, and island diving.",
        "country_zh": " 泰國兼具街頭美食、寺廟、海灘與島嶼潛水。",
        "country_ja": " タイは屋台、寺院、ビーチ、島ダイビングが揃います。",
    },
    "VN": {
        "country_tags": ["street-food", "culture", "nature", "history"],
        "cities": {
            "hanoi": {
                "tags": ["street-food", "culture", "history"],
                "en": " Hanoi is famous for street-food alleys, old quarter walks, and cafés.",
                "zh-HK": " 河內以街頭小巷美食、古城步行與咖啡聞名。",
                "ja": " ハノイは屋台横丁、旧市街散策、カフェで知られます。",
            },
            "ho-chi-minh-city": {
                "tags": ["street-food", "urban", "nightlife"],
                "en": " Ho Chi Minh City mixes street food, history, and energetic nightlife.",
                "zh-HK": " 胡志明市結合街頭美食、歷史與熱鬧夜生活。",
                "ja": " ホーチミンは屋台、歴史、活気ある夜が混在します。",
            },
            "da-nang": {
                "tags": ["beach", "nature", "food"],
                "en": " Da Nang offers beaches with easy access to heritage towns and nature.",
                "zh-HK": " 峴港有海灘，並方便前往古鎮與自然景點。",
                "ja": " ダナンはビーチと歴史都市・自然へのアクセスが良い街です。",
            },
        },
        "country_en": " Vietnam rewards travelers with street food, layered history, and coastal nature.",
        "country_zh": " 越南以街頭美食、層層歷史與海岸自然吸引旅客。",
        "country_ja": " ベトナムは屋台、重層的な歴史、海岸の自然が魅力です。",
    },
    "MY": {
        "country_tags": ["street-food", "beach", "culture", "islands"],
        "cities": {
            "kuala-lumpur": {
                "tags": ["street-food", "urban", "culture"],
                "en": " Kuala Lumpur is a street-food capital with markets and skyline views.",
                "zh-HK": " 吉隆坡是街頭美食之都，兼有市集與天際線。",
                "ja": " クアラルンプールは屋台の都で、市場とスカイラインも楽しめます。",
            },
            "penang": {
                "tags": ["street-food", "culture", "beach"],
                "en": " Penang is legendary for hawker food and heritage streets.",
                "zh-HK": " 檳城以小販美食與古蹟街道聞名。",
                "ja": " ペナンはホーカーフードとヘリテージストリートで有名です。",
            },
            "langkawi": {
                "tags": ["beach", "islands", "nature"],
                "en": " Langkawi is an island escape for beaches and rainforest cable cars.",
                "zh-HK": " 蘭卡威是海島假期，有海灘與雨林纜車。",
                "ja": " ランカウイはビーチと熱帯林ロープウェイの島リゾートです。",
            },
        },
        "country_en": " Malaysia shines for hawker street food, islands, and multicultural cities.",
        "country_zh": " 馬來西亞以小販街頭美食、島嶼與多元文化城市見稱。",
        "country_ja": " マレーシアはホーカー、島、多文化都市が魅力です。",
    },
    "MA": {
        "country_tags": ["desert", "markets", "culture", "adventure"],
        "cities": {
            "marrakech": {
                "tags": ["markets", "desert", "culture", "food"],
                "en": " Marrakech is defined by souks, riads, and desert trip gateways.",
                "zh-HK": " 馬拉喀什以市集、庭院旅店與沙漠行程門戶聞名。",
                "ja": " マラケシュはスーク、リアド、砂漠ツアーの玄関口です。",
            },
            "fez": {
                "tags": ["markets", "culture", "history"],
                "en": " Fez preserves a medieval medina of workshops, markets, and history.",
                "zh-HK": " 非斯保存中世紀古城、工坊與市集歷史。",
                "ja": " フェズは工房と市場が残る中世メディナで知られます。",
            },
        },
        "country_en": " Morocco invites travelers with desert dunes, souks, and riad stays.",
        "country_zh": " 摩洛哥以沙漠沙丘、市集與庭院旅店吸引旅客。",
        "country_ja": " モロッコは砂漠、スーク、リアド滞在が魅力です。",
    },
    "GR": {
        "country_tags": ["islands", "beach", "history", "food"],
        "cities": {
            "athens": {
                "tags": ["history", "museums", "food"],
                "en": " Athens anchors ancient history, museums, and lively food neighborhoods.",
                "zh-HK": " 雅典以古代歷史、博物館與熱鬧飲食區為核心。",
                "ja": " アテネは古代史、美術館、活気ある食の街が中心です。",
            },
            "santorini": {
                "tags": ["islands", "romance", "beach"],
                "en": " Santorini is iconic for caldera islands, sunsets, and romance.",
                "zh-HK": " 聖托里尼以火山口島嶼、日落與浪漫聞名。",
                "ja": " サントリーニはカルデラの島、夕日、ロマンスで象徴的です。",
            },
            "crete": {
                "tags": ["islands", "beach", "food", "hiking"],
                "en": " Crete offers island beaches, gorges for hiking, and strong food culture.",
                "zh-HK": " 克里特有島嶼海灘、峽谷健行與濃厚飲食文化。",
                "ja": " クレタはビーチ、峡谷ハイク、豊かな食文化があります。",
            },
        },
        "country_en": " Greece is built for island hopping, beaches, and classical history.",
        "country_zh": " 希臘適合跳島、海灘與古典歷史之旅。",
        "country_ja": " ギリシャは島 Hopping、ビーチ、古典史の旅向きです。",
    },
    "HR": {
        "country_tags": ["islands", "beach", "history", "scenic"],
        "cities": {
            "dubrovnik": {
                "tags": ["history", "beach", "islands"],
                "en": " Dubrovnik pairs walled old towns with Adriatic island day boats.",
                "zh-HK": " 杜布羅夫尼克結合古城牆與亞得里亞海島日遊。",
                "ja": " ドゥブロヴニクは城壁旧市街とアドリア海の島日帰りが魅力です。",
            },
            "split": {
                "tags": ["history", "beach", "islands"],
                "en": " Split is a ferry hub for islands with Roman ruins and beaches.",
                "zh-HK": " 斯普利特是跳島渡輪樞紐，有羅馬遺跡與海灘。",
                "ja": " スプリットはローマ遺跡とビーチ、島フェリーの拠点です。",
            },
        },
        "country_en": " Croatia mixes Adriatic beaches, islands, and historic coastal towns.",
        "country_zh": " 克羅地亞結合亞得里亞海灘、島嶼與歷史海濱城鎮。",
        "country_ja": " クロアチアはアドリアのビーチ、島、歴史ある海辺の町が魅力です。",
    },
}


def merge_tags(existing: list | None, extra: list[str]) -> list[str]:
    out: list[str] = []
    for tag in list(existing or []) + extra:
        if tag and tag not in out:
            out.append(tag)
    return out


def append_i18n(obj: dict, en: str, zh: str, ja: str) -> None:
    for key, add in (("en", en), ("zh-HK", zh), ("ja", ja)):
        base = (obj.get(key) or "").rstrip()
        if add.strip() and add.strip() not in base:
            obj[key] = f"{base}{add}" if base else add.strip()


def main() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    countries = data["countries"]
    touched = 0
    for country in countries:
        iso = country.get("iso_code")
        spec = ENRICH.get(iso)
        if not spec:
            continue
        touched += 1
        country["tags"] = merge_tags(country.get("tags"), spec.get("country_tags", []))
        append_i18n(
            country.setdefault("description", {}),
            spec.get("country_en", ""),
            spec.get("country_zh", ""),
            spec.get("country_ja", ""),
        )
        city_specs = spec.get("cities") or {}
        for bucket in ("top_cities", "cities"):
            for city in country.get(bucket) or []:
                slug = city.get("slug")
                if slug not in city_specs:
                    continue
                cs = city_specs[slug]
                city["tags"] = merge_tags(city.get("tags"), cs.get("tags", []))
                append_i18n(
                    city.setdefault("description", {}),
                    cs.get("en", ""),
                    cs.get("zh-HK", ""),
                    cs.get("ja", ""),
                )
    SEED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Enriched {touched} countries in {SEED}")


if __name__ == "__main__":
    main()
