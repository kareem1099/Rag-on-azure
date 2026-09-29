import re

ARABIC_MARKS = 'ً-ٰٟۖ-ۭـ'
ALEF_FORMS = 'أإآٱ'

GENERAL_STOPWORDS = {
    'ما', 'ماذا', 'هل', 'كيف', 'لماذا', 'متي', 'اين', 'كم', 'اي',
    'من', 'في', 'عن', 'علي', 'الي', 'مع', 'الا', 'حتي', 'عند', 'بين', 'منذ',
    'هو', 'هي', 'هم', 'هن', 'انا', 'نحن', 'انت', 'انتم',
    'هذا', 'هذه', 'ذلك', 'تلك', 'هولاء', 'الذي', 'التي', 'الذين', 'اللذان',
    'ان', 'او', 'ثم', 'بل', 'لكن', 'قد', 'لا', 'لم', 'لن', 'ليس', 'كل', 'بعض',
    'كان', 'كانت', 'يكون', 'تكون', 'به', 'بها', 'له', 'لها', 'فيه', 'فيها',
    'عليه', 'عليها', 'منه', 'منها', 'و', 'ف', 'يا',
}

QUESTION_META_WORDS = {
    'الكتاب', 'الكتب', 'حسب', 'بحسب', 'كما', 'ورد', 'وردت', 'الوارد', 'ذكر', 'ذكرها', 'ذكره', 'يذكر',
    'يري', 'يعرض', 'يعرضه', 'يشرح', 'يشرحه', 'يوضح', 'يبني', 'يربط', 'يفسران', 'بينها', 'بينه',
    'استشهد', 'المقصود', 'مبدا', 'موقف', 'قارن', 'مساله', 'نفس', 'معا', 'وكيف', 'ولماذا', 'وما',
    'وهل', 'وكم', 'وعلي', 'اساس', 'تحديد', 'تفصيل', 'التفصيلي',
}

HONORIFIC_WORDS = {
    'صلي', 'وسلم', 'الله', 'تعالي', 'رضي', 'عنه', 'عنها', 'عنهم', 'عز', 'وجل', 'جل', 'وعلا',
    'النبي', 'رسول',
}

ARABIC_STOPWORDS = GENERAL_STOPWORDS | QUESTION_META_WORDS | HONORIFIC_WORDS


def normalize_arabic(text: str) -> str:
    text = re.sub(f'[{ARABIC_MARKS}]', '', text)
    text = re.sub(f'[{ALEF_FORMS}]', 'ا', text)
    text = text.replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_arabic_sql(expression: str) -> str:
    return (
        f"translate(regexp_replace({expression}, '[{ARABIC_MARKS}]', '', 'g'), "
        f"'{ALEF_FORMS}ةى', 'ااااهي')"
    )


def build_keyword_query(text: str) -> str:
    tokens = [
        token for token in normalize_arabic(text).split()
        if token not in ARABIC_STOPWORDS and len(token) > 1
    ]
    return ' or '.join(dict.fromkeys(tokens))
