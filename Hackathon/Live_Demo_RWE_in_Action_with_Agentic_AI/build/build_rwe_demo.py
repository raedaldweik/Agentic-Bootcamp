#!/usr/bin/env python3
"""Build 'Real-World Evidence in Action with Agentic AI' (live demonstration, SAS) on the SAS EXTERNAL template.

Design language: the SAS Viya Agentic AI Experience reference deck, as in the Session 2 build:
SAS 2023 palette, Anova theme fonts (embedded in the template), light-grey arc band, white rounded
cards with soft shadows, slate section dividers, blue title/closing slides. This deck adds the
conventions of a consulting deck: action titles that state the finding, an executive summary,
evidence tables with a source line, stat tiles, and problem / solution pages for each live example.
"""
import json, os, math
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.dml import MSO_LINE
from pptx.oxml.ns import qn
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, 'icons')
ARC_JSON = os.path.join(HERE, 'arc.json')
TEMPLATE = os.environ.get('SAS_TEMPLATE', os.path.normpath(os.path.join(HERE, '..', '..', '..', 'templates', 'SAS_External_Template.pptx')))
OUT = os.environ.get('DEMO_OUT', os.path.normpath(os.path.join(HERE, '..', 'RWE_in_Action_with_Agentic_AI.pptx')))

# ---- palette (SAS-2023 theme) --------------------------------------------------------------
BLUE = '0766D1'; NAVY = '032954'; SKY = '4398F9'; LIGHT = 'C4DEFD'; MID = '98C5FB'
SLATE = '7E889A'; GRAY = 'BAC0C9'; PANEL = 'E4E7EA'; ARC = 'F0F1F3'
WHITE = 'FFFFFF'; BLACK = '000000'; INK = '262626'; GREEN = '009242'; RED = 'C00000'
PALE = 'EAF3FE'

# ---- page geometry (20 x 11.25 in) ---------------------------------------------------------
X0 = 1.37; XW = 17.25; X1 = X0 + XW
MJ = '+mj-lt'   # theme major font (Anova Bold)

def rgb(h): return RGBColor.from_string(h)

# ============================================================================================
# low-level helpers (shared with the Session 2 build)
# ============================================================================================
def _fill(shape, hexcol):
    shape.fill.solid(); shape.fill.fore_color.rgb = rgb(hexcol)

def _no_line(shape):
    shape.line.fill.background()

def _line(shape, hexcol, width=1.0, dash=None):
    shape.line.color.rgb = rgb(hexcol); shape.line.width = Pt(width)
    if dash: shape.line.dash_style = dash

def _effect_clear(spPr):
    for el in spPr.findall(qn('a:effectLst')):
        spPr.remove(el)

def _no_shadow(shape):
    spPr = shape._element.spPr
    _effect_clear(spPr)
    etree.SubElement(spPr, qn('a:effectLst'))

def _shadow(shape, blur=16, dist=3, alpha=16, angle=90):
    spPr = shape._element.spPr
    _effect_clear(spPr)
    eff = etree.SubElement(spPr, qn('a:effectLst'))
    sh = etree.SubElement(eff, qn('a:outerShdw'))
    sh.set('blurRad', str(int(Pt(blur)))); sh.set('dist', str(int(Pt(dist))))
    sh.set('dir', str(angle * 60000)); sh.set('algn', 'ctr'); sh.set('rotWithShape', '0')
    clr = etree.SubElement(sh, qn('a:srgbClr')); clr.set('val', '000000')
    a = etree.SubElement(clr, qn('a:alpha')); a.set('val', str(alpha * 1000))

def _bullet(p, color=BLUE, indent=0.26, char='•'):
    pPr = p._p.get_or_add_pPr()
    pPr.set('marL', str(int(Inches(indent)))); pPr.set('indent', str(-int(Inches(indent))))
    for tag in ('a:buClr', 'a:buFont', 'a:buChar', 'a:buNone'):
        for el in pPr.findall(qn(tag)): pPr.remove(el)
    buClr = etree.SubElement(pPr, qn('a:buClr')); c = etree.SubElement(buClr, qn('a:srgbClr')); c.set('val', color)
    buFont = etree.SubElement(pPr, qn('a:buFont')); buFont.set('typeface', 'Arial')
    buChar = etree.SubElement(pPr, qn('a:buChar')); buChar.set('char', char)

_ALIGN = {'l': PP_ALIGN.LEFT, 'c': PP_ALIGN.CENTER, 'r': PP_ALIGN.RIGHT}
_ANCHOR = {'t': MSO_ANCHOR.TOP, 'm': MSO_ANCHOR.MIDDLE, 'b': MSO_ANCHOR.BOTTOM}

def _runs(p, text, size, color, bold, font, italic=False):
    """'**bold**' markup -> Anova Bold runs."""
    parts = text.split('**')
    for i, seg in enumerate(parts):
        if seg == '': continue
        r = p.add_run(); r.text = seg
        f = r.font; f.size = Pt(size); f.color.rgb = rgb(color)
        is_b = bold or (i % 2 == 1)
        if is_b: f.name = MJ
        elif font: f.name = font
        if italic: f.italic = True

def fill_paras(tf, paras, size=18, color=BLACK, bold=False, font=None, align='l',
               line_spacing=None, space_after=None, space_before=None):
    if isinstance(paras, str): paras = [paras]
    first = True
    for item in paras:
        if isinstance(item, str): item = {'t': item}
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = _ALIGN[item.get('align', align)]
        ls = item.get('line_spacing', line_spacing)
        if ls: p.line_spacing = ls
        sa = item.get('space_after', space_after)
        if sa is not None: p.space_after = Pt(sa)
        sb = item.get('space_before', space_before)
        if sb is not None: p.space_before = Pt(sb)
        if item.get('bullet'):
            _bullet(p, item.get('bullet_color', BLUE), indent=item.get('indent', 0.26), char=item.get('char', '•'))
        _runs(p, item.get('t', ''), item.get('size', size), item.get('color', color),
              item.get('bold', bold), item.get('font', font), item.get('italic', False))
    return tf

def text(slide, x, y, w, h, paras, size=18, color=BLACK, bold=False, font=None, align='l', anchor='t',
         margins=(0.05, 0.03, 0.05, 0.03), line_spacing=None, space_after=None, rotation=None, wrap=True):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = wrap
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = [Inches(m) for m in margins]
    tf.vertical_anchor = _ANCHOR[anchor]
    fill_paras(tf, paras, size, color, bold, font, align, line_spacing, space_after)
    if rotation is not None: tb.rotation = rotation
    return tb

def shape_text(shape, paras, size=18, color=WHITE, bold=False, font=None, align='c', anchor='m',
               margins=(0.12, 0.06, 0.12, 0.06), line_spacing=None, space_after=None):
    tf = shape.text_frame; tf.word_wrap = True
    tf.margin_left, tf.margin_top, tf.margin_right, tf.margin_bottom = [Inches(m) for m in margins]
    tf.vertical_anchor = _ANCHOR[anchor]
    fill_paras(tf, paras, size, color, bold, font, align, line_spacing, space_after)
    return shape

def rect(slide, x, y, w, h, fill=WHITE, radius=0.28, shadow=False, line=None, line_w=1.0, dash=None):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius: s.adjustments[0] = min(0.5, radius / min(w, h))
    if fill: _fill(s, fill)
    else: s.fill.background()
    if line: _line(s, line, line_w, dash)
    else: _no_line(s)
    if shadow: _shadow(s)
    else: _no_shadow(s)
    return s

def card(slide, x, y, w, h, fill=WHITE, radius=0.28, shadow=True, line=None):
    return rect(slide, x, y, w, h, fill=fill, radius=radius, shadow=shadow, line=line)

def pill(slide, x, y, w, h, label, fill=NAVY, color=WHITE, size=16, bold=True, shadow=False):
    s = rect(slide, x, y, w, h, fill=fill, radius=h / 2, shadow=shadow)
    shape_text(s, label, size=size, color=color, bold=bold, margins=(0.1, 0.02, 0.1, 0.02))
    return s

def oval(slide, cx, cy, d, fill=BLUE, shadow=False, line=None, line_w=1.0):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
    if fill: _fill(s, fill)
    else: s.fill.background()
    if line: _line(s, line, line_w)
    else: _no_line(s)
    if shadow: _shadow(s)
    else: _no_shadow(s)
    return s

def icon(slide, name, variant, x, y, size):
    path = os.path.join(ICONS, f'{name}_{variant}.png')
    return slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(size), Inches(size))

def icon_circle(slide, cx, cy, d, fill, name, variant='w', shadow=True, scale=0.52):
    oval(slide, cx, cy, d, fill=fill, shadow=shadow)
    isz = d * scale
    icon(slide, name, variant, cx - isz / 2, cy - isz / 2, isz)

_ARROWS = {'right': MSO_SHAPE.RIGHT_ARROW, 'left': MSO_SHAPE.LEFT_ARROW, 'down': MSO_SHAPE.DOWN_ARROW, 'up': MSO_SHAPE.UP_ARROW}
def arrow(slide, x, y, w, h, fill=BLUE, kind='right'):
    s = slide.shapes.add_shape(_ARROWS[kind], Inches(x), Inches(y), Inches(w), Inches(h))
    _fill(s, fill); _no_line(s); _no_shadow(s)
    return s

