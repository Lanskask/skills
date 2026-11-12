#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Build synthetic test books (deterministic, no copyright issues).

  --kind en     5 chapters + contents/preface/index, 2-level outline, running headers, page numbers,
                hyphenated line breaks, bold terms, captions, equations.     (~45 pages)
  --kind noout  same pages but with NO PDF outline  -> exercises the heading-regex fallback
  --kind scan   a few en pages rasterised to images only -> exercises the OCR fallback
  --kind ru     a small Russian book (3 chapters) with outline
  --kind fig    3 short chapters with vector figures + captions (figure detection/cropping tests)
  --kind book2  no bookmarks, split running heads, code listing, derivation lines, garbled problem (mimics a real textbook)
  --offset N    (en/noout) front matter of N pages numbered i, ii, ...; printed page 1 = PDF page N+1
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pymupdf

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
             Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/msttcorefonts")]
CANDIDATES = [("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf"), ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf"),
              ("Arial.ttf", "Arial_Bold.ttf", "Arial_Italic.ttf")]


def find_fonts() -> tuple[str, str, str]:
    for r, b, i in CANDIDATES:
        for d in FONT_DIRS:
            if (d / r).exists() and (d / b).exists() and (d / i).exists():
                return str(d / r), str(d / b), str(d / i)
    raise SystemExit("no TTF font with Cyrillic found; install Arial or DejaVu")


