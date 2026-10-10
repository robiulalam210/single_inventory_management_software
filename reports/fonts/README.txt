PDF এ বাংলা/Unicode অক্ষর দেখাতে এখানে একটা .ttf ফন্ট রাখুন, নাম হতে হবে:
  NotoSansBengali-Regular.ttf   (বা HindSiliguri-Regular.ttf, DejaVuSans.ttf)
অথবা settings.py তে: REPORT_PDF_FONT = BASE_DIR / 'path/to/font.ttf'
(reportlab যুক্তাক্ষর জোড়া লাগাতে পারে না — বিস্তারিত UPDATE_GUIDE_BN.md দেখুন।)
