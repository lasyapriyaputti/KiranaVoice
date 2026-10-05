"""Message templates (replaces the long if/elif language chains) + localized item names."""
from i18n import ITEM_TRANSLATIONS


def lang_key(lang: str) -> str:
    name = lang.split(" ")[0]
    return "Hindi" if name == "Hinglish" else name


def get_localized_item_name(raw_name: str, lang: str) -> str:
    """Exact match only (the old substring fallback could pick the wrong translation)."""
    clean = raw_name.split(" (")[0].strip()
    return ITEM_TRANSLATIONS.get(clean, {}).get(lang, clean)


def pick(table: dict, lang: str, key: str = None):
    row = table.get(lang_key(lang), table["English"])
    if key is None:
        return row
    return row.get(key, table["English"][key])


REPEAT = {
    "English": {"STOCK_IN": "Restock received: {items}.", "STOCK_OUT": "Sale: {items}."},
    "Telugu": {"STOCK_IN": "దుకాణంలో దిగుమతి అయింది: {items}.", "STOCK_OUT": "అమ్మకం జరిగింది: {items}."},
    "Tamil": {"STOCK_IN": "கடைக்கு புதிய வரவு: {items}.", "STOCK_OUT": "விற்பனை செய்யப்பட்டது: {items}."},
    "Kannada": {"STOCK_IN": "ಅಂಗಡಿಗೆ ಹೊಸ ದಾಸ್ತಾನು ಬಂದಿದೆ: {items}.", "STOCK_OUT": "ಮಾರಾಟ ದಾಖಲಾಗಿದೆ: {items}."},
    "Bengali": {"STOCK_IN": "দোকানে নতুন স্টক এসেছে: {items}।", "STOCK_OUT": "পণ্য বিক্রয় হয়েছে: {items}।"},
    "Marathi": {"STOCK_IN": "दुकानात नवीन माल आला: {items}.", "STOCK_OUT": "सामान विकले गेले: {items}."},
    "Gujarati": {"STOCK_IN": "દુકાનમાં નવો માલ આવ્યો: {items}.", "STOCK_OUT": "વેચાણ નોંધાયું: {items}."},
    "Malayalam": {"STOCK_IN": "കടയിലേക്ക് പുതിയ സ്റ്റോക്ക് എത്തി: {items}.", "STOCK_OUT": "വിൽപന രേഖപ്പെടുത്തി: {items}."},
    "Punjabi": {"STOCK_IN": "ਦੁਕਾਨ ਵਿੱਚ ਨਵਾਂ ਮਾਲ ਆਇਆ: {items}।", "STOCK_OUT": "ਵਿਕਰੀ ਦਰਜ ਕੀਤੀ ਗਈ: {items}।"},
    "Hindi": {"STOCK_IN": "दुकान में माल आया: {items}।", "STOCK_OUT": "सामान बिका: {items}।"},
}

WARN = {
    "English": "Tomorrow's demand for {item} is about {demand} {unit}, but only {stock} {unit} left. Order {order} more today!",
    "Telugu": "నమస్కారం అండి! రేపు {item} డిమాండ్ దాదాపు {demand} {unit} ఉంటుంది, కానీ ప్రస్తుతం {stock} మాత్రమే ఉన్నాయి. వెంటనే మరో {order} ఆర్డర్ చేయండి!",
    "Tamil": "வணக்கம்! நாளை {item} தேவை சுமார் {demand} {unit} இருக்கும், ஆனால் தற்போது {stock} மட்டுமே உள்ளது. உடனடியாக {order} ஆர்டர் செய்யவும்!",
    "Kannada": "ನಮಸ್ಕಾರ! ನಾಳೆ {item} ಬೇಡಿಕೆ ಸುಮಾರು {demand} {unit} ಇರುತ್ತದೆ, ಆದರೆ ಪ್ರಸ್ತುತ {stock} ಮಾತ್ರ ಇವೆ. ತಕ್ಷಣವೇ {order} ಆರ್ಡರ್ ಮಾಡಿ!",
    "Bengali": "নমস্কার! আগামীকাল {item} চাহিদা প্রায় {demand} {unit} হবে, কিন্তু মাত্র {stock} বাকি আছে। অবিলম্বে আরও {order} অর্ডার করুন!",
    "Marathi": "नमस्कार! उद्या {item} मागणी सुमारे {demand} {unit} असेल, पण फक्त {stock} शिल्लक आहे. लगेच {order} मागवून घ्या!",
    "Gujarati": "નમસ્તે! આવતીકાલે {item} માંગ આશરે {demand} {unit} રહેશે, પરંતુ માત્ર {stock} બાકી છે. તરત જ બીજા {order} મંગાવી લો!",
    "Malayalam": "നമസ്കാരം! നാളെ {item} ആവശ്യം ഏകദേശം {demand} {unit} ആയിരിക്കും, എന്നാൽ {stock} മാത്രമേ ഉള്ളൂ. ഉടൻ {order} കൂടി ഓർഡർ ചെയ്യുക!",
    "Punjabi": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਕੱਲ੍ਹ {item} ਦੀ ਮੰਗ ਲਗਭਗ {demand} {unit} ਹੋਵੇਗੀ, ਪਰ ਸਿਰਫ {stock} ਬਚੇ ਹਨ। ਤੁਰੰਤ {order} ਹੋਰ ਮੰਗਵਾਓ!",
    "Hindi": "नमस्ते भैया! कल {item} की मांग लगभग {demand} {unit} होगी, लेकिन केवल {stock} बचे हैं। तुरंत {order} और मंगवा लीजिए!",
}