EN = {
    "Introduction to Plasma": [
        "A **plasma** is a quasi-neutral gas of charged and neutral particles that exhibits collective behaviour.",
        "The **Debye length** is the distance over which a charge imbalance is screened by the surrounding particles.",
        "Plasmas make up more than 99 percent of the visible matter in the universe, from stars to the solar wind.",
        "Quasi-neutrality means that on scales larger than the Debye length the electron and ion densities are nearly equal.",
        "In a laboratory, a plasma is created by heating a gas or by applying a strong electric or microwave field.",
        "The **plasma parameter** counts the number of particles inside a Debye sphere and must be large for collective effects.",
        "Collisions between charged particles are long-range, so each particle interacts with many others at once.",
        "Fusion devices such as tokamaks confine a hot plasma with magnetic fields because no material wall can survive its temperature.",
        "Low-temperature plasmas are used for etching semiconductors, for lighting, and for surface treatment of materials.",
        "Understanding when a gas becomes a plasma is the first step before any simulation can be designed.",
    ],
    "Charged Particle Motion": [
        "A charged particle in a uniform magnetic field moves along a helix around a field line.",
        "The **Larmor radius** is the radius of the circular part of that helix and grows with the particle speed.",
        "The **gyrofrequency** is the rate at which the particle circles the field line and depends only on charge, mass and field strength.",
        "When an electric field is added perpendicular to the magnetic field, the particle drifts at the **E cross B drift** velocity.",
        "This drift is the same for electrons and ions, so it carries no net current by itself.",
        "A gradient in the magnetic field makes the Larmor radius change along the orbit and produces a slow sideways drift.",
        "The magnetic moment of a gyrating particle is an adiabatic invariant that stays nearly constant when the field changes slowly.",
        "Particles trapped between two regions of strong field bounce back and forth, which is the idea of a magnetic mirror.",
        "Numerical orbit integrators must resolve the gyration, otherwise the energy of the particle drifts artificially.",
        "The Boris algorithm rotates the velocity exactly in the magnetic field and is the standard pusher in particle codes.",
    ],
    "Plasma Waves": [
        "A plasma supports waves because displaced electrons are pulled back by the electric field of the ions.",
        "The **plasma frequency** is the natural oscillation frequency of electrons and scales as the square root of the density.",
        "A **dispersion relation** links the wave frequency to its wavenumber and tells how fast a wave packet travels.",
        "Langmuir waves are electrostatic oscillations whose frequency is close to the plasma frequency for long wavelengths.",
        "Thermal motion adds a correction to the dispersion relation proportional to the square of the wavenumber.",
        "Waves can exchange energy with particles that move at the wave phase velocity, an effect known as Landau damping.",
        "Electromagnetic waves cannot propagate in a plasma when their frequency is lower than the plasma frequency.",
        "In a magnetised plasma the wave modes split into ordinary and extraordinary polarisations with different cutoffs.",
        "The upper hybrid resonance combines the plasma frequency and the gyrofrequency in a single expression.",
        "Measuring the wave spectrum is a practical way to diagnose the density of a laboratory plasma.",
    ],
    "Particle-in-Cell Methods": [
        "The **particle-in-cell** method follows many computational particles while computing fields on a fixed grid.",
        "Each computational particle, called a **macroparticle**, represents a large number of real electrons or ions.",
        "Charge is assigned from the particle positions to the grid nodes with a weighting function such as cloud-in-cell.",
        "The field solver then computes the electric field from the grid charge density by solving the Poisson equation.",
        "Forces are interpolated back from the grid to the particle positions using the same weighting function.",
        "The leapfrog scheme advances positions and velocities on staggered time levels and is second-order accurate.",
        "To avoid numerical heating the grid spacing must resolve the Debye length of the simulated plasma.",
        "The time step must be smaller than a fraction of the inverse plasma frequency for the scheme to stay stable.",
        "Statistical noise decreases only with the square root of the number of macroparticles per cell.",
        "Monte Carlo collision modules are added to the loop to model ionisation and elastic scattering of electrons.",
    ],
    "Electron Cyclotron Resonance": [
        "**Electron cyclotron resonance** heating occurs when the microwave frequency equals the electron gyrofrequency.",
        "At resonance the rotating electric field of the wave stays in phase with the gyrating electron and keeps accelerating it.",
        "A typical ECR ion source uses a 2.45 GHz microwave and a magnetic field of about 875 gauss at the resonance surface.",
        "The **resonance condition** therefore fixes the magnetic field strength for a given microwave frequency.",
        "Heated electrons ionise the background gas through collisions and sustain a dense plasma at low pressure.",
        "Because the plasma density rises, the wave can reach a cutoff when the plasma frequency exceeds the wave frequency.",
        "Magnetic mirror geometry confines the energetic electrons and lets ions leave through the open end of the device.",
        "Simulating ECR requires a kinetic description since the heating is a resonant wave-particle interaction.",
        "Full-wave codes solve Maxwell equations for the microwave field while particle codes track the electron orbits.",
        "The competition between heating, collisions and losses determines the electron energy distribution of the source.",
    ],
}
EQ = {
    "Introduction to Plasma": "λD = √(ε0 kB Te / (n e²))",
    "Charged Particle Motion": "rL = m vp / (|q| B) ≈ vp / ωc",
    "Plasma Waves": "ω² = ωp² + 3 k² vth² ≈ ωp²",
    "Particle-in-Cell Methods": "v(n+½) = v(n−½) + (q/m) E(n) Δt ± ...",
    "Electron Cyclotron Resonance": "ω = ωce = e B / me",
}
# equations drawn with real sub/superscript spans (level -1 sub, +1 sup), like a LaTeX-typeset PDF
EQP = {
    "Introduction to Plasma": [("λ", 0), ("D", -1), (" = √(ε", 0), ("0", -1), (" k", 0), ("B", -1), (" T", 0), ("e", -1),
                               (" / (n e", 0), ("2", 1), ("))", 0)],
    "Charged Particle Motion": [("r", 0), ("L", -1), (" = m v", 0), ("p", -1), (" / (|q| B) ≈ v", 0), ("p", -1), (" / ω", 0), ("c", -1)],
}
RU = {
    "Введение в моделирование": [
        "**Моделирование** называется вычислительным экспериментом, в котором свойства системы изучают на компьютере.",
        "Модель плазмы должна учитывать длину Дебая, иначе коллективные эффекты будут потеряны.",
        "Численная схема разбивает пространство на ячейки сетки и время на небольшие шаги.",
        "Хороший вычислительный эксперимент начинается с вопроса, на который нужно ответить числом.",
        "Результаты моделирования сравнивают с аналитическими оценками и данными измерений.",
        "Погрешность метода зависит от шага сетки и шага по времени одновременно.",
    ],
    "Столкновения в плазме": [
        "**Частота столкновений** — это число соударений частицы в единицу времени.",
        "Кулоновские столкновения в плазме являются дальнодействующими и происходят с малым изменением импульса.",
        "Электроны в разряде теряют энергию при упругих и неупругих столкновениях с атомами газа.",
        "Метод Монте-Карло позволяет описывать столкновения случайным выбором события на каждом шаге.",
        "Сечение рассеяния определяет вероятность столкновения при заданной энергии электрона.",
        "При низком давлении газа средняя длина свободного пробега становится сравнима с размером камеры.",
    ],
    "Численная устойчивость": [
        "**Устойчивость** схемы означает, что ошибки не растут бесконтрольно от шага к шагу.",
        "Шаг по времени должен быть меньше доли обратной плазменной частоты.",
        "Слишком крупная сетка приводит к численному нагреву частиц и нефизичному росту энергии.",
        "Условие Куранта связывает шаг по времени, шаг сетки и скорость распространения волны.",
        "Проверять устойчивость полезно на простой задаче с известным аналитическим решением.",
        "Сохранение энергии в расчёте служит быстрым индикатором численных проблем.",
    ],
}


