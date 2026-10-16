# reports/exports.py
"""
Report export — Excel (.xlsx) ও PDF বানানোর কাজ।

এই ফাইলে Django এর কিছু নেই: শুধু (শিরোনাম, কলাম, সারি, সামারি) নিয়ে ফাইলের bytes ফেরত দেয়।
কোন report এ কোন কলাম — তা REPORT_EXPORTS এ (web/static/web/js/reports.js এর `cols` এর সাথে মিল রাখা)।

কলামের format (f):  money | money0 | int | pct | date | cap | text
"""
import io
import os
import re
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# ───────────────────────── কোন report এ কোন কলাম ─────────────────────────
# kind='table'     → সারির তালিকা (+ ঐচ্ছিক summary কার্ড)
# kind='statement' → Profit/Loss এর মতো একটা হিসাবের বিবরণী
REPORT_EXPORTS = {
    'sales': {
        'title': 'Sales Report', 'view': 'SalesReportView', 'dates': True,
        'cards': [('Sales', 'total_sales', 'money'), ('Cost', 'total_cost', 'money'), ('Profit', 'total_profit', 'money'),
                  ('Margin', 'average_profit_margin', 'pct'), ('Collected', 'total_collected', 'money'),
                  ('Due', 'total_due', 'money'), ('Invoices', 'total_transactions', 'int')],
        'cols': [('Invoice', 'invoice_no', 'text'), ('Date', 'sale_date', 'date'), ('Customer', 'customer_name', 'text'),
                 ('Sold by', 'sales_by', 'text'), ('Sales', 'sales_price', 'money'), ('Cost', 'cost_price', 'money'),
                 ('Profit', 'profit', 'money'), ('Collected', 'collect_amount', 'money'), ('Due', 'due_amount', 'money')],
    },
    'purchases': {
        'title': 'Purchase Report', 'view': 'PurchaseReportView', 'dates': True,
        'cards': [('Purchases', 'total_purchases', 'money'), ('Paid', 'total_paid', 'money'),
                  ('Due', 'total_due', 'money'), ('Invoices', 'total_transactions', 'int')],
        'cols': [('Invoice', 'invoice_no', 'text'), ('Date', 'purchase_date', 'date'), ('Supplier', 'supplier', 'text'),
                 ('Payment', 'payment_status', 'cap'), ('Total', 'net_total', 'money'), ('Paid', 'paid_total', 'money'),
                 ('Due', 'due_total', 'money')],
    },
    'profit-loss': {
        'title': 'Profit / Loss', 'view': 'ProfitLossReportView', 'dates': True, 'kind': 'statement',
    },
    'expenses': {
        'title': 'Expense Report', 'view': 'ExpenseReportView', 'dates': True,
        'cards': [('Expenses', 'total_count', 'int'), ('Total spent', 'total_amount', 'money')],
        'cols': [('Date', 'expense_date', 'date'), ('Head', 'head', 'text'), ('Sub head', 'subhead', 'text'),
                 ('Method', 'payment_method', 'text'), ('Note', 'note', 'text'), ('Amount', 'amount', 'money')],
    },
    'customer-due': {
        'title': 'Customer Due / Advance', 'view': 'CustomerDueAdvanceReportView', 'dates': True,
        'cards': [('Customers', 'total_customers', 'int'), ('Total sales', 'total_sales_amount', 'money'),
                  ('Received', 'total_received_amount', 'money'), ('Due', 'total_due_amount', 'money'),
                  ('Advance', 'total_advance_amount', 'money'), ('Net balance', 'net_balance', 'money')],
        'cols': [('No.', 'customer_no', 'text'), ('Customer', 'customer_name', 'text'), ('Phone', 'phone', 'text'),
                 ('Sales', 'total_sales', 'money'), ('Received', 'total_received', 'money'),
                 ('Due', 'present_due', 'money0'), ('Advance', 'present_advance', 'money0')],
    },
    'supplier-due': {
        'title': 'Supplier Due / Advance', 'view': 'SupplierDueAdvanceReportView', 'dates': True,
        'cards': [('Suppliers', 'total_suppliers', 'int'), ('Due', 'total_due_amount', 'money'),
                  ('Advance', 'total_advance_amount', 'money'), ('Net balance', 'net_balance', 'money')],
        'cols': [('No.', 'supplier_no', 'text'), ('Supplier', 'supplier_name', 'text'), ('Phone', 'phone', 'text'),
                 ('Email', 'email', 'text'), ('Due', 'present_due', 'money0'), ('Advance', 'present_advance', 'money0')],
    },
    'stock': {
        'title': 'Stock Report', 'view': 'StockReportView', 'dates': False,
        'cards': [('Products', 'total_products', 'int'), ('Units in stock', 'total_stock_quantity', 'int'),
                  ('Stock value', 'total_stock_value', 'money')],
        'cols': [('No.', 'product_no', 'text'), ('Product', 'product_name', 'text'), ('Category', 'category', 'text'),
                 ('Brand', 'brand', 'text'), ('Avg cost', 'avg_purchase_price', 'money'),
                 ('Price', 'selling_price', 'money'), ('In stock', 'current_stock', 'int'), ('Value', 'value', 'money')],
    },
    'low-stock': {
        'title': 'Low Stock', 'view': 'LowStockReportView', 'dates': False,
        'cards': [('Low-stock items', 'total_low_stock_items', 'int'), ('Out of stock', 'critical_items', 'int'),
                  ('Level used', 'threshold', 'int')],
        'cols': [('Product', 'product_name', 'text'), ('Category', 'category', 'text'), ('Brand', 'brand', 'text'),
                 ('Price', 'selling_price', 'money'), ('Alert at', 'alert_quantity', 'int'),
                 ('In stock', 'total_stock_quantity', 'int'), ('Sold', 'total_sold_quantity', 'int')],
    },
    'top-products': {
        'title': 'Top Selling Products', 'view': 'TopSoldProductsReportView', 'dates': True,
        'cards': [('Products', 'total_products', 'int'), ('Units sold', 'total_quantity_sold', 'int'),
                  ('Sales', 'total_sales_amount', 'money'), ('Profit', 'total_profit', 'money')],
        'cols': [('Product', 'product_name', 'text'), ('Price', 'selling_price', 'money'),
                 ('Sold', 'total_sold_quantity', 'int'), ('Sales', 'total_sold_price', 'money'),
                 ('Profit', 'total_profit', 'money'), ('In stock', 'current_stock', 'int')],
    },
}

