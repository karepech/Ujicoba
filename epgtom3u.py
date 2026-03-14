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

# 3 Sumber M3U Karepech (Sesuai Permintaan)
MASTER_SOURCES = [
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/sports_combined.m3u",    # (1)
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/event_combined.m3u",     # (2)
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/indonesia_combined.m3u"  # (3)
]

OUTPUT_FILE = "live_matches_only.m3u"
M3U_HEADER = '#EXTM3U url-tvg="https://www.open-epg.com/generate/bXxbrwUThe.xml" name="🔴 BAKUL WIFI SPORTS"'

# ==========================================
# 2. MESIN REGEX & FILTER 
# ==========================================
RX_CHAMPS = re.compile(r'\b(?:champions?\s*tv|ctv)\s*(\d+)\b')
RX_STARS = re.compile(r'\bsports?\s+stars?\b')
RX_SPOTV = re.compile(r'\bspo\s+tv\b')
RX_KUALITAS = re.compile(r'\b(hd|fhd|uhd|4k|8k|tv|hevc|raw|plus|max|sd|hq)\b')
RX_LIVE = re.compile(r'(?i)(\(l\)|\[l\]|\blive\b|\blangsung\b)')
RX_ATTR = re.compile(r'\s*(group-title|tvg-id|tvg-name|tvg-logo)="[^"]*"')

def normalisasi(n):
    if not n: return ""
    n = n.lower().strip()
    n = RX_CHAMPS.sub(r'champions tv \1', n)
    n = RX_STARS.sub('sportstars', n)
    n = RX_SPOTV.sub('spotv', n)
    n = RX_KUALITAS.sub('', n).strip()
    return n

def get_flag(n):
    n = n.lower()
    if any(x in n for x in [' au', 'aus', 'optus']): return "🇦🇺"
    if any(x in n for x in [' my', 'malaysia', 'astro']): return "🇲🇾"
    if any(x in n for x in [' sg', 'singapore', 'hub']): return "🇸🇬"
    if any(x in n for x in [' th', 'thai']): return "🇹🇭"
    if any(x in n for x in [' uk', 'english']): return "🇬🇧"
    if any(x in n for x in [' ar', 'mena', 'arab', 'premium']): return "🇸🇦"
    return "🇮🇩"

# --- A. FILTER CHANNEL (SPORTS & ASTRO WHITELIST) ---
def is_sports_channel(name):
    n = name.lower()
    if 'astro' in n:
        haram = ['awani','ria','oasis','prima','rania','citra','hijrah','ceria','warna','shiq','vellithirai','vinmeen','box office', 'a-list']
        if any(x in n for x in haram): return False
        halal_astro = ['arena', 'supersport', 'grandstand', 'premier', 'cricket', 'badminton', 'football', 'golf', 'tennis', 'rugby', 'sport']
        if not any(x in n for x in halal_astro): return False
        return True

    sports_keywords = ['bein', 'spotv', 'sport', 'soccer', 'champions', 'espn', 'arena bola', 'golf', 'tennis', 'motor', 'fight', 'wwe', 'tnt', 'sky', 'optus', 'hub', 'mola', 'vidio', 'cbs']
    return any(x in n for x in sports_keywords)

# --- B. FILTER BUKU HITAM (ANTI SIARAN ULANG & SAMPAH) ---
def is_allowed_event(title):
    if not title: return False
    t = title.lower()

    # 1. Inisial & Singkatan
    haram_inisial = ["(d)", "[d]", "(r)", "[r]", "(c)", "[c]", "hls", "hl ", "h/l", "rev ", "rep ", "del "]
    if any(x in t for x in haram_inisial): return False

    # 2. Bahasa Inggris (Replay, HL, Talkshow)
    haram_en = [
        "replay", "delay", "re-run", "rerun", "recorded", "archives", "classic", "rewind", "encore",
        "highlights", "best of", "the best of", "compilation", "collection",
        "pre-match", "post-match", "build-up", "build up", "preview", "review", "road to", 
        "kick-off show", "warm up", "magazine", "studio", "talk", "show", "update", "weekly", "planet"
    ]
    if any(x in t for x in haram_en): return False

    # 3. Bahasa Indonesia & Malaysia (Tunda, Ulang, Sorotan)
    haram_id_my = [
        "tunda", "siaran tunda", "tertunda", "ulang", "siaran ulang", "tayangan ulang", "ulangan",
        "rakaman", "cuplikan", "cuplikan gol", "sorotan", "sorotan perlawanan", "rangkuman", 
        "ringkasan", "kilas", "lensa", "jurnal", "terbaik", "aksi terbaik", "pilihan",
        "pemanasan", "menuju kick off", "pra-perlawanan", "pra perlawanan", "pasca-perlawanan", "sepak mula"
    ]
    if any(x in t for x in haram_id_my): return False

    # 4. Sampah Non-Olahraga
    haram_sampah = [
        "berita", "news", "apa kabar", "religi", "quran", "mekkah", "makkah", "masterchef", 
        "caribbean", "hex", "witchcraft", "cgtn", "arirang", "cctv", "cnn", "al jazeera",
        "lfctv", "mutv", "chelsea tv"
    ]
    if any(x in t for x in haram_sampah): return False

    return True

def parse_time(ts):
    if not ts: return None
    try:
        if len(ts) >= 19 and ('+' in ts or '-' in ts):
            dt = datetime.strptime(ts[:20].strip(), "%Y%m%d%H%M%S %z")
            return dt.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        else:
            return datetime.strptime(ts[:14], "%Y%m%d%H%M%S") + timedelta(hours=7)
    except Exception:
        return None

