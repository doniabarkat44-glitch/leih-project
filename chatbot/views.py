
import os
import re
import json
import requests
from urllib.parse import quote_plus
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

SYSTEM_PROMPT = """أنت «مساعد مبتكر»، مساعد ودود بيساعد الأطفال والكبار يحولوا أفكارهم لألعاب. اتكلم بالعربية المصرية البسيطة.

لو السؤال عام ومش عن لعبة معينة: جاوب بشرح واضح ومختصر، من غير كود لعبة ومن غير TITLE أو VIDEOS.

لو المستخدم طلب لعبة أو فكرة لعبة، التزم بالترتيب ده بالظبط:

TITLE: اسم اللعبة في سطر واحد

## فكرة اللعبة
(سطرين بالكتير)

## طرق البداية
(من ٥ لـ ٧ خطوات مرقمة وواضحة وحدد برنامج مناسب للمبتدئ زي Scratch أو Roblox Studio)

VIDEOS: عبارة بحث يوتيوب ١ | عبارة بحث يوتيوب ٢ | عبارة بحث يوتيوب ٣

وبعدها كود لعبة كاملة جوه بلوك `html ... ``` بدون أي كلام بعد الكود.

قواعد إلزامية لبناء لعبة حقيقية وشغالة ومختلفة (ممنوع استخدام <canvas> وممنوع الاختصار):
1. مساحة لعب واضحة ومحددة الأبعاد:
   - اجعل ساحة اللعب `div` أبعاده واضحة ومثلاً `width: 300px; height: 380px; position: relative; overflow: hidden; margin: 0 auto;` داخل كارت مرتب في المنتصف على خلفية داكنة `#0f172a`.
   - في سباق السيارات: اجعل الطريق رأسياً بطول الساحة (`height: 100%`) مع حارات واضحة وخطوط متقطعة متحركة للأسفل، وسيارة لاعب كرتونية بـ `<svg>` في الأسفل وعربيات منافسة كرتونية بـ `<svg>` تتحرك في الحارات مع تفادي التصادم وتجاوز/تجميع نقاط.
   - في ألعاب القطط أو غيرها: صمّم بيئة واضحة وميكانيكية مختلفة غير مكررة تناسب الفكرة فعلاً (مثلاً قطة كرتونية بـ `<svg>` تتحرك وتطارد أهدافاً وتتفادى عوائق/مطاردين)، وليس مجرد تكرار أعمى لنفس القالب.

2. أزرار تحكم شغالة وواضحة على الشاشة والكيبورد:
   - ضع أزرار تحكم واضحة وكبيرة باللمس والماوس تحت ساحة اللعب بالـ IDs: `left` و `right` (و `up` و `down` عند الحاجة للحركة في ٤ اتجاهات).
   - اربط كل زر بـ `pointerdown` و `pointerup` و `pointerleave` و `pointercancel` مع `e.preventDefault()` لتحديث متغير الحالة `keys`، واربط أسهم الكيبورد (`ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`) بنفس المتغير، وحرّك اللاعب داخل `requestAnimationFrame`.

3. النقاط، القلوب، الصوت، والفوز/الخسارة:
   - شريط علوي يعرض النقاط، القلوب ❤️❤️❤️، وزر الصوت `<button id="soundBtn">🔊</button>` الذي يستخدم Web Audio API (`AudioContext`) لأصوات النقاط والتصادم والفوز/الخسارة داخل `try/catch`.
   - عند الخسارة (انتهاء القلوب) أو الفوز (الوصول للهدف المطلوب)، أظهر صندوق نتيجة واضح داخل ساحة اللعب ("لقد خسرت!" أو "لقد ربحت!") مع زر `<button id="restartBtn">العب تاني</button>` يعيد ضبط كل المتغيرات ويبدأ اللعب فوراً.
   - تأكد من إغلاق كل الأقواس والدوال وعدم وجود أي أخطاء، ولا تكتب أي شرح بعد بلوك الكود.
"""