# Profit/Loss বিবরণীর সারি: (লেখা, key, মোটা কিনা)
STATEMENT_LINES = [
    ('Sales', 'total_sales', False),
    ('Purchases', 'total_purchase', False),
    ('Gross profit', 'gross_profit', True),
    ('Expenses', 'total_expenses', False),
    ('Purchase returns (credit)', 'purchase_returns', False),
    ('Sales returns', 'sales_returns', False),
    ('Net profit', 'net_profit', True),
]


# ───────────────────────── ছোট সহায়ক ─────────────────────────
def to_number(v):
    """'1,234.50' / None / Decimal — সবই সংখ্যা করে; না পারলে 0।"""
    if v is None or v == '':
        return 0.0
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return 0.0


def to_date(v):
    """ISO তারিখ/সময়ের লেখা → date; না পারলে None।"""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', str(v))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def nice_date(v):
    d = to_date(v)
    return d.strftime('%d %b %Y') if d else ('—' if v in (None, '') else str(v))


def cap(v):
    return str(v).replace('_', ' ').capitalize() if v else '—'


def money_text(v):
    return f'{to_number(v):,.2f}'


def cell_text(value, f):
    """PDF/স্ক্রিনের মতো দেখানোর লেখা।"""
    if f == 'money':
        return money_text(value)
    if f == 'money0':
        return '—' if to_number(value) == 0 else money_text(value)
    if f == 'int':
        return f'{to_number(value):,.0f}'
    if f == 'pct':
        return f'{to_number(value):.1f}%'
    if f == 'date':
        return nice_date(value)
    if f == 'cap':
        return cap(value)
    return '—' if value in (None, '') else str(value)


def period_text(start, end, dates=True):
    if not dates:
        return 'As of ' + datetime.now().strftime('%d %b %Y')
    if not start and not end:
        return 'All time'
    if start == end:
        return nice_date(start)
    return f'{nice_date(start)} – {nice_date(end)}'


def safe_filename(key):
    return f'{re.sub(r"[^a-z0-9-]", "", key.lower())}-report-{datetime.now():%Y-%m-%d}'


# ───────────────────────── Excel ─────────────────────────
_HEAD_FILL = PatternFill('solid', fgColor='1F2937')
_HEAD_FONT = Font(bold=True, color='FFFFFF')
_THIN = Side(style='thin', color='D1D5DB')
_BORDER = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)