# ==========================================
# 3. PROSES EKSEKUSI UTAMA
# ==========================================
def main():
    now_wib = datetime.utcnow() + timedelta(hours=7)
    epg_chans, epg_logos, current_events = {}, {}, {}
    
    ses = requests.Session()
    ses.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

    print("Step 1: Sedot EPG (Mencari acara SAAT INI yang Lolos Filter)...")
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
                
                title = pg.findtext("title") or ""
                # TEMBAK MATI: Buang acara kalau masuk daftar haram!
                if not is_allowed_event(title): continue
                
                st = parse_time(pg.get("start"))
                sp = parse_time(pg.get("stop"))
                if not st or not sp: continue
                
                # REAL-TIME: Hanya simpan yang sedang tayang
                if (st - timedelta(minutes=5)) <= now_wib < sp:
                    clean_title = RX_LIVE.sub('', title).strip()
                    current_events[cid] = {
                        "title": clean_title,
                        "start": st,
                        "stop": sp,
                        "logo": pg.find("icon").get("src") if pg.find("icon") is not None else ""
                    }
        except Exception as e:
            print(f"Peringatan EPG: {e}")
            continue

    # Membuat Kamus Cerdas Pencocokan Channel
    epg_smart_map = {}
    for cid, ename in epg_chans.items():
        epg_smart_map[normalisasi(ename)] = cid

    print("Step 2: Sedot M3U Karepech (Blok Penuh & Eksekusi Anti-Rungseb)...")
    hasil_m3u = []
    url_tracker = set()
    
    for idx, url in enumerate(MASTER_SOURCES, 1):
        try:
            lines = ses.get(url, timeout=30).text.splitlines()
            block = []
            for ln in lines:
                ln_clean = ln.strip()
                if not ln_clean or "EXTM3U" in ln_clean.upper(): continue
                
                # PAWANG M3U: Mengamankan 1 Blok Penuh (Termasuk Token/User-Agent)
                if ln_clean.upper().startswith("#EXTINF"):
                    if any(t.upper().startswith("#EXTINF") for t in block):
                        block = [] 
                    block.append(ln_clean)
                elif ln_clean.startswith("#"): 
                    block.append(ln_clean)
                else:
                    stream_url = ln_clean
                    extinf_idx = -1
                    
                    # Cari lokasi baris #EXTINF di dalam blok
                    for i, t in enumerate(block):
                        if t.upper().startswith("#EXTINF"):
                            extinf_idx = i
                            break
                    
                    if extinf_idx != -1:
                        extinf_line = block[extinf_idx]
                        if "," in extinf_line:
                            raw_attrs, m3u_name = extinf_line.split(",", 1)
                            m3u_name = m3u_name.strip()
                            
                            # Filter 1: Harus Channel Olahraga
                            if not is_sports_channel(m3u_name):
                                block = []
                                continue
                                
                            # Filter 2: Gembok URL Anti-Spam
                            if stream_url in url_tracker:
                                block = []
                                continue
                            url_tracker.add(stream_url)
                            
                            # Bersihkan Atribut untuk ditulis ulang
                            clean_attr = RX_ATTR.sub('', raw_attrs).replace('#EXTINF:-1', '').strip()
                            flag = get_flag(m3u_name)
                            
                            # Pencocokan Instan KTP Channel
                            matched_cid = None
                            n_m3u = normalisasi(m3u_name)
                            
                            if n_m3u in epg_smart_map:
                                matched_cid = epg_smart_map[n_m3u]
                            else:
                                for n_epg, cid in epg_smart_map.items():
                                    if len(n_epg) > 4 and n_epg in n_m3u:
                                        matched_cid = cid
                                        break
                            
                            # LOGIKA ANTI-RUNGSEB & REAL-TIME
                            # Jika jadwal tersedia DAN sedang tayang, TAMPILKAN! Jika tidak, BUANG!
                            if matched_cid and matched_cid in current_events:
                                ev = current_events[matched_cid]
                                jam = f"{ev['start'].strftime('%H:%M')}-{ev['stop'].strftime('%H:%M')} WIB"
                                logo = ev['logo'] or epg_logos.get(matched_cid, "")
                                
                                judul = f"{flag} 🔴 {jam} - {ev['title']} [{m3u_name}] ({idx})"
                                block[extinf_idx] = f'#EXTINF:-1 {clean_attr} group-title="🔴 SPORTS SEDANG TAYANG" tvg-id="{matched_cid}" tvg-logo="{logo}", {judul}'
                                
                                # Simpan 1 blok utuh beserta URL-nya
                                hasil_m3u.append({"sort_name": m3u_name, "block_data": block + [stream_url]})
                            
                    block = [] # Reset blok untuk membaca channel selanjutnya
        except Exception as e:
            print(f"Peringatan M3U: {e}")
            continue

    print("Step 3: Menyimpan Playlist Bakul Wifi...")
    hasil_m3u.sort(key=lambda x: x["sort_name"].lower())
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(M3U_HEADER + '\n')
        if not hasil_m3u: 
            f.write(f'#EXTINF:-1 group-title="ℹ️ INFO", BELUM ADA PERTANDINGAN SAAT INI\n{L_STANDBY}\n')
        for item in hasil_m3u: 
            f.write("\n".join(item["block_data"]) + "\n")

    print(f"🔥 SUKSES! {len(hasil_m3u)} Channel Olahraga AKTIF berhasil diproses.")

if __name__ == "__main__": main()