class Book:
    def __init__(self, title: str, header_book: str, lang: str):
        self.doc = pymupdf.open()
        self.reg, self.bold, self.ital = find_fonts()
        self.f = {k: pymupdf.Font(fontfile=v) for k, v in (("r", self.reg), ("b", self.bold), ("i", self.ital))}
        self.toc: list[list] = []
        self.title, self.header_book, self.lang = title, header_book, lang
        self.page = None
        self.y = 0.0
        self.chapter_title = ""
        self.running = True

    # ── pages ──
    def new_page(self, running: bool = True):
        self.page = self.doc.new_page(width=595, height=842)
        for k, p in (("r", self.reg), ("b", self.bold), ("i", self.ital)):
            self.page.insert_font(fontname=f"F{k}", fontfile=p)
        n = self.doc.page_count
        if getattr(self, "headmode", None) == "runhead":
            # textbook layout: no footer; running head with the page number as a SEPARATE text run (even: "124   Chapter", odd: "Section   125")
            self.y = 95.0
            if n > 8:
                printed = n - 8 + 122  # 8 unnumbered front-matter pages; first body page is printed 123
                if printed % 2 == 0:
                    self.page.insert_text((72, 48), str(printed), fontname="Fr", fontsize=9)
                    self.page.insert_text((110, 48), self.chapter_title, fontname="Fi", fontsize=9)
                else:
                    self.page.insert_text((72, 48), getattr(self, "section_title", ""), fontname="Fi", fontsize=9)
                    self.page.insert_text((500, 48), str(printed), fontname="Fr", fontsize=9)
            return
        self.y = 90.0 if running else 150.0
        if running:
            txt, x = (self.header_book, 72) if n % 2 == 0 else (self.chapter_title, 595 - 72 - self.f["i"].text_length(self.chapter_title, 9))
            if txt:
                self.page.insert_text((x, 44), txt, fontname="Fi", fontsize=9, color=(0.35, 0.35, 0.35))
        off = getattr(self, "offset", 0)
        if off:  # front matter numbered i, ii, ...; body starts at printed page 1 after `off` pages
            label = str(n - off) if n > off else ["i", "ii", "iii", "iv", "v", "vi"][n - 1]
        else:
            label = str(n)
        self.page.insert_text((297, 800), label, fontname="Fr", fontsize=10)
        self.page.insert_text((72, 818), "© 2026 Example Press. All rights reserved. Not for resale.", fontname="Fr", fontsize=7, color=(0.5, 0.5, 0.5))

    def ensure(self, h: float):
        if self.page is None or self.y + h > 765:
            self.new_page()

    # ── text ──
    def line(self, segs: list[tuple[str, str]], size: float, x: float = 72):
        for txt, st in segs:
            self.page.insert_text((x, self.y), txt, fontname=f"F{st}", fontsize=size)
            x += self.f[st].text_length(txt, size)

    def para(self, text: str, size: float = 10.5, lead: float = 14.5, gap: float = 9.0, style: str = "r", hyphenate: bool = True):
        words: list[tuple[str, str]] = []
        for i, chunk in enumerate(re.split(r"\*\*", text)):
            for w in chunk.split():
                words.append((w, "b" if i % 2 else style))
        width, line, x = 595 - 144, [], 0.0
        space = self.f["r"].text_length(" ", size)
        lines: list[list[tuple[str, str]]] = []
        for w, st in words:
            wl = self.f[st].text_length(w, size)
            if x + wl <= width:
                line.append((w, st)); x += wl + space; continue
            room = width - x
            if hyphenate and len(w) >= 9 and ("-" not in w):
                cut = next((c for c in range(len(w) - 3, 3, -1) if self.f[st].text_length(w[:c] + "-", size) <= room), None)
                if cut:
                    line.append((w[:cut] + "-", st)); lines.append(line)
                    w, wl = w[cut:], self.f[st].text_length(w[cut:], size)
                    line, x = [(w, st)], wl + space
                    continue
            lines.append(line)
            line, x = [(w, st)], wl + space
        if line:
            lines.append(line)
        for ln in lines:
            self.ensure(lead)
            # merge words into styled segments
            segs, cur, cs = [], "", None
            for w, st in ln:
                piece = w + " "
                if st != cs and cur:
                    segs.append((cur, cs)); cur = ""
                cur += piece; cs = st
            if cur:
                segs.append((cur.rstrip(), cs))
            self.line(segs, size)
            self.y += lead
        self.y += gap

    def equation(self, title: str):
        self.ensure(34)
        self.eq_n = getattr(self, "eq_n", 0) + 1
        x, base = 110.0, self.y
        for txt, lvl in EQP.get(title) or [(EQ[title], 0)]:
            size = 11 if lvl == 0 else 7.5
            y = base + (3.2 if lvl < 0 else -4.5 if lvl > 0 else 0)
            self.page.insert_text((x, y), txt, fontname="Fi", fontsize=size)
            x += self.f["i"].text_length(txt, size)
        self.page.insert_text((500, base), f"({self.chapter_no}.{self.eq_n})", fontname="Fr", fontsize=11)
        self.y += 26

    def figure(self, caption: str, steep: float = 3.0):
        """A vector figure (frame + axes labels + decaying curve) with its caption below, like a LaTeX/Word PDF."""
        self.ensure(200)
        x0, top, w, h = 150.0, self.y + 4, 290.0, 130.0
        self.page.draw_rect(pymupdf.Rect(x0, top, x0 + w, top + h), color=(0.25, 0.25, 0.25), width=1)
        pts = [pymupdf.Point(x0 + w * i / 40, top + h - h * 0.92 * (2.718 ** (-steep * i / 40))) for i in range(41)]
        self.page.draw_polyline(pts, color=(0.1, 0.3, 0.7), width=2)
        self.page.insert_text((x0 + w / 2 - 22, top + h + 12), "r / lambda_D", fontname="Fr", fontsize=9)
        self.page.insert_text((x0 - 38, top + h / 2), "phi (r)", fontname="Fr", fontsize=9)
        self.y = top + h + 30
        self.para(caption, size=9, style="i", gap=12)

    def heading(self, text: str, size: float, style: str = "b", gap: float = 12):
        self.ensure(size * 2.5)
        self.y += gap
        self.page.insert_text((72, self.y), text, fontname=f"F{style}", fontsize=size)
        self.y += size * 1.4


