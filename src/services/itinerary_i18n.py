"""Locale-aware narrative strings for the itinerary agent (heuristic path)."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.schemas.country import Locale

ROOT = Path(__file__).resolve().parents[2]
PHOTO_MAP_PATH = ROOT / "data" / "poi_category_photos.json"

# Fallback meal photos (prefer meal_photo()).
MEAL_PHOTO_LUNCH = (
    "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=800&q=80"
)
MEAL_PHOTO_DINNER = (
    "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=800&q=80"
)

# Safer generic fallbacks (no desert / Paris bridge / tropical beach).
CATEGORY_PHOTOS: dict[str, list[str]] = {
    "attraction": [
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1528164344705-47542687000d?auto=format&fit=crop&w=800&q=80",
    ],
    "food": [
        "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?auto=format&fit=crop&w=800&q=80",
    ],
    "rest": [
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=800&q=80",
    ],
}


@lru_cache
def _photo_map() -> dict[str, Any]:
    if not PHOTO_MAP_PATH.exists():
        return {}
    return json.loads(PHOTO_MAP_PATH.read_text(encoding="utf-8"))


def _locale_key(locale: Locale | str | None) -> str:
    if locale is None:
        return Locale.EN.value
    if isinstance(locale, Locale):
        return locale.value
    return str(locale)


def pick(locale: Locale | str | None, table: dict[str, str], *, fallback: str = "") -> str:
    key = _locale_key(locale)
    return table.get(key) or table.get(Locale.EN.value) or fallback


def photo_shape(poi_name: str, category: str) -> str:
    """Coarse visual bucket so stock photos match shrine vs park vs sports."""
    hay = f"{poi_name or ''} {category or ''}".lower()
    if any(
        tok in hay
        for tok in (
            "sport",
            "ground",
            "stadium",
            "arena",
            "ballpark",
        )
    ):
        return "sports"
    if any(
        tok in hay
        for tok in (
            "shrine",
            "temple",
            "church",
            "mosque",
            "worship",
            "cathedral",
            "神社",
            "寺",
            "教会",
        )
    ):
        return "worship"
    if category == "rest" or any(
        tok in hay for tok in ("park", "garden", "nature", "onsen", "bamboo", "momiji")
    ):
        return "park" if any(
            tok in hay for tok in ("park", "garden", "nature", "bamboo", "momiji")
        ) else "rest"
    return (category or "attraction").strip().lower() or "attraction"


def unsplash_allowlist() -> set[str]:
    """Photo IDs present in the on-disk map (reject invented / 404 Unsplash URLs)."""
    from src.services.itinerary_eval import photo_id_from_url

    data = _photo_map()
    ids: set[str] = set()
    for bucket in (data.get("defaults") or {}).values():
        for url in bucket or []:
            pid = photo_id_from_url(str(url))
            if pid:
                ids.add(pid)
    for bucket in (data.get("by_key") or {}).values():
        for url in bucket or []:
            pid = photo_id_from_url(str(url))
            if pid:
                ids.add(pid)
    for url in (data.get("meals") or {}).values():
        pid = photo_id_from_url(str(url))
        if pid:
            ids.add(pid)
    return ids


def photo_candidates(
    category: str,
    *,
    city: str | None = None,
    iso: str | None = None,
    poi_name: str | None = None,
) -> list[str]:
    """Deduped Unsplash URLs for city/iso/shape, then safer defaults."""
    data = _photo_map()
    by_key: dict[str, list[str]] = data.get("by_key") or {}
    defaults: dict[str, list[str]] = data.get("defaults") or CATEGORY_PHOTOS
    city_iso: dict[str, str] = data.get("city_iso") or {}

    slug = (city or "").strip().lower().replace(" ", "-")
    iso_key = (iso or city_iso.get(slug) or "").strip().lower()
    shape = photo_shape(poi_name or "", category)
    cat = (category or "attraction").strip().lower()

    ordered: list[str] = []
    seen: set[str] = set()
    keys = (
        f"{slug}:{shape}",
        f"{iso_key}:{shape}",
        f"{slug}:{cat}",
        f"{iso_key}:{cat}",
    )
    for key in keys:
        for url in by_key.get(key) or []:
            if url and url not in seen and not _denied_photo(url):
                seen.add(url)
                ordered.append(url)
    if not ordered:
        fallback = list(
            defaults.get(shape)
            or defaults.get(cat)
            or CATEGORY_PHOTOS.get(cat)
            or CATEGORY_PHOTOS["attraction"]
        )
        for url in fallback:
            if url and url not in seen and not _denied_photo(url):
                seen.add(url)
                ordered.append(url)
    if not ordered:
        ordered = [u for u in CATEGORY_PHOTOS["attraction"] if not _denied_photo(u)]
    return ordered


def _denied_photo(url: str | None) -> bool:
    from src.services.itinerary_eval import is_denied_stock_photo

    return is_denied_stock_photo(url)


def all_stock_photo_urls() -> list[str]:
    """Flatten allowlisted stock URLs (defaults + by_key), skipping denied IDs."""
    data = _photo_map()
    ordered: list[str] = []
    seen: set[str] = set()
    for bucket in (data.get("defaults") or {}).values():
        for url in bucket or []:
            if url and url not in seen and not _denied_photo(url):
                seen.add(url)
                ordered.append(url)
    for bucket in (data.get("by_key") or {}).values():
        for url in bucket or []:
            if url and url not in seen and not _denied_photo(url):
                seen.add(url)
                ordered.append(url)
    return ordered


def category_photo(
    category: str,
    index: int = 0,
    *,
    city: str | None = None,
    iso: str | None = None,
    poi_name: str | None = None,
) -> str:
    """Pick a city/cuisine-aware Unsplash URL."""
    candidates = photo_candidates(category, city=city, iso=iso, poi_name=poi_name)
    if not candidates:
        return ""
    if poi_name:
        material = poi_name.strip().lower().encode("utf-8")
        index = int(hashlib.md5(material).hexdigest(), 16) % len(candidates)
    return candidates[index % len(candidates)]


def meal_photo(poi_name: str, meal_role: str = "lunch") -> str:
    """Dish → Unsplash meal photo (disabled — planner uses lunch/dinner icons)."""
    _ = (poi_name, meal_role)
    return ""
    # --- meal/food image search (commented out) ---
    # data = _photo_map()
    # meals: dict[str, str] = data.get("meals") or {}
    # hay = (poi_name or "").lower()
    # name = poi_name or ""
    # for key in (
    #     "monjayaki",
    #     "okonomiyaki",
    #     "takoyaki",
    #     "kushikatsu",
    #     "ramen",
    #     "izakaya",
    #     "tempura",
    #     "tonkatsu",
    #     "matcha",
    #     "nishiki",
    #     "kaiseki",
    #     "yudofu",
    #     "obanzai",
    #     "shojin",
    #     "tofu",
    #     "soba",
    #     "udon",
    #     "yakiniku",
    #     "unagi",
    #     "sushi",
    #     "tapas",
    #     "paella",
    #     "tagine",
    #     "pizza",
    #     "pasta",
    #     "bbq",
    # ):
    #     if key in hay:
    #         return _safe_meal_url(
    #             meals.get(key) or meals.get("default_lunch") or MEAL_PHOTO_LUNCH,
    #             meal_role,
    #         )
    # if any(tok in name for tok in ("抹茶",)):
    #     return _safe_meal_url(meals.get("matcha") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("懷石", "懐石", "湯豆腐", "精進")):
    #     return _safe_meal_url(
    #         meals.get("kaiseki") or meals.get("tofu") or MEAL_PHOTO_LUNCH,
    #         meal_role,
    #     )
    # if any(tok in name for tok in ("豆腐", "湯葉")):
    #     return _safe_meal_url(meals.get("tofu") or meals.get("kaiseki") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("錦市場", "錦")):
    #     return _safe_meal_url(meals.get("nishiki") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("拉麵", "ラーメン")):
    #     return _safe_meal_url(meals.get("ramen") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("大阪燒", "章魚", "たこ焼き", "お好み焼き", "もんじゃ", "文字燒")):
    #     return _safe_meal_url(
    #         meals.get("okonomiyaki") or meals.get("monjayaki") or MEAL_PHOTO_LUNCH,
    #         meal_role,
    #     )
    # if any(tok in name for tok in ("天婦羅", "天ぷら")):
    #     return _safe_meal_url(meals.get("tempura") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("豬排", "とんかつ", "トンカツ")):
    #     return _safe_meal_url(meals.get("tonkatsu") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("蕎麥", "そば")):
    #     return _safe_meal_url(meals.get("soba") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("烏冬", "うどん")):
    #     return _safe_meal_url(meals.get("udon") or MEAL_PHOTO_LUNCH, meal_role)
    # if any(tok in name for tok in ("燒肉", "焼肉")):
    #     return _safe_meal_url(
    #         meals.get("yakiniku") or meals.get("bbq") or MEAL_PHOTO_DINNER,
    #         meal_role,
    #     )
    # if "串" in name:
    #     return _safe_meal_url(
    #         meals.get("kushikatsu") or meals.get("izakaya") or MEAL_PHOTO_DINNER,
    #         meal_role,
    #     )
    # if any(tok in name for tok in ("壽司", "寿司")):
    #     return _safe_meal_url(meals.get("sushi") or MEAL_PHOTO_DINNER, meal_role)
    # if meal_role == "dinner":
    #     return _safe_meal_url(meals.get("default_dinner") or MEAL_PHOTO_DINNER, meal_role)
    # return _safe_meal_url(meals.get("default_lunch") or MEAL_PHOTO_LUNCH, meal_role)


def _safe_meal_url(url: str | None, meal_role: str) -> str:
    """Only emit Unsplash IDs that exist in the on-disk photo map."""
    from src.services.itinerary_eval import photo_id_from_url

    fallback = MEAL_PHOTO_DINNER if meal_role == "dinner" else MEAL_PHOTO_LUNCH
    allowed = unsplash_allowlist()
    pid = photo_id_from_url(url)
    if pid and pid in allowed and str(url or "").startswith("https://"):
        return str(url)
    fb_id = photo_id_from_url(fallback)
    if fb_id and fb_id in allowed:
        return fallback
    return fallback


def localize_activity_description(
    description: str,
    *,
    poi_name: str,
    category: str,
    locale: Locale | str | None,
) -> str:
    """Wrap English POI blurbs in a localized template for zh-HK / ja."""
    key = _locale_key(locale)
    text = (description or "").strip() or poi_name
    if key == "en" or not text:
        return text
    cjk = sum(
        1 for ch in text if "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff"
    )
    if cjk >= max(3, len(text) // 4):
        return text
    if key == "zh-HK":
        label = {"attraction": "景點", "food": "美食", "rest": "休憩"}.get(
            category, "行程"
        )
        return f"{poi_name}（{label}）：{text}"
    if key == "ja":
        label = {"attraction": "観光", "food": "グルメ", "rest": "休憩"}.get(
            category, "スポット"
        )
        return f"{poi_name}（{label}）：{text}"
    return text


MOCK_CITY_NAMES: dict[str, dict[str, str]] = {
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
        "en": "Tokyo",
        "zh-HK": "東京",
        "ja": "東京",
    },
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": {
        "en": "Seoul",
        "zh-HK": "首爾",
        "ja": "ソウル",
    },
}

# needle in city name → locale → lunch/dinner rotation lists
CITY_CUISINE: list[tuple[str, dict[str, dict[str, list[str]]]]] = [
    (
        "tokyo",
        {
            "en": {
                "lunch": [
                    "Japanese Ramen / Teishoku",
                    "Sushi / Chirashi",
                    "Soba / Udon",
                    "Tempura Set",
                    "Tonkatsu Teishoku",
                ],
                "dinner": [
                    "Izakaya / Yakitori",
                    "Sushi Set",
                    "Yakiniku",
                    "Monjayaki / Okonomiyaki",
                    "Unagi / Kaiseki",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "日式拉麵／定食",
                    "壽司／散壽司",
                    "蕎麥麵／烏冬",
                    "天婦羅定食",
                    "炸豬排定食",
                ],
                "dinner": [
                    "居酒屋／烤雞串",
                    "壽司套餐",
                    "日式燒肉",
                    "文字燒／大阪燒",
                    "鰻魚／懷石",
                ],
            },
            "ja": {
                "lunch": [
                    "ラーメン／定食",
                    "寿司／ちらし",
                    "そば／うどん",
                    "天ぷら定食",
                    "とんかつ定食",
                ],
                "dinner": [
                    "居酒屋／焼き鳥",
                    "寿司セット",
                    "焼肉",
                    "もんじゃ／お好み焼き",
                    "うなぎ／懐石",
                ],
            },
        },
    ),
    (
        "osaka",
        {
            "en": {
                "lunch": [
                    "Okonomiyaki / Takoyaki",
                    "Kushikatsu",
                    "Osaka Ramen",
                    "Udon / Kitsune",
                    "Kaisen-don",
                ],
                "dinner": [
                    "Kushikatsu / Izakaya",
                    "Okonomiyaki Dinner",
                    "Yakiniku",
                    "Street-food Stalls",
                    "Kappo / Seasonal Set",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "大阪燒／章魚燒",
                    "串炸",
                    "大阪拉麵",
                    "烏冬／狐狸烏冬",
                    "海鮮丼",
                ],
                "dinner": [
                    "串炸／居酒屋",
                    "大阪燒晚餐",
                    "日式燒肉",
                    "街頭小吃攤",
                    "割烹／時令套餐",
                ],
            },
            "ja": {
                "lunch": [
                    "お好み焼き／たこ焼き",
                    "串カツ",
                    "大阪ラーメン",
                    "うどん／きつね",
                    "海鮮丼",
                ],
                "dinner": [
                    "串カツ／居酒屋",
                    "お好み焼きディナー",
                    "焼肉",
                    "屋台グルメ",
                    "割烹／季節のコース",
                ],
            },
        },
    ),
    (
        "kyoto",
        {
            "en": {
                "lunch": [
                    "Kaiseki / Tofu Cuisine",
                    "Nishiki Market Bites",
                    "Matcha Sweets / Soba",
                    "Obanzai Lunch",
                    "Yudofu Set",
                ],
                "dinner": [
                    "Kaiseki Dinner",
                    "Nishiki Evening Bites",
                    "Izakaya / Kyo-yasai",
                    "Shojin Ryori",
                    "Unagi / Kyoto Grill",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "懷石／豆腐料理",
                    "錦市場小吃",
                    "抹茶甜點／蕎麥麵",
                    "京野菜家常午餐",
                    "湯豆腐定食",
                ],
                "dinner": [
                    "懷石晚餐",
                    "錦市場夜市小吃",
                    "居酒屋／京野菜",
                    "精進料理",
                    "鰻魚／京都燒烤",
                ],
            },
            "ja": {
                "lunch": [
                    "京懐石／湯葉料理",
                    "錦市場グルメ",
                    "抹茶／そば",
                    "おばんざいランチ",
                    "湯豆腐定食",
                ],
                "dinner": [
                    "懐石ディナー",
                    "錦の夜グルメ",
                    "居酒屋／京野菜",
                    "精進料理",
                    "うなぎ／京焼き",
                ],
            },
        },
    ),
    (
        "seoul",
        {
            "en": {
                "lunch": [
                    "Korean BBQ / Banchan",
                    "Street Food / Mandu",
                    "Bibimbap / Kimchi Stew",
                    "K-fried Chicken Lunch",
                    "Naengmyeon",
                ],
                "dinner": [
                    "Korean BBQ Dinner",
                    "Street Food Night",
                    "Samgyeopsal / Soju Bites",
                    "Jjigae / Banchan Spread",
                    "Korean Fried Chicken",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "韓式烤肉／小菜",
                    "街頭小吃／餃子",
                    "石鍋拌飯／泡菜湯",
                    "韓式炸雞午餐",
                    "冷麵",
                ],
                "dinner": [
                    "韓式烤肉晚餐",
                    "街頭夜市小吃",
                    "五花肉／小酌",
                    "鍋物／小菜拼盤",
                    "韓式炸雞",
                ],
            },
            "ja": {
                "lunch": [
                    "韓国焼肉／バンチャン",
                    "屋台／マンドゥ",
                    "ビビンバ／キムチチゲ",
                    "チキンランチ",
                    "冷麺",
                ],
                "dinner": [
                    "焼肉ディナー",
                    "屋台ナイト",
                    "サムギョプサル",
                    "チゲ／バンチャン",
                    "フライドチキン",
                ],
            },
        },
    ),
    (
        "paris",
        {
            "en": {
                "lunch": [
                    "Bistro Lunch / Croque",
                    "Bakery / Cafe Lunch",
                    "Market Crepe / Galette",
                    "Salad / Quiche",
                    "Wine-bar Small Plates",
                ],
                "dinner": [
                    "French Brasserie Dinner",
                    "Bistro Classics",
                    "Seafood / Moules",
                    "Regional French Dinner",
                    "Wine-paired Tasting",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "巴黎小館／法式三明治",
                    "麵包店／咖啡午餐",
                    "市集可麗餅",
                    "沙律／鹹派",
                    "酒吧小食",
                ],
                "dinner": [
                    "法式酒館晚餐",
                    "小館經典",
                    "海鮮／青口",
                    "地區法式晚餐",
                    "配酒品嚐",
                ],
            },
            "ja": {
                "lunch": [
                    "ビストロ／クロック",
                    "ベーカリー／カフェ",
                    "クレープ／ガレット",
                    "サラダ／キッシュ",
                    "ワインバル小皿",
                ],
                "dinner": [
                    "ブラッスリーディナー",
                    "ビストロ定番",
                    "シーフード／ムール",
                    "地方フランス料理",
                    "ワインペアリング",
                ],
            },
        },
    ),
    (
        "rome",
        {
            "en": {
                "lunch": [
                    "Pasta / Roman Trattoria",
                    "Pizza al Taglio",
                    "Supplì / Street Bites",
                    "Cacio e Pepe Lunch",
                    "Market Panino",
                ],
                "dinner": [
                    "Authentic Neapolitan Pizza",
                    "Trattoria Dinner",
                    "Seafood Roman Dinner",
                    "Carbonara Night",
                    "Wine-bar Aperitivo",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "義大利麵／羅馬小館",
                    "羅馬切塊薄餅",
                    "炸飯團／街頭小吃",
                    "胡椒起司麵午餐",
                    "市集三明治",
                ],
                "dinner": [
                    "正宗拿坡里薄餅",
                    "小館晚餐",
                    "羅馬海鮮晚餐",
                    "培根蛋麵之夜",
                    "酒吧開胃餐",
                ],
            },
            "ja": {
                "lunch": [
                    "パスタ／トラットリア",
                    "ピザアルタリョ",
                    "スップリ／屋台",
                    "カチョエペペ",
                    "マーケットパニーノ",
                ],
                "dinner": [
                    "ナポリピザ",
                    "トラットリアディナー",
                    "ローマ海鮮",
                    "カルボナーラ",
                    "アペリティーボ",
                ],
            },
        },
    ),
    (
        "barcelona",
        {
            "en": {
                "lunch": [
                    "Tapas / Paella Lunch",
                    "Mercat Bites",
                    "Bocadillo / Jamón",
                    "Seafood Rice Lunch",
                    "Catalan Set Lunch",
                ],
                "dinner": [
                    "Catalan Dinner",
                    "Tapas Crawl",
                    "Paella Dinner",
                    "Vermouth / Pintxos",
                    "Seafood Grill",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "西班牙小吃／海鮮飯",
                    "市場小吃",
                    "火腿三明治",
                    "海鮮飯午餐",
                    "加泰羅尼亞套餐",
                ],
                "dinner": [
                    "加泰羅尼亞晚餐",
                    "小吃巡禮",
                    "海鮮飯晚餐",
                    "苦艾酒／串燒",
                    "海鮮燒烤",
                ],
            },
            "ja": {
                "lunch": [
                    "タパス／パエリア",
                    "市場グルメ",
                    "ボカディージョ",
                    "シーフードライス",
                    "カタルーニャ定食",
                ],
                "dinner": [
                    "カタルーニャ料理",
                    "タパスクロール",
                    "パエリアディナー",
                    "ベルモット／ピンチョス",
                    "海鮮グリル",
                ],
            },
        },
    ),
    (
        "bangkok",
        {
            "en": {
                "lunch": [
                    "Thai Street Food",
                    "Pad Thai / Noodles",
                    "Boat Noodle Lunch",
                    "Som Tam / Grilled Chicken",
                    "Curry Rice Lunch",
                ],
                "dinner": [
                    "Curry / Seafood Dinner",
                    "Night Market Street Food",
                    "Thai BBQ Dinner",
                    "Royal Thai Set",
                    "Riverside Seafood",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "泰式街頭美食",
                    "炒河粉／麵食",
                    "船麵午餐",
                    "青木瓜沙律／燒雞",
                    "咖喱飯午餐",
                ],
                "dinner": [
                    "咖喱／海鮮晚餐",
                    "夜市街頭美食",
                    "泰式燒烤",
                    "皇室泰菜套餐",
                    "河邊海鮮",
                ],
            },
            "ja": {
                "lunch": [
                    "タイ屋台飯",
                    "パッタイ／麺",
                    "ボートヌードル",
                    "ソムタム／ガイヤーン",
                    "カレーライス",
                ],
                "dinner": [
                    "カレー／海鮮ディナー",
                    "ナイトマーケット",
                    "タイBBQ",
                    "ロイヤルタイ",
                    "リバーサイド海鮮",
                ],
            },
        },
    ),
    (
        "london",
        {
            "en": {
                "lunch": [
                    "Pub Lunch / Pie",
                    "Market Street Food",
                    "Fish and Chips",
                    "Sunday Roast Lunch",
                    "Indian / Brick Lane Bites",
                ],
                "dinner": [
                    "British / Global Dinner",
                    "Gastropub Dinner",
                    "Indian Curry Night",
                    "Modern British Tasting",
                    "Riverside Dining",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "英式酒吧午餐／餡餅",
                    "市集街頭美食",
                    "炸魚薯條",
                    "週日烤肉午餐",
                    "印度／磚巷小吃",
                ],
                "dinner": [
                    "英式／國際晚餐",
                    "美食酒吧晚餐",
                    "印度咖喱之夜",
                    "現代英式品嚐",
                    "河邊晚餐",
                ],
            },
            "ja": {
                "lunch": [
                    "パブランチ／パイ",
                    "マーケット屋台",
                    "フィッシュアンドチップス",
                    "サンデーロースト",
                    "インド／ブリックレーン",
                ],
                "dinner": [
                    "ブリティッシュ／多国籍",
                    "ガストロパブ",
                    "カレーナイト",
                    "モダンブリティッシュ",
                    "リバーサイド",
                ],
            },
        },
    ),
    (
        "marrakech",
        {
            "en": {
                "lunch": [
                    "Tagine / Couscous",
                    "Medina Street Bites",
                    "Harira / Bread Lunch",
                    "Kefta / Salad Lunch",
                    "Pastilla Lunch",
                ],
                "dinner": [
                    "Moroccan Dinner / Mint Tea",
                    "Tagine Dinner",
                    "Mechoui / Grill",
                    "Rooftop Moroccan Set",
                    "Couscous Feast",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "塔吉鍋／couscous",
                    "麥地那街頭小吃",
                    "哈里拉湯／麵包",
                    "肉丸／沙律午餐",
                    "酥皮餡餅午餐",
                ],
                "dinner": [
                    "摩洛哥晚餐／薄荷茶",
                    "塔吉鍋晚餐",
                    "烤全羊／燒烤",
                    "天台摩洛哥套餐",
                    "couscous 盛宴",
                ],
            },
            "ja": {
                "lunch": [
                    "タジン／クスクス",
                    "メディナ屋台",
                    "ハリーラ／パン",
                    "ケフタ／サラダ",
                    "パスティラ",
                ],
                "dinner": [
                    "モロッコ料理／ミントティー",
                    "タジンディナー",
                    "メシュイ／グリル",
                    "屋上モロッコ",
                    "クスクスフルコース",
                ],
            },
        },
    ),
    (
        "reykjav",
        {
            "en": {
                "lunch": [
                    "Seafood Soup Lunch",
                    "Lamb Stew Lunch",
                    "Hot Dog / Bakery Lunch",
                    "Fish and Chips Lunch",
                    "Skyr / Cafe Lunch",
                ],
                "dinner": [
                    "Nordic Dinner",
                    "Catch-of-the-day Dinner",
                    "Lamb / Game Dinner",
                    "Seafood Grill",
                    "Modern Icelandic Set",
                ],
            },
            "zh-HK": {
                "lunch": [
                    "海鮮湯午餐",
                    "羊肉燉午餐",
                    "熱狗／麵包店午餐",
                    "炸魚薯條午餐",
                    "Skyr／咖啡午餐",
                ],
                "dinner": [
                    "北歐晚餐",
                    "當日鮮魚晚餐",
                    "羊肉／野味晚餐",
                    "海鮮燒烤",
                    "現代冰島套餐",
                ],
            },
            "ja": {
                "lunch": [
                    "シーフードスープ",
                    "ラムシチュー",
                    "ホットドッグ／ベーカリー",
                    "フィッシュアンドチップス",
                    "スキル／カフェ",
                ],
                "dinner": [
                    "ノルディックディナー",
                    "本日の魚",
                    "ラム／ジビエ",
                    "海鮮グリル",
                    "モダンアイスランド",
                ],
            },
        },
    ),
]

DEFAULT_MEALS: dict[str, tuple[str, str]] = {
    "en": ("Regional Lunch Specialty", "Local Dinner Cuisine"),
    "zh-HK": ("當地特色午餐", "當地風味晚餐"),
    "ja": ("ご当地ランチ", "ローカルディナー"),
}

# Shared cuisine families so lunch/dinner do not repeat the same dish type.
CUISINE_FAMILY_NEEDLES: list[tuple[str, tuple[str, ...]]] = [
    ("sushi", ("sushi", "chirashi", "壽司", "寿司", "ちらし")),
    ("okonomiyaki", ("okonomiyaki", "monjayaki", "takoyaki", "大阪燒", "お好み焼き", "もんじゃ", "たこ焼き", "文字燒")),
    ("yakiniku", ("yakiniku", "焼肉", "燒肉")),
    ("ramen", ("ramen", "拉麵", "ラーメン")),
    ("soba", ("soba", "udon", "蕎麥", "そば", "烏冬", "うどん")),
    ("tempura", ("tempura", "天婦羅", "天ぷら")),
    ("izakaya", ("izakaya", "yakitori", "居酒屋", "焼き鳥", "烤雞串")),
    ("kushikatsu", ("kushikatsu", "串炸", "串カツ")),
    ("kaiseki", ("kaiseki", "yudofu", "obanzai", "shojin", "懷石", "懐石", "湯豆腐", "おばんざい", "精進")),
    ("tofu", ("tofu", "yuba", "豆腐", "湯葉")),
    ("matcha", ("matcha", "抹茶")),
    ("nishiki", ("nishiki", "錦")),
    ("unagi", ("unagi", "鰻")),
    ("bbq", ("bbq", "barbecue", "烤肉")),
]


def cuisine_family(label: str) -> str:
    text = label or ""
    hay = text.lower()
    # Some dish labels include multiple cuisine needles (e.g. "Matcha Sweets / Soba").
    # Choose the "best" family deterministically instead of returning the first match in
    # CUISINE_FAMILY_NEEDLES ordering.
    best_family: str | None = None
    best_score: tuple[int, int, int] | None = None
    for family, needles in CUISINE_FAMILY_NEEDLES:
        match_count = 0
        earliest_idx: int | None = None
        longest_needle_len = 0
        for needle in needles:
            n = str(needle).lower()
            idx = hay.find(n)
            if idx == -1:
                continue
            match_count += 1
            earliest_idx = idx if earliest_idx is None else min(earliest_idx, idx)
            longest_needle_len = max(longest_needle_len, len(n))
        if match_count == 0 or earliest_idx is None:
            continue
        # Higher is better:
        # - more needle matches
        # - earlier occurrence in the string
        # - longer needle length (more specific)
        score = (match_count, -earliest_idx, longest_needle_len)
        if best_score is None or score > best_score:
            best_family = family
            best_score = score
    if best_family:
        return best_family
    return re.sub(r"\s+", " ", hay).strip()[:32] or "other"


def meal_pair(
    city_name: str,
    preferences: list[str],
    day_number: int,
    locale: Locale | str | None,
    *,
    used: set[str] | None = None,
) -> tuple[str, str]:
    key = _locale_key(locale)
    hay = f"{city_name} {' '.join(preferences)}".lower()
    used_labels = used or set()
    day_idx = max(0, int(day_number) - 1)
    for needle, by_locale in CITY_CUISINE:
        if needle not in hay:
            continue
        slots = by_locale.get(key) or by_locale.get("en") or {}
        lunches = list(slots.get("lunch") or [])
        dinners = list(slots.get("dinner") or [])
        if lunches and dinners:
            lunch = _pick_rotated(lunches, day_idx, used_labels)
            dinner = _pick_rotated(dinners, day_idx, used_labels, other=lunch)
            return lunch, dinner
    if preferences:
        pref = preferences[day_idx % len(preferences)].replace("-", " ")
        if key == "zh-HK":
            return (f"{pref} 靈感午餐", f"{pref} 靈感晚餐")
        if key == "ja":
            return (f"{pref}ランチ", f"{pref}ディナー")
        pref_t = pref.title()
        return (f"{pref_t}-inspired Lunch", f"{pref_t}-inspired Dinner")
    return DEFAULT_MEALS.get(key) or DEFAULT_MEALS["en"]


def _pick_rotated(
    items: list[str],
    start: int,
    used: set[str],
    *,
    other: str | None = None,
) -> str:
    n = len(items)
    if n == 0:
        return other or ""
    used_fam = {cuisine_family(u) for u in used}
    other_fam = cuisine_family(other) if other else None
    for i in range(n):
        cand = items[(start + i) % n]
        fam = cuisine_family(cand)
        if cand in used or fam in used_fam or fam == other_fam:
            continue
        return cand
    for i in range(n):
        cand = items[(start + i) % n]
        fam = cuisine_family(cand)
        if other and (cand == other or fam == other_fam):
            continue
        return cand
    return items[start % n]


def meal_description(
    role: str,
    city_name: str,
    locale: Locale | str | None,
    *,
    dish: str | None = None,
) -> str:
    key = _locale_key(locale)
    label = (dish or "").strip()
    if role == "lunch":
        if label:
            return pick(
                key,
                {
                    "en": f"Lunch food type: {label} — typical {city_name} fare (not a specific restaurant).",
                    "zh-HK": f"午餐類型：{label}（{city_name} 常見吃法，非指定餐廳）。",
                    "ja": f"ランチの料理タイプ：{label}（{city_name}のご当地グルメ。店名ではありません）。",
                },
            )
        return pick(
            key,
            {
                "en": f"Lunch food-type recommendation for {city_name}.",
                "zh-HK": f"{city_name} 的午餐類型建議。",
                "ja": f"{city_name}のランチ（料理タイプ）おすすめ。",
            },
        )
    if label:
        return pick(
            key,
            {
                "en": f"Dinner food type: {label} — typical {city_name} fare (not a specific restaurant).",
                "zh-HK": f"晚餐類型：{label}（{city_name} 常見吃法，非指定餐廳）。",
                "ja": f"ディナーの料理タイプ：{label}（{city_name}のご当地グルメ。店名ではありません）。",
            },
        )
    return pick(
        key,
        {
            "en": f"Dinner food-type recommendation for {city_name}.",
            "zh-HK": f"{city_name} 的晚餐類型建議。",
            "ja": f"{city_name}のディナー（料理タイプ）おすすめ。",
        },
    )


def day_theme(
    day_number: int,
    preferences: list[str],
    selected: list[dict[str, Any]],
    locale: Locale | str | None,
) -> str:
    key = _locale_key(locale)
    pref = preferences[0] if preferences else None
    cats = {p["category"] for p in selected}
    tags = " ".join(t for p in selected for t in p.get("tags") or []).lower()

    if pref:
        return pick(
            key,
            {
                "en": f"Day {day_number}: {pref.replace('-', ' ').title()} focus",
                "zh-HK": f"第 {day_number} 天：{pref} 主題",
                "ja": f"{day_number}日目：{pref}フォーカス",
            },
        )
    if "museum" in tags:
        return pick(
            key,
            {
                "en": f"Day {day_number}: Museums & culture",
                "zh-HK": f"第 {day_number} 天：博物館與文化",
                "ja": f"{day_number}日目：博物館と文化",
            },
        )
    if cats == {"food"} or (len(cats) == 2 and "food" in cats and "rest" in cats):
        return pick(
            key,
            {
                "en": f"Day {day_number}: Food crawl",
                "zh-HK": f"第 {day_number} 天：美食巡禮",
                "ja": f"{day_number}日目：食べ歩き",
            },
        )
    return pick(
        key,
        {
            "en": f"Day {day_number}: City highlights",
            "zh-HK": f"第 {day_number} 天：城市亮點",
            "ja": f"{day_number}日目：街のハイライト",
        },
    )


def day_validated_reasoning(
    day_number: int,
    turn: int,
    max_turns: int,
    cost: float,
    duration_minutes: Any,
    locale: Locale | str | None,
) -> str:
    key = _locale_key(locale)
    return pick(
        key,
        {
            "en": (
                f"Day {day_number}: validated on turn {turn}/{max_turns} "
                f"(${cost:.0f}, {duration_minutes} min incl. travel)."
            ),
            "zh-HK": (
                f"第 {day_number} 天：於第 {turn}/{max_turns} 輪通過驗證"
                f"（${cost:.0f}，含交通約 {duration_minutes} 分鐘）。"
            ),
            "ja": (
                f"{day_number}日目：ターン {turn}/{max_turns} で検証OK"
                f"（${cost:.0f}、移動込み約 {duration_minutes} 分）。"
            ),
        },
    )


def trip_user_summary(
    city_name: str,
    days: int,
    pace: str,
    preferences: list[str],
    locale: Locale | str | None,
    *,
    missing_tags: list[str] | None = None,
) -> str:
    """Friendly 'what we optimized for' copy (not evaluator turn logs)."""
    key = _locale_key(locale)
    skip = {"popular", "unconventional"}
    focus = [p.replace("-", " ") for p in preferences if p and p.lower() not in skip]
    unconventional = any(p.lower() == "unconventional" for p in preferences)
    if key == "zh-HK":
        focus_txt = "、".join(focus) if focus else "均衡行程"
        style = "偏門小店" if unconventional else "熱門地標"
        extra = ""
        if missing_tags:
            extra = " 資料庫較少「" + "、".join(missing_tags) + "」景點，可用地圖自訂地點補上。"
        return (
            f"這次 {days} 天（{pace}）{city_name} 行程以{focus_txt}為主，並偏向{style}。"
            f"{extra}"
        ).strip()
    if key == "ja":
        focus_txt = "、".join(focus) if focus else "バランスの取れた見学"
        style = "穴場" if unconventional else "定番スポット"
        extra = ""
        if missing_tags:
            extra = (
                " データ上「"
                + "、".join(missing_tags)
                + "」の候補が少ないので、地図からカスタム地点を追加してください。"
            )
        return (
            f"{city_name}の{days}日間（{pace}）プランは{focus_txt}を優先し、{style}寄りです。"
            f"{extra}"
        ).strip()
    focus_txt = ", ".join(focus) if focus else "a balanced mix of sights"
    style = "lesser-known stops" if unconventional else "popular landmarks"
    extra = ""
    if missing_tags:
        extra = (
            f" Limited pool coverage for {', '.join(missing_tags)} — "
            "add a custom map pin if you have a specific venue in mind."
        )
    return (
        f"We focused this {days}-day {pace} plan in {city_name} on {focus_txt}, "
        f"leaning toward {style}.{extra}"
    )


def trip_prep_tips(
    city_name: str,
    preferences: list[str],
    locale: Locale | str | None,
) -> list[str]:
    key = _locale_key(locale)
    prefs = {p.strip().lower() for p in preferences if p}
    tips: list[tuple[str, dict[str, str]]] = [
        (
            "hours",
            {
                "en": f"Confirm opening hours the day before — {city_name} spots often close one weekday.",
                "zh-HK": f"出發前確認開放時間——{city_name}景點常有固定休息日。",
                "ja": f"前日に営業時間を確認。{city_name}は定休日がある施設が多いです。",
            },
        ),
        (
            "tickets",
            {
                "en": "Pre-book tickets for observation decks and popular museums when you can.",
                "zh-HK": "觀景台與熱門博物館盡量提早網上預約。",
                "ja": "展望台や人気ミュージアムは可能なら事前予約を。",
            },
        ),
    ]
    if "nightlife" in prefs:
        tips.append(
            (
                "nightlife",
                {
                    "en": "Nightlife venues may have cover charges or ID checks — bring cash and a photo ID.",
                    "zh-HK": "夜生活場所有時收入場費或查證件，帶現金與證件。",
                    "ja": "ナイトスポットはチャージや身分証確認があることがあります。現金とIDを。",
                },
            )
        )
    if any(p in prefs for p in ("temples", "culture", "history")):
        tips.append(
            (
                "dress",
                {
                    "en": "Cover shoulders and speak quietly at temples and shrines.",
                    "zh-HK": "寺廟神社請遮肩、保持安靜。",
                    "ja": "寺社では肩を出しすぎず、静かに見学を。",
                },
            )
        )
    if "food" in prefs or "street-food" in prefs:
        tips.append(
            (
                "food",
                {
                    "en": "Popular food streets get long queues at dinner — go early or share stalls.",
                    "zh-HK": "熱門美食街晚餐時段人多，提早去或分檔位。",
                    "ja": "人気の食べ歩きは夜混むので、早めか時間をずらして。",
                },
            )
        )
    return [pick(key, table) for _, table in tips[:4]]


def fallback_agent_reasoning(
    days: int,
    pace: str,
    city_name: str,
    daily_budget: float,
    locale: Locale | str | None,
) -> str:
    key = _locale_key(locale)
    return pick(
        key,
        {
            "en": (
                f"Built a {days}-day {pace} plan for {city_name} "
                f"within ${daily_budget:.0f}/day."
            ),
            "zh-HK": (
                f"已為 {city_name} 建立 {days} 天（{pace}）行程，"
                f"每日預算約 ${daily_budget:.0f}。"
            ),
            "ja": (
                f"{city_name}向けに {days} 日間（{pace}）のプランを作成。"
                f"1日あたり約 ${daily_budget:.0f}。"
            ),
        },
    )


def locale_language_instruction(locale: Locale | str | None) -> str:
    key = _locale_key(locale)
    if key == "zh-HK":
        return (
            "Language: Write theme, meal poi_name labels, and ALL description fields "
            "in Traditional Chinese (zh-HK). Keep attraction/rest poi_name EXACTLY "
            "as in the POI pool for grounding."
        )
    if key == "ja":
        return (
            "Language: Write theme, meal poi_name labels, and ALL description fields "
            "in Japanese. Keep attraction/rest poi_name EXACTLY as in the POI pool "
            "for grounding."
        )
    return (
        "Language: Write theme, meal poi_name labels, and description fields in English. "
        "Keep attraction/rest poi_name EXACTLY as in the POI pool for grounding."
    )