def chevron(slide, x, y, w, h, fill=BLUE, rotation=0):
    s = slide.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x), Inches(y), Inches(w), Inches(h))
    _fill(s, fill); _no_line(s); _no_shadow(s)
    if rotation: s.rotation = rotation
    return s

def connector(slide, x1, y1, x2, y2, color=SLATE, width=1.25, dash=None, head=False, tail=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color); c.line.width = Pt(width)
    if dash: c.line.dash_style = dash
    ln = c.line._get_or_add_ln()
    if head:
        e = etree.SubElement(ln, qn('a:headEnd')); e.set('type', 'triangle'); e.set('w', 'med'); e.set('len', 'med')
    if tail:
        e = etree.SubElement(ln, qn('a:tailEnd')); e.set('type', 'triangle'); e.set('w', 'med'); e.set('len', 'med')
    spPr = c._element.spPr
    _effect_clear(spPr); etree.SubElement(spPr, qn('a:effectLst'))
    return c

def send_to_back(slide, shape, index=2):
    sp = shape._element; tree = slide.shapes._spTree
    tree.remove(sp); tree.insert(index, sp)

ARCPTS = json.load(open(ARC_JSON))['points']
def arc_bg(slide):
    scale = 12700
    fb = slide.shapes.build_freeform(int(ARCPTS[0][0] * scale), int(ARCPTS[0][1] * scale), scale=1.0)
    fb.add_line_segments([(int(x * scale), int(y * scale)) for x, y in ARCPTS[1:]], close=True)
    s = fb.convert_to_shape()
    _fill(s, ARC); _no_line(s); _no_shadow(s)
    send_to_back(slide, s)
    return s

def notes(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt.strip()

def placeholder(slide, idx):
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx: return ph
    return None

def drop_placeholder(ph):
    if ph is not None:
        ph._element.getparent().remove(ph._element)

def set_ph(ph, txt, size=None, color=None, bold=None):
    tf = ph.text_frame
    tf.text = txt
    for p in tf.paragraphs:
        for r in p.runs:
            if size: r.font.size = Pt(size)
            if color: r.font.color.rgb = rgb(color)
            if bold is not None: r.font.bold = bold

# ============================================================================================
# presentation set-up
# ============================================================================================
prs = Presentation(TEMPLATE)
sldIdLst = prs.slides._sldIdLst
for sldId in list(sldIdLst):
    prs.part.drop_rel(sldId.rId); sldIdLst.remove(sldId)
mlst = prs.slide_masters._sldMasterIdLst
for el in list(mlst)[1:]:
    prs.part.drop_rel(el.rId); mlst.remove(el)
M = prs.slide_masters[0]
LAY = {l.name: l for l in M.slide_layouts}

def action_slide(title, tag=None, title_size=None, arc=True, title_w=None):
    """A content slide with an action title (the finding, as a sentence, up to two lines) and no subtitle."""
    s = prs.slides.add_slide(LAY['SAS - Title & Subtitle'])
    if arc: arc_bg(s)
    t = s.shapes.title
    t.text = title
    if not title_size:
        title_size = 36 if len(title) <= 60 else 32
    t.left = Inches(X0); t.top = Inches(0.78); t.width = Inches(title_w or XW); t.height = Inches(1.35)
    tf = t.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.TOP
    for p in tf.paragraphs:
        for r in p.runs: r.font.size = Pt(title_size)
    drop_placeholder(placeholder(s, 10))
    if tag:
        text(s, X0, 0.36, 12.0, 0.32, tag, size=11, color=BLUE, bold=True)
    return s

def section_slide(title, subtitle, icon_name, title_size=60):
    s = prs.slides.add_slide(LAY['SAS - Section'])
    set_ph(s.shapes.title, title, size=title_size)
    set_ph(placeholder(s, 10), subtitle, size=36)
    oval(s, 17.15, 2.15, 2.3, fill=None, line=WHITE, line_w=2.5)
    icon(s, icon_name, 'w', 17.15 - 0.62, 2.15 - 0.62, 1.24)
    return s

def sources(slide, txt):
    text(slide, X0, 10.2, XW, 0.5, txt, size=9, color=SLATE, anchor='t')

def heading(slide, x, y, w, txt, size=20, color=BLUE, h=0.5):
    return text(slide, x, y, w, h, txt, size=size, color=color, bold=True)

def label(slide, x, y, w, txt, color=BLUE):
    return text(slide, x, y, w, 0.3, txt.upper(), size=10.5, color=color, bold=True)

def icon_row(slide, x, y, w, name, lab, desc, circle=BLUE, d=0.66, label_size=16, desc_size=13, row_h=1.2):
    icon_circle(slide, x + d / 2, y + d / 2, d, circle, name, shadow=False, scale=0.55)
    text(slide, x + d + 0.22, y - 0.06, w - d - 0.22, 0.42, lab, size=label_size, color=INK, bold=True)
    return text(slide, x + d + 0.22, y + 0.34, w - d - 0.22, row_h - 0.34, desc, size=desc_size, color=INK)

def numbered_row(slide, x, y, w, n, lab, desc, d=0.62, label_size=17, desc_size=13.5, row_h=1.5, fill=BLUE):
    c = oval(slide, x + d / 2, y + d / 2, d, fill=fill)
    shape_text(c, str(n), size=18, color=WHITE, bold=True, margins=(0, 0, 0, 0))
    text(slide, x + d + 0.25, y - 0.05, w - d - 0.25, 0.45, lab, size=label_size, color=INK, bold=True)
    text(slide, x + d + 0.25, y + 0.4, w - d - 0.25, row_h - 0.4, desc, size=desc_size, color=INK)

def stat_tile(slide, x, y, w, h, number, lab, fill=PALE, num_color=NAVY, num_size=28, label_size=12):
    rect(slide, x, y, w, h, fill=fill, radius=0.2)
    text(slide, x + 0.3, y + 0.12, w - 0.6, 0.6, number, size=num_size, color=num_color, bold=True)
    text(slide, x + 0.3, y + 0.72, w - 0.6, h - 0.8, lab, size=label_size, color=INK)

def scq(slide, x, y, w, lab, body, h=1.5, size=15.5):
    label(slide, x, y, w, lab)
    return text(slide, x, y + 0.3, w, h, body, size=size, color=INK)

def table(slide, x, y, w, h, rows, colw, header_size=14, body_size=12, header_h=0.6, bold_cols=(0,),
          color_cols=None, center_cols=(), first_col_color=INK):
    color_cols = color_cols or {}
    tbl = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h)).table
    for i, cw in enumerate(colw): tbl.columns[i].width = Inches(cw)
    tbl.rows[0].height = Inches(header_h)
    for r in range(1, len(rows)): tbl.rows[r].height = Inches((h - header_h) / (len(rows) - 1))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if r == 0 else (WHITE if r % 2 == 1 else ARC))
            cell.margin_left = Inches(0.16); cell.margin_right = Inches(0.16); cell.margin_top = Inches(0.06); cell.margin_bottom = Inches(0.06)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame; tf.word_wrap = True
            al = 'c' if c in center_cols else 'l'
            if r == 0:
                fill_paras(tf, val, size=header_size, color=WHITE, bold=True, align=al)
            else:
                col = color_cols.get(c, first_col_color if c == 0 else INK)
                fill_paras(tf, val, size=body_size, color=col, bold=(c in bold_cols), align=al)
    tblPr = tbl._tbl.tblPr
    tblPr.set('firstRow', '1'); tblPr.set('bandRow', '0')
    return tbl


