# -*- coding: utf-8 -*-
"""
Пакетный переводчик JSON-каталогов Claude Desktop EN -> RU.
Эндпоинт: clients5.google.com (dict-chrome-ex) — быстрый, без блокировок.
Батчи по 25 строк, 4 потока, кэш, защита плейсхолдеров, ICU-сегментация.
"""
import json, re, sys, time, urllib.request, urllib.parse, os, threading
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
# вход: извлечённый en-US.json из ion-dist.asar новой версии (аргумент или original/)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, 'original', 'en-US.json')
DST = os.path.join(BASE, '..', 'translations', 'ru.json')
CACHE = os.path.join(BASE, '..', 'translations', 'cache.json')

ICU_RE = re.compile(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*),\s*(plural|select|selectordinal)\s*,')
PH_RE = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[a-z]+(?:\s*:\s*[^{}]+)?)*)\}')

_print_lock = threading.Lock()
BATCH = 25
WORKERS = 4


def translate_batch(lines, sl='en', tl='ru', retries=6):
    """Перевод списка строк одним запросом. Возвращает список переводов или None."""
    text = '\n'.join(lines)
    url = ("https://clients5.google.com/translate_a/t?client=dict-chrome-ex"
           f"&sl={sl}&tl={tl}&q=" + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for attempt in range(retries):
        try:
            r = urllib.request.urlopen(req, timeout=30)
            d = json.loads(r.read().decode())
            # формат: ["все строки через \n"] или [["перевод","ориг"]...]
            if isinstance(d, list):
                if isinstance(d[0], str):
                    parts = d[0].split('\n')
                else:
                    parts = [x[0] for x in d]
                if len(parts) == len(lines):
                    return parts
            return None
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 + attempt)


class Marker:
    def __init__(self):
        self.map = {}
        self.n = 0

    def _add(self, original):
        m = f"⟦{self.n}⟧"
        self.map[m] = original
        self.n += 1
        return m

    def protect(self, text):
        return PH_RE.sub(lambda m: self._add(m.group(0)), text)

    def restore(self, text):
        for m, orig in self.map.items():
            text = text.replace(m, orig)
        return text


def segment_icu(text):
    """Разбор ICU-строки на (сегмент, is_shell)."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = ICU_RE.search(text, i)
        if not m:
            out.append((text[i:], False))
            break
        if m.start() > i:
            out.append((text[i:m.start()], False))
        j = m.start()
        depth = 0
        while j < n:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = text[m.start():j + 1]
        parts = []
        k = 0
        while k < len(block):
            bm = re.search(r'\{([^{}]*)\}', block[k:])
            if not bm:
                parts.append((block[k:], True))
                break
            pre = block[k:k + bm.start()]
            if pre:
                parts.append((pre, True))
            parts.append(('{', True))
            inner = bm.group(1)
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', inner.strip()):
                parts.append((inner, True))
            else:
                parts.append((inner, False))
            parts.append(('}', True))
            k = k + bm.end()
        for p, is_shell in parts:
            if is_shell or ICU_RE.search(p):
                out.append((p, True))
            else:
                out.append((p, False))
        i = j + 1
    return [s for s in out if s[0] != '']


def apply_glossary(text):
    fixes = {
        'Клод': 'Claude', 'КЛОД': 'Claude', 'клод': 'Claude',
        'клода': 'Claude', 'Клода': 'Claude', 'клоду': 'Claude', 'Клоду': 'Claude',
        'клодом': 'Claude', 'Клодом': 'Claude', 'клоде': 'Claude', 'Клоде': 'Claude',
        'Клоуд': 'Claude', 'клоуд': 'Claude', 'кло́д': 'Claude',
        'Антропик': 'Anthropic', 'антропик': 'Anthropic',
    }
    for bad, good in fixes.items():
        text = re.sub(r'(?<![A-Za-zА-Яа-яёЁ])' + re.escape(bad) + r'(?![A-Za-zА-Яа-яёЁ])', good, text)
    return text


def main():
    os.makedirs(os.path.join(BASE, 'translated'), exist_ok=True)
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding='utf-8'))
    en = json.load(open(SRC, encoding='utf-8'))
    keys = list(en.keys())
    values = [en[k] for k in keys]
    print(f'ключей: {len(keys)}, кэш: {len(cache)}')

    todo_vals = [v for v in dict.fromkeys(values) if v not in cache]
    print(f'уникальных к переводу: {len(todo_vals)}')

    # подготовка: защищённые тексты
    # protected_map: value -> ('icu', [(protected_seg, is_shell, orig_seg)...]) | ('plain', protected, marker) | None
    protected_map = {}
    all_texts = []
    for v in todo_vals:
        if ICU_RE.search(v):
            segs = segment_icu(v)
            prot_segs = []
            for seg, is_shell in segs:
                if is_shell:
                    prot_segs.append((seg, True, seg))
                else:
                    mk = Marker()
                    p = mk.protect(seg)
                    prot_segs.append((p, False, seg, mk))
                    if re.sub(r'⟦\d+⟧|\s', '', p):
                        all_texts.append(p)
            protected_map[v] = ('icu', prot_segs)
        else:
            mk = Marker()
            p = mk.protect(v)
            if not re.sub(r'⟦\d+⟧|\s', '', p):
                protected_map[v] = None
            else:
                protected_map[v] = ('plain', p, mk)
                all_texts.append(p)

    uniq = list(dict.fromkeys(all_texts))
    batches = [uniq[i:i + BATCH] for i in range(0, len(uniq), BATCH)]
    print(f'текстов: {len(uniq)}, батчей: {len(batches)}')

    translations = {}
    t0 = time.time()
    done = [0]

    def worker(batch):
        for attempt in range(6):
            try:
                res = translate_batch(batch)
                if res is not None:
                    return list(zip(batch, res))
            except Exception:
                time.sleep(0.5 + attempt)
        out = []
        for line in batch:
            try:
                r = translate_batch([line])
                out.append((line, r[0] if r else line))
            except Exception:
                out.append((line, line))
        return out

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for pairs in ex.map(worker, batches):
            for src, dst in pairs:
                translations[src] = dst
            done[0] += 1
            if done[0] % 50 == 0:
                el = time.time() - t0
                rate = (done[0] * BATCH) / el
                with _print_lock:
                    print(f'{done[0]}/{len(batches)} батчей | {rate:.0f} строк/с | '
                          f'осталось ~{(len(batches) - done[0]) * BATCH / max(rate, 1) / 60:.1f} мин', flush=True)

    # сборка результатов
    results = {}
    for v in todo_vals:
        p = protected_map[v]
        if p is None:
            results[v] = v
            continue
        if p[0] == 'icu':
            out = []
            for item in p[1]:
                if len(item) == 3:
                    _, is_shell, seg = item
                    out.append(seg)
                else:
                    prot, _, seg, mk = item
                    tr = translations.get(prot, prot)
                    out.append(mk.restore(tr))
            results[v] = apply_glossary(''.join(out))
        else:
            prot, mk = p[1], p[2]
            tr = translations.get(prot, prot)
            results[v] = apply_glossary(mk.restore(tr))

    cache.update(results)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)

    out = {}
    for k in keys:
        out[k] = cache.get(en[k], en[k])
    json.dump(out, open(DST, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    n_translated = sum(1 for k in keys if out[k] != en[k])
    print(f'Готово за {(time.time() - t0) / 60:.1f} мин: {DST}')
    print(f'ключей переведено: {n_translated}/{len(keys)}')


if __name__ == '__main__':
    main()