def build_en(book: Book, outline: bool):
    d = book.doc
    # title page, contents, preface
    book.new_page(running=False)
    book.page.insert_text((72, 300), "Plasma Simulation Primer", fontname="Fb", fontsize=30)
    book.page.insert_text((72, 340), "A synthetic textbook for testing book-to-course", fontname="Fi", fontsize=13)
    book.new_page(running=False)
    contents_page = d.page_count
    book.y = 100
    book.heading("Contents", 22)
    book.y += 10
    toc_lines_at = book.y
    book.new_page()
    preface_page = d.page_count
    book.y = 100
    book.heading("Preface", 22)
    for k in range(3):
        book.para("This primer introduces the physics and numerics needed to simulate a low-temperature plasma on a computer. "
                  "Every chapter starts from a physical picture and then shows how it is turned into an algorithm. "
                  f"Readers are expected to know vector calculus and basic mechanics, as in preface paragraph {k + 1}.")
    entries = []
    for ci, (title, pool) in enumerate(EN.items(), start=1):
        book.chapter_title = f"Chapter {ci}. {title}"
        book.chapter_no, book.eq_n = ci, 0
        book.new_page(running=False)
        start = d.page_count
        book.page.insert_text((72, 110), f"Chapter {ci}", fontname="Fr", fontsize=15, color=(0.4, 0.4, 0.4))
        book.page.insert_text((72, 150), title, fontname="Fb", fontsize=26)
        book.y = 190
        sections = [f"{ci}.{j} {name}" for j, name in enumerate(["Core idea", "Mathematical description", "Practical consequences"], start=1)]
        entries.append([1, f"Chapter {ci}. {title}", start])
        for si, sec in enumerate(sections):
            book.ensure(60)
            sec_page = d.page_count
            book.heading(sec, 14)
            entries.append([2, sec, sec_page])
            for pi in range(14):
                n = len(pool)
                sents = [pool[(si * 3 + pi * 2 + k) % n] for k in range(4)]
                sents.append(f"In worked example {ci}.{si + 1}.{pi + 1} the density is {1 + pi * 2}e16 per cubic metre and the field is {200 + 50 * ci + 10 * pi} gauss.")
                book.para(" ".join(sents))
                if pi % 5 == 2:
                    book.equation(title)
                if pi % 5 == 4:
                    book.para(f"Figure {ci}.{si + 1}. Schematic of the {sec.split(' ', 1)[1].lower()} for {title.lower()}.", size=9, style="i", gap=12)
    index_page = None
    book.new_page(running=False)
    index_page = d.page_count
    book.y = 100
    book.heading("Index", 22)
    for t in ["Debye length, 8", "Larmor radius, 14", "plasma frequency, 20", "macroparticle, 27", "resonance condition, 38"] * 6:
        book.para(t, gap=2)
    # contents text (with dot leaders) written onto the contents page
    cp = d[contents_page - 1]
    y = toc_lines_at
    for lvl, t, pg in entries:
        if lvl == 1:
            cp.insert_text((72, y), f"{t} {'.' * 6} {pg}", fontname="Fr", fontsize=11)
            y += 18
    toc = [[1, "Contents", contents_page], [1, "Preface", preface_page]] + entries + [[1, "Index", index_page]]
    if outline:
        d.set_toc(toc)