def solution_overview(s, left_top, left_bottom, agent, tools, bridge, delivers):
    """The solution-overview diagram: unstructured and structured inputs on the left, the agent in the middle,
    the MCP server and its tools on the right, the bridge element underneath, what it delivers at the bottom."""
    # -- left column, top: unstructured input, three steps down
    t_label, t_src, t_sub, t_mid, t_end = left_top
    text(s, X0, 2.5, 4.3, 0.4, t_label, size=16, color=BLUE, bold=True, align='c')
    rect(s, X0, 2.9, 4.3, 3.25, fill=None, radius=0.25, line=BLUE, line_w=1.25, dash=MSO_LINE.ROUND_DOT)
    d1 = rect(s, X0 + 0.3, 3.1, 3.7, 0.7, fill=PANEL, radius=0.12)
    shape_text(d1, t_src, size=13, color=INK, bold=True)
    text(s, X0 + 0.3, 3.82, 3.7, 0.5, t_sub, size=11, color=SLATE, align='c')
    arrow(s, X0 + 2.15 - 0.17, 4.34, 0.34, 0.32, kind='down')
    e1 = rect(s, X0 + 0.6, 4.7, 3.1, 0.52, fill=LIGHT, radius=0.1)
    shape_text(e1, t_mid, size=13, color=NAVY, bold=True)
    arrow(s, X0 + 2.15 - 0.17, 5.26, 0.34, 0.3, kind='down')
    v1 = rect(s, X0 + 0.3, 5.58, 3.7, 0.5, fill=BLUE, radius=0.1)
    shape_text(v1, t_end, size=13, color=WHITE, bold=True)
    # -- left column, bottom: structured input
    b_label, b_src, b_sub = left_bottom
    text(s, X0, 6.35, 4.3, 0.4, b_label, size=16, color=BLUE, bold=True, align='c')
    rect(s, X0, 6.75, 4.3, 1.95, fill=None, radius=0.25, line=BLUE, line_w=1.25, dash=MSO_LINE.ROUND_DOT)
    d2 = rect(s, X0 + 0.3, 6.95, 3.7, 0.7, fill=PANEL, radius=0.12)
    shape_text(d2, b_src, size=13, color=INK, bold=True)
    text(s, X0 + 0.3, 7.7, 3.7, 0.75, b_sub, size=11, color=SLATE, align='c')
    # -- the agent
    a_name, a_desc, a_inner, a_arrow = agent
    AX, AY, AW, AH = 7.0, 2.65, 4.4, 5.35
    text(s, X0 + 4.3, 4.1, AX - X0 - 4.3, 0.4, a_arrow, size=12, color=BLUE, bold=True, align='c')
    arrow(s, X0 + 4.3 + 0.08, 4.5, AX - X0 - 4.3 - 0.16, 0.36, kind='right')
    card(s, AX, AY, AW, AH, fill=BLUE)
    text(s, AX + 0.3, AY + 0.25, AW - 0.6, 0.55, a_name, size=20, color=WHITE, bold=True, align='c')
    rect(s, AX + 0.9, AY + 0.85, AW - 1.8, 0.03, fill=WHITE, radius=0)
    text(s, AX + 0.3, AY + 1.0, AW - 0.6, 1.45, a_desc, size=14, color=WHITE, align='c', anchor='t')
    rect(s, AX + 0.3, AY + 2.6, AW - 0.6, 2.5, fill=PALE, radius=0.18)
    text(s, AX + 0.5, AY + 2.75, AW - 1.0, 2.25, [{'t': ln, 'bullet': True, 'space_before': (0 if i == 0 else 4)} for i, ln in enumerate(a_inner)],
         size=13, color=NAVY, anchor='m')
    # -- MCP server and tools
    MX, MY, MW, MH = 12.3, 3.5, 2.3, 2.3
    arrow(s, AX + AW + 0.08, 4.5, MX - AX - AW - 0.16, 0.36, kind='right')
    rect(s, MX, MY, MW, MH, fill=LIGHT, radius=0.3, shadow=True)
    icon(s, 'usb', 'n', MX + MW / 2 - 0.4, MY + 0.3, 0.8)
    text(s, MX, MY + 1.2, MW, 0.9, ['MCP server', {'t': 'one plug, every tool', 'size': 11, 'bold': False}], size=18, color=NAVY, bold=True, align='c', anchor='t')
    TX, TW, TH, TG = 15.4, X1 - 15.4, 0.72, 0.22
    text(s, TX, 2.5, TW, 0.4, 'Tools', size=16, color=BLUE, bold=True, align='c')
    palette = [(SLATE, WHITE), (LIGHT, NAVY), (SKY, WHITE), (BLUE, WHITE), (NAVY, WHITE)]
    tool_y = []
    for i, t in enumerate(tools):
        col, tc = palette[i % len(palette)]
        yy = 3.05 + i * (TH + TG); tool_y.append(yy)
        tt = rect(s, TX, yy, TW, TH, fill=col, radius=0.1, shadow=True)
        shape_text(tt, t, size=12, color=tc, bold=True, margins=(0.1, 0.03, 0.1, 0.03))
        connector(s, MX + MW + 0.04, MY + MH / 2, TX - 0.05, yy + TH / 2, color=BLUE, width=1.5, tail=True)
    # -- the bridge element under the agent, fed by the structured input and read by the last tool
    br_icon, br_label, br_tool = bridge
    icon(s, br_icon, 'b', AX + 0.35, 8.17, 0.5)
    text(s, AX + 0.95, 8.15, 3.6, 0.5, br_label, size=16, color=BLUE, bold=True, anchor='m')
    connector(s, X0 + 4.3, 7.65, AX + 0.3, 8.4, color=BLUE, width=1.5, dash=MSO_LINE.ROUND_DOT, tail=True)
    connector(s, AX + 3.9, 8.4, TX + TW / 2, tool_y[br_tool] + TH + 0.02, color=BLUE, width=1.5, dash=MSO_LINE.ROUND_DOT, tail=True)
    # -- what it delivers, three plain lines
    gvw = (XW - 2 * 0.4) / 3
    for i, g in enumerate(delivers):
        x = X0 + i * (gvw + 0.4)
        icon(s, 'check', 'b', x, 9.17, 0.4)
        text(s, x + 0.55, 9.05, gvw - 0.55, 0.75, g, size=13, color=INK, anchor='m')

def copyright_line(slide, color=LIGHT):
    text(slide, 1.37, 10.78, 6.0, 0.27, 'Copyright © SAS Institute Inc. All rights reserved.', size=10, color=color, anchor='b')

# ============================================================================================
# SLIDES
# ============================================================================================
# 1 ---- Title -------------------------------------------------------------------------------
s = prs.slides.add_slide(LAY['SAS - Title'])
set_ph(s.shapes.title, 'Real-World Evidence in Action\nwith Agentic AI', size=60)
set_ph(placeholder(s, 10), 'Live demonstration  ·  SAS', size=36)
set_ph(placeholder(s, 11), 'Raed Aldweik  |  SAS\nAgentic AI Hackathon', size=24)
notes(s, """
Forty-five minutes, two live demonstrations, one argument: agentic AI has moved from pilots to production in health
care, and the value sits in real-world data that health systems already hold and nobody has the hours to act on.
Timing: executive summary 3 min (slide 2); why now and what it is 5 min (3-5); the evidence and the use-case map
7 min (6-8); Example 1, population health, 5 min on slides (10-13) and 10 min live; Example 2, cancer early warning,
5 min on slides (15-18) and 7 min live; what it means 3 min (19-20); questions. Slides 13 and 18 are backups if a
live environment misbehaves. Before the session: open the app on the second screen with Example 1 warmed up on the
morning briefing and Example 2 loaded with Fatima's profile; check the trace panel is visible.
""")

# 2 ---- Executive summary -------------------------------------------------------------------
s = action_slide('Agentic AI has left the pilot stage; the value is in real-world data you already hold', 'EXECUTIVE SUMMARY', title_w=12.0)
panel = rect(s, 13.7, 0, 6.3, 11.25, fill=NAVY, radius=0)
send_to_back(s, panel, index=3)
msgs = [
    ('Production deployments now report measured outcomes',
     'Documentation time down 16 minutes a day (JAMA, 2026). Clinician burnout 52% to 39% in 30 days (JAMA Network Open, 2025). '
     'Two-year mortality 43% lower after ML-guided screening outreach (Geisinger). 40% of prior authorisations with no human touch (MUSC Health).'),
    ('The use cases are known; the question is which workflow first',
     'The same pattern runs before, during and after the visit, in population health and prevention, in operations and finance, and in research.'),
    ('The pattern behind every success is the same',
     'A language model that reasons, surrounded by your data, your models and your guidelines as governed tools, with a person at the decision '
     'and a trace of every step.'),
    ('Today: two live examples on synthetic data',
     'A population-health agent over a diabetes registry, and a bowel-cancer early-warning check. Both turn real-world data into evidence '
     'and a next action in seconds, and show their working.'),
]
for i, (a, b) in enumerate(msgs):
    y = 2.6 + i * 1.9
    text(s, X0, y - 0.12, 1.4, 0.9, f'0{i + 1}', size=36, color=BLUE, bold=True)
    text(s, X0 + 1.45, y, 10.3, 0.5, a, size=18, color=INK, bold=True)
    text(s, X0 + 1.45, y + 0.5, 10.3, 1.3, b, size=13, color=INK)
text(s, 14.3, 2.6, 5.2, 0.5, 'The next 45 minutes', size=18, color=WHITE, bold=True)
plan = [('presentation', 'The evidence', '10 min. What is working, what is not, and where it could go next'),
        ('heart', 'Example 1 · Population health', '15 min. Five on slides, ten live'),
        ('scan', 'Example 2 · Cancer early warning', '12 min. Five on slides, seven live'),
        ('check', 'What it means for your use case', '8 min. One blueprint, five tests, questions')]
for i, (ic, a, b) in enumerate(plan):
    y = 3.5 + i * 1.6
    icon_circle(s, 14.6, y + 0.3, 0.6, BLUE, ic, shadow=False, scale=0.55)
    text(s, 15.1, y - 0.02, 4.5, 0.45, a, size=14, color=WHITE, bold=True)
    text(s, 15.1, y + 0.42, 4.5, 0.9, b, size=12, color=LIGHT)
notes(s, """
The whole session on one page; say it in ninety seconds and the room knows where you are going. Four messages: the
evidence is in (measured outcomes, not pilots); the use cases are known across the whole pathway, so the question is
which workflow first; the winning pattern is always the same (model in the middle, your data and guidelines around
it, a person at the decision); and today you will see that pattern twice, live, on synthetic data. The panel on the
right is the running order.
""")

# 3 ---- Why now: the RWE loop ----------------------------------------------------------------
s = action_slide('Health systems hold more real-world data than they have hours to turn into decisions', 'WHY NOW')
bw, bh = 3.9, 1.7
boxes = [('Real-world data', 'HIE, registries, screening programmes, claims', X0 + 0.2, 2.75, NAVY),
         ('Evidence', 'cohorts, risk, care gaps, what the guideline says', X0 + 5.5, 2.75, BLUE),
         ('Action', 'a recall, a referral, a draft for sign-off', X0 + 5.5, 7.3, BLUE),
         ('Outcome', 'measured, written back into the data', X0 + 0.2, 7.3, NAVY)]