FENCE = chr(96) * 3
BT = chr(96)

GROQ_URL = "https://api.groq.com/openai/v1"

PREFERRED = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
SKIP_WORDS = ("whisper", "tts", "guard", "playai", "orpheus", "embed")

_model_cache = {"name": None}


def home(request):
    return render(request, "index.html")


def pick_model(api_key):
    if _model_cache["name"]:
        return _model_cache["name"]
    r = requests.get(
        f"{GROQ_URL}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    r.raise_for_status()
    available = [m["id"] for m in r.json().get("data", [])]
    print("Groq available models:", available)
    for name in PREFERRED:
        if name in available:
            _model_cache["name"] = name
            return name
    for name in available:
        if not any(w in name.lower() for w in SKIP_WORDS):
            _model_cache["name"] = name
            return name
    raise RuntimeError("no usable model")


def youtube_search_url(query):
    return "https://www.youtube.com/results?search_query=" + quote_plus(query)


def parse_reply(text):
    game_html = None

    m = re.search(
        FENCE + r"(?:html)?\s*(<(?:!doctype|html)[\s\S]*?)" + FENCE, text, re.I
    )
    if m:
        game_html = m.group(1).strip()
        text = text[: m.start()] + text[m.end():]
    else:
        m = re.search(FENCE + r"(?:html)?\s*<(?:!doctype|html)", text, re.I)
        if m:
            text = text[: m.start()]

    if game_html is not None and len(game_html) < 80:
        game_html = None

    title = None
    m = re.search(r"^[ \t]*TITLE[ \t]*[:：][ \t]*(.+)$", text, re.M | re.I)
    if m:
        title = m.group(1).strip().strip("*# " + BT)
        text = text[: m.start()] + text[m.end():]

    queries = []
    m = re.search(r"^[ \t]*VIDEOS[ \t]*[:：][ \t]*(.+)$", text, re.M | re.I)
    if m:
        queries = [q.strip(" *\"" + BT) for q in m.group(1).split("|")]
        queries = [q for q in queries if q][:3]
        text = text[: m.start()] + text[m.end():]

    if title and not queries:
        queries = [f"{title} tutorial", f"{title} Scratch"]

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    videos = [{"title": q, "url": youtube_search_url(q)} for q in queries]

    if game_html and not title:
        title = "لعبتك"

    return text, title, game_html, videos


@csrf_exempt
@require_POST
def ask_ai(request):
    try:
        data = json.loads(request.body)
        question = data.get("question", "").strip()[:1000]

        if not question:
            return JsonResponse({"error": "اكتبي سؤالك الأول."}, status=400)

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return JsonResponse({"error": "مفتاح Groq غير موجود."}, status=500)

        model = pick_model(api_key)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 6000,
        }
        if "gpt-oss" in model:
            payload["reasoning_effort"] = "low"

        response = requests.post(
            f"{GROQ_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )

        if response.status_code != 200:
            print("Groq error:", response.status_code, response.text[:400])
            _model_cache["name"] = None
            return JsonResponse(
                {"error": "خدمة الذكاء الاصطناعي غير متاحة حاليًا، جربي تاني."},
                status=502,
            )

        raw = (response.json()["choices"][0]["message"].get("content") or "").strip()
        if not raw:
            return JsonResponse({"error": "الرد طلع فاضي، جربي تاني."}, status=502)

        answer, game_title, game_html, videos = parse_reply(raw)

        if not answer and not game_html:
            return JsonResponse({"error": "الرد طلع فاضي، جربي تاني."}, status=502)

        return JsonResponse(
            {
                "answer": answer or "اتفضلي، دي لعبتك 🎮",
                "game_title": game_title,
                "game_html": game_html,
                "videos": videos,
            }
        )

    except Exception as e:
        print("Groq error:", e)
        return JsonResponse(
            {"error": "حصلت مشكلة في الرد. جربي تاني بعد شوية."},
            status=500,
        )