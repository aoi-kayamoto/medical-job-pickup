"""
案件分類ロジック（配布版ベース + 詐欺判定を統合）

Tier 1 = 医療系案件（看護師・医療知識が活かせる案件）
Tier 2 = 一般案件（ライター・SNS運用など）
Scam  = 詐欺・勧誘・MLM系（自動除外）
"""
import re

# ──────────────────────────────────────────
# 必須キーワード（配布版 REQUIRED_KEYWORDS そのまま）
# いずれかにマッチ → Tier 1: 医療系案件
# ──────────────────────────────────────────
MEDICAL_KEYWORDS = [
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

# 後方互換
TIER1_KEYWORDS = MEDICAL_KEYWORDS
TIER2_KEYWORDS = []

# ──────────────────────────────────────────
# ライター系キーワード → Tier 2
# ──────────────────────────────────────────
WRITER_KEYWORDS = [
    "Webライター", "Webライティング", "コンテンツライター",
    "ライター募集", "ライター案件", "記事執筆", "記事作成",
    "ブログ記事", "コラム執筆", "ライティング", "執筆",
    "文章作成", "コンテンツ制作",
]

# ──────────────────────────────────────────
# SNS運用系キーワード → Tier 2
# ──────────────────────────────────────────
SNS_KEYWORDS = [
    "SNS運用", "SNS管理", "SNS投稿", "SNSマーケティング",
    "Instagram運用", "インスタ運用", "インスタグラム運用",
    "Twitter運用", "X運用", "TikTok運用",
    "ソーシャルメディア運用", "SNSアカウント管理",
]

# SNS_WRITING_FILTER（後方互換）
SNS_WRITING_FILTER = WRITER_KEYWORDS + SNS_KEYWORDS

# ──────────────────────────────────────────
# 医療専門職ワード（これがあると信頼度アップ）
# ──────────────────────────────────────────
PROFESSIONAL_MEDICAL_WORDS = [
    "監修", "記事作成", "専門知識", "執筆", "医学的", "エビデンス",
    "校閲", "アドバイザー", "コンサルティング", "マニュアル作成",
    "講義", "セミナー", "教育", "指導",
]

# ──────────────────────────────────────────
# カテゴリラベル
# ──────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "訪問・在宅": ["訪問看護", "在宅看護", "在宅医療", "訪問介護"],
    "美容・クリニック": ["美容看護", "美容クリニック", "美容外科", "美容皮膚科", "エステ"],
    "医療ライティング": ["記事監修", "医療監修", "医療ライター", "医療翻訳", "コンテンツ", "ブログ", "記事作成"],
    "SNS・マーケ": ["SNS運用", "Instagram", "インスタ", "YouTube", "動画", "マーケティング"],
    "相談・コンサル": ["健康相談", "医療コンサル", "オンライン診療", "カウンセリング"],
    "資料・教材": ["患者向け", "教材", "資料作成", "マニュアル", "テキスト"],
    "求人・スタッフ": ["求人", "募集", "スタッフ", "パート", "アルバイト", "正社員", "業務委託"],
    "介護・福祉": ["介護", "福祉", "デイサービス", "特養", "老人ホーム"],
}

# ──────────────────────────────────────────
# 詐欺ハードブロック（即除外）
# ──────────────────────────────────────────
HARD_SCAM_KEYWORDS = [
    "ネットワークビジネス", "ネットビジネス", "MLM", "マルチ商法",
    "ねずみ講", "連鎖販売取引", "アムウェイ", "ニュースキン",
    "不労所得", "権利収入", "自動収入", "寝ながら稼げる",
    "紹介するだけで稼げる",
]

# ──────────────────────────────────────────
# 詐欺スコア制キーワード（累計で判定）
# ──────────────────────────────────────────
SOFT_SCAM_KEYWORDS: dict[str, int] = {
    "簡単に稼げる": 3, "誰でも稼げる": 3, "未経験 高収入": 2,
    "在宅 高収入": 2, "FX 副業": 3, "投資 副業": 3,
    "バイナリーオプション": 4, "友達紹介 報酬": 3,
    "モニター募集": 1, "スマホだけ": 2, "パソコン不要": 1,
    "初心者歓迎 高収入": 2, "入力するだけ": 2,
    "データ入力": 3,
    "動画編集": 3,
    "YouTube動画作成": 3,
    "YouTube動画編集": 3,
    "0件のレビュー": 4, "本人確認未提出": 4,
    "発注ルールチェック未回答": 4,
    "レビュー件数0件": 4, "本人確認未完了": 4,
    "実績作り歓迎": 4, "実績作りにおすすめ": 4,
    "未経験OK": 2, "未経験可": 2, "初心者歓迎": 2,
    "未経験歓迎": 2, "未経験者歓迎": 2,
    "20代～30代向け": 4, "20代向け": 4, "30代向け": 4,
    "ご家族構成": 4, "一人暮らし／実家暮らし": 4,
    "雇用形態・フリーランス": 4,
}