for t, d, x, y, col in boxes:
    b = rect(s, x, y, bw, bh, fill=col, radius=0.22, shadow=True)
    shape_text(b, [{'t': t, 'size': 18, 'bold': True}, {'t': d, 'size': 12, 'space_before': 3}], color=WHITE)
arrow(s, X0 + 4.35, 3.35, 0.9, 0.5, kind='right')
arrow(s, X0 + 7.2, 4.65, 0.5, 2.45, kind='down')
arrow(s, X0 + 4.35, 7.9, 0.9, 0.5, kind='left')
arrow(s, X0 + 1.9, 4.65, 0.5, 2.45, kind='up')
text(s, X0 + 2.7, 5.0, 4.2, 1.75, ['The bottleneck is not data.', {'t': 'It is analyst and clinician hours.', 'color': BLUE}],
     size=15, color=NAVY, bold=True, align='c', anchor='m')
tx = 11.4; tw = X1 - tx; th = 2.15
stat_tile(s, tx, 2.6, tw, th, '20.7%', 'of adults in the UAE live with diabetes: 1.27 million people, among the highest rates in the world (IDF Diabetes Atlas, 11th edition).', num_color=BLUE)
stat_tile(s, tx, 2.6 + th + 0.3, tw, th, 'No. 1', 'Bowel cancer is the most common cancer among men in the UAE, and a quarter to a half of cases are diagnosed before the age of 50 (National Cancer Registry; CA Cancer J Clin, 2024).', num_color=BLUE)
stat_tile(s, tx, 2.6 + 2 * (th + 0.3), tw, th, '~70%', 'of new drug and biologic submissions to the US FDA now include real-world evidence. Regulators, not only providers, run on registry data (2026).', num_color=BLUE)
sources(s, 'Sources: International Diabetes Federation, IDF Diabetes Atlas 11th ed. (2025), UAE profile  ·  UAE National Cancer Registry, Cancer Incidence in UAE 2021 (MOHAP)  ·  '
           'Al-Shamsi et al., CA: A Cancer Journal for Clinicians, 2024  ·  MedCity News, March 2026.')
notes(s, """
The frame for everything that follows. The loop on the left is what 'real-world evidence' means in practice: data that
already exists (the HIE, the registry, the screening programme) becomes evidence (a cohort, a risk, a gap, a guideline
section), evidence becomes an action (a recall, a referral, a draft), and the outcome is written back. Every health
system runs this loop; the constraint is the human hours in the middle. On the right, why it matters here: one in five
adults in the UAE lives with diabetes; bowel cancer is the most common cancer among men and strikes young; and real-
world evidence is now mainstream even with regulators. Agentic AI is the first technology that can run the loop, not
just one step of it.
""")

# 4 ---- What agentic AI is: three cards -----------------------------------------------------
s = action_slide('Agentic AI is the step from answering questions to completing work', 'WHAT AGENTIC AI IS')
cols = [('model', 'Analytical AI', [('You give it', 'Data'), ('It gives back', 'A prediction: a risk score, a forecast, a classification'),
                                   ('It stops when', 'The score is computed'), ('In today\'s demos', 'The deterioration-risk model; the screening score')], WHITE, NAVY),
        ('sparkles', 'Generative AI', [('You give it', 'A prompt'), ('It gives back', 'Text: a summary, a draft, an answer'),
                                       ('It stops when', 'The answer is written'), ('In today\'s demos', 'Writes every answer and explanation, in English or Arabic')], WHITE, SKY),
        ('robot', 'Agentic AI', [('You give it', 'A goal'), ('It gives back', 'Finished work, with every step it took shown'),
                                 ('It stops when', 'The goal is met, or a person must decide'), ('In today\'s demos', 'The agents: they decide what to run, run it, check it, and hand over')], BLUE, WHITE)]
cw3 = (XW - 2 * 0.4) / 3
for i, (ic, t, rows_, fill, circ) in enumerate(cols):
    x = X0 + i * (cw3 + 0.4); y = 2.6; h = 6.5
    dark = fill == BLUE
    card(s, x, y, cw3, h, fill=fill)
    icon_circle(s, x + 0.7, y + 0.7, 0.9, circ, ic, variant=('b' if dark else 'w'), shadow=False)
    text(s, x + 1.35, y + 0.42, cw3 - 1.6, 0.6, t, size=22, color=(WHITE if dark else INK), bold=True)
    for j, (lab, val) in enumerate(rows_):
        yy = y + 1.65 + j * 1.18
        text(s, x + 0.4, yy, cw3 - 0.8, 0.3, lab.upper(), size=10.5, color=(LIGHT if dark else BLUE), bold=True)
        text(s, x + 0.4, yy + 0.3, cw3 - 0.8, 0.85, val, size=14, color=(WHITE if dark else INK))
text(s, X0, 9.4, XW, 0.7, 'An agent pursues a goal by reasoning about the next step, using tools to act, checking the result, and staying inside limits set by people. Nothing in the third column replaces the first two: the agent puts them to work.',
     size=13, color=SLATE)
notes(s, """
Three cards instead of three definitions. Analytical AI predicts, and most health systems already run it. Generative
AI writes, and most of the room has used it. Agentic AI is given a goal, decides which tools to use, uses them,
checks the result and keeps going until the job is done or a person has to decide. The last row of each card ties it
to what they will see: the risk model and the screening score are analytical; the language model writes; the agent
orchestrates both. The sentence underneath is the only definition in the deck.
""")

# 5 ---- What surrounds the model ------------------------------------------------------------
s = action_slide('What makes an agent trustworthy in a hospital is not the model but what surrounds it', 'WHAT AGENTIC AI IS')
cx, cy = 10.0, 6.0
blocks = [('files', 'Knowledge', 'Your guidelines, retrieved on demand and quoted with the section (retrieval-augmented generation).'),
          ('api', 'Tools', 'Your data, models and rules, reached through one governed plug (the Model Context Protocol), never directly.'),
          ('oversight', 'Oversight', 'The goal, the limits, the approvals. The agent drafts, lists and ranks; a person decides.'),
          ('log', 'Trace', 'Every retrieval, query and model call on record, next to the answer. The audit trail is built in.')]
cw_, ch_ = 6.2, 2.5
pos = [(X0, 2.7), (X0, 6.6), (X1 - cw_, 2.7), (X1 - cw_, 6.6)]
for (ic, lab, desc), (x, y) in zip(blocks, pos):
    left = x < 9
    connector(s, (x + cw_) if left else x, y + ch_ / 2, cx + (-1.55 if left else 1.55), cy, color=MID, width=1.5, dash=MSO_LINE.ROUND_DOT)
    card(s, x, y, cw_, ch_)
    icon_circle(s, x + 0.95, y + ch_ / 2, 1.1, NAVY if ic in ('oversight', 'log') else BLUE, ic, shadow=False)
    text(s, x + 1.75, y + 0.3, cw_ - 2.0, 0.5, lab, size=21, color=INK, bold=True)
    text(s, x + 1.75, y + 0.9, cw_ - 2.0, 1.5, desc, size=14, color=INK)
oval(s, cx, cy, 3.1, fill=NAVY, shadow=True)
oval(s, cx, cy, 2.75, fill=None, line=WHITE, line_w=1.5)
icon(s, 'brain', 'w', cx - 0.4, cy - 1.05, 0.8)
text(s, cx - 1.3, cy - 0.2, 2.6, 1.2, ['The model', {'t': 'reasons, plans, writes', 'size': 13}], size=20, color=WHITE, bold=True, align='c', anchor='t')
text(s, X0, 9.45, XW, 0.5, 'The model never touches a system. The four blocks around it do, with the permissions you gave them. Every deployment on the next slide is built this way.', size=13, color=SLATE)
notes(s, """
The architecture every successful deployment shares, and the one both demos use. The language model sits in the
middle and only reasons, plans and writes. Knowledge is what it may quote: your guidelines, retrieved and cited.
Tools are what it may call: your data, models and rules behind one governed plug, so you can read the tool list and
know exactly what it can reach. Oversight is the person at the decision. Trace is the audit trail, built in rather
than bolted on. Say the footer slowly; it is the sentence that settles the security conversation.
""")

# 6 ---- Evidence cards ----------------------------------------------------------------------
s = action_slide('Agentic AI is already in production across the care pathway, with measured results', 'THE EVIDENCE')
ev = [('16 min', 'less documentation per clinician per day', 'Ambient AI scribes draft the note while the clinician listens. Five US academic health systems, 8,581 clinicians; 0.49 more visits a week.', 'JAMA, 2026'),
      ('52% → 39%', 'clinician burnout after 30 days', 'An ambient scribe in daily use, with the clinician finalising every note. Six health systems, 263 clinicians.', 'JAMA Network Open, 2025'),
      ('43%', 'lower two-year mortality than controls', 'Machine learning ranks who is at risk and overdue for bowel screening; outreach works the list. 6.9% more colonoscopies within six months.', 'Geisinger · M&SOM, 2026'),
      ('2.6×', 'the FIT opt-in among Spanish speakers', 'A voice agent calls people due for bowel screening in their own language and offers the kit: 18.2% vs 7.1%. 1,878 patients.', 'WellSpan Health with Hippocratic AI, 2025'),
      ('40%', 'of prior authorisations with no human touch', 'Agents work the payer portals end to end; denials are escalated to a person. About 30 minutes to about 1 minute per case.', 'MUSC Health with Notable, 2025'),
      ('87%', 'accuracy in clinical trial matching', 'A language model screens patient records against trial criteria and explains each match; 42.6% less clinician screening time.', 'NIH TrialGPT · Nature Communications, 2024')]