def build_xlsx(business, title, period, cols, rows, cards=None, statement=None):
    """
    cols: [(label, key, f)]   rows: [dict]   cards: [(label, value, f)]
    statement: [(label, value, bold)] — দিলে সারির তালিকার বদলে বিবরণী যায়।
    ফেরত: .xlsx এর bytes
    """
    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r'[\\/*?:\[\]]', '-', title)[:31]
    width = max(len(cols), 2) if cols else 2

    ws['A1'] = business
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f'{title} · {period}'
    ws['A2'].font = Font(color='6B7280')
    r = 4

    if cards:
        for label, value, f in cards:
            ws.cell(row=r, column=1, value=label).font = Font(bold=True)
            c = ws.cell(row=r, column=2)
            if f in ('money', 'money0', 'int', 'pct'):
                c.value = to_number(value)
                c.number_format = {'int': '#,##0', 'pct': '0.0"%"'}.get(f, '#,##0.00')
            else:
                c.value = cell_text(value, f)
            c.alignment = Alignment(horizontal='right')
            r += 1
        r += 1

    if statement is not None:
        for label, value, bold in statement:
            a = ws.cell(row=r, column=1, value=label)
            b = ws.cell(row=r, column=2, value=to_number(value))
            b.number_format = '#,##0.00;[Red]-#,##0.00'
            if bold:
                a.font = b.font = Font(bold=True)
            r += 1
        extra = statement_extra(statement)
        if extra:
            r += 1
            ws.cell(row=r, column=1, value='Expenses by head').font = Font(bold=True)
            r += 1
            for label, total in extra:
                ws.cell(row=r, column=1, value=label)
                b = ws.cell(row=r, column=2, value=to_number(total))
                b.number_format = '#,##0.00'
                r += 1
        ws.column_dimensions['A'].width = 34
        ws.column_dimensions['B'].width = 18
        return _save(wb)

    head_row = r
    for i, (label, _k, f) in enumerate(cols, 1):
        c = ws.cell(row=r, column=i, value=label)
        c.fill, c.font, c.border = _HEAD_FILL, _HEAD_FONT, _BORDER
        c.alignment = Alignment(horizontal='right' if f in ('money', 'money0', 'int', 'pct') else 'left')
    r += 1

    for row in rows:
        for i, (_label, k, f) in enumerate(cols, 1):
            raw = row.get(k)
            c = ws.cell(row=r, column=i)
            if f in ('money', 'money0'):
                c.value, c.number_format = to_number(raw), '#,##0.00'
            elif f == 'int':
                c.value, c.number_format = to_number(raw), '#,##0'
            elif f == 'pct':
                c.value, c.number_format = to_number(raw), '0.0"%"'
            elif f == 'date':
                d = to_date(raw)
                c.value = d if d else ('' if raw in (None, '') else str(raw))
                if d:
                    c.number_format = 'DD MMM YYYY'
                    c.alignment = Alignment(horizontal='left')
            elif f == 'cap':
                c.value = cap(raw) if raw else ''
            else:
                c.value = '' if raw is None else str(raw)
            c.border = _BORDER
        r += 1

    # কলামের চওড়া — লেখার সবচেয়ে বড় মাপ ধরে (সর্বোচ্চ ৪০)
    for i, (label, k, f) in enumerate(cols, 1):
        longest = max([len(str(label))] + [len(cell_text(row.get(k), f)) for row in rows[:500]])
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 3, 11), 40)
    ws.column_dimensions['A'].width = max(ws.column_dimensions['A'].width or 0, 16)
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f'A{head_row}:{get_column_letter(len(cols))}{head_row + len(rows)}'
    return _save(wb)


def _save(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ───────────────────────── PDF ─────────────────────────
# reportlab এর ডিফল্ট ফন্টে বাংলা নেই। একটা Unicode .ttf পেলে সেটা ব্যবহার হয়
# (settings.REPORT_PDF_FONT, বা reports/fonts/ এর নিচে)। না পেলে ইংরেজি/সংখ্যা ঠিক থাকে,
# বাংলা অক্ষর '?' হয় — Excel এ সবসময় পুরো বাংলা যায়।
_FONT_CACHE = {}


def _find_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if 'name' in _FONT_CACHE:
        return _FONT_CACHE['name']
    candidates = []
    try:
        from django.conf import settings
        if getattr(settings, 'REPORT_PDF_FONT', None):
            candidates.append(str(settings.REPORT_PDF_FONT))
    except Exception:
        pass
    here = os.path.join(os.path.dirname(__file__), 'fonts')
    candidates += [os.path.join(here, n) for n in ('NotoSansBengali-Regular.ttf', 'HindSiliguri-Regular.ttf', 'DejaVuSans.ttf')]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont('ReportFont', path))
                _FONT_CACHE['name'] = ('ReportFont', 'ReportFont', True)
                return _FONT_CACHE['name']
            except Exception:
                continue
    _FONT_CACHE['name'] = ('Helvetica', 'Helvetica-Bold', False)
    return _FONT_CACHE['name']


def _pdf_safe(text, unicode_ok):
    s = str(text)
    if unicode_ok:
        return s
    # Helvetica এর WinAnsi (cp1252) এ যা আছে (– — · › ইত্যাদি) রাখে; বাকি (বাংলা) '?'
    return s.encode('cp1252', 'replace').decode('cp1252')


