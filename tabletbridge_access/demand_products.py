"""Exact names only; no fuzzy conversion between goods or measurement units."""
import unicodedata
import re

PRODUCTS={'WHEAT':'Trigo','BARLEY':'Cevada','OAT':'Aveia','MAIZE':'Milho','CANOLA':'Canola',
    'SOYBEAN':'Soja','SUNFLOWER':'Girassol','SORGHUM':'Sorgo','RICE':'Arroz','RICELONGGRAIN':'Arroz longo',
    'STRAW':'Palha','SILAGE':'Silagem','GRASS_WINDROW':'Capim','DRYGRASS_WINDROW':'Feno',
    'POTATO':'Batata','SUGARBEET':'Beterraba','CARROT':'Cenoura','PARSNIP':'Pastinaca','BEETROOT':'Beterraba vermelha','PEA':'Ervilha'}
PRODUCTS.update({'FLOUR':'Farinha','BREAD':'Pão','SUGAR':'Açúcar','BUTTER':'Manteiga','CHEESE':'Queijo','EGG':'Ovos','WOOL':'Lã','MILK':'Leite','HONEY':'Mel','SEEDS':'Sementes','FERTILIZER':'Fertilizante sólido'})
def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFD',str(value).strip().casefold()) if unicodedata.category(c)!='Mn')
def product_key(name):
    if isinstance(name,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,39}',name.strip()):return name.strip()
    name=normalized(name)
    return next((key for key,label in PRODUCTS.items() if name in (normalized(key),normalized(label))),None)
def demand_matches(item,product,quantity,price):
    return (item.demand.status=='published' and item.unit=='L' and product_key(item.product_name)==product
        and quantity<=item.progress()['available'] and item.unit_price>0 and price==item.unit_price)