ew = (XW - 2 * 0.4) / 3; eh = 3.45
for i, (n, lab, d, src) in enumerate(ev):
    r, c = divmod(i, 3)
    x = X0 + c * (ew + 0.4); y = 2.55 + r * (eh + 0.35)
    card(s, x, y, ew, eh)
    text(s, x + 0.4, y + 0.25, ew - 0.8, 0.75, n, size=32, color=BLUE if c != 1 else NAVY, bold=True)
    text(s, x + 0.4, y + 1.0, ew - 0.8, 0.55, lab, size=13.5, color=INK, bold=True)
    text(s, x + 0.4, y + 1.6, ew - 0.8, 1.3, d, size=12, color=INK)
    text(s, x + 0.4, y + eh - 0.55, ew - 0.8, 0.4, src, size=10.5, color=SLATE)
sources(s, 'Sources: JAMA, April 2026, multisite AI-scribe study (Mass General Brigham, Emory, UCSF, Yale New Haven, UC Davis)  ·  Olson et al., JAMA Network Open, October 2025  ·  '
           'Manufacturing & Service Operations Management, 2026 (Geisinger)  ·  WellSpan Health / Hippocratic AI retrospective analysis, 2025  ·  Becker\'s Hospital Review, 2025 (MUSC Health)  ·  Jin et al., Nature Communications, 2024.')
notes(s, """
Six deployments, six measured results, all published or reported in the last two years. Read the big numbers only.
Documentation: sixteen minutes a day across five academic systems and 8,581 clinicians, modest and real. Burnout: from
half of clinicians to under four in ten in a month. Screening outreach: a machine-learning list and a phone call, and
two-year mortality 43% lower than controls. Multilingual outreach: the agent reached the group the system was failing.
Prior authorisation: 40% of cases never touched by a human. Trial matching: 87% accuracy, 43% less screening time.
What they have in common: a named workflow, a number, and a person still in the loop.
""")

# 7 ---- Use-case landscape ------------------------------------------------------------------
s = action_slide('Where agentic AI can go to work: six places across the care pathway', 'THE EVIDENCE')
uc = [('clipboard', 'Before the visit', ['A conversational pre-visit interview, summarised for the clinician', 'Symptoms triaged to the right route and the right slot'], False),
      ('stethoscope', 'During the visit', ['The note drafted while the clinician listens', 'Decision support that cites the guideline by section'], False),
      ('phone', 'After the visit', ['Post-discharge follow-up calls, in the patient\'s language', 'Adherence and refill reminders, with a nurse on call'], False),
      ('heart', 'Population and prevention', ['Registry surveillance: who is slipping, where the care gaps are', 'Screening outreach and early warning: who is due, who has red flags'], True),
      ('coins', 'Operations and finance', ['Prior authorisation worked end to end, denials to a person', 'Capacity and demand forecasting, with the draft plan attached'], False),
      ('flask', 'Research and evidence', ['Trial matching with explained eligibility', 'Continuous real-world evidence: safety signals, outcomes, registries'], False)]
uw = (XW - 2 * 0.4) / 3; uh = 3.45
for i, (ic, t, lines, live) in enumerate(uc):
    r, c = divmod(i, 3)
    x = X0 + c * (uw + 0.4); y = 2.55 + r * (uh + 0.35)
    card(s, x, y, uw, uh, fill=BLUE if live else WHITE)
    icon_circle(s, x + 0.65, y + 0.65, 0.78, WHITE if live else NAVY, ic, variant=('b' if live else 'w'), shadow=False, scale=0.55)
    text(s, x + 1.25, y + 0.35, uw - 1.5 - (1.7 if live else 0), 0.6, t, size=18, color=WHITE if live else INK, bold=True)
    if live:
        pill(s, x + uw - 1.85, y + 0.45, 1.55, 0.44, 'Live today', fill=WHITE, color=BLUE, size=11)
    text(s, x + 0.4, y + 1.45, uw - 0.8, uh - 1.6, [{'t': l, 'bullet': True, 'bullet_color': (LIGHT if live else BLUE)} for l in lines],
         size=13.5, color=WHITE if live else INK, space_after=8)
text(s, X0, 9.95, XW, 0.4, 'Every one of these follows the pattern on the previous two slides: a goal, governed tools over data that already exists, a person at the decision, a trace.', size=12.5, color=SLATE)
notes(s, """
The map of where this goes. Six places along the pathway, two use cases each, all of them running somewhere today in
some form: before the visit (intake, triage), during (documentation, cited decision support), after (follow-up calls,
adherence), population and prevention (registry surveillance, screening outreach and early warning), operations and
finance (prior authorisation, capacity), research (trial matching, continuous real-world evidence). The blue card is
where the two demos sit. Invite the room to place their own idea on this map; most land in one of the six.
""")

# 8 ---- Reality check -----------------------------------------------------------------------
s = action_slide('Most AI pilots never show a return; the deployments that do share four traits', 'THE EVIDENCE')
stat_tile(s, X0, 2.6, 6.4, 3.0, '95%', 'of organisations saw no measurable return from their generative-AI pilots, against USD 30 to 40 billion invested. Brittle workflows and poor fit with daily operations, not the models (MIT NANDA, July 2025, preliminary).', num_size=40, num_color=BLUE)
stat_tile(s, X0, 5.9, 6.4, 3.0, '>40%', 'of agentic AI projects will be cancelled by the end of 2027: escalating cost, unclear business value, inadequate risk controls. Of thousands of "agentic" vendors, Gartner counts about 130 as real (Gartner, June 2025).', num_size=40, num_color=BLUE)
rx = 8.4; rw = X1 - rx
heading(s, rx, 2.55, rw, 'What the deployments that work have in common', size=19)
traits = [('A named workflow with a number attached', 'Minutes per note, completions per hundred invitations, authorisations per day. Not "transformation".'),
          ('Data and systems that already exist', 'The EHR, the registry, the payer portal, the guideline. The agent is added to a workflow, not sold as a replacement for one.'),
          ('A person at the decision, an agent at the legwork', 'Denials go to a human. Drafts wait for sign-off. The clinician finalises the note.'),
          ('Measured in weeks, not promised in years', 'Burnout at 30 days, completions at six months, authorisations the next morning. If it cannot be measured quickly, it is not ready.')]
for i, (a, b) in enumerate(traits):
    numbered_row(s, rx, 3.3 + i * 1.65, rw, i + 1, a, b, row_h=1.5, fill=NAVY if i % 2 == 0 else BLUE)
sources(s, 'Sources: MIT NANDA, The GenAI Divide: State of AI in Business 2025 (preliminary, July 2025)  ·  Gartner, press release, 25 June 2025: over 40% of agentic AI projects will be cancelled by end of 2027.')
notes(s, """
Credibility slide. Two numbers the sceptics in the room already know: 95% of generative-AI pilots with no measurable
return, and more than four in ten agentic projects expected to be cancelled by 2027. Do not argue with them; agree,
and then show what separates the six deployments on the evidence slide from the pilots that died. A workflow with a
number. Data that already exists. A person at the decision. Measured in weeks. The two demos are built to pass all
four tests, and the last slide of the deck turns them into a checklist for the hackathon use cases.
""")

# 9 ---- Section: Example 1 ------------------------------------------------------------------
s = section_slide('Example 1 · Population health', 'A diabetes registry that answers back', 'heart', title_size=54)
notes(s, "Example 1. Five minutes on the problem, the solution and the demo plan, then ten minutes live in the app: the Assistant tab, with the trace panel open.")

# 10 ---- Example 1: the problem --------------------------------------------------------------
s = action_slide('The problem: the registry already knows who is slipping, but every answer costs days of analyst time', 'EXAMPLE 1 · POPULATION HEALTH')
lw = 10.0
scq(s, X0, 2.55, lw, 'Situation',
    'A programme lead runs diabetes care for 4,000 registered patients across 18 hospitals and health centres in five regions. The registry holds 54 fields per patient: '
    'HbA1c, blood pressure, lipids, kidney function, therapy, adherence, open care gaps, visits and cost, over 36 months.', h=2.0)
scq(s, X0, 5.1, lw, 'Complication',
    'The questions that matter every week (who is uncontrolled, where the gaps are, who is at risk, what the guideline says, what a programme would save) each need an analyst request, '
    'a guideline lookup and a spreadsheet. Answers take days, so the questions are asked rarely, and the gaps are found late.', h=2.0)
scq(s, X0, 7.65, lw, 'What good looks like',
    'Ask the registry in plain language and get the number with its cohort, the guideline section that applies, a chart, and a draft action ready for a clinician to approve. '
    'In seconds, with the trail to prove where every figure came from.', h=2.0)
tx = 12.1; tw = (X1 - tx - 0.3) / 2; th = 1.95
tiles = [('4,000', 'patients, 18 facilities, 5 regions'), ('34.9%', 'well controlled (HbA1c below 7%)'),
         ('760', 'patients overdue an HbA1c test'), ('AED 64.0M', 'annual cost, last 12 months')]
