"""Bounded native object save DTO. Complete units, stable fill names, no paths outside game data/mods."""
from decimal import Decimal,InvalidOperation
import re

def decode_object(data):
    if not isinstance(data,str) or not 1<=len(data)<=8192 or len(data)%2 or not re.fullmatch('[0-9a-f]+',data):raise ValueError('Manifesto de objeto inválido.')
    try:raw=bytes.fromhex(data).decode('utf-8')
    except (ValueError,UnicodeError):raise ValueError('Manifesto de objeto inválido.') from None
    lines=raw.split('\n')
    if len(lines)<4 or lines[0]!='O1' or lines[1] not in ('Bale','Vehicle') or lines[-1]!='':raise ValueError('Classe de objeto incompatível.')
    fields={}
    for line in lines[2:-1]:
        match=re.fullmatch('([0-9a-f]+):([snbv]):([0-9a-f]*)',line)
        if not match:raise ValueError('Característica de objeto inválida.')
        key,kind,value=match.groups()
        try:key=bytes.fromhex(key).decode();value=bytes.fromhex(value).decode()
        except (ValueError,UnicodeError):raise ValueError('Característica de objeto inválida.') from None
        if len(fields)>=64 or len(key)>128 or len(value)>512 or not re.fullmatch(r'[A-Za-z0-9_.()#]+',key) or not re.search(r'#[A-Za-z][A-Za-z0-9_]*$',key) or '..' in key or key=='#farmId' or key in fields or any(ord(c)<32 for c in value):raise ValueError('Característica de objeto inválida.')
        if kind=='b' and value not in ('true','false'):raise ValueError('Característica de objeto inválida.')
        try:
            if kind=='n':
                number=Decimal(value)
                if not number.is_finite() or abs(number)>10**12:raise ValueError()
            elif kind=='v':
                parts=value.split()
                if not 2<=len(parts)<=4 or any(not Decimal(p).is_finite() or abs(Decimal(p))>10**12 for p in parts):raise ValueError()
        except (InvalidOperation,ValueError):raise ValueError('Número de objeto inválido.') from None
        fields[key]={'kind':kind,'value':value}
    path=fields.get('#filename',{}).get('value','')
    if not path.endswith('.xml') or '..' in path or re.search(r'[\\:\x00\r\n]',path) or not (path.startswith('data/') or re.match(r'^\$moddir\$[A-Za-z0-9_]+/',path)):raise ValueError('Modelo de objeto incompatível.')
    if fields.get('#isMissionBale',{}).get('value','false')!='false':raise ValueError('Objetos de missão não podem ser vendidos.')
    products={};total=Decimal(0)
    for key,row in fields.items():
        if key.endswith('#fillType'):
            product=row['value'];level=fields.get(key[:-9]+'#fillLevel')
            if row['kind']!='s' or not re.fullmatch('[A-Z][A-Z0-9_]{0,39}',product) or not level:raise ValueError('Produto de objeto incompatível.')
            try:amount=Decimal(level['value'])
            except InvalidOperation:raise ValueError('Quantidade de objeto inválida.') from None
            if not amount.is_finite() or amount<0:raise ValueError('Quantidade de objeto inválida.')
            if amount>0:products[product]=True;total+=amount
    if len(products)!=1 or not 0<total<=10**9 or total!=total.quantize(Decimal('.001')):raise ValueError('O objeto deve conter um único produto e volume conhecido.')
    return {'className':lines[1],'fields':fields,'filename':path,'product':next(iter(products)),'liters':total}
