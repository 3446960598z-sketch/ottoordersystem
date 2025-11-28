import csv
from django.core.management.base import BaseCommand, CommandParser
from shop.models import Product, Shop
from django.core.exceptions import ObjectDoesNotExist

class Command(BaseCommand):
    help = '从 CSV 文件批量导入商品数据'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('csv_file', type=str, help='要导入的 CSV 文件路径')

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        self.stdout.write(self.style.SUCCESS(f'开始从 {csv_file_path} 导入商品...'))

        try:
            with open(csv_file_path, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    try:
                        shop_id = row['shop_id']
                        shop = Shop.objects.get(pk=shop_id)
                        
                        product, created = Product.objects.update_or_create(
                            sku=row['sku'],
                            defaults={
                                'shop': shop,
                                'name': row['name'],
                                'price': row['price'],
                                'stock': row['stock'],
                                'description': row.get('description', ''),
                            }
                        )
                        
                        if created:
                            self.stdout.write(self.style.SUCCESS(f'成功创建商品: {product.name}'))
                        else:
                            self.stdout.write(self.style.WARNING(f'成功更新商品: {product.name}'))

                    except ObjectDoesNotExist:
                        self.stderr.write(self.style.ERROR(f"错误: 店铺 ID {row.get('shop_id')} 不存在，跳过行: {row}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f'处理行时出错 {row}: {e}'))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'错误: 文件 {csv_file_path} 未找到。'))
        
        self.stdout.write(self.style.SUCCESS('导入完成。'))