for i, (n, lab) in enumerate(tiles):
    r, c = divmod(i, 2)
    stat_tile(s, tx + c * (tw + 0.3), 2.6 + r * (th + 0.3), tw, th, n, lab, num_size=30, label_size=13, num_color=BLUE)
text(s, tx, 7.15, X1 - tx, 1.6, 'A synthetic registry modelled on a national health information exchange, with a teaching set of national guidelines. The numbers are real for this data only.', size=12, color=SLATE)
notes(s, """
Situation, complication, what good looks like. The programme lead has the data: 4,000 patients, 54 fields, three
years of history. What they do not have is the hours: every question is an analyst request and a guideline lookup,
so questions are asked rarely and gaps are found late. The tiles give the room a feel for the registry before the
demo: a third well controlled, 760 overdue a test, AED 64 million a year. Be explicit that the data is synthetic and
the guidelines are a teaching set; the numbers are real for this data only.
""")

# 11 ---- Example 1: the solution overview --------------------------------------------------
s = action_slide('The solution: one agent over the registry, the guidelines and the models, and a person who signs every action', 'EXAMPLE 1 · POPULATION HEALTH')
solution_overview(s,
    left_top=('Unstructured data', 'Clinical guidelines & policy documents', 'National guidelines, care protocols, policy frameworks', 'Embedding model', 'Vector store (RAG)'),
    left_bottom=('Structured data', 'National HIE  ·  diabetes registry', 'Patients, encounters, diagnoses, facilities: 4,000 patients, 36 months'),
    agent=('Population Health Agent', 'Patient-level questions, population insights, cost and policy what-ifs, with cited, traceable reasoning. English or Arabic.',
           ['Orchestrator: a supervisor sends five specialists to work', 'Guideline grounding: every clinical statement cites its section', 'Audit log: every call on record, next to the answer'],
           'Agentic retrieval'),
    tools=['Score & simulate (deployed ML models)', 'Quality measures & care gaps', 'Draft action → approval queue', 'Generate charts', 'Query data (SQL)'],
    bridge=('table', 'CAS table (SAS Viya)', 4),
    delivers=['Ask in plain language; get governed numbers, cohorts and charts', 'Risk scoring, programme simulation and demand forecasts on demand',
              'Every answer cites the guideline, shows its tool calls, and ends in a draft a person approves'])
notes(s, """
The one picture to remember. Left: two kinds of data. The guidelines are chunked, embedded and stored as vectors (the
knowledge base the agent quotes from); the registry is loaded as a CAS table in SAS Viya. Middle: the agent, a
supervisor that sends five specialists to work (cohort, guideline, risk, population health, action), grounds every
clinical statement in a guideline section, and logs every call. Right: the MCP server and the tools it exposes: score
and simulate with the deployed models, quality measures and care gaps, a draft that lands in the approval queue, a
chart, a query. Follow the dotted line: the registry becomes a CAS table and the SQL tool reads it; the agent itself
never touches the table. Nothing the agent drafts reaches the record; the approval queue is the only exit.
""")

# 12 ---- Example 1: the demo plan ------------------------------------------------------------
s = action_slide('What you will see: four questions a programme lead asks on a Monday morning', 'EXAMPLE 1 · POPULATION HEALTH')
qs = [('Give me my morning briefing: review the panel and tell me who needs attention today.',
       'The cohort and risk specialists scan the panel; the supervisor ranks who needs attention and why.', 'A ranked list, one reason per name. The programme lead decides.'),
      ('Review my highest-risk patient whose HbA1c is rising on metformin alone: summarise, score the risk, check the guideline, and draft what is needed.',
       'The record and 36-month trajectory; the model score with its drivers; the guideline section; a draft prescription change.', 'A summary, a score, a citation, a draft. The clinician decides, in the approval queue.'),
      ('How many type 2 patients with HbA1c above 8% are not on an SGLT2 inhibitor or GLP-1 agonist, what is closing that gap worth, and draft the review list.',
       'A cohort query; the intervention priced from the measured effects in the policy document; a review list drafted.', 'A number with its cohort, a value in AED, a list. The clinic decides, from the queue.'),
      ('Which patients are overdue for retinal screening, where is the backlog, and draft the recall.',
       'A care-gap query by facility; a chart of the backlog; a recall campaign drafted.', 'A chart, a facility ranking, a recall draft. The programme lead decides.')]
qw = (XW - 0.4) / 2; qh = 3.55
for i, (q, under, out) in enumerate(qs):
    r, c = divmod(i, 2)
    x = X0 + c * (qw + 0.4); y = 2.5 + r * (qh + 0.3)
    card(s, x, y, qw, qh)
    o = oval(s, x + 0.6, y + 0.6, 0.62, fill=BLUE); shape_text(o, str(i + 1), size=18, color=WHITE, bold=True, margins=(0, 0, 0, 0))
    text(s, x + 1.1, y + 0.25, qw - 1.4, 1.35, '“' + q + '”', size=14, color=NAVY, bold=True)
    text(s, x + 0.4, y + 1.7, qw - 0.8, 0.3, 'UNDERNEATH', size=10.5, color=BLUE, bold=True)
    text(s, x + 0.4, y + 1.98, qw - 0.8, 0.7, under, size=12.5, color=INK)
    text(s, x + 0.4, y + 2.65, qw - 0.8, 0.3, 'OUT, AND WHO DECIDES', size=10.5, color=BLUE, bold=True)
    text(s, x + 0.4, y + 2.93, qw - 0.8, 0.6, out, size=12.5, color=INK)
text(s, X0, 10.0, XW, 0.4, 'If time allows: the programme simulation on the ML model, the equity analysis, the 12-month demand forecast, the quality scorecard over MCP. Keep the trace panel open.', size=12, color=SLATE)
notes(s, """
One minute, then switch to the app. Four questions in a deliberate order: a briefing (the agent reads the whole
panel), a single patient (record, score, guideline, draft), a cohort with a value attached (what closing the gap is
worth), and a recall campaign (a chart and a draft). For each, show the answer, then point at the trace: which
specialist was called, what it ran, what came back. The approval queue is the end of every path. If the environment
is slow, drop question 4; if it fails, use the next slide.
""")

# 13 ---- Example 1: anatomy of one answer ----------------------------------------------------
s = action_slide('Every number traces to a query, every recommendation to a guideline section, every action to a person', 'EXAMPLE 1 · POPULATION HEALTH')
rect(s, X0, 2.55, XW, 7.5, fill=PANEL, radius=0.35, shadow=True)
steps = [('1 · Cohort specialist', 'Pulls the patient\'s record and 36-month trajectory from the exchange: HbA1c rising from 9.2% to 10.3% on metformin alone, BMI 31.7, adherence 45%.', NAVY),
         ('2 · Risk specialist', 'Scores the deployed model: a deterioration risk well above the 10.4% base rate, with the drivers that moved it.', SKY),
         ('3 · Guideline specialist', 'Retrieves the diabetes guideline, section 4: consider a GLP-1 receptor agonist when HbA1c stays above target and BMI is over 30. Cited by section.', BLUE),
         ('4 · Action specialist', 'Drafts the prescription change and the referral, citation attached. Nothing reaches the record.', NAVY),
         ('5 · Supervisor', 'Writes the answer: summary, score, citation, draft, and a source line listing every call it made.', BLUE),
         ('6 · The clinician', 'Approves, edits or rejects in the queue. The decision and the full trace are logged together.', GREEN)]
cw2 = 5.05; gap = 0.67; ch2 = 2.75
for i, (t, d, col) in enumerate(steps):
    r, c = divmod(i, 3)
    x = X0 + 0.5 + c * (cw2 + gap); y = 3.35 + r * (ch2 + 0.95)
    card(s, x, y, cw2, ch2, shadow=False)
    p = rect(s, x + 0.35, y - 0.3, cw2 - 0.7, 0.6, fill=col, radius=0.3, shadow=True)
    shape_text(p, t, size=15, color=WHITE, bold=True, margins=(0.1, 0.02, 0.1, 0.02))
    text(s, x + 0.35, y + 0.5, cw2 - 0.7, ch2 - 0.65, d, size=13.5, color=INK, anchor='m', align='c')
    if c < 2:
        arrow(s, x + cw2 + 0.12, y + ch2 / 2 - 0.22, gap - 0.24, 0.44, kind='right')
notes(s, """
Question 2, taken apart. Use it after the live demo to replay what the room just saw, or instead of it if the
environment fails. Six beats: the cohort specialist pulls the record, the risk specialist scores it, the guideline
specialist finds the section, the action specialist drafts, the supervisor writes the cited answer, and the
clinician decides. Three design choices are hiding here: the guideline was read before any recommendation was
written; the draft never reached the record; and the decision is logged next to the trace that produced it.
""")

# 14 ---- Section: Example 2 ------------------------------------------------------------------
s = section_slide('Example 2 · Cancer early warning', 'A bowel-cancer screening check that triages, routes and explains', 'scan', title_size=54)
notes(s, "Example 2. Five minutes on the problem, the engine and the four people, then seven minutes live in the app: the Example 2 tab.")