def build_pdf(business, title, period, cols, rows, cards=None, statement=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold, uni = _find_font()
    safe = lambda t: _pdf_safe(t, uni)  # noqa: E731
    esc = lambda t: safe(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')  # noqa: E731

    wide = bool(cols) and len(cols) > 6
    page = landscape(A4) if wide else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm, title=title, author=business)

    h1 = ParagraphStyle('h1', fontName=bold, fontSize=15, leading=19)
    sub = ParagraphStyle('sub', fontName=regular, fontSize=9.5, leading=13, textColor=colors.HexColor('#6B7280'))
    cell = ParagraphStyle('cell', fontName=regular, fontSize=8, leading=10)
    cell_r = ParagraphStyle('cell_r', parent=cell, alignment=2)
    head = ParagraphStyle('head', parent=cell, fontName=bold, textColor=colors.white)
    head_r = ParagraphStyle('head_r', parent=head, alignment=2)

    story = [Paragraph(esc(business), h1),
             Paragraph(esc(f'{title} · {period}'), sub),
             Paragraph('Amounts in BDT', sub), Spacer(1, 6 * mm)]

    if cards:
        pairs = [[Paragraph(esc(l), cell), Paragraph(f'<b>{esc(cell_text(v, f))}</b>', cell_r)] for l, v, f in cards]
        t = Table(pairs, colWidths=[55 * mm, 40 * mm], hAlign='LEFT')
        t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E5E7EB')),
                               ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        story += [t, Spacer(1, 6 * mm)]

    if statement is not None:
        data = []
        for label, value, is_bold in statement:
            st, st_r = (ParagraphStyle('b', parent=cell, fontName=bold, fontSize=9.5), ParagraphStyle('br', parent=cell_r, fontName=bold, fontSize=9.5)) \
                if is_bold else (ParagraphStyle('n', parent=cell, fontSize=9.5), ParagraphStyle('nr', parent=cell_r, fontSize=9.5))
            data.append([Paragraph(esc(label), st), Paragraph(esc(money_text(value)), st_r)])
        t = Table(data, colWidths=[85 * mm, 45 * mm], hAlign='LEFT')
        t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E5E7EB')),
                               ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        story.append(t)
        # ব্যয়ের ভাগ (থাকলে)
        extra = statement_extra(statement)
        if extra:
            story += [Spacer(1, 6 * mm), Paragraph('<b>Expenses by head</b>', ParagraphStyle('s', parent=cell, fontName=bold, fontSize=10))]
            data = [[Paragraph(esc(a), cell), Paragraph(esc(money_text(b)), cell_r)] for a, b in extra]
            t2 = Table(data, colWidths=[85 * mm, 45 * mm], hAlign='LEFT')
            t2.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E5E7EB'))]))
            story += [Spacer(1, 2 * mm), t2]
    else:
        right = {'money', 'money0', 'int', 'pct'}
        data = [[Paragraph(esc(l), head_r if f in right else head) for l, _k, f in cols]]
        for row in rows:
            data.append([Paragraph(esc(cell_text(row.get(k), f)), cell_r if f in right else cell) for _l, k, f in cols])
        if len(data) == 1:
            data.append([Paragraph('No records for this period.', cell)] + [''] * (len(cols) - 1))
        avail = page[0] - 24 * mm
        weights = [1.6 if f == 'text' and k not in ('invoice_no', 'phone', 'customer_no', 'supplier_no', 'product_no') else 1.0
                   for _l, k, f in cols]
        widths = [avail * w / sum(weights) for w in weights]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor('#6B7280'))
        canvas.drawString(12 * mm, 8 * mm, safe(f'{business} · {title}'))
        canvas.drawRightString(page[0] - 12 * mm, 8 * mm, f'Page {d.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def statement_extra(statement):
    """P&L এর ব্যয়-ভাগ — build_* এ আলাদা করে পাঠানো হলে (statement_with_breakdown)।"""
    return getattr(statement, 'breakdown', None)


class _Statement(list):
    """list এর মতোই; সাথে ঐচ্ছিক expense breakdown বহন করে।"""
    breakdown = None


def statement_from_data(data):
    """ProfitLossReportView এর data dict → বিবরণীর সারি।"""
    lines = _Statement()
    for label, key, bold in STATEMENT_LINES:
        if key in ('purchase_returns', 'sales_returns') and key not in data:
            continue
        lines.append((label, data.get(key), bold))
    lines.breakdown = [
        ((e.get('head') or '—') + (f" › {e['subhead']}" if e.get('subhead') and e.get('subhead') != 'No Subcategory' else ''), e.get('total'))
        for e in (data.get('expense_breakdown') or [])
    ]
    return lines
