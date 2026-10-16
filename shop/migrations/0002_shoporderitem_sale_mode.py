from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0001_initial'),
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='shoporderitem',
            name='sale_mode',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='products.salemode'),
        ),
        migrations.AddField(
            model_name='shoporderitem',
            name='mode_name',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
        migrations.AddField(
            model_name='shoporderitem',
            name='base_qty',
            field=models.PositiveIntegerField(default=0, help_text='বেস ইউনিটে (যেমন গ্রাম) স্টক থেকে যত কমবে; 0 = qty'),
        ),
        migrations.AlterField(
            model_name='shoporderitem',
            name='qty',
            field=models.PositiveIntegerField(help_text='সেল মোডের এককে পরিমাণ (প্যাক সংখ্যা / গ্রাম / কেজি)'),
        ),
    ]