# 15 ---- Example 2: the problem --------------------------------------------------------------
s = action_slide('The problem: bowel cancer in the UAE strikes young, and screening only works if people know they are due', 'EXAMPLE 2 · CANCER EARLY WARNING')
lw = 10.0
scq(s, X0, 2.55, lw, 'Situation',
    'Bowel cancer is the most common cancer among men in the UAE and the third overall. Registered cases rose from 377 in 2013 to 532 in 2021, and between a quarter and a half are diagnosed '
    'before the age of 50. The national programme therefore starts at 40, with a yearly stool test (FIT) or a colonoscopy every ten years, up to 75.', h=2.3)
scq(s, X0, 5.25, lw, 'Complication',
    'Most people do not know their risk tier, which test applies to them, when it is due or where the nearest door is. Family history changes the rules and is rarely asked. '
    'Warning symptoms get parked, and once there are symptoms a stool test is the wrong test.', h=1.9)
scq(s, X0, 7.65, lw, 'What good looks like',
    'Anyone can find out in two minutes what applies to them and where to go. Red flags go straight to the urgent route. '
    'And the programme can see who is due, who is overdue and where the capacity is.', h=1.9)
tx = 12.1; tw = (X1 - tx - 0.3) / 2; th = 1.95
tiles = [('No. 1', 'cancer among men in the UAE; third overall'), ('532', 'new cases in 2021, up from 377 in 2013'),
         ('24–50%', 'of cases diagnosed before the age of 50'), ('40', 'the age screening starts in the UAE; 45 to 50 elsewhere')]
for i, (n, lab) in enumerate(tiles):
    r, c = divmod(i, 2)
    stat_tile(s, tx + c * (tw + 0.3), 2.6 + r * (th + 0.3), tw, th, n, lab, num_size=30, label_size=13, num_color=BLUE)
text(s, tx, 7.15, X1 - tx, 1.6, 'The check is an educational prototype on a published risk score and a simplified version of the national programme. It does not diagnose, and it says so.', size=12, color=SLATE)
sources(s, 'Sources: UAE National Cancer Registry, Cancer Incidence in UAE, annual report (MOHAP)  ·  Al-Shamsi et al., "Not only a Western world issue: cancer incidence in younger individuals in the UAE", CA: A Cancer Journal for Clinicians, 2024  ·  '
           'UAE National Guideline for Colorectal Cancer Screening and Diagnosis (MOHAP).')
notes(s, """
Same structure as Example 1. Situation: bowel cancer is the most common cancer among men in the UAE, it is rising,
and it strikes young, which is why the national programme starts at 40 rather than 45 or 50. Complication: the
programme only works if people know they are due, which test applies, and where to go; family history changes the
rules and is rarely asked; symptoms get parked. What good looks like: two minutes to a personal answer, red flags
straight to the urgent route, and a programme view of who is due. Be clear that the check is a prototype on a
published score and a simplified version of the programme; it does not diagnose.
""")

# 16 ---- Example 2: the solution overview --------------------------------------------------
s = action_slide('The solution: a screening agent that scores risk, picks the pathway and points to the nearest door', 'EXAMPLE 2 · CANCER EARLY WARNING')
solution_overview(s,
    left_top=('Unstructured input', 'What the person writes in their own words', 'Symptoms, family history, worries, questions', 'Language model reads it', 'Flags to tick, questions answered'),
    left_bottom=('Structured input', 'The screening form', 'Age, sex, BMI, smoking, family history, own history, symptoms, last test, location'),
    agent=('Screening Agent', 'Scores risk, picks the pathway, finds the nearest door, explains the result and answers questions. English or Arabic.',
           ['Rules first: a published score and the national programme decide', 'Red flags override everything: a doctor within two weeks', 'Never diagnoses, nothing stored'],
           'Free text in'),
    tools=['Score risk (APCS, Gut 2011)', 'Apply pathway rules (national programme)', 'Find the nearest facility (distance, minutes)', 'Lifestyle levers', 'Answer questions (LLM)'],
    bridge=('map', 'Facilities & services table', 2),
    delivers=['A risk tier with the measured chance of a finding at colonoscopy', 'The right test, when it is due, and where to go, on a map',
              'Red flags routed to a doctor within two weeks, not into the screening queue'])
text(s, X0, 9.85, XW, 0.4, 'Educational prototype: a published score, a simplified version of the national programme, no diagnosis, nothing stored.', size=11, color=SLATE)
notes(s, """
Same picture, second example. Left: what the person writes in their own words is read by the language model and turned
into flags to tick ("you mentioned blood") and questions answered; what they enter in the form feeds the score and the
rules. Middle: the screening agent, with the rules in charge: a published score and the national programme decide the
pathway, red flags override everything, the model only explains, nothing is stored. Right: the tools behind the MCP
server: the score, the pathway rules, the nearest facility with distance and minutes, the lifestyle levers, and the
question-answering model. Follow the dotted line: the facilities table feeds the nearest-door tool. What it delivers: a
tier with a measured chance, the right test and place, and red flags sent to a doctor rather than the screening queue.
""")

# 17 ---- Example 2: the demo plan, four personas --------------------------------------------
s = action_slide('What you will see: four people, four different routes through the same programme', 'EXAMPLE 2 · CANCER EARLY WARNING')
people = [('Fatima', '44', 'Never screened, no family history, non-smoker, BMI 24', 'Average · 0 of 8 points', LIGHT, NAVY,
           'Due now: a FIT kit at home, repeated yearly', 'The nearest health centre'),
          ('Khalid', '56', 'Smoker, diabetes, BMI 30, father diagnosed at 71, never screened', 'Higher · 7 of 8 points', BLUE, WHITE,
           'Due now; with this tier, colonoscopy is worth considering directly', 'A health centre for FIT, or a hospital for colonoscopy'),
          ('Mariam', '38', 'Sister diagnosed at 46; otherwise healthy, active, non-smoker', 'Moderately raised · 2 of 8', SKY, WHITE,
           'Colonoscopy every five years from 36: due now, not at 40', 'A hospital endoscopy unit'),
          ('Youssef', '61', 'Bleeding and a changed bowel habit for three weeks; last colonoscopy over ten years ago', 'Symptoms decide, not the score', RED, WHITE,
           'Urgent: a doctor within two weeks, then colonoscopy by referral. Not screening.', 'The nearest doctor, this week')]
pw = (XW - 3 * 0.4) / 4; ph = 6.7
for i, (name, age, enters, tier, tcol, ttxt, route, where) in enumerate(people):
    x = X0 + i * (pw + 0.4); y = 2.55
    card(s, x, y, pw, ph)
    text(s, x + 0.35, y + 0.3, pw - 0.7, 0.55, [{'t': name + '  ', 'size': 22, 'bold': True}, {'t': age, 'size': 16, 'color': SLATE}], color=INK)
    text(s, x + 0.35, y + 1.05, pw - 0.7, 0.3, 'ENTERS', size=10.5, color=BLUE, bold=True)
    text(s, x + 0.35, y + 1.33, pw - 0.7, 1.3, enters, size=12.5, color=INK)
    p = rect(s, x + 0.35, y + 2.75, pw - 0.7, 0.5, fill=tcol, radius=0.25)
    shape_text(p, tier, size=11.5, color=ttxt, bold=True, margins=(0.1, 0.02, 0.1, 0.02))
    text(s, x + 0.35, y + 3.5, pw - 0.7, 0.3, 'THE ROUTE', size=10.5, color=BLUE, bold=True)
    text(s, x + 0.35, y + 3.78, pw - 0.7, 1.55, route, size=13, color=NAVY, bold=True)
    text(s, x + 0.35, y + 5.35, pw - 0.7, 0.3, 'WHERE', size=10.5, color=BLUE, bold=True)
    text(s, x + 0.35, y + 5.63, pw - 0.7, 0.95, where, size=12.5, color=INK)
text(s, X0, 9.5, XW, 0.7, 'Then: type "I noticed some blood last week" into the notes and watch the check pick it up. Ask the assistant what a FIT test involves, in Arabic. Finally, zoom out to the programme view.', size=12, color=SLATE)
notes(s, """
Four people, chosen so that the same programme sends each one somewhere different. Fatima: average risk, due for
her first FIT at the nearest health centre. Khalid: seven points out of eight, due now, and the check says
colonoscopy is worth considering directly. Mariam: 38, so not yet 40, but a sister diagnosed at 46 moves her to
colonoscopy from 36, so she is due now. Youssef: the score is irrelevant, the symptoms send him to a doctor within
two weeks. Then the two things that show the agent: free text being picked up, and a question answered in Arabic.
""")

# 18 ---- Example 2: at programme scale -------------------------------------------------------
s = action_slide('From one person to a programme: the same engine over the registry becomes an early-warning system', 'EXAMPLE 2 · CANCER EARLY WARNING')
lw = 9.3
heading(s, X0, 2.55, lw, 'What the engine does at population scale', size=19)
rowsL = [('users', 'Who is due, and who is overdue', 'By facility and region, with the test that applies to each person, so outreach starts from a list rather than a campaign.'),
         ('alarm', 'Red flags into the urgent route', 'Symptoms reported anywhere (a form, a note, a call) are triaged to a doctor within two weeks, not into the screening queue.'),
         ('map', 'Capacity matched to demand', 'FIT kits at health centres, endoscopy slots at hospitals, and the travel time in between, so the list is bookable.')]
