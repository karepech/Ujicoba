import requests, re, gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. KONFIGURASI SUMBER M3U & EPG
# ==========================================
EPG_URLS = [
    "https://raw.githubusercontent.com/AqFad2811/epg/main/indonesia.xml",
    "https://raw.githubusercontent.com/AqFad2811/epg/refs/heads/main/astro.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SPORTS.xml.gz"
]

MASTER_SOURCES = [
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/sports_combined.m3u",    
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/event_combined.m3u",     
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/indonesia_combined.m3u"  
]

OUTPUT_FILE = "live_matches_only.m3u"
LINK_UPCOMING = "https://bwifi.my.id/5menit.mp4"
L_STANDBY = "https://bwifi.my.id/live.mp4"
M3U_HEADER = '#EXTM3U url-tvg="https://www.open-epg.com/generate/bXxbrwUThe.xml" name="🔴 BAKUL WIFI SPORTS"'

# ==========================================
# 2. MESIN REGEX & FILTER 
# ==========================================
RX_CHAMPS = re.compile(r'\b(?:champions?\s*tv|ctv)\s*(\d+)\b')
RX_STARS = re.compile(r'\bsports?\s+stars?\b')
RX_SPOTV = re.compile(r'\bspo\s+tv\b')
RX_KUALITAS = re.compile(r'\b(hd|fhd|uhd|4k|8k|tv|hevc|raw|plus|max|sd|hq)\b')
RX_LIVE = re.compile(r'(?i)(\(l\)|\[l\]|\blive\b|\blangsung\b)')

def get_channel_number(text):
    nums = re.findall(r'\d+', text)
    return nums[0] if nums else '0'

def normalisasi(n):
    if not n: return ""
    n = n.lower().strip()
    n = RX_CHAMPS.sub(r'champions tv \1', n)
    n = RX_STARS.sub('sportstars', n)
    n = RX_SPOTV.sub('spotv', n)
    return RX_KUALITAS.sub('', n).strip()

def get_flag(n):
    n = n.lower()
    if any(x in n for x in [' au', 'aus', 'optus']): return "🇦🇺"
    if any(x in n for x in [' my', 'malaysia', 'astro']): return "🇲🇾"
    if any(x in n for x in [' sg', 'singapore', 'hub']): return "🇸🇬"
    if any(x in n for x in [' th', 'thai']): return "🇹🇭"
    if any(x in n for x in [' uk', 'english']): return "🇬🇧"
    if any(x in n for x in [' ar', 'mena', 'arab', 'premium']): return "🇸🇦"
    return "🇮🇩"

# --- FILTER CHANNEL ---
def is_sports_channel(name):
    n = name.lower()
    if 'astro' in n:
        haram = ['awani','ria','oasis','prima','rania','citra','hijrah','ceria','warna','shiq','vellithirai','vinmeen','box office', 'a-list']
        if any(x in n for x in haram): return False
        halal_astro = ['arena', 'supersport', 'grandstand', 'premier', 'cricket', 'badminton', 'football', 'golf', 'tennis', 'rugby', 'sport']
        return any(x in n for x in halal_astro)

    sports_keywords = ['bein', 'spotv', 'sport', 'soccer', 'champions', 'espn', 'arena bola', 'golf', 'tennis', 'motor', 'fight', 'wwe', 'tnt', 'sky', 'optus', 'hub', 'mola', 'vidio', 'cbs']
    return any(x in n for x in sports_keywords)

# --- BUKU HITAM ---
def is_allowed_event(title):
    if not title: return False
    t = title.lower()

    haram_inisial = ["(d)", "[d]", "(r)", "[r]", "(c)", "[c]", "hls", "hl ", "h/l", "rev ", "rep ", "del "]
    haram_en = ["replay", "delay", "re-run", "rerun", "recorded", "archives", "classic", "rewind", "encore", "highlights", "best of", "the best of", "compilation", "collection", "pre-match", "post-match", "build-up", "build up", "preview", "review", "road to", "kick-off show", "warm up", "magazine", "studio", "talk", "show", "update", "weekly", "planet", "mini match", "mini", "life", "documentary"]
    haram_id_my = ["tunda", "siaran tunda", "tertunda", "ulang", "siaran ulang", "tayangan ulang", "ulangan", "rakaman", "cuplikan", "cuplikan gol", "sorotan", "sorotan perlawanan", "rangkuman", "ringkasan", "kilas", "lensa", "jurnal", "terbaik", "aksi terbaik", "pilihan", "pemanasan", "menuju kick off", "pra-perlawanan", "pra perlawanan", "pasca-perlawanan", "sepak mula", "dokumenter", "obrolan", "bincang"]
    haram_sampah = ["berita", "news", "apa kabar", "religi", "quran", "mekkah", "makkah", "masterchef", "caribbean", "hex", "witchcraft", "cgtn", "arirang", "cctv", "cnn", "al jazeera", "lfctv", "mutv", "chelsea tv"]

    if any(x in t for x in haram_inisial + haram_en + haram_id_my + haram_sampah): 
        return False
    return True