# ──────────────────────────────────────────
# 正規表現スコアパターン
# ──────────────────────────────────────────
SCAM_REGEX_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"月収\s*\d+\s*[万百千]"), 3, "高額月収の誇張"),
    (re.compile(r"(誰でも|初心者でも).{0,30}(稼げる|収入)"), 3, "初心者でも稼げる系"),
    (re.compile(r"紹介.{0,20}報酬.{0,20}仕組み"), 4, "紹介報酬の仕組み"),
    (re.compile(r"(審査なし|登録だけ|登録するだけ).{0,20}(稼|収入|報酬)"), 3, "審査なし系"),
    (re.compile(r"(スキマ|すきま|隙間|空き)時間.*(歓迎|[oO][kK]|◎|を活用|で|に)"), 3, "スキマ時間アピール"),
    (re.compile(r"未経験(◎|[oO][kK]|の方|さん|歓迎|大歓迎|から)"), 3, "未経験釣り"),
    (re.compile(r"初心者.*(の方|さん|[oO][kK]|歓迎|大歓迎|◎)"), 3, "初心者釣り"),
    (re.compile(r"実績(不問|の有無は問いません|は問いません)"), 3, "実績不問"),
    (re.compile(r"スクール"), 4, "スクール（情報商材誘導）"),
    (re.compile(r"(共感系|あるある系|あるある投稿)"), 4, "共感系・あるある系"),
    (re.compile(r"会社員"), 3, "会社員ターゲット（副業勧誘）"),
    (re.compile(r"フリーランス志望"), 4, "フリーランス志望"),
    (re.compile(r"本業と並行"), 3, "本業と並行（副業勧誘の定型）"),
    (re.compile(r"(フルネーム|お名前).{0,30}(ご年齢|年齢).{0,50}(ご職業|職業|雇用形態|応募理由|志望動機|作業時間|PC環境|パソコン)", re.DOTALL), 4, "応募フォームで個人情報収集"),
    (re.compile(r"現在の.*(職業|お仕事|働き方|雇用形態|状況)", re.DOTALL), 3, "現在の状況聞き取り"),
    # クラウドソーシング特有の怪しいパターン
    (re.compile(r"在宅[oO][kK]|在宅で.*(収入|月収|お小遣い).*([uU][pP]|アップ)"), 4, "在宅・収入UPアピール"),
]

# ──────────────────────────────────────────
# 明らかな対象外（完全除外）
# ──────────────────────────────────────────
OUT_OF_SCOPE_PATTERNS = [
    r"MLM", r"ネットワークビジネス", r"アムウェイ", r"FX", r"仮想通貨", r"投資",
    r"バイナリー", r"ギャンブル", r"ライブ配信", r"チャットレディ", r"アダルト",
    r"営業代行", r"フルコミッション営業", r"完全歩合制営業",
    r"せどり", r"転売", r"情報商材", r"代理店募集",
    r"テレアポ", r"コールセンター", r"テレマーケティング",
    r"会社登記", r"法人登記", r"行政書士", r"司法書士",
    r"記帳代行", r"経理代行", r"確定申告代行",
    r"清掃(業務|作業|スタッフ)", r"引越(し)?(作業|スタッフ)",
    r"不動産(仲介|営業|管理)", r"建築(設計|施工)",
    r"イベントスタッフ", r"展示会(営業|スタッフ)",
    r"ナレーター?(さん)?(?:の)?募集", r"ナレーション(収録|依頼)",
    r"声優(募集|オーディション)", r"音声(収録|録音|素材)",
    r"データ(収集|整理|まとめ).*リスト",
    r"スマホ(簡単|で(できる|稼げる)|作業|タスク)",
    r"ロゴ(制作|デザイン)",
    r"ECサイト(構築|制作)", r"ネットショップ(開設|構築)",
    r"(サイト|ホームページ)(制作|構築|コーディング)",
    r"サーバー(構築|移行|管理)",
    r"技術顧問", r"技術(コンサルタント|アドバイザー)",
]