def build_fig(book: Book):
    """3 short chapters, each with a vector figure and a caption: exercises figure detection and cropping."""
    d = book.doc
    entries = []
    names = ["Screening", "Orbits", "Waves"]
    for ci, name in enumerate(names, start=1):
        book.chapter_title = f"Chapter {ci}. {name}"
        book.new_page(running=False)
        entries.append([1, f"Chapter {ci}. {name}", d.page_count])
        book.page.insert_text((72, 110), f"Chapter {ci}", fontname="Fr", fontsize=15, color=(0.4, 0.4, 0.4))
        book.page.insert_text((72, 150), name, fontname="Fb", fontsize=26)
        book.y = 190
        pool = list(EN.values())[ci - 1]
        for k in range(2):
            book.para(" ".join(pool[(k * 3 + j) % len(pool)] for j in range(4)))
            book.figure(f"Figure {ci}.{k + 1}. Potential of a test charge in the {name.lower()} regime, panel {k + 1}.", steep=2.5 + k)
        book.para(" ".join(pool[j] for j in range(5)))
    d.set_toc(entries)


def build_book2(book: Book):
    """Mimics a textbook PDF without bookmarks: running heads with split page numbers, unnumbered front matter, a Courier listing,
    a multi-line derivation drawn as separate lines, a problem with garbled math, chapter/section headings by font size."""
    book.headmode = "runhead"
    for k in range(8):
        book.new_page(running=False)
        book.para("Front matter page %d. This textbook has no bookmarks and no printed numbers on its first eight pages." % (k + 1))
    plan = [(6, "Monte Carlo Techniques", ["Random Numbers", "Integration", "Problems"]),
            (7, "Stochastic Methods", ["The Random Walk", "Diffusion and Entropy", "Problems"])]
    pools = list(EN.values())
    for ci, (num, title, secs) in enumerate(plan):
        book.chapter_title = f"{num} {title}"
        book.section_title = f"{num}.1 {secs[0]}"
        book.new_page(running=True)
        book.page.insert_text((72, 120), f"{num} {title}", fontname="Fb", fontsize=22)
        book.y = 150
        for si, sec in enumerate(secs, start=1):
            book.section_title = f"{num}.{si} {sec}"
            book.ensure(70)
            book.heading(f"{num}.{si} {sec}", 14)
            pool = pools[(ci + si) % len(pools)]
            if sec == "Problems":
                book.ensure(160)  # keep the problem statements on one page
                book.para(f"{num}-1 Estimate the average of a random variable uniform on the interval from zero to one using one thousand samples and compare it with the exact value.")
                book.para(f"{num}-2 The “volume” of a 2-sphere x2 + y2 = r2 (AKA a “circle”) is (1)πr2. The volume of a 3-sphere x2 + y2 + z2 = r2 is … πr3. "
                          f"The equation for a 4-sphere is x2+y2+z2+w2 = r2. We can guess, by extrapolation from the 2-dimensional and 3-dimensional cases, "
                          f"that the “volume” of a 4-sphere is απr4. Use Monte Carlo integration to estimate α.")
                continue
            for pi in range(24):
                book.para(" ".join(pool[(pi * 2 + j) % len(pool)] for j in range(4)))
                if sec in ("Random Numbers", "The Random Walk") and pi == 1:
                    book.ensure(70)
                    for k, ln in enumerate(["import random", "count = 0", "for i in range(100):", "    count = count+1"]):
                        book.page.insert_text((90 + (14 if ln.startswith("    ") else 0), book.y + 12 * k), ln.strip(), fontname="cour", fontsize=9)
                    book.y += 12 * 4 + 12
                if sec in ("Integration", "Diffusion and Entropy") and pi == 2:
                    book.ensure(60)
                    for k, ln in enumerate(["s² = ∑ xi² / n", "= ∑ (xi − m)² / n + m²", "= σ² + m²"]):
                        book.page.insert_text((120, book.y + 13 * k), ln, fontname="Fi", fontsize=11)
                    book.page.insert_text((500, book.y + 13 * 2), f"({num}.{pi})", fontname="Fr", fontsize=11)
                    book.y += 13 * 3 + 14


