"""Pure profile routing and numeric conversions, independent of Home Assistant."""
from decimal import Decimal, InvalidOperation
import math
import re

VIEWS = ('home','timers','music','weather','guide','answer','controls')

def validate_profiles(config):
    profiles=config.get('devices', [])
    if not profiles: raise ValueError('At least one device profile is required')
    for field in ('id','satellite','device_id'):
        values=[p[field] for p in profiles]
        if len(set(values)) != len(values) or not all(values): raise ValueError('Duplicate or missing '+field)
    for p in profiles:
        if not re.fullmatch(r'[a-z0-9_]+',p['id']): raise ValueError('Invalid device slug')
        for k,domain in [('satellite','assist_satellite.'),('music_player','media_player.'),('weather','weather.')]:
            if not p[k].startswith(domain): raise ValueError('Invalid '+k)
        p.setdefault('name',p['id'].replace('_',' ').title())
        p.setdefault('controls',[])
        p.setdefault('speakers',[{'entity_id':p['music_player'],'name':p['name']}])
        if p['music_player'] not in [x['entity_id'] for x in p['speakers']]:raise ValueError('Default speaker missing')
        if not all(x['entity_id'].startswith('media_player.') for x in p['speakers']):raise ValueError('Invalid speaker')
        # Native players that make up this Echo's speaker, so playback started from the Sonos app or Spotify
        # Connect (which leaves the Music Assistant entity idle) still shows and is controlled here.
        native=p.setdefault('native_players',list((p.get('ducking') or {}).get('players',[])))
        if not isinstance(native,list) or not all(isinstance(e,str) and re.fullmatch(r'media_player\.[a-z0-9_]+',e) for e in native):raise ValueError('Invalid native players')
        cfg=p.get('ducking')
        if cfg is not None:
            if not isinstance(cfg,dict):raise ValueError('Invalid ducking configuration')
            cfg.setdefault('enabled',True)
            if not isinstance(cfg['enabled'],bool):raise ValueError('Invalid ducking enabled flag')
            players=cfg.get('players',[])
            satellites=cfg.get('additional_satellites',[])
            if not isinstance(players,list) or not players or not all(isinstance(e,str) and re.fullmatch(r'media_player\.[a-z0-9_]+',e) for e in players):raise ValueError('Ducking requires explicit media players')
            if len(players)!=len(set(players)):raise ValueError('Duplicate ducking player')
            if not isinstance(satellites,list) or not all(isinstance(e,str) and re.fullmatch(r'assist_satellite\.[a-z0-9_]+',e) for e in satellites):raise ValueError('Invalid ducking satellite')
            for key,default,low,high in [('volume_factor',0.1,0.01,1),('restore_delay',1,0,10),('max_duration',120,10,600)]:
                value=cfg.setdefault(key,default)
                if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid ducking '+key)

    return config

def route_profile(profiles, *, device_id=None, satellite=None):
    """No default fallback: an unknown origin must never control another Echo."""
    matches=[p for p in profiles if (device_id and p['device_id']==device_id) or (satellite and p['satellite']==satellite)]
    return matches[0] if len(matches)==1 else None

# SI factors; ounces are avoirdupois, not fluid ounces. Ambiguous cups/pints excluded.
UNITS = {
 'g':('mass','1'), 'kg':('mass','1000'), 'mg':('mass','0.001'),
 'oz':('mass','28.349523125'), 'lb':('mass','453.59237'),
 'ml':('volume','1'), 'l':('volume','1000'),
 'uk pint':('volume','568.26125'), 'us pint':('volume','473.176473'),
 'us cup':('volume','236.5882365'), 'metric cup':('volume','250'),
 'uk fl oz':('volume','28.4130625'), 'us fl oz':('volume','29.5735295625'),
 'mm':('length','0.001'), 'cm':('length','0.01'), 'm':('length','1'),
 'km':('length','1000'), 'in':('length','0.0254'), 'ft':('length','0.3048'), 'yd':('length','0.9144'), 'mi':('length','1609.344'),
 'c':('temperature','1'),'f':('temperature','1'),'k':('temperature','1'),
}
ALIASES={'grams':'g','gram':'g','kilograms':'kg','kilogram':'kg','milligrams':'mg','milligram':'mg','ounces':'oz','ounce':'oz','pounds':'lb','pound':'lb',
 'millilitres':'ml','milliliters':'ml','millilitre':'ml','milliliter':'ml','litres':'l','liters':'l','litre':'l','liter':'l',
 'celsius':'c','centigrade':'c','fahrenheit':'f','kelvin':'k','°c':'c','°f':'f',
 'millimetres':'mm','centimetres':'cm','metres':'m','meters':'m','kilometres':'km','kilometers':'km','inches':'in','inch':'in','feet':'ft','foot':'ft','yards':'yd','miles':'mi',
 'imperial pint':'uk pint','imperial pints':'uk pint','uk pints':'uk pint','us pints':'us pint','us cups':'us cup','metric cups':'metric cup',
 'millimetre':'mm','millimeter':'mm','millimeters':'mm','centimetre':'cm','centimeter':'cm','centimeters':'cm',
 'metre':'m','meter':'m','kilometre':'km','kilometer':'km','kilometers':'km','yard':'yd','mile':'mi'}

def convert(value, from_unit, to_unit):
    normalize=lambda unit:' '.join(unit.strip().lower().replace('_',' ').split())
    a=ALIASES.get(normalize(from_unit),normalize(from_unit))
    b=ALIASES.get(normalize(to_unit),normalize(to_unit))
    if a not in UNITS or b not in UNITS:
        missing=', '.join(u for u in (from_unit,to_unit) if ALIASES.get(normalize(u),normalize(u)) not in UNITS)
        raise ValueError(f'Unsupported or ambiguous unit: {missing}. Supported categories are length/distance, mass, volume and temperature. Cups, pints and fluid ounces need a UK, US or metric standard.')
    if UNITS[a][0]!=UNITS[b][0]:raise ValueError('These units measure different quantities. Volume to mass needs the ingredient and its density.')
    try: v=Decimal(str(value))
    except InvalidOperation as e:raise ValueError('A finite number is required') from e
    if not v.is_finite() or abs(v)>Decimal('1e18'):raise ValueError('A finite value within ±1e18 is required')
    if UNITS[a][0]=='temperature':
        c=(v-32)*Decimal(5)/9 if a=='f' else v-Decimal('273.15') if a=='k' else v
        if c<Decimal('-273.15'):raise ValueError('Temperature is below absolute zero')
        result=c*9/5+32 if b=='f' else c+Decimal('273.15') if b=='k' else c
    else:result=v*Decimal(UNITS[a][1])/Decimal(UNITS[b][1])
    number=float(result)
    if not math.isfinite(number):raise ValueError('Result is out of range')
    label=lambda u: {'c':'°C','f':'°F','k':'K','l':'L','ml':'mL'}.get(u,u)
    return {'value':float(v),'from_unit':label(a),'to_unit':label(b),'result':number,'equation':f'{float(v):g} {label(a)} = {number:,.4f}'.rstrip('0').rstrip('.')+f' {label(b)}'}


def normalize_timer_name(name):
    """Treat the optional spoken suffix 'timer' consistently without fuzzy matching."""
    text=' '.join(str(name or '').casefold().split())
    return re.sub(r'\s+timer$', '', text).strip()