# ──────────────────────────────────────────
# 明らかな常勤・出勤前提の除外（求人票特有）
# ──────────────────────────────────────────
EMPLOYMENT_EXCLUDE_PATTERNS = [
    # 雇用形態が明確に常勤のもの
    r"正社員", r"契約社員", r"派遣",
    r"完全週休二日制", r"年間休日\s*\d+\s*日",
    r"日払い", r"週払い",
    # 出勤前提が明確なもの
    r"出社必須", r"要出社", r"客先常駐",
    r"オンコール",
    r"街頭インタビュー", r"イベント救護", r"救護スタッフ",
    r"アートメイク",
]


# ──────────────────────────────────────────
# 公開インターフェース
# ──────────────────────────────────────────

def classify_job(title: str, description: str = "", source: str = "") -> dict:
    """
    案件を分類する。

    Returns:
        {
            "tier": 1 | 2 | None,
                1 = 医療系案件
                2 = 一般案件（ライター・SNS関係）
                None = 対象外
            "is_scam": bool,
            "scam_score": int,
            "scam_reasons": [str],
            "matched_keywords": [str],
            "categories": [str],
        }
    """
    combined = f"{title} {description}"
    result: dict = {
        "tier": None,
        "is_scam": False,
        "scam_score": 0,
        "scam_reasons": [],
        "matched_keywords": [],
        "categories": [],
    }

    # ── Step 1: 詐欺ハードブロック ──
    for kw in HARD_SCAM_KEYWORDS:
        if kw in combined:
            result["is_scam"] = True
            result["scam_score"] = 99
            result["scam_reasons"].append(f"ハードブロック: {kw}")
            return result

    # ── Step 2: 明らかな対象外 ──
    for pat in OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, combined):
            result["tier"] = None
            return result

    # ── Step 3: 常勤・出勤前提の除外 ──
    for pat in EMPLOYMENT_EXCLUDE_PATTERNS:
        if re.search(pat, combined):
            result["tier"] = None
            return result

    # ── Step 4: 詐欺スコア計算 ──
    score = 0
    reasons = []
    for phrase, pts in SOFT_SCAM_KEYWORDS.items():
        if phrase in combined:
            score += pts
            reasons.append(f"{phrase}(+{pts})")
    for pattern, pts, label in SCAM_REGEX_PATTERNS:
        if pattern.search(combined):
            score += pts
            reasons.append(f"{label}(+{pts})")

    result["scam_score"] = score
    result["scam_reasons"] = reasons

    # ── Step 5: 医療系かどうかチェック（配布版 is_nursing_job に相当）──
    medical_matched = [kw for kw in MEDICAL_KEYWORDS if kw in combined]

    if medical_matched:
        # 専門ワードがあればスコアを大幅緩和
        prof_matched = [w for w in PROFESSIONAL_MEDICAL_WORDS if w in combined]
        if prof_matched:
            score -= 6
        else:
            score -= 2

        # 医療案件は閾値を高めに（多少怪しくても表示してユーザーが判断）
        if score >= 8:
            result["is_scam"] = True
            return result

        result["tier"] = 1
        result["matched_keywords"] = medical_matched
        cats = [cat for cat, kws in CATEGORY_KEYWORDS.items()
                if any(kw in combined for kw in kws)]
        result["categories"] = cats if cats else ["その他"]
        return result

    # ── Step 6: ライター・SNS案件かどうか ──
    is_writer = any(kw in combined for kw in WRITER_KEYWORDS)
    is_sns = any(kw in combined for kw in SNS_KEYWORDS)

    if is_writer or is_sns:
        if score >= 5:
            result["is_scam"] = True
            return result
        result["tier"] = 2
        result["matched_keywords"] = [kw for kw in WRITER_KEYWORDS + SNS_KEYWORDS if kw in combined]
        cats = [cat for cat, kws in CATEGORY_KEYWORDS.items()
                if any(kw in combined for kw in kws)]
        result["categories"] = cats if cats else ["その他"]
        return result

    # ── Step 7: それ以外は対象外 ──
    result["tier"] = None
    return result


def extract_matched_keywords(text: str) -> list[str]:
    """後方互換用"""
    return [kw for kw in MEDICAL_KEYWORDS if kw in text]


def is_nursing_job(title: str, description: str = "") -> bool:
    """後方互換用 — classify_job を使うことを推奨"""
    r = classify_job(title, description)
    return r["tier"] == 1 and not r["is_scam"]