# --- GEMBOK BENUA ---
def is_valid_kickoff(st, title):
    w = st.hour + (st.minute / 60.0)
    t = title.lower()

    if any(k in t for k in ['badminton','bwf','motogp','f1','qualifying','practice','nba',' fp1',' fp2',' q1','sesi']): 
        return True

    rules = [
        (['premier','champions league','serie a','la liga','bundesliga','ucl','uefa','fa cup'], w >= 18.0 or w <= 4.0),
        (['mls','major league','concacaf','libertadores','sudamericana','liga mx','brasileiro'], 2.0 <= w <= 11.5),
        (['j-league','k-league','afc','asian','aff','liga 1','bri liga','timnas'], 11.5 <= w <= 22.5),
        (['saudi','roshn','caf ','africa','afcon'], w >= 20.0 or w <= 6.5),
        (['a-league','nrl','afl'], 7.5 <= w <= 17.5)
    ]
    
    for keys, cond in rules:
        if any(k in t for k in keys): return cond
    
    return not (4.5 < w < 11.0 and " vs " not in t)

def parse_time(ts):
    if not ts: return None
    try:
        if len(ts) >= 19 and ('+' in ts or '-' in ts):
            dt = datetime.strptime(ts[:20].strip(), "%Y%m%d%H%M%S %z")
            return dt.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        return datetime.strptime(ts[:14], "%Y%m%d%H%M%S") + timedelta(hours=7)
    except Exception:
        return None