CHECK = {
    "English": "{item}: {stock} {unit} left.",
    "Telugu": "{item}: {stock} {unit} ఉన్నాయి.",
    "Tamil": "{item}: {stock} {unit} உள்ளது.",
    "Kannada": "{item}: {stock} {unit} ಇದೆ.",
    "Hindi": "{item}: {stock} {unit} बचा है।",
}

# Extra UI strings. Languages not listed fall back to English: add them as you get native review.
UI = {
    "English": {
        "no_tx": "No transactions recorded yet today.", "all_safe": "All items have enough stock.",
        "not_understood": "Could not understand. Please speak again.", "undo_btn": "↩️ Undo last entry",
        "undo_done": "Last transaction undone.", "balance": "Balance",
        "oversold": "Sold more than in stock! Only available stock was deducted.",
        "assumed": "Quantity not heard, assumed 1. Please correct it.",
        "nothing_undo": "Nothing to undo.",
    },
    "Telugu": {
        "no_tx": "ఈ రోజు ఇంకా లావాదేవీలు నమోదు కాలేదు.", "all_safe": "అన్ని వస్తువుల స్టాక్ తగినంతగా ఉంది.",
        "not_understood": "అర్థం కాలేదు. దయచేసి మళ్లీ మాట్లాడండి.", "undo_btn": "↩️ చివరి నమోదును రద్దు చేయండి",
        "undo_done": "చివరి లావాదేవీ రద్దు చేయబడింది.", "balance": "నిల్వ",
        "oversold": "స్టాక్ కంటే ఎక్కువ అమ్మకం! ఉన్నది మాత్రమే తీసివేయబడింది.",
        "assumed": "సంఖ్య వినబడలేదు, 1 అనుకున్నాను. సరిచేయండి.", "nothing_undo": "రద్దు చేయడానికి ఏమీ లేదు.",
    },
    "Hindi": {
        "no_tx": "आज अभी तक कोई लेन-देन दर्ज नहीं हुआ।", "all_safe": "सभी सामान का स्टॉक पर्याप्त है।",
        "not_understood": "समझ नहीं आया। कृपया दोबारा बोलें।", "undo_btn": "↩️ आखिरी एंट्री रद्द करें",
        "undo_done": "आखिरी लेन-देन रद्द किया गया।", "balance": "बचा",
        "oversold": "स्टॉक से ज़्यादा बिक्री! सिर्फ़ उपलब्ध मात्रा घटाई गई।",
        "assumed": "संख्या सुनाई नहीं दी, 1 मान लिया। ठीक करें।", "nothing_undo": "रद्द करने के लिए कुछ नहीं है।",
    },
    "Tamil": {
        "no_tx": "இன்று இதுவரை பதிவுகள் இல்லை.", "all_safe": "அனைத்து பொருட்களும் போதுமான இருப்பில் உள்ளன.",
        "not_understood": "புரியவில்லை. மீண்டும் பேசவும்.", "undo_btn": "↩️ கடைசி பதிவை ரத்து செய்",
        "undo_done": "கடைசி பதிவு ரத்து செய்யப்பட்டது.", "balance": "இருப்பு",
        "oversold": "இருப்பை விட அதிக விற்பனை! உள்ளதை மட்டும் கழித்தேன்.",
        "assumed": "எண் கேட்கவில்லை, 1 என எடுத்தேன். திருத்தவும்.", "nothing_undo": "ரத்து செய்ய எதுவும் இல்லை.",
    },
    "Kannada": {
        "no_tx": "ಇಂದು ಇನ್ನೂ ವ್ಯವಹಾರ ದಾಖಲಾಗಿಲ್ಲ.", "all_safe": "ಎಲ್ಲಾ ಸರಕುಗಳ ದಾಸ್ತಾನು ಸಾಕಷ್ಟಿದೆ.",
        "not_understood": "ಅರ್ಥವಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಮಾತನಾಡಿ.", "undo_btn": "↩️ ಕೊನೆಯ ದಾಖಲೆ ರದ್ದುಮಾಡಿ",
        "undo_done": "ಕೊನೆಯ ವ್ಯವಹಾರ ರದ್ದಾಗಿದೆ.", "balance": "ಬಾಕಿ",
        "oversold": "ದಾಸ್ತಾನಿಗಿಂತ ಹೆಚ್ಚು ಮಾರಾಟ! ಇರುವಷ್ಟೇ ಕಳೆಯಲಾಗಿದೆ.",
        "assumed": "ಸಂಖ್ಯೆ ಕೇಳಿಸಲಿಲ್ಲ, 1 ಎಂದು ಭಾವಿಸಿದೆ. ಸರಿಪಡಿಸಿ.", "nothing_undo": "ರದ್ದುಮಾಡಲು ಏನೂ ಇಲ್ಲ.",
    },
}
