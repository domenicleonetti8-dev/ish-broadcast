from __future__ import annotations
import struct,time,zlib,zipfile
from pathlib import Path

class AppleARError(RuntimeError): pass

_USDC_MAGIC=b'PXR-USDC'

def _require_usdc_payload(data:bytes):
    if len(data)<16: raise AppleARError('usdc_too_small')
    if not data.startswith(_USDC_MAGIC): raise AppleARError('usdc_bad_magic')

def package_usdc(usdc_path,out_path):
    src=Path(usdc_path); out=Path(out_path)
    if not src.is_file(): raise AppleARError(f'usdc_missing:{src}')
    data=src.read_bytes(); _require_usdc_payload(data)
    name=b'model.usdc'; crc=zlib.crc32(data)&0xffffffff
    tm=time.localtime(); dos_time=((tm.tm_hour&31)<<11)|((tm.tm_min&63)<<5)|((tm.tm_sec//2)&31); dos_date=(((tm.tm_year-1980)&127)<<9)|((tm.tm_mon&15)<<5)|(tm.tm_mday&31)
    base=30+len(name)
    pad=(-base)%64
    extra=b''
    if pad:
        if pad<4: pad+=64
        extra=struct.pack('<HH',0xFFFF,pad-4)+b'\0'*(pad-4)
    local=struct.pack('<IHHHHHIIIHH',0x04034b50,20,0,0,dos_time,dos_date,crc,len(data),len(data),len(name),len(extra))+name+extra
    central=struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,20,20,0,0,dos_time,dos_date,crc,len(data),len(data),len(name),0,0,0,0,0,0)+name
    cd_offset=len(local)+len(data)
    end=struct.pack('<IHHHHIIH',0x06054b50,0,0,1,1,len(central),cd_offset,0)
    out.write_bytes(local+data+central+end)
    validate_usdz(out)
    return out

def validate_usdz(path):
    p=Path(path)
    if not p.is_file() or p.stat().st_size<64: raise AppleARError('usdz_missing_or_too_small')
    raw=p.read_bytes()
    if raw[:4]!=b'PK\x03\x04': raise AppleARError('usdz_bad_zip_header')
    name_len,extra_len=struct.unpack_from('<HH',raw,26)
    data_offset=30+name_len+extra_len
    if data_offset%64: raise AppleARError(f'usdz_payload_not_64_byte_aligned:{data_offset}')
    try:
        with zipfile.ZipFile(p,'r') as z:
            infos=z.infolist()
            if len(infos)!=1: raise AppleARError(f'usdz_unexpected_member_count:{len(infos)}')
            info=infos[0]
            if info.compress_type!=zipfile.ZIP_STORED: raise AppleARError('usdz_compression_forbidden')
            if info.filename!='model.usdc': raise AppleARError('usdz_root_layer_missing')
            payload=z.read(info)
            _require_usdc_payload(payload)
            bad=z.testzip()
            if bad: raise AppleARError(f'usdz_crc_failed:{bad}')
    except zipfile.BadZipFile as exc: raise AppleARError('usdz_bad_zip') from exc
    return {'ok':True,'path':str(p),'size':p.stat().st_size,'root_layer':'model.usdc','payload_alignment':data_offset,'usdc_magic':_USDC_MAGIC.decode()}