# ==========================================
# 3. PROSES EKSEKUSI UTAMA
# ==========================================
def main():
    now_wib = datetime.utcnow() + timedelta(hours=7)
    match_data = {}
    epg_chans, epg_logos = {}, {}
    limit_date = now_wib + timedelta(hours=24)

    ses = requests.Session()
    ses.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    print(f"Step 1: Sedot EPG (Jadwal 24 Jam Sampai: {limit_date.strftime('%d-%m-%Y %H:%M')} WIB)...")
    for url in EPG_URLS:
        try:
            r = ses.get(url, timeout=60).content
            root = ET.fromstring(gzip.decompress(r) if r[:2] == b'\x1f\x8b' else r)
            
            for ch in root.findall("channel"):
                cid, cn = ch.get("id"), ch.findtext("display-name")
                if cid and cn: 
                    epg_chans[cid] = cn.strip()
                    icon = ch.find("icon")
                    if icon is not None: epg_logos[cid] = icon.get("src")
                    
            for pg in root.findall("programme"):
                cid = pg.get("channel")
                if cid not in epg_chans: continue
                
                st, sp = parse_time(pg.get("start")), parse_time(pg.get("stop"))
                if not st or not sp: continue
                
                if sp <= now_wib: continue 
                if st >= limit_date: continue 
                
                title = pg.findtext("title") or ""
                
                if not is_allowed_event(title): continue
                if not is_valid_kickoff(st, title): continue
                
                is_live = (st - timedelta(minutes=5)) <= now_wib < sp
                
                if cid not in match_data: match_data[cid] = []
                match_data[cid].append({
                    "title": RX_LIVE.sub('', title).strip(),
                    "start": st,
                    "stop": sp,
                    "live": is_live,
                    "logo": pg.find("icon").get("src") if pg.find("icon") is not None else ""
                })
        except Exception:
            continue

    print("Step 2: Merakit M3U (HANYA YANG ADA EPG)...")
    hasil_m3u = []
    up_tracker = set()
    
    for idx, url in enumerate(MASTER_SOURCES, 1):
        try:
            lines = ses.get(url, timeout=30).text.splitlines()
            block = []
            for ln in lines:
                ln_clean = ln.strip()
                if not ln_clean or "EXTM3U" in ln_clean.upper(): continue
                
                if ln_clean.startswith("#"):
                    if ln_clean.upper().startswith("#EXTINF"):
                        if any(t.upper().startswith("#EXTINF") for t in block):
                            block = [] 
                    block.append(ln_clean) 
                else:
                    stream_url = ln_clean
                    extinf_idx = next((i for i, t in enumerate(block) if t.upper().startswith("#EXTINF")), -1)
                    
                    if extinf_idx != -1:
                        raw_extinf = block[extinf_idx]
                        if "," in raw_extinf:
                            raw_attrs, m3u_name = raw_extinf.split(",", 1)
                            m3u_name = m3u_name.strip()
                            
                            if is_sports_channel(m3u_name):
                                # 1. Sedot Logo Asli M3U (Buat Jaga-Jaga)
                                logo_match = re.search(r'(?i)tvg-logo=["\']([^"\']*)["\']', raw_attrs)
                                orig_logo = logo_match.group(1) if logo_match else ""

                                # 2. Bersihkan atribut HATI-HATI (Amankan #EXTINF)
                                clean_attr = re.sub(r'(?i)\s*(group-title|tvg-id|tvg-logo|tvg-name)=["\'][^"\']*["\']', '', raw_attrs).strip()
                                if not clean_attr.upper().startswith("#EXTINF"):
                                    clean_attr = "#EXTINF:-1 " + clean_attr.replace('#EXTINF:-1', '').replace('#EXTINF:0', '').strip()

                                flag = get_flag(m3u_name)
                                n_m3u = normalisasi(m3u_name)
                                num_m3u = get_channel_number(n_m3u)
                                
                                matched_cid = None
                                for cid, ename in epg_chans.items():
                                    n_epg = normalisasi(ename)
                                    if n_epg == n_m3u or (n_epg in n_m3u and len(n_epg) > 4):
                                        if get_channel_number(n_epg) == num_m3u:
                                            matched_cid = cid
                                            break
                                
                                # HANYA MASUK JIKA ADA JADWAL DI EPG
                                if matched_cid and matched_cid in match_data:
                                    for ev in match_data[matched_cid]:
                                        jam = f"{ev['start'].strftime('%H:%M')}-{ev['stop'].strftime('%H:%M')} WIB"
                                        
                                        # HIERARKI LOGO: EPG Program -> EPG Channel -> Logo M3U Asli Karepech
                                        final_logo = ev['logo'] if ev.get('logo') else (epg_logos.get(matched_cid) if epg_logos.get(matched_cid) else orig_logo)
                                        
                                        if ev["live"]:
                                            # LIVE: BEBAS DUPLIKAT
                                            judul = f"{flag} 🔴 {jam} - {ev['title']} [{m3u_name}] ({idx})"
                                            live_block = list(block) 
                                            live_block[extinf_idx] = f'{clean_attr} group-title="🔴 SEDANG TAYANG" tvg-id="{matched_cid}" tvg-logo="{final_logo}", {judul}'
                                            hasil_m3u.append({"order": 0, "sort_name": m3u_name, "block_data": live_block + [stream_url]})
                                            
                                        else:
                                            # UPCOMING: GEMBOK KETAT (1 Acara = 1 Baris)
                                            up_key = f"{matched_cid}_{ev['start'].timestamp()}"
                                            if up_key in up_tracker: continue
                                            up_tracker.add(up_key)
                                            
                                            lbl = "Besok " if ev['start'].date() == (now_wib.date() + timedelta(days=1)) else ""
                                            judul = f"{flag} ⏳ {lbl}{jam} - {ev['title']} ({idx})"
                                            up_extinf = f'{clean_attr} group-title="📅 AKAN TAYANG" tvg-id="{matched_cid}" tvg-logo="{final_logo}", {judul}'
                                            hasil_m3u.append({"order": 1, "sort_name": str(ev['start'].timestamp()), "block_data": [up_extinf, LINK_UPCOMING]})
                                            
                    block = [] 
        except Exception as e:
            continue

    print("Step 3: Rendering Playlist TiviMate...")
    hasil_m3u.sort(key=lambda x: (x["order"], x["sort_name"].lower()))
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(M3U_HEADER + '\n')
        if not hasil_m3u: 
            f.write(f'#EXTINF:-1 group-title="ℹ️ INFO", BELUM ADA PERTANDINGAN\n{L_STANDBY}\n')
        for item in hasil_m3u: 
            f.write("\n".join(item["block_data"]) + "\n")

    print(f"Selesai! {len(hasil_m3u)} Jadwal Siap Meluncur ke TiviMate.")

if __name__ == "__main__": main()
