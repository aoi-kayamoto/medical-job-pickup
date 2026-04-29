"""
看護師・医療系案件のキーワード定義と判定ロジック
"""

# 必須キーワード（医療・看護系）
REQUIRED_KEYWORDS = [
    "看護師", "看護師さん", "ナース",
    "医療", "クリニック", "病院", "診療所",
    "訪問看護", "在宅看護", "在宅医療",
    "美容看護", "美容クリニック",
    "記事監修", "医療監修",
    "医療ライター",
    "患者向け", "介護", "福祉",
    "保健師", "助産師", "医療知識",
    "資格保有者歓迎", "医療資格",
    "健康", "ヘルスケア", "メディカル",
    "歯科", "薬剤師", "リハビリ",
    "医師", "ドクター", "医院",
    "産婦人科", "小児科", "整形外科",
    "皮膚科", "内科", "外科",
    "オンライン診療", "医療コンサル",
    "健康相談", "医療翻訳",
    "治験", "臨床", "医学",
    "看護知識", "医療系", "看護系",
]

# ライター系キーワード（医療限定なし）
WRITER_KEYWORDS = [
    "Webライター", "Webライティング", "コンテンツライター",
    "ライター募集", "ライター案件", "記事執筆", "記事作成",
    "ブログ記事", "コラム執筆", "ライティング", "執筆",
    "文章作成", "コンテンツ制作",
]

# SNS運用系キーワード（医療限定なし）
SNS_KEYWORDS = [
    "SNS運用", "SNS管理", "SNS投稿", "SNSマーケティング",
    "Instagram運用", "インスタ運用", "インスタグラム運用",
    "Twitter運用", "X運用", "TikTok運用",
    "ソーシャルメディア運用", "SNSアカウント管理",
]

# カテゴリ分類（ラベル付け用）
CATEGORY_KEYWORDS = {
    "訪問・在宅": ["訪問看護", "在宅看護", "在宅医療", "訪問介護"],
    "美容・クリニック": ["美容看護", "美容クリニック", "美容外科", "美容皮膚科", "エステ"],
    "医療ライティング": ["記事監修", "医療監修", "医療ライター", "医療翻訳", "コンテンツ", "ブログ", "記事作成"],
    "SNS・マーケ": ["SNS運用", "Instagram", "インスタ", "YouTube", "動画", "マーケティング"],
    "相談・コンサル": ["健康相談", "医療コンサル", "オンライン診療", "カウンセリング"],
    "資料・教材": ["患者向け", "教材", "資料作成", "マニュアル", "テキスト"],
    "求人・スタッフ": ["求人", "募集", "スタッフ", "パート", "アルバイト", "正社員", "業務委託"],
    "介護・福祉": ["介護", "福祉", "デイサービス", "特養", "老人ホーム"],
}


def extract_matched_keywords(text: str) -> list[str]:
    """テキストからマッチしたキーワードを抽出（医療・ライター・SNS全対応）"""
    matched = []
    all_keywords = REQUIRED_KEYWORDS + WRITER_KEYWORDS + SNS_KEYWORDS
    for kw in all_keywords:
        if kw in text:
            matched.append(kw)
    return list(set(matched))


def is_nursing_job(title: str, description: str = "") -> bool:
    """看護師・医療系案件かどうかを判定"""
    combined = f"{title} {description}"
    return any(kw in combined for kw in REQUIRED_KEYWORDS)


def is_writer_job(title: str, description: str = "") -> bool:
    """ライター案件かどうかを判定"""
    combined = f"{title} {description}"
    return any(kw in combined for kw in WRITER_KEYWORDS)


def is_sns_job(title: str, description: str = "") -> bool:
    """SNS運用案件かどうかを判定"""
    combined = f"{title} {description}"
    return any(kw in combined for kw in SNS_KEYWORDS)


def is_target_job(title: str, description: str = "") -> bool:
    """収集対象案件かどうかを判定（医療 OR ライター OR SNS）"""
    return is_nursing_job(title, description) or is_writer_job(title, description) or is_sns_job(title, description)


def get_categories(title: str, description: str = "") -> list[str]:
    """案件のカテゴリを判定"""
    combined = f"{title} {description}"
    categories = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            categories.append(category)
    return categories if categories else ["その他"]