for i, (ic, a, b) in enumerate(rowsL):
    icon_row(s, X0, 3.4 + i * 1.9, lw, ic, a, b, circle=RED if ic == 'alarm' else (NAVY if i % 2 == 0 else BLUE), d=0.7, label_size=16, desc_size=13.5, row_h=1.7)
rx = 11.4; rw = X1 - rx
heading(s, rx, 2.55, rw, 'What the evidence says it is worth', size=19)
stat_tile(s, rx, 3.3, rw, 2.7, '43%', 'lower two-year mortality when machine learning picks who to call and the outreach follows the list; 6.9% more colonoscopies completed within six months (Geisinger, 2026).', num_size=36, num_color=BLUE)
stat_tile(s, rx, 6.3, rw, 2.7, '2.6×', 'the FIT opt-in rate when an AI agent calls people in their own language: 18.2% among Spanish speakers against 7.1% among English speakers (WellSpan Health with Hippocratic AI, 2025).', num_size=36, num_color=BLUE)
sources(s, 'Sources: "Cancer Screening Outreach Guided by Machine Learning: The Benefits of Proactive Care", Manufacturing & Service Operations Management, 2026 (Geisinger)  ·  '
           'WellSpan Health / Hippocratic AI, retrospective analysis of a multilingual AI care agent for colorectal cancer screening, 2025 (completion rates not measured).')
notes(s, """
Zoom out. The check you just saw is one person at a time; the same score and the same rules over the registry
produce the programme view: who is due, who is overdue, by facility; red flags triaged out of the screening queue;
capacity matched to demand. And the evidence that this is worth doing is already published: at Geisinger, a
machine-learning list plus outreach cut two-year mortality by 43% relative to controls; at WellSpan, an AI agent
calling people in their own language more than doubled FIT opt-in among the group the system was failing. Note the
caveat on WellSpan: opt-in, not completion. That is the bridge back to the hackathon: this is a use case with
real-world data, published evidence, and a number to beat.
""")

# 19 ---- Blueprint comparison ---------------------------------------------------------------
s = action_slide('Both examples follow one blueprint: real-world data, published evidence, governed tools, a human decision', 'WHAT IT MEANS')
rows = [('', 'Example 1  ·  Population health', 'Example 2  ·  Cancer early warning'),
        ('Real-world data', 'A diabetes registry from the health information exchange: 4,000 patients, 36 months', 'What one person enters, plus the facilities and the services each offers'),
        ('Evidence it stands on', 'Four national guidelines, cited by section; a deterioration-risk model with drivers', 'A validated clinical score (Gut, 2011) and the national screening programme'),
        ('Tools the agent calls', 'Registry queries, model scoring, quality measures and care gaps over MCP, guideline retrieval', 'The score, the pathway rules, distance to facilities; the language model only explains'),
        ('Output, and who decides', 'A cited answer, a chart, a draft in the approval queue; the clinician or programme lead decides', 'A tier, a pathway, a place to go, what to change; the person and their doctor decide'),
        ('What is logged', 'Every specialist call, query and retrieval, next to the answer', 'Every input and the rule that fired, next to the result')]
table(s, X0, 2.55, XW, 6.9, rows, [3.35, 6.95, 6.95], header_size=15, body_size=14, header_h=0.7, first_col_color=NAVY)
notes(s, """
One table, two columns, five rows: the blueprint. Both examples start from real-world data that already exists,
stand on published evidence (guidelines, a validated score, a national programme), use a model and explicit rules
as tools, produce a draft or a recommendation rather than an action, leave the decision with a person, and log
everything. The language model is in neither column as a source of facts; it reads, chooses and writes. This is the
table to copy when a team designs its own use case.
""")

# 20 ---- Five tests -------------------------------------------------------------------------
s = action_slide('Five tests for an agentic use case worth building', 'WHAT IT MEANS')
tests = [('A workflow with a number on it', 'Someone does it by hand today, and you can say what better means: minutes, completions, approvals, days to an answer.'),
         ('Data that already exists', 'A registry, the HIE, a screening programme, claims. The agent reads what is there; it does not wait for a data project.'),
         ('Evidence to stand on', 'A guideline to cite, a published score, a champion model. The agent quotes and calls; it does not improvise.'),
         ('A person at the decision', 'The agent drafts, lists and ranks. A clinician or a manager approves. Decide where that line sits before you build.'),
         ('A trace you could show an auditor', 'Every query, retrieval and model call next to the answer. If you cannot see how it got there, you cannot trust it.')]
sw5 = (XW - 4 * 0.4) / 5
for i, (t, d) in enumerate(tests):
    x = X0 + i * (sw5 + 0.4); y = 2.7; h = 5.3
    card(s, x, y, sw5, h, fill=NAVY if i == 4 else WHITE)
    dark = i == 4
    c = oval(s, x + 0.7, y + 0.7, 0.9, fill=WHITE if dark else (NAVY if i % 2 == 0 else BLUE))
    shape_text(c, str(i + 1), size=24, color=NAVY if dark else WHITE, bold=True, margins=(0, 0, 0, 0))
    text(s, x + 0.3, y + 1.45, sw5 - 0.6, 1.25, t, size=17, color=WHITE if dark else INK, bold=True)
    text(s, x + 0.3, y + 2.75, sw5 - 0.6, h - 2.95, d, size=14, color=WHITE if dark else INK)
text(s, X0, 8.35, XW, 1.1, 'On SAS Viya this is the standard toolkit: Intelligent Decisioning sets the autonomy-to-oversight ratio for an agent and approves, audits and traces its decisions; '
     'Retrieval Agent Manager builds the knowledge base and the agent without code; the models come from Model Studio. (SAS Innovate, April 2026.)', size=12.5, color=SLATE)
notes(s, """
The close, and the hand-over to the hackathon teams. Five tests, drawn from the evidence slide and the two demos: a
workflow with a number, data that exists, evidence to stand on, a person at the decision, a trace. A use case that
passes all five is one of the deployments on slide 6 waiting to happen; one that fails two of them is one of
Gartner's cancellations. The footer names the SAS tooling, once: decisioning for the oversight ratio and the audit,
Retrieval Agent Manager for the knowledge base and the agent, Model Studio for the models. Then questions.
""")

# 21 ---- Sources ----------------------------------------------------------------------------
s = action_slide('Sources', title_size=36)
srcL = [
    '1. International Diabetes Federation. IDF Diabetes Atlas, 11th edition (2025): United Arab Emirates country profile.',
    '2. UAE National Cancer Registry. Cancer Incidence in United Arab Emirates, annual report 2021. Ministry of Health and Prevention.',
    '3. Al-Shamsi HO et al. Not only a Western world issue: cancer incidence in younger individuals in the United Arab Emirates. CA: A Cancer Journal for Clinicians, 2024.',
    '4. Ministry of Health and Prevention. The National Guideline for Colorectal Cancer Screening and Diagnosis, UAE.',
    '5. Yeoh KG et al. The Asia-Pacific Colorectal Screening score. Gut 2011;60:1236-41.',
    '6. JAMA, April 2026. Changes in clinician time expenditure and visit quantity with adoption of AI-powered scribes: a multisite study (Mass General Brigham, Emory, UCSF, Yale New Haven Health, UC Davis).',
    '7. Olson KE et al. Ambient artificial intelligence scribes to reduce administrative burden and professional burnout. JAMA Network Open, October 2025.',
    '8. Cancer screening outreach guided by machine learning: the benefits of proactive care. Manufacturing & Service Operations Management, 2026 (Geisinger).',
]
srcR = [
    '9. WellSpan Health and Hippocratic AI. Using a multilingual AI care agent to reduce disparities in colorectal cancer screening: higher FIT adoption among Spanish-speaking patients. Retrospective analysis, 2025.',
    '10. Becker\'s Hospital Review, 2025. Prior authorizations, patient check-ins: MUSC Health\'s AI agents; Notable customer story.',
    '11. Jin Q et al. Matching patients to clinical trials with large language models (TrialGPT). Nature Communications, 2024.',
    '12. MIT NANDA. The GenAI Divide: State of AI in Business 2025. Preliminary report, July 2025.',
    '13. Gartner. Press release, 25 June 2025: Gartner predicts over 40% of agentic AI projects will be canceled by end of 2027.',
    '14. SAS. Press releases, SAS Innovate, April 2026: SAS Viya governed AI assistants and agentic AI capabilities; SAS Intelligent Decisioning; SAS Retrieval Agent Manager.',
    '15. MedCity News, March 2026. Real-world evidence meets machine learning (RWE in about 70% of new drug and biologic submissions to the FDA).',
]
text(s, X0, 2.4, 8.45, 7.7, [{'t': t, 'space_after': 9} for t in srcL], size=11.5, color=INK)
text(s, X0 + 8.8, 2.4, 8.45, 7.7, [{'t': t, 'space_after': 9} for t in srcR], size=11.5, color=INK)
notes(s, "Reference slide. Leave it in the shared deck; skip it live.")

# 22 ---- Closing ----------------------------------------------------------------------------
s = prs.slides.add_slide(LAY['SAS - Closing'])
set_ph(s.shapes.title, 'Thank you!', size=72)
set_ph(placeholder(s, 11), 'Questions?', size=28)
notes(s, "Questions. Keep the evidence slide (6) and the blueprint (19) ready to flip back to.")

prs.save(OUT)
print('saved', OUT, 'slides:', len(prs.slides))