def build_ru(book: Book):
    d = book.doc
    entries = []
    for ci, (title, pool) in enumerate(RU.items(), start=1):
        book.chapter_title = f"Глава {ci}. {title}"
        book.new_page(running=False)
        start = d.page_count
        book.page.insert_text((72, 110), f"Глава {ci}", fontname="Fr", fontsize=15, color=(0.4, 0.4, 0.4))
        book.page.insert_text((72, 150), title, fontname="Fb", fontsize=24)
        book.y = 190
        entries.append([1, f"Глава {ci}. {title}", start])
        for si in range(2):
            sec = f"{ci}.{si + 1} Раздел {si + 1}"
            sp = d.page_count
            book.heading(sec, 14)
            entries.append([2, sec, sp])
            for pi in range(8):
                sents = [pool[(si * 2 + pi + k) % len(pool)] for k in range(4)]
                sents.append(f"В примере {ci}.{si + 1}.{pi + 1} плотность равна {1 + pi}e16 на кубический метр.")
                book.para(" ".join(sents))
    d.set_toc(entries)


def rasterise(src: Path, pages: list[int], out: Path):
    s = pymupdf.open(str(src))
    o = pymupdf.open()
    for p in pages:
        pix = s[p - 1].get_pixmap(dpi=200)
        pg = o.new_page(width=595, height=842)
        pg.insert_image(pg.rect, pixmap=pix)
    o.save(str(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["en", "noout", "scan", "ru", "fig", "book2"], default="en")
    ap.add_argument("--offset", type=int, default=0, help="en/noout: pages before printed page 1 (front matter numbered i, ii, ...)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.kind in ("en", "noout"):
        b = Book("Plasma Simulation Primer", "Plasma Simulation Primer", "en")
        b.offset = a.offset
        build_en(b, outline=a.kind == "en")
        b.doc.set_metadata({"title": "Plasma Simulation Primer"})
        b.doc.save(str(out))
    elif a.kind == "book2":
        b = Book("Computational Physics Sample", "Computational Physics Sample", "en")
        build_book2(b)
        b.doc.save(str(out))
    elif a.kind == "fig":
        b = Book("Figures Primer", "Figures Primer", "en")
        build_fig(b)
        b.doc.set_metadata({"title": "Figures Primer"})
        b.doc.save(str(out))
    elif a.kind == "ru":
        b = Book("Основы моделирования плазмы", "Основы моделирования плазмы", "ru")
        build_ru(b)
        b.doc.set_metadata({"title": "Основы моделирования плазмы"})
        b.doc.save(str(out))
    else:
        tmp = out.with_suffix(".tmp.pdf")
        b = Book("Plasma Simulation Primer", "Plasma Simulation Primer", "en")
        build_en(b, outline=False)
        b.doc.save(str(tmp))
        rasterise(tmp, [6, 7, 8], out)
        tmp.unlink()
    print(f"wrote {out} ({pymupdf.open(str(out)).page_count} pages)")


if __name__ == "__main__":
    main()
