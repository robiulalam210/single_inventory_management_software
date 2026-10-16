from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='salemode',
            name='show_in_shop',
            field=models.BooleanField(default=True, help_text='অনলাইন শপে (ই-কমার্স) এই মোড দেখাবে'),
        ),
        migrations.AddField(
            model_name='salemode',
            name='show_in_webapp',
            field=models.BooleanField(default=True, help_text="ওয়েব অ্যাপের Sale / POS ফর্মের 'Sold by' এ এই মোড দেখাবে"),
        ),
    ]
