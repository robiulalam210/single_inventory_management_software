"""পুরনো migration ফাইল মুছে ফেলে (শুধু প্রজেক্টের নিজের app)। ডাটাবেস ফ্রেশ শুরু করার সময় একবার চালান:

    python tools/reset_migrations.py
    python manage.py makemigrations
    python manage.py migrate
    python manage.py setup_erp --create-superuser --username admin --password <পাসওয়ার্ড>

সতর্কতা: এতে পুরনো ডাটাবেসের সাথে migration ইতিহাস মিলবে না — তাই ডাটাবেসও ফাঁকা/নতুন হতে হবে।
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
removed = 0
for mig in ROOT.glob('*/migrations'):
    if '.venv' in mig.parts or 'site-packages' in mig.parts:
        continue
    for f in mig.glob('*.py'):
        if f.name != '__init__.py':
            f.unlink(); removed += 1
            print('মোছা:', f.relative_to(ROOT))
    for f in mig.glob('*.pyc'):
        f.unlink()
print(f'{removed} টা migration ফাইল মোছা হয়েছে।')
